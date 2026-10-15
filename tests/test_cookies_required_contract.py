"""Required-cookie HTTP contracts in fresh, guard-first -I -B children."""
import hashlib
import json
import os
import subprocess
import sys
import textwrap

import pytest

from .test_template_security_contract import BOOTSTRAP, WEB_ROOT


def probe(source, tmp_path, record_property):
    env = {'PATH': os.defpath, 'PYTHON_DOTENV_DISABLED': '1', 'LC_ALL': 'C'}
    for key in ('HOME', 'TMPDIR', 'XDG_CACHE_HOME', 'XDG_DATA_HOME', 'XDG_CONFIG_HOME'):
        env[key] = str(tmp_path)
    program = BOOTSTRAP + '\n' + textwrap.dedent(source) + '''
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
    assert result.returncode == 0, result.stdout + result.stderr
    outcome = json.loads(result.stdout.splitlines()[-1])
    assert outcome == {'completed': True, 'isolated': 1, 'no_bytecode': True}


@pytest.mark.parametrize('mode', ['ordinary', 'generator'])
def test_missing_cookie_is_default_http400(mode, tmp_path, record_property):
    probe('mode = ' + repr(mode) + '\n' + r'''
accepted = []
class Index:
    def GET(self):
        def read():
            web.cookies('session_id', 'user_id')
            accepted.append('accepted')
            return 'accepted'
        if mode == 'generator':
            def body():
                yield read()
            return body()
        return read()
app = web.application(('/', Index), {}, autoreload=False)
try:
    response = app.request('/')
except Exception as error:
    print(json.dumps({'exception': type(error).__name__,
                      'cause': type(error.__cause__).__name__, 'accepted': accepted}))
    raise
print(json.dumps({'status': response.status, 'body': response.data.decode(),
                  'accepted': accepted}))
assert response.status == '400 Bad Request', response.status
assert response.data == b'bad request'
assert accepted == []
assert dict(web.ctx.items()) == {}
''', tmp_path, record_property)


@pytest.mark.parametrize('mode', ['ordinary', 'generator'])
@pytest.mark.parametrize('cookie', ['', 'session_id=example', 'user_id=7'],
                         ids=['both-missing', 'second-missing', 'first-missing'])
@pytest.mark.parametrize('conflicting_defaults', [False, True])
def test_rejection_precedes_start_response(mode, cookie, conflicting_defaults,
                                           tmp_path, record_property):
    probe('mode, cookie, conflicting = ' + repr((mode, cookie, conflicting_defaults)) + '\n' + r'''
from wsgiref.util import setup_testing_defaults
trace, errors = [], []
class Index:
    def GET(self):
        trace.append('handler')
        assert '_parsed_cookies' not in web.ctx
        def read():
            trace.append('cookies')
            defaults = {'session_id': 'fallback', 'user_id': 'fallback'} if conflicting else {}
            try:
                values = web.cookies('session_id', 'user_id', **defaults)
            except web.HTTPError as error:
                errors.append((type(error), error.args, error.data, web.ctx.status))
                trace.append('cookie-error')
                raise  # Observe the real exception without changing dispatch.
            trace.append('accepted')
            return json.dumps(dict(values))
        if mode == 'generator':
            def body():
                trace.append('generator')
                yield read()
            return body()
        return read()
app = web.application(('/', Index), {}, autoreload=False)
# No custom processors or HTTP hooks for the default request helper.
response = app.request('/', headers={'Cookie': cookie})
assert (response.status, response.data) == ('400 Bad Request', b'bad request')
assert errors == [(web.BadRequest, ('400 Bad Request',), 'bad request', '400 Bad Request')]
assert 'accepted' not in trace and dict(web.ctx.items()) == {}
trace.clear(); errors.clear()
def observe(handler):
    trace.append('processor-enter')
    try:
        result = handler()
    except web.HTTPError:
        trace.append('processor-error')
        raise
    trace.append('processor-return')
    return result
app.add_processor(observe)
env = {}
setup_testing_defaults(env)
env.update(PATH_INFO='/', HTTP_COOKIE=cookie, REQUEST_METHOD='GET')
statuses, chunks = [], []
def start_response(status, headers):
    trace.append('start_response')
    statuses.append(status)
    assert headers == [('Content-Type', 'text/html')]
    assert 'accepted' not in trace
    assert errors == [(web.BadRequest, ('400 Bad Request',), 'bad request', '400 Bad Request')]
    return lambda data: chunks.append(data)
result = app.wsgifunc()(env, start_response)
for chunk in result:
    trace.append('chunk')
    chunks.append(chunk)
expected = (['processor-enter', 'handler', 'cookies', 'cookie-error', 'processor-error']
            if mode == 'ordinary' else
            ['processor-enter', 'handler', 'processor-return', 'generator', 'cookies', 'cookie-error'])
