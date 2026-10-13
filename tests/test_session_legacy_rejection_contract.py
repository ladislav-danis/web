"""Fail-closed legacy sessions; benign owned fixtures, never deployed data."""
import importlib.util
from pathlib import Path

import pytest

_spec = importlib.util.spec_from_file_location(
    '_legacy_security_helpers', Path(__file__).with_name('test_session_security_contract.py'))
_helpers = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_helpers)
probe = _helpers.probe


def test_unsigned_benign_dict_is_rejected(tmp_path, record_property):
    probe(r'''
        import base64
        import pickle
        store = session.Store()
        store.secret_key = os.environ['SESSION_SECRET_KEY']
        payload = base64.encodebytes(pickle.dumps({'logged_in': 1}, protocol=2))
        raises(session.SessionTamperedError, lambda: store.decode(payload))
        print(json.dumps({'unsigned_benign_dict_rejected': True}))
    ''', tmp_path, record_property)


HTTP_SETUP = r'''
import base64
import pickle
from contextlib import ExitStack
from datetime import datetime, timedelta
from http.cookies import SimpleCookie
from tempfile import TemporaryDirectory

stack = ExitStack()
root = Path(stack.enter_context(TemporaryDirectory()))
old_id = 'a' * 64
legacy_value = {'session_id': old_id, 'ip': '192.0.2.1', 'logged_in': 1,
                'permissions': 0, 'user_id': 7, 'csrf_token': 'old-token',
                'allowed_modules': ['private'], 'legacy_only': 'must-not-leak'}
legacy = base64.encodebytes(pickle.dumps(legacy_value, protocol=2))
if backend == 'disk':
    store = session.DiskStore(str(root / 'sessions'))
    def put_raw(sid, value):
        (root / 'sessions' / sid).write_bytes(value)
    def raw(sid):
        return (root / 'sessions' / sid).read_bytes()
    def ids():
        return {p.name for p in (root / 'sessions').iterdir()}
else:
    db = web.database(dbn='sqlite', db=str(root / 'sessions.db'))
    stack.callback(db.ctx.db.close)
    db.query('CREATE TABLE sessions (session_id TEXT UNIQUE, atime TEXT, data TEXT)')
    db.query('CREATE TABLE audit (operation TEXT, sid TEXT, old_data TEXT, new_data TEXT, old_atime TEXT, new_atime TEXT)')
    db.query("CREATE TRIGGER upd AFTER UPDATE ON sessions BEGIN INSERT INTO audit VALUES ('UPDATE', OLD.session_id, OLD.data, NEW.data, OLD.atime, NEW.atime); END")
    db.query("CREATE TRIGGER ins AFTER INSERT ON sessions BEGIN INSERT INTO audit VALUES ('INSERT', NEW.session_id, NULL, NEW.data, NULL, NEW.atime); END")
    db.query("CREATE TRIGGER del AFTER DELETE ON sessions BEGIN INSERT INTO audit VALUES ('DELETE', OLD.session_id, OLD.data, NULL, OLD.atime, NULL); END")
    store = session.DBStore(db, 'sessions')
    def put_raw(sid, value):
        db.insert('sessions', False, session_id=sid, data=value.decode('ascii'),
                  atime=str(datetime.now() - timedelta(seconds=10)))
    def raw(sid):
        return db.select('sessions', where='session_id=$sid', vars=locals())[0].data.encode('ascii')
    def ids():
        return {r.session_id for r in db.select('sessions')}
put_raw(old_id, legacy)
if backend == 'db':
    db.query('DELETE FROM audit')
web.config.session_parameters.update(secret_key=os.environ['SESSION_SECRET_KEY'],
    ignore_expiry=ignore_expiry, ignore_change_ip=False, timeout=86400,
    httponly=True, secure=True, samesite='Lax')
app = web.application((), {}, autoreload=False)
initial = {'logged_in': 0, 'permissions': 2, 'user_id': None,
           'csrf_token': None, 'allowed_modules': [], 'visits': 0}
sess = session.Session(app, store, initializer=initial)
seen, errors = [], []
original_internalerror = app.internalerror
def internalerror():
    errors.append(sys.exc_info()[1])
    return original_internalerror()
app.internalerror = internalerror
class Private:
    def GET(self):
        seen.append(dict(sess.items()))
        if not sess.get('logged_in'):
            raise web.seeother('/login')
        return 'private content'
class Login:
    def GET(self):
        seen.append(dict(sess.items()))
        sess.visits += 1
        return 'guest login page'
app.add_mapping('/private', Private)
app.add_mapping('/login', Login)
def request(path='/private', sid=old_id):
    headers = {} if sid is None else {'Cookie': 'webpy_session_id=' + sid}
    return app.request(path, https=True, headers=headers, env={'REMOTE_ADDR': '192.0.2.1'})
def cookies(response):
    jar = SimpleCookie()
    for key, value in response.header_items:
        if key.lower() == 'set-cookie':
            jar.load(value)
    return jar
'''


