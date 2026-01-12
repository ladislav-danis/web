"""
Session Management
(from web.py)

This module provides session management functionality for web.py applications.
It supports various storage backends including disk, database, and memory stores.
"""

import datetime
import os
import os.path
import pickle
import shutil
import threading
import time
from base64 import decodebytes, encodebytes
from copy import deepcopy
from hashlib import sha1

from . import utils
from . import webapi as web
from .py3helpers import iteritems

__all__ = ["Session", "SessionExpired", "Store", "DiskStore", "DBStore", "MemoryStore"]

web.config.session_parameters = utils.storage(
    {
        "cookie_name": "webpy_session_id",
        "cookie_domain": None,
        "cookie_path": None,
        "samesite": None,
        "timeout": 86400,  # 24 * 60 * 60, # 24 hours in seconds
        "ignore_expiry": True,
        "ignore_change_ip": True,
        "secret_key": "fLjUfxqXtfNoIldA0A0J",
        "expired_message": "Session expired",
        "httponly": True,
        "secure": False,
    }
)


class SessionExpired(web.HTTPError):
    """Exception raised when a session has expired.

    Args:
        message (str): The error message to display when the session expires.
    """

    def __init__(self, message):
        web.HTTPError.__init__(self, "200 OK", {}, data=message)


class Session:
    """Session management for web.py.

    This class handles session creation, storage, and retrieval for web applications.
    It supports various storage backends through the Store interface.

    Args:
        app: The web.py application instance to attach the session processor to.
        store: The session store instance to use for persisting sessions.
        initializer: Optional initializer function or dict to set initial session values.

    Examples:
        >>> import web
        >>> from web.session import Session, DiskStore
        >>> app = web.application((), globals())
        >>> store = DiskStore('/tmp/sessions')
        >>> session = Session(app, store)
    """

    __slots__ = [
        "store",
        "_initializer",
        "_last_cleanup_time",
        "_config",
        "_data",
        "__getitem__",
        "__setitem__",
        "__delitem__",
    ]

    def __init__(self, app, store, initializer=None):
        """Initialize a new session.

        Args:
            app: The web.py application instance to attach the session processor to.
            store: The session store instance to use for persisting sessions.
            initializer: Optional initializer function or dict to set initial session values.
        """
        self.store = store
        self._initializer = initializer
        self._last_cleanup_time = 0
        self._config = utils.storage(web.config.session_parameters)
        self._data = utils.threadeddict()

        self.__getitem__ = self._data.__getitem__
        self.__setitem__ = self._data.__setitem__
        self.__delitem__ = self._data.__delitem__

        if app:
            app.add_processor(self._processor)

    def __contains__(self, name):
        """Check if a session key exists.

        Args:
            name (str): The session key to check.

        Returns:
            bool: True if the key exists in the session, False otherwise.
        """
        return name in self._data

    def __getattr__(self, name):
        """Get an attribute from the session data.

        Args:
            name (str): The attribute name to retrieve.

        Returns:
            The value of the attribute from session data.
        """
        return getattr(self._data, name)

    def __setattr__(self, name, value):
        """Set an attribute in the session data.

        Args:
            name (str): The attribute name to set.
            value: The value to assign to the attribute.
        """
        if name in self.__slots__:
            object.__setattr__(self, name, value)
        else:
            setattr(self._data, name, value)

    def __delattr__(self, name):
        """Delete an attribute from the session data.

        Args:
            name (str): The attribute name to delete.
        """
        delattr(self._data, name)

    def _processor(self, handler):
        """Application processor to setup session for every request.

        This method is called for each request and handles loading,
        saving, and cleanup of sessions.

        Args:
            handler: The next handler in the application chain.

        Returns:
            The result of the handler function.
        """
        self._cleanup()
        self._load()

        try:
            return handler()
        finally:
            self._save()

    def _load(self):
        """Load the session from the store, by the id from cookie.

        This method retrieves the session ID from cookies, validates it,
        checks for expiration, and loads the session data.
        If no valid session exists, a new one is created.
        """
        cookie_name = self._config.cookie_name
        self.session_id = web.cookies().get(cookie_name)

        # protection against session_id tampering
        if self.session_id and not self._valid_session_id(self.session_id):
            self.session_id = None

        self._check_expiry()
        if self.session_id:
            d = self.store[self.session_id]
            self.update(d)
            self._validate_ip()

        if not self.session_id:
            self.session_id = self._generate_session_id()

            if self._initializer:
                if isinstance(self._initializer, dict):
                    self.update(deepcopy(self._initializer))
                elif hasattr(self._initializer, "__call__"):
                    self._initializer()

        self.ip = web.ctx.ip

    def _check_expiry(self):
        """Check if the session has expired.

        If the session ID is not found in the store, it's considered expired.
        Depending on the configuration, either ignore the expiry or call expired().

        Returns:
            None: If session is valid or ignored.
            SessionExpired: If session has expired and expiry is not ignored.
        """
        # check for expiry
        if self.session_id and self.session_id not in self.store:
            if self._config.ignore_expiry:
                self.session_id = None
            else:
                return self.expired()

    def _validate_ip(self):
        """Validate that the session IP matches the current request IP.

        If the IP has changed and ignore_change_ip is False, the session expires.

        Returns:
            None: If IP validation passes.
            SessionExpired: If IP has changed and change is not ignored.
        """
        # check for change of IP
        if self.session_id and self.get("ip", None) != web.ctx.ip:
            if not self._config.ignore_change_ip:
                return self.expired()

    def _save(self):
        """Save the current session data to storage.

        This method prepares session data for saving by removing internal keys,
        sets cookies, and stores the session in the configured store.
        """
        current_values = dict(self._data)
        del current_values["session_id"]
        del current_values["ip"]

        if not self.get("_killed"):
            self._setcookie(self.session_id)
            self.store[self.session_id] = dict(self._data)
        else:
            if web.cookies().get(self._config.cookie_name):
                self._setcookie(self.session_id, expires=-1)

    def _setcookie(self, session_id, expires="", **kw):
        """Set the session cookie in the HTTP response.

        Args:
            session_id (str): The session identifier to set in the cookie.
            expires (str): Expiration time for the cookie.
            **kw: Additional keyword arguments for cookie settings.
        """
        cookie_name = self._config.cookie_name
        cookie_domain = self._config.cookie_domain
        cookie_path = self._config.cookie_path
        httponly = self._config.httponly
        secure = self._config.secure
        samesite = kw.get("samesite", self._config.get("samesite", None))
        web.setcookie(
            cookie_name,
            session_id,
            expires=expires,
            domain=cookie_domain,
            httponly=httponly,
            secure=secure,
            path=cookie_path,
            samesite=samesite,
        )

    def _generate_session_id(self):
        """Generate a random id for session.

        Returns:
            str: A unique session identifier.
        """
        while True:
            rand = os.urandom(16)
            now = time.time()
            secret_key = self._config.secret_key

            hashable = f"{rand}{now}{utils.safestr(web.ctx.ip)}{secret_key}"
            session_id = sha1(hashable.encode("utf-8")).hexdigest()
            if session_id not in self.store:
                break
        return session_id

    def _valid_session_id(self, session_id):
        """Validate that a session ID is properly formatted.

        Args:
            session_id (str): The session ID to validate.

        Returns:
            bool: True if the session ID is valid, False otherwise.
        """
        rx = utils.re_compile("^[0-9a-fA-F]+$")
        return rx.match(session_id)

    def _cleanup(self):
        """Cleanup the stored sessions.

        Removes expired sessions from storage based on the configured timeout.
        This method is called periodically to maintain session storage.
        """
        current_time = time.time()
        timeout = self._config.timeout
        if current_time - self._last_cleanup_time > timeout:
            self.store.cleanup(timeout)
            self._last_cleanup_time = current_time

    def expired(self):
        """Called when an expired session is accessed.

        Marks the session as killed, saves it, and raises a SessionExpired exception.

        Raises:
            SessionExpired: Exception indicating that the session has expired.
        """
        self._killed = True
        self._save()
        raise SessionExpired(self._config.expired_message)

    def kill(self):
        """Kill the session, make it no longer available.

        Removes the session from storage and marks it as killed.
        """
        del self.store[self.session_id]
        self._killed = True


