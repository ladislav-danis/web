# Network Utilities Documentation

This document describes the network utility functions in [`net.py`](../net.py), which provide various helper functions for IP address validation, URL encoding, HTTP date handling, and HTML escaping.

## Overview

The net module contains essential networking utilities used throughout the web.py framework. It provides functions for validating IP addresses (both IPv4 and IPv6), handling HTTP dates, encoding/decoding URLs and HTML entities, and ensuring safe string handling for web applications.

## Module Contents

The module exports the following functions via [`__all__`](#all):

- [`validipaddr()`](#validipaddreaddress) - Validate IPv4 address
- [`validip6addr()`](#validip6addreaddress) - Validate IPv6 address
- [`validipport()`](#validipporteport) - Validate port number
- [`validip()`](#validipeip-defaultaddr0000-defaultport8080) - Parse IP:port string
- [`validaddr()`](#validaddrestring_) - Parse IP or Unix socket path
- [`urlquote()`](#urlquoteval) - URL-encode a string
- [`httpdate()`](#httpdate-date_obj) - Format datetime for HTTP headers
- [`parsehttpdate()`](#parsehttpdate-string_) - Parse HTTP date string
- [`htmlquote()`](#htmlquotetext) - HTML-encode text
- [`htmlunquote()`](#htmlunquotetext) - HTML-decode text
- [`websafe()`](#websafeval) - Make value safe for HTML

## Functions

### `validip6addr(address)`

Returns `True` if `address` is a valid IPv6 address.

**Parameters:**
- `address` (str): The IPv6 address to validate

**Returns:**
- `bool`: `True` if the address is valid, `False` otherwise

**Examples:**
```python
>>> validip6addr('::')
True
>>> validip6addr('aaaa:bbbb:cccc:dddd::1')
True
>>> validip6addr('1:2:3:4:5:6:7:8:9:10')
False
>>> validip6addr('12:10')
False
```

### `validipaddr(address)`

Returns `True` if `address` is a valid IPv4 address.

**Parameters:**
- `address` (str): The IPv4 address to validate

**Returns:**
- `bool`: `True` if the address is valid, `False` otherwise

**Examples:**
```python
>>> validipaddr('192.168.1.1')
True
>>> validipaddr('192.168. 1.1')
False
>>> validipaddr('192.168.1.800')
False
>>> validipaddr('192.168.1')
False
```

### `validipport(port)`

Returns `True` if `port` is a valid IPv4 port.

**Parameters:**
- `port` (str): The port number to validate

**Returns:**
- `bool`: `True` if the port is valid, `False` otherwise

**Examples:**
```python
>>> validipport('9000')
True
>>> validipport('foo')
False
>>> validipport('1000000')
False
```

### `validip(ip, defaultaddr="0.0.0.0", defaultport=8080)`

Returns `(ip_address, port)` from string `ip`.

**Parameters:**
- `ip` (str): IP address string in various formats (IPv4, IPv6 with optional brackets, or just port)
- `defaultaddr` (str): Default IP address if not specified. Defaults to `"0.0.0.0"`
- `defaultport` (int): Default port if not specified. Defaults to `8080`

**Returns:**
- `tuple`: `(ip_address, port)` tuple

**Raises:**
- `ValueError`: If the input string is not a valid IP address/port combination

**Examples:**
```python
>>> validip('1.2.3.4')
('1.2.3.4', 8080)
>>> validip('80')
('0.0.0.0', 80)
>>> validip('192.168.0.1:85')
('192.168.0.1', 85)
>>> validip('::')
('::', 8080)
>>> validip('[::]:88')
('::', 88)
>>> validip('[::1]:80')
('::1', 80)
```

### `validaddr(string_)`

Returns either `(ip_address, port)` or `"/path/to/socket"` from `string_`.

**Parameters:**
- `string_` (str): Address string (either a Unix socket path containing `/` or an IP:port string)

**Returns:**
- `str` or `tuple`: Either a socket path string or `(ip_address, port)` tuple

**Raises:**
- `ValueError`: If the input is not a valid IP address/port and doesn't contain `/`

**Examples:**
```python
>>> validaddr('/path/to/socket')
'/path/to/socket'
>>> validaddr('8000')
('0.0.0.0', 8000)
>>> validaddr('127.0.0.1')
('127.0.0.1', 8080)
>>> validaddr('127.0.0.1:8000')
('127.0.0.1', 8000)
>>> validaddr('[::1]:80')
('::1', 80)
```

### `urlquote(val)`

Quotes a string for use in a URL.

**Parameters:**
- `val` (str): Value to encode. If `None`, returns empty string.

**Returns:**
- `str`: URL-encoded string

**Examples:**
```python
>>> urlquote('://?f=1&j=1')
'%3A//%3Ff%3D1%26j%3D1'
>>> urlquote(None)
''
>>> urlquote(u'\u203d')
'%E2%80%BD'
```

### `httpdate(date_obj)`

Formats a datetime object for use in HTTP headers.

**Parameters:**
- `date_obj` (datetime.datetime): Datetime object to format

**Returns:**
- `str`: Formatted date string in HTTP date format (e.g., `'Thu, 01 Jan 1970 01:01:01 GMT'`)

**Examples:**
```python
>>> import datetime
>>> httpdate(datetime.datetime(1970, 1, 1, 1, 1, 1))
'Thu, 01 Jan 1970 01:01:01 GMT'
```

### `parsehttpdate(string_)`

Parses an HTTP date string into a datetime object.

**Parameters:**
- `string_` (str): HTTP date string in format `'Thu, 01 Jan 1970 01:01:01 GMT'`

**Returns:**
- `datetime.datetime` or `None`: Parsed datetime object or `None` if parsing fails

**Examples:**
```python
>>> parsehttpdate('Thu, 01 Jan 1970 01:01:01 GMT')
datetime.datetime(1970, 1, 1, 1, 1, 1)
```

### `htmlquote(text)`
Encodes text for raw use in HTML.

**Parameters:**
- `text` (str): Text to encode

**Returns:**
- `str`: HTML-encoded string

**Examples:**
```python
htmlquote(u"<'&\">")  # u'&lt;&#39;&amp;&quot;&gt;'
htmlquote(u'\u203d')  # u'\u203d'
```

### `htmlunquote(text)`
Decodes HTML-quoted text.

**Parameters:**
- `text` (str): HTML-encoded text to decode

**Returns:**
- `str`: Decoded string

**Examples:**
```python
htmlunquote(u'&lt;&#39;&amp;&quot;&gt;')  # u'<\'&">'
htmlunquote(u'&lt;&#39;&amp;&quot;&gt;')  # u'<\'&">'
```

### `websafe(val)`
Converts a value to be safe for use in Unicode HTML.

**Parameters:**
- `val` (any): Value to make safe

**Returns:**
- `str`: Safe HTML string

**Examples:**
```python
websafe("<'&\">")  # u'&lt;&#39;&amp;&quot;&gt;'
websafe(None)  # u''
websafe(u'\u203d')  # u'\u203d'
```

## Constants

### `__all__`

List of public functions exported by this module:

```python
__all__ = [
    "validipaddr",
    "validip6addr",
    "validipport",
    "validip",
    "validaddr",
    "urlquote",
    "httpdate",
    "parsehttpdate",
    "htmlquote",
    "htmlunquote",
    "websafe",
]
```

## Usage Examples

### IP Address Validation

Validate IPv4 addresses:
```python
>>> validipaddr('192.168.1.1')
True
>>> validipaddr('192.168. 1.1')
False
>>> validipaddr('192.168.1.800')
False
```

Validate IPv6 addresses:
```python
>>> validip6addr('::1')
True
>>> validip6addr('aaaa:bbbb:cccc:dddd::1')
True
```

Parse IP with port:
```python
>>> ip, port = validip('192.168.0.1:8080')
>>> ip, port
('192.168.0.1', 8080)
```

Parse IPv6 with port:
```python
>>> ip, port = validip('[::1]:80')
>>> ip, port
('::1', 80)
```

### HTTP Date Handling

Format date for HTTP headers:
```python
>>> import datetime
>>> now = datetime.datetime.now()
>>> date_header = httpdate(now)
>>> date_header
'Thu, 06 Feb 2026 09:01:06 GMT'
```

Parse HTTP date:
```python
>>> parsed_date = parsehttpdate(date_header)
>>> parsed_date
datetime.datetime(2026, 2, 6, 9, 1, 6)
```

### URL and HTML Encoding

URL encode data:
```python
>>> encoded = urlquote('hello world & special chars')
>>> encoded
'hello%20world%20%26%20special%20chars'
```

HTML encode text:
```python
>>> safe_html = htmlquote('<script>alert("xss")</script>')
>>> safe_html
'<script>alert("xss")</script>'
```

Safe web output:
```python
>>> safe_output = websafe('<script>alert("xss")</script>')
>>> safe_output
'<script>alert("xss")</script>'
```
