# Web Python 3 Helpers Documentation

This document describes the Python 3 compatibility utilities in `web/py3helpers.py`, which provide cross-compatibility functions for dictionary iteration between Python 2 and Python 3.

## Overview

The `py3helpers` module contains utility functions that help maintain compatibility between Python 2 and Python 3 by providing consistent interfaces for dictionary iteration operations. These helpers are particularly useful when writing code that needs to run on both Python versions.

In Python 2, dictionary methods like `.keys()`, `.values()`, and `.items()` return lists, while in Python 3 they return iterators. These helpers ensure consistent iterator behavior across both versions.

## Functions

### `iterkeys(d)`

Returns an iterator over the dictionary's keys.

**Parameters:**
- `d` (dict): The dictionary to iterate over

**Returns:**
- Iterator over dictionary keys

**Example:**
```python
d = {'a': 1, 'b': 2}
for key in iterkeys(d):
    print(key)
```

### `itervalues(d)`

Returns an iterator over the dictionary's values.

**Parameters:**
- `d` (dict): The dictionary to iterate over

**Returns:**
- Iterator over dictionary values

**Example:**
```python
d = {'a': 1, 'b': 2}
for value in itervalues(d):
    print(value)
```

### `iteritems(d)`

Returns an iterator over the dictionary's key-value pairs.

**Parameters:**
- `d` (dict): The dictionary to iterate over

**Returns:**
- Iterator over dictionary items (key, value tuples)

**Example:**
```python
d = {'a': 1, 'b': 2}
for key, value in iteritems(d):
    print(key, value)
```

## Usage Examples

### Cross-Version Dictionary Iteration

```python
from web.py3helpers import iterkeys, itervalues, iteritems

# These functions work consistently across Python 2 and 3
data = {'name': 'John', 'age': 30, 'city': 'New York'}

for key in iterkeys(data):
    print(key)

for value in itervalues(data):
    print(value)

for key, value in iteritems(data):
    print(f"{key}: {value}")
```

### Migration from Python 2 to 3

```python
# Instead of:
# for key in dict.keys():  # Python 2 (returns list)
# for key in dict:         # Python 3 (iterates over keys)

# Use:
from web.py3helpers import iterkeys
for key in iterkeys(dict):
    pass
```

## Implementation Details

The module uses simple lambda functions that wrap the standard dictionary methods:

```python
iterkeys = lambda d: iter(d.keys())
itervalues = lambda d: iter(d.values())
iteritems = lambda d: iter(d.items())
```

## Notes

- These functions are designed to provide a consistent interface regardless of the Python version being used
- In Python 3, they return iterators (as opposed to lists) for memory efficiency
- The module is primarily intended for internal use within web.py to maintain compatibility
- These helpers are not needed in pure Python 3 code where standard dictionary methods can be used directly
- In Python 3, `dict.keys()`, `dict.values()`, and `dict.items()` already return dictionary view objects (which are iterators), so the `iter()` wrapper is redundant but harmless

## Dependencies

This module has no external dependencies beyond the standard library.
