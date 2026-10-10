# Web Python 3 Helpers Documentation

`web.py3helpers` provides `iterkeys`, `itervalues`, and `iteritems` for dictionary
iteration. The current web.py package is Python 3 only; all runnable examples on
this page target Python 3.

## Overview

Historically these helpers bridged dictionary iteration in Python 2 and Python 3.
Python 2's `.keys()`, `.values()`, and `.items()` returned lists. In Python 3 these
methods return **dictionary views**, which are iterable but are not iterators:
you can iterate over a view repeatedly, but `next(view)` raises `TypeError`.

Each helper applies `iter()` to the corresponding view and returns a fresh,
one-shot iterator. `iter(iterator)` returns that same iterator; `next()` consumes
one entry and eventually raises `StopIteration`. Iterating again does not rewind
it. Call the helper again for a fresh independent traversal of the dictionary.
The `iter()` wrapper is therefore not redundant when an iterator is required.

```python
from web.py3helpers import iterkeys

data = {'a': 1, 'b': 2}
view = data.keys()
assert list(view) == ['a', 'b']
assert list(view) == ['a', 'b']
try:
    next(view)
except TypeError:
    pass
else:
    raise AssertionError('A dictionary view is not an iterator')

iterator = iterkeys(data)
assert iter(iterator) is iterator
assert next(iterator) == 'a'
assert list(iterator) == ['b']
assert list(iterator) == []
try:
    next(iterator)
except StopIteration:
    pass
else:
    raise AssertionError('The iterator should be exhausted')
assert list(iterkeys(data)) == ['a', 'b']
```

## Functions

### `iterkeys(d)`

Returns an iterator over the dictionary's keys.

**Parameters:**
- `d` (dict): The dictionary to iterate over

**Returns:**
- Iterator over dictionary keys

**Example:**
```python
from web.py3helpers import iterkeys

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
from web.py3helpers import itervalues

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
from web.py3helpers import iteritems

d = {'a': 1, 'b': 2}
for key, value in iteritems(d):
    print(key, value)
```

## Usage Examples

### Current Python 3 Dictionary Iteration

```python
from web.py3helpers import iterkeys, itervalues, iteritems

# This example imports the current Python 3 package.
data = {'name': 'John', 'age': 30, 'city': 'New York'}

for key in iterkeys(data):
    print(key)

for value in itervalues(data):
    print(value)

for key, value in iteritems(data):
    print(f"{key}: {value}")
```

### Migration from Python 2 to 3

When porting a loop, pass a dictionary **instance**, not the builtin `dict` type.
This runnable example is for the current Python 3 package:

```python
from web.py3helpers import iterkeys

data = {'a': 1, 'b': 2}
for key in iterkeys(data):
    print(key)
```

## Implementation Details

The following is a source illustration, not a substitute for importing the real
helpers in application code:

```python
iterkeys = lambda d: iter(d.keys())
itervalues = lambda d: iter(d.values())
iteritems = lambda d: iter(d.items())
```

## Notes

- For a plain Python 3 `for` loop, use `for key in data`, `for value in
  data.values()`, or `for key, value in data.items()` directly. Use
  `iter(data)`, `iter(data.values())`, `iter(data.items())`, or these helpers when
  you specifically need an iterator, for example for `next()`.
- All traversal examples assume the dictionary is left unchanged during traversal.
- The three lambda expressions above are syntactically portable between Python
  2 and Python 3. That does **not** make the current package importable on Python
  2: importing `web.py3helpers` first initializes `web`, whose imported modules
  use Python 3 syntax such as f-strings and type annotations. The usage example
  above also contains an f-string. The source module's historical compatibility
  docstring is not a current package-support guarantee. No Python 2 execution is
  claimed here.

## Dependencies

The three helper expressions themselves use only Python builtins. Importing
`web.py3helpers` still initializes the package and requires web.py's dependencies;
the small helper file is not an independent, dependency-free package import.
See the [framework README](../README.md) for current setup and usage.
