# Web API Documentation

This document describes the web API utilities in `web/webapi.py`, which provide a WSGI wrapper and various helper functions for handling HTTP requests and responses in web.py applications.

## Overview

The webapi module serves as the core interface between WSGI applications and HTTP request/response handling. It provides utilities for managing HTTP status codes, headers, cookies, input data, and error handling while maintaining compatibility with the WSGI specification.

## Classes

### `HTTPError`

Base exception class for HTTP errors. All HTTP error classes inherit from this class.

#### Constructor

```python
def __init__(self, status, headers={}, data="")
```

**Parameters:**
- `status` (str): HTTP status code and message (e.g., "404 Not Found")
- `headers` (dict): HTTP headers to include in response
- `data` (str): Error message/data to return in response body

**Example:**
```python
raise web.HTTPError("403 Forbidden", {"Content-Type": "text/html"}, "Access denied")
```

### Status Code Classes

All status code classes are generated dynamically and follow the pattern where both uppercase (e.g., `OK`) and lowercase (e.g., `ok`) variants are available.

#### Success Status Codes (2xx)

| Class | Status Code | Description |
|-------|-------------|-------------|
| `OK` / `ok` | 200 | Standard successful response |
| `Created` / `created` | 201 | Request successful, resource created |
| `Accepted` / `accepted` | 202 | Request accepted for processing |
| `NoContent` / `nocontent` | 204 | Successful response with no content |

**Example:**
```python
return web.ok()  # Returns 200 OK
return web.created()  # Returns 201 Created
```

#### Redirection Status Codes (3xx)

| Class | Status Code | Description |
|-------|-------------|-------------|
| `Redirect` / `redirect` | 301 | Moved permanently |
| `Found` / `found` | 302 | Found (temporary redirect) |
| `SeeOther` / `seeother` | 303 | See other (redirect to different URI) |
| `NotModified` / `notmodified` | 304 | Not modified (cache validation) |
| `TempRedirect` / `tempredirect` | 307 | Temporary redirect |

**Example:**
```python
# Redirect to a new URL (relative to current path)
raise web.redirect("about")

# Redirect to absolute URL
raise web.found("https://example.com/new-page", absolute=True)

# Redirect with 303 See Other (typically after POST)
raise web.seeother("/result")
```

#### Client Error Status Codes (4xx)

| Class | Status Code | Description |
|-------|-------------|-------------|
| `BadRequest` / `badrequest` | 400 | Malformed request syntax |
| `Unauthorized` / `unauthorized` | 401 | Authentication required |
| `Forbidden` / `forbidden` | 403 | Access denied |
| `NotFound` / `notfound` | 404 | Resource not found |
| `NoMethod` / `nomethod` | 405 | Method not allowed |
| `NotAcceptable` / `notacceptable` | 406 | Not acceptable |
| `Conflict` / `conflict` | 409 | Conflict with current state |
| `Gone` / `gone` | 410 | Resource no longer available |
| `PreconditionFailed` / `preconditionfailed` | 412 | Precondition failed |
| `UnsupportedMediaType` / `unsupportedmediatype` | 415 | Unsupported media type |
| `UnavailableForLegalReasons` / `unavailableforlegalreasons` | 451 | Unavailable for legal reasons |

**Example:**
```python
raise web.notfound("Page not found")
raise web.forbidden("Access denied")
raise web.badrequest("Invalid input data")
```

#### Server Error Status Codes (5xx)

| Class | Status Code | Description |
|-------|-------------|-------------|
| `InternalError` / `internalerror` | 500 | Internal server error |

**Example:**
```python
raise web.internalerror("An unexpected error occurred")
```

## Functions

### `header(hdr, value, unique=False)`

Adds an HTTP header to the response.

**Parameters:**
- `hdr` (str): Header name (e.g., "Content-Type", "X-Custom-Header")
- `value` (str): Header value
- `unique` (bool): If True, don't add header if one with the same name already exists

**Raises:**
- `ValueError`: If header name or value contains invalid characters (newline or carriage return)

**Example:**
```python
web.header("Content-Type", "application/json")
web.header("X-Request-ID", request_id, unique=True)
```

### `rawinput(method=None)`

Returns a storage object with GET or POST arguments without processing. This is the lower-level function that `input()` uses internally.

