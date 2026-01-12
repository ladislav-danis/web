"""
Database API
(part of web.py)

This module provides a database interface for various database backends including
PostgreSQL, MySQL, SQLite, and others. It offers a consistent API for database
operations such as queries, inserts, updates, and deletes.

The module supports different database drivers and provides utilities for
parameter interpolation, SQL query building, and transaction management.

Examples:
    >>> # This is a conceptual example. A real database connection is needed.
    >>> # import web.db
    >>> # db = web.db.database(dbn='sqlite', db=':memory:')
    >>> # db.query("CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT)")
    -1
    >>> # db.insert('users', name='Alice')
    1
    >>> # list(db.select('users'))
    [<storage {'id': 1, 'name': 'Alice'}>]
"""

import ast
import datetime
import logging
import os
import re
import time
from types import ModuleType
from typing import (
    Any,
    Dict,
    Iterable,
    Iterator,
    List,
    Optional,
    Set,
    Tuple,
    Type,
    Union,
)
from urllib.parse import unquote, urlparse

from .py3helpers import iteritems
from .utils import iters, safestr, safeunicode, storage, threadeddict

try:
    # db module can work independent of web.py
    from .webapi import config, debug
except ImportError:
    import sys

    debug = sys.stderr
    config = storage()

__all__ = [
    "UnknownParamstyle",
    "UnknownDB",
    "TransactionError",
    "sqllist",
    "sqlors",
    "reparam",
    "sqlquote",
    "SQLQuery",
    "SQLParam",
    "sqlparam",
    "SQLLiteral",
    "sqlliteral",
    "database",
    "DB",
]

TOKEN = "[ \\f\\t]*(\\\\\\r?\\n[ \\f\\t]*)*(#[^\\r\\n]*)?(((\\d+[jJ]|((\\d+\\.\\d*|\\.\\d+)([eE][-+]?\\d+)?|\\d+[eE][-+]?\\d+)[jJ])|((\\d+\\.\\d*|\\.\\d+)([eE][-+]?\\d+)?|\\d+[eE][-+]?\\d+)|(0[xX][\\da-fA-F]+[lL]?|0[bB][01]+[lL]?|(0[oO][0-7]+)|(0[0-7]*)[lL]?|[1-9]\\d*[lL]?))|((\\*\\*=?|>>=?|<<=?|<>|!=|//=?|[+\\-*/%&|^=<>]=?|~)|[][(){}]|(\\r?\\n|[:;.,`@]))|([uUbB]?[rR]?'[^\\n'\\\\]*(?:\\\\.[^\\n'\\\\]*)*'|[uUbB]?[rR]?\"[^\\n\"\\\\]*(?:\\\\.[^\\n\"\\\\]*)*\")|[a-zA-Z_]\\w*)"

tokenprog = re.compile(TOKEN)

# Supported db drivers.
pg_drivers = ("psycopg2",)
mysql_drivers = ("pymysql", "MySQLdb", "mysql.connector")
sqlite_drivers = ("sqlite3", "pysqlite2.dbapi2", "sqlite")


class UnknownDB(Exception):
    """Raised for unsupported database management systems."""

    pass


class _ItplError(ValueError):
    """Internal error for string interpolation failures."""

    def __init__(self, text: str, pos: int) -> None:
        """Initializes the interpolation error.

        Args:
            text: The text where the error occurred.
            pos: The character position of the error.
        """
        super().__init__()
        self.text = text
        self.pos = pos

    def __str__(self) -> str:
        """Returns a string representation of the error."""
        return f"unfinished expression in {repr(self.text)} at char {self.pos}"


class TransactionError(Exception):
    """Raised for errors during a database transaction."""

    pass


class UnknownParamstyle(Exception):
    """Raised for unsupported DB API paramstyles.

    Currently supported styles are: qmark, numeric, format, pyformat.
    """

    pass


class SQLParam:
    """Represents a parameter in an SQLQuery.

    This class encapsulates a value that will be substituted into an SQL query,
    handling various parameter styles required by different database drivers.

    Args:
        value: The value to be used as a parameter in the SQL query.

    Examples:
        >>> q = SQLQuery(["SELECT * FROM test WHERE name=", SQLParam("joe")])
        >>> q
        <sql: "SELECT * FROM test WHERE name='joe'">
        >>> q.query()
        'SELECT * FROM test WHERE name=%s'
        >>> q.values()
        ['joe']
    """

    __slots__ = ["value"]

    def __init__(self, value: Any) -> None:
        """Initializes the SQL parameter.

        Args:
            value: The parameter value.
        """
        self.value = value

    def get_marker(self, paramstyle: str = "pyformat") -> str:
        """Gets the parameter marker for a given parameter style.

        Args:
            paramstyle: The parameter style to use. Supported styles are
                'qmark', 'numeric', 'format', and 'pyformat'.

        Returns:
            The appropriate parameter marker string for the given style.

        Raises:
            UnknownParamstyle: If the provided paramstyle is not supported.
        """
        if paramstyle == "qmark":
            return "?"
        elif paramstyle == "numeric":
            return ":1"
        elif paramstyle is None or paramstyle in ["format", "pyformat"]:
            return "%s"
        raise UnknownParamstyle(paramstyle)

    def sqlquery(self) -> "SQLQuery":
        """Converts this SQLParam to an SQLQuery.

        Returns:
            A new SQLQuery containing only this parameter.
        """
        return SQLQuery([self])

    def __add__(self, other: Any) -> "SQLQuery":
        """Adds this parameter to another query component."""
        return self.sqlquery() + other

    def __radd__(self, other: Any) -> "SQLQuery":
        """Adds another query component to this parameter."""
        return other + self.sqlquery()

    def __str__(self) -> str:
        """Returns the string representation of the parameter's value."""
        return str(self.value)

    def __eq__(self, other: Any) -> bool:
        """Checks for equality with another SQLParam."""
        return isinstance(other, SQLParam) and other.value == self.value

    def __repr__(self) -> str:
        """Returns the formal representation of the SQLParam."""
        return f"<param: {repr(self.value)}>"


sqlparam = SQLParam


