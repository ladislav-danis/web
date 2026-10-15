# Web API Documentation

This document describes the web API utilities in `web/webapi.py`, which provide a WSGI wrapper and various helper functions for handling HTTP requests and responses in web.py applications.

## Overview

The webapi module serves as the core interface between WSGI applications and HTTP request/response handling. It provides utilities for managing HTTP status codes, headers, cookies, input data, and error handling while maintaining compatibility with the WSGI specification.

## Classes

### `HTTPError`

Base exception class for HTTP errors. All HTTP error classes inherit from this class.

#### Constructor

```python
def __init__(self, status, headers={}, data="")
```

**Parameters:**
- `status` (str): HTTP status code and message (e.g., "404 Not Found")
- `headers` (dict): HTTP headers to include in response
- `data` (str): Error message/data to return in response body

**Example:**
```python
raise web.HTTPError("403 Forbidden", {"Content-Type": "text/html"}, "Access denied")
```

### Status Code Classes

Only the 2xx exception classes below are generated dynamically. Their lowercase
names are aliases to the same classes. Redirection classes and the other public
4xx exception classes are defined explicitly.

`NotFound` / `notfound`, `InternalError` / `internalerror`, and
`UnavailableForLegalReasons` / `unavailableforlegalreasons` are **factory functions**,
not exception types. With no truthy message they consult the active application's
corresponding hook (or use the default if there is no active application); an
explicit nonempty message constructs the corresponding default HTTPError.
Do not use these factories in an `except` clause: use `except web.HTTPError`
(or a real exception class such as `web.BadRequest`). The tables list public
callables, not exclusively classes.

Constructing an `HTTPError` immediately sets `ctx.status` and adds its headers;
it does not raise itself. `raise` makes the WSGI response use its `.data`.
Returning the exception object instead stringifies its status: `return
web.created(data="payload")` sets 201 but sends `b"201 Created"`, not the payload.
For ordinary responses set `web.ctx.status` and return the body explicitly.

#### Success Status Codes (2xx)

| Class | Status Code | Description |
|-------|-------------|-------------|
| `OK` / `ok` | 200 | Standard successful response |
| `Created` / `created` | 201 | Request successful, resource created |
| `Accepted` / `accepted` | 202 | Request accepted for processing |
| `NoContent` / `nocontent` | 204 | Successful response with no content |

**Example:**
```python
import web

web.config.debug = False

class SuccessExample:
    def GET(self):
        if web.ctx.path == "/ok":
            raise web.ok()  # 200 with an empty body
        raise web.created(data="Created payload", headers={"X-Result": "created"})

app = web.application(("/.*", SuccessExample), {}, autoreload=False)
response = app.request("/")
assert (response.status, response.data) == ("201 Created", b"Created payload")
```

#### Redirection Status Codes (3xx)

| Class | Status Code | Description |
|-------|-------------|-------------|
| `Redirect` / `redirect` | 301 | Moved permanently |
| `Found` / `found` | 302 | Found (temporary redirect) |
| `SeeOther` / `seeother` | 303 | See other (redirect to different URI) |
| `NotModified` / `notmodified` | 304 | Not modified (cache validation) |
| `TempRedirect` / `tempredirect` | 307 | Temporary redirect |

**Example:**
```python
# Redirect to a new URL (relative to current path)
raise web.redirect("about")

# Redirect to absolute URL
raise web.found("https://example.com/new-page", absolute=True)

# Redirect with 303 See Other (typically after POST)
raise web.seeother("/result")
```

#### Client Error Status Codes (4xx)

| Class | Status Code | Description |
|-------|-------------|-------------|
| `BadRequest` / `badrequest` | 400 | Malformed request syntax |
| `Unauthorized` / `unauthorized` | 401 | Authentication required |
| `Forbidden` / `forbidden` | 403 | Access denied |
| `NotFound` / `notfound` | 404 | Resource not found |
| `NoMethod` / `nomethod` | 405 | Method not allowed |
| `NotAcceptable` / `notacceptable` | 406 | Not acceptable |
| `Conflict` / `conflict` | 409 | Conflict with current state |
| `Gone` / `gone` | 410 | Resource no longer available |
| `PreconditionFailed` / `preconditionfailed` | 412 | Precondition failed |
| `UnsupportedMediaType` / `unsupportedmediatype` | 415 | Unsupported media type |
| `UnavailableForLegalReasons` / `unavailableforlegalreasons` | 451 | Unavailable for legal reasons |

