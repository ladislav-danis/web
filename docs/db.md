
# Web Database API Documentation

This document describes the database API implemented in `web/db.py`, which provides a unified interface for working with different database backends.

## Overview

The web.py database module provides a consistent API for database operations across different database systems including PostgreSQL, MySQL, SQLite, Firebird, Microsoft SQL Server, and Oracle. It handles connection management, query building, parameter interpolation, result set handling, and transaction management.

## Classes

### `UnknownDB`
Exception raised when an unsupported database backend is specified.

### `TransactionError`
Exception raised when database transaction operations fail.

### `_ItplError`
Internal exception raised by the SQL parser when it encounters an unfinished expression during interpolation.

### `UnknownParamstyle`
Exception raised for unsupported database parameter styles (qmark, numeric, format, pyformat).

### `SQLParam`
Represents a parameter in SQL queries. Used to safely inject values into SQL queries.

#### Constructor
```python
SQLParam(value)
```

#### Methods
- `get_marker(paramstyle)`: Returns the appropriate parameter marker for the given style (`?`, `:1`, or `%s`).
- `sqlquery()`: Returns an SQLQuery object containing this parameter.
- `__add__(other)`, `__radd__(other)`: Support for string concatenation with SQL queries.
- `__str__()`: Returns the string representation of the value.
- `__eq__(other)`: Compares with another SQLParam.
- `__repr__()`: Returns a debug representation.

#### Example
```python
>>> q = SQLQuery(["SELECT * FROM test WHERE name=", SQLParam("joe")])
>>> q.query()
'SELECT * FROM test WHERE name=%s'
>>> q.values()
['joe']
```

### `SQLQuery`
Represents a SQL query that can be built incrementally. Supports parameterized queries and safe SQL construction.

#### Constructor
```python
SQLQuery(items=None)
```

#### Methods
- `append(value)`: Appends a value to the query items.
- `__add__(other)`, `__radd__(other)`, `__iadd__(other)`: Support for query concatenation.
- `__len__()`: Returns the length of the query string.
- `__eq__(other)`: Compares with another SQLQuery.
- `query(paramstyle=None)`: Returns the SQL query string with parameter markers. Supports different paramstyles: `qmark` (?), `numeric` (:1), `format` (%s), `pyformat` (%s).
- `values()`: Returns the list of parameter values.
- `join(items, sep=" ", prefix=None, suffix=None, target=None)`: Static method that joins multiple queries with a separator.

#### Example
```python
>>> q = SQLQuery(['SELECT * FROM ', 'test', ' WHERE x=', SQLParam(1)])
>>> q.query()
'SELECT * FROM test WHERE x=%s'
>>> q.values()
[1]
```

### `SQLLiteral`
Protects a string from being escaped during SQL quoting. Useful for SQL functions and expressions.

#### Constructor
```python
SQLLiteral(v)
```

#### Methods
- `__repr__()`: Returns a string representation of the literal.

#### Example
```python
>>> sqlquote('NOW()')
<sql: "'NOW()'">
>>> sqlquote(SQLLiteral('NOW()'))
<sql: 'NOW()'>
```

### `BaseResultSet`
Base class for result sets returned by database queries. A result set is a
forward-only iterator, not a reusable sequence. Rows are storage objects with
both mapping and attribute access. Every consuming operation shares the same
position; none rewinds the cursor.

#### Constructor
```python
BaseResultSet(cursor)
```

#### Methods
- `list()`: Consumes and returns all **remaining** rows as a list. A subsequent call returns `[]`.
- `_prepare_row(row)`: Prepares a single row for return as a storage object.
- `__iter__()`: Returns the result set itself.
- `__next__()` / `next()`: Consumes the next row or raises `StopIteration` at the end. The compatibility method `result.next()` follows the same path as `next(result)`.
- `first(default=None)`: Consumes the next remaining row, or returns `default` if exhausted. Repeated calls advance; “first” does not mean the original first row after earlier consumption.
- `__getitem__(i)`: Consumes through the **absolute zero-based** position `i` in the original query result. For example, fresh `result[2]` discards positions 0 and 1 and returns position 2. The next read starts at position 3. Negative indices, already-consumed positions (including repeating the same index), and positions past the end raise `IndexError`. An out-of-range forward request consumes any intervening remaining rows before raising. Slices are not supported.

