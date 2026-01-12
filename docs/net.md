# Web Network Utilities Documentation

This document describes the network utility functions in `web/net.py`, which provide various helper functions for IP address validation, URL encoding, HTTP date handling, and HTML escaping.

## Overview

The net module contains essential networking utilities used throughout the web.py framework. It provides functions for validating IP addresses (both IPv4 and IPv6), handling HTTP dates, encoding/decoding URLs and HTML entities, and ensuring safe string handling for web applications.

## Functions

### `validip6addr(address)`
Validates an IPv6 address.

**Parameters:**
- `address` (str): The IPv6 address to validate

**Returns:**
- `bool`: True if the address is valid, False otherwise

**Examples:**
```python
validip6addr('::')  # True
validip6addr('aaaa:bbbb:cccc:dddd::1')  # True
validip6addr('1:2:3:4:5:6:7:8:9:10')  # False
```

### `validipaddr(address)`
Validates an IPv4 address.

**Parameters:**
- `address` (str): The IPv4 address to validate

**Returns:**
- `bool`: True if the address is valid, False otherwise

**Examples:**
```python
validipaddr('192.168.1.1')  # True
validipaddr('192.168. 1.1')  # False
validipaddr('192.168.1.800')  # False
```

### `validipport(port)`
Validates an IPv4 port number.

**Parameters:**
- `port` (str): The port number to validate

**Returns:**
- `bool`: True if the port is valid, False otherwise

**Examples:**
```python
validipport('9000')  # True
validipport('foo')  # False
validipport('1000000')  # False
```

### `validip(ip, defaultaddr="0.0.0.0", defaultport=8080)`
Parses an IP address and port string into a tuple.

**Parameters:**
- `ip` (str): IP address string in various formats
- `defaultaddr` (str): Default IP address if not specified
- `defaultport` (int): Default port if not specified

**Returns:**
- `tuple`: (ip_address, port) tuple

**Examples:**
```python
validip('1.2.3.4')  # ('1.2.3.4', 8080)
validip('80')  # ('0.0.0.0', 80)
validip('192.168.0.1:85')  # ('192.168.0.1', 85)
validip('[::]')  # ('::', 8080)
validip('[::]:88')  # ('::', 88)
validip('[::1]:80')  # ('::1', 80)
```

### `validaddr(string_)`
Parses an address string that can be either a Unix socket path or IP address/port.

**Parameters:**
- `string_` (str): Address string

**Returns:**
- `str` or `tuple`: Either a socket path string or (ip_address, port) tuple

**Examples:**
```python
validaddr('/path/to/socket')  # '/path/to/socket'
validaddr('8000')  # ('0.0.0.0', 8000)
validaddr('127.0.0.1:8000')  # ('127.0.0.1', 8000)
validaddr('[::1]:80')  # ('::1', 80)
```

### `urlquote(val)`
URL-encodes a string for use in URLs.

**Parameters:**
- `val` (str): Value to encode

**Returns:**
- `str`: URL-encoded string

**Examples:**
```python
urlquote('://?f=1&j=1')  # '%3A//%3Ff%3D1%26j%3D1'
urlquote(None)  # ''
```

### `httpdate(date_obj)`
Formats a datetime object for use in HTTP headers.

**Parameters:**
- `date_obj` (datetime): Datetime object to format

**Returns:**
- `str`: Formatted date string

**Examples:**
```python
import datetime
httpdate(datetime.datetime(1970, 1, 1, 1, 1, 1))  # 'Thu, 01 Jan 1970 01:01:01 GMT'
```

### `parsehttpdate(string_)`
Parses an HTTP date string into a datetime object.

**Parameters:**
- `string_` (str): HTTP date string

**Returns:**
- `datetime` or `None`: Parsed datetime object or None if invalid

**Examples:**
```python
parsehttpdate('Thu, 01 Jan 1970 01:01:01 GMT')  # datetime.datetime(1970, 1, 1, 1, 1, 1)
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
- `validip6addr`
- `validipaddr`
- `validipport`
- `validip`
- `validaddr`
- `urlquote`
- `httpdate`
- `parsehttpdate`
- `htmlquote`
- `htmlunquote`
- `websafe`

## Usage Examples

### IP Address Validation
```python
# Validate IPv4 addresses
if validipaddr('192.168.1.1'):
    print("Valid IP address")

# Validate IPv6 addresses  
if validip6addr('::1'):
    print("Valid IPv6 address")

# Parse IP with port
ip, port = validip('192.168.0.1:8080')

# Parse IPv6 with port
ip, port = validip('[::1]:80')
```

### HTTP Date Handling
```python
import datetime

# Format date for HTTP headers
now = datetime.datetime.now()
date_header = httpdate(now)

# Parse HTTP date
parsed_date = parsehttpdate(date_header)
```

### URL and HTML Encoding
```python
# URL encode data
encoded = urlquote('hello world & special chars')

# HTML encode text
safe_html = htmlquote('<script>alert("xss")</script>')

# Safe web output
safe_output = websafe(user_input)
```
