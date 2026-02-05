# Template Rendering Interface

This module provides interfaces to various templating engines for use with the Web.py framework.

## Overview

The `web.contrib.template` module offers a unified interface to different Python templating engines, making it easy to switch between them without changing your application code. It currently supports Cheetah, Genshi, Jinja2, and Mako templating engines.

## Classes

### `render_cheetah`

Rendering interface to Cheetah Templates.

**Example:**
```python
render = render_cheetah('templates')
render.hello(name="cheetah")
```

**Parameters:**

*   `path` (str): Directory path where templates are stored.

### `render_genshi`

Rendering interface to Genshi templates.

**Example for XML/HTML templates:**
```python
render = render_genshi(['templates/'])
render.hello(name='genshi')
```

**Example for text templates:**
```python
render = render_genshi(['templates/'], type='text')
render.hello(name='genshi')
```

**Parameters:**

*   `*a`: Arguments passed to `TemplateLoader`.
*   `type` (str, optional): Template type ('text' for text templates, defaults to HTML).

### `render_jinja`

Rendering interface to Jinja2 Templates.

**Example:**
```python
render = render_jinja('templates')
render.hello(name='jinja2')
```

**Parameters:**

*   `*a`: Arguments passed to `FileSystemLoader`.
*   `extensions` (list, optional): List of Jinja2 extensions to use.
*   `globals` (dict, optional): Global variables to make available in templates.

### `render_mako`

Rendering interface to Mako Templates.

**Example:**
```python
render = render_mako(directories=['templates'])
render.hello(name="mako")
```

**Parameters:**

*   `*a`: Arguments passed to `TemplateLookup`.
*   `**kwargs`: Keyword arguments passed to `TemplateLookup`.

### `cache`

Cache for any rendering interface.

**Example:**
```python
render = cache(render_cheetah("templates/"))
render.hello(name='cache')
```

**Parameters:**

*   `render`: A rendering interface instance (e.g., `render_cheetah`, `render_genshi`, etc.).

## Usage Notes

1.  Each renderer class expects templates to be stored with a `.html` extension by default.
2.  Template names are mapped directly to method calls on the renderer object.
3.  The `cache` wrapper can improve performance for frequently used templates.
4.  All rendering functions accept keyword arguments that become template variables.
5.  The module will raise `ImportError` if the required templating engine is not installed.

## Installation Requirements

To use the different template engines, you need to install the corresponding packages:

*   **Cheetah**: `pip install Cheetah`
*   **Genshi**: `pip install Genshi`
*   **Jinja2**: `pip install Jinja2`
*   **Mako**: `pip install Mako`