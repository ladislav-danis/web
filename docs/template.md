# Web Template Documentation

## Overview

`web.template` is a simple, elegant templating system that compiles templates to Python code for efficient execution. It provides a clean syntax for generating dynamic content while maintaining security through AST-based validation.

### Design Principles

- **Template string is split into tokens** and combined into nodes
- **Parse tree** consists of text nodes, expression nodes, and block nodes (for loops, if statements, etc.)
- Each node emits Python code strings
- **Root node** emits Python code that is validated for safe execution and executed in the given environment
- **Line-to-line matching** between template and generated code for accurate error reporting

## Template Syntax

### Basic Syntax

Templates use `$` as the escape character for dynamic content:

| Syntax | Description |
|--------|-------------|
| `$varname` | Output variable value (HTML-escaped by default) |
| `$:varname` | Output variable value without HTML escaping |
| `$(expression)` | Output expression result (HTML-escaped) |
| `${expression}` | Output expression result (HTML-escaped, alternative syntax) |
| `$$` | Literal dollar sign `$` |
| `$# comment` | Comment (not rendered in output) |

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
- `escape` - Whether to HTML-escape the output
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
- `filename` - Filename for error reporting
- `filter` - Function to apply to output (e.g., HTML escaping)
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

AST visitor that validates template code for security.

Checks for:
- Restricted AST nodes (only nodes in `ALLOWED_AST_NODES` are allowed)
- Access to restricted attributes (starting with `_`, `func_`, `im_`)
- Assignment to attributes
- Access to names starting with `__`

##### Methods

- `walk(tree, filename)` - Validates the AST and raises `SecurityError` if unsafe
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

### Basic Template

```python
from web.template import Template

template = Template("Hello $name!")
result = template(name="World")
print(result)  # Hello World!
```

### Template with Variables

```python
template = Template("""
$def with (title, items)
<html>
<head><title>$title</title></head>
<body>
$for item in items:
    <p>$item</p>
</body>
</html>
""")

html = template(title="My Page", items=["Item 1", "Item 2"])
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

Templates are validated using AST walking to prevent unsafe operations:

- Only predefined AST nodes are allowed
- Access to attributes starting with `_` is denied
- Assignment to attributes is denied
- Access to names starting with `__` is denied

### Safe Built-ins

Templates have access to a restricted set of built-in functions, preventing access to potentially dangerous functions.

### HTML Escaping

By default, all output is HTML-escaped to prevent XSS attacks. Use `$:var` to output unescaped content when needed.

## Template Syntax Reference

### Variables

```python
$name              # Output variable (escaped)
$:name             # Output variable (unescaped)
${name}            # Output variable (escaped, alternative syntax)
$(expression)      # Output expression (escaped)
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
