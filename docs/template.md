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

Fences beginning with `$` are **template fragments**, not Python programs.
Compile their exact text with `Template`, supplying the sample data below as
`globals` unless the fragment declares arguments. Inline `#` annotations on
ordinary output lines are literal template text; `$#` starts a template comment.
Blank lines within an indented block are part of that block's output.

Fragment sample data used by the executable reference tests:

| Fragment | Explicit sample data / call |
| --- | --- |
| Syntax Expressions | `varname="V"`, object with `attribute="A"` and `method()` returning an object with `attr="M"`, `list=["L"]`, `func` summing its positional numbers, `x=1`, `y=2`, `items=["a", "b"]` |
| If Statements | `condition=False`, `other_condition=True` |
| For Loops | `items=["a", "b"]` |
| While Loops | `condition=False` (zero-iteration syntax smoke only; a real repeating loop must make progress toward termination) |
| Assignments (both) | `value=7` |
| Function Definitions | `default="B"`, call with `"A"` |
| Variables Declaration | `value=7`; the second declaration overwrites the result attribute |
| Structure: Basic Template | call with `"Ada"` |
| Structure: Template with Control Structures | call with `["a", "b"]` |
| Structure: Template with Variables | no input |
| Reference: Variables | declared `name` and `expression`, both `"<b>"`; test with an HTML filename/filter |
| Reference: Expressions | function summing its positional numbers, `obj.attr="A"`, `list=["L"]`, `dict={"key": "D"}`, `items=["a", "b"]` |
| Reference: Control Structures | `condition=False`, `items=["a", "b"]`; the while arm is not entered |
| Comments | no input |
| `$def with (...)` directive | call with `"Ada"`, leaving `age=25` |
| `$var name: value` directive | no input |
| Simple-statement directive | `items=iter([None, "stop", "after"])`; break leaves `"after"` unconsumed |

Python recipes below include their own imports and owned sample files. Constructor
fences and the `STATEMENT_NODES` class-name table are **signature/reference only**,
not standalone recipes. The candidate-name list is a literal reference checked
against the actual constant. The diagnostic doctest runner intentionally returns
nonzero for the historical failures described there.

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

`length`, `last`, `revindex` and `revindex0` need a sized input (`len(seq)`).
When `len` raises, the current implementation uses `length=0`, not lookahead:
for a two-item iterator `last` is `False, False`, `revindex` is `0, -1`, and
`revindex0` is `-1, -2`. Forward indices, first/parity helpers still work.
Materialize a finite iterator with `list(...)` before passing it when reverse/end
information is required; this consumes the iterator and uses memory proportional
to its size. `enumerate(items)` is also unsized on Python 3.

#### While Loops

```python
$while condition:
    content
```

#### Code Blocks

`$code:` supports local calculations and function definitions, but imports in
trusted template source are still rejected by `SafeVisitor`. Import in application
Python and pass a deliberately selected callable through `globals` or an argument.
Such callables retain their application capabilities; this is not a sandbox.

```python
from math import sqrt
from web.template import Template

template = Template("""$code:
    def helper(x):
        return root(x) * 2
$helper(9)
""", globals={"root": sqrt})
result = template()
assert str(result) == "6.0\n"
```

### Assignments

Template fragment; sample global: `value=7`. The space after `$` makes a
local Python assignment. `$var a:` instead stores multiline text on the result;
inside the template read it as `self.a` (outside as `result.a`).

```python
$ a = value
$a
$var a:
    content
$self.a
```

### Function Definitions

The argument declaration must be the very first line, with **no final colon**.
This template fragment uses the sample global `default="B"`; call with `"A"`
for `arg1`. Indentation in ordinary text is preserved.

```python
$def with (arg1, arg2=default)
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

<h1>$self.title</h1>
$self.content
```

## Classes

### `Parser`

Base parser class that converts template text into a parse tree.

#### Methods

##### `parse(text, name="<template>")`

Parses template text and returns a `DefwithNode` representing the parse tree.

##### `read_defwith(text)`

Returns `(declaration, remaining_text)` from the beginning of the text. The
declaration omits `$` and is stripped; if absent it is `""` and text is unchanged.

##### `read_section(text)`