**Parameters:**
- `method` (str): Request method to parse. Options:
  - `"both"` (default): Parse both GET and POST
  - `"get"`: Parse only GET/query parameters
  - `"post"`, `"put"`, `"patch"`: Parse POST/PUT/PATCH body

**Returns:**
- `storage`: Storage object containing request parameters

**Example:**
```python
# Get all parameters
params = web.rawinput()

# Get only POST data
post_data = web.rawinput("post")

# Get only GET parameters
get_data = web.rawinput("get")
```

### `input(*requireds, **defaults)`

Returns a `storage` object with GET and POST arguments, with support for required parameters and defaults.

**Parameters:**
- `*requireds` (str): Required parameter names. Raises `BadRequest` if missing.
- `**defaults`: Default values for optional parameters
  - `_method` (str): Request method ("both", "get", "post", "put", "patch")
  - `_unicode` (bool): Convert values to unicode (default: True)
  - Other keys: Default values for parameters

**Returns:**
- `storage`: Storage object with request parameters

**Raises:**
- `BadRequest`: If required parameters are missing

**Example:**
```python
# Get all form data
data = web.input()

# Get specific parameters with defaults
name = web.input(name="Anonymous").name
page = web.input(page=1).page

# Require specific parameters
try:
    user = web.input(required=["username", "password"])
except web.badrequest:
    # Handle missing required parameters
    pass

# Handle POST and GET data separately
post_data = web.input(_method="post")
get_data = web.input(_method="get")
```

### `data()`

Returns the raw data sent with the HTTP request body.

**Returns:**
- `bytes`: Raw request body data

**Example:**
```python
# Get raw JSON data
json_data = web.data().decode("utf-8")

# Parse JSON
import json
data = json.loads(web.data())
```

### `setcookie(name, value, expires="", domain=None, secure=False, httponly=False, path=None, samesite=None)`

Sets an HTTP cookie in the response.

**Parameters:**
- `name` (str): Cookie name
- `value` (str): Cookie value
- `expires` (str/int): Expiration date (string) or days until expiration (integer). Use negative value for immediate expiration.
- `domain` (str): Cookie domain. If not specified, uses current domain.
- `secure` (bool): If True, cookie only sent over HTTPS
- `httponly` (bool): If True, cookie inaccessible to JavaScript
- `path` (str): Cookie path. Defaults to application home path.
- `samesite` (str): SameSite attribute. Options: "strict", "lax", "none"

**Example:**
```python
# Set a simple cookie
web.setcookie("session_id", "abc123")

# Set cookie with expiration (3600 seconds = 1 hour)
web.setcookie("user_prefs", "dark_mode", expires=3600)

# Set secure cookie
web.setcookie("auth_token", token, secure=True, httponly=True)

# Set SameSite cookie for CSRF protection
web.setcookie("csrf_token", "xyz789", samesite="strict")

# Delete a cookie
web.setcookie("session_id", "", expires=-1)
```

### `parse_cookies(http_cookie)`

Parses HTTP_COOKIE header into a dictionary of cookie names and decoded values.

**Parameters:**
- `http_cookie` (str): Raw HTTP_COOKIE header value

**Returns:**
- `dict`: Dictionary of cookie names and decoded values

**Examples:**
```python
# Basic parsing
web.parse_cookies('a=1')  # {'a': '1'}
web.parse_cookies('a=1; b=2')  # {'a': '1', 'b': '2'}

# URL-encoded values
web.parse_cookies('a=1%202')  # {'a': '1 2'}

# Unicode values
web.parse_cookies('a=Z%C3%A9Z')  # {'a': 'Z\xc3\xa9Z'}

# Complex values with special characters
web.parse_cookies('keebler="E=mc2; L=\\"Loves\\"; fudge=\\n;"')
# {'keebler': 'E=mc2; L="Loves"; fudge=\n;"'}
```

### `cookies(*requireds, **defaults)`

Returns a `storage` object with all request cookies, with support for required cookies and defaults.

**Parameters:**
- `*requireds` (str): Required cookie names. Raises `BadRequest` if missing.
- `**defaults`: Default values for optional cookies
  - `_unicode` (bool): Convert values to unicode (default: True)
  - Other keys: Default values for cookies

**Returns:**
- `storage`: Storage object with cookie data