The internal `_index` counts rows actually consumed, including rows skipped by
forward indexing. Peeking, rejected backward indices and failed reads at the end
do not increment it. For reusable/random access, explicitly save the remaining
rows once with `rows = result.list()` and index that ordinary list instead.

### `ResultSet`
Result set implementation for most database backends (PostgreSQL, MySQL), with
the same forward-only consumption methods.

#### Methods
- `__len__()`: Returns `int(cursor.rowcount)` from the driver. This is not a separately maintained count of remaining rows; availability and meaning depend on the driver. Truth testing uses this length, unlike the SQLite peek described below. A raw SQLite SELECT cursor reports `-1`, so wrapping it in `ResultSet` does not provide a usable Python `len()`.

### `SqliteResultSet`
Result set returned by SQLite queries. SQLite SELECT cursors do not supply a
usable row count; `len(result)` is unsupported (`TypeError`). This does not
prevent consuming the remaining rows with `result.list()`.

#### Methods
- `__bool__()`: Peeks at the next remaining row. Repeated truth tests do not consume rows. Returns `False` on empty or exhausted results.
- `__next__()` and `list()`: Consume any peeked row exactly once before reading further rows from the cursor. This also applies to `next()`, `first()` and forward indexing, which share the same consumption path.

#### Executable SQLite example
This example uses an owned in-memory database, not an application database. The
explicit `ORDER BY` defines the row order used by the indices.

```python
import web

db = web.database(dbn="sqlite", db=":memory:")
try:
    sql = "SELECT n FROM (SELECT 1 AS n UNION ALL SELECT 2 UNION ALL SELECT 3 UNION ALL SELECT 4) ORDER BY n"
    result = db.query(sql)
    assert bool(result) and bool(result)  # Peek, without consuming position 0.
    assert next(result).n == 1
    assert result[2].n == 3               # Consume position 1, return position 2.
    assert result.first().n == 4          # The next remaining row, not row 1.
    assert result.first("empty") == "empty"
    assert not result

    remaining = db.query(sql)
    assert bool(remaining)
    rows = remaining.list()              # Includes the buffered first row once.
    assert [row.n for row in rows] == [1, 2, 3, 4]
    assert remaining.list() == []
    assert rows[2].n == 3                 # Reusable ordinary list.
finally:
    db.ctx.db.close()
```

### `Transaction`
Database transaction management class. Supports context manager protocol for automatic commit/rollback.

#### Constructor
```python
Transaction(ctx)
```

#### Methods
- `commit()`: Commits the current transaction.
- `rollback()`: Rolls back the current transaction.
- `__enter__()`: Context manager entry.
- `__exit__(exctype, excvalue, traceback)`: Context manager exit - automatically commits or rolls back based on exception.

#### Example
```python
with db.transaction():
    db.insert('users', name='John')
    db.update('users', where='id=1', name='Jane')
```

### `DB`
Base database class that provides common functionality for all database implementations. Not used directly; use database-specific subclasses.

#### Constructor
```python
DB(db_module, keywords)
```

