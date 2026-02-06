# Web HTTP Utilities Documentation

This document describes the HTTP utility functions in `web/http.py`, which provide helper functions for working with HTTP headers, URL manipulation, and request/response handling.

## Overview

The http module provides various utility functions for HTTP operations including setting cache headers, handling conditional requests, URL encoding, and profiling. These utilities are commonly used in web.py applications to handle common HTTP patterns and improve performance.

## Functions

### `prefixurl(base="")`
Generates a relative URL prefix based on the current path depth. This is useful for creating relative links that work correctly regardless of the current URL depth.

**Parameters:**
- `base`: Base path string to prepend (default: "")

**Returns:** Relative path prefix like "../" or "./"

**Example:**
```python
# If current path is /foo/bar/baz
prefixurl()  # Returns: "../../"
prefixurl("static/")  # Returns: "../../static/"
```

### `expires(delta)`
Sets an HTTP `Expires` header based on a time delta from now. This header tells browsers when the cached content should be considered stale.

**Parameters:**
- `delta`: A `timedelta` object or number of seconds until expiration

**Returns:** None (sets HTTP header)

**Example:**
```python
import datetime

# Set cache to expire in 1 hour
expires(3600)

# Set cache to expire in 24 hours
expires(datetime.timedelta(hours=24))
```

### `lastmodified(date_obj)`
Sets an HTTP `Last-Modified` header. This header indicates when the resource was last changed, enabling conditional requests.

**Parameters:**
- `date_obj`: A datetime object representing the last modification time

**Returns:** None (sets HTTP header)

**Example:**
```python
import datetime

# Set last modified date
lastmodified(datetime.datetime(2023, 1, 1, 12, 0, 0))
```

### `modified(date=None, etag=None)`
Handles conditional requests using `Last-Modified` and `ETag` headers. This function implements HTTP caching validation to avoid sending unchanged content.

When a client makes a request, it may include `If-Modified-Since` and `If-None-Match` headers. This function checks these against the provided `date` and `etag` values:

- If the resource hasn't been modified, it raises `web.notmodified()` (which sends a 304 response)
- If the resource has been modified or no validation headers are present, it sets the appropriate response headers and returns `True`

**Parameters:**
- `date`: Last modification date (datetime object) for `Last-Modified` header
- `etag`: Entity tag string for `ETag` header (opaque token for version identification)

**Returns:** 
- `True` if validation passes (resource hasn't been modified)
- Raises `web.notmodified()` if resource hasn't been modified (client cache is valid)

**Example:**
```python
import datetime

def GET(self):
    last_modified = datetime.datetime(2023, 1, 1)
    etag = "abc123"
    
    if modified(date=last_modified, etag=etag):
        # Resource hasn't been modified, send normal response
        return render.page()
```

### `urlencode(query, doseq=False)`
Encodes a dictionary into a URL-encoded query string, supporting Unicode strings.

**Parameters:**
- `query`: Dictionary of query parameters
- `doseq`: If True, handles list values by creating multiple parameters (default: False)

**Returns:** URL-encoded string

**Example:**
```python
urlencode({'text': 'foo bar'})  # Returns: 'text=foo+bar'
urlencode({'x': [1, 2]}, doseq=True)  # Returns: 'x=1&x=2'
```

### `changequery(query=None, **kw)`
Creates a new URL with modified query parameters. This is useful for updating URLs while preserving existing parameters.

**Parameters:**
- `query`: Existing query parameters dictionary (defaults to current GET parameters from `web.rawinput()`)
- `**kw`: Keyword arguments specifying parameter changes. Set a parameter to `None` to remove it.

**Returns:** New URL string with updated parameters

**Example:**
```python
# If current URL is /foo?a=1&b=2
changequery(a=3)  # Returns: '/foo?a=3&b=2'
changequery(a=None)  # Returns: '/foo?b=2' (removes 'a')
changequery(page=2, sort='name')  # Returns: '/foo?a=1&b=2&page=2&sort=name'
```

### `url(path=None, doseq=False, **kw)`
Creates a full URL by combining the home path with a given path and optional query parameters.

**Parameters:**
- `path`: Path to append (defaults to current path `web.ctx.path`)
- `doseq`: If True, handles list values in query parameters (default: False)
- `**kw`: Query parameters to append

**Returns:** Full URL string

**Example:**
```python
# If web.ctx.homepath is 'http://example.com'
url('/api/users')  # Returns: 'http://example.com/api/users'
url('/api/users', limit=10, offset=20)  # Returns: 'http://example.com/api/users?limit=10&offset=20'
url(doseq=True, tags=['python', 'web'])  # Returns: 'http://example.com/current?tags=python&tags=web'
```

### `profiler(app)`
Wraps a WSGI application with profiling information. This decorator adds profiling output to each response for performance analysis.

**Parameters:**
- `app`: WSGI application to profile

**Returns:** Wrapped WSGI application that outputs profiling info at the bottom of each response

**Example:**
```python
app = web.application(urls, globals())
app = profiler(app)  # Enable profiling
```

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
- `web.net` for HTTP date utilities (`httpdate`, `parsehttpdate`)
- `web.utils` for utility functions (`safestr`)
- `web.webapi` for web context access (`ctx`, `header`, `notmodified`, `rawinput`)
- `web.py3helpers` for Python 3 compatibility (`iteritems`)

## Usage Examples

### Setting Cache Headers
```python
import datetime

# Set cache to expire in 1 hour
expires(3600)

# Set last modified date
lastmodified(datetime.datetime.now())

# Combine both for better caching
expires(3600)
lastmodified(article.updated_at)
```

### Handling Conditional Requests
```python
import datetime

def GET(self):
    # Get article from database
    article = db.get_article(id)
    
    # Check if page has been modified
    last_modified = article.updated_at
    etag = f"article-{article.id}-{article.version}"
    
    if modified(date=last_modified, etag=etag):
        # Page hasn't been modified, return normal content
        return render.article(article=article)
    # If modified() returns True, continue with normal processing
    # If it raises notmodified(), the response is already handled
```

### URL Manipulation
```python
# Create a new URL with modified parameters
new_url = changequery(page=2, sort='name')

# Build full URLs
full_url = url('/api/users', limit=10, offset=20)

# Preserve current parameters while adding new ones
updated_url = changequery(filter='active', order='desc')
```

### URL Encoding
```python
# Simple encoding
query = urlencode({'search': 'hello world'})
# Result: 'search=hello+world'

# Encoding with sequences
query = urlencode({'tags': ['python', 'web']}, doseq=True)
# Result: 'tags=python&tags=web'
