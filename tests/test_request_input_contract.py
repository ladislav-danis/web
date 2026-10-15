"""Missing request input contracts through real WSGI and AppBrowser.

Fresh guard-first -I -B children avoid clearing unrelated Core thread locals.
These are in-process HTTP tests, not network-wire or OS-sandbox guarantees.
"""
import hashlib
import json
import os
import subprocess
import sys
import textwrap

import pytest

from .test_template_security_contract import BOOTSTRAP, WEB_ROOT


SOURCE_FILES = ('application.py', 'webapi.py', 'browser.py', '__init__.py')


def probe(source, tmp_path, record_property):
    env = {'PATH': os.defpath, 'PYTHON_DOTENV_DISABLED': '1', 'LC_ALL': 'C'}
    for key in ('HOME', 'TMPDIR', 'XDG_CACHE_HOME', 'XDG_DATA_HOME', 'XDG_CONFIG_HOME'):
        env[key] = str(tmp_path)
    program = BOOTSTRAP + '\n' + '''
import hashlib
source_hashes = {name: hashlib.sha256((Path(sys.argv[1]) / 'web' / name).read_bytes()).hexdigest()
                 for name in ('application.py', 'webapi.py', 'browser.py', '__init__.py')}
print(json.dumps({'bootstrap': True, 'isolated': sys.flags.isolated,
                  'no_bytecode': sys.dont_write_bytecode, 'sources': source_hashes}), flush=True)
''' + textwrap.dedent(source) + '''
assert not {'core', 'modules', 'dotenv'}.intersection(sys.modules)
assert not blocked
print(json.dumps({'completed': True, 'isolated': sys.flags.isolated,
                  'no_bytecode': sys.dont_write_bytecode}))
'''
    argv = [sys.executable, '-I', '-B', '-c', program, str(WEB_ROOT.parent)]
    result = subprocess.run(argv, cwd=tmp_path, env=env, text=True,
                            capture_output=True, timeout=30)
    record_property('child_argv', json.dumps(argv))
    record_property('child_environment', json.dumps(env))
    record_property('program_sha256', hashlib.sha256(program.encode()).hexdigest())
    record_property('probe_stdout', result.stdout)
    record_property('probe_stderr', result.stderr)
    record_property('child_returncode', result.returncode)
    bootstrap = json.loads(result.stdout.splitlines()[0])
    assert bootstrap == {'bootstrap': True, 'isolated': 1, 'no_bytecode': True,
                         'sources': {n: hashlib.sha256((WEB_ROOT / n).read_bytes()).hexdigest()
                                     for n in SOURCE_FILES}}
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout.splitlines()[-1]) == {
        'completed': True, 'isolated': 1, 'no_bytecode': True}


@pytest.mark.parametrize('client', ['request', 'appbrowser'])
def test_get_without_input_returns_empty_body(client, tmp_path, record_property):
    probe('client = ' + repr(client) + '\n' + r'''
class Page:
    def GET(self):
        return web.data()
app = web.application(('/', Page), {}, autoreload=False)
if client == 'request':
    response = app.request('/')
    status, body = response.status, response.data
else:
    browser = app.browser()
    response = browser.open('/')
    status, body = str(browser.status) + ' ' + browser._response.msg, response.read()
    assert browser.data == body
print(json.dumps({'client': client, 'status': status, 'body_hex': body.hex()}))
assert (status, body) == ('200 OK', b''), (status, body)
assert dict(web.ctx.items()) == {}
''', tmp_path, record_property)