class SQLQuery:
    """Represents an SQL query with parameters.

    This class allows for the programmatic construction of SQL queries by
    combining strings and SQL parameters. It handles parameter interpolation
    for different database drivers, preventing SQL injection vulnerabilities.

    Args:
        items: The initial items for the query. Can be a list of strings
            and parameters, a single parameter, another SQLQuery, or a string.

    Attributes:
        items (List[Union[str, SQLParam]]): The internal list of query components.

    Examples:
        >>> SQLQuery("x")
        <sql: 'x'>
        >>> q = SQLQuery(['SELECT * FROM ', 'test', ' WHERE x=', SQLParam(1)])
        >>> q
        <sql: 'SELECT * FROM test WHERE x=1'>
        >>> q.query(), q.values()
        ('SELECT * FROM test WHERE x=%s', [1])
        >>> SQLQuery(SQLParam(1))
        <sql: '1'>
    """

    __slots__ = ["items"]

    def __init__(
        self, items: Optional[Union[list, SQLParam, "SQLQuery", str]] = None
    ) -> None:
        """Initializes the SQLQuery.

        Args:
            items: The initial components of the query.
        """
        if items is None:
            self.items: List[Union[str, SQLParam]] = []
        elif isinstance(items, list):
            self.items = items
        elif isinstance(items, SQLParam):
            self.items = [items]
        elif isinstance(items, SQLQuery):
            self.items = list(items.items)
        else:
            self.items = [items]

        # Take care of SQLLiterals
        for i, item in enumerate(self.items):
            if isinstance(item, SQLParam) and isinstance(item.value, SQLLiteral):
                self.items[i] = item.value.v

    def append(self, value: Any) -> None:
        """Appends a value to the query items.

        Args:
            value: The value to append to the query.
        """
        self.items.append(value)

    def __add__(self, other: Union[str, "SQLQuery"]) -> "SQLQuery":
        """Concatenates this query with another component."""
        if isinstance(other, str):
            items = [other]
        elif isinstance(other, SQLQuery):
            items = other.items
        else:
            return NotImplemented
        return SQLQuery(self.items + items)

    def __radd__(self, other: Union[str, "SQLQuery"]) -> "SQLQuery":
        """Concatenates another component with this query."""
        if isinstance(other, str):
            items = [other]
        elif isinstance(other, SQLQuery):
            items = other.items
        else:
            return NotImplemented
        return SQLQuery(items + self.items)

    def __iadd__(self, other: Union[str, SQLParam, "SQLQuery"]) -> "SQLQuery":
        """Appends another component to this query in-place."""
        if isinstance(other, (str, SQLParam)):
            self.items.append(other)
        elif isinstance(other, SQLQuery):
            self.items.extend(other.items)
        else:
            return NotImplemented
        return self

    def __len__(self) -> int:
        """Returns the length of the rendered query string.

        Returns:
            The length of the query string.
        """
        return len(self.query())

    def __eq__(self, other: Any) -> bool:
        """Checks for equality with another SQLQuery.

        Args:
            other: Another object to compare with.

        Returns:
            True if both queries have the same items, False otherwise.
        """
        return isinstance(other, SQLQuery) and other.items == self.items

    def query(self, paramstyle: Optional[str] = None) -> str:
        """Returns the query string with parameter markers.

        Args:
            paramstyle: The parameter style to use ('qmark', 'numeric',
                'format', 'pyformat'). Defaults to the driver's style.

        Returns:
            The SQL query string with parameters substituted by markers.

        Examples:
            >>> q = SQLQuery(["SELECT * FROM test WHERE name=", SQLParam('joe')])
            >>> q.query()
            'SELECT * FROM test WHERE name=%s'
            >>> q.query(paramstyle='qmark')
            'SELECT * FROM test WHERE name=?'
        """
        s = []
        for x in self.items:
            if isinstance(x, SQLParam):
                x = x.get_marker(paramstyle)
                s.append(safestr(x))
            else:
                x = safestr(x)
                # automatically escape % characters in the query
                if paramstyle in ["format", "pyformat"]:
                    if "%" in x and "%%" not in x:
                        x = x.replace("%", "%%")
                s.append(x)
        return "".join(s)

    def values(self) -> List[Any]:
        """Returns the parameter values for the SQL query.

        Returns:
            A list of parameter values.

        Examples:
            >>> q = SQLQuery(["SELECT * FROM test WHERE name=", SQLParam('joe')])
            >>> q.values()
            ['joe']
        """
        return [i.value for i in self.items if isinstance(i, SQLParam)]

    @staticmethod
    def join(
        items: Iterable[Any],
        sep: str = " ",
        prefix: Optional[str] = None,
        suffix: Optional[str] = None,
        target: Optional["SQLQuery"] = None,
    ) -> "SQLQuery":
        """Joins multiple query components into a single SQLQuery.

        Args:
            items: A list of items to join.
            sep: Separator to place between items. Defaults to " ".
            prefix: A string to add before the joined items.
            suffix: A string to add after the joined items.
            target: An existing SQLQuery to append to. If None, a new one is created.

        Returns:
            A new or modified SQLQuery with the joined items.

        Examples:
            >>> SQLQuery.join(['a', 'b'], ', ')
            <sql: 'a, b'>
            >>> SQLQuery.join(['a', 'b'], ', ', prefix='(', suffix=')')
            <sql: '(a, b)'>
        """
        if target is None:
            target = SQLQuery()

        target_items = target.items

        if prefix:
            target_items.append(prefix)

        for i, item in enumerate(items):
            if i != 0 and sep != "":
                target_items.append(sep)
            if isinstance(item, SQLQuery):
                target_items.extend(item.items)
            elif item == "":  # joins with empty strings
                continue
            else:
                target_items.append(item)

        if suffix:
            target_items.append(suffix)
        return target

    def _str(self) -> str:
        """Internal helper to render the full query string with values."""
        try:
            return self.query() % tuple(sqlify(x) for x in self.values())
        except (ValueError, TypeError):
            return self.query()

    def __str__(self) -> str:
        """Returns the query with values interpolated (for debugging)."""
        return safestr(self._str())

    def __unicode__(self) -> str:
        """Returns the unicode query with values interpolated."""
        return safeunicode(self._str())

    def __repr__(self) -> str:
        """Returns the formal representation of the SQLQuery."""
        return f"<sql: {repr(str(self))}>"


class SQLLiteral:
    """Protects a string from being quoted by `sqlquote`.

    This class is used to wrap strings that should be treated as literal SQL,
    such as function calls (`NOW()`) or other expressions, preventing them
    from being escaped or quoted as string values.

    Args:
        v: The literal SQL string to protect.

    Examples:
        >>> sqlquote('NOW()')
        <sql: "'NOW()'">
        >>> sqlquote(SQLLiteral('NOW()'))
        <sql: 'NOW()'>
    """

    def __init__(self, v: str) -> None:
        """Initializes the SQL literal.

        Args:
            v: The literal SQL string.
        """
        self.v = v

    def __repr__(self) -> str:
        """Returns the formal representation of the SQLLiteral."""
        return f"<literal: {repr(self.v)}>"


sqlliteral = SQLLiteral


def _sqllist(values: Union[List[Any], Set[Any], Tuple[Any, ...]]) -> SQLQuery:
    """Converts a Python collection into an SQL list expression.

    This function takes a list, set, or tuple and converts it into a SQL
    expression like `(val1, val2, ...)`.

    Args:
        values: A list, set, or tuple of values to convert.

    Returns:
        An SQLQuery object representing the SQL list expression.

    Examples:
        >>> _sqllist([1, 2, 3])
        <sql: '(1, 2, 3)'>
        >>> _sqllist({1, 2, 3, 5})
        <sql: '(1, 2, 3, 5)'>
        >>> _sqllist((5, 1, 3, 2, 2, 5))
        <sql: '(1, 2, 3, 5)'>
    """
    items: List[Any] = ["("]
    processed_values: List[Any]

    if isinstance(values, set):
        processed_values = sorted(list(values))
    elif isinstance(values, tuple):
        # Using dict.fromkeys to preserve order and remove duplicates
        processed_values = list(dict.fromkeys(values))
    else:
        processed_values = values

    for i, v in enumerate(processed_values):
        if i != 0:
            items.append(", ")
        items.append(sqlparam(v))
    items.append(")")
    return SQLQuery(items)


def reparam(string_: str, dictionary: Dict[str, Any]) -> SQLQuery:
    """Interpolates a string with a dictionary, returning an `SQLQuery`.

    This function safely substitutes variables in an SQL-like string (e.g., `$name`)
    with values from a dictionary. It handles various data types, converting
    collections to SQL list expressions.

    Args:
        string_: The string template with variables to interpolate.
        dictionary: A dictionary mapping variable names to their values.

    Returns:
        An SQLQuery object with interpolated values.

    Examples:
        >>> reparam("s = $s", dict(s=True))
        <sql: "s = 't'">
        >>> reparam("s IN $s", dict(s=[1, 2]))
        <sql: 's IN (1, 2)'>
    """
    return SafeEval().safeeval(string_, dictionary)


def sqlify(obj: Any) -> str:
    """Converts a Python object to its proper SQL string representation.

    This function is primarily for debugging and rendering queries, converting
    Python types like `None` and `bool` to their SQL equivalents (`NULL`, `'f'`).

    Args:
        obj: The Python object to convert.

    Returns:
        The SQL string representation of the object.

    Examples:
        >>> sqlify(None)
        'NULL'
        >>> sqlify(True)
        "'t'"
        >>> sqlify(3)
        '3'
    """
    if obj is None:
        return "NULL"
    elif obj is True:
        return "'t'"
    elif obj is False:
        return "'f'"
    elif isinstance(obj, int):
        return str(obj)
    elif isinstance(obj, datetime.datetime):
        return repr(obj.isoformat())
    else:
        return repr(obj)


def sqllist(lst: Union[str, List[str]]) -> str:
    """Converts a list into a comma-separated SQL list string.

    This is a simple utility for creating comma-separated lists for clauses
    like `FROM table1, table2`. For value lists, use `sqlquote`.

    Args:
        lst: A list of items or a single string.

    Returns:
        A comma-separated string representation.

    Examples:
        >>> sqllist(['a', 'b'])
        'a, b'
        >>> sqllist('a')
        'a'
    """
    if isinstance(lst, str):
        return lst
    else:
        return ", ".join(lst)


