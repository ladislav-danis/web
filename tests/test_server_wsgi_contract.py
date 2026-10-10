"""Server/dispatch characterizations and executable documentation contracts.

Fresh interpreters isolate web globals. Python audit hooks deny nonlocal network,
processes and application imports; these guards are not an OS/native sandbox.
Only dispatch/optional-flup boundaries are recording stubs, never live deployment.
"""
import os
from pathlib import Path
import subprocess
import sys
import textwrap

import pytest

WEB_ROOT = Path(__file__).resolve().parents[1]
BOOTSTRAP = r'''
import hashlib
import importlib.abc
import io
import json
import os
from pathlib import Path
import socket
import sys
import threading
import types

class NoApplication(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {'core', 'modules', 'dotenv'}:
            raise AssertionError('Unexpected application import: ' + fullname)
sys.meta_path.insert(0, NoApplication())
ports, listeners, events, hashes = set(), [], [], []
cached_bind = socket.socket.bind
original_listen = socket.socket.listen
class Denied(BaseException):
    pass

def audit(event, args):
    if event in {'socket.bind', 'socket.connect', 'socket.sendto'}:
        sock, address = args[0], args[-1]
        allowed = (sock.family in (socket.AF_INET, socket.AF_INET6)
                   and isinstance(address, tuple)
                   and address[0] in ('127.0.0.1', '::1'))
        if event != 'socket.bind':
            allowed = allowed and address[1] in ports
        events.append([event, list(address) if isinstance(address, tuple) else str(address), allowed])
        if not allowed:
            raise Denied(event)
    if event in {'socket.getaddrinfo', 'socket.gethostbyname', 'socket.gethostbyaddr'}:
        if args[0] not in ('127.0.0.1', '::1'):
            raise Denied(event)
    if event in {'subprocess.Popen', 'os.system', 'os.posix_spawn'}:
        raise Denied(event)
sys.addaudithook(audit)

def bind(sock, address):
    result = cached_bind(sock, address)
    ports.add(sock.getsockname()[1])
    return result

def listen(sock, *args):
    actual = sock.getsockname()
    assert actual[0] in ('127.0.0.1', '::1') and actual[1]
    result = original_listen(sock, *args)
    listeners.append((sock, actual))
    return result
socket.socket.bind = bind
socket.socket.listen = listen
sys.path.insert(0, sys.argv[1])
import web
from web import httpserver, wsgi
assert Path(web.__file__).resolve().parent == Path(sys.argv[1]) / 'web'
web.config.debug = False

def blocks(document):
    text = Path(web.__file__).with_name('docs').joinpath(document).read_text()
    heading, fence, current, result = None, None, [], {}
    for line in text.splitlines(keepends=True):
        if fence is not None:
            if line.startswith('```'):
                if fence == 'python':
                    assert heading not in result, heading
                    result[heading] = ''.join(current)
                fence, current = None, []
            else:
                current.append(line)
        elif line.startswith('```'):
            fence = line.strip()[3:]
        elif line.startswith('#'):
            heading = line.lstrip('#').strip()
    assert fence is None, 'Unclosed Markdown fence'
    return result

def execute(document, heading):
    source = blocks(document)[heading]
    hashes.append([document, heading, hashlib.sha256(source.encode()).hexdigest()])
    ns = {'__name__': 'documentation_example'}
    exec(compile(source, '<' + document + ':' + heading + '>', 'exec'), ns)
    return ns
'''


def probe(source, tmp_path, record_property):
    script = tmp_path / 'probe.py'
    script.write_text(BOOTSTRAP + '\n' + textwrap.dedent(source) + '''
assert all(s.fileno() == -1 for s, addr in listeners), listeners
assert socket.socket.bind is bind and socket.socket.listen is listen
print(json.dumps({'fence_sha256': hashes, 'network_events': events,
                  'listeners_closed': [addr for s, addr in listeners],
                  'pid': os.getpid()}))
''')
    result = subprocess.run(
        [sys.executable, '-I', str(script), str(WEB_ROOT.parent)],
        cwd=tmp_path, env={'PATH': os.defpath, 'HOME': str(tmp_path),
                          'TMPDIR': str(tmp_path), 'PYTHONDONTWRITEBYTECODE': '1',
                          'PYTHON_DOTENV_DISABLED': '1'},
        text=True, capture_output=True, timeout=30,
    )
    record_property('probe_stdout', result.stdout)
    record_property('probe_stderr', result.stderr)
    assert result.returncode == 0, result.stdout + result.stderr


