# Web Utilities Documentation

This document describes the utility functions in `web/utils.py`, which provide a wide range of helper functions for common programming tasks in web.py applications.

## Overview

The utils module contains general-purpose utility functions that are commonly used throughout the web.py framework. These utilities cover areas such as data structures, string manipulation, date formatting, threading, and email handling.

## Classes

### `Storage`
A dictionary-like object that supports both attribute-style and key-style access.

**Example:**
```python
o = storage(a=1)
o.a  # Returns 1
o['a']  # Returns 1
o.a = 2  # Sets value to 2
del o.a  # Deletes the key
```

### `Counter`
A dictionary subclass that keeps count of how many times items are added.

**Methods:**
- `add(n)`: Increments count for item `n`
- `most()`: Returns keys with maximum count
- `least()`: Returns keys with minimum count
- `percent(key)`: Returns what percentage a certain key is of all entries
- `sorted_keys()`: Returns keys sorted by value
- `sorted_values()`: Returns values sorted by value
- `sorted_items()`: Returns items sorted by value

### `IterBetter`
An iterator wrapper that allows both iteration and indexed access.

**Methods:**
- `first(default=None)`: Returns first element or default if none exists
- `__getitem__(i)`: Access elements by index (cannot go backwards)
- `__nonzero__()`: Boolean test for iterator contents (peeks at first value)

### `ThreadedDict`
Thread-local storage for data that persists per thread.

**Methods:**
- `clear_all()`: Clears all ThreadedDict instances (static method)
- All standard dict methods (get, set, delete, etc.)

### `_EmailMessage`
Internal class for creating and sending email messages with attachments.

## Functions

### `storify(mapping, *requireds, **defaults)`
Creates a `storage` object from a dictionary, handling special cases like lists and objects with value attributes.

**Parameters:**
- `mapping`: Dictionary to convert
- `*requireds`: Required keys (raises KeyError if missing)
- `**defaults`: Default values for optional keys
- `_unicode=False`: If True, converts strings to unicode using `safeunicode`

**Behavior:**
- If a value is a list, returns the last element unless the key appears in `defaults` as a list
- If a value has a `value` attribute, returns that value unless the key appears in `defaults` as a dictionary

**Examples:**
```python
# Basic usage
storify({'a': 1, 'c': 3}, b=2, c=0)  # Returns storage({'a': 1, 'b': 2, 'c': 3})

# List handling - returns last element
storify({'a': [1, 2]}).a  # Returns 2

# List handling with default - returns full list
storify({'a': [1, 2]}, a=[])  # Returns [1, 2]

# Object with value attribute
storify({'a': storage(value=1)}).a  # Returns 1
storify({'a': storage(value=1)}, a={})  # Returns <Storage {'value': 1}>
```

### `rstrips(text, remove)`
Removes the string `remove` from the right side of `text`.

### `lstrips(text, remove)`
Removes the string `remove` from the left side of `text`.

### `strips(text, remove)`
Removes the string `remove` from both sides of `text`.

### `safestr(obj, encoding="utf-8")`
Converts any object to a UTF-8 encoded string.

### `safeunicode(obj, encoding="utf-8")`
Alias for `safestr` (Python 3 compatibility).

### `timelimit(timeout)`
Decorator that limits function execution time to `timeout` seconds, raising `RuntimeError` if it takes longer.

**Caveat:** The function isn't stopped after `timeout` seconds but continues executing in a separate thread. There is no way to kill a thread in Python.

**Example:**
```python
import time

def meaningoflife():
    time.sleep(.2)
    return 42

timelimit(.1)(meaningoflife)()  # Raises RuntimeError: took too long
timelimit(1)(meaningoflife)()   # Returns 42
```

### `memoize(func, expires=None, background=True)`
Memoizes a function's return values with optional expiration and background updates.

**Parameters:**
- `func`: Function to memoize
- `expires`: If specified, values are recalculated after `expires` seconds
- `background`: If True (default), values are recalculated in a separate thread

### `re_compile(pattern)`
Memoized version of `re.compile`. Useful for frequently used regex patterns.

### `group(seq, size)`
Groups sequence elements into sublists of specified size.

**Returns:** An iterator over lists of length `size` from the iterable.

**Example:**
```python
list(group([1,2,3,4], 2))  # [[1, 2], [3, 4]]
list(group([1,2,3,4,5], 2))  # [[1, 2], [3, 4], [5]]
```

### `uniq(seq, key=None)`
Removes duplicate elements while preserving order.

**Parameters:**
- `seq`: Sequence to remove duplicates from
- `key`: Optional function that takes a single argument and returns a key to test uniqueness