@pytest.mark.parametrize('method', ['GET', 'HEAD'])
@pytest.mark.parametrize('payload', ['none', 'bytes', 'str', 'dict', 'invalid-truthiness'])
def test_missing_input_ignores_data_without_coercion(method, payload, tmp_path, record_property):
    probe('method, payload = ' + repr((method, payload)) + '\n' + r'''
from io import BytesIO
class Poison:
    def __bool__(self): raise AssertionError('data truthiness must not be evaluated')
    def __str__(self): raise AssertionError('data must not be converted')
body = {'none': None, 'bytes': b'ignored\xff', 'str': 'ignored ž',
        'dict': {'q': 'ignored'}, 'invalid-truthiness': Poison()}[payload]
streams = []
caller = {'sentinel': object()}
original = dict(caller)
class Page:
    def GET(self):
        stream = web.ctx.env['wsgi.input']
        assert isinstance(stream, BytesIO) and stream.tell() == 0 and not stream.closed
        assert stream.getvalue() == b''
        assert 'CONTENT_LENGTH' not in web.ctx.env and 'CONTENT_TYPE' not in web.ctx.env
        assert web.ctx.method == method and web.ctx.env['HTTP_X_PROBE'] == 'retained'
        assert web.ctx.env['sentinel'] is caller['sentinel']
        assert web.input().q == 'ž'
        assert web.data() == b''
        streams.append(stream)
        # Deliberately contaminate only this owned stream, to expose sharing.
        stream.write(b'owned mutation')
        return b''
app = web.application(('/', Page), {}, autoreload=False)
for _ in range(2):
    response = app.request('/?q=%C5%BE', method=method, data=body, env=caller,
                           headers={'X-Probe': 'retained'})
    assert (response.status, response.data) == ('200 OK', b'')
    assert caller == original and 'wsgi.input' not in caller
    assert dict(web.ctx.items()) == {}
assert streams[0] is not streams[1]
assert all(not stream.closed for stream in streams)
''', tmp_path, record_property)


@pytest.mark.parametrize('method', ['GET', 'HEAD'])
def test_missing_input_preserves_explicit_metadata(method, tmp_path, record_property):
    probe('method = ' + repr(method) + '\n' + r'''
rows = [({}, {}, {}),
        ({'CONTENT_LENGTH': 0}, {}, {'CONTENT_LENGTH': 0}),
        ({'CONTENT_LENGTH': '0', 'CONTENT_TYPE': 'custom/zero'}, {},
         {'CONTENT_LENGTH': '0', 'CONTENT_TYPE': 'custom/zero'}),
        ({'CONTENT_LENGTH': 7}, {}, {'CONTENT_LENGTH': 7}),
        ({'CONTENT_LENGTH': 'wrong'}, {}, {'CONTENT_LENGTH': 'wrong'}),
        ({'CONTENT_LENGTH': None}, {}, {'CONTENT_LENGTH': None}),
        ({'CONTENT_LENGTH': '99', 'CONTENT_TYPE': 'old/type'},
         {'Content-Length': '2', 'Content-Type': 'new/type'},
         {'CONTENT_LENGTH': '2', 'CONTENT_TYPE': 'new/type'}),
        ({'HTTP_CONTENT_LENGTH': '0', 'HTTP_CONTENT_TYPE': 'alias/type'}, {},
         {'CONTENT_LENGTH': '0', 'CONTENT_TYPE': 'alias/type'})]
class Page:
    def GET(self):
        actual = {k: web.ctx.env[k] for k in ['CONTENT_LENGTH', 'CONTENT_TYPE'] if k in web.ctx.env}
        assert actual == expected
        assert 'HTTP_CONTENT_LENGTH' not in web.ctx.env and 'HTTP_CONTENT_TYPE' not in web.ctx.env
        return web.data()
app = web.application(('/', Page), {}, autoreload=False)
for env, headers, expected in rows:
    before, before_headers = dict(env), dict(headers)
    response = app.request('/', method=method, env=env, headers=headers)
    assert (response.status, response.data) == ('200 OK', b'')
    assert env == before and headers == before_headers
    assert dict(web.ctx.items()) == {}
''', tmp_path, record_property)


