# Web Form Documentation

This document describes the form handling functionality in `web/form.py`, which provides a framework for creating and processing HTML forms in web.py applications.

## Overview

The form module provides classes and functions for building HTML forms, validating user input, and rendering form elements. It supports various input types including textboxes, checkboxes, dropdowns, and more, with built-in validation capabilities.

## Classes

### `Form`
Main form class that manages a collection of input fields.

#### Constructor
```python
def __init__(self, *inputs, **kw)
```

**Parameters:**
- `*inputs`: Input field instances to include in the form
- `**kw`: Additional keyword arguments including `validators` (list of form-level validators)

**Attributes:**
- `valid`: Boolean indicating if the form passed validation
- `note`: Error message from the last validation attempt

#### Methods
- `__call__(self, x=None)`: Returns a copy of the form, optionally validating with input data
- `render(self)`: Renders the form as HTML table with labels and error notes
- `render_css(self)`: Renders the form with CSS-friendly markup (without table structure)
- `rendernote(self, note)`: Renders error notes as `<strong class="wrong">note</strong>`
- `validates(self, source=None, _validate=True, **kw)`: Validates or fills form data
  - `source`: Input data (web.input(), dict, or object)
  - `_validate`: If True, validates; if False, just fills values
  - Returns `True` if validation passes, `False` otherwise
- `_validate(self, value)`: Runs custom form-level validators
- `fill(self, source=None, **kw)`: Fills form fields with data without validation (calls `validates` with `_validate=False`)
- `__getitem__(self, i)`: Gets an input field by name (raises `KeyError` if not found)
- `__getattr__(self, name)`: Gets an input field by name (raises `AttributeError` if not found)
- `get(self, i, default=None)`: Safely gets an input field by name
- `d`: Property that returns a storage object with all field values

#### Usage
```python
from web import form

# Create form fields
name = form.Textbox('name', required=True, description='Full Name')
email = form.Email('email', required=True, description='Email Address')
submit = form.Button('submit', type='submit', value='Submit')

# Create form with validators
f = form.Form(name, email, submit)

# Render form
print(f.render())

# Validate form data
if f.validates():
    # Process valid data
    name_value = f['name'].value
    email_value = f['email'].value
else:
    # Handle validation errors
    print(f.note)  # Error message
```

### `Input`
Base class for all form input elements. Type attribute must be specified when called directly.

#### Constructor
```python
def __init__(self, name, *validators, **attrs)
```

**Parameters:**
- `name`: Field name (used as HTML `name` attribute)
- `*validators`: Validation rules (instances of `Validator`)
- `**attrs`: HTML attributes for the input element

**Keyword Arguments:**
- `type`: HTML input type (required for base `Input` class)
- `description`: Field description (defaults to `name`)
- `value`: Initial field value
- `pre`: HTML to prepend to the input when rendering
- `post`: HTML to append to the input when rendering
- `id`: HTML id attribute (defaults to `name`)
- `class_`: CSS class (renamed to `class` internally)

#### Methods
- `is_hidden(self)`: Returns `True` if input is hidden (overridden by `Hidden` class)
- `get_type(self)`: Gets the HTML input type (raises `AttributeError` if not set)
- `get_default_id(self)`: Gets default ID for the input (defaults to `name`)
- `validate(self, value)`: Validates a value against validators
  - Sets `note` attribute with error message if validation fails
  - Returns `True` if valid, `False` otherwise
- `set_value(self, value)`: Sets the field's value
- `get_value(self)`: Gets the field's value
- `render(self)`: Renders the HTML input element
- `rendernote(self, note)`: Renders error notes as `<strong class="wrong">note</strong>`
- `addatts(self)`: Returns string of additional attributes with leading space

#### Input Subclasses

##### `Textbox`
Text input field (`type="text"`).

**Example:**
```python
Textbox(name='foo', value='bar').render()
# Output: u'<input id="foo" name="foo" type="text" value="bar"/>'
```

##### `Password`
Password input field (`type="password"`).

**Example:**
```python
Password(name='password', value='secret').render()
# Output: u'<input id="password" name="password" type="password" value="secret"/>'
```

##### `Textarea`
Multi-line text input field.