@pytest.mark.parametrize('backend', ['disk', 'db'])
@pytest.mark.parametrize('ignore_expiry', [True, False])
def test_legacy_http_gets_fresh_guest_not_old_identity(backend, ignore_expiry, tmp_path, record_property):
    probe('backend = ' + repr(backend) + '\nignore_expiry = ' + repr(ignore_expiry) + '\n' + HTTP_SETUP + r'''
try:
    response = request()
    assert response.status == '303 See Other', response.status
    replacement = cookies(response)['webpy_session_id']
    new_id = replacement.value
    assert new_id != old_id and len(new_id) == 64
    assert replacement['secure'] and replacement['httponly'] and replacement['samesite'] == 'Lax'
    assert seen == [dict(initial, session_id=new_id, ip='192.0.2.1')]
    assert store.decode(raw(new_id)) == seen[0]
    assert raw(old_id) == legacy and ids() == {old_id, new_id}
    if backend == 'db':
        changes = list(db.select('audit'))
        assert [(c.operation, c.sid) for c in changes] == [('UPDATE', old_id), ('INSERT', new_id)]
        assert changes[0].old_data == changes[0].new_data == legacy.decode('ascii')
        assert changes[0].old_atime != changes[0].new_atime
    # Replacement cookie is usable; the rejected cookie also cannot authorize a retry.
    login = request('/login', new_id)
    assert login.status == '200 OK' and login.data == b'guest login page'
    assert cookies(login)['webpy_session_id'].value == new_id
    assert store.decode(raw(new_id))['visits'] == 1
    assert request(sid=new_id).status == '303 See Other'
    retry = request()
    assert retry.status == '303 See Other'
    retry_id = cookies(retry)['webpy_session_id'].value
    assert retry_id not in {old_id, new_id}
    fresh = request('/login', None)
    assert fresh.status == '200 OK' and fresh.data == b'guest login page'
    fresh_id = cookies(fresh)['webpy_session_id'].value
    assert fresh_id not in {old_id, new_id, retry_id}
    assert initial['visits'] == 0 and initial['allowed_modules'] == []
    assert all(not d['logged_in'] and d['permissions'] == 2 and d['user_id'] is None
               and d['csrf_token'] is None and 'legacy_only' not in d for d in seen)
    # A legitimate signed fixture still reaches the same authorization gate.
    signed_id = 'b' * 64
    store[signed_id] = dict(initial, session_id=signed_id, ip='192.0.2.1', logged_in=1)
    allowed = request(sid=signed_id)
    assert allowed.status == '200 OK' and allowed.data == b'private content'
    assert cookies(allowed)['webpy_session_id'].value == signed_id
    assert raw(old_id) == legacy
    if backend == 'db':
        old_changes = [c for c in db.select('audit') if c.sid == old_id]
        assert len(old_changes) == 2
        assert all(c.operation == 'UPDATE' and c.old_data == c.new_data == legacy.decode('ascii') for c in old_changes)
    assert not errors
    print(json.dumps({'backend': backend, 'ignore_expiry': ignore_expiry,
                      'guest_recovery': True, 'old_payload_unchanged': True,
                      'no_authentication_from_legacy': True, 'signed_control': True}))
finally:
    if backend == 'db':
        db.ctx.db.close()
    stack.close()
assert not root.exists()
''', tmp_path, record_property)


