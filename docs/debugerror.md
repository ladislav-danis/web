# Web Debug Error Documentation

This document describes the debug error handling functionality in `web/debugerror.py`, which provides enhanced error reporting for web.py applications.

## Overview

The debugerror module provides tools for displaying detailed debugging information when errors occur in web.py applications. It includes features for pretty-printing stack traces, showing request context, and emailing error reports to developers.

## Functions

### `debugerror()`
Returns an internal error handler that displays a detailed debug page with stack trace information, request data, and local variables.

**Usage:**
```python
import web
from web.debugerror import debugerror

# Set as the internal error handler
web.config.debug = True
web.internalerror = debugerror
```

### `djangoerror()`
Generates a Django-style error page with detailed debugging information including:

- Exception type and value
- Full stack trace with source code context
- Local variables at each stack frame
- Request information (headers, cookies, environment)
- Response data

**Returns:** HTML content for the debug error page

### `emailerrors(to_address, olderror, from_address=None)`
Creates an error handler that emails error details to a specified address while still displaying the normal error page.

**Parameters:**
- `to_address`: Email address to send errors to
- `olderror`: The previous internal error handler
- `from_address`: Optional sender email address (defaults to to_address)

**Returns:** A new error handler function that emails errors and returns the original error

## Classes

### `SQLParam`
Represents a parameter in SQL queries.

#### Methods
- `get_marker(paramstyle)`: Returns the appropriate parameter marker for the given style
- `sqlquery()`: Returns an SQLQuery object containing this parameter
- `__add__()`, `__radd__()`: Support for string concatenation with SQL queries
- `__str__()`, `__eq__()`, `__repr__()`: Standard Python object methods

### `SQLQuery`
Represents a SQL query that can be built incrementally.

#### Methods
- `append(value)`: Appends a value to the query items
- `__add__()`, `__radd__()`, `__iadd__()`: Support for query concatenation
- `__len__()`, `__eq__()`: Standard Python object methods
- `query(paramstyle=None)`: Returns the SQL query string with parameter markers
- `values()`: Returns the list of parameter values
- `join(items, sep=" ", prefix=None, suffix=None, target=None)`: Joins multiple queries

## Constants

### `djangoerror_t`
Template string for the Django-style error page HTML.

### `djangoerror_r`
Template object created from `djangoerror_t` for rendering error pages.

## Usage Examples

### Basic Debug Mode
```python
import web
from web.debugerror import debugerror

# Enable debug mode and set error handler
web.config.debug = True
web.internalerror = debugerror

# Your application code here
```

### Email Error Handler
```python
import web
from web.debugerror import emailerrors, debugerror

# Set up email error reporting
web.config.debug = True
web.internalerror = emailerrors('developer@example.com', debugerror)

# Errors will be emailed to the developer while still showing a normal error page
```

### Custom Error Handler
```python
import web
from web.debugerror import djangoerror

def custom_error_handler():
    # Custom error handling logic here
    return "Custom error page"

web.internalerror = custom_error_handler
```

## Features

1. **Pretty Stack Traces**: Shows source code context around errors with line numbers
2. **Variable Inspection**: Displays local variables at each stack frame
3. **Request Context**: Shows HTTP headers, cookies, and request data
4. **Email Notifications**: Can automatically email error reports to developers
5. **Template Support**: Works with web.py's template system for rendering error pages
6. **Debug Mode Toggle**: Only active when `web.config.debug` is True

## Security Note

The debug error handler should only be used in development environments as it exposes sensitive information about the application and server configuration.
