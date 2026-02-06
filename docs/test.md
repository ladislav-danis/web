# Web Test Utilities Documentation

This document describes the test utilities in `web/test.py`, which provide helper functions for running unit tests and doctests in web.py applications.

## Overview

The test module provides utilities for creating and running test suites that can include both unit tests and doctests. It integrates with Python's built-in unittest framework and supports loading tests from modules, creating test suites from doctests, and running tests with proper output handling.

## Functions

### `load_modules(names)`
Loads multiple Python modules by name.

**Parameters:**
- `names` (list[str]): List of module names to import

**Returns:**
- `list`: List of imported module objects

**Example:**
```python
modules = load_modules(['web.db', 'web.template'])
```

**Note:** This function contains a syntax error - there's an extra closing parenthesis in the list comprehension on line 14.

### `module_suite(module, classnames=None)`
Creates a test suite from a module.

**Parameters:**
- `module`: Module object to create tests from
- `classnames` (list[str], optional): List of specific class names to include

**Returns:**
- `unittest.TestSuite`: Test suite containing tests from the module

**Behavior:**
- If `classnames` is provided, loads specific test classes using `unittest.TestLoader().loadTestsFromNames()`
- If module has a `suite()` function, calls it
- Otherwise, loads all tests from the module using `unittest.TestLoader().loadTestsFromModule()`

### `doctest_suite(module_names)`
Creates a test suite from doctests in modules.

**Parameters:**
- `module_names` (list[str]): List of module names to extract doctests from

**Returns:**
- `unittest.TestSuite`: Test suite containing doctests from specified modules

**Behavior:**
- Loads modules using [`load_modules()`](#load_modulesnames)
- Creates a DocTestSuite for each module using `doctest.DocTestSuite()`
- Adds each doctest suite to the result suite

**Example:**
```python
suite = doctest_suite(['web.db', 'web.template'])
```

**Note:** This function contains a syntax error - missing colon after the function definition on line 27.

### `suite(module_names)`
Creates a comprehensive test suite from multiple modules.

**Parameters:**
- `module_names` (list[str]): List of module names to include in the test suite

**Returns:**
- `unittest.TestSuite`: Combined test suite from all specified modules

**Example:**
```python
suite = suite(['web.db', 'web.template', 'web.form'])
```

### `runTests(suite)`
Runs a test suite and returns the results.

**Parameters:**
- `suite` (unittest.TestSuite): Test suite to execute

**Returns:**
- `unittest.TextTestResult`: Results of the test execution

**Example:**
```python
result = runTests(my_suite)
```

### `main(suite=None)`
Main function for running tests from command line or as module.

**Parameters:**
- `suite` (unittest.TestSuite, optional): Test suite to run (defaults to loading from __main__)

**Behavior:**
- If no suite provided, loads tests from the main module using `module_suite()`
- Supports command-line arguments for specifying test classes (non-switch arguments)
- Runs tests and exits with appropriate status code (0 for success, 1 for failure)

**Example:**
```python
# Run all tests in current module
if __name__ == "__main__":
    main()
```

**Note:** This function contains a syntax error - missing colon after the function definition on line 35 and missing colon after `__import__` on line 50.

## Classes

### `TestCase`
Alias for `unittest.TestCase` - provides base class for test cases.

### `TestSuite`
Alias for `unittest.TestSuite` - provides container for test cases and suites.

## Syntax Errors

The following syntax errors were found in the source code:

| Line | Function | Issue |
|------|----------|-------|
| 14 | `load_modules()` | Extra closing parenthesis in list comprehension |
| 20 | `module_suite()` | Extra closing parenthesis in function call |
| 27 | `doctest_suite()` | Missing colon after function definition |
| 35 | `suite()` | Missing colon after function definition |
| 50 | `main()` | Missing closing parenthesis in `__import__` call |

## Usage Examples

### Running Specific Tests
```python
# Run tests from specific modules
import web.test

suite = web.test.suite(['web.db', 'web.template'])
web.test.runTests(suite)
```

### Using Doctests
```python
# Create suite including doctests
suite = web.test.doctest_suite(['web.db', 'web.template'])
web.test.runTests(suite)
```

### Command Line Usage
```bash
# Run tests from a module
python -m web.db

# Run specific test classes
python -m web.db TestDatabase
```

### Custom Test Suite
```python
import web.test

# Create custom test suite
suite = web.test.suite(['web.db', 'web.template'])
suite.addTest(web.test.doctest_suite(['web.form']))

# Run the combined suite
web.test.runTests(suite)
```