**Raises:**
- `BadRequest`: If required cookies are missing

**Example:**
```python
# Get all cookies
all_cookies = web.cookies()

# Get specific cookie with default
session_id = web.cookies(session_id="default_session").session_id

# Require specific cookies
try:
    auth = web.cookies(required=["session_id", "user_id"])
except web.badrequest:
    # Handle missing required cookies
    pass
```

### `debug(*args)`

Prints pretty-printed arguments to stderr for debugging purposes.

**Parameters:**
- `*args`: Arguments to print

**Returns:**
- `str`: Empty string (for use in templates where output is expected)

**Example:**
```python
# Debug request data
web.debug(web.input())
web.debug(web.ctx)

# Debug complex objects
web.debug({"key": "value", "nested": {"data": [1, 2, 3]}})
```

### `ctx`

Thread-local context object containing request and response information. This is a `storage` object with the following attributes:

#### Request Information

| Attribute | Type | Description |
|-----------|------|-------------|
| `environ` (or `env`) | dict | WSGI environment variables |
| `host` | str | Host header from request |
| `home` | str | Base path for application |
| `realhome` | str | Real base path (including protocol and host) |
| `ip` | str | Client IP address |
| `method` | str | HTTP method used |
| `path` | str | Request path |
| `query` | str | Query string with '?' prefix |
| `fullpath` | str | Full request path including query |
| `homepath` | str | Home path without trailing slash |

#### Response Information

| Attribute | Type | Description |
|-----------|------|-------------|
| `status` | str | HTTP status code (default: "200 OK") |
| `headers` | list | List of 2-tuples for response headers |
| `output` | str | Response body content |
| `data` | bytes | Raw request body data |
| `_fieldstorage` | dict | Parsed form data (internal use) |
| `_parsed_cookies` | dict | Parsed cookies (internal use) |

**Example:**
```python
# Access request information
print(web.ctx.ip)  # Client IP
print(web.ctx.path)  # Request path
print(web.ctx.method)  # HTTP method

# Set response headers
web.ctx.headers.append(("X-Custom-Header", "value"))

# Set status
web.ctx.status = "404 Not Found"
```

## Configuration

The module uses a global `config` object for various settings:

| Attribute | Type | Description |
|-----------|------|-------------|
| `debug` | bool | When True, enables reloading, disables template caching, and sets internalerror to debugerror |

**Example:**
```python
web.config.debug = True  # Enables debugging features
```

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
page = web.input(page=1).page

# Require specific parameters
try:
    user = web.input(required=["username", "password"])
except web.badrequest:
    # Handle missing required parameters
    pass

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

# Delete a cookie
web.setcookie("session_id", "", expires=-1)
```

### Custom Error Pages

```python
def notfound():
    return "<h1>404 - Page Not Found</h1>"

def internalerror():
    return "<h1>500 - Internal Server Error</h1>"

# Configure application to use custom error handlers
app.notfound = notfound
app.internalerror = internalerror
```

### Redirects

```python
# Redirect to a relative path
raise web.redirect("about")

# Redirect to absolute URL
raise web.found("https://example.com/new-page", absolute=True)

# Redirect with 303 See Other (typically after POST)
raise web.seeother("/result")

# Temporary redirect
raise web.tempredirect("/temp-page")
```

### Custom Headers

```python
# Set custom header
web.header("X-Request-ID", request_id)

# Set Content-Type
web.header("Content-Type", "application/json")

# Prevent caching
web.header("Cache-Control", "no-cache, no-store, must-revalidate")
web.header("Pragma", "no-cache")
web.header("Expires", "0")
```

## Security Considerations

The webapi module includes several security features:

- **Header Validation**: All header values are validated against HTTP response splitting attacks by rejecting newline and carriage return characters
- **Cookie Encoding**: Cookie values are properly encoded and escaped
- **Input Processing**: Input data is processed safely to prevent injection attacks
- **SameSite Support**: Cookie SameSite attribute helps prevent CSRF attacks
- **HttpOnly Support**: Cookies can be marked as HttpOnly to prevent JavaScript access

## See Also

- [`web.http`](docs/http.md) - HTTP utilities
- [`web.wsgi`](docs/wsgi.md) - WSGI interface
- [`web.utils`](docs/utils.md) - Utility functions