def test_runbasic_python3_fails_before_any_bind(tmp_path, record_property):
    probe('''
        assert 'SocketServer' not in sys.modules
        before = len(events)
        try:
            httpserver.runbasic(lambda env, start: [], ('127.0.0.1', 0))
        except ModuleNotFoundError as exc:
            assert exc.name == 'SocketServer'
        else:
            raise AssertionError('Legacy entry point unexpectedly succeeded')
        assert events[before:] == []  # actual import failure, no aliases or bind
        assert not listeners
    ''', tmp_path, record_property)


def test_runsimple_blocks_returns_none_retains_stopped_global(tmp_path, record_property):
    probe('''
        import http.client
        ready, finished = threading.Event(), threading.Event()
        owned, results, errors = [], [], []
        factory = httpserver.WSGIServer
        def make(address, application):
            server = factory(address, application)
            server.shutdown_timeout = 2
            server.reuse_port = False  # Cheroot rejects reuse_port with port 0
            owned.append(server)
            prepare = server.prepare
            def prepared():
                prepare()
                ready.set()
            server.prepare = prepared
            return server
        httpserver.WSGIServer = make
        class Index:
            def GET(self): return 'actual runsimple'
        app = web.application(('/', Index), locals(), autoreload=False)
        def run():
            try:
                results.append(httpserver.runsimple(app.wsgifunc(), ('127.0.0.1', 0)))
            except BaseException as exc:
                errors.append(exc)
                ready.set()
            finally:
                finished.set()
        thread = threading.Thread(target=run)
        connection = None
        try:
            thread.start()
            assert ready.wait(5) and not errors, errors
            assert not finished.is_set() and not results and thread.is_alive()
            server = owned[0]
            assert httpserver.server is server
            assert isinstance(server.wsgi_app, httpserver.LogMiddleware)
            assert isinstance(server.wsgi_app.app, httpserver.StaticMiddleware)
            address = server.socket.getsockname()
            assert address[0] == '127.0.0.1' and address[1] > 0
            connection = http.client.HTTPConnection(*address[:2], timeout=3)
            connection.request('GET', '/')
            response = connection.getresponse()
            assert response.status == 200 and response.read() == b'actual runsimple'
        finally:
            if connection: connection.close()
            for server in owned:
                server.stop()
            thread.join(5)
            httpserver.WSGIServer = factory
        assert not thread.is_alive() and finished.is_set() and not errors
        assert results == [None]
        assert httpserver.server is server and not server.ready
        assert server.socket is None
    ''', tmp_path, record_property)


@pytest.mark.parametrize('exception', ['KeyboardInterrupt', 'SystemExit', 'ValueError'])
def test_runsimple_exception_global_policy(exception, tmp_path, record_property):
    probe('''
        factory, owned = httpserver.WSGIServer, []
        def make(address, application):
            server = factory(address, application)
            server.shutdown_timeout = 2
            server.reuse_port = False  # Cheroot rejects reuse_port with port 0
            owned.append(server)
            def start():
                server.prepare()  # real owned listener and Cheroot workers
                raise EXCEPTION('injected after real prepare')
            server.start = start
            return server
        httpserver.WSGIServer = make
        try:
            if EXCEPTION is ValueError:
                try:
                    httpserver.runsimple(lambda env, start: [], ('127.0.0.1', 0))
                except ValueError:
                    pass
                else:
                    raise AssertionError('Unexpected exception suppression')
                assert httpserver.server is owned[0] and owned[0].ready
            else:
                assert httpserver.runsimple(lambda env, start: [], ('127.0.0.1', 0)) is None
                assert httpserver.server is None
                assert not owned[0].ready and owned[0].socket is None
        finally:
            for server in owned: server.stop()
            httpserver.WSGIServer = factory
    '''.replace('EXCEPTION', exception), tmp_path, record_property)