**Example:**
```python
raise web.notfound("Page not found")
raise web.forbidden("Access denied")
raise web.badrequest("Invalid input data")
```

#### Server Error Status Codes (5xx)

| Class | Status Code | Description |
|-------|-------------|-------------|
| `InternalError` / `internalerror` | 500 | Internal server error |

**Example:**
```python
raise web.internalerror("An unexpected error occurred")
```

## Functions

### `header(hdr, value, unique=False)`

Adds an HTTP header to the response. This helper rejects CR and LF in both name
and value. Prefer it to direct `ctx.headers` mutations: the framework does not
revalidate that list when calling WSGI `start_response`. Any additional validation
by a particular server or middleware is outside this helper's guarantee.

**Parameters:**
- `hdr` (str): Header name (e.g., "Content-Type", "X-Custom-Header")
- `value` (str): Header value
- `unique` (bool): If True, don't add header if one with the same name already exists

**Raises:**
- `ValueError`: If header name or value contains invalid characters (newline or carriage return)

**Example:**
```python
import web

web.config.debug = False

class HeaderExample:
    def GET(self):
        web.header("Content-Type", "application/json")
        web.header("X-Request-ID", "example-id", unique=True)
        web.header("x-request-id", "not-a-replacement", unique=True)
        return '{"ok": true}'

app = web.application(("/", HeaderExample), {}, autoreload=False)
response = app.request("/")
assert response.headers["X-Request-ID"] == "example-id"
```

### `rawinput(method=None)`

Returns a `storage` object with parsed GET or POST arguments, before `input()`
selects scalar/list values and applies defaults. For URL-encoded text, values are
lists of strings (including empty strings); combined mode gives the body precedence.
This is parsing, not validation. Import `rawinput` from `web.webapi`: it is not in
that module's `__all__` or the package's star exports, and `web.rawinput` is absent.

**Parameters:**
- `method` (str): Request method to parse. Options:
  - `"both"` (default): Parse both GET and POST
  - `"get"`: Parse only GET/query parameters
  - `"post"`, `"put"`, `"patch"`: Parse POST/PUT/PATCH body

**Returns:**
- `storage`: Storage object containing request parameters

**Example:**
```python
import json
import web
from web.webapi import rawinput

web.config.debug = False

class RawInputExample:
    def GET(self):
        return json.dumps({"both": dict(rawinput()),
                           "post": dict(rawinput("post")),
                           "get": dict(rawinput("get"))})

    POST = GET

app = web.application(("/", RawInputExample), {}, autoreload=False)
response = app.request("/?name=Z%C3%A9Z&tag=a&tag=b")
assert response.status == "200 OK"
assert json.loads(response.data)["get"] == {"name": ["ZéZ"], "tag": ["a", "b"]}
```

### `input(*requireds, **defaults)`

Parses request parameters and returns a `storage` object. Positional names check
**presence**, not nonempty values, types, authorization, or injection safety.
For URL-encoded GET/POST data, supplied values remain strings; a default such as
`page=1` does not convert a supplied `page` to an integer. Repeated parameters use
the last value unless a list default (for example `tags=[]`) requests all values.
The default combined mode lets body parameters override same-named query parameters.

**Parameters:**
- `*requireds` (str): Required parameter names. Raises `BadRequest` if absent from the parsed request, even if that name also has a default. Present empty strings pass.
- `**defaults`: Default values for optional parameters
  - `_method` (str): Request method ("both", "get", "post", "put", "patch")
  - `_unicode` (bool): Convert values to unicode (default: True)
  - Other keys: Default values for parameters

**Returns:**
- `storage`: Storage object with request parameters

**Raises:**
- `BadRequest`: If required parameters are missing

`required=["username", "password"]` is an ordinary default named `required`,
not a validation option. Use positional names instead. Let `BadRequest` propagate
so the application sends HTTP 400; catching it and continuing does not enforce a
rejection. Use `_method="get"` or `_method="post"` when only one source is intended.

**Example (standalone, offline presence check; not authentication):**
```python
import json
import web

web.config.debug = False

class InputExample:
    def GET(self):
        values = web.input("username", "password", name="Anonymous", page=1)
        web.header("Content-Type", "application/json")
        # Do not return the password. Empty values still satisfy presence.
        return json.dumps({"username": values.username,
                           "name": values.name, "page": values.page})

    POST = GET

app = web.application(("/", InputExample), {}, autoreload=False)
assert app.request("/").status == "400 Bad Request"
assert app.request("/?username=Alice&password=example").status == "200 OK"
assert app.request("/?username=&password=").status == "200 OK"
```