@pytest.mark.parametrize('method', ['GET', 'HEAD'])
@pytest.mark.parametrize('kind', ['bytesio', 'nonseekable', 'falsy-bool', 'falsy-len'])
def test_explicit_stream_identity_position_cache_and_no_close(method, kind, tmp_path, record_property):
    probe('method, kind = ' + repr((method, kind)) + '\n' + r'''
from io import BytesIO
trace = []
class WatchedBytesIO(BytesIO):
    def read(self, *args):
        trace.append(args)
        return super().read(*args)
class Nonseekable:
    def read(self, *args): return backing.read(*args)
    def seek(self, *args): raise AssertionError('must not rewind')
    def close(self): raise AssertionError('caller retains ownership')
class FalsyBool(Nonseekable):
    def __bool__(self): return False
class FalsyLen(Nonseekable):
    def __len__(self): return 0
backing = WatchedBytesIO(b'xxA\xffBC')
backing.seek(2)
stream = {'bytesio': backing, 'nonseekable': Nonseekable(),
          'falsy-bool': FalsyBool(), 'falsy-len': FalsyLen()}[kind]
if kind.startswith('falsy'): assert not stream
caller = {'wsgi.input': stream, 'CONTENT_LENGTH': '2', 'CONTENT_TYPE': 'custom/type'}
original = dict(caller)
received = []
class Page:
    def GET(self):
        assert web.ctx.env['wsgi.input'] is stream
        assert backing.tell() == 2 + 2 * len(received)
        assert len(trace) == len(received)  # no helper read before handler
        first = web.data()
        assert web.data() is first  # request-local cache, no second read
        received.append(first)
        return first
app = web.application(('/', Page), {}, autoreload=False)
for expected in [b'A\xff', b'BC']:
    response = app.request('/', method=method, data=b'ignored', env=caller)
    assert (response.status, response.data) == ('200 OK', expected)
    assert caller == original and caller['wsgi.input'] is stream
    assert not backing.closed and dict(web.ctx.items()) == {}
assert received == [b'A\xff', b'BC'] and trace == [(2,), (2,)]
assert backing.tell() == 6
''', tmp_path, record_property)


@pytest.mark.parametrize('method', ['GET', 'HEAD'])
def test_explicit_stream_retains_content_length_read_policy(method, tmp_path, record_property):
    probe('method = ' + repr(method) + '\n' + r'''
from io import BytesIO
rows = [({}, 0, b''), ({'CONTENT_LENGTH': 0}, 0, b''),
        ({'CONTENT_LENGTH': '2'}, 2, b'AB'), ({'CONTENT_LENGTH': 2}, 2, b'AB'),
        ({'CONTENT_LENGTH': 'wrong'}, 0, b''),
        ({'CONTENT_LENGTH': '-1'}, -1, b'ABCD'),
        ({'CONTENT_LENGTH': '99'}, 99, b'ABCD'),
        ({'CONTENT_LENGTH': '0', 'HTTP_TRANSFER_ENCODING': 'chunked'}, None, b'ABCD')]
class Stream(BytesIO):
    def read(self, *args):
        trace.append(args)
        return super().read(*args)
class Page:
    def GET(self):
        assert web.ctx.env['wsgi.input'] is stream
        return web.data()
app = web.application(('/', Page), {}, autoreload=False)
for metadata, size, expected in rows:
    stream, trace = Stream(b'ABCD'), []
    env = dict(metadata, **{'wsgi.input': stream})
    response = app.request('/', method=method, env=env)
    assert (response.status, response.data) == ('200 OK', expected)
    assert trace == [() if size is None else (size,)]
    assert stream.tell() == len(expected) and not stream.closed
    assert env == dict(metadata, **{'wsgi.input': stream})
    assert dict(web.ctx.items()) == {}
''', tmp_path, record_property)


@pytest.mark.parametrize('method', ['GET', 'HEAD'])
@pytest.mark.parametrize('kind', ['none', 'runtime-error', 'http-error', 'system-exit'])
def test_explicit_invalid_input_keeps_exception_and_http_policy(method, kind, tmp_path, record_property):
    probe('method, kind = ' + repr((method, kind)) + '\n' + r'''
observed = []
error = RuntimeError('owned read failure') if kind == 'runtime-error' else SystemExit('owned exit')
class Broken:
    def read(self, *args):
        if kind == 'http-error':
            global error
            error = web.badrequest('owned rejection')
        raise error
stream = None if kind == 'none' else Broken()
class Page:
    def GET(self):
        assert web.ctx.env['wsgi.input'] is stream
        try: return web.data()
        except BaseException as caught:
            observed.append(caught)
            raise
app = web.application(('/', Page), {}, autoreload=False)
env = {'wsgi.input': stream}
if kind == 'system-exit':
    caught = raises(SystemExit, lambda: app.request('/', method=method, env=env))
    assert caught is error and observed == [error]
    # Escaped SystemExit is the existing dispatcher boundary; explicit test cleanup.
    app._cleanup()
else:
    response = app.request('/', method=method, env=env)
    expected = ('400 Bad Request', b'owned rejection') if kind == 'http-error' else (
        '500 Internal Server Error', b'internal server error')
    assert (response.status, response.data) == expected
    if kind == 'none': assert len(observed) == 1 and isinstance(observed[0], AttributeError)
    else: assert observed == [error]
    assert dict(web.ctx.items()) == {}  # observed before test-owned teardown
assert env == {'wsgi.input': stream}
''', tmp_path, record_property)


