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
- `**kw`: Additional keyword arguments including `validators`

#### Methods
- `__call__(self, x=None)`: Returns a copy of the form, optionally validating with input data
- `render(self)`: Renders the form as HTML table
- `render_css(self)`: Renders the form with CSS-friendly markup
- `rendernote(self, note)`: Renders error notes
- `validates(self, source=None, _validate=True, **kw)`: Validates form data
- `_validate(self, value)`: Runs custom validators on form data
- `fill(self, source=None, **kw)`: Fills form fields with data without validation
- `__getitem__(self, i)`: Gets an input field by name
- `__getattr__(self, name)`: Gets an input field by name (alternative access)
- `get(self, i, default=None)`: Safely gets an input field by name
- `d`: Property that returns a storage object with all field values

### `Input`
Base class for all form input elements.

#### Constructor
```python
def __init__(self, name, *validators, **attrs)
```

**Parameters:**
- `name`: Field name
- `*validators`: Validation rules
- `**attrs`: HTML attributes for the input element

#### Methods
- `is_hidden(self)`: Returns True if input is hidden
- `get_type(self)`: Gets the HTML input type
- `get_default_id(self)`: Gets default ID for the input
- `validate(self, value)`: Validates a value against validators
- `set_value(self, value)`: Sets the field's value
- `get_value(self)`: Gets the field's value
- `render(self)`: Renders the HTML input element
- `rendernote(self, note)`: Renders error notes
- `addatts(self)`: Returns string of additional attributes

### `AttributeList`
Helper class for managing HTML attributes.

#### Methods
- `copy(self)`: Creates a copy of the attribute list
- `__str__(self)`: String representation with sorted attributes
- `__repr__(self)`: String representation for debugging

### Input Subclasses

#### `Textbox`
Text input field.

#### `Password`
Password input field.

#### `Textarea`
Multi-line text input field.

#### `Dropdown`
Select dropdown menu.

#### `GroupedDropdown`
Select dropdown with grouped options.

#### `Radio`
Radio button group.

#### `Checkbox`
Checkbox input field.

#### `Button`
HTML button element.

#### `Hidden`
Hidden input field.

#### `File`
File upload input field.

#### `Telephone`
Telephone number input field.

#### `Email`
Email address input field.

#### `Date`
Date input field.

#### `Time`
Time input field.

#### `Search`
Search input field.

#### `Url`
URL input field.

#### `Number`
Numeric input field.

#### `Range`
Range slider input field.

#### `Color`
Color picker input field.

#### `Datalist`
Datalist input with autocomplete options.

### `Validator`
Base class for form validation rules.

#### Constructor
```python
def __init__(self, msg, test, jstest=None)
```

**Parameters:**
- `msg`: Error message for invalid values
- `test`: Function that tests if a value is valid
- `jstest`: Optional JavaScript validation function

#### Methods
- `valid(self, value)`: Tests if a value is valid
- `__deepcopy__(self, memo)`: Creates a deep copy of the validator

### Predefined Validators

- `notnull`: Validates that a field is not empty
- `regexp(pattern, msg)`: Validates against a regular expression pattern

## Functions

### `attrget(obj, attr, value=None)`
Safely gets an attribute from an object, handling various edge cases.

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