### `data()`

Returns the raw data sent with the HTTP request body.

**Returns:**
- `bytes`: Raw request body data

**Example:**
```python
# Get raw JSON data
json_data = web.data().decode("utf-8")

# Parse JSON
import json
data = json.loads(web.data())
```

### `setcookie(name, value, expires="", domain=None, secure=False, httponly=False, path=None, samesite=None)`

Sets an HTTP cookie in the response.

**Parameters:**
- `name` (str): Cookie name
- `value` (str): Cookie value
- `expires` (str/int): Expiration date (string) or relative **seconds** (integer), not days. Empty string omits Expires; a negative integer requests a date far in the past for deletion.
- `domain` (str): Optional Domain attribute. Omitted by default (a host-only cookie).
- `secure` (bool): If True, emit Secure; defaults to False
- `httponly` (bool): If True, emit HttpOnly; defaults to False
- `path` (str): Cookie path. Defaults to `ctx.homepath + "/"` (root: `/`). Use the same path/domain when deleting.
- `samesite` (str): Optional SameSite attribute: "strict", "lax", "none" (case-insensitive selection). Other values are omitted.

These are header attributes, not authentication or a complete CSRF policy.
Browsers enforce cookie policy; this example only demonstrates emitted headers.

**Example (standalone, offline):**
```python
import web

web.config.debug = False

class SetCookieExample:
    def GET(self):
        web.setcookie("session_id", "abc123")
        web.setcookie("user_prefs", "dark_mode", expires=3600)
        web.setcookie("auth_token", "example-token", secure=True, httponly=True)
        web.setcookie("csrf_token", "xyz789", samesite="strict")
        web.setcookie("session_id", "", expires=-1)
        return "Cookies set"

app = web.application(("/", SetCookieExample), {}, autoreload=False)
assert app.request("/").status == "200 OK"
```

### `parse_cookies(http_cookie)`

Parses an `HTTP_COOKIE` header into decoded Python 3 strings, not UTF-8 byte
spellings. Import `parse_cookies` from `web.webapi`; it is absent from that
module's `__all__`, star exports and `web.parse_cookies`.

In quoted cookie syntax a raw `\n` unescapes to `n`, whereas octal `\012`
decodes to a newline. That does **not** guarantee acceptance: the verified
Python 3.13.5 stdlib rejects decoded control characters, and this framework's
fallback returns `{}` for the isolated newline-bearing example below. Older
stdlibs may accept the decoded newline. Do not use control characters in cookie
values or treat parsing as authenticity/session validation.

**Parameters:**
- `http_cookie` (str): Raw HTTP_COOKIE header value

**Returns:**
- `dict`: Dictionary of cookie names and decoded values

**Examples:**
```python
from http.cookies import SimpleCookie
from web.webapi import parse_cookies

assert parse_cookies('a=1') == {'a': '1'}
assert parse_cookies('a=1; b=2') == {'a': '1', 'b': '2'}
assert parse_cookies('a=1%202') == {'a': '1 2'}
assert parse_cookies('a=Z%C3%A9Z') == {'a': 'ZéZ'}
assert parse_cookies(r'keebler="E=mc2; L=\"Loves\"; fudge=\n;"') == {
    'keebler': 'E=mc2; L="Loves"; fudge=n;'}

# Decode syntax separately from the stdlib's cookie-acceptance policy.
assert SimpleCookie().value_decode(r'"\012"')[0] == '\n'
# In the verified interpreter this control-bearing cookie is rejected.
assert parse_cookies(r'keebler="E=mc2; L=\"Loves\"; fudge=\012;"') == {}
```

### `cookies(*requireds, **defaults)`

Returns a `storage` object with request cookies and optional defaults. As with
`input()`, `required=[...]` only supplies a default named `required`; it does not
require the listed cookie names. Parsed cookie values are untrusted input, not
proof of authentication.

**Parameters:**
- `*requireds` (str): Required cookie names. Raises `BadRequest` when absent, even if that name also has a default. Present empty values satisfy this presence check.
- `**defaults`: Default values for optional cookies
  - `_unicode` (bool): Unicode conversion option (default: False, unlike `input()`)
  - Other keys: Default values for cookies

