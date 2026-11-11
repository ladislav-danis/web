# web.py

A lightweight Python web framework providing routing, templating, form handling, session management, database abstraction, and HTTP utilities.

## Overview

This repository contains the modified web.py library used by Mosaic. It can also run standalone applications without Mosaic Core. The library provides explicit URL-to-handler mappings, request processors, built-in template rendering, forms, and configurable server-side session stores. It does not discover Mosaic modules or provide `ModuleContext`.

**Security boundary:** a plain `web.application` dispatches a POST to its handler without requiring a CSRF token, login, or role. Adding `web.session.Session` does not add CSRF checks or role-based access control. Applications must configure their own authentication, authorization, and CSRF protection; session cookies alone are not those protections.

Mosaic adds a separate application layer: Core's `ModuleContext` (`src/core/registry.py` in the separate Core repository), module discovery and application wiring (`src/core/app.py` in Core), and CSRF/access helpers and policy (`src/core/access.py` in Core). Core wires these processors into its own application. Their behavior depends on that configuration, route exceptions, and handler-level checks; importing this library does not enable them or guarantee protection of every endpoint.

## Documentation

The index below describes the library components. The linked reference pages are separate documents; for exact current behavior, consult the corresponding source files and tests.

| File | Description |
|------|-------------|
| [application.md](./docs/application.md) | Explicit route mappings, HTTP method dispatch, request processors, and WSGI application |
| [browser.md](./docs/browser.md) | `AppBrowser` in-process application client and `Browser` network HTTP client |
| [db.md](./docs/db.md) | Multi-backend database abstraction and parameterized query helpers |
| [debugerror.md](./docs/debugerror.md) | Debug mode error pages and traceback display |
| [form.md](./docs/form.md) | Form definitions, validation, and rendering |
| [http.md](./docs/http.md) | HTTP cache headers, URL/query helpers, and profiling |
| [httpserver.md](./docs/httpserver.md) | Built-in HTTP server and static-file serving |
| [net.md](./docs/net.md) | Network utilities (IP validation, URL encoding, date handling) |
| [py3helpers.md](./docs/py3helpers.md) | Python 3 compatibility helpers |
| [session.md](./docs/session.md) | Server-side session stores and session-ID cookie handling |
| [template.md](./docs/template.md) | Built-in template rendering, optional layouts, and globals |
| [test.md](./docs/test.md) | Testing utilities and test helpers |
| [utils.md](./docs/utils.md) | General utility functions |
| [webapi.md](./docs/webapi.md) | Request context, input/cookies, response headers, and HTTP errors |
| [wsgi.md](./docs/wsgi.md) | WSGI server startup helpers, including FastCGI/SCGI dispatch |
| [contrib/template.md](./docs/contrib/template.md) | Optional third-party template-engine adapters |

## Quick Start

With this library and its dependencies available on Python's import path, save this as `hello.py` (not `web.py`) and run `python hello.py`. Visit `http://localhost:8080/hello`; stop the development server with Ctrl-C. No Mosaic Core configuration, session, or database is needed.

```python
import web

class Hello:
    def GET(self):
        return "Hello, world!"

urls = ('/hello', Hello)
app = web.application(urls, globals())
app.run()
```

For an offline check, the resulting `app.request('/hello')` returns status `200 OK` and data `b'Hello, world!'` without a listening server. The [README smoke tests](./tests/test_readme_contract.py) execute the exact fence with only the blocking `app.run()` entry point intercepted, then exercise the real application.

## Key Components

- **Routing** ([source](./application.py)): `web.application(mapping, fvars)` maps URL patterns to handler classes and dispatches their HTTP methods. `app.add_mapping(pattern, handler)` explicitly adds a route. Optional autoreloading of imported code is not Mosaic module discovery or a service/plugin registry.
- **Templating** ([source](./template.py)): the built-in `web.template.Render` (also exposed as `web.template.render`) loads template files itself, with optional `base` layout wrapping and `globals`. `FileSystemLoader` belongs to the optional Jinja2 adapter in [contrib/template.py](./contrib/template.py), not the built-in renderer. That module also provides Cheetah, Genshi, and Mako adapters; each needs its third-party engine installed separately.
- **Forms** ([source](./form.py)): declarative form definitions with validation and rendering, not automatic CSRF or authorization enforcement.
- **Sessions** ([source](./session.py)): `Session` loads/saves server-side state through `DiskStore`, `DBStore`, or `MemoryStore`; the browser cookie carries a session ID, not the session payload. Configure a non-default `web.config.session_parameters.secret_key` before constructing a session, and choose cookie/storage settings for your deployment. There is no automatic CSRF-token generation or RBAC policy in this layer.
- **Database** ([source](./db.py)): `web.database` provides parameterized query helpers with six built-in `dbn` registrations: `mysql` (MySQL), `postgres` (PostgreSQL), `sqlite` (SQLite), `firebird` (Firebird), `mssql` (SQL Server), and `oracle` (Oracle). Use these exact registration names, not `postgresql`, `sqlite3`, or `sqlserver`. Backends require their corresponding drivers and connection configuration; registration does not imply those dependencies are installed.
- **HTTP clients** ([source](./browser.py)): `AppBrowser`, also returned by `app.browser()`, sends requests in-process through `app.request`; `Browser` uses urllib for network HTTP requests. These are clients, not user-agent detection or JavaScript browser automation.
- **Mosaic integration**: module discovery, `ModuleContext`, and configured CSRF/access processors belong to the separately configured Core layer described above, not this library's standalone API.
