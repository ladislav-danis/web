# Web Debug Error Documentation

This document describes the debug error handling functionality in `web/debugerror.py`, which provides enhanced error reporting for web.py applications.

## Overview

The `debugerror` module provides tools for displaying detailed debugging information when errors occur in web.py applications. It includes features for pretty-printing stack traces, showing request context, and emailing error reports to developers.

The module is inspired by Django's debug error pages and includes:

- Detailed stack traces with source code context
- Local variable inspection at each frame
- Request and environment information
- Email notification capabilities for production error reporting

## Functions

### `debugerror()`

Returns an internal error handler that displays a detailed debug page with stack trace information, request data, and local variables.

**Returns:** A function that returns a `web._InternalError` containing the HTML debug page

**Usage:**
```python
import web
from web.debugerror import debugerror

# Enable debug mode and set error handler
web.config.debug = True
web.internalerror = debugerror

# Your application code here
```

### `djangoerror()`

Generates a Django-style error page with detailed debugging information. This function is called internally by `debugerror()` and can also be used directly for custom error handling.

**Returns:** HTML content for the debug error page containing:
- Exception type and value
- Full stack trace with source code context (7 lines before/after)
- Local variables at each stack frame
- Request information (headers, cookies, environment)
- Response data (if any)

**Internal Behavior:**
- Extracts exception information from `sys.exc_info()`
- Builds a list of stack frames with context lines
- Renders the `djangoerror_t` template with the exception data

### `emailerrors(to_address, olderror, from_address=None)`

Creates an error handler that emails error details to a specified address while still displaying the normal error page. This is useful for production environments where you want to be notified of errors without exposing debug information to users.

**Parameters:**
- `to_address` (str): Email address to send error notifications to
- `olderror` (function): The previous internal error handler function
- `from_address` (str, optional): Sender email address. Defaults to `to_address`

**Returns:** A new error handler function that:
1. Calls the original error handler to display the error page
2. Sends an email with:
   - Text traceback in the message body
   - HTML debug page as an attachment named `bug.html`
   - Subject line with error type, value, and path

**Usage:**
```python
import web
from web.debugerror import emailerrors, debugerror

# Set up email error reporting for production
web.config.debug = False  # Hide debug from users
web.internalerror = emailerrors('developer@example.com', debugerror)

# Errors will be emailed to the developer while showing a normal error page
```

## Constants

### `djangoerror_t`

Template string for the Django-style error page HTML. Contains:
- CSS styling for a clean, readable error page
- JavaScript for toggling visibility of stack frames and local variables
- Template variables for exception data, frames, request info, and environment

### `djangoerror_r`

Template object created from `djangoerror_t` using web.py's `Template` class. This is cached after first creation for performance.

**Initialization:**
```python
djangoerror_r = Template(djangoerror_t, filename=__file__, filter=websafe)
```

### `whereami`

Contains the path to the `debugerror.py` file, used for template resolution.

## Classes and Data Structures

### Frame Object

Each frame in the traceback contains the following attributes:

| Attribute | Type | Description |
|-----------|------|-------------|
| `tback` | traceback object | Original traceback object |
| `filename` | str | Path to the source file |
| `function` | str | Name of the function being executed |
| `lineno` | int | Line number where the error occurred |
| `vars` | dict | Local variables at this frame |
| `id` | int | Unique identifier for the frame |
| `pre_context` | list | Lines before the error line |
| `context_line` | str | The line where the error occurred |
| `post_context` | list | Lines after the error line |
| `pre_context_lineno` | int | Line number of the first context line |

## Template Variables

The `djangoerror_t` template uses the following variables:

| Variable | Description |
|----------|-------------|
| `exception_type` | The type of exception (e.g., `NameError`) |
| `exception_value` | The exception message |
| `ctx.path` | The request path |
| `ctx.method` | HTTP method (GET, POST, etc.) |
| `ctx.home` | The base URL of the application |
| `ctx.output` | Response body (if any was generated) |
| `ctx.headers` | Response headers |
| `frames` | List of traceback frames |
| `prettify(x)` | Function to pretty-print Python objects |

## Usage Examples

### Basic Debug Mode

Enable detailed error pages during development:

```python
import web
from web.debugerror import debugerror

urls = (
    '/', 'Index'
)

class Index:
    def GET(self):
        # This will cause a NameError
        return this_does_not_exist

app = web.application(urls, globals())
web.config.debug = True
app.internalerror = debugerror

if __name__ == '__main__':
    app.run()
```

### Production Error Notification

Set up email notifications for production while hiding debug details:

```python
import web
from web.debugerror import emailerrors, debugerror

urls = (
    '/', 'Index'
)

class Index:
    def GET(self):
        # Your application code
        pass

app = web.application(urls, globals())
web.config.debug = False  # Hide debug from users
app.internalerror = emailerrors('errors@example.com', debugerror)

if __name__ == '__main__':
    app.run()
```

### Custom Error Handler with Django Error

Create a custom error handler that uses the Django-style page:

```python
import web
from web.debugerror import djangoerror

def custom_error_handler():
    # Log the error to a file
    import logging
    logging.error("An error occurred: %s", str(web.ctx.get('error', 'Unknown')))
    
    # Return the Django-style error page
    return djangoerror()

web.internalerror = custom_error_handler
```

### Combining with Custom Logging

```python
import web
from web.debugerror import emailerrors, debugerror
import logging

# Configure logging
logging.basicConfig(filename='app_errors.log', level=logging.ERROR)

def logged_email_errors(to_address, olderror):
    def handler():
        # Log the error
        exc_info = sys.exc_info()
        logging.error("Error occurred", exc_info=exc_info)
        
        # Email the error
        return emailerrors(to_address, olderror)()
    
    return handler

web.internalerror = logged_email_errors('dev@example.com', debugerror)
```

## Features

1. **Pretty Stack Traces**: Shows source code context around errors with line numbers and visual highlighting
2. **Variable Inspection**: Displays local variables at each stack frame in a collapsible section
3. **Request Context**: Shows HTTP headers, cookies, request data, and environment variables
4. **Email Notifications**: Can automatically email error reports to developers with both text and HTML versions
5. **Template Support**: Works with web.py's template system for rendering error pages
6. **Interactive UI**: JavaScript-powered toggling of stack frames and variable sections
7. **Debug Mode Toggle**: Only active when `web.config.debug` is `True`

## Internal Functions

### `update_globals_template(t, globals)`

Updates the template's global namespace with additional variables.

**Parameters:**
- `t`: Template object
- `globals`: Dictionary of global variables to add

### `_get_lines_from_file(filename, lineno, context_lines)`

Reads lines from a source file around a specific line number.

**Parameters:**
- `filename` (str): Path to the source file
- `lineno` (int): Line number to center on
- `context_lines` (int): Number of lines to show before and after

**Returns:** Tuple of `(pre_context_lineno, pre_context, context_line, post_context)`

### `prettify(x)`

Converts Python objects to a readable string representation using `pprint`.

**Parameters:**
- `x`: Any Python object

**Returns:** String representation of the object, or an error message if formatting fails

## Security Considerations

⚠️ **Important**: The debug error handler should **never** be used in production environments because it exposes:

- Full source code of your application
- Local variable contents (may include passwords, API keys, etc.)
- File system paths
- Server environment variables
- Request and session data

**Best Practices:**
1. Always set `web.config.debug = False` in production
2. Use `emailerrors()` to receive error notifications without exposing debug info
3. Never commit debug error pages to version control if they contain sensitive data
4. Consider using a proper logging system instead of debug pages in production

## Customization

### Modifying the Error Template

The `djangoerror_t` template can be customized by creating a new template with the same variables:

```python
custom_template = """\
<!DOCTYPE html>
<html>
<head><title>Error</title></head>
<body>
    <h1>$exception_type</h1>
    <p>$exception_value</p>
    <!-- Your custom styling -->
</body>
</html>
"""

custom_error_r = Template(custom_template, filename=__file__, filter=websafe)
```

### Adjusting Context Lines

To show more or fewer lines of context around errors, modify the `_get_lines_from_file` call in `djangoerror()`:

```python
# Change from 7 to 15 lines of context
pre_context_lineno, pre_context, context_line, post_context = _get_lines_from_file(filename, lineno, 15)
```

## Troubleshooting

### Error: "Template not found"

Ensure the template file path is correct and the file exists. The template is embedded in the `djangoerror_t` string constant.

### Errors Not Being Emailed

1. Verify SMTP settings are configured in `web.utils.sendmail`
2. Check that the `from_address` has permission to send email
3. Ensure the `to_address` is correctly formatted

### Debug Page Not Showing

1. Verify `web.config.debug = True`
2. Ensure `web.internalerror` is set to `debugerror`
3. Check that the exception is not being caught by other error handlers

## See Also

- [`web/api`](webapi.md) - Core web.py API
- [`web/template`](template.md) - Template system documentation
- [`web/utils`](utils.md) - Utility functions including `sendmail`