def sqlors(left: str, lst: Any) -> SQLQuery:
    """Creates an SQL OR clause from a left-hand side and a list of values.

    Generates an expression like `(left val1 OR left val2 OR ...)`.

    Args:
        left: The left-hand side of the clause (e.g., 'tablename.col = ').
        lst: A list of values or a single value to be OR'd.

    Returns:
        An SQLQuery object representing the OR expression.

    Examples:
        >>> sqlors('foo = ', [])
        <sql: '1=2'>
        >>> sqlors('foo = ', [1])
        <sql: 'foo = 1'>
        >>> sqlors('foo = ', 1)
        <sql: 'foo = 1'>
        >>> sqlors('foo = ', [1,2,3])
        <sql: '(foo = 1 OR foo = 2 OR foo = 3 OR 1=2)'>
    """
    if isinstance(lst, iters):
        lst = list(lst)
        ln = len(lst)
        if ln == 0:
            return SQLQuery("1=2")
        if ln == 1:
            lst = lst[0]

    if isinstance(lst, iters):
        return SQLQuery(
            ["("] + sum(([left, sqlparam(x), " OR "] for x in lst), []) + ["1=2)"]
        )
    else:
        return SQLQuery([left, sqlparam(lst)])


def sqlwhere(data: Iterable[Tuple[str, Any]], grouping: str = " AND ") -> SQLQuery:
    """Converts an iterable of (key, value) pairs to an SQL WHERE clause.

    Args:
        data: An iterable of (key, value) tuples representing conditions.
        grouping: The operator to join conditions (default: " AND ").

    Returns:
        An SQLQuery object representing the WHERE clause.

    Examples:
        >>> sqlwhere((('cust_id', 2), ('order_id',3)))
        <sql: 'cust_id = 2 AND order_id = 3'>
        >>> sqlwhere((('order_id', 3), ('cust_id', 2)), grouping=', ')
        <sql: 'order_id = 3, cust_id = 2'>
        >>> sqlwhere((('a', 'a'), ('b', 'b'))).query()
        'a = %s AND b = %s'
    """
    return SQLQuery.join([k + " = " + sqlparam(v) for k, v in data], grouping)


def sqlquote(a: Any) -> SQLQuery:
    """Ensures a value is properly quoted for use in an SQL query.

    This function safely handles various data types, including lists, tuples,
    and sets, converting them into properly parameterized SQL constructs.

    Args:
        a: The value to be quoted (can be a single value or a collection).

    Returns:
        An SQLQuery object with the properly quoted value(s).

    Examples:
        >>> 'WHERE x = ' + sqlquote(True)
        <sql: "WHERE x = 't'">
        >>> 'WHERE y IN ' + sqlquote([2, 3])
        <sql: 'WHERE y IN (2, 3)'>
        >>> 'WHERE z IN ' + sqlquote({2, 3, 4})
        <sql: 'WHERE z IN (2, 3, 4)'>
    """
    if isinstance(a, (list, tuple, set)):
        return _sqllist(a)
    else:
        return sqlparam(a).sqlquery()


class BaseResultSet:
    """Base implementation for the result of a database query.

    This class provides the core functionality for iterating over query results
    and accessing individual rows. It manages the database cursor.

    Args:
        cursor: The database cursor object used to fetch results.

    Attributes:
        cursor: The database cursor.
        names: A list of column names from the query result.
    """

    def __init__(self, cursor: Any) -> None:
        """Initializes the result set.

        Args:
            cursor: The database cursor from the executed query.
        """
        self.cursor = cursor
        self.names = [x[0] for x in cursor.description]
        self._index = 0

    def list(self) -> List[storage]:
        """Returns all rows from the result set as a list.

        Returns:
            A list of `storage` objects, each representing a row.
        """
        rows = [self._prepare_row(d) for d in self.cursor.fetchall()]
        self._index += len(rows)
        return rows

    def _prepare_row(self, row: tuple) -> storage:
        """Converts a single row tuple into a `storage` object.

        Args:
            row: A tuple representing a single row from the database.

        Returns:
            A `storage` object with column names as keys.
        """
        return storage(dict(zip(self.names, row)))

    def __iter__(self) -> "BaseResultSet":
        """Makes the result set iterable.

        Returns:
            Itself as the iterator.
        """
        return self

    def __next__(self) -> storage:
        """Returns the next row from the result set.

        Returns:
            The next row as a `storage` object.

        Raises:
            StopIteration: When there are no more rows.
        """
        row = self.cursor.fetchone()
        if row is None:
            raise StopIteration()
        self._index += 1
        return self._prepare_row(row)

    next = __next__  # Python 2.7 compatibility

    def first(self, default: Any = None) -> Any:
        """Returns the first row or a default value if the result is empty.

        Args:
            default: The value to return if the result set is empty.

        Returns:
            The first row as a `storage` object, or the default value.
        """
        try:
            return next(iter(self))
        except StopIteration:
            return default

    def __getitem__(self, i: int) -> storage:
        """Gets a specific row by index.

        Args:
            i: The index of the row to retrieve.

        Returns:
            The row at the specified index as a `storage` object.

        Raises:
            IndexError: If the index is out of range or has already been passed.
        """
        if i < self._index:
            raise IndexError(f"already passed {i}")
        try:
            while i > self._index:
                next(self)
            # now self._index == i
            return next(self)
        except StopIteration:
            raise IndexError(str(i))


class ResultSet(BaseResultSet):
    """The result of a database query, supporting `len()`."""

    def __len__(self) -> int:
        """Returns the number of rows in the result set.

        Note: This may not be supported by all database drivers.

        Returns:
            The number of rows in the result set.
        """
        return int(self.cursor.rowcount)


class SqliteResultSet(BaseResultSet):
    """Result Set for SQLite.

    This is the same as ResultSet but does not support `len()`.
    """

    def __init__(self, cursor: Any) -> None:
        """Initializes the SQLite result set.

        Args:
            cursor: The SQLite database cursor.
        """
        super().__init__(cursor)
        self._head: Optional[storage] = None

    def __next__(self) -> storage:
        """Returns the next row from the result set.

        Returns:
            The next row as a `storage` object.

        Raises:
            StopIteration: When there are no more rows.
        """
        if self._head is not None:
            row = self._head
            self._head = None
            return row
        else:
            return super().__next__()

    def __bool__(self) -> bool:
        """Checks if the result set contains any rows.

        Returns:
            True if there are rows, False otherwise.
        """
        if self._head is None:
            try:
                self._head = super().__next__()
            except StopIteration:
                return False
        return True


class Transaction:
    """Manages a database transaction.

    This class supports both top-level and nested transactions (using savepoints)
    and is designed to be used with a `with` statement.

    Args:
        ctx: The thread-local context containing database connection info.
    """

    def __init__(self, ctx: threadeddict) -> None:
        """Initializes a new transaction.

        Args:
            ctx: The database context.
        """
        self.ctx = ctx
        self.transaction_count = len(ctx.transactions)

        class transaction_engine:
            def do_transact(self) -> None:
                ctx.commit(unload=False)

            def do_commit(self) -> None:
                ctx.commit()

            def do_rollback(self) -> None:
                ctx.rollback()

        class subtransaction_engine:
            def query(self, q: str) -> None:
                db_cursor = ctx.db.cursor()
                ctx.db_execute(db_cursor, SQLQuery(q % self.transaction_count))

            def do_transact(self) -> None:
                self.query("SAVEPOINT webpy_sp_%s")

            def do_commit(self) -> None:
                self.query("RELEASE SAVEPOINT webpy_sp_%s")

            def do_rollback(self) -> None:
                self.query("ROLLBACK TO SAVEPOINT webpy_sp_%s")

        class dummy_engine:
            def do_transact(self) -> None:
                pass

            def do_commit(self) -> None:
                pass

            def do_rollback(self) -> None:
                pass

        if self.transaction_count:
            if self.ctx.get("ignore_nested_transactions"):
                self.engine = dummy_engine()
            else:
                self.engine = subtransaction_engine()
        else:
            self.engine = transaction_engine()

        self.engine.do_transact()
        self.ctx.transactions.append(self)

    def __enter__(self) -> "Transaction":
        """Enters the runtime context for the transaction.

        Returns:
            The transaction object itself.
        """
        return self

    def __exit__(self, exctype: Any, excvalue: Any, traceback: Any) -> None:
        """Exits the runtime context, committing or rolling back.

        Args:
            exctype: The exception type if an exception occurred.
            excvalue: The exception value if an exception occurred.
            traceback: The traceback object if an exception occurred.
        """
        if exctype is not None:
            self.rollback()
        else:
            self.commit()

    def commit(self) -> None:
        """Commits the current transaction or savepoint."""
        if len(self.ctx.transactions) > self.transaction_count:
            self.engine.do_commit()
            self.ctx.transactions = self.ctx.transactions[: self.transaction_count]

    def rollback(self) -> None:
        """Rolls back the current transaction or savepoint."""
        if len(self.ctx.transactions) > self.transaction_count:
            self.engine.do_rollback()
            self.ctx.transactions = self.ctx.transactions[: self.transaction_count]


