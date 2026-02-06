# Web HTTP Server Documentation

This document describes the HTTP server utilities in `web/httpserver.py`, which provide tools for running WSGI applications with built-in static file serving and logging capabilities.

## Overview

The httpserver module provides functions for running WSGI applications using different web servers. It includes support for static file serving, request logging, and various middleware components to enhance the development experience.

## Functions

### `runsimple(func, server_address=("0.0.0.0", 8080))`

Runs a WSGI server hosting a WSGI app with static file serving using the CherryPy WSGI server.

**Parameters:**
- `func`: WSGI application function
- `server_address`: Tuple of (host, port) to bind the server to (default: ("0.0.0.0", 8080))

**Returns:** None (starts server and blocks)

**Features:**
- Serves static files from the `static/` directory by default
- Uses CherryPy WSGI server via `cheroot.wsgi.Server`
- Provides request logging through `LogMiddleware`
- Handles keyboard interrupts gracefully
- Supports SSL when `server.ssl_adapter` is configured

**Notes:**
- The global `server` variable is set to the WSGIServer instance, allowing it to be stopped in embedded mode
- The server is wrapped with `StaticMiddleware` and `LogMiddleware` before starting

### `runbasic(func, server_address=("0.0.0.0", 8080))`

Runs a basic HTTP server hosting a WSGI app using Python's built-in HTTP server (Python 2 compatible).

**Parameters:**
- `func`: WSGI application function
- `server_address`: Tuple of (host, port) to bind the server to (default: ("0.0.0.0", 8080))

**Returns:** None (starts server and blocks)

**Features:**
- Serves static files from the `static/` directory
- Uses Python's built-in `http.server` module
- Handles basic HTTP methods (GET, POST, PUT, DELETE)
- Includes error handling for common network errors (ECONNABORTED, EPIPE)
- Supports Python 2's `SocketServer` module

**Notes:**
- This function is primarily for Python 2 compatibility
- Uses `WSGIHandler` class that extends `SimpleHTTPRequestHandler`
- The server runs in a blocking `serve_forever()` loop

### `WSGIServer(server_address, wsgi_app)`

Creates a CherryPy WSGI server instance.

**Parameters:**
- `server_address`: Tuple of (host, port) to bind the server to
- `wsgi_app`: WSGI application to serve

**Returns:** CherryPy WSGI Server instance (`cheroot.wsgi.Server`)

**Notes:**
- This function can be overwritten to customize the webserver or use a different webserver
- Sets `server.nodelay` based on platform (disabled on JVM)
- The server name is set to "localhost"

## Classes

### `StaticApp`

WSGI application for serving static files. Implements the WSGI callable interface.

**Constructor:**
```python
def __init__(self, environ, start_response)
```

**Parameters:**
- `environ`: WSGI environment dictionary
- `start_response`: WSGI start_response callable

**Methods:**
- `__iter__()`: Generator that yields file content in 16KB blocks
- `send_response(status, msg="")`: Sets HTTP response status code and message
- `send_header(name, value)`: Adds HTTP response header to the headers list
- `end_headers()`: Finalizes HTTP headers (no-op, headers sent in `__iter__`)
- `log_message(*a)`: Logs messages (no-op implementation)

**WSGI Interface:**
- Implements `__iter__` to yield file content
- Supports ETag-based caching with `HTTP_IF_NONE_MATCH` header
- Returns 304 Not Modified when client ETag matches server ETag

### `StaticMiddleware`

WSGI middleware for serving static files from a specified prefix.

**Constructor:**
```python
def __init__(self, app, prefix="/static/")
```

**Parameters:**
- `app`: The main WSGI application to delegate to when path doesn't match prefix
- `prefix`: URL prefix for static files (default: "/static/")

**Methods:**
- `__call__(environ, start_response)`: Middleware handler that delegates to StaticApp or main app based on path
- `normpath(path)`: Normalizes a file path using `posixpath.normpath` and `urllib.parse.unquote`

