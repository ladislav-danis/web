# Web Template Documentation
## Overview
## Core Concepts
### Template Syntax
### Template Structure
## Classes
### `Parser`
#### Methods
### `PythonTokenizer`
#### Methods
### Node Classes
#### `DefwithNode`
#### `TextNode`
#### `ExpressionNode`
#### `AssignmentNode`
#### `LineNode`
#### `BlockNode`
#### `ForNode`
#### `CodeNode`
#### `StatementNode`
#### `IfNode`
#### `ElseNode`
#### `ElifNode`
#### `DefNode`
#### `VarNode`
#### `SuiteNode`
### Template Execution Classes
#### `ForLoop`
#### `ForLoopContext`
#### `BaseTemplate`
#### `Template`
#### `CompiledTemplate`
#### `Render`
#### `GAE_Render`
### Security Classes
#### `SafeVisitor`
#### `TemplateResult`
## Functions
### `splitline(text)`
### `compile_templates(root)`
### `frender(path, **keywords)`
### `test()`
## Constants
### `STATEMENT_NODES`
### `KEYWORDS`
### `TEMPLATE_BUILTIN_NAMES`
### `TEMPLATE_BUILTINS`
### `ALLOWED_AST_NODES`
## Usage Examples
### Basic Template
### Template with Variables
### Template with Control Structures
### Rendering from Directory
## Security Features
## Template Syntax Reference
### Variables
### Expressions
### Control Structures
### Assignments
### Comments
## Template Directives
### `$def with (...)`
### `$var name: value`
### `$code:`
### `$pass`, `$break`, `$continue`, `$return`
