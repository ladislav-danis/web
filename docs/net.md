# Network Utilities Documentation

This document describes the network utility functions in [`net.py`](../net.py), which provide various helper functions for IP address validation, URL encoding, HTTP date handling, and HTML escaping.

## Overview

The net module provides IPv4/IPv6 address helpers, HTTP date formatting/parsing,
URL quoting, and five-character HTML escaping with its limited inverse. These
helpers have specific input and output-context limits, described below; they
are not general address canonicalizers or web-content sanitizers.

## Module Contents

The module exports the following functions via [`__all__`](#all):

- [`validipaddr()`](#validipaddr-address) - Check four integer-based IPv4 components
- [`validip6addr()`](#validip6addr-address) - Validate IPv6 address
- [`validipport()`](#validipport-port) - Validate port number
- [`validip()`](#validip-ip-defaultaddr0000-defaultport8080) - Parse IP:port string
- [`validaddr()`](#validaddr-string_) - Parse IP or Unix socket path
- [`urlquote()`](#urlquote-val) - URL-encode a string
- [`httpdate()`](#httpdate-date_obj) - Format datetime for HTTP headers
- [`parsehttpdate()`](#parsehttpdate-string_) - Parse HTTP date string
- [`htmlquote()`](#htmlquote-text) - HTML-encode text
- [`htmlunquote()`](#htmlunquote-text) - Invert five HTML entity replacements
- [`websafe()`](#websafe-val) - Convert a value to text and HTML-escape it

## Functions

All examples use the shared import setup `from web.net import *`. Run that
import first; each fence is otherwise independent. Expected representations
are for Python 3.

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

Returns `True` when a string splits on `.` into exactly four components,
none contains a literal ASCII space (`U+0020`), and each converts with
Python's `int()` to a value from 0 through 255 inclusive. Conversion
`ValueError` returns `False`.

This is a tolerant integer-based check, **not** strict validation of canonical
dotted-decimal spelling. It accepts leading `+`, leading zeros, surrounding
tabs/newlines, and other accepted `int()` grammar such as digit underscores
and Unicode decimal digits. It does not normalize the spelling. Use a
separate strict policy when canonical addresses are required (for example,
when comparing security-sensitive address identifiers).

**Parameters:**
- `address` (str): The four-component address string to check

**Returns:**
- `bool`: `True` if the four components satisfy the above check, `False` otherwise

**Examples:**
```python
>>> validipaddr('192.168.1.1')
True
>>> validipaddr('+1.002.3.4')
True
>>> validipaddr('1.2.3.\t4')
True
>>> validipaddr('1_0.2.3.4')
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

Quotes a value using UTF-8 percent-encoding, preserving `/`. This is not a
whole-URL validator or scheme allowlist. Choose quoting appropriate to the
intended URL component: preserving `/` is unsuitable when it must be encoded
as data within a single path segment. HTML escaping is a separate step when
putting a URL into a quoted HTML attribute.

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

Formats the supplied datetime fields with
`strftime("%a, %d %b %Y %H:%M:%S GMT")`. It appends literal `GMT`: it does
**not** convert time zones or validate that the input is UTC. Pass a UTC
datetime (or a naive datetime already known to represent UTC); explicitly
convert an aware non-UTC value with `date_obj.astimezone(datetime.timezone.utc)`
first. Do not assume a naive local `datetime.now()` is UTC.

The weekday/month names depend on `LC_TIME`; the helper does not enforce
English. HTTP headers require English names. The examples temporarily select
the `C` locale and restore it. Locale changes are process-wide: in a concurrent
application configure an appropriate locale at startup, not per request.

**Parameters:**
- `date_obj` (datetime.datetime): UTC fields to format; timezone offsets are not applied

**Returns:**
- `str`: Formatted date string in HTTP date format (e.g., `'Thu, 01 Jan 1970 01:01:01 GMT'`)

**Examples:**
```python
>>> import datetime
>>> import locale
>>> previous_locale = locale.setlocale(locale.LC_TIME)
>>> _ = locale.setlocale(locale.LC_TIME, 'C')
>>> httpdate(datetime.datetime(1970, 1, 1, 1, 1, 1))
'Thu, 01 Jan 1970 01:01:01 GMT'
>>> _ = locale.setlocale(locale.LC_TIME, previous_locale)
```

### `parsehttpdate(string_)`

Parses an HTTP date string using `time.strptime` and returns a **naive**
datetime (no `tzinfo`), or `None` on a parsing `ValueError`. Parsing also
depends on the process locale. For the shown English `GMT` input, use the
`C` locale; the returned fields represent UTC but are not timezone-aware.

**Parameters:**
- `string_` (str): HTTP date string in format `'Thu, 01 Jan 1970 01:01:01 GMT'`

**Returns:**
- `datetime.datetime` or `None`: Parsed datetime object or `None` if parsing fails

**Examples:**
```python
>>> import locale
>>> previous_locale = locale.setlocale(locale.LC_TIME)
>>> _ = locale.setlocale(locale.LC_TIME, 'C')
>>> parsehttpdate('Thu, 01 Jan 1970 01:01:01 GMT')
datetime.datetime(1970, 1, 1, 1, 1, 1)
>>> _ = locale.setlocale(locale.LC_TIME, previous_locale)
```

### `htmlquote(text)`
Escapes `&`, `<`, `>`, `'` and `"` to `&amp;`, `&lt;`, `&gt;`, `&#39;` and
`&quot;`, respectively, replacing `&` first. Use the result as HTML text or
inside an ordinary **quoted** HTML attribute. This is not JavaScript/CSS
escaping, URL validation, or an arbitrary HTML sanitizer: do not use it to
make inline script, event-handler code or an untrusted URL scheme safe.

**Parameters:**
- `text` (str): Text to encode

**Returns:**
- `str`: HTML-encoded string

**Examples:**
```python
>>> htmlquote("<'&\">")
'&lt;&#39;&amp;&quot;&gt;'
>>> htmlquote('\u203d')
'‽'
```

### `htmlunquote(text)`
Inverts the five substitutions made by `htmlquote`. It replaces exactly
`&quot;`, `&#39;`, `&gt;`, `&lt;`, then `&amp;`, in that order. Ampersand is
last, so a newly exposed entity is not recursively decoded.

This is **not a general HTML entity decoder**: alternative numeric spellings
such as `&#60;` and `&#x3c;`, and named entities such as `&apos;` and `&nbsp;`,
remain unchanged. Decoding is not sanitization; decoded text must be escaped
again before insertion into HTML text or a quoted attribute.

**Parameters:**
- `text` (str): Text containing the five supported entity spellings

**Returns:**
- `str`: String with only the five ordered replacements applied

**Examples:**
```python
>>> htmlunquote('&lt;tag&gt;')
'<tag>'
>>> original = "<'&\">"
>>> htmlunquote(htmlquote(original)) == original
True
>>> htmlunquote('&#60; &apos; &nbsp;')
'&#60; &apos; &nbsp;'
>>> htmlunquote('&amp;lt;')
'&lt;'
```

### `websafe(val)`
Converts `None` to an empty string, decodes bytes as UTF-8, or converts other
non-string values with `str()`, then applies `htmlquote`. The same HTML text /
quoted-attribute limits apply; the name does not imply JavaScript or URL safety.

**Parameters:**
- `val` (any): Value to convert and escape

**Returns:**
- `str`: HTML-escaped text

**Examples:**
```python
>>> websafe("<'&\">")
'&lt;&#39;&amp;&quot;&gt;'
>>> websafe(None)
''
>>> websafe('\u203d')
'‽'
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

Check IPv4 components (with the tolerant `int()` grammar described above):
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

Format a fixed UTC date for a deterministic HTTP header (6 February 2026 is
Friday). For a live timestamp use `datetime.datetime.now(datetime.timezone.utc)`
instead, with no fixed expected output:
```python
>>> import datetime
>>> import locale
>>> previous_locale = locale.setlocale(locale.LC_TIME)
>>> _ = locale.setlocale(locale.LC_TIME, 'C')
>>> fixed_utc = datetime.datetime(2026, 2, 6, 9, 1, 6, tzinfo=datetime.timezone.utc)
>>> date_header = httpdate(fixed_utc)
>>> date_header
'Fri, 06 Feb 2026 09:01:06 GMT'
>>> _ = locale.setlocale(locale.LC_TIME, previous_locale)
```

Parse the fixed HTTP date independently of the previous example:
```python
>>> import locale
>>> previous_locale = locale.setlocale(locale.LC_TIME)
>>> _ = locale.setlocale(locale.LC_TIME, 'C')
>>> date_header = 'Fri, 06 Feb 2026 09:01:06 GMT'
>>> parsed_date = parsehttpdate(date_header)
>>> parsed_date
datetime.datetime(2026, 2, 6, 9, 1, 6)
>>> parsed_date.tzinfo is None
True
>>> _ = locale.setlocale(locale.LC_TIME, previous_locale)
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
'&lt;script&gt;alert(&quot;xss&quot;)&lt;/script&gt;'
```

HTML-escaped text (not script/URL sanitization):
```python
>>> safe_output = websafe('<script>alert("xss")</script>')
>>> safe_output
'&lt;script&gt;alert(&quot;xss&quot;)&lt;/script&gt;'
```
