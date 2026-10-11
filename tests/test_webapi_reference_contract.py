"""Exact WebAPI reference bytes in fresh offline -I -B processes.

No Core, dotenv, network, subprocess or DB access in probes; these Python guards
are isolation, not an OS sandbox. Header-boundary probes never use a server.
"""
import hashlib
import json
import os
import subprocess
import sys
import textwrap

import pytest

from .test_template_security_contract import BOOTSTRAP, WEB_ROOT, fences

DOC = WEB_ROOT / 'docs/webapi.md'


def probe(source, tmp_path, record_property):
    program = BOOTSTRAP + '\n' + textwrap.dedent(source) + '''
assert not {'core', 'modules', 'dotenv'}.intersection(sys.modules)
print(json.dumps({'completed': True, 'isolated': sys.flags.isolated,
                  'no_bytecode': sys.dont_write_bytecode, 'web_path': web.__file__}))
'''
    env = {'PATH': os.defpath, 'HOME': str(tmp_path), 'TMPDIR': str(tmp_path),
           'LC_ALL': 'C', 'PYTHON_DOTENV_DISABLED': '1'}
    result = subprocess.run([sys.executable, '-I', '-B', '-c', program, str(WEB_ROOT.parent)],
                            cwd=tmp_path, env=env, text=True, capture_output=True, timeout=30)
    record_property('program_sha256', hashlib.sha256(program.encode()).hexdigest())
    record_property('probe_stdout', result.stdout)
    record_property('probe_stderr', result.stderr)
    record_property('probe_exit', result.returncode)
    assert result.returncode == 0, result.stdout + result.stderr
    outcome = json.loads(result.stdout.splitlines()[-1])
    assert outcome['completed'] and outcome['isolated'] == 1 and outcome['no_bytecode']


def documented(heading, record_property):
    selected = [b for b in fences(DOC.read_bytes()) if b[0] == heading]
    assert len(selected) == 1, heading
    _, line, language, code, closed = selected[0]
    assert language == 'python' and closed
    record_property('fence_sha256', hashlib.sha256(code).hexdigest())
    record_property('markdown_line', line)
    return ("namespace = {'__name__': '__main__'}\nexec(compile(" + repr(code)
            + ", 'docs/webapi.md', 'exec'), namespace)\n")


def test_actual_module_and_package_exports(tmp_path, record_property):
    probe(r'''
from web.webapi import rawinput, parse_cookies
module_star, package_star = {}, {}
exec('from web.webapi import *', module_star)
exec('from web import *', package_star)
assert '__all__' not in vars(web)
assert {n for n in module_star if n != '__builtins__'} == set(web.webapi.__all__)
for name, function in [('rawinput', rawinput), ('parse_cookies', parse_cookies)]:
    assert name not in web.webapi.__all__
    assert name not in module_star and name not in package_star
    assert not hasattr(web, name)
    assert getattr(web.webapi, name) is function
for name in web.webapi.__all__:
    assert module_star[name] is getattr(web.webapi, name)
    assert package_star[name] is getattr(web, name) is module_star[name]
''', tmp_path, record_property)


@pytest.mark.parametrize('method', ['GET', 'POST'])
def test_rawinput_documented_real_parsing(method, tmp_path, record_property):
    source = documented('### `rawinput(method=None)`', record_property)
    probe(source + 'method = ' + repr(method) + '\n' + r'''
app = namespace['app']
if method == 'GET':
    response = app.request('/?same=query&repeat=one&repeat=two&blank=&name=Z%C3%A9Z')
    query = {'same': ['query'], 'repeat': ['one', 'two'], 'blank': [''], 'name': ['ZéZ']}
    expected = {'both': query, 'get': query, 'post': {}}
else:
    response = app.request('/?same=query&query=Q', method='POST',
                           data='same=body&repeat=one&repeat=two&blank=&name=Z%C3%A9Z',
                           headers={'Content-Type': 'application/x-www-form-urlencoded'})
    post = {'same': ['body'], 'repeat': ['one', 'two'], 'blank': [''], 'name': ['ZéZ']}
    expected = {'both': dict(post, query=['Q']), 'get': {'same': ['query'], 'query': ['Q']}, 'post': post}
assert response.status == '200 OK'
assert json.loads(response.data) == expected
''', tmp_path, record_property)


def test_probe_guards_deny_core_env_network_process_and_db(tmp_path, record_property):
    probe(r'''
import importlib
import socket
import sqlite3
import subprocess
for name in ('core', 'modules', 'dotenv'):
    raises(AssertionError, lambda: importlib.import_module(name))
raises(AssertionError, lambda: open('.env'))
raises(AssertionError, lambda: sqlite3.connect(':memory:'))
raises(AssertionError, lambda: socket.getaddrinfo('example.invalid', 443))
raises(AssertionError, lambda: subprocess.run([sys.executable, '-V']))
assert len(blocked) == 7
''', tmp_path, record_property)


