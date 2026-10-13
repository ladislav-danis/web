"""Session security documentation and unchanged-runtime characterizations.

Fresh interpreters protect unrelated ThreadedDict/DB fixtures. The Python-level
pre-import guards below are test isolation, not a general-purpose OS sandbox.
Legacy probes use only locally generated benign dictionaries, never live stores.
"""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import textwrap

import pytest

WEB_ROOT = Path(__file__).resolve().parents[1]
DOC = WEB_ROOT / 'docs/session.md'
BOOTSTRAP = r'''
import importlib.abc
import json
import os
from pathlib import Path
import sys

class NoApplication(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {'core', 'modules', 'dotenv'}:
            raise AssertionError('Standalone probe imported ' + fullname)
sys.meta_path.insert(0, NoApplication())
def offline(event, args):
    if event.startswith('socket.') and event != 'socket.__new__':
        raise AssertionError('Standalone probe attempted network: ' + event)
    if event in {'subprocess.Popen', 'os.system', 'os.posix_spawn'}:
        raise AssertionError('Standalone probe attempted process: ' + event)
sys.addaudithook(offline)
sys.path.insert(0, sys.argv[1])
import web
from web import session
assert Path(web.__file__).resolve().parent == Path(sys.argv[1]) / 'web'
assert Path(session.__file__).resolve() == Path(sys.argv[1]) / 'web/session.py'
assert sys.dont_write_bytecode
web.config.debug = False

def raises(kind, operation):
    try:
        operation()
    except kind as error:
        return error
    raise AssertionError('Expected ' + kind.__name__)
'''


def probe(source, tmp_path, record_property):
    env = {'PATH': os.defpath, 'PYTHON_DOTENV_DISABLED': '1',
           'HOME': str(tmp_path), 'TMPDIR': str(tmp_path), 'LC_ALL': 'C',
           'SESSION_SECRET_KEY': 'test-only-persistent-session-secret'}
    result = subprocess.run(
        [sys.executable, '-I', '-B', '-c', BOOTSTRAP + '\n' + textwrap.dedent(source),
         str(WEB_ROOT.parent)], cwd=tmp_path, env=env,
        text=True, capture_output=True, timeout=30)
    record_property('probe_stdout', result.stdout)
    record_property('probe_stderr', result.stderr)
    assert result.returncode == 0, result.stdout + result.stderr


def fences(raw):
    """Parse headings only outside fences and preserve the exact code bytes."""
    heading, opened, language = '', None, None
    result = []
    for line_number, line in enumerate(raw.splitlines(keepends=True), 1):
        if opened is not None:
            if line.rstrip(b'\r\n') == b'```':
                result.append((heading, opened, language, b''.join(body)))
                opened = None
            else:
                body.append(line)
        elif line.startswith(b'```'):
            opened, language, body = line_number, line.strip()[3:].decode(), []
        elif line.startswith(b'#'):
            heading = line.decode().strip()
    assert opened is None, 'Unclosed Markdown fence'
    assert result
    return result


# These are executable examples, not API signatures or the issue-13 expiry
# fragment. Every fence bearing Session construction must have explicit setup.
EXECUTABLE_HEADINGS = [
    '### `Session`', '### `DiskStore`', '### `DBStore`', '### `MemoryStore`',
    '### `ShelfStore`', '### Configuration Example', '### Basic Session Setup',
    '### Database Session Store', '### Memory Session Store (Testing)',
    '### Session with Initialization', '### Using Dictionary Initializer',
    '### Session with Custom IP Validation', '### Session Kill (Logout)',
    '### Shelf Store Example', '### Signed store example',
]


@pytest.mark.parametrize('heading', EXECUTABLE_HEADINGS)
def test_documented_security_example(heading, tmp_path, record_property):
    # Subheadings exist in the reference sections, so examples carry a stable
    # explicit marker rather than treating a Python comment as a heading.
    blocks = fences(DOC.read_bytes())
    selected = [x for x in blocks if x[3].startswith(('# Executable: ' + heading + '\n').encode())]
    assert len(selected) == 1, heading
    _, line, language, code = selected[0]
    assert language == 'python'
    record_property('fence_sha256', hashlib.sha256(code).hexdigest())
    record_property('markdown_line', line)
    probe('''
        source = ''' + repr(code) + '''
        namespace = {'__name__': '__main__'}
        exec(compile(source, 'docs/session.md', 'exec'), namespace)
        print(json.dumps({'executed_exact_fence': True}))
    ''', tmp_path, record_property)