**Example:**
```python
uniq([9,0,2,1,0])  # [9, 0, 2, 1]
uniq(["Foo", "foo", "bar"], key=lambda s: s.lower())  # ['Foo', 'bar']
```

### `iterview(x)`
Returns an iterator that shows progress to stderr during iteration.

**Parameters:**
- `x`: Iterable to iterate over

**Example:**
```python
for item in iterview(range(100)):
    # Process item with progress displayed on stderr
    process(item)
```

### `safeiter(it, cleanup=None, ignore_errors=True)`
Returns a lazy generator over an iterable, preserving each yielded value. Neither
`iter(it)` nor the first `next(it)` runs until the wrapper is first advanced.

- `StopIteration` from advancing the iterator ends the wrapper normally (no
  cleanup, traceback, or PEP 479 `RuntimeError`).
- For another `Exception` raised by `next(it)`, a supplied `cleanup` is called
  **once, without arguments, before** applying the error policy. A falsy callable
  is still called; a noncallable value other than `None` fails when used.
- With `ignore_errors=True` (default), the original exception is printed using
  `traceback.print_exc()` to stderr, then the same iterator is advanced again.
  With `False`, the original exception propagates without traceback printing.
- If cleanup raises, its error is not caught or retried by `safeiter`; there is
  no additional traceback printing by the wrapper.
- `SystemExit`, `KeyboardInterrupt`, and `GeneratorExit` propagate without
  cleanup or logging. Errors from `iter(it)` also propagate without this handling.
  The handler surrounds only advancing the iterator, not `yield`: an exception
  injected with the wrapper's `throw()` is not treated as an iterator failure.
  Normal Python generator rules still apply: a `StopIteration` escaping
  `iter(it)` or cleanup, or injected with `throw()`, becomes a PEP 479
  `RuntimeError` with that `StopIteration` as its cause. Only exhaustion from
  the underlying `next(it)` is handled as normal completion.

Cleanup is an **error callback**, not a resource-finalization hook: normal
exhaustion and wrapper `close()` do not call it, and closing the wrapper does not
forward `close()` to the underlying iterator. Manage owned resources explicitly.
The name does not promise safe or bounded execution for arbitrary iterators:
there is no retry budget, so an iterator that keeps raising ordinary exceptions
can loop forever inside one `next()` call with `ignore_errors=True`. A generator
that raises an unhandled exception is normally closed; retrying it will not
resurrect it or recover its remaining values. Recovery depends on the iterator's
state and possibly the cleanup callback. Prefer strict mode if recovery is not
known to be possible. Tracebacks can expose exception details; this is not a
redacting logger.

These finite, standalone examples require only the framework import:

```python
from web.utils import safeiter

value = object()
wrapped = safeiter([value, None, 3])
assert next(wrapped) is value
assert next(wrapped) is None
assert next(wrapped) == 3
sentinel = object()
assert next(wrapped, sentinel) is sentinel
assert next(wrapped, sentinel) is sentinel
```

A custom iterator can advance past a bad step. Here cleanup records the failed
step; the first run captures the expected traceback, and the strict run stops at
the same error instead of silently continuing:

```python
import contextlib
import io
from web.utils import safeiter

class Steps:
    def __init__(self):
        self.position = 0
        self.error = ValueError('bad step')

    def __iter__(self):
        return self

    def __next__(self):
        self.position += 1
        if self.position == 1:
            return 'before'
        if self.position == 2:
            raise self.error
        if self.position == 3:
            return 'after'
        raise StopIteration

source = Steps()
cleaned = []
wrapped = safeiter(source, cleanup=lambda: cleaned.append(source.position))
stderr = io.StringIO()
with contextlib.redirect_stderr(stderr):
    assert next(wrapped) == 'before'
    assert next(wrapped) == 'after'
    sentinel = object()
    assert next(wrapped, sentinel) is sentinel
assert cleaned == [2]
assert 'ValueError: bad step' in stderr.getvalue()

source = Steps()
cleaned = []
wrapped = safeiter(source, cleanup=lambda: cleaned.append(source.position),
                   ignore_errors=False)
assert next(wrapped) == 'before'
try:
    next(wrapped)
except ValueError as error:
    assert error is source.error
else:
    raise AssertionError('strict iteration must propagate the error')
assert cleaned == [2]
assert source.position == 2
```

### `safewrite(filename, content)`
Writes content to a temporary file and moves it to avoid overwriting errors.

### `dictreverse(mapping)`
Returns a new dictionary with keys and values swapped.

### `dictfind(dictionary, element)`
Returns a key whose value in the dictionary is `element`
or, if none exists, None.