#### Methods
- `_getctx()`: Returns the current database context.
- `_load_context(ctx)`: Loads the database connection into the context.
- `_unload_context(ctx)`: Unloads the database connection from the context.
- `_connect(keywords)`: Creates a new database connection.
- `_connect_with_pooling(keywords)`: Creates a pooled database connection using DBUtils.
- `_db_cursor()`: Returns a new database cursor.
- `_param_marker()`: Returns the parameter marker used by the database driver.
- `_db_execute(cur, sql_query)`: Executes a SQL query with the given cursor, handling errors and transactions.
- `_process_query(sql_query)`: Processes an SQLQuery object into query string and parameters.
- `_where(where, vars)`: Converts where clause to SQLQuery.
- `_where_dict(where)`: Converts dictionary to WHERE clause.
- `query(sql_query, vars=None, processed=False, _test=False)`: Executes a SQL query.
- `create_result_set(cursor)`: Creates a result set from a cursor.
- `select(tables, vars=None, what="*", where=None, order=None, group=None, limit=None, offset=None, _test=False)`: Performs SELECT queries.
- `where(table, what="*", order=None, group=None, limit=None, offset=None, _test=False, **kwargs)`: Selects rows with WHERE conditions from a table.
- `sql_clauses(what, tables, where, group, order, limit, offset)`: Returns SQL clauses for SELECT queries.
- `gen_clause(sql, val, vars)`: Generates a clause for SQL query building.
- `insert(tablename, seqname=None, _test=False, **values)`: Inserts a row into a table.
- `multiple_insert(tablename, values, seqname=None, _test=False)`: Inserts multiple rows into a table.
- `update(tables, where, vars=None, _test=False, **values)`: Updates rows in a table.
- `delete(table, where, using=None, vars=None, _test=False)`: Deletes rows from a table.
- `_get_insert_default_values_query(table)`: Returns the SQL query for inserting default values.
- `_process_insert_query(query, tablename, seqname)`: Processes insert queries for specific databases.
- `transaction()`: Starts a new transaction.

#### Identifier checks and their limits (this fork)
The DML builders use the internal `_sql_safe_identifier` helper. Failed checks
raise `SQLInjectionError`, available as `web.db.SQLInjectionError` or via
`from web.db import SQLInjectionError`; it is **not** star-exported.

The helper rejects non-strings and the empty unquoted string. It accepts exactly
one complete identifier, in either of these forms:

- An ASCII letter or underscore followed by ASCII letters, digits or underscores:
  `users`, `_private` and `user_data2`. Unquoted `public.users`, spaces, hyphens
  and non-ASCII names are rejected.
- A double-quoted token with every interior double quote encoded as a doubled
  quote: `"table name"`, `"user-data"`, `"café"` or `"a"";--"`. Spaces, Unicode,
  punctuation, semicolons and comment-like characters **inside** the token are
  name content, not SQL code. Empty quoted content (`""`) remains accepted.
  Quoted LF and NUL are rejected; quoted CR and tab remain accepted.

The entire string must match: no leading/trailing data, whitespace or final
newline is discarded. Unbalanced or undoubled interior quotes are rejected.
The helper returns the input unchanged; it does not escape, quote or trim it.
This intentionally tightens the former permissive quoted check: `"a"; "b"`,
`"users" WHERE 1=1 --"`, final LF after a bare or quoted identifier, and quoted
NUL no longer pass. Previously valid single-token quoted names remain accepted;
internal LF was not supported before and is not newly supported.

This bounded token grammar is not a guarantee of validity in every backend's
SQL dialect. Keep identifiers application-controlled (for user choices, map a
bounded allowlist to fixed identifiers). Raw SQL is not protected by this check;
do not treat quoting arbitrary input as a substitute for an allowlist.

