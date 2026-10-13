# Web HTTP Utilities Documentation

This document describes the HTTP utility functions in `web/http.py`, which provide helper functions for working with HTTP headers, URL manipulation, and request/response handling.

## Overview

The http module provides various utility functions for HTTP operations including setting cache headers, handling conditional requests, URL encoding, and profiling. These utilities are commonly used in web.py applications to handle common HTTP patterns and improve performance.

## Functions

### `prefixurl(base="")`
Appends one `../` to `base` for each slash in `web.ctx.path.lstrip("/")`.
If the result is empty, returns `./`. The base is a prefix, not a suffix;
this is string concatenation, not URL normalization. Empty/root paths and
`/foo` add no parent segment, `/foo/` adds one, and `/foo/bar/` adds two.

Each example on this page is self-contained and can run without a server.
Request-dependent helpers run inside real `application.request` handlers.

```python
import web

class Page:
    def GET(self):
        assert web.prefixurl() == "../../"
        assert web.prefixurl("static/") == "static/../../"
        # To put static after the parent segments, concatenate explicitly.
        return web.prefixurl() + "static/"

app = web.application(("/foo/bar/baz", Page), globals(), autoreload=False)
response = app.request("/foo/bar/baz")
assert response.status == "200 OK"
assert response.data == b"../../static/"
```

### `expires(delta)`
Sets an HTTP `Expires` header based on a time delta from now. This header tells browsers when the cached content should be considered stale.

**Parameters:**
- `delta`: Integer seconds (`int`) or `datetime.timedelta`. A float such as
  `1.5` raises `TypeError`; use `timedelta(seconds=1.5)` instead.

**Returns:** None (sets HTTP header)

**Example:**
```python
import datetime
from email.utils import parsedate_to_datetime
import web

class Page:
    def GET(self):
        web.expires(datetime.timedelta(seconds=1.5))
        return "cacheable"

app = web.application(("/", Page), globals(), autoreload=False)
before = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=1.5)
response = app.request("/")
after = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=1.5)
assert response.status == "200 OK" and response.data == b"cacheable"
expires_at = parsedate_to_datetime(response.headers["Expires"])
# The UTC header has whole-second precision, not fractional seconds.
assert before.replace(microsecond=0) <= expires_at <= after.replace(microsecond=0)
```

Expiration is computed from the current UTC clock. Header formatting drops
microseconds; fractional timedeltas are accepted but are not transmitted with
fractional precision. This only sets `Expires`, not a complete cache policy.

### `lastmodified(date_obj)`
Sets an HTTP `Last-Modified` header. This header indicates when the resource was last changed, enabling conditional requests.

**Parameters:**
- `date_obj`: A datetime representing the last modification time in UTC.
  Formatting labels its clock fields `GMT` without converting timezones and
  drops microseconds. Convert aware non-UTC values to UTC first. Use UTC naive
  datetimes with `modified`, which compares against a parsed naive datetime.

**Returns:** None (sets HTTP header)

**Example:**
```python
import datetime
import web

class Page:
    def GET(self):
        web.lastmodified(datetime.datetime(2023, 1, 1, 12, 0, 0, 500000))
        return "document"

app = web.application(("/", Page), globals(), autoreload=False)
response = app.request("/")
assert response.status == "200 OK" and response.data == b"document"
assert response.headers["Last-Modified"] == "Sun, 01 Jan 2023 12:00:00 GMT"
```

### `modified(date=None, etag=None)`
Checks request validators against a supplied UTC naive `datetime` and/or an
unquoted, nonempty ETag string. Returns `True` when **no supplied validator
proves the resource unchanged**, including absent or nonmatching request
headers. Generate the normal response after that return; it does not prove
that the resource changed. A match raises `web.notmodified()` (304), so code
after the call does not run. Supplied truthy date/ETag values set response
`Last-Modified`/quoted `ETag` headers on both paths.

