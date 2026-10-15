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
- `most()`: Returns all keys tied for maximum count
- `least()`: Returns all keys tied for minimum count
- `percent(key)`: Returns `float(self[key]) / sum(self.values())`, a fraction,
  not a percentage number. Multiply by 100 for percent. It is in 0..1 only
  for nonnegative counts with a positive total. Arbitrary assigned counts can
  give values outside that range; a zero total raises `ZeroDivisionError`,
  and a missing key raises `KeyError`.
- `sorted_keys()`: Returns keys sorted by value
- `sorted_values()`: Returns values sorted by value
- `sorted_items()`: Returns items sorted by value

Both `most()` and `least()` raise `ValueError` on an empty counter.
These examples are standalone Python 3 code:

```python
from web.utils import Counter

c = Counter(a=3, b=1, c=1)
assert c.least() == ['b', 'c']
assert c.most() == ['a']
shares = Counter(a=3, b=1)
assert shares.percent('a') == 0.75
assert 100 * shares.percent('a') == 75.0
```

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
- The return value is always the outer `Storage`; the following conversions
  describe its **items**, not the outer object.
- A nonempty list item becomes its last element unless its default is a list.
- An object with a `value` attribute becomes that value unless its default is
  a dictionary (file-like values with `file` and `raw` have special handling).
- Each key is processed once: required names first, then remaining mapping keys,
  in first-occurrence order. Repeating a required name does not repeat conversion;
  a missing required key still raises `KeyError`, even with a default.
- A selected object with both `file` and `raw` is converted with `file.read()`
  from its current position; bytes are not automatically decoded. A dictionary
  default preserves the selected object without this conversion or a data read.
  For a plain list, a dictionary default still selects its last element; a list
  default converts every element and keeps the resulting list.
- No rewind or deduplication by object identity is performed. Different keys
  sharing one stream consume it separately. Attribute getters (including a
  `raw` property) retain their own behavior, so one key conversion is not a
  guarantee of one low-level stream read.

**Examples:**
```python
from web.utils import Storage, storage, storify

outer = storify({'a': 1, 'c': 3}, b=2, c=0)
assert isinstance(outer, Storage)
assert outer == {'a': 1, 'b': 2, 'c': 3}
assert storify({'a': [1, 2]}).a == 2
assert storify({'a': [1, 2]}, a=[]).a == [1, 2]
inner = storage(value=1)
assert storify({'a': inner}).a == 1
assert storify({'a': inner}, a={}).a is inner
```

### `rstrips(text, remove)`
Removes the string `remove` from the right side of `text`.

### `lstrips(text, remove)`
Removes the string `remove` from the left side of `text`.

### `strips(text, remove)`
Removes the string `remove` from both sides of `text`.

### `safestr(obj, encoding="utf-8")`
Normally returns `str(obj)`, not encoded bytes or decoded text. The `encoding`
argument is ignored. For a truthy object with `__next__`, it instead eagerly
consumes the object and returns a **list** of recursive `safestr` conversions.
A normal list or tuple is stringified; this special case is not general iterable
conversion. Use `bytes.decode(encoding)` explicitly when decoding is intended.

```python
from web.utils import safestr, safeunicode

assert safestr(b'abc') == "b'abc'"
assert safestr(b'abc', encoding='not-a-codec') == "b'abc'"
assert safestr(iter([1, b'abc'])) == ['1', "b'abc'"]
assert safestr([1, 2]) == '[1, 2]'
assert b'abc'.decode('utf-8') == 'abc'
assert safeunicode is safestr
```

### `safeunicode(obj, encoding="utf-8")`
Alias for `safestr`, including its ignored encoding and iterator-to-list behavior.

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
Groups a sized, sliceable sequence using `len(seq)` and `seq[i:i + size]`.
For the usual positive integer `size`, the last chunk may be shorter.

**Returns:** A generator of slices: lists for list input, tuples for tuple input,
strings for string input. It does not support arbitrary iterables. Explicitly
materialize a finite iterator first if that memory/consumption cost is intended.