def test_parse_cookies_documented_unicode_and_raw_escapes(tmp_path, record_property):
    source = documented('### `parse_cookies(http_cookie)`', record_property)
    probe(source + r'''
parse = namespace['parse_cookies']
assert parse('a=Z%C3%A9Z') == {'a': 'ZéZ'}
# The verified interpreter rejects decoded cookie control characters.
from http.cookies import SimpleCookie, CookieError
raw_newline = r'keebler="E=mc2; L=\"Loves\"; fudge=\012;"'
assert SimpleCookie().value_decode(r'"\012"')[0] == '\n'
raises(CookieError, lambda: SimpleCookie(raw_newline))
assert parse(raw_newline) == {}
assert parse(r'keebler="E=mc2; L=\"Loves\"; fudge=\n;"') == {
    'keebler': 'E=mc2; L="Loves"; fudge=n;'}
assert parse('') == {} and parse('a=; b=two%20words') == {'a': '', 'b': 'two words'}
''', tmp_path, record_property)


def test_cookie_unicode_default_and_presence_are_already_correct(tmp_path, record_property):
    probe(r'''
seen = []
class Index:
    def GET(self):
        plain = web.cookies(number=7, missing=None)
        explicit = web.cookies(_unicode=False, number=7, missing=None)
        converted = web.cookies(_unicode=True, number=7, missing=None)
        seen.append((dict(plain), dict(explicit), dict(converted)))
        return web.cookies('a').a
app = web.application(('/', Index), {}, autoreload=False)
for cookie, value in [('a=Z%C3%A9Z', 'ZéZ'), ('a=', '')]:
    response = app.request('/', headers={'Cookie': cookie})
    assert response.status == '200 OK' and response.data == value.encode()
    expected = {'a': value, 'number': 7, 'missing': None}
    assert seen[-1][0] == seen[-1][1] == seen[-1][2] == expected
# Missing-required exception / ordinary500 / generatorRuntimeError and explicit
# membership+raise workaround are retained in test_webapi_validation_contract.
''', tmp_path, record_property)


def test_cookie_expiry_prose_uses_seconds():
    section = DOC.read_text().split('### `setcookie(', 1)[1].split('### `parse_cookies(', 1)[0]
    assert 'days until expiration' not in section
    assert 'seconds' in section


def test_setcookie_documented_real_headers_and_expiry(tmp_path, record_property):
    heading = '### `setcookie(name, value, expires="", domain=None, secure=False, httponly=False, path=None, samesite=None)`'
    source = documented(heading, record_property)
    probe(source + r'''
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from http.cookies import SimpleCookie
app = namespace['app']
before = datetime.now(timezone.utc).replace(microsecond=0)
response = app.request('/')
after = datetime.now(timezone.utc).replace(microsecond=0)
assert response.status == '200 OK' and response.data == b'Cookies set'
headers = [v for k,v in response.headers.items() if k.lower() == 'set-cookie']
# app.request's header mapping coalesces duplicate names; use header_items.
headers = [v for k,v in response.header_items if k.lower() == 'set-cookie']
assert len(headers) == 5
cookies = [SimpleCookie(h) for h in headers]
plain, timed, secure, same, deleted = [next(iter(c.values())) for c in cookies]
assert plain.key == 'session_id' and plain.value == 'abc123'
assert plain['path'] == '/' and not plain['domain'] and not plain['expires']
assert not plain['secure'] and not plain['httponly'] and not plain['samesite']
expiry = parsedate_to_datetime(timed['expires'])
assert before + timedelta(seconds=3600) <= expiry <= after + timedelta(seconds=3600)
assert timed.value == 'dark_mode'
assert secure.value == 'example-token' and secure['secure'] and secure['httponly']
assert same['samesite'].lower() == 'strict'
assert deleted.key == 'session_id' and deleted.value == ''
expiry = parsedate_to_datetime(deleted['expires'])
assert before - timedelta(seconds=1000000000) <= expiry <= after - timedelta(seconds=1000000000)
''', tmp_path, record_property)


def test_status_reference_distinguishes_factories_from_classes():
    prose = DOC.read_text()
    assert 'All status code classes are generated dynamically' not in prose
    assert 'factory functions' in prose and 'except web.HTTPError' in prose


