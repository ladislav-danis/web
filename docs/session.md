# Web Session Management Documentation

This document describes the session management functionality in `web/session.py`, which provides tools for managing user sessions in web.py applications.

## Overview

The session module implements a flexible session management system that can store session data in various backends including disk, database, memory, and shelf storage. It handles session creation, validation, cleanup, and cookie management automatically.

## Classes

### `SessionExpired`

Exception raised when a session has expired. This is a subclass of `web.HTTPError` and returns a 200 OK response with the expired message as data.

#### Constructor
```python
def __init__(self, message)
```

**Parameters:**
- `message` (str): Error message to display when session expires

**Example:**
```python
try:
    # Session operations
    pass
except session.SessionExpired as e:
    return e.data  # Returns "Session expired"
```

### `Session`

Main session class that manages user sessions. It automatically loads session data on request and saves it after the handler completes.

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
store = session.DiskStore('/tmp/sessions')
sess = session.Session(app, store, initializer={'user': 'guest'})
```

#### Special Methods
- `__contains__(self, name)`: Check if session contains a key (`key in session`)
- `__getattr__(self, name)`: Get attribute from session data (`session.key`)
- `__setattr__(self, name, value)`: Set attribute on session data (`session.key = value`)
- `__delattr__(self, name)`: Delete attribute from session data (`del session.key`)
- `__getitem__(self, name)`: Get item from session data (`session['key']`)
- `__setitem__(self, name, value)`: Set item in session data (`session['key'] = value`)
- `__delitem__(self, name)`: Delete item from session data (`del session['key']`)

#### Public Methods

##### `kill()`
Kill (delete) the current session and mark it as expired.

**Example:**
```python
def POST(self):
    session.kill()
    raise web.seeother('/login')
```

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
- `encode(self, session_dict)`: Encode session dict as base64-encoded pickle string
- `decode(self, session_data)`: Decode base64-encoded pickle string to session dict

**Note:** All stores must implement the required methods. The encode/decode methods provide default serialization using pickle and base64.

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
store = session.DiskStore('/tmp/sessions')
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
| data | TEXT | Base64-encoded pickled session data |

**Example:**
```python
db = web.database(dbn='sqlite', db='mydb')
db.query('''
    CREATE TABLE sessions (
        session_id CHAR(128) UNIQUE NOT NULL,
        atime DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        data TEXT
    )
''')
store = session.DBStore(db, 'sessions')
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
store = session.MemoryStore()
# Or with a custom dict
custom_store = {}
store = session.MemoryStore(custom_store)
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
- Thread-safe access via the underlying dict
- Automatic timestamp updates on access

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
import shelve
shelf = shelve.open('/tmp/sessions.shelf')
store = session.ShelfStore(shelf)
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
| `secret_key` | str | `"fLjUfxqXtfNoIldA0A0J"` | Secret key for session ID generation |
| `expired_message` | str | `"Session expired"` | Message to display when session expires |
| `httponly` | bool | `True` | Whether to set HttpOnly flag on cookie |
| `secure` | bool | `False` | Whether to set Secure flag on cookie |

### Configuration Example

```python
import web

web.config.session_parameters = utils.storage({
    'cookie_name': 'my_app_session',
    'timeout': 3600,  # 1 hour
    'ignore_change_ip': False,  # Enable IP validation
    'httponly': True,
    'secure': True,  # Use in production with HTTPS
    'samesite': 'Lax'
})
```

## Usage Examples

### Basic Session Setup

```python
import web
from web import session

# Create a session store
store = session.DiskStore('/tmp/sessions')

# Create session object
sess = session.Session(app, store)

# Use in application handlers
class Index:
    def GET(self):
        # Initialize counter if not exists
        session.count = session.get('count', 0) + 1
        return f"Count: {session.count}"
```

### Database Session Store

```python
import web
from web import session

# Setup database
db = web.database(dbn='sqlite', db='mydb')
db.query('''
    CREATE TABLE IF NOT EXISTS sessions (
        session_id CHAR(128) UNIQUE NOT NULL,
        atime DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        data TEXT
    )
''')

# Create session store
store = session.DBStore(db, 'sessions')
sess = session.Session(app, store)
```

### Memory Session Store (Testing)