class DB:
    """A consistent database interface for web.py applications.

    This class provides a high-level API for database operations across
    different backends, handling connections, queries, and transactions.

    Args:
        db_module: The imported database driver module (e.g., psycopg2).
        keywords: A dictionary of database connection parameters.

    Attributes:
        db_module: The database driver module in use.
        keywords (Dict[str, Any]): The connection parameters.
        printing (bool): If True, SQL queries are printed for debugging.
        supports_multiple_insert (bool): If True, the backend supports multi-row inserts.
        has_pooling (bool): If True, connection pooling is enabled.
    """

    def __init__(self, db_module: ModuleType, keywords: Dict[str, Any]) -> None:
        """Initializes the database interface.

        Args:
            db_module: The database driver module.
            keywords: Connection parameters (host, user, password, etc.).
        """
        keywords.pop("driver", None)

        self.db_module = db_module
        self.keywords = keywords
        self.paramstyle: str = "pyformat"

        self._ctx = threadeddict()
        self.printing = config.get("debug_sql", config.get("debug", False))
        self.supports_multiple_insert = False

        try:
            import dbutils  # noqa: F401

            self.has_pooling = True
        except ImportError:
            self.has_pooling = False

        self.has_pooling = self.keywords.pop("pooling", True) and self.has_pooling

    @property
    def ctx(self) -> threadeddict:
        """Provides a thread-local context for the database connection."""
        if not self._ctx.get("db"):
            self._load_context(self._ctx)
        return self._ctx

    def _load_context(self, ctx: threadeddict) -> None:
        """Loads the database connection into the context."""
        ctx.dbq_count = 0
        ctx.transactions = []

        if self.has_pooling:
            ctx.db = self._connect_with_pooling(self.keywords)
        else:
            ctx.db = self._connect(self.keywords)
        ctx.db_execute = self._db_execute

        if not hasattr(ctx.db, "commit"):
            ctx.db.commit = lambda: None
        if not hasattr(ctx.db, "rollback"):
            ctx.db.rollback = lambda: None

        def commit(unload: bool = True) -> None:
            ctx.db.commit()
            if unload and self.has_pooling:
                self._unload_context(self._ctx)

        def rollback() -> None:
            ctx.db.rollback()
            if self.has_pooling:
                self._unload_context(self._ctx)

        ctx.commit = commit
        ctx.rollback = rollback

    def _unload_context(self, ctx: threadeddict) -> None:
        """Unloads the database connection from the context."""
        if hasattr(ctx, "db"):
            del ctx.db

    def _connect(self, keywords: Dict[str, Any]) -> Any:
        """Establishes a direct database connection."""
        return self.db_module.connect(**keywords)

    def _connect_with_pooling(self, keywords: Dict[str, Any]) -> Any:
        """Establishes a pooled database connection."""
        from dbutils import pooled_db as PooledDB

        if not hasattr(self, "_pooleddb"):
            self._pooleddb = PooledDB.PooledDB(creator=self.db_module, **keywords)
        return self._pooleddb.connection()

    def _db_cursor(self) -> Any:
        """Returns a new cursor from the current connection."""
        return self.ctx.db.cursor()

    def _db_execute(self, cur: Any, sql_query: SQLQuery) -> Any:
        """Executes an SQL query using the provided cursor."""
        self.ctx.dbq_count += 1
        try:
            a = time.time()
            query, params = self._process_query(sql_query)
            out = cur.execute(query, params)
            b = time.time()
        except Exception:
            logging.error("SQL Execution Error", exc_info=True)
            if self.printing:
                print(f"ERR: {str(sql_query)}", file=debug)
            if self.ctx.transactions:
                self.ctx.transactions[-1].rollback()
            else:
                self.ctx.rollback()
            raise

        if self.printing:
            duration = round(b - a, 2)
            print(f"{duration} ({self.ctx.dbq_count}): {str(sql_query)}", file=debug)
        return out

    def _process_query(self, sql_query: SQLQuery) -> Tuple[str, List[Any]]:
        """Processes an SQLQuery into a query string and parameter list."""
        paramstyle = getattr(self, "paramstyle", "pyformat")
        query = sql_query.query(paramstyle)
        params = sql_query.values()
        return query, params

    def _where(
        self, where: Any, vars: Dict[str, Any]
    ) -> Union[SQLQuery, str]:
        """Constructs a WHERE clause from various input types."""
        if isinstance(where, int):
            return SQLQuery(["id = ", sqlparam(where)])
        elif isinstance(where, dict):
            return self._where_dict(where)
        elif isinstance(where, SQLQuery):
            return where
        else:
            return reparam(where, vars)

    def _where_dict(self, where: Dict[str, Any]) -> Optional[SQLQuery]:
        """Converts a dictionary to a WHERE clause."""
        clauses = [k + " = " + sqlquote(v) for k, v in sorted(where.items())]
        return SQLQuery.join(clauses, " AND ") if clauses else None

    def query(
        self,
        sql_query: Union[str, SQLQuery],
        vars: Optional[Dict[str, Any]] = None,
        processed: bool = False,
        _test: bool = False,
    ) -> Union[ResultSet, int, SQLQuery]:
        """Executes an SQL query.

        Args:
            sql_query: The SQL query string or SQLQuery object.
            vars: A dictionary of variables to interpolate into the query.
            processed: If True, `sql_query` is assumed to be fully processed.
            _test: If True, returns the generated SQLQuery without execution.

        Returns:
            A ResultSet for SELECT queries, row count for other queries, or
            the SQLQuery object if _test is True.

        Examples:
            >>> db = DB(None, {})
            >>> db.query("SELECT * FROM foo", _test=True)
            <sql: 'SELECT * FROM foo'>
            >>> db.query("SELECT * FROM foo WHERE x = $x", vars=dict(x='f'), _test=True)
            <sql: "SELECT * FROM foo WHERE x = 'f'">
        """
        if vars is None:
            vars = {}

        if not processed and not isinstance(sql_query, SQLQuery):
            sql_query_obj = reparam(sql_query, vars)
        else:
            sql_query_obj = SQLQuery(sql_query)

        if _test:
            return sql_query_obj

        db_cursor = self._db_cursor()
        self._db_execute(db_cursor, sql_query_obj)

        if db_cursor.description:
            out: Union[ResultSet, int] = self.create_result_set(db_cursor)
        else:
            out = db_cursor.rowcount

        if not self.ctx.transactions:
            self.ctx.commit()
        return out

    def create_result_set(self, cursor: Any) -> ResultSet:
        """Creates a ResultSet from a cursor."""
        return ResultSet(cursor)

    def select(
        self,
        tables: Union[str, List[str]],
        vars: Optional[Dict[str, Any]] = None,
        what: str = "*",
        where: Any = None,
        order: Optional[str] = None,
        group: Optional[str] = None,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
        _test: bool = False,
    ) -> Union[ResultSet, int, SQLQuery]:
        """Builds and executes a SELECT query.

        Args:
            tables: The table(s) to select from.
            vars: Dictionary of variables for interpolation.
            what: The columns to select (e.g., 'id, name').
            where: The WHERE clause.
            order: The ORDER BY clause.
            group: The GROUP BY clause.
            limit: The LIMIT clause.
            offset: The OFFSET clause.
            _test: If True, returns the generated SQLQuery without execution.

        Returns:
            A ResultSet, or the SQLQuery object if _test is True.

        Examples:
            >>> db = DB(None, {})
            >>> db.select('foo', _test=True)
            <sql: 'SELECT * FROM foo'>
            >>> db.select(['foo', 'bar'], where="foo.bar_id = bar.id", limit=5, _test=True)
            <sql: 'SELECT * FROM foo, bar WHERE foo.bar_id = bar.id LIMIT 5'>
        """
        if vars is None:
            vars = {}

        sql_clauses = self.sql_clauses(what, tables, where, group, order, limit, offset)
        clauses = [
            self.gen_clause(sql, val, vars)
            for sql, val in sql_clauses
            if val is not None
        ]
        qout = SQLQuery.join(clauses)

        if _test:
            return qout
        return self.query(qout, processed=True)

    def where(
        self,
        table: str,
        what: str = "*",
        order: Optional[str] = None,
        group: Optional[str] = None,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
        _test: bool = False,
        **kwargs: Any,
    ) -> Union[ResultSet, int, SQLQuery]:
        """Selects from a table using key-value pairs for the WHERE clause.

        Args:
            table: The table to select from.
            what: The columns to select.
            order: The ORDER BY clause.
            group: The GROUP BY clause.
            limit: The LIMIT clause.
            offset: The OFFSET clause.
            _test: If True, returns the generated SQLQuery without execution.
            **kwargs: Key-value pairs for the WHERE clause (e.g., id=5).

        Returns:
            A ResultSet, or the SQLQuery object if _test is True.

        Examples:
            >>> db = DB(None, {})
            >>> db.where('foo', bar_id=3, _test=True)
            <sql: 'SELECT * FROM foo WHERE bar_id = 3'>
        """
        where = self._where_dict(kwargs)
        return self.select(
            table,
            what=what,
            where=where,
            order=order,
            group=group,
            limit=limit,
            offset=offset,
            _test=_test,
        )

    def sql_clauses(
        self,
        what: str,
        tables: Union[str, List[str]],
        where: Any,
        group: Optional[str],
        order: Optional[str],
        limit: Optional[int],
        offset: Optional[int],
    ) -> List[Tuple[str, Any]]:
        """Generates a list of SQL clauses for a SELECT statement."""
        return [
            ("SELECT", what),
            ("FROM", sqllist(tables)),
            ("WHERE", where),
            ("GROUP BY", group),
            ("ORDER BY", order),
            ("LIMIT", limit and SQLParam(limit).sqlquery()),
            ("OFFSET", offset and SQLParam(offset).sqlquery()),
        ]

    def gen_clause(self, sql: str, val: Any, vars: Dict[str, Any]) -> SQLQuery:
        """Generates a single SQL clause."""
        nout: Union[SQLQuery, str]
        if sql == "WHERE" and isinstance(val, int):
            nout = SQLQuery(["id = ", sqlquote(val)])
        elif sql == "WHERE" and isinstance(val, dict):
            nout = self._where_dict(val)
        elif isinstance(val, SQLQuery):
            nout = val
        else:
            nout = reparam(str(val), vars)

        return SQLQuery(f"{sql} {nout}") if sql and nout else SQLQuery(nout)

    def insert(
        self,
        tablename: str,
        seqname: Union[str, bool, None] = None,
        _test: bool = False,
        **values: Any,
    ) -> Union[int, None, SQLQuery]:
        """Inserts a new row into a table.

        Args:
            tablename: The name of the table.
            seqname: The name of the sequence for the primary key, or False if none.
            _test: If True, returns the generated SQLQuery without execution.
            **values: Key-value pairs for the columns to insert.

        Returns:
            The ID of the newly inserted row, None, or the SQLQuery if _test is True.

        Examples:
            >>> db = DB(None, {})
            >>> q = db.insert('foo', name='bob', age=2, created=SQLLiteral('NOW()'), _test=True)
            >>> q
            <sql: "INSERT INTO foo (age, created, name) VALUES (2, NOW(), 'bob')">
        """
        if values:
            sorted_values = sorted(values.items())
            _keys = SQLQuery.join(map(lambda t: t[0], sorted_values), ", ")
            _values = SQLQuery.join(
                [sqlparam(v) for v in map(lambda t: t[1], sorted_values)], ", "
            )
            sql_query = SQLQuery(
                f"INSERT INTO {tablename} ({_keys}) VALUES ({_values})"
            )
        else:
            sql_query = SQLQuery(self._get_insert_default_values_query(tablename))

        if _test:
            return sql_query

        db_cursor = self._db_cursor()
        if seqname is not False:
            processed_query = self._process_insert_query(sql_query, tablename, seqname)
        else:
            processed_query = sql_query

        if isinstance(processed_query, tuple):
            q1, q2 = processed_query
            self._db_execute(db_cursor, q1)
            self._db_execute(db_cursor, q2)
        else:
            self._db_execute(db_cursor, processed_query)

        try:
            out: Optional[int] = db_cursor.fetchone()[0]
        except Exception:
            out = None

        if not self.ctx.transactions:
            self.ctx.commit()
        return out

    def _get_insert_default_values_query(self, table: str) -> str:
        """Returns the query for an insert with no values."""
        return f"INSERT INTO {table} DEFAULT VALUES"

    def multiple_insert(
        self,
        tablename: str,
        values: List[Dict[str, Any]],
        seqname: Union[str, bool, None] = None,
        _test: bool = False,
    ) -> Union[List[int], None, SQLQuery]:
        """Inserts multiple rows into a table in a single query.

        Args:
            tablename: The name of the table.
            values: A list of dictionaries, where each dict represents a row.
            seqname: The name of the sequence for the primary key.
            _test: If True, returns the generated SQLQuery without execution.

        Returns:
            A list of IDs for the inserted rows, None, or the SQLQuery if _test is True.

        Examples:
            >>> db = DB(None, {})
            >>> db.supports_multiple_insert = True
            >>> vals = [{"name": "foo", "email": "foo@example.com"}, {"name": "bar", "email": "bar@example.com"}]
            >>> db.multiple_insert('person', values=vals, _test=True)
            <sql: "INSERT INTO person (email, name) VALUES ('foo@example.com', 'foo'), ('bar@example.com', 'bar')">
        """
        if not values:
            return []

        if not self.supports_multiple_insert:
            out = [
                self.insert(tablename, seqname=seqname, _test=_test, **v)
                for v in values
            ]
            return None if seqname is False else out

        keys = sorted(values[0].keys())
        for v in values:
            if sorted(v.keys()) != keys:
                raise ValueError("Not all rows have the same keys")

        sql_query = SQLQuery(f"INSERT INTO {tablename} ({', '.join(keys)}) VALUES ")

        for i, row in enumerate(values):
            if i != 0:
                sql_query.append(", ")
            SQLQuery.join(
                [SQLParam(row[k]) for k in keys],
                sep=", ",
                target=sql_query,
                prefix="(",
                suffix=")",
            )

        if _test:
            return sql_query

        db_cursor = self._db_cursor()
        processed_query = self._process_insert_query(sql_query, tablename, seqname)

        if isinstance(processed_query, tuple):
            q1, q2 = processed_query
            self._db_execute(db_cursor, q1)
            self._db_execute(db_cursor, q2)
        else:
            self._db_execute(db_cursor, processed_query)

        try:
            first_id = db_cursor.fetchone()[0]
            if self.db_module.__name__ in mysql_drivers:
                result_ids: Optional[List[int]] = list(range(first_id, first_id + len(values)))
            else:
                result_ids = list(range(first_id - len(values) + 1, first_id + 1))
        except Exception:
            result_ids = None

        if not self.ctx.transactions:
            self.ctx.commit()
        return result_ids

    def update(
        self,
        tables: Union[str, List[str]],
        where: Any,
        vars: Optional[Dict[str, Any]] = None,
        _test: bool = False,
        **values: Any,
    ) -> Union[int, SQLQuery]:
        """Updates rows in a table.

        Args:
            tables: The table(s) to update.
            where: The WHERE clause to identify rows.
            vars: Dictionary of variables for `where` clause interpolation.
            _test: If True, returns the generated SQLQuery without execution.
            **values: Key-value pairs to set for the updated rows.

        Returns:
            The number of rows updated, or the SQLQuery if _test is True.

        Examples:
            >>> db = DB(None, {})
            >>> name = 'Joseph'
            >>> q = db.update('foo', where='name = $name', name='bob', age=2, created=SQLLiteral('NOW()'), vars=locals(), _test=True)
            >>> q
            <sql: "UPDATE foo SET age = 2, created = NOW(), name = 'bob' WHERE name = 'Joseph'">
        """
        if vars is None:
            vars = {}

        where_clause = self._where(where, vars)
        sorted_values = sorted(values.items())

        query = SQLQuery(
            [
                "UPDATE ",
                sqllist(tables),
                " SET ",
                sqlwhere(sorted_values, ", "),
                " WHERE ",
                where_clause,
            ]
        )

        if _test:
            return query

        db_cursor = self._db_cursor()
        self._db_execute(db_cursor, query)
        if not self.ctx.transactions:
            self.ctx.commit()
        return db_cursor.rowcount

    def delete(
        self,
        table: str,
        where: Any,
        using: Optional[Union[str, List[str]]] = None,
        vars: Optional[Dict[str, Any]] = None,
        _test: bool = False,
    ) -> Union[int, SQLQuery]:
        """Deletes rows from a table.

        Args:
            table: The table to delete from.
            where: The WHERE clause to identify rows.
            using: The USING clause (for joins in deletes).
            vars: Dictionary of variables for `where` clause interpolation.
            _test: If True, returns the generated SQLQuery without execution.

        Returns:
            The number of rows deleted, or the SQLQuery if _test is True.

        Examples:
            >>> db = DB(None, {})
            >>> name = 'Joe'
            >>> db.delete('foo', where='name = $name', vars=locals(), _test=True)
            <sql: "DELETE FROM foo WHERE name = 'Joe'">
        """
        if vars is None:
            vars = {}

        where_clause = self._where(where, vars)
        q_parts = [f"DELETE FROM {table}"]
        if using:
            q_parts.append(f" USING {sqllist(using)}")
        if where_clause:
            q_parts.append(" WHERE ")
            q_parts.append(where_clause)

        query = SQLQuery(q_parts)

        if _test:
            return query

        db_cursor = self._db_cursor()
        self._db_execute(db_cursor, query)
        if not self.ctx.transactions:
            self.ctx.commit()
        return db_cursor.rowcount

    def _process_insert_query(
        self, query: SQLQuery, tablename: str, seqname: Union[str, bool, None]
    ) -> Union[SQLQuery, Tuple[SQLQuery, SQLQuery]]:
        """Hook for database-specific insert query processing."""
        return query

    def transaction(self) -> Transaction:
        """Starts a new database transaction.

        Returns:
            A Transaction object, to be used in a `with` statement.
        """
        return Transaction(self.ctx)


