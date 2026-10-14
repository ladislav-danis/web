"""Missing-record expiry through real WSGI and owned real session stores.

These are session lifecycle tests, not simulated authentication or deployment.
Python audit hooks isolate these probes; they are not an OS sandbox.
"""
import importlib.util
import os
from pathlib import Path
import subprocess
import sys

import pytest

_spec = importlib.util.spec_from_file_location(
    '_expiry_security_helpers', Path(__file__).with_name('test_session_security_contract.py'))
_helpers = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_helpers)

GUARD = r'''
owned = Path.cwd().resolve()
def check_path(path):
    if isinstance(path, int):
        path = os.readlink('/proc/self/fd/' + str(path))
    assert Path(os.fsdecode(path)).resolve().is_relative_to(owned), path
def guard(event, args):
    if event == 'open':
        path, mode, flags = args
        if not isinstance(path, int):
            assert Path(os.fsdecode(path)).name != '.env'
        if flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND):
            check_path(path)
    elif event == 'sqlite3.connect':
        check_path(args[0])
    elif event in ('os.remove', 'os.rmdir', 'os.mkdir'):
        check_path(args[0])
    elif event == 'os.rename':
        check_path(args[0]); check_path(args[1])
sys.addaudithook(guard)
'''


def probe(source, tmp_path, record_property):
    env = {'PATH': os.defpath, 'PYTHON_DOTENV_DISABLED': '1', 'LC_ALL': 'C',
           'SESSION_SECRET_KEY': 'owned-expiry-test-secret'}
    for key in ('HOME', 'TMPDIR', 'XDG_CACHE_HOME', 'XDG_DATA_HOME', 'XDG_CONFIG_HOME'):
        env[key] = str(tmp_path)
    result = subprocess.run(
        [sys.executable, '-B', '-I', '-c', _helpers.BOOTSTRAP + GUARD + source,
         str(_helpers.WEB_ROOT.parent)], cwd=tmp_path, env=env,
        text=True, capture_output=True, timeout=30)
    record_property('child_returncode', result.returncode)
    record_property('probe_stdout', result.stdout)
    record_property('probe_stderr', result.stderr)
    assert result.returncode == 0, result.stdout + result.stderr


