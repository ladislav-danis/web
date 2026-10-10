"""Bounded usage contracts; unchanged limitations are not runtime repairs.

Fresh -I -B children use the security contract's pre-import guards and real WSGI.
No Core, deployed data, networking, auth substitute, or existing-test mutation.
"""
import hashlib
import importlib.util
from pathlib import Path

import pytest

# Reuse isolation/extraction, not another test's behavioral assertions.
_spec = importlib.util.spec_from_file_location(
    '_session_security_helpers', Path(__file__).with_name('test_session_security_contract.py'))
_helpers = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_helpers)
probe, fences, DOC = _helpers.probe, _helpers.fences, _helpers.DOC


def usage_fence(heading):
    blocks = fences(DOC.read_bytes())
    selected = [b for b in blocks if b[0] == heading and b[2] == 'python']
    assert len(selected) == 1
    return selected[0]


@pytest.mark.parametrize('heading', ['### Session Expiration Handling', '### Session Object'])
def test_documented_usage_example(heading, tmp_path, record_property):
    _, line, _, code = usage_fence(heading)
    record_property('fence_sha256', hashlib.sha256(code).hexdigest())
    record_property('markdown_line', line)
    # On the published baseline, call the documented GET via real WSGI as well
    # as executing its setup. No injection or synthetic authentication success.
    probe('''
        namespace = {'__name__': '__main__'}
        exec(compile(''' + repr(code) + ''', 'docs/session.md', 'exec'), namespace)
        if 'Dashboard' in namespace:
            namespace['app'].add_mapping('/', namespace['Dashboard'])
            response = namespace['app'].request('/')
            assert response.status == '200 OK', response.status
        print(json.dumps({'executed_exact_fence': True}))
    ''', tmp_path, record_property)


EXPIRY_SETUP = r'''
from http.cookies import SimpleCookie
import importlib
import io
from types import SimpleNamespace
session.time = SimpleNamespace(time=lambda: 1000.0)
web.config.session_parameters.secret_key = os.environ['SESSION_SECRET_KEY']
web.config.session_parameters.update(ignore_expiry=ignore_expiry, ignore_change_ip=False)
app = web.application((), {}, autoreload=False)
events = []
errors = []
log = io.StringIO()
importlib.import_module('web.webapi').debug = log
original_internalerror = app.internalerror
def internalerror():
    errors.append((type(sys.exc_info()[1]).__name__, sys.exc_info()[1].args))
    return original_internalerror()
app.internalerror = internalerror
def outer(handler):
    try:
        return handler()
    except session.SessionExpired as error:
        events.append('outer-catch')
        raise web.HTTPError('400 Bad Request', {}, 'Expired outside GET')
if use_outer:
    app.add_processor(outer)
store = session.MemoryStore()
sess = session.Session(app, store, initializer={'visits': 0})
class Index:
    def GET(self):
        events.append('handler')
        try:
            sess.visits += 1
            return str(sess.visits)
        except session.SessionExpired:
            events.append('GET-catch')
            return 'too late'
app.add_mapping('/', Index)
def request(sid=None, ip='192.0.2.1'):
    headers = {} if sid is None else {'Cookie': 'webpy_session_id=' + sid}
    return app.request('/', headers=headers, env={'REMOTE_ADDR': ip})
def cookie(response):
    jar = SimpleCookie()
    for key, value in response.header_items:
        if key.lower() == 'set-cookie':
            jar.load(value)
    return jar
first = request()
assert first.status == '200 OK' and first.data == b'1'
sid = cookie(first)['webpy_session_id'].value
assert len(sid) == 64 and store[sid]['visits'] == 1
valid = request(sid)
assert valid.status == '200 OK' and valid.data == b'2'
assert cookie(valid)['webpy_session_id'].value == sid
assert store[sid]['visits'] == 2
assert events == ['handler', 'handler']
events.clear()
'''


