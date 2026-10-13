# Web Session Management Documentation

This document describes the session management functionality in `web/session.py`, which provides tools for managing user sessions in web.py applications.

## Overview

The session module implements a flexible session management system that can store session data in various backends including disk, database, memory, and shelf storage. It handles session creation, validation, cleanup, and cookie management automatically.

## Reading and running the examples

**Configure a persistent application secret before constructing any `Session`,
including one backed by MemoryStore or ShelfStore.** Provision a unique random
secret once in your deployment's secret manager/environment as `SESSION_SECRET_KEY`;
reuse it across restarts and all workers. Do not generate a new key per request or
startup, and do not commit it. The framework does not read this environment variable
itself: each standalone example explicitly assigns it before construction.

`Session` copies `web.config.session_parameters` and assigns the copied key to its
store. Leaving the exact built-in `DEFAULT_SECRET_KEY` raises
`web.session.SessionSecretRequired` immediately. This check is **not** entropy,
length, or nonempty validation: an empty/short key is accepted; a missing config
attribute raises `AttributeError`, and `None` can fail later during signing.
The examples use `os.environ["SESSION_SECRET_KEY"]` to fail on a missing variable;
operators must also reject empty/weak values. Changing global configuration later
does not update an existing Session's copied configuration.

Only fences marked `# Executable:` or `# Executable usage:` are standalone offline examples. Run them with
the provisioned environment variable; disk/SQLite/shelf demos own temporary paths
and clean them up, so they are not persistent deployment stores. A deployed store
needs an application-owned protected path and lifecycle instead. Signatures, data
shapes and handler fragments are reference material, not standalone programs.
The usage examples below exercise real offline requests, not authentication.
Unchanged runtime limitations (missing-record expiry, direct iteration and shared
MemoryStore interleavings) are called out separately; passing examples do not fix them.
Signatures and data-shape fences remain non-executable reference material.

## Classes

### `SessionExpired`

