# Web HTTP Server Documentation

This document describes the HTTP server utilities in `web/httpserver.py`, which provide tools for running WSGI applications with built-in static file serving and logging capabilities.

## Overview

The httpserver module provides functions for running WSGI applications using different web servers. It includes support for static file serving, request logging, and various middleware components to enhance the development experience.

## Functions

### `runsimple(func, server_address=("0.0.0.0", 8080))`

Runs a WSGI app using Cheroot (the CherryPy-derived WSGI server).

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
- The global `server` variable is set to the WSGIServer instance; see the lifecycle and ownership rules below.
- The WSGI callable is wrapped with `StaticMiddleware`, then `LogMiddleware`, before creating the server.
- The default `0.0.0.0:8080` is a wildcard listener, potentially reachable from other machines; it is not loopback isolation. Examples here explicitly use `127.0.0.1`.

### `runbasic(func, server_address=("0.0.0.0", 8080))`

**Unsupported legacy code in this Python 3 revision, not a deployment option.**
Calling it raises `ModuleNotFoundError: No module named 'SocketServer'` before
any socket bind or WSGI request. No compatibility alias is installed here.
The module uses Python 3 imports and syntax; this is not a working Python 2
compatibility path either. The unreachable nested handler is historical code,
not a supported server contract. Use the Cheroot `WSGIServer` / `runsimple`
path below instead; this documentation change does not port `runbasic`.

### `WSGIServer(server_address, wsgi_app)`

Creates a Cheroot WSGI server instance; construction alone does not start it or add static/logging wrappers.

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
```text
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
```text
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
```text
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

**Note:** `runbasic` remains a module attribute, but is unsupported legacy code (see above).

## Usage Examples

### Stopping the Server

`runsimple` calls `server.start()` synchronously: it **blocks**, and returns
`None`, not a server handle. Code immediately after it cannot stop an actively
serving server. Another controlling thread may use `web.httpserver.server`,
but must synchronize startup and retain the exact instance it owns. Normal
external `stop()` lets `runsimple` return and **retains** the stopped global
instance. `KeyboardInterrupt` or `SystemExit` from `start()` instead invokes
`stop()` and clears the global to `None`. Other exceptions propagate; there is
no general cleanup guarantee. `application.stop()` uses this same global.

Prefer an explicit instance for an embedded lifecycle. This self-contained,
bounded smoke example serves one actual HTTP request, then stops and joins its
own thread even on request failure. It does not set the `httpserver.server`
global. `prepare()` completes binding/worker setup before the thread starts;
an Event confirms entry to the serving thread, not a guessed startup sleep.
The socket's actual address supplies the ephemeral port. Cheroot's port-zero
mode requires `reuse_port=False` (the framework factory defaults to True).

```python
import http.client
import threading
import web

web.config.debug = False  # before constructing the application

class index:
    def GET(self):
        return "Hello World!"

app = web.application(("/", "index"), globals(), autoreload=False)
wrapped = web.httpserver.LogMiddleware(
    web.httpserver.StaticMiddleware(app.wsgifunc())
)
server = web.httpserver.WSGIServer(("127.0.0.1", 0), wrapped)
server.reuse_port = False
server.shutdown_timeout = 2
entered = threading.Event()
errors = []

def serve():
    entered.set()
    try:
        server.serve()
    except BaseException as exc:
        errors.append(exc)

thread = threading.Thread(target=serve, name="owned-wsgi-example")
connection = None
try:
    try:
        server.prepare()  # synchronous readiness; do not call start() again
        address = server.socket.getsockname()
        assert server.ready and address[0] == "127.0.0.1"
        thread.start()
        if not entered.wait(5):
            raise RuntimeError("Serving thread did not enter")
        connection = http.client.HTTPConnection(*address[:2], timeout=3)
        connection.request("GET", "/")
        response = connection.getresponse()
        status, body = response.status, response.read()
        assert status == 200 and body == b"Hello World!"
    finally:
        if connection is not None:
            connection.close()
        was_ready = server.ready
        try:
            server.stop()
        finally:
            # prepare() can fail before ready=True; stop() then does nothing.
            if not was_ready:
                server.requests.stop(2)
                if getattr(server, "_connections", None) is not None:
                    server._connections.close()
                if getattr(server, "socket", None) is not None:
                    server.socket.close()
                    server.socket = None
            if thread.ident is not None:
                thread.join(5)
                if thread.is_alive():
                    raise RuntimeError("Owned serving thread did not stop")
except BaseException as exc:
    # Check only after cleanup/join, including when the HTTP request failed.
    if errors:
        raise errors[0] from exc
    raise
if errors:
    raise errors[0]
print(status, body.decode("utf-8"))
```

After cleanup and the serving-thread join, a captured serving failure takes
precedence: the same exception is raised with its original traceback. If the
main thread also failed (for example, HTTP timed out because serving stopped),
that exception is retained as its explicit cause. When cleanup succeeds and
there is no serving failure, the original setup/request exception propagates
unchanged; it is not replaced by a generic lifecycle error.

The timeouts bound this smoke check, not arbitrary application handlers or
native code. A deployment needs its own process supervisor and shutdown policy.
The explicit wrapper order matches `runsimple`: LogMiddleware outside
StaticMiddleware. Static content is rooted in the current working directory,
selected by the `/static/` prefix; the factory alone adds neither wrapper.
Changing the prefix does not specify a separate filesystem root. This example
does not certify static-file access policy or production TLS.

## Features

1. **Static File Serving**: Automatically serves files from `static/` directory (configurable prefix)
2. **Request Logging**: Logs all HTTP requests with timestamps, host, protocol, method, path, and status codes
3. **Server backend**: Cheroot (`runsimple`); the legacy `runbasic` entry point is broken.
4. **Control exceptions**: `runsimple` stops on KeyboardInterrupt/SystemExit; other exceptions propagate.
5. **Middleware Support**: Extensible through WSGI middleware components (`StaticMiddleware`, `LogMiddleware`)
6. **Cross-platform**: Works on different operating systems with platform-specific optimizations
7. **ETag Support**: Static file serving includes ETag-based caching support
8. **SSL Support**: CherryPy server supports SSL when `ssl_adapter` is configured

## Dependencies

This module imports:
- `os`, `posixpath`, `sys` for file operations and path handling
- `http.server` for Python 3 HTTP handler helpers
- `io.BytesIO` for temporary data storage
- `urllib.parse.unquote`, `urlparse` for Python 3 URL parsing
- `web.utils` for utility functions (e.g., `safestr`)
- `web.webapi` for web context access (`web.debug`)
- `cheroot.wsgi` for CherryPy WSGI server (when available via `runsimple`)
- The obsolete `SocketServer` import is the immediate failure in `runbasic`.

## Notes

- These helpers are not a production security configuration. Disable debug explicitly before application construction; see [WSGI configuration](wsgi.md).
- Optional TLS requires a separately configured `ssl_adapter` before startup. TLS/certificates are untested here; no production certification is implied.
- `runbasic` is unsupported legacy code; do not use it for testing or deployment.
- The global `server` variable in `runsimple` allows for programmatic server control
- Static file serving is implemented via `StaticMiddleware` wrapping the WSGI application
- Request logging is implemented via `LogMiddleware` and outputs to `web.debug` by default