@pytest.mark.parametrize('scenario,ignore_expiry,use_outer', [
    ('missing', True, True), ('missing', False, True),
    ('changed-ip', False, True), ('changed-ip', False, False),
    ('changed-ip', True, True),
])
def test_real_wsgi_expiry_order_and_missing_record_limitation(
        scenario, ignore_expiry, use_outer, tmp_path, record_property):
    source = ('scenario = ' + repr(scenario) + '\nignore_expiry = ' + repr(ignore_expiry)
              + '\nuse_outer = ' + repr(use_outer) + '\n' + EXPIRY_SETUP)
    source += r'''
if scenario == 'missing':
    del store[sid]
    response = request(sid)
    if ignore_expiry:
        assert response.status == '200 OK' and response.data == b'1'
        replacement = cookie(response)['webpy_session_id'].value
        assert replacement != sid and sid not in store
        assert store[replacement]['visits'] == 1 and len(store.d_store) == 1
        assert events == ['handler'] and not errors
    else:
        assert response.status == '500 Internal Server Error'
        assert response.data == b'internal server error'
        assert errors == [('KeyError', ('ip',))], errors
        assert "KeyError: 'ip'" in log.getvalue()
        assert not cookie(response) and not store.d_store and not events
else:
    before = dict(store[sid])
    response = request(sid, ip='192.0.2.2')
    assert response.status == ('400 Bad Request' if use_outer else '200 OK')
    assert response.data == (b'Expired outside GET' if use_outer else b'Session expired')
    assert events == (['outer-catch'] if use_outer else [])
    assert not errors
    expired_cookie = cookie(response)['webpy_session_id']
    assert expired_cookie.value == sid and expired_cookie['expires']
    assert sid in store and store[sid] == before  # expired() does not delete it
    assert not store[sid].get('_killed')
    again = request()  # fresh cookie client, not an authenticated identity
    assert again.status == '200 OK' and again.data == b'1'
    assert cookie(again)['webpy_session_id'].value != sid
print(json.dumps({'scenario': scenario, 'ignore_expiry': ignore_expiry,
                  'outer': use_outer, 'status': response.status, 'events': events,
                  'errors': errors, 'store_count': len(store.d_store)}))
'''
    probe(source, tmp_path, record_property)


def test_direct_iteration_limitation_and_mapping_alternatives(tmp_path, record_property):
    probe(r'''
        web.config.session_parameters.secret_key = os.environ['SESSION_SECRET_KEY']
        sess = session.Session(None, session.MemoryStore())
        sess['alpha'] = 1
        sess.beta = 2
        assert sess.alpha == 1 and sess['beta'] == 2
        assert set(sess.keys()) == {'alpha', 'beta'}
        assert dict(sess.items()) == {'alpha': 1, 'beta': 2}
        assert 'alpha' in sess and 'missing' not in sess
        assert sess.get('missing', 42) == 42
        error = raises(KeyError, lambda: next(iter(sess)))
        assert error.args == (0,)
        del sess['alpha']
        del sess.beta
        assert not list(sess.keys())
        assert raises(KeyError, lambda: sess['missing']).args == ('missing',)
        raises(AttributeError, lambda: sess.missing)
        print(json.dumps({'direct_iteration': 'KeyError(0)', 'keys_items': True}))
    ''', tmp_path, record_property)


def test_generated_id_sha256_independent_oracle_and_collision_retry(tmp_path, record_property):
    probe(r'''
        import hashlib
        from types import SimpleNamespace
        web.config.session_parameters.secret_key = os.environ['SESSION_SECRET_KEY']
        store = session.MemoryStore()
        sess = session.Session(None, store)
        web.ctx.ip = '192.0.2.9'
        chunks = [b'A' * 16, b'B' * 16]
        # Independent construction of the actual f-string byte representation.
        def oracle(chunk):
            return hashlib.sha256((str(chunk) + '1234.5' + '192.0.2.9'
                                   + os.environ['SESSION_SECRET_KEY']).encode('utf-8')).hexdigest()
        expected_first, expected_second = map(oracle, chunks)
        store[expected_first] = {'collision': True}
        calls = []
        def urandom(length):
            assert length == 16
            calls.append(length)
            return chunks.pop(0)  # third call fails rather than unbounded retry
        session.os = SimpleNamespace(urandom=urandom)
        session.time = SimpleNamespace(time=lambda: 1234.5)
        generated = sess._generate_session_id()
        assert generated == expected_second and calls == [16, 16]
        assert len(generated) == 64 and set(generated) <= set('0123456789abcdef')
        assert store[expected_first] == {'collision': True}
        assert generated not in store  # generation itself does not reserve the ID
        print(json.dumps({'id': generated, 'algorithm': 'SHA-256', 'collision_calls': calls}))
    ''', tmp_path, record_property)