class PostgresDB(DB):
    """PostgreSQL database driver."""

    def __init__(self, **keywords: Any) -> None:
        """Initializes the PostgreSQL connection.

        Args:
            **keywords: Connection parameters. `pw` is an alias for `password`,
                and `db` is an alias for `database`.
        """
        if "pw" in keywords:
            keywords["password"] = keywords.pop("pw")
        if "db" in keywords:
            keywords["database"] = keywords.pop("db")

        db_module = import_driver(pg_drivers, preferred=keywords.pop("driver", None))
        if db_module.__name__ == "psycopg2":
            import psycopg2.extensions
            psycopg2.extensions.register_type(psycopg2.extensions.UNICODE)

        self.dbname = "postgres"
        self.paramstyle = db_module.paramstyle
        super().__init__(db_module, keywords)
        self.supports_multiple_insert = True
        self._sequences: Optional[Set[str]] = None

    def _process_insert_query(
        self, query: SQLQuery, tablename: str, seqname: Union[str, bool, None]
    ) -> SQLQuery:
        """Appends a `RETURNING id` or `currval` query for PostgreSQL."""
        if seqname is None:
            seqname = f"{tablename}_id_seq"
            if seqname not in self._get_all_sequences():
                seqname = None

        if seqname:
            query += self.get_sequence_query(str(seqname))
        return query

    def get_sequence_query(self, seqname: str) -> SQLQuery:
        """Creates a query to get the current value of a sequence."""
        if not re.match(r"^[a-zA-Z_][a-zA-Z0-9_$]*$", seqname):
            raise ValueError(f"Invalid sequence name: {seqname}")
        return SQLQuery(f"; SELECT currval('{seqname}')")

    def _get_all_sequences(self) -> Set[str]:
        """Queries PostgreSQL for all sequence names in the database."""
        if self._sequences is None:
            q = "SELECT c.relname FROM pg_class c WHERE c.relkind = 'S'"
            self._sequences = {c.relname for c in self.query(q)}
        return self._sequences

    def _connect(self, keywords: Dict[str, Any]) -> Any:
        """Connects to PostgreSQL and sets client encoding."""
        conn = super()._connect(keywords)
        conn.set_client_encoding("UTF8")
        return conn

    def _connect_with_pooling(self, keywords: Dict[str, Any]) -> Any:
        """Connects with pooling and sets client encoding."""
        conn = super()._connect_with_pooling(keywords)
        conn._con._con.set_client_encoding("UTF8")
        return conn


