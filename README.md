# web.py

A lightweight Python web framework providing routing, templating, form handling, session management, database abstraction, and HTTP utilities.

## Overview

This framework is built on a modified version of web.py and provides the foundation for the Mosaic platform's service-oriented architecture. It includes a template rendering system with layout support, a form validation system, session middleware with CSRF protection, and a modular architecture that allows plugins to register routes and services at runtime.

The framework is designed for simplicity and rapid development while maintaining security through built-in CSRF protection, session management, and role-based access control integration.

## Documentation

| File | Description |
|------|-------------|
| [application.md](./docs/application.md) | Application factory, module loading, and configuration |
| [browser.md](./docs/browser.md) | Browser detection and user-agent handling |
| [db.md](./docs/db.md) | Database abstraction layer and query helpers |
| [debugerror.md](./docs/debugerror.md) | Debug mode error pages and traceback display |
| [form.md](./docs/form.md) | Form definitions, validation, and rendering |
| [http.md](./docs/http.md) | HTTP request/response objects and utilities |
| [httpserver.md](./docs/httpserver.md) | Built-in HTTP server configuration |
| [net.md](./docs/net.md) | Network utilities (IP validation, URL encoding, date handling) |
| [py3helpers.md](./docs/py3helpers.md) | Python 3 compatibility helpers |
| [session.md](./docs/session.md) | Session management and middleware |
| [template.md](./docs/template.md) | Template rendering, layouts, and globals |
| [test.md](./docs/test.md) | Testing utilities and test helpers |
| [utils.md](./docs/utils.md) | General utility functions |
| [webapi.md](./docs/webapi.md) | API classes (HTTP, WSGI, utilities) |
| [wsgi.md](./docs/wsgi.md) | WSGI application interface |
| [contrib/template.md](./docs/contrib/template.md) | Template contribution guidelines |

## Quick Start

```python
import web

class Hello:
    def GET(self):
        return "Hello, world!"

urls = ('/hello', Hello)
app = web.application(urls, globals())
app.run()
```

## Key Components

- **Routing**: URL patterns mapped to handler classes with HTTP method dispatch
- **Templating**: FileSystemLoader with layout support and injected globals
- **Forms**: Declarative form definitions with validation and rendering
- **Sessions**: Cookie-based sessions with configurable storage and CSRF tokens
- **Database**: SQLite abstraction with parameterized queries
- **Modules**: Runtime module discovery and route registration via `ModuleContext`
