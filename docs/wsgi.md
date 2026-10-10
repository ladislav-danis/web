# Web WSGI Utilities Documentation

This document describes the WSGI utility functions in `web/wsgi.py`, which provide tools for running WSGI applications with various server backends and deployment configurations.

## Overview

The module dispatches WSGI callables to FastCGI, SCGI or the Cheroot HTTP helper using a small set of environment and argv rules. Dispatch is separate from debug configuration and from deployment safety. The source contracts below describe this revision, not general platform detection.

## Functions

### `runfcgi(func, addr=("localhost", 8000))`

Imports optional `flup.server.fcgi` and returns the result of
`WSGIServer(func, multiplexed=True, bindAddress=addr, debug=False).run()`.
`addr` is passed through **unchanged**, including None, a socket path, or an
invalid value. This function does not call `validaddr`. The `debug=False`
constructor argument configures flup, not `web.config.debug`.

### `runscgi(func, addr=("localhost", 4000))`

Imports optional `flup.server.scgi` and returns the result of
`WSGIServer(func, bindAddress=addr, debug=False).run()`. The address is likewise
passed through without framework validation. These functions need an installed,
compatible flup backend and separately configured gateway. The contract tests
record constructor/run boundaries; they do **not** start flup or certify a
FastCGI/SCGI deployment. If flup is absent the import fails, not a fallback to
HTTP. No flup package is installed by these helpers or by these tests.

### `runwsgi(func)`

Dispatch is ordered; it returns the selected backend's result. This is not a
validator for deployment security, reachability or every binding address.

1. Presence of `SERVER_SOFTWARE` (including an empty value) first writes
   `os.environ["FCGI_FORCE_CGI"] = "Y"`, overwriting a previous value. Presence
   of **either** `SERVER_SOFTWARE` or `PHP_FCGI_CHILDREN` then calls
   `runfcgi(func, None)` without parsing CLI addresses. PHP alone does not set
   or clear `FCGI_FORCE_CGI`. None delegates inherited/CGI socket behavior to
   flup; it is not a validated TCP address.
2. Otherwise an exact `fcgi` or `fastcgi` anywhere in `sys.argv` selects FastCGI.
   A copy of `sys.argv[1:]` loses the **first `fastcgi` if present**, otherwise
   the first `fcgi`. If anything remains, only its first element is passed
   through `validaddr`; otherwise `runfcgi(func, None)` is called.
3. Otherwise an exact `scgi` anywhere in `sys.argv` selects SCGI. A copy of
   `sys.argv[1:]` loses its first `scgi`. The first remaining element is passed
   to `validaddr`, or no address argument is supplied (the direct SCGI default
   is `("localhost", 4000)`).
4. Otherwise `validaddr` parses `sys.argv[1]`, defaulting to the empty string:
   the resulting default is `("0.0.0.0", 8080)`. **Only after that parse**, if
   `PORT` is present, the result is replaced by
   `("0.0.0.0", intget(os.environ["PORT"]))`, and passed to `runsimple`.
   This overrides a valid CLI host as well as its port. A malformed CLI address
   still raises ValueError even when PORT is valid; PORT does not rescue it.

`sys.argv` itself is not changed. Extra arguments after the first remaining
address are ignored, not generally parsed. Duplicate/mixed mode tokens may
therefore become invalid addresses: `fcgi fastcgi` removes `fastcgi`, then
tries to parse `fcgi`; `scgi fcgi` selects FastCGI then parses `scgi`. Mode
membership includes argv[0], but removal uses only argv[1:]: argv equal to
`["fcgi"]` reaches `runfcgi(func, None)`, whereas `["scgi"]` raises ValueError
trying to remove a missing token. `mod_wsgi` affects the debug heuristic only,
not dispatch. Unlike `_is_dev_mode`, `runwsgi` normally requires `sys.argv`;
without it the non-environment branches raise AttributeError.

`validaddr` handles CLI IP/port forms (port range 0..65535) or passes strings
containing `/` through as socket paths. It is not a blanket binding safety
check. Direct adapter addresses and the environment branch bypass it entirely.
`PORT` uses `intget`, **not range validation**: `9000` becomes 9000;
`not-a-port` or an empty string becomes None; `-1`, `0` and `65536` are passed
as those integers. Integer syntax such as surrounding spaces is accepted.
These are dispatch observations with recording server stubs, not successful
binds. Any later rejection belongs to the backend. The wildcard `0.0.0.0`
may expose the listener beyond this machine.