```python
import web
from web import session

# Use memory store for testing
store = session.MemoryStore()
sess = session.Session(app, store)
```

### Session with Initialization

```python
import web
from web import session

def init_session():
    session.user = 'guest'
    session.permissions = ['read']
    session.visits = 0

store = session.DiskStore('/tmp/sessions')
sess = session.Session(app, store, initializer=init_session)
```

### Using Dictionary Initializer

```python
import web
from web import session

initializer = {
    'user': 'guest',
    'permissions': ['read'],
    'theme': 'default'
}

store = session.DiskStore('/tmp/sessions')
sess = session.Session(app, store, initializer=initializer)
```

### Session with Custom IP Validation

```python
import web
from web import session

# Disable ignore_change_ip to enforce IP binding
web.config.session_parameters.ignore_change_ip = False

store = session.DiskStore('/tmp/sessions')
sess = session.Session(app, store)
```

### Session Expiration Handling

```python
import web
from web import session

store = session.DiskStore('/tmp/sessions')
sess = session.Session(app, store)

class Login:
    def POST(self):
        # ... authentication logic ...
        if authenticated:
            session.user = 'john'
            raise web.seeother('/dashboard')

class Dashboard:
    def GET(self):
        try:
            if 'user' not in session:
                raise web.seeother('/login')
            return f"Welcome, {session.user}!"
        except session.SessionExpired as e:
            return e.data  # "Session expired"
```

### Session Kill (Logout)

```python
import web
from web import session

store = session.DiskStore('/tmp/sessions')
sess = session.Session(app, store)

class Logout:
    def POST(self):
        session.kill()
        raise web.seeother('/login')
```

### Shelf Store Example

```python
import web
from web import session
import shelve

shelf = shelve.open('/tmp/sessions.shelf')
store = session.ShelfStore(shelf)
sess = session.Session(app, store)

# Don't forget to close the shelf when done
# shelf.close()
```

## Features

1. **Multiple Storage Backends**: Disk, database, memory, and shelf storage options
2. **Automatic Cleanup**: Periodic removal of expired sessions based on timeout
3. **IP Validation**: Optional protection against IP address changes (configurable)
4. **Cookie Management**: Automatic session cookie handling with security flags (HttpOnly, Secure, SameSite)
5. **Expiration Handling**: Configurable timeout periods with graceful handling
6. **Thread Safety**: Uses `threadeddict` for thread-safe session access
7. **Flexible Initialization**: Support for custom session initialization functions or dictionaries
8. **Cross-Version Compatibility**: Works with both Python 2 and 3
9. **Session ID Validation**: Validates session ID format to prevent tampering
10. **Atomic Operations**: DiskStore uses atomic file operations for reliability

## Security Considerations

### Session ID Generation

Session IDs are generated using SHA1 hashing with:
- Random 16-byte value from `os.urandom()`
- Current timestamp
- Client IP address
- Secret key from configuration

This provides strong uniqueness and makes session IDs difficult to predict.

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
2. **Change secret_key**: Replace the default `secret_key` with a unique, random value
3. **Set appropriate timeout**: Configure timeout based on your application's needs
4. **Enable IP validation**: Consider enabling `ignore_change_ip=False` for sensitive applications
5. **Use HttpOnly**: Keep `httponly=True` to prevent XSS attacks
6. **Clean up sessions**: Regularly clean up old session files from DiskStore
7. **Secure storage**: Ensure session storage directories have appropriate permissions

## API Reference

### Session Object

The session object behaves like a dictionary but with attribute-style access:

```python
# Dictionary-style access
session['key'] = 'value'
value = session['key']
del session['key']

# Attribute-style access
session.key = 'value'
value = session.key
del session.key

# Check existence
if 'key' in session:
    print('Key exists')

# Get all keys
for key in session:
    print(key)
```

### Session Lifecycle

1. **Request Start**: Session processor loads session from store
2. **Handler Execution**: Application code reads/writes session data
3. **Request End**: Session processor saves session to store

### Cleanup Process

The cleanup process runs automatically on each request but only performs actual cleanup when the timeout period has elapsed. This minimizes performance impact while ensuring expired sessions are eventually removed.

## See Also

- [`webapi.md`](webapi.md) - Web API module for cookie and context management
- [`utils.md`](utils.md) - Utility functions used by the session module
