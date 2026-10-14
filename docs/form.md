# Web Form Documentation

## Overview

The `web.form` module provides a powerful system for creating and validating HTML forms in web.py applications. It supports various input types, validation, and rendering options.

## Classes

### `Form`

The `Form` class represents an HTML form containing multiple input elements.

#### Constructor

```python
Form(*inputs, validators=[])
```

**Parameters:**

- `inputs` - Variable number of input objects (Textbox, Password, Dropdown, etc.)
- `validators` - Optional list of form-level validators

**Attributes:**

- `inputs` - List of input objects in the form
- `valid` - Boolean indicating if the form is valid
- `note` - Error message for form-level validation errors

#### Methods

##### `render()`

Renders the form as an HTML table.

```python
>>> f = Form(Textbox("x"))
>>> f.render()
u'<table>\n    <tr><th><label for="x">x</label></th><td><input id="x" name="x" type="text"/></td></tr>\n</table>'
```

##### `render_css()`

Renders the form with CSS-friendly output (no table structure). The label and
input are adjacent; each input ends with a newline. Python 3 displays:

```python
>>> from web import form
>>> f = form.Form(form.Textbox("x"))
>>> f.render_css()
'<label for="x">x</label><input id="x" name="x" type="text"/>\n'
```

##### `validates(source=None, _validate=True, **kw)`

Validates the form against input data.

**Parameters:**

- `source` - Input data (dict, web.input(), or similar)
- `_validate` - If True, performs validation; if False, only sets values
- `**kw` - Keyword arguments for input values

**Returns:** `True` if valid, `False` otherwise

##### `_validate(value)`

Internal method used by `validates` to perform form-level validation using registered validators.

##### `fill(source=None, **kw)`

Pre-fills form values without validation.

**Parameters:**

- `source` - Input data to populate form
- `**kw` - Keyword arguments for input values

**Returns:** `True` (always, since validation is skipped)

##### `__getitem__(i)`

Access an input by name.

```python
>>> f = Form(Textbox("x"))
>>> f["x"]
<Textbox object>
```

##### `__getattr__(name)`

Access an input by attribute.

```python
>>> f = Form(Textbox("x"))
>>> f.x
<Textbox object>
```

##### `get(i, default=None)`

Get an input by name with a default value.

##### `d` (property)

Returns a storage object containing all form values.

```python
>>> f = Form(Textbox("x"))
>>> f.fill(x="42")
>>> f.d
Storage({'x': '42'})
```

#### Usage

Run inside a request handler; `f.validates()` reads `web.input()`. This minimal
example has no field validators. See the validation examples below for required
fields and other server-side checks.

```python
from web import form

f = form.Form(
    form.Textbox("username", description="Username"),
    form.Password("password", description="Password"),
    form.Button("submit", html="Login")
)

if f.validates():
    # Process form data
    print(f.d.username)
else:
    # Display form with errors
    print(f.render())
```

---

### `Input`

Base class for all input types.

#### Constructor

```python
Input(name, *validators, **attrs)
```

**Parameters:**

- `name` - Name attribute of the input
- `validators` - Optional validators for this input
- `attrs` - Additional HTML attributes

**Keyword Arguments:**

- `description` - Label text (defaults to `name`)
- `value` - Initial value
- `pre` - HTML to prepend to the input
- `post` - HTML to append to the input
- `id` - HTML id attribute (defaults to `name`)
- `class_` - CSS class (converted to `class`)

#### Methods

##### `render()`

Renders the input as HTML.

##### `validate(value)`

Validates the input value.

##### `set_value(value)`

Sets the input value.

##### `get_value()`

Gets the current input value.

##### `is_hidden()`

Returns `True` if the input is hidden.

##### `get_type()`

Returns the input type (must be implemented by subclasses).

##### `get_default_id()`

Returns the default id value.

#### Input Subclasses

##### `Textbox`

Text input field.

**Example:**

```python
Textbox("username", description="Username", value="john")
```

##### `Password`

