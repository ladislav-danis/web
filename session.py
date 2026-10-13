"""
Session Management
(from web.py)
"""

import datetime
import hmac
import json
import os
import os.path
import shutil
import threading
import time
from base64 import decodebytes, encodebytes
from copy import deepcopy
from hashlib import sha256, sha1

from . import utils
from . import webapi as web
from .py3helpers import iteritems

__all__ = ["Session", "SessionExpired", "Store", "DiskStore", "DBStore", "MemoryStore"]

DEFAULT_SECRET_KEY = "fLjUfxqXtfNoIldA0A0J"

web.config.session_parameters = utils.storage(
    {
        "cookie_name": "webpy_session_id",
        "cookie_domain": None,
        "cookie_path": None,
        "samesite": None,
        "timeout": 86400,  # 24 * 60 * 60, # 24 hours in seconds
        "ignore_expiry": True,
        "ignore_change_ip": True,
        "secret_key": DEFAULT_SECRET_KEY,
        "expired_message": "Session expired",
        "httponly": True,
        "secure": False,
    }
)


class SessionError(Exception):
    """Base exception for session errors."""

    pass


class SessionSecretRequired(SessionError):
    """Raised when the default secret key is still configured."""

    pass


class SessionTamperedError(SessionError):
    """Raised when session data signature verification fails."""

    pass


class SessionLegacyRejected(SessionTamperedError):
    """Raised for recognized unsigned legacy data, without deserializing it."""

    pass


class SessionExpired(web.HTTPError):
    def __init__(self, message):
        web.HTTPError.__init__(self, "200 OK", {}, data=message)


class Session:
    """Session management for web.py"""

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
        self.store = store
        self._initializer = initializer
        self._last_cleanup_time = 0
        self._config = utils.storage(web.config.session_parameters)
        self._data = utils.threadeddict()

        # P0-3: Require explicit secret key
        if self._config.secret_key == DEFAULT_SECRET_KEY:
            raise SessionSecretRequired(
                "The default session secret_key must be changed. "
                "Set web.config.session_parameters.secret_key to a random string."
            )

        # Make secret_key available to store for HMAC signing
        self.store.secret_key = self._config.secret_key

        self.__getitem__ = self._data.__getitem__
        self.__setitem__ = self._data.__setitem__
        self.__delitem__ = self._data.__delitem__

        if app:
            app.add_processor(self._processor)

    def __contains__(self, name):
        return name in self._data

    def __getattr__(self, name):
        return getattr(self._data, name)

    def __setattr__(self, name, value):
        if name in self.__slots__:
            object.__setattr__(self, name, value)
        else:
            setattr(self._data, name, value)

    def __delattr__(self, name):
        delattr(self._data, name)

    def _processor(self, handler):
        """Application processor to setup session for every request"""

        self._cleanup()
        self._load()

        try:
            return handler()
        finally:
            self._save()

    def _load(self):
        """Load the session from the store, by the id from cookie"""
        cookie_name = self._config.cookie_name
        self.session_id = web.cookies().get(cookie_name)

        # protection against session_id tampering
        if self.session_id and not self._valid_session_id(self.session_id):
            self.session_id = None

        self._check_expiry()
        if self.session_id:
            try:
                d = self.store[self.session_id]
            except SessionLegacyRejected:
                # Never reuse an unsigned identity or its request-local fields.
                self._data.clear()
                self.session_id = None
            else:
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
        # check for expiry
        if self.session_id and self.session_id not in self.store:
            if self._config.ignore_expiry:
                self.session_id = None
            else:
                return self.expired()

    def _validate_ip(self):
        # check for change of IP
        if self.session_id and self.get("ip", None) != web.ctx.ip:
            if not self._config.ignore_change_ip:
                return self.expired()

    def _save(self):
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
        """Generate a random id for session"""

        while True:
            rand = os.urandom(16)
            now = time.time()
            secret_key = self._config.secret_key

            hashable = f"{rand}{now}{utils.safestr(web.ctx.ip)}{secret_key}"
            session_id = sha256(hashable.encode("utf-8")).hexdigest()
            if session_id not in self.store:
                break
        return session_id

    def _valid_session_id(self, session_id):
        rx = utils.re_compile("^[0-9a-fA-F]+$")
        return rx.match(session_id)

    def _cleanup(self):
        """Cleanup the stored sessions"""
        current_time = time.time()
        timeout = self._config.timeout
        if current_time - self._last_cleanup_time > timeout:
            self.store.cleanup(timeout)
            self._last_cleanup_time = current_time

    def expired(self):
        """Called when an expired session is atime"""
        self._killed = True
        self._save()
        raise SessionExpired(self._config.expired_message)

    def kill(self):
        """Kill the session, make it no longer available"""
        del self.store[self.session_id]
        self._killed = True


