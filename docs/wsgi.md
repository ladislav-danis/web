# Web WSGI Utilities Documentation

This document describes the WSGI utility functions in `web/wsgi.py`, which provide tools for running WSGI applications with various server backends and deployment configurations.

## Overview

The wsgi module contains utilities for deploying WSGI applications in different environments. It provides functions to run applications as FastCGI, SCGI, or using the built-in web server, automatically detecting the appropriate deployment method based on environment variables and command-line arguments.

## Functions

### `runfcgi(func, addr=("localhost", 8000))`
Runs a WSGI function as a FastCGI server.

**Parameters:**
- `func`: WSGI application function
- `addr` (tuple): Tuple of (host, port) to bind the server to

**Returns:** The result of the FastCGI server execution

**Dependencies:** Requires `flup` package for FastCGI support

### `runscgi(func, addr=("localhost", 4000))`
Runs a WSGI function as an SCGI server.

**Parameters:**
- `func`: WSGI application function
- `addr` (tuple): Tuple of (host, port) to bind the server to

**Returns:** The result of the SCGI server execution

**Dependencies:** Requires `flup` package for SCGI support

### `runwsgi(func)`
Runs a WSGI-compatible `func` using FCGI, SCGI, or a simple web server.

This function automatically detects the appropriate deployment method based on:
- Environment variables (SERVER_SOFTWARE, PHP_FCGI_CHILDREN)
- Command-line arguments (fcgi, fastcgi, scgi)
- Server environment (Heroku PORT variable)

**Parameters:**
- `func`: WSGI application function

**Returns:** The result of the server execution based on the environment

**Deployment Logic:**
1. **CGI Environment**: Uses FastCGI
2. **FastCGI Arguments**: Uses FastCGI with specified address
3. **SCGI Arguments**: Uses SCGI with specified address
4. **Heroku**: Uses built-in server on PORT environment variable
5. **Default**: Uses built-in web server with specified address

### `_is_dev_mode()`
Internal function that determines if the application is running in development mode.

**Returns:**
- `bool`: True if running in development mode, False otherwise

**Detection Logic:**
- Returns False if running under CGI, FastCGI, mod_wsgi, or other deployment environments
- Returns True otherwise (development mode)

**Note:** Some embedded Python interpreters may not have `sys.argv`, so the function safely handles this case.

## Constants and Configuration

### `web.config.debug`
Automatically set to True when running in development mode, False otherwise.

## Usage Examples

### Basic WSGI Deployment
```python
import web
from web import application

# Create a simple WSGI app
urls = ("/", "index")
class index:
    def GET(self): 
        return "Hello World!"

app = application(urls, globals())

# Run the application (automatically detects deployment method)
if __name__ == "__main__":
    web.wsgi.runwsgi(app.wsgifunc())
```

### FastCGI Deployment
```bash
# Run as FastCGI
python app.py fcgi

# Run as FastCGI with specific address
python app.py fcgi 127.0.0.1:9000
```

### SCGI Deployment
```bash
# Run as SCGI
python app.py scgi

# Run as SCGI with specific address
python app.py scgi 127.0.0.1:4000
```

### Heroku Deployment
```python
# On Heroku, the PORT environment variable is automatically used
# No special arguments needed - just run normally
web.wsgi.runwsgi(app.wsgifunc())
```

## Environment Variables

### `SERVER_SOFTWARE`
Set when running under CGI or web server environments.

### `PHP_FCGI_CHILDREN`
Set by lighttpd FastCGI.

### `PORT`
Set by Heroku and other cloud platforms for port configuration.

## Command Line Arguments

### `fcgi` or `fastcgi`
Run application as FastCGI server.

### `scgi`
Run application as SCGI server.

## Security Considerations

- The module automatically detects deployment environments to prevent inappropriate configurations
- Development mode debugging is enabled by default in development environments
- All server bindings use validated addresses through the `validaddr` utility

## Dependencies

This module requires:
- `flup` package for FastCGI and SCGI support (optional)
- `web.httpserver` for built-in web server functionality
- `web.net` for address validation
- `web.utils` for utility functions