Password input field.

**Example:**

```python
Password("password", description="Password")
```

##### `Textarea`

Multi-line text input.

**Example:**

```python
Textarea("comments", description="Comments", value="Some text")
```

##### `Dropdown`

Select dropdown input.

**Constructor:**

```python
Dropdown(name, args, *validators, **attrs)
```

**Parameters:**

- `name` - Name attribute
- `args` - List of options (strings or (value, label) tuples)
- `validators` - Optional validators
- `attrs` - Additional HTML attributes

**Example:**

```python
Dropdown("color", args=["red", "green", "blue"], value="green")
Dropdown("choice", args=[("a", "Option A"), ("b", "Option B")])
```

##### `GroupedDropdown`

Grouped select dropdown with optgroup support.

**Constructor:**

```python
GroupedDropdown(name, args, *validators, **attrs)
```

**Parameters:**

- `name` - Name attribute
- `args` - Tuple of (group_label, options) tuples
- `validators` - Optional validators
- `attrs` - Additional HTML attributes

**Example:**

```python
from web import form

car_type = form.GroupedDropdown(
    "car_type",
    args=(
        ("Swedish Cars", ("Volvo", "Saab")),
        ("German Cars", ("Mercedes", "Audi"))
    ),
    value="Audi"
)
print(car_type.render())
```

##### `Radio`

Radio button group.

**Constructor:**

```python
Radio(name, args, *validators, **attrs)
```

**Parameters:**

- `name` - Name attribute
- `args` - List of options (strings or (value, label) tuples)
- `validators` - Optional validators
- `attrs` - Additional HTML attributes

**Example:**

```python
Radio("gender", args=["male", "female"], value="male")
```

##### `Checkbox`

Checkbox input.

**Constructor:**

```python
Checkbox(name, *validators, **attrs)
```

**Keyword Arguments:**

- `checked` - Boolean to set initial checked state
- `value` - Value when checked

**Methods:**

- `set_value(value)` - Sets checked state based on value
- `get_value()` - Returns `True` if checked

**Example:**

```python
Checkbox("agree", value="yes", checked=True)
```

##### `Button`

HTML button.

**Constructor:**

```python
Button(name, *validators, **attrs)
```

**Keyword Arguments:**

- `value` - Button value
- `html` - HTML content inside the button

**Example:**

```python
Button("submit", html="<b>Submit</b>")
Button("action", value="save")
```

##### `Hidden`

Hidden input field.

**Methods:**

- `is_hidden()` - Returns `True`

**Example:**

```python
Hidden("token", value="abc123")
```

##### `File`

File upload input.

**Example:**

```python
File("upload", accept=".jpg,.png")
```

##### `Telephone`

Telephone input (HTML5 tel type).

**Example:**

```python
Telephone("phone", description="Phone Number")
```

##### `Email`

Email input (HTML5 email type).

**Example:**

```python
Email("email", description="Email Address")
```

##### `Date`

Date input (HTML5 date type).

**Note:** Not supported by desktop Safari, Internet Explorer, or Opera Mini.

**Example:**

```python
Date("birthdate", value="2020-04-01")
```

##### `Time`

Time input (HTML5 time type).

**Note:** Not supported by desktop Safari, Internet Explorer, or Opera Mini.

**Example:**

```python
Time("appointment", value="09:00")
```

##### `Search`

Search input (HTML5 search type).

**Example:**

```python
Search("query", description="Search", placeholder="Enter search term")
```

##### `Url`

URL input (HTML5 url type).

**Example:**

```python
Url("website", description="Website URL")
```

##### `Number`

Number input (HTML5 number type).

**Example:**

```python
Number("quantity", min="1", max="10", value="5")
```

##### `Range`

Range slider input (HTML5 range type).

**Example:**

```python
Range("volume", min="0", max="100", step="5", value="50")
```

##### `Color`

Color picker input (HTML5 color type).

**Note:** Not supported by Internet Explorer or Opera Mini.

**Example:**