def test_stopping_documentation_is_self_contained_live_http(tmp_path, record_property):
    probe('''
        web.config.debug = True  # recipe must establish its own policy
        ns = execute('httpserver.md', 'Stopping the Server')
        assert ns['status'] == 200 and ns['body'] == b'Hello World!'
        assert ns['address'][0] == '127.0.0.1' and ns['address'][1] > 0
        assert not ns['thread'].is_alive() and ns['server'].socket is None
        assert web.config.debug is False
        assert httpserver.server is None  # explicit instance, not runsimple global
        assert len(listeners) == 1
        # Independent real framework dispatch, not just the snippet's assertions.
        assert ns['app'].request('/').data == b'Hello World!'
        assert ns['app'].request('/missing').status == '404 Not Found'
        def fail(self): raise ValueError('PRIVATE-DOC-SENTINEL')
        ns['index'].GET = fail
        response = ns['app'].request('/')
        assert response.status == '500 Internal Server Error'
        assert response.data == b'internal server error'
        assert b'PRIVATE-DOC-SENTINEL' not in response.data
    ''', tmp_path, record_property)


@pytest.mark.parametrize('environment,argv,expected', [
    ({}, ['app.py'], True),
    ({'SERVER_SOFTWARE': ''}, ['app.py'], False),
    ({'SERVER_SOFTWARE': 'server'}, ['app.py'], False),
    ({'PHP_FCGI_CHILDREN': ''}, ['app.py'], False),
    ({'PHP_FCGI_CHILDREN': '2'}, ['app.py'], False),
    ({}, ['app.py', 'fcgi'], False),
    ({}, ['app.py', 'fastcgi'], False),
    ({}, ['app.py', 'mod_wsgi'], False),
    ({}, ['app.py', 'scgi'], True),
    ({'PORT': '9000'}, ['app.py'], True),
    ({}, ['app.py', 'FCGI'], True),
    ({}, ['fcgi'], False),
    ({}, None, True),
])
def test_dev_heuristic_and_actual_import_setdefault(environment, argv, expected,
                                                   tmp_path, record_property):
    probe('''
        import importlib
        os.environ.update(ENVIRONMENT)
        if ARGV is None:
            del sys.argv
        else:
            sys.argv = ARGV
        assert wsgi._is_dev_mode() is EXPECTED
        for preset in (None, True, False):
            for mode in ('import', 'reload'):
                web.config.pop('debug', None)
                if preset is not None:
                    web.config.debug = preset
                if mode == 'import':
                    del sys.modules['web.wsgi']
                    wsgi = importlib.import_module('web.wsgi')
                else:
                    wsgi = importlib.reload(wsgi)
                assert wsgi._is_dev_mode() is EXPECTED
                assert web.config.debug is (EXPECTED if preset is None else preset)
    '''.replace('ENVIRONMENT', repr(environment)).replace('ARGV', repr(argv))
       .replace('EXPECTED', repr(expected)), tmp_path, record_property)


def test_production_documentation_sets_debug_before_construction(tmp_path, record_property):
    probe('''
        web.config.debug = True
        constructed = []
        original_init = web.application.__init__
        def observe(self, *args, **kwargs):
            constructed.append(web.config.debug)
            original_init(self, *args, **kwargs)
        web.application.__init__ = observe
        try:
            ns = execute('wsgi.md', 'Basic WSGI Deployment')
        finally:
            web.application.__init__ = original_init
        assert constructed == [False]
        assert web.config.debug is False
        assert ns['app'].request('/').data == b'Hello World!'
        def fail(self): raise ValueError('PRIVATE-PRODUCTION-SENTINEL')
        ns['index'].GET = fail
        response = ns['app'].request('/')
        assert response.status == '500 Internal Server Error'
        assert response.data == b'internal server error'
        assert callable(ns['application'])
    ''', tmp_path, record_property)