@pytest.mark.parametrize('api', ['base', 'inherited', 'disk', 'db'])
@pytest.mark.parametrize('kind', ['protocol2', 'protocol5', 'prefix80', 'prefix8a', 'prefix90', 'protocol0', 'json', 'empty'])
def test_direct_decoders_never_unpickle(api, kind, tmp_path, record_property):
    probe('api = ' + repr(api) + '\nkind = ' + repr(kind) + r'''
import base64
import pickle
import _pickle
from contextlib import ExitStack
from tempfile import TemporaryDirectory
with ExitStack() as stack:
    root = Path(stack.enter_context(TemporaryDirectory()))
    class Inherited(session.Store):
        pass
    if api == 'base':
        store = session.Store()
    elif api == 'inherited':
        store = Inherited()
    elif api == 'disk':
        store = session.DiskStore(str(root / 'sessions'))
    else:
        db = web.database(dbn='sqlite', db=str(root / 'sessions.db'))
        stack.callback(db.ctx.db.close)
        store = session.DBStore(db, 'sessions')
    assert session is web.session
    value = {'owned': 'benign'}
    data = {'protocol2': pickle.dumps(value, protocol=2),
            'protocol5': pickle.dumps(value, protocol=5),
            'prefix80': b'\x80', 'prefix8a': b'\x8a', 'prefix90': b'\x90',
            'protocol0': pickle.dumps(value, protocol=0),
            'json': b'{"owned":"unsigned"}', 'empty': b''}[kind]
    class UnpickleCalled(BaseException):
        pass
    def forbidden(*args, **kwargs):
        raise UnpickleCalled('Runtime unpickle is forbidden even for benign input')
    pickle.loads = pickle.load = pickle.Unpickler = forbidden
    _pickle.loads = _pickle.load = _pickle.Unpickler = forbidden
    recognized = kind.startswith('prefix') or kind in ('protocol2', 'protocol5')
    expected = session.SessionLegacyRejected if recognized else session.SessionTamperedError
    assert issubclass(session.SessionLegacyRejected, session.SessionTamperedError)
    for key in ('original-owned-key', 'rotated-owned-key'):
        store.secret_key = key
        for payload in (base64.encodebytes(data), '  ' + base64.encodebytes(data).decode('ascii') + '\n'):
            error = raises(expected, lambda: store.decode(payload))
            assert type(error) is expected
        assert store.decode(store.encode(value)) == value
    print(json.dumps({'api': api, 'kind': kind, 'exception': expected.__name__, 'unpickle_calls': 0}))
assert not root.exists()
''', tmp_path, record_property)


@pytest.mark.parametrize('backend', ['disk', 'db'])
@pytest.mark.parametrize('ignore_expiry', [True, False])
def test_callable_initializer_clears_preload_state(backend, ignore_expiry, tmp_path, record_property):
    probe('backend = ' + repr(backend) + '\nignore_expiry = ' + repr(ignore_expiry) + '\n' + HTTP_SETUP + r'''
try:
    calls = []
    def initialize():
        calls.append(sess.session_id)
        sess.update(initial)
    sess._initializer = initialize
    # Reused thread/request-local state must not survive this recovery boundary.
    def preload(handler):
        sess.update(legacy_value)
        sess._killed = True
        return handler()
    app.processors.insert(0, preload)
    result = request()
    assert result.status == '303 See Other', result.status
    new_id = cookies(result)['webpy_session_id'].value
    assert calls == [new_id] and new_id != old_id
    assert seen == [dict(initial, session_id=new_id, ip='192.0.2.1')]
    assert store.decode(raw(new_id)) == seen[0] and raw(old_id) == legacy
    assert not errors
finally:
    if backend == 'db': db.ctx.db.close()
    stack.close()
assert not root.exists()
''', tmp_path, record_property)


@pytest.mark.parametrize('backend', ['disk', 'db'])
@pytest.mark.parametrize('ignore_expiry', [True, False])
@pytest.mark.parametrize('prefix', [b'\x80', b'\x8a', b'\x90'])
def test_malformed_legacy_markers_recover_without_parsing(backend, ignore_expiry, prefix, tmp_path, record_property):
    probe('backend = ' + repr(backend) + '\nignore_expiry = ' + repr(ignore_expiry) + '\n' + HTTP_SETUP + '\nprefix = ' + repr(prefix) + r'''
try:
    malformed = base64.encodebytes(prefix)
    if backend == 'disk': put_raw(old_id, malformed)
    else: db.update('sessions', where='session_id=$old_id', vars=locals(), data=malformed.decode('ascii'))
    result = request()
    assert result.status == '303 See Other', result.status
    new_id = cookies(result)['webpy_session_id'].value
    assert new_id != old_id and seen == [dict(initial, session_id=new_id, ip='192.0.2.1')]
    assert raw(old_id) == malformed and not errors
finally:
    if backend == 'db': db.ctx.db.close()
    stack.close()
assert not root.exists()
''', tmp_path, record_property)


