# Web Application Documentation

This document describes the web application framework implemented in `web/application.py`.

## Overview

The `application` class is the core component of the web.py framework that handles HTTP requests by delegating them based on URL patterns. It provides a flexible way to build web applications with clean URL routing and request processing.

## Classes

### `application`

The main application class that handles HTTP requests and routes them to appropriate handlers.

#### Constructor
```python
def __init__(self, mapping=(), fvars={}, autoreload=None)
```

**Parameters:**
- `mapping`: List of URL patterns and corresponding handlers
- `fvars`: Dictionary of global variables available to the application
- `autoreload`: Whether to enable auto-reloading during development

#### Methods

##### `add_mapping(pattern, classname)`
Adds a new URL pattern and handler to the application.

##### `add_processor(processor)`
Adds a processor to the application. Processors are functions that wrap request handling.

##### `request(localpart="/", method="GET", data=None, host="0.0.0.0:8080", headers=None, https=False, **kw)`
Makes a request to this application for the specified path and method.

**Parameters:**
- `localpart`: The URL path to request
- `method`: HTTP method (GET, POST, etc.)
- `data`: Request data
- `host`: Host address
- `headers`: HTTP headers as a dictionary
- `https`: Whether to use HTTPS

##### `handle()`
Handles the current request by matching URL patterns and delegating to appropriate handlers.

##### `handle_with_processors()`
Handles the request with all registered processors applied.

##### `wsgifunc(*middleware)`
Returns a WSGI-compatible function for this application.

##### `run(*middleware)`
Starts handling HTTP requests using WSGI.

##### `stop()`
Stops the HTTP server started by `run()`.

##### `cgirun(*middleware)`
Returns a CGI handler for Google App Engine.

##### `gaerun(*middleware)`
Returns a handler compatible with Google App Engine.

##### `load(env)`
Initializes ctx using env.

##### `_delegate(f, fvars, args=[])`
Delegates request handling to appropriate handlers based on the matched pattern.

##### `_match(mapping, value)`
Matches URL patterns against the request path.

##### `_delegate_sub_application(dir, app)`
Handles requests to sub-applications.

##### `get_parent_app()`
Get the parent application from the context stack.

##### `notfound()`
Returns HTTPError with '404 not found' message.

##### `internalerror()`
Returns HTTPError with '500 internal error' message.

### `auto_application`

An application that automatically constructs URL mappings using metaclass magic.

#### Constructor
```python
def __init__(self)
```

### `subdir_application`

An application that delegates requests based on the directory path (alias for `application`).

### `subdomain_application`

An application that delegates requests based on the host domain.

#### Methods

##### `handle()`
Handles requests by matching against host patterns.

##### `_match(mapping, value)`
Matches host patterns against the request host.

## Hooks

### `loadhook(h)`
Converts a load hook into an application processor.

### `unloadhook(h)`
Converts an unload hook into an application processor.

## Utilities

### `autodelegate(prefix="")`
Returns a method that automatically delegates to methods with a given prefix.

### `Reloader`
Checks for changes in loaded modules and reloads them when necessary.