**Returns:**
- `storage`: Storage object with cookie data

**Missing required cookies (reference scope WB-WEBAPI-03):**
A missing positional name raises `BadRequest` before defaults are applied.
Let it propagate: the default application returns HTTP 400 with body `bad request`
from an ordinary handler or a returned generator before its first chunk and
`start_response`. After the response has started, or if application code catches
and overrides the error, this does not guarantee replacement of the HTTP status.
Presence checks do not require nonempty values or authenticate a cookie.

**Example (standalone, explicit application-level check):**
This example reads without required names and checks membership explicitly to
provide its own error message. The separate nonempty check is an application
policy beyond positional presence checking; neither is session verification or
authentication.

```python
import web

web.config.debug = False

class CookieExample:
    def GET(self):
        values = web.cookies()
        required = ("session_id", "user_id")
        if any(name not in values for name in required):
            raise web.badrequest("Missing cookie fields")
        if any(not values[name] for name in required):
            raise web.badrequest("Cookie fields must be nonempty")
        web.header("Content-Type", "text/plain; charset=utf-8")
        return "Cookie fields present"

app = web.application(("/", CookieExample), {}, autoreload=False)
assert app.request("/").status == "400 Bad Request"
assert app.request("/", headers={"Cookie": "session_id=; user_id=7"}).status == "400 Bad Request"
response = app.request("/", headers={"Cookie": "session_id=example; user_id=7"})
assert response.status == "200 OK"
assert response.data == b"Cookie fields present"
```

### `debug(*args)`

Prints pretty-printed arguments to stderr for debugging purposes.

**Parameters:**
- `*args`: Arguments to print

**Returns:**
- `str`: Empty string (for use in templates where output is expected)

**Example:**
```python
# Debug request data
web.debug(web.input())
web.debug(web.ctx)

# Debug complex objects
web.debug({"key": "value", "nested": {"data": [1, 2, 3]}})
```

### `ctx`

Thread-local, dict-like `ThreadedDict` containing request and response information,
with attribute access. WSGI request cleanup clears it; do not retain it as shared
application state. URL fields derive from request metadata, not a trusted-origin
or Host-validation policy.

#### Request Information

| Attribute | Type | Description |
|-----------|------|-------------|
| `environ` (or `env`) | dict | WSGI environment variables |
| `host` | str | Host header from request |
| `home` | str | Base URL: scheme + host + homepath; adjusted inside sub-applications |
| `realhome` | str | Original base URL before sub-application mounting |
| `ip` | str | Client IP address |
| `method` | str | HTTP method used |
| `path` | str | Request path |
| `query` | str | Query string with '?' prefix |
| `fullpath` | str | Full request path including query |
| `homepath` | str | Mount path from SCRIPT_NAME (or REAL_SCRIPT_NAME override), extended inside sub-applications; no scheme/host |

#### Response Information

| Attribute | Type | Description |
|-----------|------|-------------|
| `status` | str | HTTP status code (default: "200 OK") |
| `headers` | list | List of 2-tuples for response headers |
| `output` | str | Legacy field initialized to `""`; not the WSGI response body source |
| `data` | bytes | Raw request body data |
| `_fieldstorage` | dict | Parsed form data (internal use) |
| `_parsed_cookies` | dict | Parsed cookies (internal use) |

WSGI sends the handler result (or `.data` from a raised `HTTPError`), not
`ctx.output`. Use `web.header()` instead of directly mutating `ctx.headers`.

**Example (standalone, in-process WSGI; no listener):**
```python
import io
import json
from wsgiref.util import setup_testing_defaults
import web

web.config.debug = False

class ContextExample:
    def GET(self):
        values = {name: getattr(web.ctx, name) for name in
                  ("home", "homepath", "realhome", "path", "query", "method")}
        values["initial_output"] = web.ctx.output
        web.ctx.output = "legacy-not-the-body"
        web.header("X-Custom-Header", "value")
        web.ctx.status = "202 Accepted"
        return json.dumps(values)

app = web.application(("/resource", ContextExample), {}, autoreload=False)

def environment(mount):
    env = {}
    setup_testing_defaults(env)
    env.update(SCRIPT_NAME=mount, PATH_INFO="/resource", QUERY_STRING="x=1",
               HTTP_HOST="example.test:8443", REQUEST_METHOD="GET")
    env["wsgi.url_scheme"] = "https"
    env["wsgi.input"] = io.BytesIO(b"")
    return env

def request(mount):
    captured = []
    body = b"".join(app.wsgifunc()(environment(mount),
                   lambda status, headers: captured.append((status, list(headers)))))
    status, headers = captured[0]
    return status, headers, body

status, headers, body = request("/mounted")
assert status == "202 Accepted"
assert json.loads(body)["home"] == "https://example.test:8443/mounted"
assert json.loads(body)["homepath"] == "/mounted"
assert b"legacy-not-the-body" not in body
```