```python
Color("background", value="#ffffff")
```

##### `Datalist`

Datalist input for autocomplete suggestions.

**Note:** Supported by Chrome, Firefox, Edge, and Opera. Not supported on Safari or Internet Explorer.

**Constructor:**

```python
Datalist(name, args, *validators, **kwargs)
```

**Parameters:**

- `name` - Name attribute
- `args` - List of options (strings or (label, value) tuples)
- `validators` - Optional validators
- `kwargs` - Additional HTML attributes

**Example:**

```python
Datalist("browser", args=["Chrome", "Firefox", "Safari"])
Datalist("choice", args=[("a", "Option A"), ("b", "Option B")])
```

---

### `AttributeList`

Dictionary subclass for managing HTML attributes.

#### Methods

- `copy()` - Returns a copy of the attribute list
- `__str__()` - Returns HTML attribute string
- `__repr__()` - Returns representation string

**Example:**

```python
attrs = AttributeList(type="text", name="x", value=20)
str(attrs)  # 'name="x" type="text" value="20"'
```

---

### `Validator`

Base class for validators.

#### Constructor

```python
Validator(msg, test, jstest=None)
```

**Parameters:**

- `msg` - Error message when validation fails
- `test` - Function that returns `True` for valid values
- `jstest` - JavaScript validation code (optional)

#### Methods

##### `valid(value)`

Validates the value using the test function.

#### Predefined Validators

##### `notnull`

Validates that the value is not empty.

```python
Textbox("name", notnull)
```

##### `regexp(pattern, msg)`

Validates the value against a regular expression.

**Constructor:**

```python
regexp(pattern, msg)
```

**Parameters:**

- `pattern` - Regular expression pattern
- `msg` - Error message when validation fails

**Example:**

```python
import re
Textbox("username", regexp(r"^[a-z0-9_]+$", "Username must be alphanumeric"))
```

---

## Functions

### `attrget(obj, attr, value=None)`

Retrieves an attribute from an object, supporting multiple object types.

**Parameters:**

- `obj` - Object to retrieve attribute from
- `attr` - Attribute name
- `value` - Default value if attribute not found

**Returns:** Attribute value or default

**Usage:**

```python
# Works with dicts, objects, and other types
attrget({"key": "value"}, "key")  # "value"
attrget(obj, "attribute")  # obj.attribute
```

---

## Usage Examples

### Basic Form Creation

```python
from web import form

f = form.Form(
    form.Textbox("username", description="Username"),
    form.Password("password", description="Password"),
    form.Button("submit", html="Login")
)

print(f.render())
```

### Form Validation

Run this block inside a request handler. Required-field checks are server-side;
an HTML input type or attribute alone does not register a validator.

```python
from web import form

f = form.Form(
    form.Textbox("username", form.notnull),
    form.Password("password", form.notnull)
)
if f.validates():
    # Form is valid
    username = f.d.username
    password = f.d.password
else:
    # Form has errors
    print(f.render())
```

### Custom Validation

Field validators are positional arguments before keyword attributes, unlike
`Form(validators=[...])`. A field's `validators=` keyword is just an HTML
attribute; it does **not** register validation. Wrap predicates in `Validator`.
This example accepts a string of ASCII digits representing an age from 0 to 150.
The type guard runs before `regexp`, which expects a string (not `None`).

```python
from web import form


def is_valid_age(value):
    try:
        return 0 <= int(value) <= 150
    except (TypeError, ValueError):
        return False


f = form.Form(
    form.Textbox(
        "age",
        form.Validator("Must be text", lambda value: isinstance(value, str)),
        form.regexp(r"\A[0-9]+\Z", "Must be a number"),
        form.Validator("Age must be between 0 and 150", is_valid_age),
        description="Age",
    )
)
```

### Form with Multiple Inputs

Validators such as `notnull` and `regexp` precede keyword attributes. The
password requires at least six characters; `notnull` rejects missing/empty
values before the string regexp runs. `Email` selects an HTML input type; it
does not by itself validate an address on the server.

