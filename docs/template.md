# Web Template Documentation

## Overview

`web.template` is a simple, elegant templating system that compiles templates to Python code for efficient execution. It provides a syntax for generating dynamic content with AST-based restrictions. Treat template source as trusted application code, not as an untrusted-user sandbox; see [Security Features](#security-features) for the boundaries and known assignment-validation defect.

### Design Principles

- **Template string is split into tokens** and combined into nodes
- **Parse tree** consists of text nodes, expression nodes, and block nodes (for loops, if statements, etc.)
- Each node emits Python code strings
- **Root node** emits Python code that is checked by the AST visitor and executed in the given environment; these checks are not a complete sandbox
- **Line-to-line matching** between template and generated code for accurate error reporting

## Template Syntax

### Basic Syntax

Templates use `$` as the escape character for dynamic content:

| Syntax | Description |
|--------|-------------|
| `$varname` | Output variable value through the configured filter, if any |
| `$:varname` | Output variable value without applying the filter |
| `$(expression)` | Output expression result through the configured filter, if any |
| `${expression}` | Alternative expression grouping, through the configured filter, if any |
| `$$` | Literal dollar sign `$` |
| `$# comment` | Comment (not rendered in output) |

Normal interpolation is HTML-escaped only when an HTML-escaping filter is selected. Literal template markup and `$:` interpolation are not filtered. For a direct HTML `Template`, explicitly use `filename="page.html"` or `filter=web.websafe`; see [HTML Escaping](#html-escaping).

### Expressions

Expressions can be simple identifiers or complex Python expressions:

```python
$varname                    # Simple variable
$object.attribute           # Attribute access
$list[0]                    # Index access
$func(1, 2, 3)              # Function call
$object.method().attr       # Chained operations
$(x + y)                    # Expression in parentheses
${len(items)}               # Expression in braces
```

### Control Structures

#### If Statements

```python
$if condition:
    content

$if condition:
    content
$elif other_condition:
    content
$else:
    content
```

#### For Loops

```python
$for item in items:
    $item

$for index, value in enumerate(items):
    $index: $value
```

Loop helpers (available inside for loops):
- `loop.index` - Current iteration number (1-based)
- `loop.index0` - Current iteration number (0-based)
- `loop.first` - True if first iteration
- `loop.last` - True if last iteration
- `loop.parity` - "odd" or "even"
- `loop.even` - True if even index
- `loop.odd` - True if odd index
- `loop.revindex` - Reverse index (from end)
- `loop.revindex0` - Reverse index (0-based from end)
- `loop.parent` - Reference to parent loop context

#### While Loops

```python
$while condition:
    content
```

#### Code Blocks

```python
$code:
    # Python code that doesn't produce output
    # Useful for imports, function definitions, etc.
    import os
    def helper(x):
        return x * 2
```

### Assignments

```python
$a = value                    # Simple assignment
$a:                           # Multi-line assignment
    content that becomes the value
```

### Function Definitions

```python
$def with (arg1, arg2=default):
    template content using $arg1 and $arg2
```

### Variables Declaration

```python
$var name: value              # Creates attribute accessible as result.name
$var name = value             # Alternative syntax
```

## Template Structure

### Basic Template

```python
$def with (name)
Hello $name!
```

### Template with Control Structures

```python
$def with (items)
<ul>
$for item in items:
    <li>$item</li>
</ul>
```

### Template with Variables

```python
$var title: My Page
$var content: Welcome

<h1>$:title</h1>
$:content
```

## Classes

### `Parser`

Base parser class that converts template text into a parse tree.

#### Methods

##### `parse(text, name="<template>")`

Parses template text and returns a `DefwithNode` representing the parse tree.

##### `read_defwith(text)`

Reads the `$def with` declaration from the beginning of the text.

##### `read_section(text)`

Reads one section from the text. Sections can be blocks, assignments, or lines.

##### `read_suite(text)`

Reads multiple sections until end of text, returning a `SuiteNode`.

##### `readline(text)`

Reads one line from the text, handling line continuation with `\`.

##### `read_node(text)`

Reads a single node (text or expression) from the text.

##### `read_text(text)`

Reads a text node from the text.

##### `read_expr(text, escape=True)`

Reads a Python expression and returns an `ExpressionNode`.

##### `read_assignment(text)`

Reads an assignment statement.

##### `read_block_section(text, begin_indent="")`

Reads a block section (for, if, while, etc.) with proper indentation handling.

##### `create_block_node(keyword, stmt, block, begin_indent)`

Creates the appropriate block node based on the keyword.

### `PythonTokenizer`

Utility wrapper over Python's tokenizer for parsing Python code within templates.

#### Methods

##### `__init__(text)`

Initializes the tokenizer with the given text.

##### `consume_till(delim)`

Consumes tokens until the specified delimiter is found.

### Node Classes

#### `DefwithNode`

Represents the template definition with arguments and suite.

- `defwith` - The `$def with` declaration
- `suite` - The body of the template
- `emit(indent)` - Generates Python code for the template

#### `TextNode`

Represents literal text in the template.

- `value` - The text content
- `emit(indent)` - Returns the text as a Python string literal

#### `ExpressionNode`

Represents a dynamic expression in the template.

- `value` - The Python expression
- `escape` - Whether to apply the template filter to this interpolated value (if a filter is configured)
- `emit(indent)` - Generates code to output the expression

#### `AssignmentNode`

Represents an assignment statement.

- `code` - The assignment code
- `emit(indent)` - Generates the assignment code

#### `LineNode`

Represents a line of template content.

- `nodes` - List of child nodes (text and expressions)
- `emit(indent, text_indent="", name="")` - Generates code for the line

#### `BlockNode`

Base class for block statements (for, if, while, etc.).

- `stmt` - The statement line
- `suite` - The body of the block
- `begin_indent` - Initial indentation level
- `emit(indent, text_indent="")` - Generates code for the block

#### `ForNode`

Represents a for loop block.

Extends `BlockNode` and wraps the iteration to support `loop` helpers.

#### `CodeNode`

Represents a `$code:` block.

- `code` - The Python code
- `emit(indent, text_indent="")` - Generates the code with proper indentation

#### `StatementNode`

Represents a simple statement (pass, break, continue, return).

- `stmt` - The statement text
- `emit(indent, begin_indent="")` - Generates the statement

#### `IfNode`, `ElseNode`, `ElifNode`

Represents if/else/elif blocks. These extend `BlockNode`.

#### `DefNode`

Represents a function definition block.

Extends `BlockNode` with special handling for function scope.

#### `VarNode`

Represents a `$var` declaration.

- `name` - The variable name
- `value` - The variable value
- `emit(indent, text_indent)` - Generates code to set the variable

#### `SuiteNode`

Represents a suite (sequence) of sections.

- `sections` - List of section nodes
- `emit(indent, text_indent="")` - Generates code for all sections

### Template Execution Classes

#### `ForLoop`

Wrapper for for loop expressions to support `loop.xxx` helpers.

- `setup(seq)` - Sets up iteration over a sequence
- `index` - Current iteration number (1-based)
- `index0` - Current iteration number (0-based)
- `first` - True if first iteration
- `last` - True if last iteration
- `parity` - "odd" or "even"
- `even` - True if even index
- `odd` - True if odd index
- `revindex` - Reverse index
- `revindex0` - Reverse index (0-based)

#### `ForLoopContext`

Stackable context for nested for loops.

- `setup(seq)` - Sets up iteration
- `parent` - Reference to parent loop context
- `length` - Length of the sequence

#### `BaseTemplate`

Base class for template execution.

##### Methods

- `__init__(code, filename, filter, globals, builtins)` - Initializes the template
- `_compile(code)` - Compiles the template code
- `__call__(*a, **kw)` - Executes the template
- `make_env(globals, builtins_)` - Creates the execution environment
- `_join(*items)` - Joins template output parts
- `_escape(value, escape=False)` - Escapes output if needed

#### `Template`

Main template class that compiles and executes templates.

##### Constructor

```python
Template(
    text, 
    filename="<template>", 
    filter=None, 
    globals=None, 
    builtins=None, 
    extensions=None
)
```

- `text` - Template source text
- `filename` - Filename for error reporting and case-sensitive extension selection of the default filter and content type
- `filter` - Function applied to normal interpolated values, not literal text or `$:` values. A truthy explicit filter overrides the extension default; `None` and `False` fall back to it, so they do not disable escaping for `.html`. See [HTML Escaping](#html-escaping).
- `globals` - Global variables available to template
- `builtins` - Built-in functions available to template
- `extensions` - List of parser extensions

##### Methods

- `__call__(*a, **kw)` - Executes the template with arguments
- `normalize_text(text)` - Normalizes template text (handles line endings, BOM)
- `generate_code(text, filename, parser=None)` - Generates Python code from template
- `compile_template(template_string, filename)` - Compiles template to executable code

##### Class Attributes

- `CONTENT_TYPES` - Mapping of file extensions to content types
- `FILTERS` - Default filters by file extension
- `globals` - Global variables shared by all templates

#### `CompiledTemplate`

Template class for pre-compiled templates.

- `__init__(f, filename)` - Initializes with a pre-compiled function

#### `Render`

Convenient template rendering from directories.

##### Constructor

```python
Render(
    loc="templates", 
    cache=None, 
    base=None, 
    **keywords
)
```

- `loc` - Directory containing templates
- `cache` - Whether to cache templates (default: not in debug mode)
- `base` - Base template to wrap all templates with
- `**keywords` - Additional arguments passed to Template constructor

##### Methods

- `_add_global(obj, name=None)` - Adds a global to this renderer
- `_load_template(name)` - Loads a template by name
- `_template(name)` - Gets a template (with caching)
- `__getattr__(name)` - Gets a template as an attribute

#### `GAE_Render`

Render class for Google App Engine.

Extends `Render` to work with GAE's module system.

### Security Classes

#### `SafeVisitor`

AST visitor enforcing restrictions on visited template nodes, not an OS or complete Python sandbox.

Checks include:
- Restricted AST node types (`ALLOWED_AST_NODES`)
- Restricted attribute prefixes (`_`, `func_`, `im_`)
- Direct attribute assignment targets
- Names starting with `__`

**Known defect:** augmented attribute assignment and tuple-unpacked attribute targets pass validation and can mutate supplied objects. The augmented-assignment visitor also omits normal child traversal. These restrictions are therefore not universal guarantees; see [AST Validation](#ast-validation).

##### Methods

- `walk(tree, filename)` - Visits the AST and raises `SecurityError` for detected violations; acceptance is not proof that execution is safe
- `fail_node(node, nodename)` - Reports an unsafe node
- `fail_attribute(node, attrname)` - Reports unsafe attribute access
- `fail_name(node)` - Reports unsafe name access

#### `TemplateResult`

Dictionary-like object for storing template output and attributes.

The template result stores output in `__body__` and additional attributes separately.

##### Methods

- `__init__(*a, **kw)` - Initializes with optional body and attributes
- `extend(parts)` - Adds parts to the output
- `keys()` - Returns all keys (including `__body__`)
- `__getitem__(name)` - Gets a value
- `__setitem__(name, value)` - Sets a value
- `__delitem__(name)` - Deletes a value
- `__getattr__(key)` - Gets a value as an attribute
- `__setattr__(key, value)` - Sets a value as an attribute
- `__delattr__(key)` - Deletes a value as an attribute
- `__str__()` / `__unicode__()` - Returns the body content
- `__repr__()` - Returns a string representation
- `__len()` - Returns the number of attributes
- `__iter__()` - Iterates over keys

### Functions

#### `splitline(text)`

Splits text at the first newline.

```python
splitline('foo\nbar')  # ('foo\n', 'bar')
splitline('foo')       # ('foo', '')
splitline('')          # ('', '')
```

#### `compile_templates(root)`

Compiles all templates in a directory to Python code.

Creates `__init__.py` files with compiled templates for faster loading.

#### `frender(path, **keywords)`

Creates a template from a file path.

```python
template = frender('path/to/template.html')
print(template())
```

#### `test()`

Runs doctests for the template module.

### Constants

#### `STATEMENT_NODES`

Dictionary mapping statement keywords to node classes:

```python
{
    "for": ForNode,
    "while": BlockNode,
    "if": IfNode,
    "elif": ElifNode,
    "else": ElseNode,
    "def": DefNode,
    "code": CodeNode,
}
```

#### `KEYWORDS`

List of simple keywords: `["pass", "break", "continue", "return"]`

#### `TEMPLATE_BUILTIN_NAMES`

List of built-in names available in templates:

```python
[
    "dict", "enumerate", "float", "int", "bool",
    "list", "reversed", "set", "slice", "tuple",
    "abs", "all", "any", "callable", "chr", "cmp",
    "divmod", "filter", "hex", "id", "isinstance",
    "iter", "len", "max", "min", "oct", "ord",
    "pow", "range", "round", "True", "False", "None",
    "__import__"
]
```

#### `TEMPLATE_BUILTINS`

Dictionary of built-in functions available in templates.

#### `ALLOWED_AST_NODES`

List of allowed AST node types for security validation.

## Usage Examples

The HTML example below that assigns `html = template(...)` and the self-contained
examples in [Security Features](#security-features) are executable security
contracts. Other legacy usage/syntax fragments on this page remain incomplete
or unverified (tracked separately in web#15); do not treat them as validated
standalone recipes or infer HTML escaping from them.

### Basic Template

```python
from web.template import Template

template = Template("Hello $name!")
result = template(name="World")
print(result)  # Hello World!
```

### Template with Variables

```python
from web.template import Template

# The argument declaration must be the first line of the template string.
template = Template("""$def with (title, items)
<html>
<head><title>$title</title></head>
<body>
$for item in items:
    <p>$item</p>
</body>
</html>
""", filename="page.html")

html = template(title="My Page", items=["Item 1", "Item 2"])
assert "<title>My Page</title>" in str(html)
assert "<p>Item 1</p>" in str(html)
```

### Template with Control Structures

```python
template = Template("""
$def with (user, items)
$if user:
    <h1>Welcome, $user.name!</h1>
$else:
    <h1>Welcome, Guest</h1>

$if items:
    <ul>
    $for item in items:
        <li>$item</li>
    </ul>
$else:
    <p>No items available</p>
""")
```

### Rendering from Directory

```python
from web.template import Render

render = Render('templates')

# Render templates from the templates directory
print(render.index())
print(render.page(name="About"))
```

### Using Base Templates

```python
render = Render('templates', base='layout')

# All templates will be wrapped with layout.html
print(render.page())  # Uses layout.html as base
```

### Template with Functions

```python
template = Template("""
$def with (items)
$def format_item(item):
    <strong>$item</strong>

<ul>
$for item in items:
    <li>$:format_item(item)</li>
</ul>
""")
```

### Template with Variables

```python
template = Template("""
$var title: My Website
$var author: John Doe

<html>
<head>
    <title>$:title</title>
</head>
<body>
    <p>By $:author</p>
</body>
</html>
""")

result = template()
print(result.title)   # My Website
print(result.author)  # John Doe
```

### Using Loop Helpers

```python
template = Template("""
$for i in range(5):
    Index: $loop.index
    Zero-based: $loop.index0
    First: $loop.first
    Last: $loop.last
    Parity: $loop.parity
    <br>
""")
```

### Nested Loops

```python
template = Template("""
$for row in rows:
    Row $loop.index
    $for col in cols:
        Column $loop.index (parent: $loop.parent.index)
    $end
$end
""")
```

## Security Features

### AST Validation

Template construction compiles generated Python and applies `SafeVisitor`.
Ordinary visited expressions reject restricted names/attributes and disallowed
node types (for example, an `import` statement). A direct attribute target such
as `a.x = 3` is rejected with `SecurityError` at construction time.

**This revision does not enforce a complete ban on attribute writes.**
`a.x += 1` and `(a.x, y) = (2, 3)` compile and mutate the supplied object when
rendered; nested tuple targets also pass. `visit_AugAssign` checks the statement
node instead of its target and does not visit its children; assignment-target
checking does not recurse into tuples. This is an unresolved source security
defect, not supported safe mutation or a runtime fix in this documentation.
A separate source-hardening issue must track rejection of these writes and
preservation of the existing restrictions before web#14 can be closed.

This harmless example uses only newly created objects, not application state:

```python
from types import SimpleNamespace
from web.template import Template, SecurityError

box = SimpleNamespace(x=1)
try:
    Template("$def with(a)\n$code:\n    a.x = 3\n$a.x")
except SecurityError:
    pass
else:
    raise AssertionError("Direct attribute assignment must be rejected")
assert box.x == 1

# Characterizations of an unresolved defect, not recommended template code.
for statement, expected in [("a.x += 1", 2), ("(a.x, y) = (2, 3)", 2)]:
    owned = SimpleNamespace(x=1)
    template = Template("$def with(a)\n$code:\n    " + statement + "\n$a.x")
    assert owned.x == 1
    assert str(template(owned)) == str(expected) + "\n"
    assert owned.x == expected
```

Treat templates as **trusted application code**. Objects, globals and callables
passed to them confer application capabilities, including side effects through
ordinary allowed method/function calls. Even complete assignment validation
would not isolate files, processes, network access or resource consumption of
those callables. Do not compile or render untrusted user-authored templates.

### Safe Built-ins

The default environment exposes a restricted built-in mapping. This reduces available names but is not a security boundary for untrusted templates or supplied callables. Application-provided globals, arguments and custom builtins affect capabilities. The legacy builtins list above is part of the separate web#15 reference audit, not a verified security allowlist.

### HTML Escaping

Escaping depends on the **case-sensitive filename extension**, not on whether
the template string contains HTML. `Render(directory)` uses the filename of the
actual file it loads; direct `Template(text)` defaults to `"<template>"`.

| Filename extension | Default interpolation filter | Content type mapping |
| --- | --- | --- |
| `.html` | `web.websafe` | `text/html; charset=utf-8` |
| `.xhtml` | `web.websafe` | `application/xhtml+xml; charset=utf-8` |
| `.xml` | `web.websafe` | None (no XML entry in `CONTENT_TYPES`) |
| `.txt` | None | `text/plain` |
| No extension, unknown extension, `.HTML`, or `"<template>"` | None | None |

A truthy explicit `filter` overrides the extension default. `filter=None` and
`filter=False` fall back to that default; they do **not** disable HTML escaping.
Filter selection and content-type selection are separate decisions.

Normal `$value`, `$(expression)` and `${expression}` interpolations convert `None` to an empty
string and other values to Unicode, then call the selected filter if any.
`${expression}` is converted to parenthesized grouping by the expression node.
Literal template markup is unchanged. `$:value` still converts the
value to text but bypasses the filter entirely, so use it only for deliberately
trusted markup, not untrusted input.

`web.websafe` escapes HTML metacharacters for text and ordinary quoted HTML
attributes. It is not JavaScript/CSS escaping, URL-scheme validation, HTML
sanitization, or blanket XSS prevention. Choose context-appropriate handling;
filtering an interpolation does not make arbitrary template markup safe.

This standalone example uses real files only in an owned temporary directory:

```python
from pathlib import Path
from tempfile import TemporaryDirectory
import web
from web.template import Template, Render

source = '$def with(value)\n<p title="$value">$(value)</p>|$:value'
value = "<b>&\"'"
escaped = "&lt;b&gt;&amp;&quot;&#39;"
filtered = '<p title="' + escaped + '">' + escaped + '</p>|' + value + '\n'
unfiltered = '<p title="' + value + '">' + value + '</p>|' + value + '\n'
assert str(Template(source)(value)) == unfiltered
assert str(Template(source, filename="page.html")(value)) == filtered
assert str(Template(source, filter=web.websafe)(value)) == filtered
assert str(Template(source, filename="page.html", filter=False)(value)) == filtered

with TemporaryDirectory() as directory:
    root = Path(directory)
    (root / "page.html").write_text(source, encoding="utf-8")
    (root / "plain.txt").write_text(source, encoding="utf-8")
    render = Render(str(root), cache=False)
    assert str(render.page(value)) == filtered
    assert str(render.plain(value)) == unfiltered
assert not root.exists()
```

## Template Syntax Reference

### Variables

```python
$name              # Variable through selected filter, if any
$:name             # Variable bypassing filter
${name}            # Alternative grouping through selected filter, if any
$(expression)      # Grouped expression through selected filter, if any
```

### Expressions

```python
$func(1, 2)        # Function call
$obj.attr          # Attribute access
$list[0]           # Index access
$dict['key']       # Dictionary access
$len(items)        # Built-in function
```

### Control Structures

```python
$if condition:
    content

$for item in items:
    content

$while condition:
    content

$code:
    # Python code
```

### Assignments

```python
$a = value         # Simple assignment
$a:                # Multi-line assignment
    content
```

### Comments

```python
$# This is a comment
```

## Template Directives

### `$def with (...)`

Defines template arguments.

```python
$def with (name, age=25)
Hello $name, you are $age years old.
```

### `$var name: value`

Declares a template variable (accessible as result.name).

```python
$var title: My Page
$var content: Welcome
```

### `$code:`

Defines Python code that doesn't produce output.

```python
$code:
    import os
    def helper(x):
        return x * 2
```

### `$pass`, `$break`, `$continue`, `$return`

Simple statements for control flow.

```python
$for item in items:
    $if not item:
        $pass
    $if item == 'stop':
        $break