@pytest.mark.parametrize('environment,argv,expected,parsed,force', [
    ({}, ['app.py'], ('simple', ('0.0.0.0', 8080)), [''], None),
    ({}, [], ('simple', ('0.0.0.0', 8080)), [''], None),
    ({}, ['app.py', '127.0.0.1:9000', 'ignored'], ('simple', ('127.0.0.1', 9000)), ['127.0.0.1:9000'], None),
    ({'PORT': '9001'}, ['app.py', '127.0.0.1:9000'], ('simple', ('0.0.0.0', 9001)), ['127.0.0.1:9000'], None),
    ({'PORT': 'not-a-port'}, ['app.py'], ('simple', ('0.0.0.0', None)), [''], None),
    ({'PORT': ''}, ['app.py'], ('simple', ('0.0.0.0', None)), [''], None),
    ({'PORT': '-1'}, ['app.py'], ('simple', ('0.0.0.0', -1)), [''], None),
    ({'PORT': '0'}, ['app.py'], ('simple', ('0.0.0.0', 0)), [''], None),
    ({'PORT': '65536'}, ['app.py'], ('simple', ('0.0.0.0', 65536)), [''], None),
    ({'PORT': ' 9000 '}, ['app.py'], ('simple', ('0.0.0.0', 9000)), [''], None),
    ({'PORT': '9001'}, ['app.py', 'invalid'], 'ValueError', ['invalid'], None),
    ({'PORT': '9001'}, ['app.py', '65536'], 'ValueError', ['65536'], None),
    ({'SERVER_SOFTWARE': '', 'PORT': 'bad'}, ['app.py', 'scgi', 'invalid'], ('fcgi', None), [], 'Y'),
    ({'SERVER_SOFTWARE': 'cgi', 'PHP_FCGI_CHILDREN': '', 'FCGI_FORCE_CGI': 'N'}, ['app.py', 'fcgi'], ('fcgi', None), [], 'Y'),
    ({'PHP_FCGI_CHILDREN': '', 'PORT': 'bad'}, ['app.py', 'scgi'], ('fcgi', None), [], None),
    ({'PHP_FCGI_CHILDREN': '2', 'FCGI_FORCE_CGI': 'N'}, ['app.py'], ('fcgi', None), [], 'N'),
    ({}, ['app.py', 'fcgi'], ('fcgi', None), [], None),
    ({}, ['app.py', 'fastcgi'], ('fcgi', None), [], None),
    ({'PORT': 'invalid'}, ['app.py', 'fcgi', '127.0.0.1:9000'], ('fcgi', ('127.0.0.1', 9000)), ['127.0.0.1:9000'], None),
    ({}, ['app.py', '127.0.0.1:9000', 'fastcgi', 'extra'], ('fcgi', ('127.0.0.1', 9000)), ['127.0.0.1:9000'], None),
    ({}, ['app.py', 'fcgi', 'fastcgi'], 'ValueError', ['fcgi'], None),
    ({}, ['app.py', 'fastcgi', 'fastcgi'], 'ValueError', ['fastcgi'], None),
    ({}, ['app.py', 'scgi', 'fcgi'], 'ValueError', ['scgi'], None),
    ({}, ['fcgi'], ('fcgi', None), [], None),
    ({}, ['app.py', 'scgi'], ('scgi', ('localhost', 4000)), [], None),
    ({'PORT': 'bad'}, ['app.py', 'scgi', '127.0.0.1:4001'], ('scgi', ('127.0.0.1', 4001)), ['127.0.0.1:4001'], None),
    ({}, ['app.py', 'scgi', 'scgi'], 'ValueError', ['scgi'], None),
    ({}, ['scgi'], 'ValueError', [], None),
    ({}, ['app.py', 'mod_wsgi'], 'ValueError', ['mod_wsgi'], None),
    ({}, ['app.py', 'fcgi', '/owned/example.sock'], ('fcgi', '/owned/example.sock'), ['/owned/example.sock'], None),
    ({}, None, 'AttributeError', [], None),
])
def test_runwsgi_dispatch_boundary(environment, argv, expected, parsed, force,
                                   tmp_path, record_property):
    probe('''
        os.environ.update(ENVIRONMENT)
        if ARGV is None:
            del sys.argv
        else:
            sys.argv = ARGV
        argv_before = getattr(sys, 'argv', None)
        argv_copy = None if argv_before is None else list(argv_before)
        calls, validations = [], []
        application, result = object(), object()
        def fcgi(func, addr=('localhost', 8000)):
            assert func is application
            calls.append(('fcgi', addr))
            return result
        def scgi(func, addr=('localhost', 4000)):
            assert func is application
            calls.append(('scgi', addr))
            return result
        def simple(func, addr):
            assert func is application
            calls.append(('simple', addr))
            return result
        validaddr = wsgi.validaddr
        def validate(value):
            validations.append(value)
            return validaddr(value)
        wsgi.runfcgi, wsgi.runscgi = fcgi, scgi
        httpserver.runsimple = simple
        wsgi.validaddr = validate
        expected = EXPECTED
        if isinstance(expected, str):
            try: wsgi.runwsgi(application)
            except Exception as exc: assert type(exc).__name__ == expected
            else: raise AssertionError('Missing dispatch error')
            assert calls == []
        else:
            assert wsgi.runwsgi(application) is result
            assert calls == [expected]
        assert validations == PARSED
        assert getattr(sys, 'argv', None) is argv_before
        assert getattr(sys, 'argv', None) == argv_copy
        after_env = dict(ENVIRONMENT)
        if FORCE_VALUE is not None: after_env['FCGI_FORCE_CGI'] = FORCE_VALUE
        for key in ('PORT', 'SERVER_SOFTWARE', 'PHP_FCGI_CHILDREN', 'FCGI_FORCE_CGI'):
            assert os.environ.get(key) == after_env.get(key)
        assert not events and not listeners
        print(json.dumps({'dispatch': calls, 'validaddr_inputs': validations,
                          'fcgi_force_cgi': os.environ.get('FCGI_FORCE_CGI')}))
    '''.replace('ENVIRONMENT', repr(environment)).replace('ARGV', repr(argv))
       .replace('EXPECTED', repr(expected)).replace('PARSED', repr(parsed))
       .replace('FORCE_VALUE', repr(force)), tmp_path, record_property)