### `dictfindall(dictionary, element)`
Returns the keys whose values in `dictionary` are `element`
or, if none exists, [].

### `dictincr(dictionary, element)`
Increments `element` in `dictionary`,
setting it to one if it doesn't exist.

### `dictadd(*dicts)`
Returns a dictionary consisting of the keys in the argument dictionaries.
If they share a key, the value from the last argument is used.

**Parameters:**
- `*dicts`: One or more dictionaries to merge

**Example:**
```python
dictadd({1: 0, 2: 0}, {2: 1, 3: 1})  # {1: 0, 2: 1, 3: 1}
```

### `requeue(queue, index=-1)`
Returns the element at index after moving it to the beginning of the queue.

**Parameters:**
- `queue`: List to modify
- `index`: Index of element to move (default: -1, last element)

**Example:**
```python
x = [1, 2, 3, 4]
requeue(x)  # Returns 4
x  # [4, 1, 2, 3]
```

### `restack(stack, index=0)`
Returns the element at index after moving it to the top of stack.

**Parameters:**
- `stack`: List to modify
- `index`: Index of element to move (default: 0, first element)

**Example:**
```python
x = [1, 2, 3, 4]
restack(x)  # Returns 1
x  # [2, 3, 4, 1]
```

### `listget(lst, ind, default=None)`
Returns `lst[ind]` if it exists, `default` otherwise.

**Parameters:**
- `lst`: List to access
- `ind`: Index to access
- `default`: Default value if index out of range

**Example:**
```python
listget(['a'], 0)  # 'a'
listget(['a'], 1)  # None
listget(['a'], 1, 'b')  # 'b'
```

### `intget(integer, default=None)`
Returns `integer` as an int or `default` if it can't be converted.

**Parameters:**
- `integer`: String or value to convert to int
- `default`: Default value if conversion fails

**Example:**
```python
intget('3')  # 3
intget('3a')  # None
intget('3a', 0)  # 0
```

### `datestr(then, now=None)`
Converts a (UTC) datetime object to a nice string representation showing relative time.

**Parameters:**
- `then`: Datetime object to convert
- `now`: Current datetime (default: UTC now)

**Returns:** Human-readable string like "2 days ago" or "January 1"

**Example:**
```python
from datetime import datetime, timedelta
now = datetime.now()
past = now - timedelta(hours=2)
datestr(past, now)  # '2 hours ago'
```

### `numify(string)`
Removes all non-digit characters from `string`.

**Parameters:**
- `string`: String to process

**Example:**
```python
numify('800-555-1212')  # '8005551212'
numify('800.555.1212')  # '8005551212'
```

### `denumify(string, pattern)`
Formats `string` according to `pattern`, where the letter X gets replaced
by characters from `string`.

**Parameters:**
- `string`: String to format
- `pattern`: Pattern with X characters to replace

**Example:**
```python
denumify("8005551212", "(XXX) XXX-XXXX")  # '(800) 555-1212'
```

### `commify(n)`
Adds commas to an integer `n`.

**Parameters:**
- `n`: Number to format

**Example:**
```python
commify(1)  # '1'
commify(1234)  # '1,234'
commify(1234567890)  # '1,234,567,890'
commify(1234.5)  # '1,234.5'
```

### `dateify(datestring)`
Formats a numified `datestring` properly.

**Parameters:**
- `datestring`: Numified date string to format

**Example:**
```python
dateify("20240115123045")  # '2024-01-15 12:30:45'
```