def test_status_aliases_and_active_application_factories(tmp_path, record_property):
    probe(r'''
import inspect
for upper in ('OK', 'Created', 'Accepted', 'NoContent', 'Redirect', 'Found',
              'SeeOther', 'NotModified', 'TempRedirect', 'BadRequest', 'Unauthorized',
              'Forbidden', 'NoMethod', 'NotAcceptable', 'Conflict', 'Gone',
              'PreconditionFailed', 'UnsupportedMediaType'):
    cls = getattr(web, upper)
    assert inspect.isclass(cls) and issubclass(cls, web.HTTPError)
    assert cls is getattr(web, upper.lower()) is getattr(web.webapi, upper)
for upper in ('NotFound', 'InternalError', 'UnavailableForLegalReasons'):
    factory = getattr(web, upper)
    assert inspect.isfunction(factory) and not inspect.isclass(factory)
    assert factory is getattr(web, upper.lower()) is getattr(web.webapi, upper)
calls = []
class Index:
    def GET(self, kind, explicit):
        factory = getattr(web, kind)
        error = factory('Explicit payload') if explicit else factory()
        assert isinstance(error, web.HTTPError)
        raise error
app = web.application(('/(NotFound|InternalError|UnavailableForLegalReasons)(/explicit)?', Index), {}, autoreload=False)
for upper, attr, status in [('NotFound','notfound','404 Not Found'),
                          ('InternalError','internalerror','500 Internal Server Error'),
                          ('UnavailableForLegalReasons','unavailableforlegalreasons','451 Unavailable For Legal Reasons')]:
    def hook(status=status):
        calls.append(status)
        return web.HTTPError(status, {'X-Factory': 'called'}, 'Hook payload')
    setattr(app, attr, hook)
    response = app.request('/' + upper)
    assert response.status == status and response.data == b'Hook payload'
    assert response.headers['X-Factory'] == 'called' and calls[-1] == status
    count = len(calls)
    response = app.request('/' + upper + '/explicit')
    assert response.status == status and response.data == b'Explicit payload'
    assert len(calls) == count
assert len(calls) == 3
''', tmp_path, record_property)


def test_success_status_documented_raise_payload(tmp_path, record_property):
    source = documented('#### Success Status Codes (2xx)', record_property)
    probe(source + r'''
app = namespace['app']
response = app.request('/')
assert response.status == '201 Created' and response.data == b'Created payload'
assert response.headers['X-Result'] == 'created'
response = app.request('/ok')
assert response.status == '200 OK' and response.data == b''
''', tmp_path, record_property)


def test_basic_error_documented_construct_return_raise_and_ctx(tmp_path, record_property):
    source = documented('### Basic Error Handling', record_property)
    probe(source + r'''
app = namespace['app']
expected = {'/raised': ('201 Created', b'Payload'),
            '/returned': ('201 Created', b'201 Created'),
            '/constructed': ('201 Created', b'Continued'),
            '/payload': ('201 Created', b'Payload'),
            '/missing': ('404 Not Found', b'Page not found')}
for path, (status, body) in expected.items():
    response = app.request(path)
    assert (response.status, response.data) == (status, body), (path, response)
assert namespace['observations'][-1] == (('201 Created',), 'Payload', '201 Created')
''', tmp_path, record_property)


@pytest.mark.parametrize('mount', ['', '/mounted'])
def test_ctx_documented_real_mounted_wsgi_and_body(mount, tmp_path, record_property):
    source = documented('#### Response Information', record_property)
    probe(source + 'mount = ' + repr(mount) + '\n' + r'''
assert isinstance(web.ctx, web.utils.ThreadedDict)
status, headers, body = namespace['request'](mount)
assert status == '202 Accepted'
assert ('X-Custom-Header', 'value') in headers
assert json.loads(body) == {'home': 'https://example.test:8443' + mount,
                           'homepath': mount, 'realhome': 'https://example.test:8443' + mount,
                           'path': '/resource', 'query': '?x=1', 'method': 'GET',
                           'initial_output': ''}
assert b'legacy-not-the-body' not in body
assert dict(web.ctx.items()) == {}
# Reuse the exact documented app under a real sub-application mount.
child = namespace['app']
outer = web.application(('/child', child), {}, autoreload=False)
env = namespace['environment'](mount)
env['PATH_INFO'] = '/child/resource'
seen = []
body = b''.join(outer.wsgifunc()(env, lambda status, headers: seen.append((status, list(headers)))))
values = json.loads(body)
assert values['home'] == 'https://example.test:8443' + mount + '/child'
assert values['homepath'] == mount + '/child'
assert values['realhome'] == 'https://example.test:8443' + mount
assert values['path'] == '/resource' and seen[0][0] == '202 Accepted'
assert dict(web.ctx.items()) == {}
''', tmp_path, record_property)