class Store:
    """Base class for session stores.

    All session store implementations should inherit from this class and implement
    its methods.
    """

    def __contains__(self, key):
        """Check if a session exists in the store.

        Args:
            key (str): The session identifier to check.

        Returns:
            bool: True if the session exists, False otherwise.

        Raises:
            NotImplementedError: If not implemented by subclass.
        """
        raise NotImplementedError()

    def __getitem__(self, key):
        """Get a session from the store.

        Args:
            key (str): The session identifier to retrieve.

        Returns:
            dict: The session data.

        Raises:
            KeyError: If the session does not exist.
            NotImplementedError: If not implemented by subclass.
        """
        raise NotImplementedError()

    def __setitem__(self, key, value):
        """Set a session in the store.

        Args:
            key (str): The session identifier to set.
            value (dict): The session data to store.

        Raises:
            NotImplementedError: If not implemented by subclass.
        """
        raise NotImplementedError()

    def cleanup(self, timeout):
        """Remove all expired sessions from the store.

        Args:
            timeout (float): The timeout in seconds after which sessions expire.

        Raises:
            NotImplementedError: If not implemented by subclass.
        """
        raise NotImplementedError()

    def encode(self, session_dict):
        """Encode session dict as a string for storage.

        Args:
            session_dict (dict): The session data to encode.

        Returns:
            bytes: The encoded session data.
        """
        pickled = pickle.dumps(session_dict)
        return encodebytes(pickled)

    def decode(self, session_data):
        """Decode stored session data back to a dict.

        Args:
            session_data (bytes or str): The encoded session data.

        Returns:
            dict: The decoded session data.
        """
        if isinstance(session_data, str):
            session_data = session_data.encode()

        pickled = decodebytes(session_data)
        return pickle.loads(pickled)