**Behavior:**
- If `PATH_INFO` starts with the prefix, serves static files via `StaticApp`
- Otherwise, delegates to the wrapped application
- Maintains trailing slashes in normalized paths

### `LogMiddleware`

WSGI middleware for logging HTTP requests with timestamps and status codes.

**Constructor:**
```python
def __init__(self, app)
```

**Parameters:**
- `app`: The WSGI application to log requests for

**Methods:**
- `__call__(environ, start_response)`: Wraps the application with logging functionality
- `log(status, environ)`: Logs request information to `wsgi.errors` or `web.debug`

**Log Format:**
```
host:port - - [timestamp] "protocol method path" - status
```

**Implementation Details:**
- Uses `BaseHTTPRequestHandler.log_date_time_string()` for timestamp formatting
- Wraps `start_response` to capture status before sending headers
- Logs to `environ.get("wsgi.errors", web.debug)` stream

## Constants

### `__all__`

List of public functions exported by this module:
- `runsimple`

**Note:** `runbasic` is not exported in `__all__` but is still available for use.

## Usage Examples

### Basic Server Setup

```python
import web

# Create a simple WSGI app
urls = ("/", "index")
class index:
    def GET(self): 
        return "Hello World!"

app = web.application(urls, globals())

# Run the server
web.httpserver.runsimple(app.wsgifunc(), ("0.0.0.0", 8080))
```

### With Static File Serving

```python
# The server automatically serves files from static/ directory
# Files in static/ are accessible at http://localhost:8080/static/filename

web.httpserver.runsimple(app.wsgifunc(), ("0.0.0.0", 8080))
```

### Custom Server Address

```python
# Run on a specific host and port
web.httpserver.runsimple(app.wsgifunc(), ("127.0.0.1", 8000))
```

### Stopping the Server

```python
# The global server variable can be used to stop the server
import web

# Start server
server = web.httpserver.runsimple(app.wsgifunc(), ("0.0.0.0", 8080))

# Stop server (in embedded mode or for testing)
web.httpserver.server.stop()
```

### Using runbasic (Python 2 compatibility)

```python
# Use the basic Python HTTP server
web.httpserver.runbasic(app.wsgifunc(), ("0.0.0.0", 8080))
```

## Features

1. **Static File Serving**: Automatically serves files from `static/` directory (configurable prefix)
2. **Request Logging**: Logs all HTTP requests with timestamps, host, protocol, method, path, and status codes
3. **Multiple Server Options**: Supports both basic Python HTTP server (`runbasic`) and CherryPy (`runsimple`)
4. **Error Handling**: Graceful handling of network errors (ECONNABORTED, EPIPE) and keyboard interrupts
5. **Middleware Support**: Extensible through WSGI middleware components (`StaticMiddleware`, `LogMiddleware`)
6. **Cross-platform**: Works on different operating systems with platform-specific optimizations
7. **ETag Support**: Static file serving includes ETag-based caching support
8. **SSL Support**: CherryPy server supports SSL when `ssl_adapter` is configured

## Dependencies

This module imports:
- `os`, `posixpath`, `sys` for file operations and path handling
- `http.server` for HTTP server functionality (Python 3) or `SimpleHTTPServer` (Python 2)
- `io.BytesIO` for temporary data storage
- `urllib.parse.unquote`, `urlparse` for URL parsing (Python 3) or `urlparse` (Python 2)
- `web.utils` for utility functions (e.g., `safestr`)
- `web.webapi` for web context access (`web.debug`)
- `cheroot.wsgi` for CherryPy WSGI server (when available via `runsimple`)
- `SocketServer` for Python 2 threading support (via `runbasic`)

## Notes

- The `runsimple` function is the recommended server for production use due to CherryPy's robustness
- The `runbasic` function is maintained for Python 2 compatibility and simple testing scenarios
- The global `server` variable in `runsimple` allows for programmatic server control
- Static file serving is implemented via `StaticMiddleware` wrapping the WSGI application
- Request logging is implemented via `LogMiddleware` and outputs to `web.debug` by default