@pytest.mark.parametrize('backend', ['fcgi', 'scgi'])
def test_direct_flup_adapter_passes_unvalidated_address(backend, tmp_path, record_property):
    probe('''
        import importlib
        backend = BACKEND
        try:
            module = importlib.import_module('flup.server.' + backend)
        except ModuleNotFoundError as exc:
            availability = {'available': False, 'missing': exc.name}
        else:
            availability = {'available': True, 'module': module.__name__}
        print(json.dumps({'optional_flup': availability}))
        # Recording import boundary ONLY: no flup constructor/run is invoked.
        modules = {name: types.ModuleType(name) for name in
                   ('flup', 'flup.server', 'flup.server.' + backend)}
        modules['flup'].__path__ = []
        modules['flup.server'].__path__ = []
        modules['flup'].server = modules['flup.server']
        setattr(modules['flup.server'], backend, modules['flup.server.' + backend])
        sys.modules.update(modules)
        calls, runs = [], []
        application, result = object(), object()
        class Boundary:
            def __init__(self, func, **kwargs):
                assert func is application
                calls.append(kwargs)
            def run(self):
                runs.append(True)
                return result
        modules['flup.server.' + backend].WSGIServer = Boundary
        def forbidden(value): raise AssertionError('Unexpected validaddr call')
        wsgi.validaddr = forbidden
        entry = getattr(wsgi, 'run' + backend)
        assert entry(application) is result
        default = ('localhost', 8000 if backend == 'fcgi' else 4000)
        addresses = [None, ('invalid-host', -1), '/unvalidated/socket', object()]
        for address in addresses:
            assert entry(application, address) is result
        for options, address in zip(calls, [default] + addresses):
            assert options['bindAddress'] is address or options['bindAddress'] == address
            expected = {'bindAddress': address, 'debug': False}
            if backend == 'fcgi': expected['multiplexed'] = True
            assert options == expected
        assert len(runs) == len(calls) == 5
        assert not events and not listeners
    '''.replace('BACKEND', repr(backend)), tmp_path, record_property)