class DiskStore(Store):
    """Store for saving a session on disk.

    Examples:
        >>> import tempfile
        >>> root = tempfile.mkdtemp()
        >>> s = DiskStore(root)
        >>> s['a'] = 'foo'
        >>> s['a']
        'foo'
        >>> time.sleep(0.01)
        >>> s.cleanup(0.01)
        >>> s['a']
        Traceback (most recent call last):
            ...
        KeyError: 'a'

    Args:
        root (str): The directory path where sessions will be stored.
    """

    def __init__(self, root):
        """Initialize the disk store.

        Args:
            root (str): The directory path where sessions will be stored.
        """
        # if the storage root doesn't exists, create it.
        if not os.path.exists(root):
            os.makedirs(os.path.abspath(root))
        self.root = root

    def _get_path(self, key):
        """Get the file path for a session key.

        Args:
            key (str): The session identifier.

        Returns:
            str: The full file path for the session.

        Raises:
            ValueError: If the key contains invalid characters.
        """
        if os.path.sep in key:
            raise ValueError("Bad key: %s" % repr(key))
        return os.path.join(self.root, key)

    def __contains__(self, key):
        """Check if a session exists in the store.

        Args:
            key (str): The session identifier to check.

        Returns:
            bool: True if the session exists, False otherwise.
        """
        path = self._get_path(key)
        return os.path.exists(path)

    def __getitem__(self, key):
        """Get a session from the store.

        Args:
            key (str): The session identifier to retrieve.

        Returns:
            dict: The session data.

        Raises:
            KeyError: If the session does not exist.
        """
        path = self._get_path(key)

        if os.path.exists(path):
            with open(path, "rb") as fh:
                pickled = fh.read()
            return self.decode(pickled)
        else:
            raise KeyError(key)

    def __setitem__(self, key, value):
        """Set a session in the store.

        Args:
            key (str): The session identifier to set.
            value (dict): The session data to store.
        """
        path = self._get_path(key)
        pickled = self.encode(value)
        try:
            tname = path + "." + threading.current_thread().name
            f = open(tname, "wb")
            try:
                f.write(pickled)
            finally:
                f.close()
                shutil.move(tname, path)  # atomic operation
        except OSError:
            pass

    def __delitem__(self, key):
        """Delete a session from the store.

        Args:
            key (str): The session identifier to delete.
        """
        path = self._get_path(key)
        if os.path.exists(path):
            os.remove(path)

    def cleanup(self, timeout):
        """Remove all expired sessions from the disk store.

        Args:
            timeout (float): The timeout in seconds after which sessions expire.
        """
        if not os.path.isdir(self.root):
            return

        now = time.time()
        for f in os.listdir(self.root):
            path = self._get_path(f)
            atime = os.stat(path).st_atime
            if now - atime > timeout:
                if os.path.isdir(path):
                    shutil.rmtree(path)
                else:
                    os.remove(path)