Returns `(section_node, remaining_text)`. Sections can be blocks, assignments,
variable declarations, simple statements or lines.

##### `read_suite(text)`

Reads multiple sections until end of text, returning a `SuiteNode`.

##### `readline(text)`

Returns `(LineNode, remaining_text)`. A terminal `\` suppresses that line's
output newline; the remaining input is returned separately, not joined to it.

##### `read_node(text)`

Returns `(node, remaining_text)` for a text or expression node.

##### `read_text(text)`

Returns `(TextNode, remaining_text)`, stopping before the next `$`.

##### `read_expr(text, escape=True)`

Returns `(ExpressionNode, remaining_text)`, **not** a node alone. Pass text
after the `$` marker; the parser need not consume the whole input.

```python
from web.template import Parser, ExpressionNode

node, rest = Parser().read_expr("name and rest", escape=False)
assert isinstance(node, ExpressionNode)
assert node.value == "name" and node.escape is False
assert rest == " and rest"
```

##### `read_assignment(text)`

Returns `(AssignmentNode, remaining_text)`; pass the assignment after `$`.

##### `read_block_section(text, begin_indent="")`

Returns `(block_node, remaining_text)` with indentation handling; pass the
statement after `$`. The class depends on the keyword (for example `IfNode`).
Related consumers: `read_var` returns `(VarNode, rest)`, `read_keyword` returns
`(StatementNode, rest)`, and `read_statement` / `read_indented_block` return two
strings. In contrast, `read_suite` consumes all input and returns just `SuiteNode`.

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

Wrapper for for loop expressions; proxies attributes of the active
`ForLoopContext`. After normal exhaustion of the outer loop, helper access
raises `AttributeError`. Nested, normally exhausted loops restore their parent.

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
- `length` - `len(seq)`, or `0` when obtaining the length raises; **not** a count of yielded elements

See the [sized/unsized limitation](#for-loops) for `last` and reverse indices.
The outermost context has `parent=None`; nested contexts refer to the actual
outer context. These descriptions concern normal exhaustion, not a guarantee
of cleanup after an interrupted iterator.

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
- `normalize_text(text)` - Normalizes CRLF/CR to LF, expands tabs, appends a missing final newline, converts legacy `\$` to `$$`, and strips only the leading legacy string `"\xef\xbb\xbf"` (not Unicode U+FEFF)
- `generate_code(text, filename, parser=None)` - Generates Python code from template
- `compile_template(template_string, filename)` - Compiles template to executable code

##### Text normalization and UTF-8 BOM

**Pinned limitation, not fixed here:** a real Unicode BOM (`U+FEFF`) remains in
the text. `Render` reads files with `encoding="utf-8"`, so a UTF-8 BOM becomes
U+FEFF, can appear in rendered output, and prevents an initial `$def with` from
being recognized (a BOM-prefixed argument declaration raises `SyntaxError`).
The removed three-character legacy string is a mojibake sequence, not U+FEFF.
Prefer UTF-8 templates saved **without** a BOM. When explicitly loading a file
in application Python, `utf-8-sig` is a bounded workaround, not a Render fix:

```python
from pathlib import Path
from tempfile import TemporaryDirectory
from web.template import Template, Render

assert Template.normalize_text("\ufeffHello") == "\ufeffHello\n"
assert Template.normalize_text("\xef\xbb\xbfHello") == "Hello\n"
with TemporaryDirectory() as directory:
    root = Path(directory)
    path = root / "hello.txt"
    path.write_bytes(b"\xef\xbb\xbfHello")
    assert str(Render(directory, cache=False).hello()) == "\ufeffHello\n"
    clean = Template(path.read_text(encoding="utf-8-sig"))
    assert str(clean()) == "Hello\n"
    path.write_bytes(b"\xef\xbb\xbf$def with (name)\nHello $name!")
    clean = Template(path.read_text(encoding="utf-8-sig"))
    assert str(clean("World")) == "Hello World!\n"
assert not root.exists()
```

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
- `__len__()` - Returns the number of mapping items, including `__body__` (not the body character count); a new result has length 1
- `__iter__()` - Iterates over keys

### Functions

#### `splitline(text)`

Splits text at the first newline.

```python
from web.template import splitline