This implementation uses **OR semantics**: either matching validator produces
304 even if the other disagrees. It does not implement ETag-over-date precedence.
ETags are split on commas with surrounding spaces/quotes stripped; `*` matches
when an ETag was supplied. Weak `W/` tags are not normalized. Invalid dates are
ignored. Date matching uses `date - timedelta(seconds=1) <= parsed_request_date`,
with the request header suffix after `;` ignored. This accommodates subsecond
precision, but also accepts an exact one-second difference; it is not exact
datetime equality. These are existing helper semantics, not a complete HTTP
cache-policy implementation.

```python
import datetime
import web

generated = []
class Page:
    def GET(self):
        if web.modified(date=datetime.datetime(2023, 1, 1), etag="abc123"):
            generated.append(True)
            return "normal response"

app = web.application(("/", Page), globals(), autoreload=False)
response = app.request("/")
assert response.status == "200 OK" and response.data == b"normal response"
cached = app.request("/", headers={"If-None-Match": '"abc123"'})
assert cached.status == "304 Not Modified" and cached.data == b""
assert generated == [True]  # The cached request never generated a body.
assert cached.headers["ETag"] == '"abc123"'
assert cached.headers["Last-Modified"] == "Sun, 01 Jan 2023 00:00:00 GMT"
```

### `urlencode(query, doseq=False)`
Encodes a dictionary into a URL-encoded query string, supporting Unicode strings.

**Parameters:**
- `query`: Dictionary of query parameters
- `doseq`: If True, handles list values by creating multiple parameters (default: False)

**Returns:** URL-encoded string

**Example:**
```python
from web.http import urlencode  # Not exported by web.http.__all__.

assert urlencode({'text': 'foo bar'}) == 'text=foo+bar'
assert urlencode({'x': [1, 2]}, doseq=True) == 'x=1&x=2'
```

### `changequery(query=None, **kw)`
Creates a new URL with modified query parameters. This is useful for updating URLs while preserving existing parameters.

**Parameters:**
- `query`: Existing query parameters dictionary (defaults to current GET parameters from `web.rawinput()`)
- `**kw`: Keyword arguments specifying parameter changes. Set a parameter to `None` to remove it.

**Returns:** New URL string with updated parameters

**Example:**
```python
import web

class Page:
    def GET(self):
        assert web.changequery(a=3) == '/foo?a=3&b=2'
        assert web.changequery(a=None) == '/foo?b=2'
        return web.changequery(page=2, sort='name')

app = web.application(('/foo', Page), globals(), autoreload=False)
response = app.request('/foo?a=1&b=2')
assert response.status == '200 OK'
assert response.data == b'/foo?a=1&b=2&page=2&sort=name'
```

### `url(path=None, doseq=False, **kw)`
Builds a root/mount-relative URL, not an origin-qualified URL. For a path
starting with `/`, prepends `web.ctx.homepath` (normally `SCRIPT_NAME`, such as
`""` or `"/mount"`). A relative path is left relative. The default path is
`web.ctx.path`; current request query parameters are not automatically copied.
`doseq=True` expands list values into repeated parameters.

**Parameters:**
- `path`: Path to append (defaults to current path `web.ctx.path`)
- `doseq`: If True, handles list values in query parameters (default: False)
- `**kw`: Query parameters to append

**Returns:** URL path with optional encoded query string.

For an absolute URL from an absolute path, concatenate
`web.ctx.homedomain + web.url('/path')`. `homedomain` comes from request
scheme/host; this is not Host validation or a trusted-origin guarantee. Use
an application-configured trusted origin when that is required.

**Example:**
```python
import web

class Page:
    def GET(self):
        mount = web.ctx.env['SCRIPT_NAME']
        assert web.ctx.homepath == mount
        assert web.ctx.homedomain == 'http://example.com'
        assert web.url('/api/users', limit=10) == mount + '/api/users?limit=10'
        assert web.url('relative', limit=10) == 'relative?limit=10'
        assert web.url(doseq=True, tags=['python', 'web']) == mount + '/current?tags=python&tags=web'
        return web.ctx.homedomain + web.url('/api/users', limit=10)

app = web.application(('/current', Page), globals(), autoreload=False)
root = app.request('/current?old=1', host='example.com', env={'SCRIPT_NAME': ''})
mounted = app.request('/current?old=1', host='example.com', env={'SCRIPT_NAME': '/mount'})
assert root.status == mounted.status == '200 OK'
assert root.data == b'http://example.com/api/users?limit=10'
assert mounted.data == b'http://example.com/mount/api/users?limit=10'
```