SETUP = r'''
from contextlib import ExitStack
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from http.cookies import SimpleCookie
import importlib
import io
import sqlite3
from tempfile import TemporaryDirectory

stack = ExitStack()
root = Path(stack.enter_context(TemporaryDirectory()))
backing_events = []
if backend == 'memory':
    class ObservedDict(dict):
        def __setitem__(self, key, value):
            backing_events.append(('SET', key))
            super().__setitem__(key, value)
        def __delitem__(self, key):
            backing_events.append(('DELETE', key))
            super().__delitem__(key)
    store = session.MemoryStore(ObservedDict())
    def snapshot():
        return deepcopy(dict(store.d_store))
    def payload(sid):
        return deepcopy(store.d_store[sid][1])
    def mutations():
        return list(backing_events)
    def clear_audit():
        backing_events.clear()
    def age(sid):
        _, data = store.d_store[sid]
        store.d_store[sid] = (0, data)
elif backend == 'disk':
    directory = root / 'sessions'
    store = session.DiskStore(str(directory))
    def audit_disk(event, args):
        if event == 'open' and not isinstance(args[0], int):
            if Path(args[0]).resolve().is_relative_to(directory) and args[2] & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND):
                backing_events.append(('WRITE', str(args[0])))
        elif event in ('os.rename', 'os.remove'):
            if Path(args[0]).resolve().is_relative_to(directory):
                backing_events.append((event, str(args[0])))
    sys.addaudithook(audit_disk)
    def snapshot():
        return {p.name: p.read_bytes() for p in directory.iterdir()}
    def payload(sid):
        return store.decode((directory / sid).read_bytes())
    def mutations():
        return list(backing_events)
    def clear_audit():
        backing_events.clear()
    def age(sid):
        os.utime(directory / sid, (0, 0))
else:
    dbpath = root / 'sessions.db'
    db = web.database(dbn='sqlite', db=str(dbpath))
    stack.callback(db.ctx.db.close)
    db.query('CREATE TABLE sessions (session_id TEXT UNIQUE, atime TEXT, data TEXT)')
    db.query('CREATE TABLE audit (operation TEXT, sid TEXT, old_data TEXT, new_data TEXT)')
    db.query("CREATE TRIGGER ins AFTER INSERT ON sessions BEGIN INSERT INTO audit VALUES ('INSERT', NEW.session_id, NULL, NEW.data); END")
    db.query("CREATE TRIGGER upd AFTER UPDATE ON sessions BEGIN INSERT INTO audit VALUES ('UPDATE', NEW.session_id, OLD.data, NEW.data); END")
    db.query("CREATE TRIGGER del AFTER DELETE ON sessions BEGIN INSERT INTO audit VALUES ('DELETE', OLD.session_id, OLD.data, NULL); END")
    store = session.DBStore(db, 'sessions')
    def rows(sql):
        conn = sqlite3.connect(dbpath)
        try:
            return conn.execute(sql).fetchall()
        finally:
            conn.close()
    def snapshot():
        return {sid: (atime, data) for sid, atime, data in rows('SELECT * FROM sessions')}
    def payload(sid):
        return store.decode(snapshot()[sid][1])
    def mutations():
        return rows('SELECT * FROM audit')
    def clear_audit():
        db.query('DELETE FROM audit')
    def age(sid):
        db.update('sessions', where='session_id=$sid', vars=locals(), atime='1970-01-01 00:00:00')

name = 'owned_session' if custom else 'webpy_session_id'
config = dict(secret_key=os.environ['SESSION_SECRET_KEY'], ignore_expiry=ignore_expiry,
              ignore_change_ip=ignore_change_ip, expired_message='Owned session expired', timeout=86400)
if custom:
    config.update(cookie_name=name, cookie_domain='example.test', cookie_path='/owned',
                  httponly=True, secure=True, samesite='Strict')
web.config.session_parameters.update(config)
app = web.application((), {}, autoreload=False)
seen, caught, errors, inner_events = [], [], [], []
log = io.StringIO()
importlib.import_module('web.webapi').debug = log
original_internalerror = app.internalerror
def internalerror():
    errors.append(sys.exc_info()[1])
    return original_internalerror()
app.internalerror = internalerror
def observe(handler):
    try:
        return handler()
    except session.SessionExpired as error:
        caught.append((type(error).__name__, error.args[0], error.data))
        if policy == 'outer':
            raise web.HTTPError('400 Bad Request', {}, 'Explicit expiry policy')
        raise
app.add_processor(observe)
initial = {'visits': 0, 'nested': []}
sess = session.Session(app, store, initializer=initial)
def inner(handler):
    inner_events.append('enter')
    try:
        return handler()
    except session.SessionExpired:
        inner_events.append('catch')
        raise web.HTTPError('409 Conflict', {}, 'Too late')
if policy == 'inner':
    app.add_processor(inner)
class Index:
    def GET(self):
        seen.append(dict(sess.items()))
        try:
            sess.visits += 1
            sess.nested.append(sess.visits)
            return str(sess.visits)
        except session.SessionExpired:
            raise AssertionError('GET must not catch load expiry')
app.add_mapping('/owned', Index)
def request(sid=None, ip='192.0.2.1'):
    headers = {} if sid is None else {'Cookie': name + '=' + sid}
    return app.request('/owned', host='example.test', https=custom,
                       headers=headers, env={'REMOTE_ADDR': ip})
def cookie(response):
    values = [v for k, v in response.header_items if k.lower() == 'set-cookie']
    assert len(values) == 1, response.header_items
    jar = SimpleCookie(); jar.load(values[0])
    assert set(jar) == {name}
    value = jar[name]
    if custom:
        assert value['path'] == '/owned' and value['domain'] == 'example.test'
        assert value['secure'] and value['httponly'] and value['samesite'] == 'Strict'
    return value
def assert_expired(response, sid):
    expected_status = '400 Bad Request' if policy == 'outer' else '200 OK'
    expected_body = b'Explicit expiry policy' if policy == 'outer' else b'Owned session expired'
    # Include exact accidental error in RED output rather than hiding it.
    assert response.status == expected_status, (response.status, [(type(e).__name__, e.args) for e in errors], log.getvalue())
    assert response.data == expected_body
    assert caught == [('SessionExpired', '200 OK', 'Owned session expired')]
    assert not seen and not inner_events and not errors and not log.getvalue()
    expired = cookie(response)
    assert expired.value == sid
    assert parsedate_to_datetime(expired['expires']) < datetime.now(timezone.utc) - timedelta(days=1)
    assert expired['max-age'] == ''  # current contract uses Expires, not Max-Age
first = request()
assert first.status == '200 OK' and first.data == b'1'
sid = cookie(first).value
assert len(sid) == 64 and set(sid) <= set('0123456789abcdef')
assert not cookie(first)['expires']
assert payload(sid) == dict(initial, visits=1, nested=[1], session_id=sid, ip='192.0.2.1')
valid = request(sid)
assert valid.status == '200 OK' and valid.data == b'2'
assert cookie(valid).value == sid and not cookie(valid)['expires']
assert payload(sid) == dict(initial, visits=2, nested=[1, 2], session_id=sid, ip='192.0.2.1')
assert len(seen) == 2 and not caught and not errors
assert initial == {'visits': 0, 'nested': []}
# An unrelated current session must survive; no bulk invalidation.
unrelated = 'f' * 64
assert unrelated != sid
store[unrelated] = {'owned': 'unrelated'}
seen.clear(); caught.clear(); inner_events.clear()
'''

