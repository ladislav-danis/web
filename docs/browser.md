# Web Browser Documentation

This document describes the browser testing framework implemented in `web/browser.py`.

## Overview

The browser module provides tools for testing web applications by simulating browser interactions. It includes classes for making HTTP requests, parsing HTML responses, and interacting with forms and links.

## Classes

### `BrowserError`
Exception class raised when browser operations fail.

### `Browser`
Base browser class that handles HTTP requests and response parsing.

#### Constructor
```python
def __init__(self)
```

#### Properties
- `text`: Returns the response data as a UTF-8 decoded string.

#### Methods
- `reset()`: Clears all cookies and history.
- `build_opener()`: Builds an opener for making HTTP requests. Subclasses can override this method.
- `do_request(req)`: Performs an HTTP request with the given Request object.
- `open(url, data=None, headers={})`: Opens the specified URL with optional data and headers.
- `show()`: Opens the current page in a real web browser by saving it to a temporary file.
- `get_response()`: Returns a copy of the current response.
- `get_soup()`: Returns a BeautifulSoup object of the current document.
- `get_text(e=None)`: Returns content of element e or the current document as plain text.
- `_get_links()`: Returns all links in the current document.
- `get_links(text=None, text_regex=None, url=None, url_regex=None, predicate=None)`: Returns filtered links based on criteria.
- `follow_link(link=None, text=None, text_regex=None, url=None, url_regex=None, predicate=None)`: Follows a link by clicking it.
- `find_link(text=None, text_regex=None, url=None, url_regex=None, predicate=None)`: Finds the first matching link.
- `_filter_links(links, text=None, text_regex=None, url=None, url_regex=None, predicate=None)`: Filters links based on criteria.
- `get_forms()`: Returns all forms in the current document using ClientForm.
- `select_form(name=None, predicate=None, index=0)`: Selects a form by name or predicate.
- `submit(**kw)`: Submits the currently selected form.
- `__getitem__(key)`: Gets a form field value.
- `__setitem__(key, value)`: Sets a form field value.

### `AppBrowser`
Browser interface specifically designed for testing web.py applications.

#### Constructor
```python
def __init__(self, app)
```

**Parameters:**
- `app`: The web.py application to test

#### Methods
- Inherits all methods from `Browser` class.
- Overrides `build_opener()` to use `AppHandler`.

### `AppHandler`
HTTP handler that processes requests using a web.py application.

#### Constructor
```python
def __init__(self, app)
```

**Parameters:**
- `app`: The web.py application to handle requests

#### Methods
- `http_open(req)`: Handles HTTP requests by delegating to the application.
- `https_open(req)`: Handles HTTPS requests (delegates to `http_open`).
- `_make_response(result, url)`: Converts a web.py response into an HTTP response object.

## Constants

- `DEBUG`: Boolean flag for enabling debug output.

## Module Functions

None

## Usage Examples

```python
# Create browser for testing
b = AppBrowser(app)

# Navigate to a page
b.open('/')

# Follow a link
b.follow_link(text='Login')

# Fill and submit a form
b.select_form(name='login')
b['username'] = 'joe'
b['password'] = 'secret'
b.submit()

# Check results
assert b.path == '/'
assert 'Welcome joe' in b.get_text()
```