### `profiler(app)`
Development-only helper for a bounded, small HTML response. Pass a **WSGI
callable**, not the non-callable `web.application` instance:
`app.wsgifunc(web.profiler)` or `web.profiler(app.wsgifunc())`.
The helper uses `web.utils.Profile` (cProfile), materializes the returned
iterable into a list, and appends an escaped UTF-8 bytes `<pre>` report. It
profiles the WSGI callable invocation, **not subsequent body iteration**.
Deferred generator work may therefore be absent from the timing/report (the
framework can consume a first chunk during invocation). This is not a streaming
profiler, end-to-end request timer, or production middleware.

**Conservative response policy:** a report is appended only for `GET` and an
accepted `200 OK` response with exactly one explicit `Content-Type: text/html`.
Media type and charset matching is case-insensitive, with space/tab whitespace
allowed around the value and parameter separators. The only optional parameter
is a single `charset=utf-8` (also accepted as `charset="utf-8"`). Missing media
type, other media/charsets, duplicate or unknown parameters, malformed values,
and ambiguous headers omit the report. HEAD, 1xx, 204, 205, 304 and every other
method/status therefore receive no added report.

Any `Content-Length` or `Content-Encoding` header, even empty or `identity`,
bypasses insertion. So do `Content-Range`, `ETag`, `Last-Modified`, `Content-MD5`,
`Digest`, `Content-Digest`, `Repr-Digest`, any `Content-Disposition` (including
inline), and requests containing `Range` or `If-Range`. Request and response
`Cache-Control: no-transform` are respected. Cache-Control accepts only a
comma-separated list of distinct token directives with optional token values;
quoted, malformed or duplicate directives conservatively omit the report.
Duplicate response header names, invalid names and control characters other
than horizontal tab in values also omit it. None of these cases rewrites
headers or recalculates a length.

**Remaining caller constraints:** this limited policy cannot identify arbitrary
custom body-dependent headers/signatures. Callers must still supply a valid
WSGI response, UTF-8-compatible HTML bytes (also when charset is omitted), no
other metadata invalidated by appending, and small bounded bodies. Bypass
preserves original status, headers and body chunks; it does not repair a bad
underlying body/HTTP response and still eagerly materializes the iterable.
It does not make unbounded streams safe. Keep profiler output away from
production clients: it exposes internal function/file names and adds overhead.

The response callback delegates the application's original arguments unchanged,
including optional `exc_info`, and returns the exact server write callable.
Report eligibility is captured from the offered metadata **before** delegation,
when the server may consume or mutate the original header list. That immutable
decision takes effect only after successful delegation, including a replacement
response with `exc_info` and lazy callbacks during iteration. A
failed callback clears the previous eligibility and its exception propagates;
there is no report without a successful response callback. Calls to `write()`
remain immediate; returned iterable chunks and any report follow them under the
existing eager behavior, not a new streaming implementation.

After acquiring the original WSGI iterable, the helper materializes it in a
`try/finally` and calls its callable `close()` exactly once, if present. This
happens on successful exhaustion or iteration failure (including `BaseException`),
before constructing the HTML report or returning the list. It closes the
original iterable, not a distinct iterator returned by `iter()`. No callable
`close()` is required. Cleanup is not deferred until a consumer exhausts or
closes the returned list; the list itself has no `close()` method.

Iteration failures propagate after cleanup. A `close()` failure propagates
instead of returning a response; if iteration also failed, normal Python
`finally` precedence applies: the close exception wins and the iteration
exception remains its `__context__`. Failures in the application/profiling call
before the iterable is acquired are outside this cleanup boundary. Iteration
and close are still outside the profiled callable invocation.