**Example:**
```python
from web.utils import group

assert list(group([1, 2, 3, 4, 5], 2)) == [[1, 2], [3, 4], [5]]
assert list(group((1, 2, 3), 2)) == [(1, 2), (3,)]
assert list(group('abc', 2)) == ['ab', 'c']
assert list(group(list(iter([1, 2, 3])), 2)) == [[1, 2], [3]]
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
Returns a lazy generator over a **sized** iterable, displaying progress on
stderr. Values are yielded unchanged, and the completion line is written when
the generator is exhausted, not merely when its last value has been yielded.
An empty sized input exhausts normally with no progress output.

**Parameters:**
- `x`: Iterable with an accurate `len(x)`. Length is read on first advancement;
  an unsized iterator raises `TypeError` before consuming values. To use a finite
  unsized iterator, explicitly materialize it as a list (which consumes it and
  uses memory). Length must remain consistent during iteration.

**Example:**
```python
import contextlib
import io
from web.utils import iterview

stderr = io.StringIO()
with contextlib.redirect_stderr(stderr):
    assert list(iterview([])) == []
assert stderr.getvalue() == ''
with contextlib.redirect_stderr(stderr):
    assert list(iterview(list(iter([10, 20])))) == [10, 20]
assert '100.0% (2/2)' in stderr.getvalue()
assert stderr.getvalue().endswith('\n')
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
Returns `lst[ind]` for a valid integer index, including valid negative indexes.
Returns the exact `default` object for out-of-range positive **or negative**
indexes. `TypeError` and other non-`IndexError` failures are not suppressed.
This is a sized-sequence/integer-index helper, not a generic indexing adapter;
its existing length/comparison gate is not a general index validation policy.

**Parameters:**
- `lst`: Sized sequence, such as a list, tuple, or string
- `ind`: Integer index
- `default`: Default value if index out of range

**Example:**
```python
from web.utils import listget

assert listget(['a'], 0) == 'a'
assert listget(('a', 'b'), -1) == 'b'
assert listget('ab', -2) == 'a'
assert listget(['a'], 1) is None
default = object()
assert listget(['a'], 1, default) is default
assert listget(['a'], -2, default) is default
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
Alias of the `CaptureStdout` class. Construction returns a callable wrapper
without calling `func`. Calling the wrapper captures what `func` prints to
stdout; it discards the function's return value. Stdout is restored even when
the function raises, and the exception propagates.

**Parameters:**
- `func`: Function to capture output from

**Returns:** `capturestdout(func)` returns a `CaptureStdout` instance;
`capturestdout(func)(*args, **kwargs)` returns the captured string on success.

**WARNING:** Not threadsafe!

**Example:**
```python
from web.utils import CaptureStdout, capturestdout

def idiot():
    print("foo")
    return 42

wrapper = capturestdout(idiot)
assert isinstance(wrapper, CaptureStdout) and callable(wrapper)
assert wrapper() == 'foo\n'
```

### `profile(func)`
Alias of the `Profile` class. Construction returns a callable wrapper without
running `func`. Calling that wrapper runs the function with real `cProfile`.

**Parameters:**
- `func`: Function to profile

**Returns:** `profile(func)` returns a `Profile` instance;
`profile(func)(*args)` returns `(function_result, profiling_info_string)` on
success. Keyword arguments are not forwarded by this wrapper. Report timings
are measurements, not stable example outputs.

The wrapper attempts to remove its temporary file in `finally`, including when
closing the initial descriptor, calling `func`, or constructing the report
raises. As before, an `OSError` from removal is ignored: the result or original
exception is preserved, but a failed removal can leave the file behind. Other
cleanup exceptions propagate and take precedence, retaining any active exception
in `__context__`. A close error is not retried; this does not guarantee descriptor
release for every OS-level close failure. Only the wrapper's own filename is
removed. Changing `tempfile.tempdir` is process-global: run this recipe in a
standalone process, not a concurrent request handler.

**Example:**
```python
import tempfile
from pathlib import Path
from web.utils import Profile, profile

def identity(value):
    return value

