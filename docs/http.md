# Web HTTP Utilities Documentation

This document describes the HTTP utility functions in `web/http.py`, which provide helper functions for working with HTTP headers, URL manipulation, and request/response handling.

## Overview

The http module provides various utility functions for HTTP operations including setting cache headers, handling conditional requests, URL encoding, and profiling. These utilities are commonly used in web.py applications to handle common HTTP patterns and improve performance.

## Functions

### `prefixurl(base="")`
Generates a relative URL prefix based on the current path depth.

**Parameters:**
- `base`: Base path string (default: "")

**Returns:** Relative path prefix like "../" or "./"

**Note:** The function description indicates it's difficult to explain, suggesting it's primarily used internally for URL construction.

### `expires(delta)`
Sets an HTTP `Expires` header based on a time delta from now.

**Parameters:**
- `delta`: A `timedelta` object or number of seconds

**Returns:** None (sets HTTP header)

**Example:**
```python
expires(3600)  # Sets Expires header to 1 hour from now
```

### `lastmodified(date_obj)`
Sets an HTTP `Last-Modified` header.

**Parameters:**
- `date_obj`: A datetime object

**Returns:** None (sets HTTP header)

### `modified(date=None, etag=None)`
Handles conditional requests using `Last-Modified` and `ETag` headers.

This function checks if the requested resource has been modified since the client's cached version. If not, it returns a 304 Not Modified response.

**Parameters:**
- `date`: Last modification date (datetime object)
- `etag`: Entity tag string for version identification

**Returns:** True if resource hasn't been modified, raises `web.notmodified()` otherwise

**Example:**
```python
# In a handler function
last_modified = datetime.datetime(2023, 1, 1)
etag = "abc123"
if modified(date=last_modified, etag=etag):
    # Resource hasn't been modified, send normal response
    return render.page()
```

### `urlencode(query, doseq=False)`
Encodes a dictionary into URL-encoded string, supporting Unicode.

**Parameters:**
- `query`: Dictionary of query parameters
- `doseq`: Whether to handle sequences in values

**Returns:** URL-encoded string

**Example:**
```python
urlencode({'text': 'foo bar'})  # Returns: 'text=foo+bar'
urlencode({'x': [1, 2]}, doseq=True)  # Returns: 'x=1&x=2'
```

### `changequery(query=None, **kw)`
Creates a new URL with modified query parameters.

**Parameters:**
- `query`: Query parameters (defaults to current GET parameters)
- `**kw`: Keyword arguments for parameter changes

**Returns:** New URL string with updated parameters

**Example:**
```python
# If current URL is /foo?a=1&b=2
changequery(a=3)  # Returns: /foo?a=3&b=2
```

### `url(path=None, doseq=False, **kw)`
Creates a full URL by combining the home path with a given path and query parameters.

**Parameters:**
- `path`: Path to append (defaults to current path)
- `doseq`: Whether to handle sequences in values
- `**kw`: Query parameters

**Returns:** Full URL string

### `profiler(app)`
Wraps an application with profiling information.

**Parameters:**
- `app`: WSGI application to profile

**Returns:** Wrapped WSGI application that outputs profiling info at the bottom of each response

## Constants

### `__all__`
List of public functions exported by this module:
- `expires`
- `lastmodified`
- `prefixurl`
- `modified`
- `changequery`
- `url`
- `profiler`

## Dependencies

This module imports:
- `datetime` for date/time operations
- `urllib.parse.urlencode` for URL encoding
- `web.net` for HTTP date utilities
- `web.utils` for utility functions
- `web.webapi` for web context access
- `web.py3helpers` for Python 3 compatibility

## Usage Examples

### Setting Cache Headers
```python
# Set cache to expire in 1 hour
expires(3600)

# Set last modified date
lastmodified(datetime.datetime.now())
```

### Handling Conditional Requests
```python
def get_page():
    # Check if page has been modified
    last_modified = datetime.datetime(2023, 1, 1)
    etag = "version-1.0"
    
    if modified(date=last_modified, etag=etag):
        # Page hasn't been modified, return normal content
        return render.page()
```

### URL Manipulation
```python
# Create a new URL with modified parameters
new_url = changequery(page=2, sort='name')

# Build full URLs
full_url = url('/api/users', limit=10, offset=20)
```