class MySQLDB(DB):
    """MySQL/MariaDB database driver."""

    def __init__(self, **keywords: Any) -> None:
        """Initializes the MySQL connection.

        Args:
            **keywords: Connection parameters. `pw` is an alias for `password`.
        """
        db_module = import_driver(mysql_drivers, preferred=keywords.pop("driver", None))

        if "pw" in keywords:
            if db_module.__name__ == "MySQLdb":
                keywords["passwd"] = keywords.pop("pw")
            else:  # pymysql, mysql.connector
                keywords["password"] = keywords.pop("pw")

        if db_module.__name__ == "mysql.connector":
            keywords.setdefault("buffered", True)

        keywords.setdefault("charset", "utf8")
        if keywords["charset"] is None:
            del keywords["charset"]

        self.paramstyle = "pyformat"
        self.dbname = "mysql"
        super().__init__(db_module, keywords)
        self.supports_multiple_insert = True

    def _process_insert_query(
        self, query: SQLQuery, tablename: str, seqname: Union[str, bool, None]
    ) -> Tuple[SQLQuery, SQLQuery]:
        """Appends a query to get the last inserted ID for MySQL."""
        return query, SQLQuery("SELECT last_insert_id();")

    def _get_insert_default_values_query(self, table: str) -> str:
        """Returns the query for an insert with no values for MySQL."""
        return f"INSERT INTO {table} () VALUES()"


def import_driver(drivers: Tuple[str, ...], preferred: Optional[str] = None) -> ModuleType:
    """Imports the first available database driver from a list.

    Args:
        drivers: A tuple of driver names to try.
        preferred: A specific driver to try first.

    Returns:
        The imported driver module.

    Raises:
        ImportError: If no suitable driver can be imported.
    """
    driver_list = (preferred,) if preferred else drivers
    for d in driver_list:
        try:
            return __import__(d, None, None, ["x"])
        except ImportError:
            pass
    raise ImportError(f"Unable to import {' or '.join(drivers)}")


class SqliteDB(DB):
    """SQLite database driver."""

    def __init__(self, **keywords: Any) -> None:
        """Initializes the SQLite connection.

        Args:
            **keywords: Connection parameters. `db` is used for the database file path.
        """
        db_module = import_driver(sqlite_drivers, preferred=keywords.pop("driver", None))

        if db_module.__name__ in ["sqlite3", "pysqlite2.dbapi2"]:
            db_module.paramstyle = "qmark"
            keywords.setdefault("detect_types", db_module.PARSE_DECLTYPES)

        self.dbname = "sqlite"
        self.paramstyle = db_module.paramstyle
        keywords["database"] = keywords.pop("db")
        keywords["pooling"] = False  # SQLite doesn't allow connection sharing

        super().__init__(db_module, keywords)

    def _process_insert_query(
        self, query: SQLQuery, tablename: str, seqname: Union[str, bool, None]
    ) -> Tuple[SQLQuery, SQLQuery]:
        """Appends a query to get the last inserted row ID for SQLite."""
        return query, SQLQuery("SELECT last_insert_rowid();")

    def create_result_set(self, cursor: Any) -> SqliteResultSet:
        """Creates a SqliteResultSet from a cursor."""
        return SqliteResultSet(cursor)