CLEANUP = r'''
finally:
    if backend == 'db':
        db.ctx.db.close()
    stack.close()
assert not root.exists()
'''


def setup(backend, policy='outer', ignore_expiry=False, ignore_change_ip=False, custom=False):
    return ('backend = ' + repr(backend) + '\npolicy = ' + repr(policy)
            + '\nignore_expiry = ' + repr(ignore_expiry)
            + '\nignore_change_ip = ' + repr(ignore_change_ip)
            + '\ncustom = ' + repr(custom) + '\n' + SETUP)


@pytest.mark.parametrize('backend', ['memory', 'disk', 'db'])
def test_missing_issued_cookie_expires_before_handler(backend, tmp_path, record_property):
    probe(setup(backend) + r'''
try:
    del store[sid]
    before = snapshot()
    assert set(before) == {unrelated}
    clear_audit()
    response = request(sid)
    assert_expired(response, sid)
    assert snapshot() == before and not mutations()
    assert sid not in store
    print(json.dumps({'backend': backend, 'status': response.status, 'caught': caught,
                      'handler_calls': len(seen), 'store_mutations': mutations(),
                      'set_cookie': cookie(response).OutputString()}))
''' + CLEANUP, tmp_path, record_property)


@pytest.mark.parametrize('backend', ['memory', 'disk', 'db'])
def test_missing_cookie_without_any_outer_processor(backend, tmp_path, record_property):
    probe(setup(backend, policy='none') + r'''
try:
    app.processors.remove(observe)
    del store[sid]
    before = snapshot()
    clear_audit()
    response = request(sid)
    assert response.status == '200 OK' and response.data == b'Owned session expired'
    assert not seen and not caught and not errors and not log.getvalue()
    expired = cookie(response)
    assert expired.value == sid and expired['max-age'] == ''
    assert parsedate_to_datetime(expired['expires']) < datetime.now(timezone.utc) - timedelta(days=1)
    assert snapshot() == before and not mutations() and sid not in store
    print(json.dumps({'backend': backend, 'outer_processors': 0,
                      'status': response.status, 'body': response.data.decode()}))
''' + CLEANUP, tmp_path, record_property)


@pytest.mark.parametrize('backend', ['memory', 'disk', 'db'])
@pytest.mark.parametrize('policy', ['none', 'inner'])
@pytest.mark.parametrize('custom', [False, True])
def test_missing_cookie_preserves_default_policy_and_processor_order(
        backend, policy, custom, tmp_path, record_property):
    probe(setup(backend, policy=policy, custom=custom) + r'''
try:
    del store[sid]
    before = snapshot()
    clear_audit()
    for attempt in range(2):
        caught.clear()
        response = request(sid)
        assert_expired(response, sid)
        assert snapshot() == before and not mutations()
    # No cookie remains a usable fresh initialized session after expiry.
    fresh = request()
    replacement = cookie(fresh).value
    assert fresh.status == '200 OK' and fresh.data == b'1'
    assert replacement not in {sid, unrelated} and sid not in store
    assert payload(replacement)['nested'] == [1]
    print(json.dumps({'backend': backend, 'policy': policy, 'custom': custom,
                      'repeat_expiry_status': response.status, 'fresh_status': fresh.status}))
''' + CLEANUP, tmp_path, record_property)


@pytest.mark.parametrize('backend', ['memory', 'disk', 'db'])
@pytest.mark.parametrize('policy', ['outer', 'none', 'inner'])
def test_cleanup_of_owned_expired_record_uses_same_expiry_contract(
        backend, policy, tmp_path, record_property):
    probe(setup(backend, policy=policy, custom=True) + r'''
try:
    retained = snapshot()[unrelated]
    age(sid)
    clear_audit()
    sess._last_cleanup_time = 0
    response = request(sid)
    assert_expired(response, sid)
    assert snapshot() == {unrelated: retained} and sid not in store
    changes = mutations()
    if backend == 'memory':
        assert changes == [('DELETE', sid)]
    elif backend == 'disk':
        assert changes == [('os.remove', str(directory / sid))]
    else:
        assert [(r[0], r[1]) for r in changes] == [('DELETE', sid)]
        assert store.decode(changes[0][2])['visits'] == 2 and changes[0][3] is None
    print(json.dumps({'backend': backend, 'policy': policy,
                      'cleanup_only': changes, 'handler_calls': len(seen)}))
''' + CLEANUP, tmp_path, record_property)