def test_every_standalone_session_setup_has_secret_before_construction():
    import ast
    blocks = fences(DOC.read_bytes())
    setups = []
    for heading, line, language, code in blocks:
        if b'session.Session(' not in code:
            continue
        assert language == 'python', (heading, line)
        tree = ast.parse(code)
        constructors = [n.lineno for n in ast.walk(tree) if isinstance(n, ast.Call)
                        and isinstance(n.func, ast.Attribute) and n.func.attr == 'Session']
        secrets = [n.lineno for n in ast.walk(tree) if isinstance(n, ast.Assign)
                   and any(isinstance(t, ast.Attribute) and t.attr == 'secret_key' for t in n.targets)]
        assert secrets and min(secrets) < min(constructors), (heading, line)
        assert b'os.environ["SESSION_SECRET_KEY"]' in code, (heading, line)
        setups.append(line)
    assert len(setups) >= 10


@pytest.mark.parametrize('backend', ['memory', 'disk', 'db', 'shelf'])
def test_default_secret_rejected_and_session_copies_config(backend, tmp_path, record_property):
    probe('''
        import shelve
        from contextlib import ExitStack
        from tempfile import TemporaryDirectory
        with ExitStack() as stack:
            root = Path(stack.enter_context(TemporaryDirectory()))
            backend = ''' + repr(backend) + '''
            if backend == 'memory':
                store = session.MemoryStore()
            elif backend == 'disk':
                store = session.DiskStore(str(root / 'sessions'))
            elif backend == 'db':
                db = web.database(dbn='sqlite', db=str(root / 'sessions.db'))
                stack.callback(db.ctx.db.close)
                store = session.DBStore(db, 'sessions')
            else:
                shelf = stack.enter_context(shelve.open(str(root / 'sessions.shelf')))
                store = session.ShelfStore(shelf)
            app = web.application((), {}, autoreload=False)
            assert web.config.session_parameters.secret_key == session.DEFAULT_SECRET_KEY
            raises(session.SessionSecretRequired, lambda: session.Session(app, store))
            web.config.session_parameters.secret_key = os.environ['SESSION_SECRET_KEY']
            sess = session.Session(app, store)
            assert store.secret_key == os.environ['SESSION_SECRET_KEY']
            web.config.session_parameters.secret_key = 'different-test-key'
            assert sess._config.secret_key == os.environ['SESSION_SECRET_KEY']
            assert store.secret_key == os.environ['SESSION_SECRET_KEY']
        assert not root.exists()
        print(json.dumps({'backend': backend, 'default_rejected': True, 'config_copy': True}))
    ''', tmp_path, record_property)


def test_secret_guard_is_not_entropy_or_nonempty_validation(tmp_path, record_property):
    probe('''
        for key in ('', 'x', None):
            web.config.session_parameters.secret_key = key
            store = session.MemoryStore()
            sess = session.Session(None, store)
            assert store.secret_key is key
        del web.config.session_parameters['secret_key']
        raises(AttributeError, lambda: session.Session(None, session.MemoryStore()))
        plain = session.Store()
        raises(AttributeError, lambda: plain.encode({'ok': True}))
        plain.secret_key = ''
        assert plain.decode(plain.encode({'ok': True})) == {'ok': True}
        plain.secret_key = None
        raises(AttributeError, lambda: plain.encode({'ok': True}))
        print(json.dumps({'missing': 'AttributeError', 'empty_accepted': True,
                          'short_accepted': True, 'none_constructor_accepted': True}))
    ''', tmp_path, record_property)