def test_port_documentation_validates_explicit_policy(tmp_path, record_property):
    probe('''
        ns = execute('wsgi.md', 'Heroku Deployment')
        configured_address = ns['configured_address']
        for env, expected in [({}, 8080), ({'PORT': '1'}, 1),
                              ({'PORT': '9000'}, 9000), ({'PORT': '65535'}, 65535)]:
            assert configured_address(env) == ('127.0.0.1', expected)
        for value in ('', 'not-a-port', '-1', '0', '65536', ' 9000 ', '+9000', '９０００'):
            try: configured_address({'PORT': value})
            except ValueError: pass
            else: raise AssertionError('Invalid deployment PORT accepted: ' + repr(value))
        assert ns['address'] == ('127.0.0.1', 8080)
        assert not events and not listeners
    ''', tmp_path, record_property)


@pytest.mark.parametrize('failure', ['prepare', 'thread-start', 'http', 'serve'])
def test_documented_owned_lifecycle_cleans_up_failures(failure, tmp_path, record_property):
    probe('''
        import http.client
        failure, owned, threads = FAILURE, [], []
        class InjectedError(Exception): pass
        class ServingFailure(Exception): pass
        injected = InjectedError(failure)
        serving_error = ServingFailure('original serving failure')
        def fail(*args, **kwargs): raise injected
        def fail_serve(): raise serving_error
        factory = httpserver.WSGIServer
        def make(address, application):
            server = factory(address, application)
            owned.append(server)
            if failure == 'prepare':
                server.requests.start = fail  # real bind/listen, before ready=True
            elif failure == 'serve':
                server.serve = fail_serve
            return server
        httpserver.WSGIServer = make
        start = threading.Thread.start
        def record_start(thread):
            if thread.name == 'owned-wsgi-example' and failure == 'thread-start':
                threads.append(thread)
                fail()
            result = start(thread)
            threads.append(thread)  # exact serving and real Cheroot worker objects
            if thread.name == 'owned-wsgi-example' and failure == 'serve':
                thread.join(5)  # failure is captured before HTTP starts, no sleep
                assert not thread.is_alive()
            return result
        threading.Thread.start = record_start
        if failure == 'http':
            getresponse = http.client.HTTPConnection.getresponse
            def fail_http(connection):
                response = getresponse(connection)  # real owned-loopback HTTP
                assert response.status == 200 and response.read() == b'Hello World!'
                raise injected
            http.client.HTTPConnection.getresponse = fail_http
        source = blocks('httpserver.md')['Stopping the Server']
        hashes.append(['httpserver.md', 'Stopping the Server', hashlib.sha256(source.encode()).hexdigest()])
        ns = {'__name__': 'documentation_example'}
        observed = None
        try:
            exec(compile(source, '<documented lifecycle failure>', 'exec'), ns)
        except BaseException as exc:
            observed = exc
        else:
            raise AssertionError('Injected lifecycle failure not observed')
        assert len(owned) == 1 and not owned[0].ready and owned[0].socket is None
        assert all(not thread.is_alive() for thread in threads)
        assert not ns['thread'].is_alive()
        assert len(listeners) == 1
        assert all(sock.fileno() == -1 for sock, address in listeners)
        if ns['connection'] is not None:
            assert ns['connection'].sock is None
        import traceback
        frames = [frame.name for frame in traceback.extract_tb(observed.__traceback__)]
        if failure == 'serve':
            assert ns['errors'] == [serving_error]
            # The documented precedence retains both original failures/tracebacks.
            assert observed is serving_error
            assert isinstance(observed.__cause__, TimeoutError)
            assert 'fail_serve' in frames
            assert 'getresponse' in [frame.name for frame in
                                     traceback.extract_tb(observed.__cause__.__traceback__)]
        else:
            assert observed is injected
            assert observed.__cause__ is None
            assert ('fail_http' if failure == 'http' else 'fail') in frames
            assert ns['errors'] == []
        print(json.dumps({'failure': failure, 'exception': type(observed).__name__,
                          'cause': None if observed.__cause__ is None else type(observed.__cause__).__name__,
                          'original_exception_preserved': True, 'traceback_frames': frames,
                          'owned_threads_joined': [thread.name for thread in threads]}))
    '''.replace('FAILURE', repr(failure)), tmp_path, record_property)