assert splitline('foo\nbar') == ('foo\n', 'bar')
assert splitline('foo') == ('foo', '')
assert splitline('') == ('', '')
```

#### `compile_templates(root)`

Compiles all templates in a directory to Python code.

Creates `__init__.py` files with compiled templates for faster loading.

#### `frender(path, **keywords)`

Creates a template from a file path.

```python
from pathlib import Path
from tempfile import TemporaryDirectory
from web.template import frender

with TemporaryDirectory() as directory:
    root = Path(directory)
    path = root / 'page.html'
    path.write_text('$def with (name)\n<p>$name</p>', encoding='utf-8')
    template = frender(str(path))
    assert str(template('<World>')) == '<p>&lt;World&gt;</p>\n'
assert not root.exists()
```

#### `test()`

`web.template.test()` is a no-op function returning `None`; its **docstring**
contains examples, but calling it runs none of them. To run only this module's
doctests and give automation a nonzero exit when they fail, save and run this
standalone Python program (with this checkout importable):

```python
import doctest
import importlib

module = importlib.import_module("web.template")
result = doctest.testmod(module)
print(result)
raise SystemExit(1 if result.failed else 0)
```

This is a diagnostic runner, **not a green quickstart**. On the tested Python
3.13 snapshot it attempts 124 examples and reports 60 failures (exit 1).
Historical expected `u'...'` representations, the `TestResult.__repr__` helper
returning body text rather than `repr(body)`, old exception wording, and the
malformed `python_lookahead('else:')` expected text need separate source-doctest
maintenance. `TemplateResult` and `read_var` repr expectations are also stale.
There is additionally a real `date.strftime(...)` failure (`KeyError:
'__import__'`) under the restricted mapping, and a historical `\$` literal emits
`SyntaxWarning`; the runner preserves both diagnostics. Format dates in trusted
application Python and pass the resulting text rather than adding `__import__`
to template builtins. This limitation needs separate source investigation.
Do not treat these failures as repaired here or run unrelated database doctests.
The module's `__main__` calls `doctest.testmod()` without propagating its result
as the process exit code; prefer the explicit exit check above for automation.

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

Legacy candidate-name list, **not** the runtime allowlist. The constant contains:

```python
[
    "dict", "enumerate", "float", "int", "bool",
    "list", "long", "reversed", "set", "slice", "tuple", "xrange",
    "abs", "all", "any", "callable", "chr", "cmp",
    "divmod", "filter", "hex", "id", "isinstance",
    "iter", "len", "max", "min", "oct", "ord",
    "pow", "range", "round", "True", "False", "None",
]
```

#### `TEMPLATE_BUILTINS`

Actual default mapping: candidates present in the interpreter's `builtins`.
On the tested Python 3 runtime, `long`, `xrange` and `cmp` are absent; use
`int` and `range` instead of the Python 2 names. `__import__` is in neither
constant, and ordinary dunder-name expressions are rejected by `SafeVisitor`.
`True`, `False` and `None` are constants, not functions. Names such as `str` and
`sorted` are not in this default mapping either: pass required trusted helpers
explicitly via `globals`/arguments. `builtins={}` replaces the default mapping.
This is Python 3 characterization, not a claim of Python 2 support or a complete
security boundary; see [Security Features](#security-features).

#### `ALLOWED_AST_NODES`

List of allowed AST node types for security validation.

## Usage Examples

The standalone Python recipes below and in [Security Features](#security-features)
are executed from their Markdown bytes. Syntax fragments use the explicit sample
data listed above; constructor signatures and class-name reference tables are not
standalone programs. Runtime characterizations of restricted builtins, unsized
loops, BOM handling and historical doctest failures are not runtime repairs.
Never infer HTML escaping from HTML-shaped text; select the appropriate filter.

### Basic Template

```python
from web.template import Template

template = Template("$def with (name)\nHello $name!")
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
from types import SimpleNamespace
from web.template import Template

template = Template("""$def with (user, items)
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
""", filename="page.html")
result = template(SimpleNamespace(name="Ada"), ["one"])
assert "<h1>Welcome, Ada!</h1>" in str(result)
assert "<h1>Welcome, Guest</h1>" in str(template(None, []))
```

### Rendering from Directory

The directory and sample files are created here; no preexisting project is
required. Real applications normally keep their trusted template files in source
control rather than rebuilding the directory per render.

```python
from pathlib import Path
from tempfile import TemporaryDirectory
from web.template import Render