**Example:**
```python
Textarea(name='foo', value='bar').render()
# Output: u'<textarea id="foo" name="foo">bar</textarea>'
```

##### `Dropdown`
Select dropdown menu.

**Constructor:**
```python
Dropdown(name, args, *validators, **attrs)
```

**Parameters:**
- `name`: Field name
- `args`: List of options (strings or tuples of `(value, label)`)
- `*validators`: Validation rules
- `**attrs`: HTML attributes

**Example:**
```python
Dropdown(name='foo', args=['a', 'b', 'c'], value='b').render()
# Output: u'<select id="foo" name="foo">\n  <option value="a">a</option>\n  <option selected="selected" value="b">b</option>\n  <option value="c">c</option>\n</select>\n'

Dropdown(name='foo', args=[('a', 'aa'), ('b', 'bb'), ('c', 'cc')], value='b').render()
# Output: u'<select id="foo" name="foo">\n  <option value="a">aa</option>\n  <option selected="selected" value="b">bb</option>\n  <option value="c">cc</option>\n</select>\n'
```

##### `GroupedDropdown`
Select dropdown with grouped options using `<optgroup>`.

**Constructor:**
```python
GroupedDropdown(name, args, *validators, **attrs)
```

**Parameters:**
- `name`: Field name
- `args`: Tuple of `(group_label, options)` tuples
- `*validators`: Validation rules
- `**attrs`: HTML attributes

**Example:**
```python
GroupedDropdown(
    name='car_type',
    args=(
        ('Swedish Cars', ('Volvo', 'Saab')),
        ('German Cars', ('Mercedes', 'Audi'))
    ),
    value='Audi'
).render()
# Output: u'<select id="car_type" name="car_type">\n  <optgroup label="Swedish Cars">\n    <option value="Volvo">Volvo</option>\n    <option value="Saab">Saab</option>\n  </optgroup>\n  <optgroup label="German Cars">\n    <option value="Mercedes">Mercedes</option>\n    <option selected="selected" value="Audi">Audi</option>\n  </optgroup>\n</select>\n'
```

##### `Radio`
Radio button group.

**Constructor:**
```python
Radio(name, args, *validators, **attrs)
```

**Parameters:**
- `name`: Field name
- `args`: List of options (strings or tuples of `(value, label)`)
- `*validators`: Validation rules
- `**attrs`: HTML attributes

**Example:**
```python
Radio(name='choice', args=['A', 'B', 'C'], value='B').render()
# Output: u'<span><input checked="checked" id="choice2" name="choice" type="radio" value="B"/> B<input id="choice1" name="choice" type="radio" value="A"/> A<input id="choice3" name="choice" type="radio" value="C"/> C</span>'
```

##### `Checkbox`
Checkbox input field.

**Constructor:**
```python
Checkbox(name, *validators, **attrs)
```

**Keyword Arguments:**
- `checked`: Boolean indicating if checkbox is initially checked

**Methods:**
- `get_default_id(self)`: Returns `name_value` (with spaces replaced by underscores)
- `set_value(self, value)`: Sets checked state based on boolean value
- `get_value(self)`: Returns `True` if checked, `False` otherwise

**Example:**
```python
Checkbox('foo', value='bar', checked=True).render()
# Output: u'<input checked="checked" id="foo_bar" name="foo" type="checkbox" value="bar"/>'

Checkbox('foo', value='bar').render()
# Output: u'<input id="foo_bar" name="foo" type="checkbox" value="bar"/>'
```

##### `Button`
HTML button element.

**Constructor:**
```python
Button(name, *validators, **attrs)
```

**Keyword Arguments:**
- `value`: Button value
- `html`: HTML content inside the button (defaults to escaped name)

**Example:**
```python
Button("save").render()
# Output: u'<button id="save" name="save">save</button>'

Button("action", value="save", html="<b>Save Changes</b>").render()
# Output: u'<button id="action" name="action" value="save"><b>Save Changes</b></button>'
```

##### `Hidden`
Hidden input field (`type="hidden"`).

**Methods:**
- `is_hidden(self)`: Returns `True`