def test_signed_json_wire_tamper_rotation_and_malformed_boundaries(tmp_path, record_property):
    probe('''
        import base64
        import binascii
        import hashlib
        import hmac
        store = session.Store()
        store.secret_key = os.environ['SESSION_SECRET_KEY']
        value = {'name': 'Příliš', 'values': [None, True, False, 7, 1.25], 'nested': {'k': 'v'}}
        encoded = store.encode(value)
        assert isinstance(encoded, bytes) and encoded.endswith(b'\\n')
        assert len(encoded.splitlines()) > 1
        signature, raw = base64.decodebytes(encoded).split(b'.', 1)
        assert raw == json.dumps(value).encode('utf-8')
        assert signature == hmac.new(store.secret_key.encode(), raw, hashlib.sha256).hexdigest().encode()
        assert len(signature) == 64
        assert store.decode(encoded) == value
        assert store.decode('  ' + encoded.decode('ascii') + '\\n') == value
        modified = base64.encodebytes(signature + b'.' + raw.replace(b'1.25', b'2.25'))
        raises(session.SessionTamperedError, lambda: store.decode(modified))
        store.secret_key = 'rotated-test-key'
        raises(session.SessionTamperedError, lambda: store.decode(encoded))
        raises(session.SessionTamperedError, lambda: store.decode(base64.encodebytes(b'no-delimiter')))
        raises(binascii.Error, lambda: store.decode(b'a'))
        bad_json = b'not-json'
        signed_bad_json = hmac.new(store.secret_key.encode(), bad_json, hashlib.sha256).hexdigest().encode() + b'.' + bad_json
        raises(json.JSONDecodeError, lambda: store.decode(base64.encodebytes(signed_bad_json)))
        print(json.dumps({'signed_json': True, 'tamper_and_rotation_rejected': True,
                          'malformed_base64': 'Error', 'signed_bad_json': 'JSONDecodeError'}))
    ''', tmp_path, record_property)


def test_json_supported_values_coercion_and_unsupported_objects(tmp_path, record_property):
    probe('''
        import math
        from datetime import datetime
        store = session.Store()
        store.secret_key = os.environ['SESSION_SECRET_KEY']
        for value in (None, True, False, 7, 1.5, 'žluťoučký', ['x', 1], {'k': {'v': None}}):
            assert store.decode(store.encode(value)) == value
        assert store.decode(store.encode({1: ('a', 'b')})) == {'1': ['a', 'b']}
        for value in (b'bytes', {1, 2}, datetime(2020, 1, 1), object()):
            raises(TypeError, lambda: store.encode(value))
        circular = []; circular.append(circular)
        raises(ValueError, lambda: store.encode(circular))
        assert math.isnan(store.decode(store.encode(float('nan'))))
        assert store.decode(store.encode(float('inf'))) == float('inf')
        print(json.dumps({'tuple_to_list': True, 'integer_keys_to_strings': True,
                          'arbitrary_objects': False, 'strict_finite_json': False}))
    ''', tmp_path, record_property)


@pytest.mark.parametrize('backend', ['disk', 'db'])
def test_owned_persistent_stores_legacy_read_does_not_rewrite(backend, tmp_path, record_property):
    probe('''
        import base64
        import pickle
        import sqlite3
        from contextlib import ExitStack
        from tempfile import TemporaryDirectory
        with ExitStack() as stack:
            root = Path(stack.enter_context(TemporaryDirectory()))
            backend = ''' + repr(backend) + '''
            if backend == 'disk':
                store = session.DiskStore(str(root / 'sessions'))
                def write_raw(value):
                    (root / 'sessions' / 'owned').write_bytes(value)
                def read_raw():
                    return (root / 'sessions' / 'owned').read_bytes()
            else:
                db = web.database(dbn='sqlite', db=str(root / 'sessions.db'))
                stack.callback(db.ctx.db.close)
                db.query('CREATE TABLE sessions (session_id TEXT UNIQUE, atime TIMESTAMP DEFAULT CURRENT_TIMESTAMP, data TEXT)')
                store = session.DBStore(db, 'sessions')
                def write_raw(value):
                    db.update('sessions', where="session_id='owned'", data=value.decode('ascii'))
                def read_raw():
                    return db.select('sessions', where="session_id='owned'")[0].data
            store.secret_key = 'old-test-key'
            store['owned'] = {'ok': True}
            modern = read_raw()
            assert isinstance(modern, bytes if backend == 'disk' else str)
            assert store['owned'] == {'ok': True}
            store.secret_key = 'new-test-key'
            raises(session.SessionTamperedError, lambda: store['owned'])
            # Benign, locally produced dictionary; never load an external pickle.
            legacy = base64.encodebytes(pickle.dumps({'legacy': 'owned'}, protocol=2))
            write_raw(legacy)
            before = read_raw()
            if backend == 'db':
                db.query('CREATE TABLE legacy_audit (operation TEXT, data_changed INTEGER, atime_changed INTEGER)')
                db.query("CREATE TRIGGER legacy_update AFTER UPDATE ON sessions BEGIN "
                         "INSERT INTO legacy_audit VALUES ('UPDATE', OLD.data != NEW.data, OLD.atime != NEW.atime); END")
                db.query("CREATE TRIGGER legacy_delete AFTER DELETE ON sessions BEGIN "
                         "INSERT INTO legacy_audit VALUES ('DELETE', 1, 0); END")
            raises(session.SessionLegacyRejected, lambda: store['owned'])
            assert read_raw() == before  # DB atime can change, payload cannot.
            store.secret_key = 'another-test-key'
            raises(session.SessionLegacyRejected, lambda: store['owned'])
            assert read_raw() == before
            if backend == 'db':
                changes = list(db.select('legacy_audit'))
                assert len(changes) == 2
                assert all(row.operation == 'UPDATE' and not row.data_changed
                           and row.atime_changed for row in changes)
            store['owned'] = {'legacy': 'owned'}
            assert read_raw() != before
            assert store['owned'] == {'legacy': 'owned'}
            store.secret_key = 'new-test-key'
            raises(session.SessionTamperedError, lambda: store['owned'])
        assert not root.exists()
        print(json.dumps({'backend': backend, 'unsigned_legacy_rejected_after_rotation': True,
                          'read_does_not_rewrite_payload': True, 'later_write_signed': True}))
    ''', tmp_path, record_property)