with TemporaryDirectory() as directory:
    root = Path(directory)
    (root / 'index.html').write_text('Welcome', encoding='utf-8')
    (root / 'page.html').write_text('$def with (name)\n<h1>$name</h1>', encoding='utf-8')
    render = Render(directory, cache=False)
    assert str(render.index()) == 'Welcome\n'
    assert str(render.page(name='About')) == '<h1>About</h1>\n'
assert not root.exists()
```

### Using Base Templates

```python
from pathlib import Path
from tempfile import TemporaryDirectory
from web.template import Render

with TemporaryDirectory() as directory:
    root = Path(directory)
    (root / 'layout.html').write_text('$def with (page)\n<main>$:page</main>', encoding='utf-8')
    (root / 'page.html').write_text('<p>About</p>', encoding='utf-8')
    render = Render(directory, base='layout', cache=False)
    assert str(render.page()) == '<main><p>About</p>\n</main>\n'
assert not root.exists()
```

The base receives the rendered `TemplateResult`. `$:page` deliberately inserts
trusted markup from the inner template; it must not be arbitrary untrusted HTML.

### Template with Functions

```python
from web.template import Template

template = Template("""$def with (items)
$def format_item(item):
    <strong>$item</strong>

<ul>
$for item in items:
    <li>$:format_item(item)</li>
</ul>
""", filename="page.html")
result = template(["one", "<two>"])
assert "<strong>&lt;two&gt;</strong>" in str(result)
```

### Template with Variables

```python
from web.template import Template

template = Template("""
$var title: My Website
$var author: John Doe

<html>
<head>
    <title>$self.title</title>
</head>
<body>
    <p>By $self.author</p>
</body>
</html>
""")

result = template()
print(result.title)   # My Website
print(result.author)  # John Doe
```

`$var` stores result attributes, not Python locals: use `self.title` and
`self.author` inside the template and `result.title` / `result.author` afterward.
For dynamic HTML values select an HTML filename/filter; plain `Template` here
has no default HTML filter.

### Using Loop Helpers

`range(5)` is sized on Python 3, so end/reverse helpers have useful values.

```python
from web.template import Template

template = Template("""
$for i in range(5):
    Index: $loop.index
    Zero-based: $loop.index0
    First: $loop.first
    Last: $loop.last
    Parity: $loop.parity
    <br>
""")
result = template()
assert str(result).count("Last: True") == 1
```

### Nested Loops

Blocks end by dedenting, not with `$end` (which would interpolate an ordinary
name `end`). Declare both input sequences; `loop.parent` is the outer context.

```python
from web.template import Template

template = Template("""$def with (rows, cols)
$for row in rows:
    Row $loop.index
    $for col in cols:
        Column $loop.index (parent: $loop.parent.index)
""")
result = template(["r1", "r2"], ["c1", "c2"])
assert "Column 2 (parent: 2)" in str(result)
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
Source hardening is tracked separately in
[web#30](https://git.home.arpa/mosaic-ai/web/issues/30); rejection of these writes
and preservation of the existing restrictions are not implemented here.

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

The default environment exposes the runtime [TEMPLATE_BUILTINS](#template_builtins)
mapping, not every legacy candidate name. This reduces available names but is not
a security boundary for untrusted templates or supplied callables.
Application-provided globals, arguments and custom builtins affect capabilities.

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

Template fragment; sample global: `value=7`. Local assignment and multiline
result attributes are different operations:

```python
$ a = value
$a
$var a:
    content
$self.a
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

Defines Python code that doesn't directly produce template output. Imports belong
in application Python, not inside `$code:`. Here the trusted function is an argument:

```python
from math import sqrt
from web.template import Template

template = Template("""$def with (root)
$code:
    def helper(x):
        return root(x) * 2
$helper(9)
""")
result = template(sqrt)
assert str(result) == "6.0\n"
```

### `$pass`, `$break`, `$continue`, `$return`

Simple statements for control flow.

```python
$for item in items:
    $if not item:
        $pass
    $if item == 'stop':
        $break
```