**Example:**
```python
Hidden(name='foo', value='bar').render()
# Output: u'<input id="foo" name="foo" type="hidden" value="bar"/>'
```

##### `File`
File upload input field (`type="file"`).

**Example:**
```python
File(name='f', accept=".doc,.docx,.xml").render()
# Output: u'<input accept=".doc,.docx,.xml" id="f" name="f" type="file"/>'
```

##### `Telephone`
Telephone number input field (`type="tel"`).

**Example:**
```python
Telephone(name='tel', value='55512345').render()
# Output: u'<input id="tel" name="tel" type="tel" value="55512345"/>'
```

##### `Email`
Email address input field (`type="email"`).

**Example:**
```python
Email(name='email', value='me@example.org').render()
# Output: u'<input id="email" name="email" type="email" value="me@example.org"/>'
```

##### `Date`
Date input field (`type="date"`).

**Note:** Not supported by desktop Safari, Internet Explorer, or Opera Mini.

**Example:**
```python
Date(name='date', value='2020-04-01').render()
# Output: u'<input id="date" name="date" type="date" value="2020-04-01"/>'
```

##### `Time`
Time input field (`type="time"`).

**Note:** Not supported by desktop Safari, Internet Explorer, or Opera Mini.

**Example:**
```python
Time(name='time', value='07:00').render()
# Output: u'<input id="time" name="time" type="time" value="07:00"/>'
```

##### `Search`
Search input field (`type="search"`).

**Example:**
```python
Search(name='search', value='Search').render()
# Output: u'<input id="search" name="search" type="search" value="Search"/>'

Search(name='search', value='Search', required='required', pattern='[a-z0-9]{2,30}', placeholder='Search...').render()
# Output: u'<input id="search" name="search" pattern="[a-z0-9]{2,30}" placeholder="Search..." required="required" type="search" value="Search"/>'
```

##### `Url`
URL input field (`type="url"`).

**Example:**
```python
Url(name='url', value='url').render()
# Output: u'<input id="url" name="url" type="url" value="url"/>'
```

##### `Number`
Numeric input field (`type="number"`).

**Example:**
```python
Number(name='num', min='0', max='10', step='2', value='5').render()
# Output: u'<input id="num" max="10" min="0" name="num" step="2" type="number" value="5"/>'
```

##### `Range`
Range slider input field (`type="range"`).

**Example:**
```python
Range(name='range', min='0', max='10', step='2', value='5').render()
# Output: u'<input id="range" max="10" min="0" name="range" step="2" type="range" value="5"/>'
```

##### `Color`
Color picker input field (`type="color"`).

**Note:** Not supported by Internet Explorer or Opera Mini.

**Example:**
```python
Color(name='color').render()
# Output: u'<input id="color" name="color" type="color"/>'
```

##### `Datalist`
Datalist input with autocomplete options (`<datalist>` element).

**Note:** Currently supported by Chrome, Firefox, Edge, and Opera. Not supported on Safari or Internet Explorer.

**Constructor:**
```python
Datalist(name, args, *validators, **kwargs)
```

**Parameters:**
- `name`: Field name
- `args`: List of options (strings, tuples, or lists)
- `*validators`: Validation rules
- `**kwargs`: HTML attributes

**Example:**
```python
Datalist(name='list', args=[('a', 'b'), ('c', 'd')]).render()
# Output: u'<datalist id="list" name="list"><option label="a" value="b"/><option label="c" value="d"/></datalist>'

Datalist(name='list', args=[['a', 'b'], ['c', 'd']]).render()
# Output: u'<datalist id="list" name="list"><option label="a" value="b"/><option label="c" value="d"/></datalist>'

Datalist(name='list', args=['a', 'b', 'c', 'd']).render()
# Output: u'<datalist id="list" name="list"><option value="a"/><option value="b"/><option value="c"/><option value="d"/></datalist>'
```

### `AttributeList`
Helper class for managing HTML attributes.

#### Methods
- `copy(self)`: Creates a copy of the attribute list
- `__str__(self)`: String representation with sorted attributes (e.g., `name="x" type="text"`)
- `__repr__(self)`: String representation for debugging (e.g., `<attrs: 'name="x" type="text"'>`)

