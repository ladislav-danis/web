"""Standalone README contracts: real WSGI requests, no Core or live server.

Each probe gets its own interpreter so application.request's ThreadedDict cleanup
cannot clear another test's session/DB context or change global web.config.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import textwrap


WEB_ROOT = Path(__file__).resolve().parents[1]
BOOTSTRAP = r'''
import importlib.abc
import json
from pathlib import Path
import sys

class NoMosaic(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {'core', 'modules', 'dotenv'}:
            raise AssertionError('Standalone example imported ' + fullname)
sys.meta_path.insert(0, NoMosaic())

def offline(event, args):
    if event in {'socket.connect', 'socket.getaddrinfo', 'socket.bind'}:
        raise AssertionError('Standalone probe attempted network: ' + event)
sys.addaudithook(offline)
sys.path.insert(0, sys.argv[1])
import web
assert Path(web.__file__).resolve().parent == Path(sys.argv[1]) / 'web'
web.config.debug = False
'''


def probe(source, tmp_path, record_property):
    env = {'PATH': os.defpath, 'PYTHON_DOTENV_DISABLED': '1',
           'TMPDIR': str(tmp_path), 'HOME': str(tmp_path)}
    result = subprocess.run(
        [sys.executable, '-I', '-c', BOOTSTRAP + '\n' + textwrap.dedent(source),
         str(WEB_ROOT.parent)], cwd=tmp_path, env=env,
        text=True, capture_output=True, timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    evidence = json.loads(result.stdout)
    record_property('standalone_result', json.dumps(evidence, sort_keys=True))
    return evidence


def test_readme_hello_fence_executes_offline(tmp_path, record_property):
    probe(r'''
        import hashlib
        import re
        readme = Path(web.__file__).with_name('README.md')
        section = readme.read_text(encoding='utf-8').split('## Quick Start', 1)[1].split('\n## ', 1)[0]
        fences = re.findall(r'^```python\n(.*?)^```', section, flags=re.M | re.S)
        assert len(fences) == 1
        source = fences[0]
        started = []
        # Replace only the indefinite server entry point; execute every fenced
        # byte unchanged, then exercise the actual resulting WSGI application.
        original_run = web.application.run
        web.application.run = lambda app, *a, **kw: started.append(app)
        namespace = {'__name__': '__main__'}
        try:
            exec(compile(source, str(readme) + ':Quick Start', 'exec'), namespace)
        finally:
            web.application.run = original_run
        app = namespace['app']
        assert started == [app]
        response = app.request('/hello')
        assert response.status == '200 OK'
        assert response.data == b'Hello, world!'
        assert app.request('/missing').status == '404 Not Found'
        assert app.request('/hello', method='POST').status == '405 Method Not Allowed'
        assert not any(n == 'core' or n.startswith('core.') for n in sys.modules)
        print(json.dumps({'hello': response.data.decode(), 'status': response.status,
                          'fence_sha256': hashlib.sha256(source.encode()).hexdigest(),
                          'server_entry_calls': len(started)}))
    ''', tmp_path, record_property)


def test_plain_post_has_no_implicit_csrf_or_access_gate(tmp_path, record_property):
    probe(r'''
        calls = []
        class Submit:
            def POST(self):
                values = dict(web.input())
                calls.append(values)
                return values['message']
        app = web.application(('/submit', Submit), locals(), autoreload=False)
        # No cookie, login, CSRF field or CSRF header is supplied.
        response = app.request('/submit', method='POST', data='message=plain+post',
                               headers={'Content-Type': 'application/x-www-form-urlencoded'})
        assert response.status == '200 OK'
        assert response.data == b'plain post'
        assert calls == [{'message': 'plain post'}]
        assert not any(k.lower() == 'set-cookie' for k, v in response.header_items)
        print(json.dumps({'status': response.status, 'handler_inputs': calls, 'cookie': False}))
    ''', tmp_path, record_property)


def test_routes_require_explicit_mapping(tmp_path, record_property):
    probe(r'''
        class Initial:
            def GET(self):
                return 'initial'
        class Later:
            def GET(self, name):
                return 'later:' + name
        app = web.application(('/initial', Initial), locals(), autoreload=False)
        assert app.request('/initial').data == b'initial'
        assert app.request('/later/alice').status == '404 Not Found'
        app.add_mapping('/later/(.*)', Later)
        response = app.request('/later/alice')
        assert response.status == '200 OK'
        assert response.data == b'later:alice'
        assert app.request('/unregistered').status == '404 Not Found'
        print(json.dumps({'before': '404 Not Found', 'after': response.status,
                          'body': response.data.decode()}))
    ''', tmp_path, record_property)


def test_session_cookie_identifies_server_side_store(tmp_path, record_property):
    probe(r'''
        from http.cookies import SimpleCookie
        web.config.session_parameters.secret_key = 'readme-test-only-secret'
        app = web.application((), {}, autoreload=False)
        store = web.session.MemoryStore()
        session = web.session.Session(app, store, initializer={'count': 0})
        class Counter:
            def POST(self):
                session.count += 1
                session.payload = 'only-in-server-store'
                return str(session.count)
        app.add_mapping('/count', Counter)
        first = app.request('/count', method='POST', data='')
        assert first.status == '200 OK' and first.data == b'1'
        cookies = SimpleCookie()
        for key, value in first.header_items:
            if key.lower() == 'set-cookie':
                cookies.load(value)
        assert set(cookies) == {'webpy_session_id'}
        sid = cookies['webpy_session_id'].value
        assert sid in store
        assert store[sid]['count'] == 1
        assert store[sid]['payload'] == 'only-in-server-store'
        assert 'csrf_token' not in store[sid]
        assert 'only-in-server-store' not in cookies.output()
        second = app.request('/count', method='POST', data='',
                             headers={'Cookie': 'webpy_session_id=' + sid})
        assert second.status == '200 OK' and second.data == b'2'
        assert store[sid]['count'] == 2
        separate = app.request('/count', method='POST', data='')
        assert separate.status == '200 OK' and separate.data == b'1'
        assert len(store.d_store) == 2
        print(json.dumps({'first': first.data.decode(), 'same_cookie': second.data.decode(),
                          'no_cookie': separate.data.decode(), 'server_stores': len(store.d_store),
                          'tokenless_session_post': second.status}))
    ''', tmp_path, record_property)


def test_database_backend_registration_names(tmp_path, record_property):
    probe(r'''
        import importlib
        db = importlib.import_module('web.db')
        expected = {'mysql': 'MySQLDB', 'postgres': 'PostgresDB', 'sqlite': 'SqliteDB',
                    'firebird': 'FirebirdDB', 'mssql': 'MSSQLDB', 'oracle': 'OracleDB'}
        actual = {key: cls.__name__ for key, cls in db._databases.items()}
        assert actual == expected
        # Display names are not extra aliases accepted by database(dbn=...).
        for name in ('postgresql', 'sqlite3', 'sqlserver'):
            try:
                web.database(dbn=name)
            except db.UnknownDB:
                pass
            else:
                raise AssertionError('Unexpected backend alias: ' + name)
        print(json.dumps(actual, sort_keys=True))
    ''', tmp_path, record_property)