class FirebirdDB(DB):
    """Firebird database driver."""

    def __init__(self, **keywords: Any) -> None:
        """Initializes the Firebird connection.

        Args:
            **keywords: Connection parameters. `pw` is an alias for `password`,
                and `db` is an alias for `database`.
        """
        try:
            import kinterbasdb as db
        except ImportError:
            raise
        if "pw" in keywords:
            keywords["password"] = keywords.pop("pw")
        keywords["database"] = keywords.pop("db")

        self.paramstyle = db.paramstyle
        super().__init__(db, keywords)

    def delete(
        self,
        table: str,
        where: Any,
        using: Optional[Union[str, List[str]]] = None,
        vars: Optional[Dict[str, Any]] = None,
        _test: bool = False,
    ) -> Union[int, SQLQuery]:
        """Deletes from a table. Firebird does not support the USING clause."""
        return super().delete(table, where, using=None, vars=vars, _test=_test)

    def sql_clauses(
        self,
        what: str,
        tables: Union[str, List[str]],
        where: Any,
        group: Optional[str],
        order: Optional[str],
        limit: Optional[int],
        offset: Optional[int],
    ) -> List[Tuple[str, Any]]:
        """Generates SQL clauses for Firebird, using FIRST and SKIP for limit/offset."""
        return [
            ("SELECT", ""),
            ("FIRST", limit),
            ("SKIP", offset),
            ("", what),
            ("FROM", sqllist(tables)),
            ("WHERE", where),
            ("GROUP BY", group),
            ("ORDER BY", order),
        ]


class MSSQLDB(DB):
    """Microsoft SQL Server database driver."""

    def __init__(self, **keywords: Any) -> None:
        """Initializes the MS SQL Server connection.

        Args:
            **keywords: Connection parameters. `pw` is an alias for `password`,
                and `db` is an alias for `database`.
        """
        import pymssql as db

        if "pw" in keywords:
            keywords["password"] = keywords.pop("pw")
        keywords["database"] = keywords.pop("db")
        self.dbname = "mssql"
        super().__init__(db, keywords)

    def _process_query(self, sql_query: SQLQuery) -> Tuple[str, Tuple[Any, ...]]:
        """Processes query, ensuring parameters are a tuple for pymssql."""
        paramstyle = getattr(self, "paramstyle", "pyformat")
        query = sql_query.query(paramstyle)
        params = sql_query.values()
        return query, tuple(params)

    def sql_clauses(
        self,
        what: str,
        tables: Union[str, List[str]],
        where: Any,
        group: Optional[str],
        order: Optional[str],
        limit: Optional[int],
        offset: Optional[int],
    ) -> List[Tuple[str, Any]]:
        """Generates SQL clauses for MS SQL, using TOP for limit."""
        return [
            ("SELECT", what),
            ("TOP", limit),
            ("FROM", sqllist(tables)),
            ("WHERE", where),
            ("GROUP BY", group),
            ("ORDER BY", order),
            ("OFFSET", offset),
        ]

    def _test(self) -> None:
        """Test for the LIMIT to TOP clause conversion.

        Fake presence of pymssql module for running tests.
        >>> import sys
        >>> sys.modules['pymssql'] = sys.modules['sys']

        MSSQL has TOP clause instead of LIMIT clause.
        >>> db = MSSQLDB(db='test', user='joe', pw='secret')
        >>> db.select('foo', limit=4, _test=True)
        <sql: 'SELECT * TOP 4 FROM foo'>
        """
        pass


class OracleDB(DB):
    """Oracle database driver."""

    def __init__(self, **keywords: Any) -> None:
        """Initializes the Oracle connection.

        Args:
            **keywords: Connection parameters. `pw` is an alias for `password`,
                and `db` is used for the DSN.
        """
        import cx_Oracle as db

        if "pw" in keywords:
            keywords["password"] = keywords.pop("pw")

        keywords["dsn"] = keywords.pop("db")
        self.dbname = "oracle"
        db.paramstyle = "numeric"
        self.paramstyle = db.paramstyle

        keywords.pop("pooling", None)
        super().__init__(db, keywords)

    def _process_insert_query(
        self, query: SQLQuery, tablename: str, seqname: Union[str, bool, None]
    ) -> SQLQuery:
        """Appends a query to get the current sequence value for Oracle."""
        if seqname:
            return query + f"; SELECT {seqname}.currval FROM dual"
        return query


def dburl2dict(url: str) -> Dict[str, Any]:
    """Parses a database URL into a dictionary of connection parameters.

    Args:
        url: The database URL string (e.g., 'postgres://user:pw@host/db').

    Returns:
        A dictionary of connection parameters.

    Examples:
        >>> dburl2dict('postgres://james:day@server:5432/mygreatdb')
        {'dbn': 'postgres', 'user': 'james', 'pw': 'day', 'db': 'mygreatdb', 'host': 'server', 'port': 5432}
        >>> dburl2dict('sqlite:///path/to/db.sqlite')
        {'dbn': 'sqlite', 'db': '/path/to/db.sqlite'}
    """
    parts = urlparse(unquote(url))
    if parts.scheme == "sqlite":
        return {"dbn": parts.scheme, "db": parts.path[1:]}
    else:
        return {
            "dbn": parts.scheme,
            "user": parts.username,
            "pw": parts.password,
            "db": parts.path[1:],
            "host": parts.hostname,
            "port": parts.port,
        }


_databases: Dict[str, Type[DB]] = {}


def database(dburl: Optional[str] = None, **params: Any) -> DB:
    """Creates a database interface from a URL or keyword arguments.

    Connection pooling is enabled by default if the `dbutils` module is available.
    It can be disabled by passing `pooling=False`.

    Args:
        dburl: A database URL. If provided, it overrides `params`.
        **params: Keyword arguments for the connection (e.g., dbn, db, user).

    Returns:
        An initialized DB object for the specified database.

    Raises:
        UnknownDB: If the specified `dbn` is not registered.
        ValueError: If no connection info is provided.
    """
    if not dburl and not params:
        dburl = os.environ.get("DATABASE_URL")
        if not dburl:
            raise ValueError("DATABASE_URL env var not set or no params provided")

    if dburl:
        params = dburl2dict(dburl)

    dbn = params.pop("dbn")
    if dbn in _databases:
        return _databases[dbn](**params)
    else:
        raise UnknownDB(dbn)


def register_database(name: str, clazz: Type[DB]) -> None:
    """Registers a new database driver class.

    Args:
        name: The name to register the driver under (e.g., 'mysql').
        clazz: The DB subclass to associate with the name.

    Examples:
        >>> class MyCustomDB(DB): pass
        >>> register_database('custom', MyCustomDB)
    """
    _databases[name] = clazz


register_database("mysql", MySQLDB)
register_database("postgres", PostgresDB)
register_database("sqlite", SqliteDB)
register_database("firebird", FirebirdDB)
register_database("mssql", MSSQLDB)
register_database("oracle", OracleDB)