@pytest.mark.parametrize('backend', ['memory', 'disk', 'db'])
@pytest.mark.parametrize('custom', [False, True])
def test_ignore_expiry_resets_to_new_initialized_id(backend, custom, tmp_path, record_property):
    probe(setup(backend, ignore_expiry=True, custom=custom) + r'''
try:
    del store[sid]
    before = snapshot()
    clear_audit()
    response = request(sid)
    replacement = cookie(response).value
    assert response.status == '200 OK' and response.data == b'1'
    assert replacement not in {sid, unrelated} and not cookie(response)['expires']
    assert not caught and not errors and len(seen) == 1
    assert set(snapshot()) == {replacement, unrelated} and sid not in store
    assert snapshot()[unrelated] == before[unrelated]
    assert payload(replacement) == dict(initial, visits=1, nested=[1], session_id=replacement, ip='192.0.2.1')
    changes = mutations()
    if backend == 'memory':
        assert changes == [('SET', replacement)]
    elif backend == 'disk':
        assert [event for event, path in changes] == ['WRITE', 'os.rename']
        assert all(Path(path).name.startswith(replacement + '.') for event, path in changes)
    else:
        assert [(r[0], r[1]) for r in changes] == [('INSERT', replacement)]
    retry = request(replacement)
    assert retry.status == '200 OK' and retry.data == b'2'
    assert cookie(retry).value == replacement and payload(replacement)['nested'] == [1, 2]
    assert initial == {'visits': 0, 'nested': []}
    print(json.dumps({'backend': backend, 'custom': custom, 'new_id': replacement,
                      'old_id': sid, 'reset_writes': changes}))
''' + CLEANUP, tmp_path, record_property)


@pytest.mark.parametrize('backend', ['memory', 'disk', 'db'])
@pytest.mark.parametrize('ignore_change_ip', [False, True])
@pytest.mark.parametrize('policy', ['outer', 'none'])
def test_changed_ip_preserves_expiry_or_configured_acceptance(
        backend, ignore_change_ip, policy, tmp_path, record_property):
    probe(setup(backend, policy=policy, ignore_change_ip=ignore_change_ip, custom=True) + r'''
try:
    before = payload(sid)
    unrelated_before = snapshot()[unrelated]
    clear_audit()
    response = request(sid, ip='192.0.2.2')
    if ignore_change_ip:
        assert response.status == '200 OK' and response.data == b'3'
        assert cookie(response).value == sid and not cookie(response)['expires']
        assert len(seen) == 1 and not caught and not errors
        assert payload(sid) == dict(before, visits=3, nested=[1, 2, 3], ip='192.0.2.2')
    else:
        assert_expired(response, sid)
        assert payload(sid) == before and '_killed' not in payload(sid)
    assert set(snapshot()) == {sid, unrelated} and snapshot()[unrelated] == unrelated_before
    changes = mutations()
    if backend == 'memory':
        assert changes == [('SET', sid)] * (2 if ignore_change_ip else 1)
    elif backend == 'disk':
        assert [event for event, path in changes] == (['WRITE', 'os.rename'] if ignore_change_ip else [])
    else:
        assert [(r[0], r[1]) for r in changes] == [('UPDATE', sid)] * (2 if ignore_change_ip else 1)
        assert changes[0][2] == changes[0][3]  # real atime-only update, not a safe-GET claim
        if ignore_change_ip:
            assert store.decode(changes[1][3])['visits'] == 3
    print(json.dumps({'backend': backend, 'ignore_change_ip': ignore_change_ip,
                      'policy': policy, 'status': response.status, 'store_events': changes}))
''' + CLEANUP, tmp_path, record_property)


@pytest.mark.parametrize('backend', ['memory', 'disk', 'db'])
def test_unrelated_store_keyerror_is_not_expiry_recovery(backend, tmp_path, record_property):
    probe(setup(backend) + r'''
try:
    before = snapshot()
    clear_audit()
    failure = KeyError('owned retrieval failure')
    original_get = type(store).__getitem__
    def fail_at_get(self, key):
        if key == sid:
            raise failure
        return original_get(self, key)
    type(store).__getitem__ = fail_at_get
    response = request(sid)
    assert response.status == '500 Internal Server Error' and response.data == b'internal server error'
    assert errors == [failure] and errors[0] is failure
    assert not caught and not seen
    assert not [v for k, v in response.header_items if k.lower() == 'set-cookie']
    assert snapshot() == before and not mutations()
    assert 'owned retrieval failure' in log.getvalue()
    print(json.dumps({'backend': backend, 'unrelated_error_preserved': True, 'status': response.status}))
''' + CLEANUP, tmp_path, record_property)