| Method | Fields checked, ordering and exceptions |
| --- | --- |
| `insert` | Checks `tablename` first, even with no values. With values, checks every keyword column name. Without values, builds the backend's default-values insert; the base default-values helper also checks the table. |
| `multiple_insert` | A falsy `values` returns `[]` **before any identifier check**. Otherwise checks `tablename`. If `supports_multiple_insert` is false (SQLite's default), delegates each row to `insert`, which checks its columns; this branch does not enforce identical key sets across rows. With the flag true, checks the first row's keys, then requires every row to have that same key set (`ValueError` on mismatch). It does not separately validate later differing keys. A nonempty list of empty dictionaries is not the empty-list early return. |
| `update` | A string `tables` is checked once; otherwise each element is checked. A noniterable such as `None` or an integer raises `TypeError` at iteration, not `SQLInjectionError`; an empty iterable checks nothing. Checks each column in `values`, even when `where` is empty. There is no empty-values no-op: it can generate an empty `SET` clause. |
| `delete` | Always checks `table`. Checks `using` only when truthy: each list/tuple element, or the single supplied value otherwise. Falsy `using` is ignored. `FirebirdDB.delete` discards `using` before calling the base method. |
| `select` / `where` / `query` | Do **not** apply this identifier checker. `select` accepts SQL in `tables`, `what`, `where`, `group` and `order`; `where()` delegates to `select`. Dictionary WHERE keys (also in update/delete), `sqlwhere` keys and `seqname` are not checked by this helper. |

Checks occur before the normal `_test=True` return. `_test` builds SQL without
executing it; it neither bypasses the checks above nor validates the resulting
SQL with a database. `multiple_insert` retains its early-return/delegation
behavior in test mode: fallback returns a list of queries, or `None` with
`seqname=False`; optimized mode returns one query. Python's `**kwargs` boundary
itself rejects non-string column keys in insert/update and delegated inserts;
optimized `multiple_insert` checks its first-row keys directly. Validation is
per statement, not an atomic whole-batch preflight: fallback `multiple_insert`
can insert earlier valid rows before a later row's invalid column raises.

WHERE handling is separate. `delete` with `where=''` or `{}` omits WHERE and
can delete **all rows**; `where=None` is not supported by the base delete/update
path and currently raises `AttributeError`. `update` with `where=''` retains
an empty WHERE clause, and `{}` currently raises `TypeError`. `select` omits a
`None` WHERE but an explicitly empty string/dictionary produces a bare WHERE;
`where()` with no keyword conditions instead passes `None`. These are builder
behaviors, not guarantees of valid SQL or automatic no-ops.

Ordinary values in insert/update/multiple_insert and `$name` substitutions are
bound parameters. This protects **values**, not SQL syntax, identifier strings
or arbitrary `where`/`order` expressions. `SQLLiteral`/`sqlliteral` deliberately
inserts raw SQL rather than a bound value. Use only trusted SQL expressions;
never treat these builders or their identifier regex as universal injection
protection. Backend grammar and feature support remain separate concerns.

#### Executable identifier and value example
Owned in-memory SQLite only; no external driver/server. The quoted identifiers
below are fixed application constants, not quoting advice for untrusted input.

```python
import web
from web.db import SQLInjectionError

db = web.database(dbn='sqlite', db=':memory:')
try:
    db.query('CREATE TABLE "user data" (id INTEGER PRIMARY KEY, name TEXT)')
    literal_value = "O'Reilly'); DROP TABLE users; --"
    built = db.insert('"user data"', name=literal_value, _test=True)
    assert built.query('qmark') == 'INSERT INTO "user data" (name) VALUES (?)'
    assert built.values() == [literal_value]
    assert db.insert('"user data"', name=literal_value) == 1
    assert db.select('"user data"', where='id=$id', vars={'id': 1}).first().name == literal_value
    db.multiple_insert('"user data"', [{'name': 'second'}, {'name': 'third'}])
    assert db.update('"user data"', where='id=$id', vars={'id': 1}, name='updated') == 1
    assert db.delete('"user data"', where='id=$id', vars={'id': 999}) == 0
    remaining_names = [row.name for row in db.select('"user data"', order='id')]
    assert remaining_names == ['updated', 'second', 'third']

    for test_mode in (False, True):
        try:
            db.delete('"user data" WHERE 1=1 --"', where='id=999', _test=test_mode)
        except SQLInjectionError:
            pass  # Rejected as more than one quoted identifier.
        else:
            raise AssertionError('Malformed quoted identifier was accepted')
        assert [row.name for row in db.select('"user data"', order='id')] == remaining_names

    try:
        db.insert('public.users', name='x', _test=True)
    except SQLInjectionError:
        pass  # Rejected before SQL execution, even in test mode.
    else:
        raise AssertionError('Unquoted schema-qualified DML name was accepted')

    raw = db.select('public.users AS u', what='u.name',
                    where='u.name=$name', vars={'name': literal_value},
                    order='u.name DESC', _test=True)
    assert raw.query() == 'SELECT u.name FROM public.users AS u WHERE u.name=%s ORDER BY u.name DESC'
    assert raw.values() == [literal_value]
    # Generated only: SELECT does not run the DML identifier checker.
finally:
    db.ctx.db.close()
```

### Database-Specific Classes

#### `PostgresDB`
PostgreSQL database implementation.

##### Constructor
```python
PostgresDB(**keywords)
```

##### Additional Methods
- `get_sequence_query(seqname)`: Returns SQL to get the current value of a sequence.
- `_get_all_sequences()`: Returns a set of all sequence names in the database.
- `_connect(keywords)`: Creates a new database connection with UTF-8 encoding.
- `_connect_with_pooling(keywords)`: Creates a pooled connection with UTF-8 encoding.

#### `MySQLDB`
MySQL database implementation.

##### Constructor
```python
MySQLDB(**keywords)
```

##### Additional Methods
- `_process_insert_query(query, tablename, seqname)`: Returns query with `SELECT last_insert_id()` for getting the inserted ID.
- `_get_insert_default_values_query(table)`: Returns query for inserting default values.

#### `SqliteDB`
SQLite database implementation.

##### Constructor
```python
SqliteDB(**keywords)
```

##### Additional Methods
- `_process_insert_query(query, tablename, seqname)`: Returns query with `SELECT last_insert_rowid()` for getting the inserted ID.
- `create_result_set(cursor)`: Returns a SqliteResultSet instance.

#### `FirebirdDB`
Firebird database implementation.

##### Constructor
```python
FirebirdDB(**keywords)
```

##### Additional Methods
- `delete(table, where=None, using=None, vars=None, _test=False)`: Overrides delete to remove the `USING` clause (not supported by Firebird).
- `sql_clauses(what, tables, where, group, order, limit, offset)`: Returns Firebird-specific clauses with `FIRST` and `SKIP` instead of `LIMIT` and `OFFSET`.

#### `MSSQLDB`
Microsoft SQL Server database implementation.

##### Constructor
```python
MSSQLDB(**keywords)
```

##### Additional Methods
- `_process_query(sql_query)`: Converts params to tuple (required by pymssql).
- `sql_clauses(what, tables, where, group, order, limit, offset)`: Returns SQL Server-specific clauses with `TOP` instead of `LIMIT`.

#### `OracleDB`
Oracle database implementation.

##### Constructor
```python
OracleDB(**keywords)
```

##### Additional Methods
- `_process_insert_query(query, tablename, seqname)`: Appends `SELECT seqname.currval FROM dual` for getting the inserted ID.

## Functions

### `import_driver(drivers, preferred=None)`
With a falsy `preferred` (the default), tries `drivers` in order, continuing
on `ImportError`. If none imports, raises `ImportError`. A **truthy** `preferred`
replaces the entire candidate tuple with `(preferred,)`: it selects one
mandatory driver, not a hint with fallback. It can name a driver outside the
original tuple. This helper imports a module; it does not open a connection.
Use `from web.db import import_driver`, not a star import.

#### Example
This offline example uses standard-library SQLite and a deliberately nonexistent
module; no optional driver or database server is needed.

```python
from web.db import import_driver

missing = '_web5_nonexistent_driver_68241'
driver = import_driver((missing, 'sqlite3'))
assert driver.__name__ == 'sqlite3'  # Fallback without preferred.
try:
    import_driver(('sqlite3',), preferred=missing)
except ImportError:
    pass  # Mandatory preferred is missing, despite sqlite3 being available.
else:
    raise AssertionError('A missing preferred driver must not fall back')
```

### `database(dburl=None, **params)`
Creates an appropriate database instance based on parameters or URL.

#### Example
```python
# Using parameters
db = database(dbn='postgres', user='joe', pw='secret', db='mydb')

# Using URL
db = database('postgres://joe:secret@localhost/mydb')
```

### `register_database(name, clazz)`
Registers a new database backend with the system.

#### Example
```python
class CustomDB(DB):
    def __init__(self, **params):
        pass

register_database('custom', CustomDB)
db = database(dbn='custom', db='test')
```

### `dburl2dict(url)`
Parses a database URL into connection parameters, without connecting. Import
it explicitly from `web.db`. The implementation applies `unquote` to the URL
before parsing; a literal `***` password remains `***`. It cannot reconstruct
a secret hidden by a redaction. All credentials below are fictitious examples.

#### Supported URL Formats
- PostgreSQL: `postgres://user:***@host:port/dbname`
- MySQL: `mysql://user:***@host:port/dbname`
- SQLite: `sqlite:///path/to/dbfile` or `sqlite:////absolute/path/to/dbfile`

#### Example
```python
from web.db import dburl2dict

params = dburl2dict('postgres://james:***@serverfarm.example.net:5432/mygreatdb')
assert params == {
    'pw': '***', 'dbn': 'postgres', 'db': 'mygreatdb',
    'host': 'serverfarm.example.net', 'user': 'james', 'port': 5432,
}
```

### `sqllist(lst)`
Converts a list to a comma-separated string for use in SQL queries.

#### Example
```python
>>> sqllist(['a', 'b'])
'a, b'
>>> sqllist('a')
'a'
```

### `sqlors(left, lst)`
Creates an OR clause for SQL WHERE conditions.

#### Example
```python
>>> sqlors('foo = ', [1, 2, 3])
<sql: '(foo = 1 OR foo = 2 OR foo = 3 OR 1=2)'>
```

### `sqlwhere(data, grouping=" AND ")`
Converts key-value pairs to a SQL WHERE clause.

#### Example
```python
>>> sqlwhere((('cust_id', 2), ('order_id',3)))
<sql: 'cust_id = 2 AND order_id = 3'>
```

### `sqlquote(a)`
Quotes values properly for use in a SQL query.

#### Example
```python
>>> 'WHERE x = ' + sqlquote(True) + ' AND y = ' + sqlquote(3)
<sql: "WHERE x = 't' AND y = 3">
>>> 'WHERE x = ' + sqlquote(True) + ' AND y IN ' + sqlquote([2, 3])
<sql: "WHERE x = 't' AND y IN (2, 3)">
```

### `reparam(string_, dictionary)`
Interpolates a string with dictionary values to create an SQLQuery.

#### Example
```python
>>> reparam("s = $s", dict(s=True))
<sql: "s = 't'">
>>> reparam("s IN $s", dict(s=[1, 2]))
<sql: 's IN (1, 2)'>
```

### `_sqllist(values)`
Internal function to convert a list/tuple/set of values into a parenthesized SQL list (e.g., `(1, 2, 3)`). Used for `IN` clauses.

### `_interpolate(format)`
Internal function that takes a format string and returns chunks of (is_expression, text) for SQL interpolation.

### `sqlify(obj)`
Converts Python objects to their SQL representation.

#### Example
```python
>>> sqlify(None)
'NULL'
>>> sqlify(True)
"'t'"
>>> sqlify(3)
'3'
>>> sqlify(datetime.datetime(2023, 1, 1))
"'2023-01-01T00:00:00'"
```

## Constants

- `pg_drivers`: Tuple of supported PostgreSQL drivers: `("psycopg2",)`
- `mysql_drivers`: Tuple of supported MySQL drivers: `("pymysql", "MySQLdb", "mysql.connector")`
- `sqlite_drivers`: Tuple of supported SQLite drivers: `("sqlite3", "pysqlite2.dbapi2", "sqlite")`
- `TOKEN`: Regular expression pattern for parsing SQL tokens.
- `tokenprog`: Compiled regular expression for token matching.

## Usage Examples

### Basic Operations

```python
# Create a database connection
db = database(dbn='postgres', user='joe', pw='secret', db='mydb')

# Insert data
db.insert('users', name='John', email='john@example.com')

# Select data
users = db.select('users', where='name=$name', vars={'name': 'John'})

# Update data
db.update('users', where='id=$id', vars={'id': 1}, name='Jane')

# Delete data
db.delete('users', where='id=$id', vars={'id': 1})
```

### Using SQLQuery and SQLParam

```python
# Build queries incrementally
q = SQLQuery(['SELECT * FROM users WHERE name=', SQLParam('John')])
print(q.query())  # SELECT * FROM users WHERE name=%s
print(q.values())  # ['John']

# Use SQLLiteral for SQL functions
db.insert('logs', created=SQLLiteral('NOW()'))
```

### Transactions

```python
# Using context manager
with db.transaction():
    db.insert('users', name='Alice')
    db.insert('users', name='Bob')

# Manual transaction control
t = db.transaction()
try:
    db.update('users', where='id=1', name='Charlie')
    t.commit()
except:
    t.rollback()
```

### Multiple Insert

```python
# Insert multiple rows efficiently
values = [
    {"name": "Alice", "email": "alice@example.com"},
    {"name": "Bob", "email": "bob@example.com"},
]
db.supports_multiple_insert = True
db.multiple_insert('users', values=values)
```

### Complex Queries

```python
# Using sqlors for OR conditions
where = sqlors('status = ', ['active', 'pending'])
users = db.select('users', where=where)

# Using sqlwhere for dictionary-based conditions
where = sqlwhere((('status', 'active'), ('role', 'admin')))
users = db.select('users', where=where)
```

## Additional Classes

### `SafeEval`
Safe evaluator for binding parameters to database queries. Used internally by `reparam` to safely interpolate values into SQL queries.

#### Methods
- `safeeval(text, mapping)`: Evaluates the text with the given mapping and returns an SQLQuery.

### `Parser`
Parser to parse string templates like "Hello $name". Used internally for SQL query interpolation.

#### Methods
- `parse(text)`: Parses the given text and returns a parse tree (generator of `_Node` objects).
- `parse_all()`: Parses all tokens in the text.
- `match()`: Matches the current position in the text against the token pattern.
- `is_literal(text)`: Checks if text is a literal value.
- `parse_expr()`: Parses an expression at the current position.

### `_Node`
Represents a node in the parse tree.

#### Constructor
```python
_Node(type, first, second=None)
```

#### Attributes
- `type`: The type of node (`text`, `param`, `literal`, `getattr`, `getitem`).
- `first`: The first part of the node (e.g., text content or parameter name).
- `second`: The second part of the node (e.g., attribute name or key).

#### Example
```python
# For "Hello $name.foo", the parse tree would be:
# [_Node("text", "Hello "), _Node("getattr", _Node("param", "name"), "foo")]
```

## Utility Functions

### `sqlliteral(value)`
Alias for `SQLLiteral`. Protects a string from being escaped during SQL quoting.

#### Example
```python
# Use SQLLiteral for SQL functions
db.insert('logs', created=sqlliteral('NOW()'))
```

## `__all__` Exports

`web.db.__all__` contains exactly these names, in source order. They are
available through `from web.db import *` and propagated by `web/__init__.py`
as `web.<name>`:

- `UnknownParamstyle`: Unsupported parameter style exception.
- `UnknownDB`: Unsupported database backend exception.
- `TransactionError`: Transaction exception.
- `sqllist`: Convert names to a comma-separated string (not identifier validation).
- `sqlors`: Build an OR clause.
- `reparam`: Bind template values in an SQLQuery.
- `sqlquote`: Represent values as SQL parameters.
- `SQLQuery`: SQL query builder.
- `SQLParam`: Bound parameter wrapper.
- `sqlparam`: Alias for SQLParam.
- `SQLLiteral`: Raw SQL expression wrapper, not a bound value.
- `sqlliteral`: Alias for SQLLiteral.
- `database`: Database factory.
- `DB`: Base database class.

Other members documented on this page exist as attributes of `web.db`, but
are **not** in this export list and are not automatically `web.<name>`.
For example, result-set classes, `Transaction`, database-specific classes,
`sqlwhere`, `sqlify`, `import_driver`, `register_database`, `dburl2dict` and
`SQLInjectionError` require module-qualified access or explicit imports:

```python
import web
from web.db import SqliteDB, sqlwhere, SQLInjectionError

assert SqliteDB is web.db.SqliteDB
assert SQLInjectionError is web.db.SQLInjectionError
assert web.sqlparam is web.SQLParam
condition = sqlwhere((('name', "O'Reilly"),))
assert condition.query() == 'name = %s'
assert condition.values() == ["O'Reilly"]
```

## See Also

- [`session.md`](session.md) - Session management with database-backed storage (DBStore)
- [`webapi.md`](webapi.md) - Web API including context and cookie management
- [`utils.md`](utils.md) - Utility functions used by the database module
