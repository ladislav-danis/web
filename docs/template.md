# Web Template Documentation

This document describes the template engine implemented in `web/template.py`, which provides a simple and elegant templating system for web.py applications.

## Overview

The template module implements a flexible templating system that allows developers to separate presentation logic from application logic. Templates are written in a simple syntax that supports variables, expressions, control structures, and custom functions while maintaining security through AST validation.

## Core Concepts

### Template Syntax
Templates use a simple syntax with the following elements:
- `$def with (...)` - Defines template parameters
- `$var name: value` - Declares template variables
- `$expression` - Inserts evaluated Python expressions
- `$:expression` - Inserts escaped expressions (HTML safe)
- `$statement` - Executes Python statements
- Control structures like `$if`, `$for`, `$while`

### Template Structure
Templates are parsed into an Abstract Syntax Tree (AST) and compiled to Python code for execution. The system ensures that only safe operations can be performed in templates.

## Classes

### `Parser`
The main parser class that converts template text into parse trees.

#### Methods
- `parse(text, name="<template>")`: Parses template text into a parse tree
- `read_defwith(text)`: Reads the template definition section
- `read_section(text)`: Reads one section from text
- `read_var(text)`: Reads variable declarations
- `read_suite(text)`: Reads multiple sections
- `readline(text)`: Reads a line of text with expressions
- `read_node(text)`: Reads a single node from text
- `read_text(text)`: Reads text nodes
- `read_keyword(text)`: Reads keyword statements
- `read_expr(text, escape=True)`: Reads Python expressions
- `read_assignment(text)`: Reads assignment statements
- `python_lookahead(text)`: Returns first Python token
- `python_tokens(text)`: Returns list of Python tokens
- `read_indented_block(text, indent)`: Reads indented blocks
- `read_statement(text)`: Reads Python statements
- `read_block_section(text, begin_indent="")`: Reads block sections
- `create_block_node(keyword, stmt, block, begin_indent)`: Creates block nodes

### `PythonTokenizer`
Utility class for tokenizing Python code.

#### Methods
- `consume_till(delim)`: Consumes tokens until delimiter
- `__next__()`: Returns next token

### Node Classes

#### `DefwithNode`
Represents the template definition section.

#### `TextNode`
Represents literal text in templates.

#### `ExpressionNode`
Represents Python expressions in templates.

#### `AssignmentNode`
Represents assignment statements in templates.

#### `LineNode`
Represents a line of content with multiple nodes.

#### `BlockNode`
Base class for block structures like loops and conditionals.

#### `ForNode`
Represents `$for` loop blocks.

#### `CodeNode`
Represents `$code` blocks.

#### `StatementNode`
Represents statement blocks.

#### `IfNode`
Represents `$if` conditional blocks.

#### `ElseNode`
Represents `$else` blocks.

#### `ElifNode`
Represents `$elif` blocks.

#### `DefNode`
Represents `$def` function definitions.

#### `VarNode`
Represents variable declarations.

#### `SuiteNode`
Represents a collection of sections.

### Template Execution Classes

#### `ForLoop`
Wrapper for loop context with helper properties.

#### `ForLoopContext`
Stackable context for nested loops.

#### `BaseTemplate`
Base class for template execution.

#### `Template`
Main template class that handles compilation and execution.

#### `CompiledTemplate`
Template that uses pre-compiled functions.

#### `Render`
Class for rendering templates from directories.

#### `GAE_Render`
Specialized renderer for Google App Engine.

### Security Classes

#### `SafeVisitor`
AST visitor that validates template safety.

#### `TemplateResult`
Dictionary-like object for storing template output.

## Functions

### `splitline(text)`
Splits text at the first newline character.

### `compile_templates(root)`
Compiles all templates in a directory to Python code.

### `frender(path, **keywords)`
Creates a template from a file path.

### `test()`
Runs doctests for the template module.

## Constants

### `STATEMENT_NODES`
Dictionary mapping statement keywords to node classes.

### `KEYWORDS`
List of reserved keywords.

### `TEMPLATE_BUILTIN_NAMES`
List of allowed built-in names.

### `TEMPLATE_BUILTINS`
Dictionary of allowed built-ins.

### `ALLOWED_AST_NODES`
List of AST node types allowed in templates.

## Usage Examples

### Basic Template
```python
from web import template

# Create a simple template
tmpl = template.Template('$def with (name)\nHello $name!')
result = tmpl('World')
print(result)  # Output: Hello World!\n
```

### Template with Variables
```python
# Template with variable declarations
tmpl = template.Template('''
$var title: My Page
$var items: ['apple', 'banana', 'cherry']

<h1>$title</h1>
<ul>
$for item in items:
    <li>$item</li>
</ul>
''')

result = tmpl()
```

### Template with Control Structures
```python
# Template with conditionals and loops
tmpl = template.Template('''
$if items:
    <ul>
    $for item in items:
        <li>$item</li>
    </ul>
$else:
    <p>No items found.</p>
''')

result = tmpl(items=['apple', 'banana'])
```

### Rendering from Directory
```python
# Using Render class to load templates from directory
render = template.Render('templates')
page = render.index()
```

## Security Features

The template system includes several security measures:
1. AST validation to prevent dangerous operations
2. Restricted built-in functions
3. HTML escaping by default for expressions
4. Safe evaluation of template code

## Template Syntax Reference

### Variables
```python
# Variable declaration
$var name: value
$var name = value

# Variable usage
$name
```

### Expressions
```python
# Unescaped expression
$name

# Escaped expression (HTML safe)
$:name

# Expression with parentheses
$(name.upper())
${name.upper()}
```

### Control Structures
```python
# If statements
$if condition:
    content

# If-elif-else
$if condition1:
    content1
$elif condition2:
    content2
$else:
    content3

# For loops
$for item in items:
    $item

# While loops
$while condition:
    content
```

### Assignments
```python
$a = 1
$b = [1, 2, 3]
$c = func()
```

### Comments
```python
$# This is a comment
```

## Template Directives

### `$def with (...)`
Defines template parameters.

### `$var name: value`
Declares template variables.

### `$code:`
Allows raw Python code execution.

### `$pass`, `$break`, `$continue`, `$return`
Control flow statements.