@pytest.mark.parametrize('client', ['request', 'appbrowser'])
@pytest.mark.parametrize('handler', ['fallback', 'explicit'])
def test_head_empty_input_and_existing_response_body_policy(client, handler, tmp_path, record_property):
    probe('client, handler = ' + repr((client, handler)) + '\n' + r'''
from urllib.request import Request
seen = []
class Page:
    def GET(self):
        seen.append(('GET', web.ctx.method))
        assert web.data() == b''
        return b'page'
if handler == 'explicit':
    def head(self):
        seen.append(('HEAD', web.ctx.method))
        assert web.data() == b''
        return b'head page'
    Page.HEAD = head
app = web.application(('/', Page), {}, autoreload=False)
expected = b'head page' if handler == 'explicit' else b'page'
if client == 'request':
    response = app.request('/', method='HEAD')
    assert (response.status, response.data) == ('200 OK', expected)
else:
    browser = app.browser()
    request = Request('http://0.0.0.0:8080/', method='HEAD')
    assert request.get_method() == 'HEAD'
    response = browser.do_request(request)
    assert browser.status == 200 and response.read() == browser.data == expected
assert seen == [('HEAD' if handler == 'explicit' else 'GET', 'HEAD')]
assert dict(web.ctx.items()) == {}
''', tmp_path, record_property)


@pytest.mark.parametrize('method', ['POST', 'PUT'])
def test_non_get_still_replaces_explicit_stream_with_data(method, tmp_path, record_property):
    probe('method = ' + repr(method) + '\n' + r'''
from io import BytesIO
original = BytesIO(b'untouched')
original.seek(2)
class Page:
    def POST(self):
        assert web.ctx.env['wsgi.input'] is not original
        assert web.ctx.env['CONTENT_LENGTH'] == '2'
        assert web.ctx.env['CONTENT_TYPE'] == 'custom/type'
        return web.data()
    PUT = POST
app = web.application(('/', Page), {}, autoreload=False)
env = {'wsgi.input': original, 'CONTENT_LENGTH': '2', 'CONTENT_TYPE': 'custom/type'}
for payload, expected in [(b'\xff\x00tail', b'\xff\x00'), (None, b'')]:
    response = app.request('/', method=method, data=payload, env=env)
    assert (response.status, response.data) == ('200 OK', expected)
    assert original.tell() == 2 and not original.closed and env['wsgi.input'] is original
    assert dict(web.ctx.items()) == {}
''', tmp_path, record_property)


def test_appbrowser_navigation_cookie_redirect_and_post_sequence(tmp_path, record_property):
    probe(r'''
from urllib.request import Request
from web.browser import AppHandler
requests = []
original_open = AppHandler.http_open
def observed(handler, request):
    assert isinstance(request, Request)
    requests.append((request.get_method(), request.selector))
    return original_open(handler, request)
AppHandler.http_open = observed
class Page:
    def GET(self):
        assert 'wsgi.input' in web.ctx.env
        if web.ctx.path == '/start':
            web.setcookie('owned', 'present', path='/')
            return b'page'
        assert web.cookies().owned == 'present'
        if web.ctx.path == '/jump': raise web.seeother('/empty?q=kept')
        if web.ctx.path == '/empty':
            assert web.input().q == 'kept'
            return web.data()  # intended missing-input body contract, not link instrumentation
        return b'done'
    def POST(self):
        assert web.cookies().owned == 'present'
        assert web.data() == b'\xff\x00'
        raise web.seeother('/done')
app = web.application(('/.*', Page), {}, autoreload=False)
browser = app.browser()
assert browser.open('/start').read() == b'page' and browser.status == 200
assert browser.open('/jump').read() == b'' and browser.status == 200
assert browser.path == '/empty?q=kept'
assert browser.open('/post', data=b'\xff\x00').read() == b'done'
assert (browser.status, browser.path) == (200, '/done')
assert [(c.name, c.value) for c in browser.cookiejar] == [('owned', 'present')]
assert requests == [('GET', '/start'), ('GET', '/jump'), ('GET', '/empty?q=kept'),
                    ('POST', '/post'), ('GET', '/done')]
assert dict(web.ctx.items()) == {}
''', tmp_path, record_property)