@pytest.mark.parametrize('backend', ['disk', 'db'])
@pytest.mark.parametrize('kind', ['tamper', 'wrong-key', 'base64', 'json', 'unsigned', 'io', 'store-error'])
def test_other_load_errors_are_not_guest_recovery(backend, kind, tmp_path, record_property):
    probe('backend = ' + repr(backend) + '\nignore_expiry = False\n' + HTTP_SETUP + '\nkind = ' + repr(kind) + r'''
import binascii
import builtins
try:
    signed = store.encode(legacy_value)
    expected_object = None
    if kind == 'tamper':
        signed = base64.encodebytes(base64.decodebytes(signed) + b' ')
        expected = session.SessionTamperedError
    elif kind == 'wrong-key':
        store.secret_key = 'different-owned-key'
        expected = session.SessionTamperedError
    elif kind == 'base64':
        signed = b'a'
        expected = binascii.Error
    elif kind == 'json':
        signed = base64.encodebytes(store._sign(b'not-json'))
        expected = json.JSONDecodeError
    elif kind == 'unsigned':
        signed = base64.encodebytes(b'{"logged_in": 1}')
        expected = session.SessionTamperedError
    else:
        expected = OSError if kind == 'io' else RuntimeError
        expected_object = expected('owned boundary failure')
    if backend == 'disk': put_raw(old_id, signed)
    else: db.update('sessions', where='session_id=$old_id', vars=locals(), data=signed.decode('ascii'))
    if expected_object is not None:
        # Inject the original error exactly at the store retrieval boundary.
        original_getitem = type(store).__getitem__
        def broken_getitem(self, key):
            if key == old_id: raise expected_object
            return original_getitem(self, key)
        type(store).__getitem__ = broken_getitem
    result = request()
    assert result.status == '500 Internal Server Error'
    assert not cookies(result) and not seen and ids() == {old_id}
    assert len(errors) == 1 and type(errors[0]) is expected
    if expected_object is not None: assert errors[0] is expected_object
    assert raw(old_id) == signed
    print(json.dumps({'backend': backend, 'kind': kind, 'error': expected.__name__, 'recovery': False}))
finally:
    if backend == 'db': db.ctx.db.close()
    stack.close()
assert not root.exists()
''', tmp_path, record_property)


# Extend the shared fresh-child isolation for every new probe. This is a Python
# audit boundary for these owned fixtures, not an OS/native-code sandbox.
def probe(source, tmp_path, record_property):
    import textwrap
    owned_guard = r'''
owned_root = Path.cwd().resolve()
owned_events = {'writes': 0, 'sqlite_connects': 0}
def owned_path(value, dir_fd=None):
    if isinstance(value, int):
        value = os.readlink('/proc/self/fd/' + str(value))
    p = Path(os.fsdecode(value))
    if not p.is_absolute() and dir_fd not in (None, -1):
        p = Path(os.readlink('/proc/self/fd/' + str(dir_fd))) / p
    resolved = p.resolve()
    assert resolved.is_relative_to(owned_root), ('unowned fixture path', str(resolved))
def owned_io(event, args):
    if event == 'open':
        path, mode, flags = args
        if not isinstance(path, int):
            assert Path(os.fsdecode(path)).name != '.env', 'dotenv file access forbidden'
        if flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND):
            owned_path(path)
            owned_events['writes'] += 1
    elif event == 'sqlite3.connect':
        owned_path(args[0])
        owned_events['sqlite_connects'] += 1
    elif event in ('os.remove', 'os.rmdir', 'os.mkdir'):
        owned_path(args[0], args[-1])
    elif event in ('os.rename', 'os.link'):
        owned_path(args[0], args[2])
        owned_path(args[1], args[3])
sys.addaudithook(owned_io)
'''
    _helpers.probe(owned_guard + '\n' + textwrap.dedent(source) +
                   "\nprint(json.dumps({'owned_io_audit': owned_events}))\n",
                   tmp_path, record_property)
