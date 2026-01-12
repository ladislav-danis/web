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
- `percent(key)`: Returns percentage of a key's count
- `sorted_keys()`: Returns keys sorted by value
- `sorted_values()`: Returns values sorted by value
- `sorted_items()`: Returns items sorted by value

### `IterBetter`
An iterator wrapper that allows both iteration and indexed access.

**Methods:**
- `first(default=None)`: Returns first element or default if none exists
- `__getitem__(i)`: Access elements by index
- `__nonzero__()`: Boolean test for iterator contents

### `ThreadedDict`
Thread-local storage for data that persists per thread.

**Methods:**
- `clear_all()`: Clears all ThreadedDict instances
- All standard dict methods (get, set, delete, etc.)

### `_EmailMessage`
Internal class for creating and sending email messages with attachments.

## Functions

### `storify(mapping, *requireds, **defaults)`
Creates a `storage` object from a dictionary, handling special cases like lists and objects with value attributes.

**Parameters:**
- `mapping`: Dictionary to convert
- `*requireds`: Required keys
- `**defaults`: Default values for optional keys

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
Decorator that limits function execution time.

**Example:**
```python
@timelimit(1)
def slow_function():
    time.sleep(2)
    return "done"
```

### `memoize(func, expires=None, background=True)`
Memoizes a function's return values with optional expiration and background updates.

### `re_compile(pattern)`
Memoized version of `re.compile`.

### `re_subm(pat, repl, string)`
Like `re.sub`, but returns both replacement and match object.

### `group(seq, size)`
Groups sequence elements into sublists of specified size.

### `uniq(seq, key=None)`
Removes duplicate elements while preserving order.

### `iterview(x)`
Returns an iterator that shows progress to stderr during iteration.

### `safeiter(it, cleanup=None, ignore_errors=True)`
Makes an iterator safe by handling exceptions during iteration.

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

### `requeue(queue, index=-1)`
Returns the element at index after moving it to the beginning of the queue.

### `restack(stack, index=0)`
Returns the element at index after moving it to the top of stack.

### `listget(lst, ind, default=None)`
Returns `lst[ind]` if it exists, `default` otherwise.

### `intget(integer, default=None)`
Returns `integer` as an int or `default` if it can't.

### `datestr(then, now=None)`
Converts a (UTC) datetime object to a nice string representation.

### `numify(string)`
Removes all non-digit characters from `string`.

### `denumify(string, pattern)`
Formats `string` according to `pattern`, where the letter X gets replaced
by characters from `string`.

### `commify(n)`
Adds commas to an integer `n`.

### `dateify(datestring)`
Formats a numified `datestring` properly.

### `nthstr(n)`
Formats an ordinal.
Doesn't handle negative numbers.

### `cond(predicate, consequence, alternative=None)`
Function replacement for if-else expressions.

### `capturestdout(func)`
Captures everything `func` prints to stdout and returns it instead.

**WARNING:** Not threadsafe!

### `profile(func)`
Profiles `func` and returns a tuple containing its output
and a string with human-readable profiling information.

### `tryall(context, prefix=None)`
Tries a series of functions and prints their results.
`context` is a dictionary mapping names to values;
the value will only be tried if it's callable.

### `autoassign(self, locals)`
Automatically assigns local variables to object attributes.

### `to36(q)`
Converts an integer to base 36 (a useful scheme for human-sayable IDs).

### `sendmail(from_address, to_address, subject, message, headers=None, **kw)`
Sends the email message `message` with mail and envelope headers
for from `from_address_` to `to_address` with `subject`.
Additional email headers can be specified with the dictionary
`headers.

Optionally cc, bcc and attachments can be specified as keyword arguments.
Attachments must be an iterable and each attachment can be either a
filename or a file object or a dictionary with filename, content and
optionally content_type keys.

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
```
