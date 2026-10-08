# Web Application Documentation

This document describes the web.py framework's core application classes and utilities. The framework provides a simple yet powerful way to build web applications with clean URL routing and request handling.

## Overview

The `application` class is the foundation of the web.py framework, handling HTTP requests by routing them to appropriate handlers based on URL patterns. It supports features like auto-reloading during development, middleware processing, and integration with WSGI servers.

## Exports

The `application` module exports the following:

- [`application`](#application) - Main application class for routing requests
- [`auto_application`](#auto_application) - Application with automatic URL registration
- [`subdir_application`](#subdir_application) - Alias for [`application`](#application)
- [`subdomain_application`](#subdomain_application) - Application routing by host domain
- [`loadhook`](#loadhook) - Hook function called before request handling
- [`unloadhook`](#unloadhook) - Hook function called after request handling
- [`autodelegate`](#autodelegate) - Method for automatic delegation to prefixed methods

## Classes

### `application`

The main application class responsible for routing requests and processing them through registered handlers and processors.

#### Constructor

```python
def __init__(
    self,
    mapping: Iterable[Union[str, "application", Any]] = (),
    fvars: Dict[str, Any] = {},
    autoreload: Optional[bool] = None,
)
```

**Parameters:**
- `mapping`: A list of URL patterns paired with handler classes or functions. For example: `("/hello", "hello")`.
- `fvars`: A dictionary of global variables available to the application (typically `globals()`).
- `autoreload`: Whether to enable automatic reloading of modules when changes are detected. Defaults to `web.config.debug` if not specified.

#### Methods

##### `add_mapping(pattern, classname)`

Adds a new URL pattern and handler to the application.

**Example:**
```python
app.add_mapping("/about", "AboutHandler")
```

##### `add_processor(processor)`

Adds a processor function to the application. Processors wrap request handling and can modify behavior before or after the main handler.

**Example:**
```python
def log_request(handler):
    print("Request started")
    return handler()

app.add_processor(log_request)
```

##### `browser()`

Returns an `AppBrowser` instance for testing the application.

**Example:**
```python
browser = app.browser()
browser.open("/hello")
```

##### `request(localpart: str = "/", method: str = "GET", data: Optional[Union[str, bytes, Dict[str, Any]]] = None, host: str = "0.0.0.0:8080", headers: Optional[Dict[str, str]] = None, https: bool = False, **kw: Any) -> web.storage`

Simulates a request to the application for testing purposes.

**Parameters:**
- `localpart`: The full URL path (including query string), e.g., `/hello?name=world`.
- `method`: HTTP method (GET, POST, etc).
- `data`: Request body data (for POST/PUT requests).
- `host`: Host address for the request.
- `headers`: Dictionary of HTTP headers.
- `https`: Whether to simulate HTTPS.

**Returns:** A `storage` object with `data`, `status`, and `headers`.

**Example:**
```python
response = app.request("/hello", headers={"User-Agent": "Test Client"})
assert response.data == b"Hello, world!"
```

##### `handle()`

Handles the current request by matching URL patterns and delegating to appropriate handlers.

##### `handle_with_processors()`

Handles the request with all registered processors applied in order.

##### `wsgifunc(*middleware)`

Returns a WSGI-compatible function for this application. Accepts optional middleware functions to wrap the application.

**Example:**
```python
wsgi_app = app.wsgifunc(middleware1, middleware2)
```

##### `run(*middleware)`

Starts handling HTTP requests. If called in a CGI or FastCGI context, follows that protocol. When run from the command line, starts an HTTP server on port 8080 (or specified port).

**Example:**
```python
if __name__ == "__main__":
    app.run()
```

##### `stop()`

Stops the HTTP server started by `run()`.

##### `cgirun(*middleware)`

Immediately executes a CGI runner; it does **not** return a WSGI callable for later use. It first builds `app.wsgifunc(*middleware)`, then tries the legacy `google.appengine.ext.webapp.util.run_wsgi_app` import and calls that runner with the wrapped application. If this raises `ImportError`, it falls back to `wsgiref.handlers.CGIHandler().run(wsgiapp)`. Its return value is the selected runner's result.

This is a legacy execution path, not a claim of compatibility with current Google hosting. To obtain a WSGI callable without executing a runner, use [`app.wsgifunc(*middleware)`](#wsgifuncmiddleware) instead.

##### `gaerun(*middleware)`

Legacy entry point for the old Google App Engine Python 2.5/2.7 API. It is **unusable on this package's current Python 3 runtime**: after constructing the middleware-wrapped WSGI callable, it raises `OSError("Google App Engine only supports python 2.5 and 2.7")` without invoking a runner. That historical error describes this helper's obsolete API restriction, not the Python versions supported by modern Google platforms.

Use [`app.wsgifunc(*middleware)`](#wsgifuncmiddleware) to obtain a WSGI callable, and configure an appropriate WSGI server separately. Neither this recommendation nor the legacy helpers certify a Google deployment.

##### `load(env)`

Initializes the request context (`web.ctx`) using the WSGI environment dictionary.

##### `_load()`

Internal method called by the `loadhook` to initialize the application on each request. It pushes the application onto the `web.ctx.app_stack`.

##### `_unload()`

Internal method called by the `unloadhook` to clean up after a request. It pops the application from the `web.ctx.app_stack` and restores the previous context if it was a sub-application.

##### `_cleanup()`

Internal method to clear thread-local state. It is called at the beginning and end of each request to ensure that thread-local data from one request does not interfere with subsequent requests.

##### `_delegate(f, fvars, args=[])`

Internal method to delegate request handling to appropriate handlers based on matched patterns.

##### `_match(mapping, value)`

Internal method to match URL patterns against the request path.

##### `_delegate_sub_application(dir, app)`

Handles requests to sub-applications by adjusting the context paths.

##### `get_parent_app()`

Returns the parent application from the context stack.

##### `notfound()`

Returns a 404 Not Found HTTP error.

##### `internalerror()`

Returns a 500 Internal Server Error HTTP error.

### `auto_application`

A subclass of `application` that automatically registers classes inheriting from `app.page` as URL handlers based on their class names.

**Example:**
```python
app = auto_application()

class hello(app.page):
    def GET(self):
        return "Hello, world!"

class foo(app.page):
    path = "/foo/.*"
    def GET(self):
        return "Foo"

# Requests to /hello and /foo/bar will be handled automatically.
```

### `subdir_application`

Alias for [`application`](#application). Provides the same functionality for handling subdirectory-based applications.

### `subdomain_application`

Routes requests based on the host domain.

**Example:**
```python
mapping = (r"hello\.example\.com", app)
app2 = subdomain_application(mapping)

# Requests to hello.example.com will be handled by 'app'
```

## Hooks

### `loadhook(h)`

Converts a load hook function into an application processor. The hook runs before request handling.

**Example:**
```python
def log_start():
    print("Request started")

app.add_processor(loadhook(log_start))
```

### `unloadhook(h)`

Converts an unload hook function into an application processor. The hook runs after request handling.

**Example:**
```python
def log_end():
    print("Request ended")

app.add_processor(unloadhook(log_end))
```

## Utilities

### `autodelegate(prefix="")`

Returns a method that delegates to methods with the specified prefix. Useful for automatically routing sub-paths.

**Example:**
```python
class Prefs:
    GET = autodelegate('GET_')
    
    def GET_password(self):
        return "Password settings"
        
    def GET_privacy(self):
        return "Privacy settings"

# /prefs/password → GET_password()
# /prefs/privacy → GET_privacy()
```

### `with_metaclass(mcls)`

Returns a class decorator that recreates the decorated class using `mcls`, preserving its name, bases and class body (apart from the `__dict__` and `__weakref__` descriptors). It is not a base-class factory. Import it explicitly from `web.application`.

**Example:**
```python
from web.application import with_metaclass

class MyMeta(type):
    pass

@with_metaclass(MyMeta)
class MyClass:
    pass
```

### `Reloader`

A class that checks for changes in loaded modules and reloads them when necessary. Used for auto-reloading during development.

**Note:** Automatically enabled when `autoreload=True` in the application constructor.

## Example Usage

```python
import web

urls = (
    "/hello", "hello",
    "/.*", "notfound"
)

class hello:
    def GET(self):
        return "Hello, world!"

class notfound:
    def GET(self):
        raise web.notfound()

app = web.application(urls, globals())
app.run()
```

This example creates a simple application with two routes: `/hello` and a catch-all for 404. The catch-all `/.*` has no capture group, matching `notfound.GET(self)`; a capturing pattern such as `/(.*)` would pass an extra path argument to the method.