**Example:**
```python
a = AttributeList(type='text', name='x', value=20)
str(a)
# Output: 'name="x" type="text" value="20"'
repr(a)
# Output: "<attrs: 'name=\"x\" type=\"text\" value=\"20\"'>"
```

### `Validator`
Base class for form validation rules.

#### Constructor
```python
def __init__(self, msg, test, jstest=None)
```

**Parameters:**
- `msg`: Error message for invalid values
- `test`: Function that tests if a value is valid
- `jstest`: Optional JavaScript validation function (not currently used)

**Methods:**
- `valid(self, value)`: Tests if a value is valid
  - Returns `False` if `test()` raises an exception
- `__deepcopy__(self, memo)`: Creates a deep copy of the validator

#### Predefined Validators

##### `notnull`
Validates that a field is not empty.

```python
notnull = Validator("Required", bool)
```

##### `regexp(pattern, msg)`
Validates against a regular expression pattern.

**Constructor:**
```python
regexp(pattern, msg)
```

**Parameters:**
- `pattern`: Regular expression pattern
- `msg`: Error message for invalid values

**Example:**
```python
email_validator = regexp(r'^[^@]+@[^@]+\.[^@]+$', 'Invalid email address')
```

## Functions

### `attrget(obj, attr, value=None)`
Safely gets an attribute from an object, handling various edge cases.

**Parameters:**
- `obj`: Object to get attribute from
- `attr`: Attribute name
- `value`: Default value if attribute not found

**Returns:**
- Attribute value if found, `value` otherwise

**Usage:**
```python
# Works with dicts
attrget({'key': 'value'}, 'key')  # Returns 'value'

# Works with objects
attrget(some_object, 'attribute')  # Returns some_object.attribute

# Works with Model objects (e.g., Google App Engine)
attrget(model_object, 'field', default='default')
```

## Usage Examples

### Basic Form Creation
```python
from web import form

# Create form fields
name = form.Textbox('name', required=True, description='Full Name')
email = form.Email('email', required=True, description='Email Address')
submit = form.Button('submit', type='submit', value='Submit')

# Create form
f = form.Form(name, email, submit)

# Render form
print(f.render())
```

### Form Validation
```python
# Validate form data
if f.validates():
    # Process valid data
    name_value = f['name'].value
    email_value = f['email'].value
else:
    # Handle validation errors
    print(f.note)  # Error message
```

### Custom Validation
```python
# Create custom validator
def is_valid_age(age):
    return age.isdigit() and 0 <= int(age) <= 150

age_validator = form.Validator("Age must be between 0 and 150", is_valid_age)
age_field = form.Textbox('age', age_validator)

# Create form with custom validator
f = form.Form(age_field)
```

### Form with Multiple Inputs
```python
# Create a more complex form
name = form.Textbox('name', required=True)
email = form.Email('email', required=True)
country = form.Dropdown('country', args=['US', 'CA', 'UK'])
newsletter = form.Checkbox('newsletter', description='Subscribe to newsletter')
submit = form.Button('submit', type='submit', value='Register')

f = form.Form(name, email, country, newsletter, submit)
```

### Form with Form-Level Validators
```python
# Create form-level validator
def validate_form(data):
    # Check that email is not the same as name
    return data.name != data.email

form_validator = form.Validator("Name and email must be different", validate_form)

f = form.Form(
    form.Textbox('name'),
    form.Email('email'),
    validators=[form_validator]
)
```

### Using Form with web.input()
```python
from web import form, webapi as web

# In a web handler
def POST(self):
    f = my_form(web.input())
    if f.validates():
        # Process valid data
        pass
    else:
        # Show form with errors
        return render.form(f)
```

### Rendering Form with CSS
```python
# Render form without table structure for CSS styling
print(f.render_css())
```

### Accessing Form Values
```python
# Access individual field values
name = f['name'].value

# Access all values as storage object
all_values = f.d
print(all_values.name)
print(all_values.email)
```

### Pre-filling Form Data
```python
# Pre-fill form with existing data
f.fill(name='John Doe', email='john@example.com')

# Or from a dict
data = {'name': 'John Doe', 'email': 'john@example.com'}
f.fill(**data)