### `_is_dev_mode()` and `web.config.debug`

This is a small heuristic, **not production detection or a security boundary**.
It returns False if `SERVER_SOFTWARE` or `PHP_FCGI_CHILDREN` is **present** in
`os.environ` (even an empty value), or if any exact, case-sensitive element of
`sys.argv` is `fcgi`, `fastcgi`, or `mod_wsgi` (including argv[0]). Otherwise it
returns True: `scgi` alone and `PORT` alone both leave it True. A missing
`sys.argv` is treated as an empty list by this heuristic, not by `runwsgi`.

Importing or reloading `web.wsgi` executes
`web.config.setdefault("debug", _is_dev_mode())`. It only supplies a missing
key: pre-set True **and** pre-set False survive. The heuristic itself just
returns a boolean; it does not update configuration. Explicitly set debug to
False **before constructing the application** in production. Neither SCGI,
cloud environment variables nor this heuristic guarantee safe error pages.
Explicit debug handlers can still expose diagnostics regardless of this flag.

## Usage Examples

### Basic WSGI Deployment

A self-contained application module exporting a WSGI callable for a separately
configured WSGI host. Importing or running this module does not open a listener;
server lifecycle is shown in [the bounded HTTP example](httpserver.md#stopping-the-server).
This sets the application's default error policy, not every deployment option.

```python
import web

web.config.debug = False

class index:
    def GET(self):
        return "Hello World!"

app = web.application(("/", "index"), globals(), autoreload=False)
application = app.wsgifunc()
```

### FastCGI / SCGI invocation reference

Argument shapes below are reference notation, **not executable deployment
recipes**. They assume a separate entry point that actually calls
`web.wsgi.runwsgi` with its WSGI callable; the application module above only
exports that callable. Configure and verify the optional gateway separately.

```text
<entry-point> fcgi
<entry-point> fcgi 127.0.0.1:9000
<entry-point> scgi
<entry-point> scgi 127.0.0.1:4000
```

### Heroku Deployment

A cloud-provided PORT is input, not validation or automatic production safety.
Here is a **deployment-configuration policy**, deliberately stricter than the
unchanged runtime: require ASCII decimal text in 1..65535, default to 8080 only
when PORT is absent, and choose loopback explicitly. The function is usable
outside a server process; this example validates and prints configuration but
does not start a listener or connect to a service.

```python
import os
import re

def configured_address(environ):
    value = environ.get("PORT", "8080")
    if not re.fullmatch(r"[0-9]+", value):
        raise ValueError("PORT must contain ASCII decimal digits")
    port = int(value)
    if not 1 <= port <= 65535:
        raise ValueError("PORT must be in 1..65535")
    return ("127.0.0.1", port)

address = configured_address(os.environ)
print(address)
```

Pass this tuple directly to an explicitly owned server (as in the linked HTTP
example), **not back through `runwsgi`**: its PORT branch would replace the
loopback host with `0.0.0.0`. Choose a different interface only deliberately
for the actual hosting platform and access policy. This does not modify
`runwsgi`, `intget`, their accepted syntax, error propagation or port policy.
The example is not Heroku platform certification.

## Environment Variables

### `SERVER_SOFTWARE`
Set when running under CGI or web server environments.

### `PHP_FCGI_CHILDREN`
Set by lighttpd FastCGI.

### `PORT`
Set by Heroku and other cloud platforms for port configuration.

## Command Line Arguments

### `fcgi` or `fastcgi`
Run application as FastCGI server.

### `scgi`
Run application as SCGI server.

## Security Considerations

- Dispatch and debug heuristics do not prevent unsafe deployment configurations.
- Set `web.config.debug = False` explicitly before application construction.
- Validate deployment configuration explicitly; only CLI addresses use `validaddr`, with the exceptions and ordering above.

## Dependencies

This module requires:
- `flup` package for FastCGI and SCGI support (optional)
- `web.httpserver` for built-in web server functionality
- `web.net` for address validation
- `web.utils` for utility functions
