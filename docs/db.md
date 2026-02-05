
# Web Database API Documentation

This document describes the database API implemented in `web/db.py`, which provides a unified interface for working with different database backends.

## Overview

The web.py database module provides a consistent API for database operations across different database systems including PostgreSQL, MySQL, SQLite, and others. It handles connection management, query building, parameter interpolation, and result set handling.

## Classes

### `UnknownDB`
Exception raised when an unsupported database backend is specified.

### `TransactionError`
Exception raised when database transaction operations fail.

### `UnknownParamstyle`
Exception raised for unsupported database parameter styles (qmark, numeric, format, pyformat).

### `SQLParam`
Represents a parameter in SQL queries.

#### Methods
- `get_marker(paramstyle)`: Returns the appropriate parameter marker for the given style.
- `sqlquery()`: Returns an SQLQuery object containing this parameter.
- `__add__()`, `__radd__()`: Support for string concatenation with SQL queries.
- `__str__()`, `__eq__()`, `__repr__()`: Standard Python object methods.

### `SQLQuery`
Represents a SQL query that can be built incrementally.

#### Methods
- `append(value)`: Appends a value to the query items.
- `__add__()`, `__radd__()`, `__iadd__()`: Support for query concatenation.
- `__len__()`, `__eq__()`: Standard Python object methods.
- `query(paramstyle=None)`: Returns the SQL query string with parameter markers.
- `values()`: Returns the list of parameter values.
- `join(items, sep=" ", prefix=None, suffix=None, target=None)`: Joins multiple queries.

### `SQLLiteral`
Protects a string from being escaped during SQL quoting.

#### Methods
- `__repr__()`: Returns a string representation of the literal.

### `BaseResultSet`
Base class for result sets returned by database queries.

#### Methods
- `list()`: Returns all rows as a list.
- `_prepare_row(row)`: Prepares a single row for return.
- `__iter__()`, `__next__()`: Iterator support.
- `first(default=None)`: Returns the first row or default if none exists.
- `__getitem__(i)`: Access rows by index.

### `ResultSet`
Result set implementation for most database backends.

#### Methods
- `__len__()`: Returns the number of rows in the result set.

### `SqliteResultSet`
Result set implementation specifically for SQLite databases.

#### Methods
- `__next__()`: Overrides next method to handle SQLite-specific behavior.
- `__bool__()`: Checks if result set has data.

### `Transaction`
Database transaction management class.

#### Methods
- `commit()`: Commits the current transaction.
- `rollback()`: Rolls back the current transaction.
- `__enter__()`, `__exit__()`: Context manager support.

### `DB`
Base database class that provides common functionality for all database implementations.

#### Constructor
```python
def __init__(self, db_module, keywords)
```

#### Methods
- `_getctx(self)`: Returns the current database context.
- `_load_context(self, ctx)`: Loads the database connection into the context.
- `_connect(self, keywords)`: Creates a new database connection.
- `_connect_with_pooling(self, keywords)`: Creates a pooled database connection.
- `_db_cursor(self)`: Returns a new database cursor.
- `_db_execute(self, cur, sql_query)`: Executes a SQL query with the given cursor.
- `_process_query(self, sql_query)`: Processes an SQLQuery object into query string and parameters.
- `_where(self, where, vars)`: Converts where clause to SQLQuery.
- `_where_dict(self, where)`: Converts dictionary to WHERE clause.
- `query(self, sql_query, vars=None, processed=False, _test=False)`: Executes a SQL query.
- `create_result_set(self, cursor)`: Creates a result set from a cursor.
- `select(self, tables, vars=None, what="*", where=None, order=None, group=None, limit=None, offset=None, _test=False)`: Performs SELECT queries.
- `where(self, table, what="*", order=None, group=None, limit=None, offset=None, _test=False, **kwargs)`: Selects rows with WHERE conditions from a table.
- `sql_clauses(self, what, tables, where, group, order, limit, offset)`: Returns SQL clauses for SELECT queries.
- `gen_clause(self, sql, val, vars)`: Generates a clause for SQL query building.
- `insert(self, tablename, seqname=None, _test=False, **values)`: Inserts a row into a table.
- `multiple_insert(self, tablename, values, seqname=None, _test=False)`: Inserts multiple rows into a table.
- `update(self, tables, where, vars=None, _test=False, **values)`: Updates rows in a table.
- `delete(self, table, where, using=None, vars=None, _test=False)`: Deletes rows from a table.
- `_process_insert_query(self, query, tablename, seqname)`: Processes insert queries for specific databases.
- `transaction(self)`: Starts a new transaction.

### Database-Specific Classes

#### `PostgresDB`
PostgreSQL database implementation.

#### `MySQLDB`
MySQL database implementation.

#### `SqliteDB`
SQLite database implementation.

#### `FirebirdDB`
Firebird database implementation.

#### `MSSQLDB`
Microsoft SQL Server database implementation.

#### `OracleDB`
Oracle database implementation.

## Functions

### `import_driver(drivers, preferred=None)`
Imports the first available driver or preferred driver from a list of drivers.

### `database(dburl=None, **params)`
Creates an appropriate database instance based on parameters or URL.

### `register_database(name, clazz)`
Registers a new database backend with the system.

### `dburl2dict(url)`
Parses a database URL into a dictionary of connection parameters.

### `sqllist(lst)`
Converts a list to a comma-separated string for use in SQL queries.

### `sqlors(left, lst)`
Creates an OR clause for SQL WHERE conditions.

### `sqlwhere(data, grouping=" AND ")`
Converts key-value pairs to a SQL WHERE clause.

### `sqlquote(a)`
Quotes values properly for use in SQL queries.

### `reparam(string_, dictionary)`
Interpolates a string with dictionary values to create an SQLQuery.

### `sqlify(obj)`
Converts Python objects to their SQL representation.

## Constants

- `pg_drivers`: List of supported PostgreSQL drivers.
- `mysql_drivers`: List of supported MySQL drivers.
- `sqlite_drivers`: List of supported SQLite drivers.
- `TOKEN`: Regular expression pattern for parsing SQL tokens.
- `tokenprog`: Compiled regular expression for token matching.

## Usage Examples

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