@pytest.mark.parametrize('value,accepted', [
    ('a', True), ('F' * 40, True), ('0' * 64, True), ('A' * 128, True),
    ('abc\n', True), ('', False), ('g', False), (' abc', False),
    ('abc ', False), ('abc\n\n', False), ('../abc', False),
])
def test_id_validator_is_not_length_or_fullmatch_policy(value, accepted, tmp_path, record_property):
    probe('''
        web.config.session_parameters.secret_key = os.environ['SESSION_SECRET_KEY']
        sess = session.Session(None, session.MemoryStore())
        value = ''' + repr(value) + '''
        assert bool(sess._valid_session_id(value)) is ''' + repr(accepted) + '''
        print(json.dumps({'value': value, 'accepted': bool(sess._valid_session_id(value))}))
    ''', tmp_path, record_property)


@pytest.mark.parametrize('scenario', ['read-overwrites-update', 'cleanup-live-iteration', 'cleanup-deletes-refresh'])
def test_memory_store_unsynchronized_interleaving_limitation(scenario, tmp_path, record_property):
    probe(r'''
        from types import SimpleNamespace
        session.time = SimpleNamespace(time=lambda: 100.0)
        scenario = ''' + repr(scenario) + r'''
        events = []
        class HookedDict(dict):
            armed = False
            def __getitem__(self, key):
                saved = super().__getitem__(key)
                if self.armed and scenario == 'read-overwrites-update':
                    self.armed = False
                    store[key] = {'version': 'new'}
                    events.append('concurrent-write')
                return saved
            def items(self):
                iterator = super().items()
                for pair in iterator:
                    yield pair
                    if self.armed:
                        self.armed = False
                        if scenario == 'cleanup-live-iteration':
                            store['other'] = {'version': 'new'}
                        elif scenario == 'cleanup-deletes-refresh':
                            store[pair[0]] = {'version': 'fresh'}
                        events.append('concurrent-write')
        backing = HookedDict({'id': (0.0, {'version': 'old'})})
        store = session.MemoryStore(backing)
        backing.armed = True
        if scenario == 'read-overwrites-update':
            assert store['id'] == {'version': 'old'}
            assert backing['id'] == (100.0, {'version': 'old'})
        elif scenario == 'cleanup-live-iteration':
            error = raises(RuntimeError, lambda: store.cleanup(10))
            assert 'dictionary changed size during iteration' in str(error)
            assert set(backing) == {'id', 'other'}
        else:
            store.cleanup(10)
            assert not backing  # refresh between selection and deletion was lost
        assert events == ['concurrent-write']
        print(json.dumps({'scenario': scenario, 'deterministic_interleaving': True,
                          'stress_test': False}))
    ''', tmp_path, record_property)


def test_thread_local_data_is_not_shared_store_synchronization(tmp_path, record_property):
    probe(r'''
        import threading
        web.config.session_parameters.secret_key = os.environ['SESSION_SECRET_KEY']
        sess = session.Session(None, session.MemoryStore())
        sess.value = 'main'
        observed = []
        def worker():
            observed.append(sess.get('value'))
            sess.value = 'worker'
            observed.append(sess.value)
        thread = threading.Thread(target=worker)
        thread.start()
        thread.join(3)
        assert not thread.is_alive()
        assert observed == [None, 'worker'] and sess.value == 'main'
        print(json.dumps({'thread_local': True, 'transaction_guarantee': False}))
    ''', tmp_path, record_property)


def test_current_import_chain_contains_python3_only_syntax(tmp_path, record_property):
    probe(r'''
        import ast
        tree = ast.parse(Path(session.__file__).read_text())
        assert any(isinstance(node, ast.JoinedStr) for node in ast.walk(tree))
        assert any(isinstance(node, ast.FunctionDef) and node.returns is not None
                   for node in ast.walk(tree))
        package = ast.parse(Path(web.__file__).read_text())
        assert any(isinstance(node, ast.ImportFrom) and node.module is None
                   and any(alias.name == 'session' for alias in node.names)
                   for node in ast.walk(package))
        assert sys.version_info.major == 3
        print(json.dumps({'tested_interpreter': sys.version, 'python2_executed': False,
                          'session_import': session.__file__}))
    ''', tmp_path, record_property)