assert trace == expected + ['start_response', 'chunk', 'chunk'], trace
assert statuses == ['400 Bad Request'] and chunks == [b'bad request', b'']
assert dict(web.ctx.items()) == {}
print(json.dumps({'trace': trace, 'statuses': statuses,
                  'body': b''.join(chunks).decode(), 'accepted_chunks': 0}))
# A subsequent successful request must not reuse rejected cookies or status.
trace.clear(); errors.clear()
response = app.request('/', headers={'Cookie': 'session_id=fresh; user_id=8'})
assert response.status == '200 OK'
assert json.loads(response.data) == {'session_id': 'fresh', 'user_id': '8'}
assert trace.count('accepted') == 1 and errors == []
assert dict(web.ctx.items()) == {}
''', tmp_path, record_property)


def test_present_values_defaults_unicode_forgiving_parse_and_cache(tmp_path, record_property):
    probe(r'''
parse = web.webapi.parse_cookies
parsed_headers = []
def observe_parse(header):
    parsed_headers.append(header)
    return parse(header)
web.webapi.parse_cookies = observe_parse
class Index:
    def GET(self):
        assert '_parsed_cookies' not in web.ctx
        values = web.cookies('session_id', 'user_id', session_id='fallback',
                             optional=7, required=['not-a-validation-switch'])
        assert '_unicode' not in values
        assert 'optional' not in web.ctx._parsed_cookies
        web.ctx.env['HTTP_COOKIE'] = 'session_id=must-not-be-reparsed; user_id=wrong'
        repeated = web.cookies('session_id', 'user_id', _unicode=False,
                               optional=7, required=['not-a-validation-switch'])
        assert values == repeated
        return json.dumps(dict(values))
app = web.application(('/', Index), {}, autoreload=False)
for header, expected in [
    ('session_id=; user_id=', {'session_id': '', 'user_id': ''}),
    ('session_id=Z%C3%A9Z; user_id=7; malformed', {'session_id': 'ZéZ', 'user_id': '7'}),
    ('session_id=first; session_id=last; user_id=7', {'session_id': 'last', 'user_id': '7'}),
    (r'broken="\012"; session_id=Z%C3%A9Z; user_id=7', {'session_id': 'ZéZ', 'user_id': '7'}),
    ('session_id="first"; session_id="last"; user_id=7', {'session_id': 'last', 'user_id': '7'}),
]:
    before = len(parsed_headers)
    response = app.request('/', headers={'Cookie': header})
    assert response.status == '200 OK', (header, response.status, response.data)
    assert json.loads(response.data) == dict(expected, optional=7, required=['not-a-validation-switch'])
    assert parsed_headers[before:] == [header]
    assert dict(web.ctx.items()) == {}
print(json.dumps({'parsed_headers': parsed_headers, 'one_parse_per_request': True}))
''', tmp_path, record_property)


@pytest.mark.parametrize('mode', ['ordinary', 'generator'])
def test_explicit_application_catch_can_override_rejection(mode, tmp_path, record_property):
    probe('mode = ' + repr(mode) + '\n' + r'''
seen = []
class Index:
    def GET(self):
        def read():
            try:
                web.cookies('missing')
            except web.BadRequest as error:
                seen.append((error.args, error.data))
                web.ctx.status = '202 Accepted'
                return 'application recovery'
            raise AssertionError('missing cookie was accepted')
        if mode == 'generator':
            def body():
                yield read()
            return body()
        return read()
app = web.application(('/', Index), {}, autoreload=False)
response = app.request('/')
assert (response.status, response.data) == ('202 Accepted', b'application recovery')
assert seen == [(('400 Bad Request',), 'bad request')]
assert dict(web.ctx.items()) == {}
''', tmp_path, record_property)


def test_missing_cookie_after_first_chunk_does_not_rewrite_started_status(tmp_path, record_property):
    probe(r'''
from wsgiref.util import setup_testing_defaults
class Index:
    def GET(self):
        yield b'first chunk'
        web.cookies('missing')
        yield b'must not be accepted'
app = web.application(('/', Index), {}, autoreload=False)
env = {}
setup_testing_defaults(env)
env.update(PATH_INFO='/', REQUEST_METHOD='GET')
statuses = []
result = app.wsgifunc()(env, lambda status, headers: statuses.append(status))
try:
    assert statuses == ['200 OK']
    assert next(result) == b'first chunk'
    error = raises(web.BadRequest, lambda: next(result))
    assert error.args == ('400 Bad Request',) and error.data == 'bad request'
    assert statuses == ['200 OK']  # No second start_response or status rewrite.
finally:
    # Late iteration failure is outside this repair; explicit fixture cleanup
    # does not claim that WSGI's normal final cleanup ran after that exception.
    app._cleanup()
assert dict(web.ctx.items()) == {}
''', tmp_path, record_property)