@pytest.mark.parametrize('backend', ['memory', 'shelf'])
def test_plain_stores_do_not_cryptographically_invalidate_on_rotation(backend, tmp_path, record_property):
    probe('''
        import shelve
        from contextlib import ExitStack
        from tempfile import TemporaryDirectory
        with ExitStack() as stack:
            root = Path(stack.enter_context(TemporaryDirectory()))
            backend = ''' + repr(backend) + '''
            if backend == 'memory':
                store = session.MemoryStore()
            else:
                shelf = stack.enter_context(shelve.open(str(root / 'sessions.shelf')))
                store = session.ShelfStore(shelf)
            # Sets are not accepted by Store.encode; both plain stores retain them.
            value = {'owned': {1, 2}}
            web.config.session_parameters.secret_key = 'old-test-key'
            session.Session(None, store)
            store['owned'] = value
            web.config.session_parameters.secret_key = 'new-test-key'
            session.Session(None, store)
            assert store['owned'] == value
        assert not root.exists()
        print(json.dumps({'backend': backend, 'rotation_retains_plain_data': True}))
    ''', tmp_path, record_property)


@pytest.mark.parametrize('httponly', [True, False])
def test_httponly_cookie_does_not_escape_response_html(httponly, tmp_path, record_property):
    probe('''
        from http.cookies import SimpleCookie
        web.config.session_parameters.update(secret_key=os.environ['SESSION_SECRET_KEY'],
            httponly=''' + repr(httponly) + ''', secure=True, samesite='Lax')
        app = web.application((), {}, autoreload=False)
        store = session.MemoryStore()
        sess = session.Session(app, store, initializer={'count': 0})
        class Index:
            def GET(self):
                sess.count += 1
                return '<b data-marker="inert">raw & unescaped</b>'
        app.add_mapping('/', Index)
        response = app.request('/', https=True)
        assert response.status == '200 OK'
        assert response.data == b'<b data-marker="inert">raw & unescaped</b>'
        cookie = SimpleCookie()
        for key, value in response.header_items:
            if key.lower() == 'set-cookie':
                cookie.load(value)
        morsel = cookie['webpy_session_id']
        assert bool(morsel['httponly']) is ''' + repr(httponly) + '''
        assert morsel['secure'] and morsel['samesite'] == 'Lax'
        sid = morsel.value
        assert store[sid]['count'] == 1
        assert app.request('/', https=True, headers={'Cookie': 'webpy_session_id=' + sid}).status == '200 OK'
        assert store[sid]['count'] == 2
        assert app.request('/', https=True).status == '200 OK'
        assert len(store.d_store) == 2
        print(json.dumps({'httponly': bool(morsel['httponly']), 'raw_html_preserved': True,
                          'independent_cookie_sessions': True}))
    ''', tmp_path, record_property)
