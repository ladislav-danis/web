# Web Browser Documentation

This document describes the browser testing framework implemented in [`browser.py`](../browser.py).

## Overview

The browser module provides tools for testing web applications by simulating browser interactions. It includes classes for making HTTP requests, parsing HTML responses, and interacting with forms and links.

## Module Exports

The module exports the following classes via `__all__`:
- `BrowserError`: Exception class for browser operations
- `Browser`: Base browser class for HTTP requests
- `AppBrowser`: Browser interface for testing web.py applications
- `AppHandler`: HTTP handler for web.py application requests

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
- `open(url, data=None, headers={})`: Opens the specified URL with optional data (string or bytes) and headers (dictionary).
- `show()`: Saves the current page to 'page.html' in the current working directory and opens it in the default web browser.
- `get_response()`: Returns a copy of the current response.
- `get_soup()`: Returns a BeautifulSoup object of the current document.
- `get_text(e=None)`: Returns the text content of element e or the current document as plain text, with HTML entities unquoted.
- `_get_links()`: Returns all links in the current document.
- `get_links(text=None, text_regex=None, url=None, url_regex=None, predicate=None)`: Returns filtered links based on criteria.
- `follow_link(link=None, text=None, text_regex=None, url=None, url_regex=None, predicate=None)`: Follows a link by clicking it.
- `find_link(text=None, text_regex=None, url=None, url_regex=None, predicate=None)`: Finds the first matching link.
- `_filter_links(links, text=None, text_regex=None, url=None, url_regex=None, predicate=None)`: Filters links based on criteria.
- `get_forms()`: Returns all forms in the current document using ClientForm.
- `select_form(name=None, predicate=None, index=0)`: Selects a form by name or predicate.
- `submit(**kw)`: Submits the currently selected form, passing any keyword arguments to the form's click method.
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

#### Attributes
- `handler_order`: Set to `100` to prioritize this handler.
- `https_request`: Alias for `HTTPHandler.do_request_` to support HTTPS.

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

### Basic Usage

```python
import web

app = web.application(urls, globals())
b = app.browser()  # Create browser for testing

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

### Working with Links

```python
# Find all links with 'example.com' in the URL
links = b.get_links(url_regex=r'example\.com')
for link in links:
    print(link['href'])

# Find a specific link by text
link = b.find_link(text='Sign Up')
if link:
    b.follow_link(link=link)
```

### Working with Forms

```python
# Select the second form with name 'login'
b.select_form(name='login', index=1)

# Access form fields
value = b['fieldname']
b['fieldname'] = 'value'
```

### Cookie Management

```python
# Clear all cookies and history
b.reset()
```

### Direct Browser Usage

```python
from web.browser import Browser, AppBrowser, AppHandler

# Using Browser directly
browser = Browser()
browser.open('http://example.com')
print(browser.text)
print(browser.status)
```

## API Reference

### BrowserError
Exception class raised when browser operations fail.

### Browser
Base browser class that handles HTTP requests and response parsing.

#### Constructor
```python
Browser()
```

#### Properties
- `text`: Returns the response data as a UTF-8 decoded string.
- `url`: The current URL after the last request.
- `path`: The current path after the last request.
- `status`: The HTTP status code of the last response.
- `data`: The raw response data (bytes).
- `form`: The currently selected form object.

#### Methods
- `reset()`: Clears all cookies and history.
- `build_opener()`: Builds an opener for making HTTP requests. Subclasses can override this method.
- `do_request(req)`: Performs an HTTP request with the given Request object. Returns the response.
- `open(url, data=None, headers={})`: Opens the specified URL with optional data (string or bytes) and headers (dictionary).
- `show()`: Saves the current page to 'page.html' in the current working directory and opens it in the default web browser.
- `get_response()`: Returns a copy of the current response as a file-like object.
- `get_soup()`: Returns a BeautifulSoup object of the current document for HTML parsing.
- `get_text(e=None)`: Returns the text content of element e or the current document as plain text, with HTML entities unquoted.
- `_get_links()`: Returns all links in the current document as a list of anchor elements.
- `get_links(text=None, text_regex=None, url=None, url_regex=None, predicate=None)`: Returns filtered links based on criteria. Returns a list of anchor elements.
- `follow_link(link=None, text=None, text_regex=None, url=None, url_regex=None, predicate=None)`: Follows a link by clicking it. Raises BrowserError if no link is found.
- `find_link(text=None, text_regex=None, url=None, url_regex=None, predicate=None)`: Finds the first matching link. Returns the link element or None.
- `_filter_links(links, text=None, text_regex=None, url=None, url_regex=None, predicate=None)`: Filters links based on criteria. Returns a list of matching link elements.
- `get_forms()`: Returns all forms in the current document using ClientForm. Returns a list of form objects.
- `select_form(name=None, predicate=None, index=0)`: Selects a form by name, predicate, or index. Returns the selected form object.
- `submit(**kw)`: Submits the currently selected form, passing any keyword arguments to the form's click method.
- `__getitem__(key)`: Gets a form field value by name.
- `__setitem__(key, value)`: Sets a form field value by name.

### AppBrowser
Browser interface specifically designed for testing web.py applications.

#### Constructor
```python
AppBrowser(app)
```

**Parameters:**
- `app`: The web.py application to test

#### Methods
- Inherits all methods from `Browser` class.
- Overrides `build_opener()` to use `AppHandler`.

### AppHandler
HTTP handler that processes requests using a web.py application.

#### Attributes
- `handler_order`: Set to `100` to prioritize this handler.
- `https_request`: Alias for `HTTPHandler.do_request_` to support HTTPS.

#### Constructor
```python
AppHandler(app)
```

**Parameters:**
- `app`: The web.py application to handle requests

#### Methods
- `http_open(req)`: Handles HTTP requests by delegating to the application.
- `https_open(req)`: Handles HTTPS requests (delegates to `http_open`).
- `_make_response(result, url)`: Converts a web.py response into an HTTP response object.

### Constants
- `DEBUG`: Boolean flag for enabling debug output (default: `False`).

## Dependencies

The browser module requires the following external libraries:
- [`BeautifulSoup`](https://www.crummy.com/software/BeautifulSoup/): For HTML parsing (used by `get_soup()`)
- [`ClientForm`](https://pythonhosted.org/ClientForm/): For form parsing and submission (used by `get_forms()` and `submit()`)

Note: These dependencies are not included in Python's standard library and must be installed separately.