def _interpolate(format_str: str) -> List[Tuple[int, str]]:
    """Internal helper to parse a format string for interpolation.

    Takes a format string and returns a list of 2-tuples of the form
    (eval_flag, string) where eval_flag is 1 if the string should be
    evaluated, and 0 otherwise.

    From <http://lfw.org/python/Itpl.py> (public domain, Ka-Ping Yee).

    Args:
        format_str: The string to parse.

    Returns:
        A list of tuples for evaluation.
    """

    def matchorfail(text: str, pos: int) -> Tuple[re.Match, int]:
        match = tokenprog.match(text, pos)
        if match is None:
            raise _ItplError(text, pos)
        return match, match.end()

    namechars = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_"
    chunks: List[Tuple[int, str]] = []
    pos = 0

    while True:
        dollar = format_str.find("$", pos)
        if dollar < 0:
            break
        nextchar = format_str[dollar + 1]

        if nextchar == "{":
            chunks.append((0, format_str[pos:dollar]))
            pos, level = dollar + 2, 1
            while level:
                match, pos = matchorfail(format_str, pos)
                tstart, tend = match.regs[3]
                token = format_str[tstart:tend]
                if token == "{":
                    level += 1
                elif token == "}":
                    level -= 1
            chunks.append((1, format_str[dollar + 2 : pos - 1]))

        elif nextchar in namechars:
            chunks.append((0, format_str[pos:dollar]))
            match, pos = matchorfail(format_str, dollar + 1)
            while pos < len(format_str):
                if (
                    format_str[pos] == "."
                    and pos + 1 < len(format_str)
                    and format_str[pos + 1] in namechars
                ):
                    match, pos = matchorfail(format_str, pos + 1)
                elif format_str[pos] in "([":
                    pos, level = pos + 1, 1
                    while level:
                        match, pos = matchorfail(format_str, pos)
                        tstart, tend = match.regs[3]
                        token = format_str[tstart:tend]
                        if token[0] in "([":
                            level += 1
                        elif token[0] in ")]":
                            level -= 1
                else:
                    break
            chunks.append((1, format_str[dollar + 1 : pos]))
        else:
            chunks.append((0, format_str[pos : dollar + 1]))
            pos = dollar + 1 + (nextchar == "$")

    if pos < len(format_str):
        chunks.append((0, format_str[pos:]))
    return chunks


class _Node:
    """An internal node for the expression parser tree."""

    def __init__(self, type: str, first: Any, second: Any = None) -> None:
        """Initializes a parser node.

        Args:
            type: The type of the node (e.g., 'text', 'param').
            first: The primary value of the node.
            second: The secondary value, if any.
        """
        self.type = type
        self.first = first
        self.second = second

    def __eq__(self, other: Any) -> bool:
        """Checks for equality with another node."""
        return (
            isinstance(other, _Node)
            and self.type == other.type
            and self.first == other.first
            and self.second == other.second
        )

    def __repr__(self) -> str:
        """Returns the formal representation of the node."""
        return f"Node({self.type!r}, {self.first!r}, {self.second!r})"


class Parser:
    """Internal parser for string templates like "Hello $name".

    Loosely based on <http://lfw.org/python/Itpl.py> (public domain, Ka-Ping Yee).
    """

    namechars = "abcdefghijklmnopqrstuvwxyz" "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_"

    def __init__(self) -> None:
        """Initializes the parser."""
        self.reset()

    def reset(self) -> None:
        """Resets the parser's internal state."""
        self.pos = 0
        self.level = 0
        self.text = ""

    def parse(self, text: str) -> Iterator[_Node]:
        """Parses the given text and yields a sequence of nodes.

        Args:
            text: The template string to parse.

        Returns:
            An iterator of _Node objects representing the parsed tree.
        """
        self.reset()
        self.text = text
        return self.parse_all()

    def parse_all(self) -> Iterator[_Node]:
        """The main parsing loop."""
        while True:
            dollar = self.text.find("$", self.pos)
            if dollar < 0:
                break
            nextchar = self.text[dollar + 1]
            if nextchar in self.namechars:
                yield _Node("text", self.text[self.pos : dollar])
                self.pos = dollar + 1
                yield self.parse_expr()
            elif nextchar == "{":
                saved_pos = self.pos
                self.pos = dollar + 2
                expr = self.parse_expr()
                if self.text[self.pos] == "}":
                    self.pos += 1
                    yield _Node("text", self.text[saved_pos : dollar])
                    yield expr
                else:
                    self.pos = saved_pos
                    break
            else:
                yield _Node("text", self.text[self.pos : dollar + 1])
                self.pos = dollar + 1
                if nextchar == "$":
                    self.pos += 1
        if self.pos < len(self.text):
            yield _Node("text", self.text[self.pos :])

    def match(self) -> Tuple[re.Match, int]:
        """Matches the next token in the text."""
        match = tokenprog.match(self.text, self.pos)
        if match is None:
            raise _ItplError(self.text, self.pos)
        return match, match.end()

    def is_literal(self, text: str) -> bool:
        """Checks if a token is a literal value."""
        return text and text[0] in "0123456789\"'"

    def parse_expr(self) -> _Node:
        """Parses a single expression (e.g., $name.attribute)."""
        match, pos = self.match()
        if self.is_literal(match.group()):
            expr = _Node("literal", match.group())
        else:
            expr = _Node("param", self.text[self.pos : pos])
        self.pos = pos
        while self.pos < len(self.text):
            if (
                self.text[self.pos] == "."
                and self.pos + 1 < len(self.text)
                and self.text[self.pos + 1] in self.namechars
            ):
                self.pos += 1
                match, pos = self.match()
                attr = match.group()
                expr = _Node("getattr", expr, attr)
                self.pos = pos
            elif self.text[self.pos] == "[":
                saved_pos = self.pos
                self.pos += 1
                key = self.parse_expr()
                if self.text[self.pos] == "]":
                    self.pos += 1
                    expr = _Node("getitem", expr, key)
                else:
                    self.pos = saved_pos
                    break
            else:
                break
        return expr


class SafeEval:
    """A safe evaluator for binding parameters to database queries."""

    def safeeval(self, text: str, mapping: Dict[str, Any]) -> SQLQuery:
        """Safely evaluates a template string against a mapping.

        Args:
            text: The template string to evaluate.
            mapping: A dictionary of variables to use for substitution.

        Returns:
            An SQLQuery object with the evaluated result.
        """
        nodes = Parser().parse(text)
        return SQLQuery.join([self.eval_node(node, mapping) for node in nodes], "")

    def eval_node(self, node: _Node, mapping: Dict[str, Any]) -> Any:
        """Evaluates a single node from the parse tree."""
        if node.type == "text":
            return node.first
        else:
            return sqlquote(self.eval_expr(node, mapping))

    def eval_expr(self, node: _Node, mapping: Dict[str, Any]) -> Any:
        """Recursively evaluates an expression node."""
        if node.type == "literal":
            return ast.literal_eval(node.first)
        elif node.type == "getattr":
            return getattr(self.eval_expr(node.first, mapping), node.second)
        elif node.type == "getitem":
            return self.eval_expr(node.first, mapping)[
                self.eval_expr(node.second, mapping)
            ]
        elif node.type == "param":
            return mapping[node.first]


def test_parser() -> None:
    """Tests the internal Parser class."""

    def f(text: str, expected: List[_Node]) -> None:
        p = Parser()
        nodes = list(p.parse(text))
        print(repr(text), nodes)
        assert nodes == expected, f"Expected {expected!r}"

    f("Hello", [_Node("text", "Hello")])
    f("Hello $name", [_Node("text", "Hello "), _Node("param", "name")])
    f(
        "Hello $name.foo",
        [_Node("text", "Hello "), _Node("getattr", _Node("param", "name"), "foo")],
    )
    f(
        "WHERE id=$self.id LIMIT 1",
        [
            _Node("text", "WHERE id="),
            _Node("getattr", _Node("param", "self"), "id"),
            _Node("text", " LIMIT 1"),
        ],
    )
    f(
        "WHERE id=$self['id'] LIMIT 1",
        [
            _Node("text", "WHERE id="),
            _Node("getitem", _Node("param", "self"), _Node("literal", "'id'")),
            _Node("text", " LIMIT 1"),
        ],
    )


def test_safeeval() -> None:
    """Tests the internal SafeEval class."""

    def f(q: str, vars: Dict[str, Any]) -> SQLQuery:
        return SafeEval().safeeval(q, vars)

    print(f("WHERE id=$id", {"id": 1}).items)
    assert f("WHERE id=$id", {"id": 1}).items == ["WHERE id=", sqlparam(1)]


if __name__ == "__main__":
    import doctest

    doctest.testmod(optionflags=doctest.IGNORE_EXCEPTION_DETAIL | doctest.ELLIPSIS)
    test_parser()
    test_safeeval()