wrapper = profile(identity)
assert isinstance(wrapper, Profile) and callable(wrapper)
old_tempdir = tempfile.tempdir
with tempfile.TemporaryDirectory() as directory:
    try:
        tempfile.tempdir = directory
        value = object()
        out, info = wrapper(value)
        assert out is value and isinstance(info, str)
        assert 'took ' in info and 'function calls' in info
        assert list(Path(directory).iterdir()) == []
    finally:
        tempfile.tempdir = old_tempdir
assert not Path(directory).exists()
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
Selection is ordered, using the actual values in `web.config`:

1. A **truthy** `smtp_server` selects SMTP, even if `email_engine` is `"aws"`.
   Presence alone is insufficient: `""`, `False`, and `None` do not select SMTP.
2. Otherwise, `email_engine == "aws"` selects AWS SES via the optional
   `boto.ses.SESConnection` (`aws_access_key_id` / `aws_secret_access_key`).
   This is the legacy `boto` package, not `boto3`; it must be installed/configured
   separately. No fallback to sendmail occurs if the selected backend fails.
3. Otherwise, a subprocess uses `sendmail_path` (default `/usr/sbin/sendmail`).
   The path must identify a working sendmail-compatible program.

The helper returns `None` on normal completion. This reference and its offline
examples do **not** certify live SMTP, AWS credentials/service availability, or
sendmail delivery. They use only synthetic payloads and inert recording seams;
no real message, network connection, or subprocess is launched.

## Constants

### `__all__`
List of public functions and classes exported by this module:
- Storage, storage
- storify
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

The names above are exported through the package root too:

```python
import web
from web import utils

namespace = {}
exec('from web.utils import *', namespace)
assert set(namespace) - {'__builtins__'} == set(utils.__all__)
assert 'storify' in utils.__all__
for name in utils.__all__:
    assert namespace[name] is getattr(utils, name) is getattr(web, name)
```

### `iters`
A tuple-subclass (`_hack`) instance containing exactly `list`, `tuple`, `set`,
and `frozenset`, suitable as the second argument of `isinstance`. It is not a
list of values, an iterator, or a test for all possible iterables.

```python
from web.utils import iters

assert isinstance(iters, tuple) and type(iters) is not tuple
assert iters == (list, tuple, set, frozenset)
assert isinstance([], iters)
assert not isinstance('abc', iters)
assert not isinstance(iter([]), iters)
```

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
Standalone offline dispatch/MIME example. Only the three transport methods are
replaced; `sendmail`, MIME construction and backend selection are real. All
patches are restored on exit. This is a recording seam, **not a delivery recipe**.

```python
from email import message_from_string
from unittest.mock import patch
import web
from web.utils import _EmailMessage, sendmail, storage

records = []
def record(backend):
    def transport(mail, text):
        records.append((backend, mail.from_address, mail.recipients, text))
    return transport

with patch.object(_EmailMessage, 'send_with_smtp', record('smtp')), \
     patch.object(_EmailMessage, 'send_with_aws', record('aws')), \
     patch.object(_EmailMessage, 'default_email_sender', record('sendmail')):
    for settings, expected in [
        (storage(smtp_server='smtp.invalid', email_engine='aws'), 'smtp'),
        (storage(smtp_server='', email_engine='aws'), 'aws'),
        (storage(), 'sendmail'),
    ]:
        with patch.object(web.webapi, 'config', settings):
            result = sendmail('sender@example.invalid', 'to@example.invalid',
                'Synthetic subject', 'Harmless body', cc=['cc@example.invalid'],
                attachments=[{'filename': 'sample.bin', 'content': b'harmless',
                              'content_type': 'application/octet-stream'}])
        assert result is None
        backend, sender, recipients, text = records[-1]
        assert backend == expected and sender == 'sender@example.invalid'
        assert recipients == ['to@example.invalid', 'cc@example.invalid']
        message = message_from_string(text)
        assert message['Subject'] == 'Synthetic subject'
        assert message.is_multipart()
        body, attachment = message.get_payload()
        assert body.get_payload(decode=True) == b'Harmless body'
        assert attachment.get_filename() == 'sample.bin'
        assert attachment.get_payload(decode=True) == b'harmless'
assert len(records) == 3
```