class DBStore(Store):
    """Store for saving a session in database.

    Requires a table with the following columns:
        session_id CHAR(128) UNIQUE NOT NULL,
        atime DATETIME NOT NULL default current_timestamp,
        data TEXT

    Args:
        db: Database connection object.
        table_name (str): Name of the table to use for storing sessions.
    """

    def __init__(self, db, table_name):
        """Initialize the database store.

        Args:
            db: Database connection object.
            table_name (str): Name of the table to use for storing sessions.
        """
        self.db = db
        self.table = table_name

    def __contains__(self, key):
        """Check if a session exists in the database.

        Args:
            key (str): The session identifier to check.

        Returns:
            bool: True if the session exists, False otherwise.
        """
        data = self.db.select(self.table, where="session_id=$key", vars=locals())
        return bool(list(data))

    def __getitem__(self, key):
        """Get a session from the database.

        Args:
            key (str): The session identifier to retrieve.

        Returns:
            dict: The session data.

        Raises:
            KeyError: If the session does not exist.
        """
        now = datetime.datetime.now()
        try:
            s = self.db.select(self.table, where="session_id=$key", vars=locals())[0]
            self.db.update(
                self.table, where="session_id=$key", atime=now, vars=locals()
            )
        except IndexError:
            raise KeyError(key)
        else:
            return self.decode(s.data)

    def __setitem__(self, key, value):
        """Set a session in the database.

        Args:
            key (str): The session identifier to set.
            value (dict): The session data to store.
        """
        # Remove the leading `b` of bytes object (`b"..."`), otherwise encoded
        # value is invalid base64 format.
        pickled = self.encode(value).decode()

        now = datetime.datetime.now()
        if key in self:
            self.db.update(
                self.table,
                where="session_id=$key",
                data=pickled,
                atime=now,
                vars=locals(),
            )
        else:
            self.db.insert(self.table, False, session_id=key, atime=now, data=pickled)

    def __delitem__(self, key):
        """Delete a session from the database.

        Args:
            key (str): The session identifier to delete.
        """
        self.db.delete(self.table, where="session_id=$key", vars=locals())

    def cleanup(self, timeout):
        """Remove all expired sessions from the database.

        Args:
            timeout (float): The timeout in seconds after which sessions expire.
        """
        timeout = datetime.timedelta(
            timeout / (24.0 * 60 * 60)
        )  # timedelta takes numdays as arg
        last_allowed_time = datetime.datetime.now() - timeout
        self.db.delete(self.table, where="$last_allowed_time > atime", vars=locals())


class ShelfStore:
    """Store for saving session using `shelve` module.

    Examples:
        >>> import shelve
        >>> store = ShelfStore(shelve.open('session.shelf'))

    XXX: is shelve thread-safe?

    Args:
        shelf: A shelf object from the shelve module.
    """

    def __init__(self, shelf):
        """Initialize the shelf store.

        Args:
            shelf: A shelf object from the shelve module.
        """
        self.shelf = shelf

    def __contains__(self, key):
        """Check if a session exists in the shelf.

        Args:
            key (str): The session identifier to check.

        Returns:
            bool: True if the session exists, False otherwise.
        """
        return key in self.shelf

    def __getitem__(self, key):
        """Get a session from the shelf.

        Args:
            key (str): The session identifier to retrieve.

        Returns:
            dict: The session data.
        """
        atime, v = self.shelf[key]
        self[key] = v  # update atime
        return v

    def __setitem__(self, key, value):
        """Set a session in the shelf.

        Args:
            key (str): The session identifier to set.
            value (dict): The session data to store.
        """
        self.shelf[key] = time.time(), value

    def __delitem__(self, key):
        """Delete a session from the shelf.

        Args:
            key (str): The session identifier to delete.
        """
        try:
            del self.shelf[key]
        except KeyError:
            pass

    def cleanup(self, timeout):
        """Remove all expired sessions from the shelf.

        Args:
            timeout (float): The timeout in seconds after which sessions expire.
        """
        now = time.time()
        for k in self.shelf:
            atime, v = self.shelf[k]
            if now - atime > timeout:
                del self[k]


class MemoryStore(Store):
    """Store for saving a session in memory.
    Useful where there is limited fs writes on the disk, like
    flash memories

    Data will be saved into a dict:
    k: (time, pydata)

    Args:
        d_store (dict): Optional initial dictionary to use as storage.
    """

    def __init__(self, d_store=None):
        """Initialize the memory store.

        Args:
            d_store (dict): Optional initial dictionary to use as storage.
        """
        if d_store is None:
            d_store = {}
        self.d_store = d_store

    def __contains__(self, key):
        """Check if a session exists in memory.

        Args:
            key (str): The session identifier to check.

        Returns:
            bool: True if the session exists, False otherwise.
        """
        return key in self.d_store

    def __getitem__(self, key):
        """Get a session from memory and update its last access time.

        Args:
            key (str): The session identifier to retrieve.

        Returns:
            dict: The session data.

        Raises:
            KeyError: If the session does not exist.
        """
        t, value = self.d_store[key]
        self.d_store[key] = (time.time(), value)
        return value

    def __setitem__(self, key, value):
        """Set a session in memory.

        Args:
            key (str): The session identifier to set.
            value (dict): The session data to store.
        """
        self.d_store[key] = (time.time(), value)

    def __delitem__(self, key):
        """Delete a session from memory.

        Args:
            key (str): The session identifier to delete.
        """
        del self.d_store[key]

    def cleanup(self, timeout):
        """Remove all expired sessions from memory.

        Args:
            timeout (float): The timeout in seconds after which sessions expire.
        """
        now = time.time()
        to_del = []
        for k, (atime, value) in iteritems(self.d_store):
            if now - atime > timeout:
                to_del.append(k)

        # to avoid exception on "dict change during iterations"
        for k in to_del:
            del self.d_store[k]


if __name__ == "__main__":
    import doctest

    doctest.testmod()
