# Web HTTP Server Documentation

This document describes the HTTP server utilities in `web/httpserver.py`, which provide tools for running WSGI applications with built-in static file serving and logging capabilities.

## Overview

The httpserver module provides functions for running WSGI applications using different web servers. It includes support for static file serving, request logging, and various middleware components to enhance the development experience.

## Functions

### `runsimple(func, server_address=("0.0.0.0", 8080))`
Runs a simple HTTP server hosting a WSGI app with static file serving.

**Parameters:**
- `func`: WSGI application function
- `server_address`: Tuple of (host, port) to bind the server to

**Returns:** None (starts server and blocks)

**Features:**
- Serves static files from the `static/` directory
- Uses CherryPy WSGI server by default
- Provides request logging
- Handles keyboard interrupts gracefully

### `runbasic(func, server_address=("0.0.0.0", 8080))`
Runs a basic HTTP server hosting a WSGI app using Python's built-in HTTP server.

**Parameters:**
- `func`: WSGI application function
- `server_address`: Tuple of (host, port) to bind the server to

**Returns:** None (starts server and blocks)

**Features:**
- Serves static files from the `static/` directory
- Uses Python's built-in HTTP server
- Handles basic HTTP methods (GET, POST, PUT, DELETE)
- Includes error handling for network issues

### `WSGIServer(server_address, wsgi_app)`
Creates a CherryPy WSGI server instance.

**Parameters:**
- `server_address`: Tuple of (host, port) to bind the server to
- `wsgi_app`: WSGI application to serve

**Returns:** CherryPy WSGI Server instance

## Classes

### `StaticApp`
WSGI application for serving static files.

#### Methods
- `__init__(environ, start_response)`: Initializes the static file handler
- `__iter__()`: Generator that yields file content
- `send_response(status, msg="")`: Sets HTTP response status
- `send_header(name, value)`: Adds HTTP response header
- `end_headers()`: Finalizes HTTP headers
- `log_message(*a)`: Logs messages (no-op)

### `StaticMiddleware`
WSGI middleware for serving static files.

#### Constructor
```python
def __init__(self, app, prefix="/static/")
```

**Parameters:**
- `app`: The main WSGI application
- `prefix`: URL prefix for static files (default: "/static/")

#### Methods
- `__call__(environ, start_response)`: Middleware handler that delegates to StaticApp or main app
- `normpath(path)`: Normalizes a file path

### `LogMiddleware`
WSGI middleware for logging HTTP requests.

#### Constructor
```python
def __init__(self, app)
```

**Parameters:**
- `app`: The WSGI application to log

#### Methods
- `__call__(environ, start_response)`: Wraps the application with logging
- `log(status, environ)`: Logs request information

## Constants

### `__all__`
List of public functions exported by this module:
- `runsimple`
- `runbasic`

## Usage Examples

### Basic Server Setup
```python
import web
from web import application

# Create a simple WSGI app
urls = ("/", "index")
class index:
    def GET(self): 
        return "Hello World!"

app = application(urls, globals())

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

## Features

1. **Static File Serving**: Automatically serves files from `static/` directory
2. **Request Logging**: Logs all HTTP requests with timestamps and status codes
3. **Multiple Server Options**: Supports both basic Python HTTP server and CherryPy
4. **Error Handling**: Graceful handling of network errors and interrupts
5. **Middleware Support**: Extensible through WSGI middleware components
6. **Cross-platform**: Works on different operating systems

## Dependencies

This module imports:
- `os`, `posixpath`, `sys` for file operations and path handling
- `http.server` for HTTP server functionality
- `io.BytesIO` for temporary data storage
- `urllib.parse.unquote`, `urlparse` for URL parsing
- `web.utils` for utility functions
- `web.webapi` for web context access
- `cheroot.wsgi` for CherryPy WSGI server (when available)
