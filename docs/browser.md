# Web Browser Documentation

This document describes the browser testing helpers in [`browser.py`](../browser.py).

## Overview

`Browser` is an HTTP client built on `urllib.request`; `AppBrowser` uses the same interface to call a web.py application in-process through `AppHandler`. Neither executes JavaScript or renders a desktop browser. GET navigation, response bytes and cookies work without optional HTML/form parsers.

## Pinned Python 3 Limitations

The original audit at source revision `a540a4bd0ce90ad3cd8c2c91c9fbfd332eabb7ed` is tracked in [web#3](https://git.home.arpa/mosaic-ai/web/issues/3). [web#21](https://git.home.arpa/mosaic-ai/web/issues/21) repairs the A-006 application bytes bridge and Unicode byte length. The other limitations below remain unchanged; this repair does not resolve A-008 or A-009.

- **A-006 — repaired bytes bridge, retained str boundary:** `AppBrowser.open(..., data=bytes)` now dispatches the real handler and preserves raw bytes, including non-UTF-8/NUL. `Browser.open(..., data=str)` and `AppBrowser.open(..., data=str)` still fail in urllib with `TypeError: POST data should be bytes, an iterable of bytes, or a file object. It cannot be of type str.` Encode text as UTF-8 or URL-encoded forms as ASCII bytes before calling these clients. Direct `app.request` also accepts `str` and `dict`; see [the executable direct POST example](application.md#direct-post-workaround). The AppBrowser guarantee here covers bytes, not arbitrary iterables/file objects or legacy ClientForm compatibility.
- **A-008 — callable link predicates:** `_filter_links` calls `predicate.append(predicate)` instead of appending to its list. A truthy callable such as a lambda raises `AttributeError: 'function' object has no attribute 'append'`, even for an empty input list. The same defect affects `get_links`, `find_link` and `follow_link` with `predicate=`. Use bounded text/URL criteria or filter returned links manually, as below. This is not a limitation of `select_form`'s separate predicate handling.
- **A-009 — `show()`:** responses are bytes, but `show()` opens `page.html` in text mode (`'w'`). It creates or truncates that file in the current working directory, then raises `TypeError: write() argument must be str, not bytes`, before reaching `webbrowser.open`. Avoid this helper; use an owned temporary directory and a binary write below. Do not call it in a directory containing a valuable `page.html`.
- **A-010 — `reset()`:** clears cookies only. It preserves `path`, `url`, `_response`, `data`, `status`, selected `form` and cached `_forms`. It does not clear navigation/response state or destroy server-side sessions. Create a new `Browser()` or `app.browser()` for fresh client state; server-side isolation is separate.

The two former A-006 bytes limitation assertions are replaced one-to-one by desired-success regressions. The two str/urllib boundary regressions retain their original identities. A-008/A-009 characterizations and cookie-only reset coverage remain; future source repairs must reconcile affected identities rather than silently remove assertions.

## Module Exports

- `BrowserError`: Exception class for browser operations.
- `Browser`: Network HTTP client.
- `AppBrowser`: In-process browser interface for web.py applications.
- `AppHandler`: urllib HTTP handler for web.py application requests.

## Classes

### `BrowserError`

Exception class raised for operations such as following a missing link or submitting without a selected form. It does not wrap every urllib, parser or type error.

### `Browser`

Construct with `Browser()`; it owns a cookie jar and starts at `http://0.0.0.0:8080/` with path `/`, no response and no selected form.

#### Properties

- `text`: `data` decoded as UTF-8; requires a response and suitable encoding.
- `url`, `path`: Current URL/path after the last request.
- `status`: Integer HTTP status of the last response.
- `data`: Raw response bytes.
- `form`: Currently selected form object, or `None`.

#### Method Table

| Method | Pinned behavior |
| --- | --- |
| `reset()` | Clears cookies only; preserves navigation, response and form state (A-010). |
| `build_opener()` | Builds a urllib opener; subclasses can override it. |
| `do_request(req)` | Performs a request, stores its response and returns a response copy. Uses the bytes body policy in A-006. |
| `open(url, data=None, headers={})` | Resolves a URL relative to the current URL. `data=None` means GET; bytes (including empty bytes) select POST. Strings are rejected by urllib; AppBrowser passes bytes unchanged (A-006). |
| `show()` | Broken for response bytes; creates/truncates `page.html` before raising TypeError, without launching a browser (A-009). |
| `get_response()` | Returns a file-like copy of the current response body/headers/URL. |
| `get_soup()` | Requires the optional legacy `BeautifulSoup` module. |
| `get_text(e=None)` | Extracts text with entities unquoted; without `e`, requires that same legacy parser. |
| `_get_links()` | Obtains anchor elements through `get_soup()`. |
| `get_links(text=None, text_regex=None, url=None, url_regex=None, predicate=None)` | Filters anchors by text/URL; callable `predicate` is broken (A-008). Requires the legacy parser. |
| `find_link(text=None, text_regex=None, url=None, url_regex=None, predicate=None)` | First matching anchor, or `None`; same parser and predicate limits. |
| `follow_link(link=None, text=None, text_regex=None, url=None, url_regex=None, predicate=None)` | Opens the selected anchor's href, or raises `BrowserError`; searching has the same parser and predicate limits. An explicit `link` avoids searching. |
| `_filter_links(links, text=None, text_regex=None, url=None, url_regex=None, predicate=None)` | Filters supplied anchor-like objects; callable `predicate` is broken, even for `[]` (A-008). |
| `get_forms()` | Requires optional legacy `ClientForm`; returns/caches parsed form objects. |
| `select_form(name=None, predicate=None, index=0)` | Selects a parsed form; requires ClientForm unless already cached. Its predicate is separate from the broken link predicate. |
| `submit(**kw)` | Calls selected form's `click(**kw)` then `do_request`; legacy ClientForm integration is not certified by the bytes bridge tests. |
| `__getitem__(key)`, `__setitem__(key, value)` | Read/write fields of the selected form; do not submit or change the body policy. |

### `AppBrowser`

Construct with `AppBrowser(app)` or `app.browser()`. It inherits `Browser` methods and limitations and overrides `build_opener()` to use `AppHandler`. Use it for GET navigation, cookies and POST bytes. Direct application requests additionally accept str/dict. The inherited ClientForm example in the source docstring still requires a compatible optional dependency; it is not certified here.

### `AppHandler`

Construct with `AppHandler(app)`. `handler_order = 100` prioritizes this handler. `https_request` aliases `HTTPHandler.do_request_`.

- `http_open(req)`: Delegates request path, method, host, bytes data and headers to `app.request` without decoding the body.
- `https_open(req)`: Delegates to `http_open` with HTTPS metadata; an AppBrowser request is still in-process, not a TLS connection.
- `_make_response(result, url)`: Converts the web.py response to a urllib response.

## Usage Examples

### Basic Usage

A complete GET example, without network access, JavaScript, BeautifulSoup or ClientForm:

```python
import web

class Page:
    def GET(self):
        return 'Hello, world!'
    def POST(self):
        return web.input().message

app = web.application(('/', Page), {}, autoreload=False)
b = app.browser()
b.open('/')
assert b.path == '/'
assert b.status == 200
assert b.data == b'Hello, world!'
assert b.text == 'Hello, world!'
```

### Working with Links

Requires a compatible **legacy `BeautifulSoup`** installation and an already loaded page containing flat anchors such as `<a href="/next">Next</a>`. This example is not applicable to the plain-text page above. `bs4` is not the imported module. Exact text compares `link.string` (not all descendant text); regex uses search, and multiple supplied criteria are ANDed. Keep URL matches bounded; a filter is not a URL safety policy.

```python
# No callable predicate= argument: it is broken on this pin.
links = b.get_links(text='Next', url_regex=r'^/next$')
link = b.find_link(url='/next')
# Apply custom predicates in user code to the returned anchors instead.
selected = [candidate for candidate in links if candidate.get('href') == '/next']
if selected:
    b.follow_link(link=selected[0])
```

Without the legacy dependency, use your own parser explicitly; `b.data` and `b.text` do not require it. A stdlib parser seam in the regression tests exercises the real filtering/navigation methods with flat anchors only; it is **limited integration**, not proof of compatibility with BeautifulSoup.

### Working with Forms

`get_forms()`/`select_form()` still require legacy `ClientForm`; the bytes repair does not certify that dependency. Without a form parser, construct URL-encoded fields explicitly. This fence continues the `app` and `b` namespace from Basic Usage: the direct str request remains supported, and the AppBrowser request sends Unicode form values as encoded bytes.

```python
from urllib.parse import urlencode

response = app.request('/', method='POST',
                       data=urlencode([('message', 'hello world')]),
                       headers={'Content-Type': 'application/x-www-form-urlencoded'})
assert response.status == '200 OK'
assert response.data == b'hello world'

form_body = urlencode([('message', 'ž 😀')]).encode('ascii')
assert form_body == b'message=%C5%BE+%F0%9F%98%80'
browser_response = b.open('/', data=form_body,
                          headers={'Content-Type': 'application/x-www-form-urlencoded'})
assert b.status == 200
assert browser_response.read() == b'\xc5\xbe \xf0\x9f\x98\x80'
assert b.data == b'\xc5\xbe \xf0\x9f\x98\x80'
```

Direct requests do not inherit `b.cookiejar`, automatically select successful HTML controls or supply application-specific CSRF tokens. For authenticated applications explicitly preserve the relevant cookies and tokens, and form field names. AppBrowser does carry its cookie jar, but neither approach discovers successful HTML controls or generates CSRF tokens for you. See the [standalone dict/string example](application.md#direct-post-workaround) and [raw body example](application.md#raw-request-bodies). Use `urlencode(pairs)` for repeated fields; dictionary lists are not expanded automatically.

### Cookie Management

```python
# Clears cookies only; all current page/response/form state remains.
b.reset()
# For fresh client state, create a new instance instead.
b = app.browser()
```

Neither operation resets application/database state or invalidates a server-side session.

### Saving a Response Without Launching a Browser

After a successful GET, write bytes into an owned temporary directory, not `page.html` in the working directory. This snippet never launches a desktop browser. The file is available inside the context; if you choose to inspect it manually, do so before the context ends. Treat untrusted HTML as active content. The directory/file are removed on exit.

```python
from pathlib import Path
from tempfile import TemporaryDirectory

with TemporaryDirectory(prefix='web-preview-') as directory:
    preview = Path(directory) / 'response.html'
    preview.write_bytes(b.data)
    saved_bytes = preview.read_bytes()
    assert saved_bytes == b.data
    preview_uri = preview.as_uri()  # Optional manual inspection, no automatic launch.
```

### Direct Browser Usage

`Browser()` is a network client, unlike `app.browser()`. Calling `browser.open(url)` will contact the supplied server. For POST its data must satisfy urllib's bytes-oriented contract; do not pass strings. AppBrowser accepts bytes through its in-process bridge; this is not a promise to support every other body type accepted by urllib. Use a controlled test server rather than a production URL.

## API Reference

The [method table](#method-table) is the canonical signature/behavior list; the following notes apply to all inherited methods as well.

- **Requests:** `open`/`do_request` store `url`, `path`, `data`, `status`, `_response`, clear cached `_forms` and set `form = None` on success. GET and bytes POST work in AppBrowser; strings still fail in urllib (A-006). `submit` goes through the same bridge and additionally depends on a compatible legacy form object.
- **Response inspection:** `get_response()` returns a new file-like body copy. `show()` is not a safe save/preview helper for bytes on this pin (A-009); use the binary temporary-file recipe.
- **Links:** `_get_links`/`get_links`/`find_link`/searching `follow_link` depend on legacy BeautifulSoup. Text/URL exact and regex filters work with suitable anchor objects. Callable `predicate=` is broken in all link-filter entry points (A-008). Use manual list filtering, then `follow_link(link=...)`; no match returns `[]`/`None` or raises `BrowserError` when following.
- **Forms:** `get_forms` parses with ClientForm and caches results. `select_form` filters by name/predicate and selects by index; field access delegates to that selected form. This API description is not certification of legacy ClientForm integration; the manually encoded bytes example above does not use that dependency.
- **Reset:** `reset()` only calls `cookiejar.clear()`. Path/URL, response/body/status and selected/cached forms remain (A-010). Start a new client for fresh client state.

## Constants

`DEBUG` is a boolean flag for request debug output (default `False`). There are no module-level public functions.

## Dependencies

HTML/form helpers have **optional, legacy dependencies**, imported lazily:

- [`BeautifulSoup`](https://www.crummy.com/software/BeautifulSoup/): the literal `import BeautifulSoup` in `get_soup()`, not `bs4`. Link helpers and default `get_text()` depend on its older API.
- [`ClientForm`](https://pythonhosted.org/ClientForm/): the literal `import ClientForm` in `get_forms()`, whose objects support form field access and `click()`.

They are not in Python's standard library and are not needed for basic GET, manually encoded AppBrowser POST, cookie handling, response bytes/text, direct `app.request`, or the binary-write workaround. If absent, the dependent helpers raise `ModuleNotFoundError`. This guide does not install them or certify that these legacy packages work on current Python; installing modern BeautifulSoup under another name is not a supported automatic substitute. Parser-seam tests are labelled separately from real legacy-package integration.