```python
from web import form

f = form.Form(
    form.Textbox("username", form.notnull, description="Username"),
    form.Email("email", description="Email"),
    form.Password("password", form.notnull,
                  form.regexp(r".{6,}", "At least 6 characters"),
                  description="Password"),
    form.Checkbox("agree", description="I agree to the terms"),
    form.Button("submit", html="Register")
)
```

### Form with Form-Level Validators

`Form(validators=[...])` requires validator objects (with `valid` and `msg`),
not bare functions. They receive the **whole source** passed to `validates`,
including extra keys, not `f.d` or a single field. They run only after all
field validators pass. The example uses mapping access, so either a nonempty
plain dict or `web.storage` from `web.input()` works. Attribute access such as
`values.password` would require storage (or another attribute-bearing object),
not a plain dict. `validates()` without a truthy source or keyword values reads
`web.input()` and therefore needs an active request.

```python
from web import form


def passwords_match(values):
    return values["password"] == values["confirm_password"]


f = form.Form(
    form.Password("password", form.notnull, description="Password"),
    form.Password("confirm_password", form.notnull, description="Confirm Password"),
    validators=[form.Validator("Passwords must match", passwords_match)]
)
```

### Using Form with web.input()

Run inside a request handler to read its actual input mapping.

```python
import web
from web import form

f = form.Form(form.Textbox("name", form.notnull))
if f.validates(web.input()):
    # Process validated input
    pass
```

### Rendering Form with CSS

```python
from web import form

f = form.Form(form.Textbox("name"))
print(f.render_css())  # No table structure
```

### Accessing Form Values

```python
from web import form

f = form.Form(form.Textbox("username"), form.Textbox("email"))
f.fill(username="john", email="john@example.com")

# Access via attribute
print(f.username.name)  # "username"

# Access via dictionary-style
print(f["email"].name)  # "email"

# Get all values
print(f.d)  # Storage({'username': 'john', 'email': 'john@example.com'})
```

### Pre-filling Form Data

```python
from web import form

f = form.Form(form.Textbox("name"), form.Textbox("email"))
f.fill(name="John", email="john@example.com")
print(f.render())  # Values pre-filled in inputs
```

### Conditional Form Rendering

Run this block inside a request handler: `web.input()` reads that request.
The regexp is a **field** validator receiving the email string, not the whole
input mapping. This is a simple lowercase `.com` example, not complete email
address validation. Missing/empty email is rejected before applying the regexp.
Without a truthy `submit` parameter the form is rendered without validation.

```python
import web
from web import form

f = form.Form(
    form.Textbox("email", form.notnull,
                 form.regexp(r"\A[^@\s]+@[^@\s]+\.com\Z", "Must be a .com email"),
                 description="Email")
)

source = web.input()
if source.get("submit"):
    if f.validates(source):
        # Process form
        pass
    else:
        # Show form with errors
        pass
else:
    # Show empty form
    pass

print(f.render())
```

## Source doctests and module CLI

The Python 3 source docstrings in `web.form` execute 45 examples across 22
nonempty doctest cases. Their expected string representations no longer carry
the Python 2 `u` prefix; the rendered HTML bytes, attribute ordering, escaping
and form validation behavior are unchanged. This source-doctest result does not
certify every illustrative snippet on this reference page; older displayed
representations above are retained here.

With this checkout's `web` package importable, `python -m web.form` runs the
module's doctests and returns exit 0 on success or exit 1 on doctest failure.
This intentionally replaces the old always-zero status on reported failures.
An ordinary positional argument such as `Form` is ignored, not a class selector;
it still runs all 45 examples. The entry point calls `doctest.testmod()`, not
`web.test.main()`. Importing the package can produce a runpy preimport
`RuntimeWarning`; it is distinct from doctest failure.

Inspect the real result and nonempty execution count rather than treating exit
0 alone as coverage. This policy applies to the form module entry point, not
to custom scripts that discard the result returned by `web.test.runTests`.