An expiry exception derived from `web.HTTPError`, with status `200 OK` and the
configured expired message as data. Not every expiry path reaches this exception:
see the [missing-record limitation and outer-processor example](#session-expiration-handling).

#### Constructor
```python
def __init__(self, message)
```

**Parameters:**
- `message` (str): Error message to display when session expires

Catch this exception in an outer application processor registered **before**
constructing `Session`, not around operations inside GET; see the executable
[expiration example](#session-expiration-handling).

### `Session`

Main session class that manages request session data. Its processor calls cleanup
and load **before** entering the handler try/finally; after a successful load it
saves in finally, even when the handler raises. A load/cleanup failure bypasses
that finally block (although `expired()` itself attempts a save).

#### Constructor
```python
def __init__(self, app, store, initializer=None)
```

**Parameters:**
- `app`: The web.py application instance (used to add the session processor)
- `store`: Session storage backend (DiskStore, DBStore, MemoryStore, or ShelfStore)
- `initializer`: Optional function or dict to initialize new sessions

**Example:**
```python
# Executable: ### `Session`
import os
import web
from web import session

web.config.session_parameters.secret_key = os.environ["SESSION_SECRET_KEY"]
app = web.application((), {}, autoreload=False)

from tempfile import TemporaryDirectory
with TemporaryDirectory() as root:
    store = session.DiskStore(root)
    sess = session.Session(app, store, initializer={'user': 'guest'})
    assert store.secret_key == os.environ["SESSION_SECRET_KEY"]
```

#### Special Methods
- `__contains__(self, name)`: Check if session contains a key (`key in sess`)
- `__getattr__(self, name)`: Get attribute from session data (`sess.key`)
- `__setattr__(self, name, value)`: Set attribute on session data (`sess.key = value`)
- `__delattr__(self, name)`: Delete attribute from session data (`del sess.key`)
- `__getitem__(self, name)`: Get item from session data (`sess['key']`)
- `__setitem__(self, name, value)`: Set item in session data (`sess['key'] = value`)
- `__delitem__(self, name)`: Delete item from session data (`del sess['key']`)

#### Public Methods

##### `kill()`
Kill (delete) the current session and mark it as expired.

**Handler fragment (requires the configured `sess` instance):**
```python
def POST(self):
    sess.kill()
    raise web.seeother('/login')
```
For an executable request/store example see [Session Kill](#session-kill-logout).

#### Internal Methods (for reference)

- `_processor(self, handler)`: Application processor that wraps handler execution
- `_load(self)`: Load session data from storage based on cookie
- `_check_expiry(self)`: Check if session has expired
- `_validate_ip(self)`: Validate IP address hasn't changed (if configured)
- `_save(self)`: Save session data to storage
- `_setcookie(self, session_id, expires="", **kw)`: Set session cookie
- `_generate_session_id(self)`: Generate a unique session ID
- `_valid_session_id(self, session_id)`: Validate session ID format
- `_cleanup(self)`: Cleanup expired sessions
- `expired(self)`: Handle expired session (raises SessionExpired)

### `Store`

Abstract base class for all session storage backends. Defines the interface that all stores must implement.

#### Methods

##### Required Methods
- `__contains__(self, key)`: Check if key exists in store
- `__getitem__(self, key)`: Get item from store (raises KeyError if not found)
- `__setitem__(self, key, value)`: Set item in store
- `cleanup(self, timeout)`: Remove all expired sessions

##### Utility Methods
- `encode(self, session_dict)`: `json.dumps` → UTF-8 bytes → HMAC-SHA256
  hexadecimal signature + `b'.'` + JSON bytes → `base64.encodebytes`. Returns
  **bytes**, including base64 line breaks; this is authentication, not encryption.
- `decode(self, session_data)`: Accepts bytes or text, strips surrounding whitespace,
  base64-decodes, verifies the modern signature, then applies `json.loads`.

Direct `Store`, `DiskStore` and `DBStore` serialization requires assigning
`store.secret_key` first. `Session` normally does this during construction.
Modern signed-payload tampering or use of a different key raises
`web.session.SessionTamperedError`. This is not a universal parse-error wrapper:
malformed base64 can raise `binascii.Error`, and correctly signed invalid JSON can
raise `json.JSONDecodeError`.

JSON-compatible dictionaries, lists, strings, numbers, booleans and null values
are supported. This is not arbitrary Python-object persistence: tuples become
lists, integer dictionary keys become strings; bytes, sets, datetimes and arbitrary
objects raise `TypeError`, and circular structures fail. The default Python JSON
encoder/decoder also accepts non-finite floats (NaN/Infinity); do not infer strict
finite-JSON validation or type-preserving round trips for every input.

**Legacy trust boundary:** Runtime decoding is fail-closed: after base64 decoding,
a first byte `0x80`, `0x8a` or `0x90` raises
`web.session.SessionLegacyRejected`, a `SessionTamperedError` subclass, **without
unpickling**. This includes malformed data with one of those markers. Other
unsigned data follows normal signature verification and is rejected there; there
is no unsigned fallback, automatic migration or switch to re-enable unpickling.
Modern signed JSON keeps its existing wire format and parsing behavior.

On this specific legacy exception during store retrieval, `Session._load` discards
request-local fields and starts a new session with a new ID and the configured
initializer, then sets the current IP. Configure an unauthenticated/guest initializer
and keep application authentication/authorization gates in place: no old identity,
permissions, CSRF token or other legacy fields are imported. This recovery applies
with either `ignore_expiry` value when the legacy record exists; it does not use
`expired()` or fix the separate missing-record limitation. Normal response saving
sets the replacement cookie and writes a **new** signed record. The old payload is
not rewritten or deleted by rejection, and retrying its cookie cannot authenticate
from it. `DBStore.__getitem__` still updates `atime` **before** decoding, so even a
rejected read can perform an atime-only UPDATE. Ordinary periodic expiry cleanup
is a separate lifecycle operation, not migration or rejection cleanup.

Direct `Store.decode` and persistent-store reads expose `SessionLegacyRejected`;
only the Session load boundary performs the narrow recovery. Modern bad-HMAC,
malformed-base64/JSON and I/O/general store errors retain their existing failure
behavior (including HTTP 500 where applicable), not a blanket guest fallback.
Only locally generated benign dictionaries are used in regression tests; no
production legacy records have been inspected or assumed to exist. Protect store
permissions and backups regardless of this change.

MemoryStore keeps Python values in a dict; ShelfStore uses `shelve` and its own
pickle-based persistence. Neither normally calls `Store.encode/decode` for stored
values, so neither has this signed-JSON verification/rotation guarantee. Treat
shelf files as trusted inputs too. See [rotation policy](#secret-rotation-policy).

### Signed store example

This exercises only the modern format; it is not a legacy-migration command.

```python
# Executable: ### Signed store example
import os
from web import session

store = session.Store()
store.secret_key = os.environ["SESSION_SECRET_KEY"]
payload = store.encode({'user': 'guest', 'permissions': ['read']})
assert isinstance(payload, bytes)
assert store.decode(payload) == {'user': 'guest', 'permissions': ['read']}
```

### `DiskStore`

Session storage that saves sessions to individual files on the filesystem.

#### Constructor
```python
def __init__(self, root)
```

**Parameters:**
- `root` (str): Directory path where sessions will be stored. Created automatically if it doesn't exist.

**Example:**
```python
# Executable: ### `DiskStore`
import os
from tempfile import TemporaryDirectory
from web import session

with TemporaryDirectory() as root:
    store = session.DiskStore(root)
    store.secret_key = os.environ["SESSION_SECRET_KEY"]
    store['example'] = {'user': 'guest'}
    assert store['example'] == {'user': 'guest'}
```

#### Methods

##### File-based Methods
- `_get_path(self, key)`: Get file path for session (raises ValueError if key contains path separator)

##### Standard Store Methods
- `__contains__(self, key)`: Check if session file exists
- `__getitem__(self, key)`: Read and decode session from file
- `__setitem__(self, key, value)`: Write session to file (atomic operation using temp file)
- `__delitem__(self, key)`: Delete session file
- `cleanup(self, timeout)`: Remove session files older than timeout

**Features:**
- Atomic writes using temp file + move
- Automatic directory creation
- Thread-safe file operations

### `DBStore`

Session storage that saves sessions to a database table.

#### Constructor
```python
def __init__(self, db, table_name)
```

**Parameters:**
- `db`: Database connection object (web.py database instance)
- `table_name` (str): Name of the sessions table

#### Database Schema

The sessions table must have the following columns:

| Column | Type | Description |
|--------|------|-------------|
| session_id | CHAR(128) | Unique session identifier (PRIMARY KEY) |
| atime | DATETIME | Last access time (auto-updated) |
| data | TEXT | ASCII text of the base64-encoded signed JSON payload (legacy records may still contain unsigned pickle) |

**Example:**
```python
# Executable: ### `DBStore`
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import web
from web import session

with TemporaryDirectory() as root:
    db = web.database(dbn='sqlite', db=str(Path(root) / 'sessions.db'))
    connection = db.ctx.db
    try:
        db.query("CREATE TABLE sessions (session_id TEXT UNIQUE NOT NULL, "
                 "atime DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, data TEXT)")
        store = session.DBStore(db, 'sessions')
        store.secret_key = os.environ["SESSION_SECRET_KEY"]
        store['example'] = {'user': 'guest'}
        assert store['example'] == {'user': 'guest'}
        assert isinstance(db.select('sessions')[0].data, str)
    finally:
        connection.close()
```

#### Methods

##### Database Methods
- `__contains__(self, key)`: Check if session exists in database
- `__getitem__(self, key)`: Retrieve session and update atime
- `__setitem__(self, key, value)`: Insert or update session
- `__delitem__(self, key)`: Delete session from database
- `cleanup(self, timeout)`: Delete sessions older than timeout

**Features:**
- Automatic atime updates on read
- Supports INSERT or UPDATE based on session existence

### `MemoryStore`

Session storage that keeps sessions in memory using a dictionary. Useful for testing or environments with limited filesystem writes.

#### Constructor
```python
def __init__(self, d_store=None)
```

**Parameters:**
- `d_store` (dict): Optional dictionary to use as storage backend. Defaults to empty dict.

**Example:**
```python
# Executable: ### `MemoryStore`
from web import session

custom_store = {}
store = session.MemoryStore(custom_store)
store['example'] = {'user': 'guest'}
assert store['example'] == {'user': 'guest'}
# Direct MemoryStore operations do not sign values. Session still requires a key.
```

#### Data Structure

Sessions are stored as:
```python
d_store = {
    'session_id': (timestamp, session_data_dict)
}
```

#### Methods

##### Dictionary-based Methods
- `__contains__(self, key)`: Check if key exists in dictionary
- `__getitem__(self, key)`: Get session and update access timestamp
- `__setitem__(self, key, value)`: Store session with current timestamp
- `__delitem__(self, key)`: Delete session from dictionary
- `cleanup(self, timeout)`: Remove sessions older than timeout

**Features:**
- Automatic timestamp updates on access
- No lock around read + timestamp write or cleanup. A concurrent update can be
  overwritten by a reader; cleanup iterates the live dict and then deletes selected
  keys, so concurrent mutation can raise `RuntimeError` or remove a refreshed row.
  Request-local `Session` data is not shared-store synchronization. Coordinate
  shared access separately; this store provides no transactional/concurrent-session
  update guarantee. These are bounded deterministic interleaving characterizations,
  not a throughput or stress-test certification.

### `ShelfStore`

Session storage using Python's `shelve` module for persistent key-value storage.

#### Constructor
```python
def __init__(self, shelf)
```

**Parameters:**
- `shelf`: Shelf object from `shelve.open()`

**Example:**
```python
# Executable: ### `ShelfStore`
import shelve
from pathlib import Path
from tempfile import TemporaryDirectory
from web import session

with TemporaryDirectory() as root:
    with shelve.open(str(Path(root) / 'sessions.shelf')) as shelf:
        store = session.ShelfStore(shelf)
        store['example'] = {'user': 'guest'}
        assert store['example'] == {'user': 'guest'}
# Direct ShelfStore operations are not signed JSON. Never open untrusted shelves.
```

#### Methods

##### Shelve-based Methods
- `__contains__(self, key)`: Check if key exists in shelf
- `__getitem__(self, key)`: Get session and update access timestamp
- `__setitem__(self, key, value)`: Store session with current timestamp
- `__delitem__(self, key)`: Delete session from shelf
- `cleanup(self, timeout)`: Remove sessions older than timeout

**Note:** The shelve module's thread-safety depends on the underlying dbm implementation.

## Configuration

Session behavior is controlled through `web.config.session_parameters`, which is a `utils.storage` object containing:

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `cookie_name` | str | `"webpy_session_id"` | Name of the session cookie |
| `cookie_domain` | str | `None` | Domain for the session cookie |
| `cookie_path` | str | `None` | Path for the session cookie |
| `samesite` | str | `None` | SameSite attribute for cookie (`Lax`, `Strict`, or `None`) |
| `timeout` | int | `86400` (24 hours) | Session timeout in seconds |
| `ignore_expiry` | bool | `True` | Whether to ignore expired sessions (reset instead of error) |
| `ignore_change_ip` | bool | `True` | Whether to ignore IP address changes |
| `secret_key` | str | `"fLjUfxqXtfNoIldA0A0J"` (rejected by Session) | Explicit application secret for ID generation and signed-store HMAC; configure before construction |
| `expired_message` | str | `"Session expired"` | Message to display when session expires |
| `httponly` | bool | `True` | Whether to set HttpOnly flag on cookie |
| `secure` | bool | `False` | Whether to set Secure flag on cookie |

### Configuration Example

```python
# Executable: ### Configuration Example
import os
import web
from web import session

# Update, rather than replace, to retain the other required defaults.
web.config.session_parameters.update(
    cookie_name='my_app_session', timeout=3600,
    httponly=True, secure=True, samesite='Lax')
web.config.session_parameters.secret_key = os.environ["SESSION_SECRET_KEY"]
app = web.application((), {}, autoreload=False)
sess = session.Session(app, session.MemoryStore())
class Index:
    def GET(self):
        sess.visits = sess.get('visits', 0) + 1
        return str(sess.visits)
app.add_mapping('/', Index)
response = app.request('/', https=True)
assert response.status == '200 OK' and response.data == b'1'
assert any('HttpOnly' in value and 'Secure' in value and 'SameSite=Lax' in value
           for key, value in response.header_items if key.lower() == 'set-cookie')
```

## Usage Examples

### Basic Session Setup

```python
# Executable: ### Basic Session Setup
import os
import web
from web import session

web.config.session_parameters.secret_key = os.environ["SESSION_SECRET_KEY"]
app = web.application((), {}, autoreload=False)

from tempfile import TemporaryDirectory
with TemporaryDirectory() as root:
    store = session.DiskStore(root)
    sess = session.Session(app, store)
    class Index:
        def GET(self):
            sess.count = sess.get('count', 0) + 1
            return f"Count: {sess.count}"
    app.add_mapping('/', Index)
    first, second = app.browser(), app.browser()
    assert first.open('/').read() == b'Count: 1'
    assert first.open('/').read() == b'Count: 2'
    assert second.open('/').read() == b'Count: 1'
```

### Database Session Store

```python
# Executable: ### Database Session Store
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import web
from web import session

with TemporaryDirectory() as root:
    db = web.database(dbn='sqlite', db=str(Path(root) / 'sessions.db'))
    connection = db.ctx.db
    try:
        db.query("CREATE TABLE sessions (session_id TEXT UNIQUE NOT NULL, "
                 "atime DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, data TEXT)")
        store = session.DBStore(db, 'sessions')
        web.config.session_parameters.secret_key = os.environ["SESSION_SECRET_KEY"]
        app = web.application((), {}, autoreload=False)
        sess = session.Session(app, store)
        store['example'] = {'user': 'guest'}
        assert store['example'] == {'user': 'guest'}
        assert isinstance(db.select('sessions')[0].data, str)
    finally:
        connection.close()
```

### Memory Session Store (Testing)

```python
# Executable: ### Memory Session Store (Testing)
import os
import web
from web import session

web.config.session_parameters.secret_key = os.environ["SESSION_SECRET_KEY"]
app = web.application((), {}, autoreload=False)

store = session.MemoryStore()
sess = session.Session(app, store)
class Index:
    def GET(self):
        sess.count = sess.get('count', 0) + 1
        return f"Count: {sess.count}"
app.add_mapping('/', Index)
first, second = app.browser(), app.browser()
assert first.open('/').read() == b'Count: 1'
assert first.open('/').read() == b'Count: 2'
assert second.open('/').read() == b'Count: 1'
```

### Session with Initialization

```python
# Executable: ### Session with Initialization
import os
import web
from web import session

web.config.session_parameters.secret_key = os.environ["SESSION_SECRET_KEY"]
app = web.application((), {}, autoreload=False)

def init_session():
    sess.user = 'guest'
    sess.permissions = ['read']
    sess.visits = 0

store = session.MemoryStore()
sess = session.Session(app, store, initializer=init_session)
class Index:
    def GET(self):
        sess.visits += 1
        return f"{sess.user}: {sess.visits} ({','.join(sess.permissions)})"
app.add_mapping('/', Index)
first, second = app.browser(), app.browser()
assert first.open('/').read() == b'guest: 1 (read)'
assert first.open('/').read() == b'guest: 2 (read)'
assert second.open('/').read() == b'guest: 1 (read)'
assert not hasattr(session, 'user')  # Never write user data on the shared module.
```

### Using Dictionary Initializer

```python
# Executable: ### Using Dictionary Initializer
import os
import web
from web import session

web.config.session_parameters.secret_key = os.environ["SESSION_SECRET_KEY"]
app = web.application((), {}, autoreload=False)

initializer = {'user': 'guest', 'permissions': ['read'], 'visits': 0}

store = session.MemoryStore()
sess = session.Session(app, store, initializer=initializer)
class Index:
    def GET(self):
        sess.visits += 1
        return f"{sess.user}: {sess.visits} ({','.join(sess.permissions)})"
app.add_mapping('/', Index)
first, second = app.browser(), app.browser()
assert first.open('/').read() == b'guest: 1 (read)'
assert first.open('/').read() == b'guest: 2 (read)'
assert second.open('/').read() == b'guest: 1 (read)'
assert not hasattr(session, 'user')  # Never write user data on the shared module.
```

### Session with Custom IP Validation

```python
# Executable: ### Session with Custom IP Validation
import os
import web
from web import session

web.config.session_parameters.secret_key = os.environ["SESSION_SECRET_KEY"]
app = web.application((), {}, autoreload=False)

# Same-IP smoke only; expiry/error paths are not covered by this example.
web.config.session_parameters.ignore_change_ip = False
store = session.MemoryStore()
sess = session.Session(app, store)
class Index:
    def GET(self):
        sess.count = sess.get('count', 0) + 1
        return f"Count: {sess.count}"
app.add_mapping('/', Index)
first, second = app.browser(), app.browser()
assert first.open('/').read() == b'Count: 1'
assert first.open('/').read() == b'Count: 2'
assert second.open('/').read() == b'Count: 1'
```

### Session Expiration Handling

`Session._processor` calls cleanup and load before GET. A catch inside GET cannot
handle those failures. `application.handle_with_processors` propagates `HTTPError`
subclasses (including `SessionExpired`) through outer processors; ordinary errors
are converted to HTTP 500 at the inner processor boundary.

With `ignore_expiry=True` (the default), a cookie whose record is absent starts a
new session. **Current limitation:** with `ignore_expiry=False`, that missing record
calls `expired()` before `ip` has been loaded. Its `_save()` raises `KeyError('ip')`
before `SessionExpired`, producing HTTP 500 with no replacement/deletion cookie.
An outer `SessionExpired` catch does not repair this bug; do not broadly catch
`KeyError` or all exceptions and turn failures into successful/authenticated requests.

An existing record with a changed IP and `ignore_change_ip=False` does reach
`SessionExpired`, because the saved `ip` was loaded. The following bounded example
handles **that** path, changes its default 200 to an explicit 400, and proves GET
was not called. `expired()` marks the cookie for expiry but does not delete the
existing stored record. There is no authentication or authorization in this demo.

```python
# Executable usage: ### Session Expiration Handling
import os
from http.cookies import SimpleCookie
import web
from web import session

web.config.session_parameters.secret_key = os.environ["SESSION_SECRET_KEY"]
web.config.session_parameters.update(ignore_expiry=False, ignore_change_ip=False)
app = web.application((), {}, autoreload=False)
seen = []

def handle_expiry(handler):
    try:
        return handler()
    except session.SessionExpired:
        seen.append('expiry')
        raise web.HTTPError('400 Bad Request', {}, 'Session expired; start again')

# Registration order matters: this processor must surround the Session processor.
app.add_processor(handle_expiry)
store = session.MemoryStore()
sess = session.Session(app, store, initializer={'visits': 0})

class Index:
    def GET(self):
        seen.append('GET')
        sess.visits += 1
        return str(sess.visits)

app.add_mapping('/', Index)
first = app.request('/', env={'REMOTE_ADDR': '192.0.2.1'})
assert first.status == '200 OK' and first.data == b'1'
cookies = SimpleCookie()
for key, value in first.header_items:
    if key.lower() == 'set-cookie':
        cookies.load(value)
sid = cookies['webpy_session_id'].value
headers = {'Cookie': 'webpy_session_id=' + sid}
valid = app.request('/', headers=headers, env={'REMOTE_ADDR': '192.0.2.1'})
assert valid.status == '200 OK' and valid.data == b'2'
changed = app.request('/', headers=headers, env={'REMOTE_ADDR': '192.0.2.2'})
assert changed.status == '400 Bad Request'
assert changed.data == b'Session expired; start again'
assert seen == ['GET', 'GET', 'expiry']
assert store[sid]['visits'] == 2  # no handler/save of new data on expiry
expired_cookie = SimpleCookie()
for key, value in changed.header_items:
    if key.lower() == 'set-cookie':
        expired_cookie.load(value)
assert expired_cookie['webpy_session_id']['expires']
# A fresh client with no cookie starts over; no identity has been authenticated.
assert app.request('/', env={'REMOTE_ADDR': '192.0.2.2'}).data == b'1'
```

### Session Kill (Logout)

```python
# Executable: ### Session Kill (Logout)
import os
import web
from web import session

web.config.session_parameters.secret_key = os.environ["SESSION_SECRET_KEY"]
app = web.application((), {}, autoreload=False)

store = session.MemoryStore()
sess = session.Session(app, store)
class Index:
    def GET(self):
        sess.visits = sess.get('visits', 0) + 1
        return str(sess.visits)
class Logout:
    def POST(self):
        sess.kill()
        raise web.seeother('/login')
app.add_mapping('/', Index)
app.add_mapping('/logout', Logout)
first = app.request('/')
from http.cookies import SimpleCookie
cookies = SimpleCookie()
for key, value in first.header_items:
    if key.lower() == 'set-cookie':
        cookies.load(value)
sid = cookies['webpy_session_id'].value
assert sid in store
response = app.request('/logout', method='POST', data='',
                       headers={'Cookie': 'webpy_session_id=' + sid})
assert response.status == '303 See Other' and sid not in store
assert app.request('/').data == b'1'
# Supply authentication/CSRF policy separately in a real application.
```

### Shelf Store Example

```python
# Executable: ### Shelf Store Example
import os
import web
from web import session

web.config.session_parameters.secret_key = os.environ["SESSION_SECRET_KEY"]
app = web.application((), {}, autoreload=False)

import shelve
from pathlib import Path
from tempfile import TemporaryDirectory
with TemporaryDirectory() as root:
    with shelve.open(str(Path(root) / 'sessions.shelf')) as shelf:
        store = session.ShelfStore(shelf)
        sess = session.Session(app, store)
        class Index:
            def GET(self):
                sess.count = sess.get('count', 0) + 1
                return f"Count: {sess.count}"
        app.add_mapping('/', Index)
        first, second = app.browser(), app.browser()
        assert first.open('/').read() == b'Count: 1'
        assert first.open('/').read() == b'Count: 2'
        assert second.open('/').read() == b'Count: 1'
```

## Features

1. **Multiple Storage Backends**: Disk, database, memory, and shelf storage options
2. **Automatic Cleanup**: Periodic removal of expired sessions based on timeout
3. **IP Validation**: Optional protection against IP address changes (configurable)
4. **Cookie Management**: Automatic session cookie handling with security flags (HttpOnly, Secure, SameSite)
5. **Expiration Handling**: Configurable timeout/reset policy; the missing-record error path above is not graceful
6. **Thread-local Data**: Uses `threadeddict` for per-thread request state, not locking or transactions across shared-store operations
7. **Flexible Initialization**: Support for custom session initialization functions or dictionaries
8. **Python Version**: The current package import chain includes session f-strings and function annotations, requiring Python 3 syntax. Python 2 was not executed or certified; this is not a guarantee for every Python 3 release
9. **Session ID Validation**: Applies the permissive hexadecimal regex described below; format checks alone do not authenticate a cookie or prevent tampering
10. **Atomic Operations**: DiskStore uses atomic file operations for reliability

## Security Considerations

### Session ID Generation

`_generate_session_id()` uses **SHA-256**, returning 64 lowercase hexadecimal
characters. It hashes the UTF-8 encoding of the concatenated string representations
of 16 bytes from `os.urandom(16)`, `time.time()`, `utils.safestr(web.ctx.ip)` and the
copied secret key (the implementation uses an f-string). It retries when that ID
already exists in the store. Generation/check is not an atomic reservation across
workers; no universal collision/concurrency guarantee is implied.

The separate `_valid_session_id()` uses `re.match` with `^[0-9a-fA-F]+$`, **not** a
64-character fullmatch. Short/long and uppercase hex strings are accepted, and
Python's `$` also allows a final newline (`'abc\n'` matches). Empty strings,
non-hex letters and surrounding spaces fail. These are direct-validator results,
not a promise that every such spelling survives HTTP cookie parsing. The format
check is not cryptographic authentication of a session ID or an authorization policy.

### Cookie Security

The following cookie security features are available:

| Feature | Description | Recommendation |
|---------|-------------|----------------|
| `httponly` | Prevents JavaScript access to cookie | Enable (`True`) |
| `secure` | Only send cookie over HTTPS | Enable in production (`True`) |
| `samesite` | Controls cross-site request sending | Set to `Lax` or `Strict` |
| `cookie_domain` | Restrict cookie to specific domain | Set when needed |
| `cookie_path` | Restrict cookie to specific path | Set when needed |

### IP Address Validation

When `ignore_change_ip` is `False`, the session will expire if the client's IP address changes. This provides protection against session hijacking but may cause issues for users with dynamic IPs or when using proxies.

### Best Practices

1. **Use HTTPS in production**: Always set `secure=True` when using HTTPS
2. **Configure secret_key before construction (required)**: Use a unique random persistent application secret, shared by all workers; the exact built-in default raises `SessionSecretRequired`, even with MemoryStore or ShelfStore. Do not generate a fresh key per request/restart.
3. **Set appropriate timeout**: Configure timeout based on your application's needs
4. **Enable IP validation**: Consider enabling `ignore_change_ip=False` for sensitive applications
5. **Use HttpOnly**: Keep `httponly=True` to restrict JavaScript access to the session cookie. It does not escape response HTML or prevent XSS; use context-appropriate output escaping and other XSS defenses. An XSS payload can still act through the victim's browser.
6. **Clean up sessions**: Regularly clean up old session files from DiskStore
7. **Secure storage**: Ensure session storage directories have appropriate permissions

### Secret rotation policy

For modern signed JSON in DiskStore/DBStore, a different key rejects the old
payload with `SessionTamperedError`; that error is not itself a graceful logout
workflow. Coordinate every writer/worker to use the new persistent secret and
recreate/restart Sessions to take the new configuration. Mixed-key writers cannot
reliably read one another's signed payloads.

Do **not** promise that key rotation logs out every session: MemoryStore/ShelfStore
do not verify signed JSON on their normal data path. Unsigned legacy records on
the Store decoder path are rejected regardless of the configured key; changing a
key is neither migration nor a universal logout workflow. If all sessions must be
invalidated, separately plan explicit invalidation of the relevant backing stores,
including in-memory/shelf state, while coordinating every writer. This is an
operator policy, not authorization to delete a production store.

### Coordinated rollout of legacy rejection

This change supplies no migration tool and performs no offline migration,
production-store inspection, key rotation or deployment. Users whose stored
sessions are rejected will need to sign in again after an authorized rollout.

1. Identify and stop/drain **all** writers/workers sharing the store, including
   background jobs and older application versions. Do not mix legacy-reading
   workers with hardened workers; old code could still accept unsigned identities.
2. Take a consistent backup while writers are stopped. Restrict ownership and
   permissions on live stores, backup copies and secrets; never open an untrusted
   shelf or unpickle backup content. Record the deployed revision and restore plan.
3. Install the same hardened version on every worker and configure the same
   strong, persistent application key before constructing Sessions. Keep the
   current key unless a separate coordinated rotation is explicitly authorized;
   rotating it also rejects previously valid signed sessions. Do not restore an
   old unsafe decoder as a runtime compatibility switch.
4. Before reopening traffic, verify the exact deployed revisions/configuration
   on all workers and run a disposable-store smoke: fresh session and ordinary
   signed session succeed; a locally generated benign legacy fixture fails at
   the direct API and yields a new guest ID over HTTP, with login gates still
   enforced. Check replacement-cookie retries and protected-route redirects.
   Compare the fixture's raw old payload before/after separately from DB atime
   updates and new guest inserts. Do not use a production record as a test payload.
5. Resume coordinated workers only after those checks; monitor session errors
   without logging raw session data or keys. Investigate modern signature/parse
   failures rather than swallowing them as migration. Any future offline migration
   would require its own trusted-data policy, explicit approval, backup and
   independent verification; none is delivered or performed here.

Protect both secrets and store integrity: signing authenticates data, it does not
encrypt it. The separate ShelfStore pickle trust boundary is unchanged.

## API Reference

### Session Object

Use `sess` for the instance; `session` below remains the imported module.
Bracket/attribute access, membership and `get` work on request-local values.
Iterate `sess.keys()` or `sess.items()`: direct `for key in sess` is not supported
in this revision and falls back to integer item access, raising `KeyError(0)` for
ordinary string-key data. Missing bracket keys raise `KeyError`; missing attributes
raise `AttributeError`. Avoid names that collide with Session methods/internal data.

```python
# Executable usage: ### Session Object
import os
import web
from web import session

web.config.session_parameters.secret_key = os.environ["SESSION_SECRET_KEY"]
app = web.application((), {}, autoreload=False)
store = session.MemoryStore()
sess = session.Session(app, store)

class Index:
    def GET(self):
        sess['example_key'] = 'value'
        assert sess.example_key == 'value'
        sess.example_key = 'changed'
        assert sess['example_key'] == 'changed'
        assert 'example_key' in sess
        assert sess.get('absent', 'fallback') == 'fallback'
        assert 'example_key' in list(sess.keys())
        assert dict(sess.items())['example_key'] == 'changed'
        del sess['example_key']
        assert 'example_key' not in sess
        sess.example_key = 'again'
        del sess.example_key
        assert 'example_key' not in sess
        return 'mapping operations checked'

app.add_mapping('/', Index)
response = app.request('/')
assert response.status == '200 OK' and response.data == b'mapping operations checked'
assert not hasattr(session, 'example_key')  # never store request state on the module
```

### Session Lifecycle

1. **Request Start**: Session processor runs cleanup, then loads/initializes session data
2. **Handler Execution**: Only after successful load, application code reads/writes session data
3. **Request End**: A finally block saves after handler return or error; it does not cover cleanup/load failures

### Cleanup Process

The cleanup process runs automatically on each request but only performs actual cleanup when the timeout period has elapsed. This minimizes performance impact while ensuring expired sessions are eventually removed.

## See Also

- [`webapi.md`](webapi.md) - Web API module for cookie and context management
- [`utils.md`](utils.md) - Utility functions used by the session module
