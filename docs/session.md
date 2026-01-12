# Web Session Management Documentation

This document describes the session management functionality in `web/session.py`, which provides tools for managing user sessions in web.py applications.

## Overview

The session module implements a flexible session management system that can store session data in various backends including disk, database, memory, and shelf storage. It handles session creation, validation, cleanup, and cookie management automatically.

## Classes

### `SessionExpired`
Exception raised when a session has expired.

#### Constructor
```python
def __init__(self, message)
```

**Parameters:**
- `message` (str): Error message to display when session expires

### `Session`
Main session class that manages user sessions.

#### Constructor
```python
def __init__(self, app, store, initializer=None)
```

**Parameters:**
- `app`: The web.py application instance
- `store`: Session storage backend (DiskStore, DBStore, etc.)
- `initializer`: Optional function or dict to initialize new sessions

#### Methods
- `__contains__(self, name)`: Check if session contains a key
- `__getattr__(self, name)`: Get attribute from session data
- `__setattr__(self, name, value)`: Set attribute on session data
- `__delattr__(self, name)`: Delete attribute from session data
- `_processor(self, handler)`: Application processor for handling sessions
- `_load(self)`: Load session data from storage
- `_check_expiry(self)`: Check if session has expired
- `_validate_ip(self)`: Validate IP address hasn't changed
- `_save(self)`: Save session data to storage
- `_setcookie(self, session_id, expires="", **kw)`: Set session cookie
- `_generate_session_id(self)`: Generate a unique session ID
- `_valid_session_id(self, session_id)`: Validate session ID format
- `_cleanup(self)`: Cleanup expired sessions
- `expired(self)`: Handle expired session
- `kill(self)`: Kill (delete) the current session

### `Store`
Base class for all session storage backends.

#### Methods
- `__contains__(self, key)`: Check if key exists in store
- `__getitem__(self, key)`: Get item from store
- `__setitem__(self, key, value)`: Set item in store
- `cleanup(self, timeout)`: Remove expired sessions
- `encode(self, session_dict)`: Encode session data for storage
- `decode(self, session_data)`: Decode session data from storage

### `DiskStore`
Session storage that saves sessions to the filesystem.

#### Constructor
```python
def __init__(self, root)
```

**Parameters:**
- `root` (str): Directory path where sessions will be stored

#### Methods
- `_get_path(self, key)`: Get file path for session
- `__contains__(self, key)`: Check if session exists
- `__getitem__(self, key)`: Get session data
- `__setitem__(self, key, value)`: Store session data
- `__delitem__(self, key)`: Delete session
- `cleanup(self, timeout)`: Remove expired sessions

### `DBStore`
Session storage that saves sessions to a database.

#### Constructor
```python
def __init__(self, db, table_name)
```

**Parameters:**
- `db`: Database connection object
- `table_name` (str): Name of the sessions table

#### Methods
- `__contains__(self, key)`: Check if session exists in database
- `__getitem__(self, key)`: Get session data from database
- `__setitem__(self, key, value)`: Store session data in database
- `__delitem__(self, key)`: Delete session from database
- `cleanup(self, timeout)`: Remove expired sessions from database

### `MemoryStore`
Session storage that keeps sessions in memory.

#### Constructor
```python
def __init__(self, d_store=None)
```

**Parameters:**
- `d_store` (dict): Optional dictionary to use as storage backend

#### Methods
- `__contains__(self, key)`: Check if session exists in memory
- `__getitem__(self, key)`: Get session data from memory
- `__setitem__(self, key, value)`: Store session data in memory
- `__delitem__(self, key)`: Delete session from memory
- `cleanup(self, timeout)`: Remove expired sessions from memory

### `ShelfStore`
Session storage using Python's `shelve` module.

#### Constructor
```python
def __init__(self, shelf)
```

**Parameters:**
- `shelf`: Shelf object from `shelve.open()`

#### Methods
- `__contains__(self, key)`: Check if session exists in shelf
- `__getitem__(self, key)`: Get session data from shelf
- `__setitem__(self, key, value)`: Store session data in shelf
- `__delitem__(self, key)`: Delete session from shelf
- `cleanup(self, timeout)`: Remove expired sessions from shelf

## Configuration

Session behavior is controlled through `web.config.session_parameters` which includes:

- `cookie_name` (str): Name of the session cookie
- `cookie_domain` (str): Domain for the session cookie
- `cookie_path` (str): Path for the session cookie
- `samesite` (str): SameSite attribute for cookie
- `timeout` (int): Session timeout in seconds (default: 86400)
- `ignore_expiry` (bool): Whether to ignore expired sessions
- `ignore_change_ip` (bool): Whether to ignore IP address changes
- `secret_key` (str): Secret key for session ID generation
- `expired_message` (str): Message to display when session expires
- `httponly` (bool): Whether to set HttpOnly flag on cookie
- `secure` (bool): Whether to set Secure flag on cookie

## Usage Examples

### Basic Session Setup
```python
import web
from web import session

# Create a session store
store = session.DiskStore('/tmp/sessions')

# Create session object
session = session.Session(app, store)

# Use in application handlers
class Index:
    def GET(self):
        session.count = session.get('count', 0) + 1
        return f"Count: {session.count}"
```

### Database Session Store
```python
# Using database session store
db = web.database(dbn='sqlite', db='mydb')
store = session.DBStore(db, 'sessions_table')
session = session.Session(app, store)
```

### Memory Session Store
```python
# Using memory session store (for testing or limited writes)
store = session.MemoryStore()
session = session.Session(app, store)
```

### Session with Initialization
```python
def init_session():
    session.user = 'guest'
    session.permissions = ['read']

store = session.DiskStore('/tmp/sessions')
session = session.Session(app, store, initializer=init_session)
```

## Features

1. **Multiple Storage Backends**: Disk, database, memory, and shelf storage options
2. **Automatic Cleanup**: Periodic removal of expired sessions
3. **IP Validation**: Optional protection against IP address changes
4. **Cookie Management**: Automatic session cookie handling with security flags
5. **Expiration Handling**: Configurable timeout periods
6. **Thread Safety**: Uses threadeddict for thread-safe session access
7. **Flexible Initialization**: Support for custom session initialization functions
8. **Cross-Version Compatibility**: Works with both Python 2 and 3

## Security Considerations

- Session IDs are generated using SHA1 hashing with secret key
- Sessions can be configured to use HttpOnly and Secure cookie flags
- IP address validation can be enabled to prevent session hijacking
- Session data is encoded/decoded for storage security