class Store:
    """Base class for session stores"""

    def __contains__(self, key):
        raise NotImplementedError()

    def __getitem__(self, key):
        raise NotImplementedError()

    def __setitem__(self, key, value):
        raise NotImplementedError()

    def cleanup(self, timeout):
        """removes all the expired sessions"""
        raise NotImplementedError()

    def _sign(self, data: bytes) -> bytes:
        """Sign data with HMAC-SHA256 using the secret key."""
        secret = self.secret_key.encode("utf-8")
        signature = hmac.new(secret, data, sha256).hexdigest()
        return signature.encode("utf-8") + b"." + data

    def _verify(self, signed_data: bytes) -> bytes:
        """Verify HMAC signature and return raw data. Raises SessionTamperedError on failure."""
        secret = self.secret_key.encode("utf-8")
        try:
            sig_part, data_part = signed_data.split(b".", 1)
        except ValueError:
            raise SessionTamperedError("Malformed session data: missing signature delimiter")

        expected_sig = hmac.new(secret, data_part, sha256).hexdigest().encode("utf-8")

        if not hmac.compare_digest(sig_part, expected_sig):
            raise SessionTamperedError("Session data signature verification failed")

        return data_part

    def encode(self, session_dict):
        """encodes session dict as a signed JSON string"""
        json_data = json.dumps(session_dict).encode("utf-8")
        signed = self._sign(json_data)
        return encodebytes(signed)

    def decode(self, session_data):
        """decodes the signed JSON data to get back the session dict"""
        if isinstance(session_data, str):
            session_data = session_data.encode()

        # Strip whitespace that may be added by base64 decoding in storage
        session_data = session_data.strip()

        decoded = decodebytes(session_data)

        # Recognized unsigned legacy formats must never be deserialized.
        if decoded[0:1] in (b"\x80", b"\x8a", b"\x90"):
            raise SessionLegacyRejected("Unsigned legacy session data is not supported")

        verified = self._verify(decoded)
        return json.loads(verified)


class DiskStore(Store):
    """
    Store for saving a session on disk.

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
    """

    def __init__(self, root):
        # if the storage root doesn't exists, create it.
        if not os.path.exists(root):
            os.makedirs(os.path.abspath(root))
        self.root = root

    def _get_path(self, key):
        if os.path.sep in key:
            raise ValueError("Bad key: %s" % repr(key))
        return os.path.join(self.root, key)

    def __contains__(self, key):
        path = self._get_path(key)
        return os.path.exists(path)

    def __getitem__(self, key):
        path = self._get_path(key)

        if os.path.exists(path):
            with open(path, "rb") as fh:
                raw = fh.read()
            return self.decode(raw)
        else:
            raise KeyError(key)

    def __setitem__(self, key, value):
        path = self._get_path(key)
        signed_data = self.encode(value)
        try:
            tname = path + "." + threading.current_thread().name
            f = open(tname, "wb")
            try:
                f.write(signed_data)
            finally:
                f.close()
                shutil.move(tname, path)  # atomic operation
        except OSError:
            pass

    def __delitem__(self, key):
        path = self._get_path(key)
        if os.path.exists(path):
            os.remove(path)

    def cleanup(self, timeout):
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
    """Store for saving a session in database
    Needs a table with the following columns:

        session_id CHAR(128) UNIQUE NOT NULL,
        atime DATETIME NOT NULL default current_timestamp,
        data TEXT
    """

    def __init__(self, db, table_name):
        self.db = db
        self.table = table_name

    def __contains__(self, key):
        data = self.db.select(self.table, where="session_id=$key", vars=locals())
        return bool(list(data))

    def __getitem__(self, key):
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
        # encode returns bytes, decode to str for storage in TEXT column
        signed_data = self.encode(value).decode("ascii")

        now = datetime.datetime.now()
        if key in self:
            self.db.update(
                self.table,
                where="session_id=$key",
                data=signed_data,
                atime=now,
                vars=locals(),
            )
        else:
            self.db.insert(self.table, False, session_id=key, atime=now, data=signed_data)

    def __delitem__(self, key):
        self.db.delete(self.table, where="session_id=$key", vars=locals())

    def cleanup(self, timeout):
        timeout = datetime.timedelta(
            timeout / (24.0 * 60 * 60)
        )  # timedelta takes numdays as arg
        last_allowed_time = datetime.datetime.now() - timeout
        self.db.delete(self.table, where="$last_allowed_time > atime", vars=locals())


class ShelfStore:
    """Store for saving session using `shelve` module.

        import shelve
        store = ShelfStore(shelve.open('session.shelf'))
    """

    def __init__(self, shelf):
        self.shelf = shelf
        self.lock = threading.Lock()

    def __contains__(self, key):
        with self.lock:
            return key in self.shelf

    def __getitem__(self, key):
        with self.lock:
            atime, v = self.shelf[key]
            self.shelf[key] = time.time(), v  # update atime
            return v

    def __setitem__(self, key, value):
        with self.lock:
            self.shelf[key] = time.time(), value

    def __delitem__(self, key):
        with self.lock:
            try:
                del self.shelf[key]
            except KeyError:
                pass

    def cleanup(self, timeout):
        now = time.time()
        with self.lock:
            # We must convert keys to a list to avoid "dictionary changed size during iteration"
            for k in list(self.shelf.keys()):
                atime, v = self.shelf[k]
                if now - atime > timeout:
                    try:
                        del self.shelf[k]
                    except KeyError:
                        pass


class MemoryStore(Store):
    """Store for saving a session in memory.
    Useful where there is limited fs writes on the disk, like
    flash memories

    Data will be saved into a dict:
    k: (time, pydata)
    """

    def __init__(self, d_store=None):
        if d_store is None:
            d_store = {}
        self.d_store = d_store

    def __contains__(self, key):
        return key in self.d_store

    def __getitem__(self, key):
        """Return the value and update the last seen value"""
        t, value = self.d_store[key]
        self.d_store[key] = (time.time(), value)
        return value

    def __setitem__(self, key, value):
        self.d_store[key] = (time.time(), value)

    def __delitem__(self, key):
        del self.d_store[key]

    def cleanup(self, timeout):
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
