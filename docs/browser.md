# Web Browser Documentation

This document describes the browser testing helpers in [`browser.py`](../browser.py).

## Overview

`Browser` is an HTTP client built on `urllib.request`; `AppBrowser` uses the same interface to call a web.py application in-process through `AppHandler`. Neither client itself executes JavaScript or renders pages; the explicit `show()` helper requests an external desktop browser after saving. GET navigation, response bytes and cookies work without optional HTML/form parsers.

## Pinned Python 3 Limitations

The original audit at source revision `a540a4bd0ce90ad3cd8c2c91c9fbfd332eabb7ed` is tracked in `web#3`. `web#21` repairs the A-006 application bytes bridge and Unicode byte length. `web#22` repairs A-008 callable link filtering. `web#23` repairs A-009 binary saving and file closure. The retained str/reset boundaries below remain unchanged.

- **A-006 — repaired bytes bridge, retained str boundary:** `AppBrowser.open(..., data=bytes)` now dispatches the real handler and preserves raw bytes, including non-UTF-8/NUL. `Browser.open(..., data=str)` and `AppBrowser.open(..., data=str)` still fail in urllib with `TypeError: POST data should be bytes, an iterable of bytes, or a file object. It cannot be of type str.` Encode text as UTF-8 or URL-encoded forms as ASCII bytes before calling these clients. Direct `app.request` also accepts `str` and `dict`; see [the executable direct POST example](application.md#direct-post-workaround). The AppBrowser guarantee here covers bytes, not arbitrary iterables/file objects or legacy ClientForm compatibility.
- **A-008 — repaired callable link predicates:** `_filter_links`, `get_links`, `find_link` and searching `follow_link` accept a truthy callable `predicate`. It receives each anchor surviving the supplied text/URL criteria; a truthy result accepts the anchor. Criteria are ANDed in text, text-regex, URL, URL-regex, callable order and short-circuit on rejection. Empty input returns `[]` without calling it; results preserve input order and duplicate object identities. Predicate exceptions propagate unchanged. The existing truthiness gate is retained: `None` and falsy callable objects are ignored. This repair does not change `select_form`'s separate predicate handling or provide a legacy parser.
- **A-009 — repaired binary `show()`:** saves the exact response bytes (including empty, multibyte UTF-8, non-UTF-8 and NUL bytes) to `page.html` in the current working directory using binary overwrite mode (`'wb'`). It closes the file before requesting exactly one `webbrowser.open("file://" + os.path.abspath("page.html"))`. Open/write/close exceptions propagate; no browser launch is requested unless both write and close succeed. The context manager also closes the file on a write exception. A launch exception propagates after saving; the helper retains its `None` return value, even if `webbrowser.open` returns false. It preserves response bytes and navigation/status state. **Compatibility policy:** the filename/CWD and overwrite behavior are unchanged: an existing file is truncated, not atomically replaced or protected by no-clobber/sandbox checks. An I/O failure can leave a truncated or partial file. Do not use a valuable working directory or `page.html`; treat untrusted HTML as active content. Prefer the no-auto-launch temporary-file recipe below. This is not URL security or a guarantee that the external browser successfully renders the file.
- **A-010 — `reset()`:** clears cookies only. It preserves `path`, `url`, `_response`, `data`, `status`, selected `form` and cached `_forms`. It does not clear navigation/response state or destroy server-side sessions. Create a new `Browser()` or `app.browser()` for fresh client state; server-side isolation is separate.

The two former A-006 bytes limitation assertions are replaced one-to-one by desired-success regressions. The two str/urllib boundary regressions retain their original identities. The four former A-008 limitation identities (`_filter_links`, `get_links`, `find_link`, `follow_link`) are replaced one-to-one by `test_callable_links_desired_contract` with the same parameter identities. The former A-009 identity `test_pinned_limitation_a009_show_bytes_truncates_without_launch` is replaced one-to-one by `test_show_bytes_desired_save_closed_single_launch`, asserting exact binary save, closed file and one intercepted post-save launch. Cookie-only reset, text/URL/manual filtering, the exact Markdown parser-seam regression and `test_markdown_binary_preview_workaround_without_launch` remain unchanged; future source repairs must reconcile affected identities rather than silently remove assertions.

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
| `show()` | Saves exact bytes to CWD `page.html` (overwriting), closes the file, then requests one desktop launch; open/write/close failure prevents launch (A-009 repaired). |
| `get_response()` | Returns a file-like copy of the current response body/headers/URL. |
| `get_soup()` | Requires the optional legacy `BeautifulSoup` module. |
| `get_text(e=None)` | Extracts text with entities unquoted; without `e`, requires that same legacy parser. |
| `_get_links()` | Obtains anchor elements through `get_soup()`. |
| `get_links(text=None, text_regex=None, url=None, url_regex=None, predicate=None)` | Filters anchors by text/URL AND a truthy callable `predicate` (A-008 repaired). Requires the legacy parser. |
| `find_link(text=None, text_regex=None, url=None, url_regex=None, predicate=None)` | First matching anchor, or `None`; supports the same criteria/callable and requires the legacy parser. Filtering evaluates all surviving candidates, not just the first match. |
| `follow_link(link=None, text=None, text_regex=None, url=None, url_regex=None, predicate=None)` | Opens the first matching anchor's href, or raises `BrowserError`; searching supports the same criteria/callable and requires the legacy parser. An explicit `link` avoids searching and ignores search criteria. |
| `_filter_links(links, text=None, text_regex=None, url=None, url_regex=None, predicate=None)` | Filters supplied anchor-like objects with criteria AND callable; `[]` returns `[]` without calling the predicate. No parser needed for supplied objects (A-008 repaired). |
| `get_forms()` | Requires optional legacy `ClientForm`; returns/caches parsed form objects. |
| `select_form(name=None, predicate=None, index=0)` | Selects a parsed form; requires ClientForm unless already cached. Its predicate handling is separate from link filtering. |
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

The namespace must supply `b`, a browser with a compatible **legacy `BeautifulSoup`** installation and an already loaded page containing flat anchors such as `<a href="/next">Next</a>`. This example is not applicable to the plain-text page above. `bs4` is not the imported module. Exact text compares `link.string` (not all descendant text); regex uses search, and multiple supplied criteria are ANDed. Keep URL matches bounded; a filter is not a URL safety policy.

```python
# Callable results are ANDed with the bounded text/URL criteria.
links = b.get_links(text='Next', url_regex=r'^/next$',
                    predicate=lambda candidate: candidate.get('href') == '/next')
link = b.find_link(url='/next', predicate=lambda candidate: candidate.string == 'Next')
# Manual filtering and following an explicit anchor remain supported alternatives.
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

Preferred even after the `show()` repair: after a successful GET, write bytes into an owned temporary directory, not `page.html` in the working directory. The initial namespace supplies `b`, a browser with a loaded bytes response; all other imports are in the snippet. This snippet never launches a desktop browser. The file is available inside the context; if you choose to inspect it manually, do so before the context ends. Treat untrusted HTML as active content. The directory/file are removed on exit.

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
- **Response inspection:** `get_response()` returns a new file-like body copy. `show()` now saves bytes and closes before requesting an external browser (A-009 repaired). Its fixed CWD filename still overwrites existing content and is not an atomic or sandboxed save; prefer the binary temporary-file recipe without auto-launch.
- **Links:** `_get_links`/`get_links`/`find_link`/searching `follow_link` depend on legacy BeautifulSoup. Text/URL exact and regex filters work with suitable anchor objects. A truthy callable `predicate=` runs after the built-in filters and is ANDed with them (A-008 repaired); `None`/falsy callable objects are ignored. Exceptions propagate, and order/duplicates are preserved. Manual list filtering followed by `follow_link(link=...)` is also supported; no match returns `[]`/`None` or raises `BrowserError` when following.
- **Forms:** `get_forms` parses with ClientForm and caches results. `select_form` filters by name/predicate and selects by index; field access delegates to that selected form. This API description is not certification of legacy ClientForm integration; the manually encoded bytes example above does not use that dependency.
- **Reset:** `reset()` only calls `cookiejar.clear()`. Path/URL, response/body/status and selected/cached forms remain (A-010). Start a new client for fresh client state.

## Constants

`DEBUG` is a boolean flag for request debug output (default `False`). There are no module-level public functions.

## Dependencies

HTML/form helpers have **optional, legacy dependencies**, imported lazily:

- [`BeautifulSoup`](https://www.crummy.com/software/BeautifulSoup/): the literal `import BeautifulSoup` in `get_soup()`, not `bs4`. Link helpers and default `get_text()` depend on its older API.
- [`ClientForm`](https://pythonhosted.org/ClientForm/): the literal `import ClientForm` in `get_forms()`, whose objects support form field access and `click()`.

They are not in Python's standard library and are not needed for basic GET, manually encoded AppBrowser POST, cookie handling, response bytes/text, direct `app.request`, binary `show()`, or the manual binary-write recipe. If absent, the dependent helpers raise `ModuleNotFoundError`. This guide does not install them or certify that these legacy packages work on current Python; installing modern BeautifulSoup under another name is not a supported automatic substitute. Parser-seam tests are labelled separately from real legacy-package integration.