## Configuration

The module uses a global `config` object for various settings:

| Attribute | Type | Description |
|-----------|------|-------------|
| `debug` | bool | When True, enables reloading, disables template caching, and sets internalerror to debugerror |

**Example:**
```python
web.config.debug = True  # Enables debugging features
```

## Usage Examples

### Basic Error Handling

```python
import web

web.config.debug = False
observations = []

class ErrorExample:
    def GET(self):
        if web.ctx.path == "/missing":
            raise web.notfound("Page not found")
        if web.ctx.path == "/payload":
            web.ctx.status = "201 Created"
            return "Payload"
        error = web.created(data="Payload")
        observations.append((error.args, error.data, web.ctx.status))
        if web.ctx.path == "/raised":
            raise error
        if web.ctx.path == "/returned":
            return error  # Characterization, not the recommended payload pattern
        return "Continued"  # Construction alone does not interrupt the handler

app = web.application(("/.*", ErrorExample), {}, autoreload=False)
assert app.request("/raised").data == b"Payload"
response = app.request("/returned")
assert (response.status, response.data) == ("201 Created", b"201 Created")
assert app.request("/payload").data == b"Payload"
assert app.request("/constructed").data == b"Continued"
```

### Handling Input Data

Presence and application validation are separate steps. This standalone example
requires both keys, rejects a blank username and an empty password, converts page
to an integer, and applies an example range of 1–100. These are explicit application
policies, not `input()` defaults. The username is checked with `strip()` but kept
unchanged; passwords are not stripped (a whitespace-only password is nonempty).
This is a parsing/validation demonstration for URL-encoded text GET/POST, not an
authentication endpoint or an upload validator. Multipart values require a separate
application type/error policy; the required-upload double-read source defect is
tracked in [web#37](https://git.home.arpa/mosaic-ai/web/issues/37).

```python
import json
import web

web.config.debug = False

class ValidatedInput:
    def GET(self):
        values = web.input("username", "password", page="1")
        if not values.username.strip() or not values.password:
            raise web.badrequest("Username must be nonblank and password nonempty")
        try:
            page = int(values.page)
        except ValueError:
            raise web.badrequest("Page must be an integer")
        if not 1 <= page <= 100:
            raise web.badrequest("Page must be between 1 and 100")
        web.header("Content-Type", "application/json")
        return json.dumps({"username": values.username, "page": page})

    POST = GET

app = web.application(("/", ValidatedInput), {}, autoreload=False)
assert app.request("/").status == "400 Bad Request"
assert app.request("/?username=&password=example").status == "400 Bad Request"
assert app.request("/?username=Alice&password=example&page=oops").status == "400 Bad Request"
response = app.request("/", method="POST",
                       data="username=Alice&password=example&page=2",
                       headers={"Content-Type": "application/x-www-form-urlencoded"})
assert response.status == "200 OK"
assert json.loads(response.data) == {"username": "Alice", "page": 2}
```

### Setting Cookies

```python
# Set a simple cookie
web.setcookie("session_id", "abc123")

# Set secure cookie with expiration
web.setcookie("user_prefs", "dark_mode", expires=3600, secure=True)

# Set SameSite cookie
web.setcookie("csrf_token", "xyz789", samesite="strict")

# Delete a cookie
web.setcookie("session_id", "", expires=-1)
```

### Custom Error Pages

Application hooks must return an `HTTPError`, not a string: the framework raises the returned object. Register callbacks on the application instance. Do not call the no-argument `web.notfound()` or `web.internalerror()` dispatchers from their own hooks, which would recurse.

```python
import web

web.config.debug = False
app = web.application((), globals())  # Add your routes here.

def notfound():
    return web.HTTPError(
        "404 Not Found",
        {"Content-Type": "text/html; charset=utf-8"},
        "<h1>404 - Page Not Found</h1>",
    )

def internalerror():
    return web.HTTPError(
        "500 Internal Server Error",
        {"Content-Type": "text/html; charset=utf-8"},
        "<h1>500 - Internal Server Error</h1>",
    )

# Configure application to use custom error handlers
app.notfound = notfound
app.internalerror = internalerror
```

### Redirects

```python
# Redirect to a relative path
raise web.redirect("about")

# Redirect to absolute URL
raise web.found("https://example.com/new-page", absolute=True)

# Redirect with 303 See Other (typically after POST)
raise web.seeother("/result")

# Temporary redirect
raise web.tempredirect("/temp-page")
```

### Custom Headers

```python
# Set custom header
web.header("X-Request-ID", request_id)

# Set Content-Type
web.header("Content-Type", "application/json")

# Prevent caching
web.header("Cache-Control", "no-cache, no-store, must-revalidate")
web.header("Pragma", "no-cache")
web.header("Expires", "0")
```

## Security Considerations

The webapi module includes several security features:

- **Header Validation**: `header()` rejects CR/LF in names and values. Direct `ctx.headers` mutations bypass this check; the framework does not revalidate them at WSGI handoff. Use the helper. Server-specific validation is not established here; this is not evidence of a deployed exploit.
- **Cookie Encoding**: Cookie values are properly encoded and escaped
- **Input Processing**: Parsing and presence checks are not injection protection; apply application validation, SQL parameter binding, and output-context escaping separately (see below).
- **SameSite Support**: Cookie SameSite attribute helps prevent CSRF attacks
- **HttpOnly Support**: Cookies can be marked as HttpOnly to prevent JavaScript access

### Parsing is not injection protection

`input()` parses and storifies values; it leaves apostrophes and HTML metacharacters
in supplied strings. Presence checks do not enforce nonempty values, numeric types,
domain constraints, or authentication. Validate those rules explicitly, as in
[Handling Input Data](#handling-input-data).

Use SQL **parameter binding** for values, not string interpolation or concatenation
into SQL. Bind parameters do not stand for table/column names or arbitrary SQL
clauses; keep those fixed or choose from an application-owned allowlist. Bind the
original value, not an HTML-escaped version of it.

Escape at the output boundary for **HTML text** and ordinary **quoted attributes**.
The example uses `html.escape(..., quote=True)` for text and a quoted `title` value.
This is not JavaScript or CSS escaping, nor URL-scheme validation; HTML escaping
alone cannot make arbitrary `href`/`src` URLs or event-handler attributes safe.
Use context-specific encoding and URL policies for those separate contexts.

This demonstration accepts URL-encoded text, not multipart uploads; see the
separate upload limitation and type policy above. This standalone offline example
creates a fresh, owned in-memory SQLite
fixture per request and closes it afterward. It is not a production persistence
pattern or a login implementation. The SQL and identifiers are fixed; even an
apostrophe-bearing comparison-looking value is matched only as literal data.

```python
from contextlib import closing
from html import escape
import sqlite3
from urllib.parse import urlencode
import web

web.config.debug = False

class SafeOutput:
    def GET(self):
        values = web.input("name")
        with closing(sqlite3.connect(":memory:")) as db:
            db.execute("CREATE TABLE names (name TEXT NOT NULL)")
            db.executemany("INSERT INTO names (name) VALUES (?)",
                           [("Alice",), ("O'Reilly <b>&\"",)])
            count = db.execute("SELECT COUNT(*) FROM names WHERE name = ?",
                               (values.name,)).fetchone()[0]
        escaped = escape(values.name, quote=True)
        web.header("Content-Type", "text/html; charset=utf-8")
        return ('<p title="' + escaped + '">' + escaped
                + '</p><p>Matches: ' + str(count) + '</p>')

    POST = GET

app = web.application(("/", SafeOutput), {}, autoreload=False)
response = app.request("/?" + urlencode({"name": "O'Reilly <b>&\""}))
assert response.status == "200 OK"
assert response.data == (b'<p title="O&#x27;Reilly &lt;b&gt;&amp;&quot;">'
                         b'O&#x27;Reilly &lt;b&gt;&amp;&quot;</p><p>Matches: 1</p>')
```

## See Also

- [`web.http`](http.md) - HTTP utilities
- [`web.wsgi`](wsgi.md) - WSGI interface
- [`web.utils`](utils.md) - Utility functions