def test_ctx_prose_distinguishes_url_path_and_legacy_output():
    section = DOC.read_text().split('### `ctx`', 1)[1].split('## Configuration', 1)[0]
    assert 'ThreadedDict' in section
    assert '| `home` | str | Base path for application |' not in section
    assert '| `output` | str | Response body content |' not in section
    assert 'legacy' in section.lower() and 'handler' in section


def test_header_security_prose_scopes_validation():
    prose = DOC.read_text()
    assert 'All header values are validated' not in prose
    assert 'direct' in prose and 'revalidate' in prose


def test_header_documented_helper_and_unique_semantics(tmp_path, record_property):
    source = documented('### `header(hdr, value, unique=False)`', record_property)
    probe(source + r'''
response = namespace['app'].request('/')
assert response.status == '200 OK' and response.data == b'{"ok": true}'
assert response.headers['Content-Type'] == 'application/json'
assert [(k,v) for k,v in response.header_items if k.lower() == 'x-request-id'] == [('X-Request-ID','example-id')]
''', tmp_path, record_property)


def test_header_crlf_helper_rejection_vs_inert_wsgi_capture(tmp_path, record_property):
    probe(r'''
import io
from wsgiref.util import setup_testing_defaults
checks = []
class Index:
    def GET(self):
        for name, value in [('X-Probe\r', 'safe'), ('X-Probe\n', 'safe'),
                            ('X-Probe', 'a\rb'), ('X-Probe', 'a\nb')]:
            before = list(web.ctx.headers)
            error = raises(ValueError, lambda: web.header(name, value))
            assert str(error) == 'invalid characters in header'
            assert web.ctx.headers == before
            checks.append((name, value))
        web.header('X-Safe', 'first')
        web.header('x-safe', 'ignored', unique=True)
        web.header('X-Safe', 'second')
        # Only inert in-process capture sees this value; no socket/server involved.
        web.ctx.headers.append(('X-Inert', 'a\r\nb'))
        return 'Inert body'
app = web.application(('/', Index), {}, autoreload=False)
env = {}
setup_testing_defaults(env)
env.update(PATH_INFO='/', REQUEST_METHOD='GET', HTTP_HOST='example.test')
env['wsgi.input'] = io.BytesIO(b'')
captured = []
body = b''.join(app.wsgifunc()(env, lambda status, headers: captured.append((status,list(headers)))))
assert len(checks) == 4
assert captured == [('200 OK', [('X-Safe','first'), ('X-Safe','second'), ('X-Inert','a\r\nb')])]
assert body == b'Inert body'
assert dict(web.ctx.items()) == {}
''', tmp_path, record_property)


def test_setcookie_mount_domain_flags_are_header_policy_only(tmp_path, record_property):
    probe(r'''
from http.cookies import SimpleCookie
class Cookie:
    def GET(self):
        web.setcookie('default', 'Zé Z')
        web.setcookie('explicit', 'value', path='/fixed', domain='example.test',
                      secure=True, httponly=True, samesite='LaX')
        web.setcookie('invalid', 'value', samesite='unsupported')
        return 'ok'
child = web.application(('/', Cookie), {}, autoreload=False)
app = web.application(('/mount', child), {}, autoreload=False)
response = app.request('/mount/')
assert response.status == '200 OK'
headers = [v for k,v in response.header_items if k.lower() == 'set-cookie']
assert len(headers) == 3
plain, explicit, invalid = [next(iter(SimpleCookie(h).values())) for h in headers]
assert plain.value == 'Z%C3%A9%20Z' and plain['path'] == '/mount/'
assert not plain['domain'] and not plain['secure'] and not plain['httponly']
assert explicit['path'] == '/fixed' and explicit['domain'] == 'example.test'
assert explicit['secure'] and explicit['httponly'] and explicit['samesite'] == 'LaX'
assert not invalid['samesite']
''', tmp_path, record_property)


def test_cookie_default_does_not_enable_unicode_conversion(tmp_path, record_property):
    probe(r'''
# Observe and delegate the real converter; do not replace the parser/storify.
original = web.utils.safeunicode
calls = []
def observe(value):
    calls.append(value)
    return original(value)
web.utils.safeunicode = observe
class Index:
    def GET(self):
        calls.clear()
        plain = web.cookies()
        assert calls == []
        explicit = web.cookies(_unicode=False)
        assert calls == []
        converted = web.cookies(_unicode=True)
        assert calls == ['ZéZ']
        assert dict(plain) == dict(explicit) == dict(converted) == {'a': 'ZéZ'}
        return 'ok'
app = web.application(('/', Index), {}, autoreload=False)
response = app.request('/', headers={'Cookie': 'a=Z%C3%A9Z'})
assert response.status == '200 OK' and response.data == b'ok'
web.utils.safeunicode = original
''', tmp_path, record_property)