The example exercises the supported development GET/200 HTML case, using an
in-process WSGI validator, not a server. Automatic report omission does not
remove the remaining caller constraints above.

```python
import io
from wsgiref.util import setup_testing_defaults
from wsgiref.validate import validator
import web

class Page:
    def GET(self):
        web.header("Content-Type", "text/html; charset=utf-8")
        return "<h1>Development page</h1>"

app = web.application(("/", Page), globals(), autoreload=False)
wsgi = app.wsgifunc(web.profiler)
env = {}
setup_testing_defaults(env)
env.update(REQUEST_METHOD="GET", PATH_INFO="/", QUERY_STRING="",
           HTTP_HOST="example.test", **{"wsgi.input": io.BytesIO()})
captured = []
def start_response(status, headers, exc_info=None):
    captured.append((status, headers))

body = validator(wsgi)(env, start_response)
try:
    chunks = list(body)
finally:
    body.close()
assert captured == [("200 OK", [("Content-Type", "text/html; charset=utf-8")])]
assert all(isinstance(chunk, bytes) for chunk in chunks)
response = b"".join(chunks)
assert response.startswith(b"<h1>Development page</h1>")
assert b"<pre>" in response and b"function calls" in response
assert response.endswith(b"</pre>")
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
- `web.utils` for utility functions (`safestr`, `profile`)
- `web.webapi` for web context access (`ctx`, `header`, `notmodified`, `rawinput`)
- `web.py3helpers` for Python 3 compatibility (`iteritems`)

## Usage Examples

### Setting Cache Headers
```python
import datetime
from email.utils import parsedate_to_datetime
import web

class Page:
    def GET(self):
        web.expires(3600)
        web.lastmodified(datetime.datetime(2023, 1, 1))
        return "article"

app = web.application(("/", Page), globals(), autoreload=False)
before = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=1)
response = app.request("/")
after = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=1)
assert response.status == "200 OK" and response.data == b"article"
assert response.headers["Last-Modified"] == "Sun, 01 Jan 2023 00:00:00 GMT"
assert before.replace(microsecond=0) <= parsedate_to_datetime(response.headers["Expires"]) <= after.replace(microsecond=0)
```

### Handling Conditional Requests
```python
import datetime
import web

class Article:
    def GET(self):
        # Substitute your stored update time/version in an application.
        web.modified(date=datetime.datetime(2023, 1, 1, 0, 0, 0, 500000),
                     etag="article-1-v2")
        return "article body"  # Only reached when no validator matched.

app = web.application(("/article", Article), globals(), autoreload=False)
normal = app.request("/article", headers={"If-None-Match": '"old"'})
assert normal.status == "200 OK" and normal.data == b"article body"
# Date matches with subsecond grace, despite the nonmatching ETag (OR).
cached = app.request("/article", headers={
    "If-None-Match": '"old"',
    "If-Modified-Since": "Sun, 01 Jan 2023 00:00:00 GMT",
})
assert cached.status == "304 Not Modified" and cached.data == b""
```

### URL Manipulation
```python
import web

class Page:
    def GET(self):
        assert web.changequery(page=2) == '/users?filter=active&page=2'
        # url adds SCRIPT_NAME; changequery uses ctx.path without the mount.
        assert web.url('/api/users', limit=10) == '/mount/api/users?limit=10'
        return web.url(page=2)  # Builds a new query, not the old filter.

app = web.application(('/users', Page), globals(), autoreload=False)
response = app.request('/users?filter=active', host='example.com', env={'SCRIPT_NAME': '/mount'})
assert response.status == '200 OK'
assert response.data == b'/mount/users?page=2'
```

### URL Encoding
```python
from web.http import urlencode

assert urlencode({'search': 'hello world'}) == 'search=hello+world'
assert urlencode({'tags': ['python', 'web']}, doseq=True) == 'tags=python&tags=web'
```