### `nthstr(n)`
Formats an ordinal (doesn't handle negative numbers).

**Parameters:**
- `n`: Number to format as ordinal

**Example:**
```python
nthstr(1)  # '1st'
nthstr(2)  # '2nd'
nthstr(3)  # '3rd'
nthstr(4)  # '4th'
nthstr(111)  # '111th'
```

### `cond(predicate, consequence, alternative=None)`
Function replacement for if-else to use in expressions.

**Parameters:**
- `predicate`: Condition to evaluate
- `consequence`: Value if predicate is True
- `alternative`: Value if predicate is False (default: None)

**Example:**
```python
x = 2
cond(x % 2 == 0, "even", "odd")  # 'even'
cond(x % 2 == 0, "even", "odd") + '_row'  # 'even_row'
```

### `capturestdout(func)`
Captures everything `func` prints to stdout and returns it instead.

**Parameters:**
- `func`: Function to capture output from

**Returns:** String containing captured stdout

**WARNING:** Not threadsafe!

**Example:**
```python
def idiot():
    print("foo")
capturestdout(idiot)()  # 'foo\n'
```

### `profile(func)`
Profiles `func` and returns a tuple containing its output
and a string with human-readable profiling information.

**Parameters:**
- `func`: Function to profile

**Returns:** Tuple of (function_result, profiling_info_string)

**Example:**
```python
import time
out, inf = profile(time.sleep)(.001)
inf[:10].strip()  # 'took 0.0'
```

### `tryall(context, prefix=None)`
Tries a series of functions and prints their results.

**Parameters:**
- `context`: Dictionary mapping names to values (functions will be tried)
- `prefix`: Optional prefix to filter function names

**Example:**
```python
def test_a():
    return True

def test_b():
    return False

tryall(globals())  # Prints results of all test functions
```

### `autoassign(self, locals)`
Automatically assigns local variables to object attributes.

**Parameters:**
- `self`: Object to assign attributes to
- `locals`: Dictionary of local variables (typically `locals()`)

**Example:**
```python
def __init__(self, foo, bar, baz=1):
    autoassign(self, locals())
# self.foo, self.bar, self.baz are now set
```

### `to36(q)`
Converts an integer to base 36 (a useful scheme for human-sayable IDs).

**Parameters:**
- `q`: Positive integer to convert

**Returns:** Base-36 string representation

**Example:**
```python
to36(35)  # 'z'
to36(119292)  # '2k1o'
to36(0)  # '0'
```

### `sendmail(from_address, to_address, subject, message, headers=None, **kw)`
Sends the email message `message` with mail and envelope headers
for from `from_address` to `to_address` with `subject`.

**Parameters:**
- `from_address`: Sender email address
- `to_address`: Recipient email address (or list of addresses)
- `subject`: Email subject
- `message`: Email message body
- `headers`: Optional dictionary of additional email headers
- `cc`: Optional carbon copy recipients (list or string)
- `bcc`: Optional blind carbon copy recipients (list or string)
- `attachments`: Optional list of attachments (filenames, file objects, or dicts)

**Attachment Format:**
Attachments can be:
- Filename string
- File object
- Dictionary with `filename`, `content`, and optionally `content_type` keys

**Email Configuration:**
If `web.config.smtp_server` is set, it will send the message
to that SMTP server. Otherwise it will look for
`/usr/sbin/sendmail`, the typical location for the sendmail-style
binary. To use sendmail from a different path, set `web.config.sendmail_path`.

## Constants

### `__all__`
List of public functions and classes exported by this module:
- Storage, storage
- Counter, counter
- iters
- rstrips, lstrips, strips
- safeunicode, safestr
- timelimit
- Memoize, memoize
- re_compile, re_subm
- group, uniq, iterview
- IterBetter, iterbetter
- safeiter, safewrite
- dictreverse, dictfind, dictfindall
- dictincr, dictadd
- requeue, restack
- listget, intget
- datestr, numify, denumify, commify, dateify
- nthstr, cond
- CaptureStdout, capturestdout
- Profile, profile
- tryall
- ThreadedDict, threadeddict
- autoassign
- to36
- sendmail

### `iters`
A list of iterable items (like lists, but not strings). Includes whichever
of lists, tuples, sets, and Sets are available in this version of Python.

## Usage Examples

### Storage Object
```python
# Create storage object
data = storage(name='John', age=30)

# Access like dictionary or attribute
print(data['name'])  # 'John'
print(data.name)     # 'John'

# Set values
data.email = 'john@example.com'
```

### Counter
```python
# Count occurrences
c = counter()
c.add('apple')
c.add('banana')
c.add('apple')

print(c['apple'])  # 2
print(c.most())    # ['apple']
```

### Memoization
```python
@memoize
def expensive_function():
    time.sleep(1)
    return "result"

# First call takes 1 second, subsequent calls are instant
result = expensive_function()
```

### Date Formatting
```python
from datetime import datetime, timedelta

now = datetime.now()
past = now - timedelta(hours=2)

print(datestr(past, now))  # '2 hours ago'
```

### Email Sending
```python
# Send simple email
sendmail('sender@example.com', 'recipient@example.com',
         'Subject', 'Message body')

# Send with attachments
sendmail('sender@example.com', 'recipient@example.com',
         'Subject', 'Message body', attachments=['file.pdf'])

# Send with multiple recipients and CC
sendmail('sender@example.com', ['to1@example.com', 'to2@example.com'],
         'Subject', 'Message body', cc=['cc@example.com'])

# Send with file object attachment
with open('document.pdf', 'rb') as f:
    sendmail('sender@example.com', 'recipient@example.com',
             'Subject', 'Message body', attachments=[f])
```
