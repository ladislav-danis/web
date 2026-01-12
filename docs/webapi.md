# Web API Documentation

This document describes the web API utilities in `web/webapi.py`, which provide a WSGI wrapper and various helper functions for handling HTTP requests and responses in web.py applications.

## Overview

The webapi module serves as the core interface between WSGI applications and HTTP request/response handling. It provides utilities for managing HTTP status codes, headers, cookies, input data, and error handling while maintaining compatibility with the WSGI specification.

## Classes

### `HTTPError`
Base exception class for HTTP errors.

#### Constructor
```python
def __init__(self, status, headers={}, data="")
```

**Parameters:**
- `status` (str): HTTP status code and message
- `headers` (dict): HTTP headers to include in response
- `data` (str): Error message/data to return

### Status Code Classes

#### `OK`, `Created`, `Accepted`, `NoContent`
Success status codes (200, 201, 202, 204).

#### `Redirect`, `Found`, `SeeOther`, `NotModified`, `TempRedirect`
Redirection status codes (301, 302, 303, 304, 307).

#### `BadRequest`, `Unauthorized`, `Forbidden`, `NotFound`, `NoMethod`, `NotAcceptable`, `Conflict`, `Gone`, `PreconditionFailed`, `UnsupportedMediaType`, `UnavailableForLegalReasons`
Client error status codes (400-415, 451).

#### `InternalError`
Server error status code (500).

## Functions

### `header(hdr, value, unique=False)`
Adds an HTTP header to the response.

**Parameters:**
- `hdr` (str): Header name
- `value` (str): Header value
- `unique` (bool): If True, don't add if header already exists

**Raises:**
- `ValueError`: If header contains invalid characters

### `rawinput(method=None)`
Returns storage object with GET or POST arguments without processing.

**Parameters:**
- `method` (str): Request method ("both", "get", "post", "put", "patch")

**Returns:**
- `storage`: Storage object containing request parameters

### `input(*requireds, **defaults)`
Returns a `storage` object with GET and POST arguments.

**Parameters:**
- `*requireds`: Required parameter names
- `**defaults`: Default values for optional parameters
- `_method` (str): Request method ("both", "get", "post", "put", "patch")

**Returns:**
- `storage`: Storage object with request parameters

**Raises:**
- `BadRequest`: If required parameters are missing

### `data()`
Returns the raw data sent with the HTTP request.

**Returns:**
- `bytes`: Raw request body data

### `setcookie(name, value, expires="", domain=None, secure=False, httponly=False, path=None, samesite=None)`
Sets an HTTP cookie in the response.

**Parameters:**
- `name` (str): Cookie name
- `value` (str): Cookie value
- `expires` (str/int): Expiration date or days until expiration
- `domain` (str): Cookie domain
- `secure` (bool): Secure flag
- `httponly` (bool): HttpOnly flag
- `path` (str): Cookie path
- `samesite` (str): SameSite attribute ("strict", "lax", "none")

### `parse_cookies(http_cookie)`
Parses HTTP_COOKIE header into a dictionary of cookie names and decoded values.

**Parameters:**
- `http_cookie` (str): Raw HTTP_COOKIE header value

**Returns:**
- `dict`: Dictionary of cookie names and values

**Examples:**
```python
parse_cookies('a=1; b=2')  # {'a': '1', 'b': '2'}
parse_cookies('a=Z%C3%A9Z')  # {'a': 'Z\xc3\xa9Z'}
```

### `cookies(*requireds, **defaults)`
Returns a `storage` object with all request cookies.

**Parameters:**
- `*requireds`: Required cookie names
- `**defaults`: Default values for optional cookies

**Returns:**
- `storage`: Storage object with cookie data

**Raises:**
- `BadRequest`: If required cookies are missing

### `debug(*args)`
Prints pretty-printed arguments to stderr.

**Parameters:**
- `*args`: Arguments to print

**Returns:**
- `str`: Empty string (for use in templates)

### `ctx`
Thread-local context object containing request and response information.

## Context Variables

The `ctx` object contains various request and response related information:

### Request Information
- `environ` (dict): WSGI environment variables
- `host` (str): Host header from request
- `home` (str): Base path for application
- `ip` (str): Client IP address
- `method` (str): HTTP method used
- `path` (str): Request path
- `query` (str): Query string with '?' prefix
- `fullpath` (str): Full request path including query

### Response Information
- `status` (str): HTTP status code (default: "200 OK")
- `headers` (list): List of 2-tuples for response headers
- `output` (str): Response body content

## Usage Examples

### Basic Error Handling
```python
import web

# Raise HTTP errors
raise web.notfound("Page not found")
raise web.forbidden("Access denied")
raise web.internalerror("Server error")

# Return success status codes
return web.ok()  # 200 OK
return web.created()  # 201 Created
```

### Handling Input Data
```python
# Get all form data
data = web.input()

# Get specific parameters with defaults
name = web.input(name="Anonymous").name

# Require specific parameters
user = web.input(required=["username", "password"])

# Handle POST and GET data
post_data = web.input(_method="post")
get_data = web.input(_method="get")
```

### Setting Cookies
```python
# Set a simple cookie
web.setcookie("session_id", "abc123")

# Set secure cookie with expiration
web.setcookie("user_prefs", "dark_mode", expires=3600, secure=True)

# Set SameSite cookie
web.setcookie("csrf_token", "xyz789", samesite="strict")
```

### Custom Error Pages
```python
def notfound():
    return "<h1>404 - Page Not Found</h1>"

# Configure application to use custom error handler
app.notfound = notfound
```

## Configuration

The module uses a global `config` object for various settings:

```python
web.config.debug = True  # Enables debugging features
```

## Security Considerations

- All header values are validated against HTTP response splitting attacks
- Cookie values are properly encoded and escaped
- Input data is processed safely to prevent injection attacks
- Session management uses secure cookie practices