def test_factory_and_static_log_wrapper_boundaries(tmp_path, record_property):
    probe('''
        from wsgiref.util import setup_testing_defaults
        calls = []
        def application(env, start_response):
            calls.append(env['PATH_INFO'])
            start_response('200 OK', [('Content-Type', 'text/plain')])
            return [b'dynamic route']
        server = httpserver.WSGIServer(('127.0.0.1', 0), application)
        assert server.wsgi_app is application
        assert server.server_name == 'localhost' and server.reuse_port is True
        assert server.nodelay is (not sys.platform.startswith('java'))
        assert not server.ready and not listeners
        Path('static').mkdir()
        Path('static/owned.txt').write_bytes(b'owned static bytes')
        wrapped = httpserver.LogMiddleware(httpserver.StaticMiddleware(application))
        for path, expected in [('/static/owned.txt', b'owned static bytes'),
                               ('/', b'dynamic route')]:
            env, captured, log = {}, [], io.StringIO()
            setup_testing_defaults(env)
            env.update(PATH_INFO=path, REQUEST_METHOD='GET', REMOTE_ADDR='127.0.0.1',
                       REMOTE_PORT='12345', ACTUAL_SERVER_PROTOCOL='HTTP/1.1')
            env['wsgi.errors'] = log
            def start_response(status, headers, exc_info=None):
                captured.append((status, headers))
            result = wrapped(env, start_response)
            try: assert b''.join(result) == expected
            finally:
                if hasattr(result, 'close'): result.close()
            print(json.dumps({'wrapper_path': path, 'response': captured, 'log': log.getvalue()}))
            expected_status = '200 ' if path.startswith('/static/') else '200 OK'
            assert captured[0][0] == expected_status
            assert '"HTTP/1.1 GET ' + path + '" - ' + expected_status in log.getvalue()
        assert calls == ['/']
        assert not events and not listeners
    ''', tmp_path, record_property)


def test_all_executable_fences_are_accounted_for(tmp_path, record_property):
    probe('''
        expected = {'httpserver.md': {'Stopping the Server'},
                    'wsgi.md': {'Basic WSGI Deployment', 'Heroku Deployment'}}
        for document, headings in expected.items():
            sources = blocks(document)
            assert set(sources) == headings
            for heading, source in sources.items():
                compile(source, document + ':' + heading, 'exec')
    ''', tmp_path, record_property)


def test_probe_network_guard_rejects_cached_wildcard_and_external(tmp_path, record_property):
    probe('''
        for family, host in ((socket.AF_INET, '0.0.0.0'), (socket.AF_INET6, '::')):
            with socket.socket(family, socket.SOCK_STREAM) as sock:
                try: cached_bind(sock, (host, 0))
                except Denied: pass
                else: raise AssertionError('Cached C bind bypassed audit guard')
        with socket.socket() as sock:
            for target in (('192.0.2.1', 80), ('127.0.0.1', 1)):
                try: sock.connect(target)
                except Denied: pass
                else: raise AssertionError('Unowned target allowed')
        for host in ('external.invalid', 'localhost'):
            try: socket.getaddrinfo(host, 80)
            except Denied: pass
            else: raise AssertionError('Unapproved DNS allowed')
        with socket.socket(socket.AF_INET6, socket.SOCK_STREAM) as sock:
            try: sock.bind(('::1', 0))
            except OSError as exc:
                print(json.dumps({'ipv6_loopback_available': False, 'errno': exc.errno}))
            else:
                sock.listen(1)
                assert sock.getsockname()[0] == '::1'
                print(json.dumps({'ipv6_loopback_available': True}))
    ''', tmp_path, record_property)


def test_legacy_documentation_is_not_a_deployment_recipe():
    text = (WEB_ROOT / 'docs/httpserver.md').read_text()
    assert 'unsupported legacy' in text.lower()
    assert 'ModuleNotFoundError' in text and 'SocketServer' in text
    assert 'Python 2 compatible' not in text
    assert 'maintained for Python 2' not in text
    import re
    executable = '\n'.join(re.findall(r'```python\n(.*?)```', text, re.S))
    assert '.runbasic(' not in executable
