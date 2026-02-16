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

Renders the form with CSS-friendly output (no table structure).

```python
>>> f = Form(Textbox("x"))
>>> f.render_css()
u'<label for="x">x</label>\n<input id="x" name="x" type="text"/>\n'
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

```python
from web import form

f = Form(
    Textbox("username", description="Username"),
    Password("password", description="Password"),
    Button("submit", html="Login")
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
GroupedDropdown(
    "car_type",
    args=(
        ("Swedish Cars", ("Volvo", "Saab")),
        ("German Cars", ("Mercedes", "Audi"))
    ),
    value="Audi"
)
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

f = Form(
    Textbox("username", description="Username"),
    Password("password", description="Password"),
    Button("submit", html="Login")
)

print(f.render())
```

### Form Validation

```python
if f.validates():
    # Form is valid
    username = f.d.username
    password = f.d.password
else:
    # Form has errors
    print(f.render())
```

### Custom Validation

```python
def is_valid_age(value):
    try:
        age = int(value)
        return age >= 0 and age <= 150
    except:
        return False

f = Form(
    Textbox("age", 
            description="Age",
            validators=[regexp(r"^\d+$", "Must be a number"),
                       is_valid_age])
)
```

### Form with Multiple Inputs

```python
f = Form(
    Textbox("username", description="Username", notnull),
    Email("email", description="Email"),
    Password("password", description="Password", validators=[regexp(".{6,}", "At least 6 characters")]),
    Checkbox("agree", description="I agree to the terms"),
    Button("submit", html="Register")
)
```

### Form with Form-Level Validators

```python
def passwords_match(values):
    return values.password == values.confirm_password

f = Form(
    Password("password", description="Password"),
    Password("confirm_password", description="Confirm Password"),
    validators=[passwords_match]
)
```

### Using Form with web.input()

```python
f = Form(Textbox("name"))
if f.validates(web.input()):
    # Process validated input
    pass
```

### Rendering Form with CSS

```python
f = Form(Textbox("name"))
print(f.render_css())  # No table structure
```

### Accessing Form Values

```python
f = Form(Textbox("username"), Textbox("email"))
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
f = Form(Textbox("name"), Textbox("email"))
f.fill(name="John", email="john@example.com")
print(f.render())  # Values pre-filled in inputs
```

### Conditional Form Rendering

```python
f = Form(
    Textbox("email", description="Email"),
    validators=[regexp(r".+@.+\.com", "Must be a .com email")]
)

if web.input().get("submit"):
    if f.validates():
        # Process form
        pass
    else:
        # Show form with errors
        pass
else:
    # Show empty form
    pass

print(f.render())