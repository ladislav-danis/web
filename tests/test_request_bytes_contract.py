"""web#21 desired body contracts through real WSGI and urllib requests.

The two binary cases replace A006's request-bytes/appbrowser-bytes limitations
one-to-one. str rejection remains in test_browser_contract under its old IDs.
Fresh guarded interpreters avoid clearing unrelated Core ThreadedDict state.
"""
import json
import os
import subprocess
import sys
import textwrap

import pytest

from .test_readme_contract import BOOTSTRAP, WEB_ROOT


def request_probe(source, tmp_path, record_property):
    result = subprocess.run(
        [sys.executable, '-I', '-B', '-c', BOOTSTRAP + '\n' + textwrap.dedent(source),
         str(WEB_ROOT.parent)], cwd=tmp_path,
        env={'PATH': os.defpath, 'PYTHON_DOTENV_DISABLED': '1',
             'TMPDIR': str(tmp_path), 'HOME': str(tmp_path)},
        text=True, capture_output=True, timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    evidence = json.loads(result.stdout)
    record_property('standalone_result', json.dumps(evidence, sort_keys=True))
    return evidence


RAW_APP = r'''
calls = []
class Echo:
    def POST(self):
        body = web.data()
        calls.append((body, str(web.ctx.env['CONTENT_LENGTH']),
                      web.ctx.env.get('CONTENT_TYPE')))
        return body
app = web.application(('/echo', Echo), {}, autoreload=False)
'''


@pytest.mark.parametrize('client', ['request', 'appbrowser'],
                         ids=['request-bytes', 'appbrowser-bytes'])
def test_binary_bytes_reach_handler_unchanged(tmp_path, record_property, client):
    request_probe(RAW_APP + '\nclient = ' + repr(client) + r'''
body = b'\xff\x00\x80A\r\n'
headers = {'Content-Type': 'application/octet-stream'}
if client == 'request':
    response = app.request('/echo', method='POST', data=body, headers=headers)
    assert response.status == '200 OK'
    actual = response.data
else:
    from urllib.request import Request
    from web.browser import AppHandler
    b = app.browser()
    # Observe the real Request at the bridge, while delegating unchanged.
    original = AppHandler.http_open
    requests = []
    def observed(handler, request):
        assert isinstance(request, Request)
        requests.append((request.get_method(), request.data))
        return original(handler, request)
    AppHandler.http_open = observed
    response = b.open('/echo', data=body, headers=headers)
    assert (b.status, b.path) == (200, '/echo')
    assert requests == [('POST', b'\xff\x00\x80A\r\n')]
    actual = response.read()
    assert b.data == actual
assert actual == b'\xff\x00\x80A\r\n'
assert calls == [(b'\xff\x00\x80A\r\n', '6', 'application/octet-stream')]
print(json.dumps({'client': client, 'handler_calls': len(calls),
                  'body_hex': actual.hex(), 'content_length': calls[0][1]}))
''', tmp_path, record_property)


def test_unicode_str_uses_utf8_byte_length(tmp_path, record_property):
    request_probe(RAW_APP + r'''
response = app.request('/echo', method='POST', data='ž😀\x00',
                       headers={'Content-Type': 'text/plain; charset=utf-8'})
assert response.status == '200 OK'
assert response.data == b'\xc5\xbe\xf0\x9f\x98\x80\x00', (response.data, calls)
assert calls == [(b'\xc5\xbe\xf0\x9f\x98\x80\x00', '7', 'text/plain; charset=utf-8')]
print(json.dumps({'body_hex': response.data.hex(), 'content_length': calls[0][1]}))
''', tmp_path, record_property)


@pytest.mark.parametrize('client', ['request', 'appbrowser'])
def test_utf8_bytes_are_not_decoded_or_double_encoded(tmp_path, record_property, client):
    request_probe(RAW_APP + '\nclient = ' + repr(client) + r'''
body = b'\xc5\xbe\xf0\x9f\x98\x80\x00'
headers = {'Content-Type': 'text/plain; charset=utf-8'}
if client == 'request':
    response = app.request('/echo', method='POST', data=body, headers=headers)
    actual = response.data
    assert response.status == '200 OK'
else:
    b = app.browser()
    actual = b.open('/echo', data=body, headers=headers).read()
    assert b.status == 200
assert actual == b'\xc5\xbe\xf0\x9f\x98\x80\x00'
assert calls == [(b'\xc5\xbe\xf0\x9f\x98\x80\x00', '7', 'text/plain; charset=utf-8')]
print(json.dumps({'client': client, 'body_hex': actual.hex(), 'content_length': '7'}))
''', tmp_path, record_property)


@pytest.mark.parametrize('body', ['message=%C5%BE+%26', b'message=%C5%BE+%26',
                                  {'message': 'ž &'}], ids=['str', 'bytes', 'dict'])
def test_direct_form_types_preserve_urlencoding(tmp_path, record_property, body):
    request_probe('\nbody = ' + repr(body) + r'''
calls = []
class Form:
    def POST(self):
        calls.append((web.data(), str(web.ctx.env['CONTENT_LENGTH']), dict(web.input())))
        return web.input().message
app = web.application(('/', Form), {}, autoreload=False)
r = app.request('/', method='POST', data=body,
                headers={'Content-Type': 'application/x-www-form-urlencoded'})
assert (r.status, r.data) == ('200 OK', b'\xc5\xbe &')
assert calls == [(b'message=%C5%BE+%26', '18', {'message': 'ž &'})]
print(json.dumps({'parsed': calls[0][2], 'body_hex': calls[0][0].hex(), 'content_length': '18'}))
''', tmp_path, record_property)


def test_real_urllib_request_repeated_form_keys(tmp_path, record_property):
    request_probe(r'''
from urllib.request import Request
from urllib.parse import urlencode
calls = []
class Form:
    def POST(self):
        calls.append((web.data(), str(web.ctx.env['CONTENT_LENGTH']), dict(web.input(tag=[]))))
        return '|'.join(web.input(tag=[]).tag)
app = web.application(('/form', Form), {}, autoreload=False)
body = urlencode([('tag', 'ž'), ('tag', '😀')]).encode('ascii')
assert body == b'tag=%C5%BE&tag=%F0%9F%98%80'
req = Request('http://0.0.0.0:8080/form', data=body,
              headers={'Content-Type': 'application/x-www-form-urlencoded'})
b = app.browser()
r = b.do_request(req)
assert b.status == 200 and r.read() == b'\xc5\xbe|\xf0\x9f\x98\x80'
assert calls == [(b'tag=%C5%BE&tag=%F0%9F%98%80', '27', {'tag': ['ž', '😀']})]
print(json.dumps({'parsed': calls[0][2], 'body_hex': calls[0][0].hex(), 'content_length': '27'}))
''', tmp_path, record_property)


def test_dictionary_lists_keep_non_doseq_semantics(tmp_path, record_property):
    request_probe(RAW_APP + r'''
r = app.request('/echo', method='POST', data={'tag': ['a', 'b']})
assert (r.status, r.data) == ('200 OK', b'tag=%5B%27a%27%2C+%27b%27%5D')
assert calls == [(b'tag=%5B%27a%27%2C+%27b%27%5D', '28', None)]
print(json.dumps({'body_hex': r.data.hex(), 'content_length': '28', 'doseq': False}))
''', tmp_path, record_property)


@pytest.mark.parametrize('origin', ['headers', 'env'])
def test_explicit_content_length_and_type_are_not_overwritten(tmp_path, record_property, origin):
    request_probe('\norigin = ' + repr(origin) + r'''
calls = []
class Echo:
    def POST(self):
        body = web.data()
        calls.append((body, web.ctx.env['wsgi.input'].read(),
                      web.ctx.env['CONTENT_LENGTH'], web.ctx.env['CONTENT_TYPE'],
                      web.ctx.env['HTTP_X_PROBE']))
        return body
app = web.application(('/', Echo), {}, autoreload=False)
kw = {'headers': {'X-Probe': 'retained'}}
if origin == 'headers':
    kw['headers'].update({'Content-Length': '2', 'Content-Type': 'custom/type'})
    kw['env'] = {'CONTENT_LENGTH': '99', 'CONTENT_TYPE': 'overridden/type'}
else:
    kw['env'] = {'CONTENT_LENGTH': '2', 'CONTENT_TYPE': 'custom/type'}
r = app.request('/', method='POST', data=b'\xff\x00tail', **kw)
assert (r.status, r.data) == ('200 OK', b'\xff\x00')
assert calls == [(b'\xff\x00', b'tail', '2', 'custom/type', 'retained')]
print(json.dumps({'origin': origin, 'explicit_length': calls[0][2], 'type': calls[0][3],
                  'read_hex': r.data.hex(), 'unread_hex': calls[0][1].hex()}))
''', tmp_path, record_property)


@pytest.mark.parametrize('body', [None, '', b'', {}], ids=['none', 'str', 'bytes', 'dict'])
def test_empty_direct_post_body(tmp_path, record_property, body):
    request_probe(RAW_APP + '\nbody = ' + repr(body) + r'''
r = app.request('/echo', method='POST', data=body)
assert (r.status, r.data) == ('200 OK', b'')
assert calls == [(b'', '0', None)]
print(json.dumps({'content_length': '0', 'handler_calls': len(calls)}))
''', tmp_path, record_property)


def test_empty_appbrowser_bytes_is_post_not_get(tmp_path, record_property):
    request_probe(RAW_APP + r'''
b = app.browser()
r = b.open('/echo', data=b'')
assert b.status == 200 and r.read() == b''
assert calls == [(b'', '0', 'application/x-www-form-urlencoded')]
print(json.dumps({'content_length': '0', 'handler_calls': len(calls)}))
''', tmp_path, record_property)


@pytest.mark.parametrize('method', ['GET', 'HEAD'])
def test_get_head_ignore_data_and_preserve_explicit_input(tmp_path, record_property, method):
    request_probe('\nmethod = ' + repr(method) + r'''
from io import BytesIO
calls = []
class Page:
    def GET(self):
        calls.append((web.ctx.method, web.ctx.env['wsgi.input'].read(),
                      web.ctx.env['CONTENT_LENGTH'], web.ctx.env['CONTENT_TYPE']))
        return 'page'
app = web.application(('/', Page), {}, autoreload=False)
r = app.request('/', method=method, data=b'ignored\xff',
                env={'wsgi.input': BytesIO(b'original'), 'CONTENT_LENGTH': '8',
                     'CONTENT_TYPE': 'original/type'})
assert r.status == '200 OK'
# Direct application.request retains the GET body even for HEAD; unchanged.
assert r.data == b'page'
assert calls == [(method, b'original', '8', 'original/type')]
print(json.dumps({'method': method, 'preserved_input': True, 'body_hex': r.data.hex()}))
''', tmp_path, record_property)


@pytest.mark.parametrize('method', ['PUT', 'PATCH', 'DELETE'])
def test_other_body_methods_accept_bytes(tmp_path, record_property, method):
    request_probe(RAW_APP + '\nmethod = ' + repr(method) + r'''
setattr(Echo, method, Echo.POST)
r = app.request('/echo', method=method, data=b'\xff\x00')
assert (r.status, r.data) == ('200 OK', b'\xff\x00')
assert calls == [(b'\xff\x00', '2', None)]
print(json.dumps({'method': method, 'body_hex': r.data.hex(), 'content_length': '2'}))
''', tmp_path, record_property)


@pytest.mark.parametrize('client', ['request', 'appbrowser'])
def test_post_cookie_headers_and_redirect(tmp_path, record_property, client):
    request_probe('\nclient = ' + repr(client) + r'''
calls = []
class Page:
    def GET(self):
        if web.ctx.path == '/cookie':
            web.setcookie('probe', 'present', path='/')
        return web.cookies().get('probe', 'absent')
    def POST(self):
        calls.append((web.data(), web.cookies().probe, web.ctx.env['HTTP_X_PROBE']))
        web.header('X-Result', 'retained')
        raise web.seeother('/done')
app = web.application(('/.*', Page), {}, autoreload=False)
if client == 'request':
    r = app.request('/post', method='POST', data=b'\xff\x00',
                    headers={'Cookie': 'probe=present', 'X-Probe': 'sent'})
    assert r.status == '303 See Other' and r.data == b''
    assert r.headers['Location'] == 'http://0.0.0.0:8080/done'
    assert r.headers['X-Result'] == 'retained'
else:
    b = app.browser()
    b.open('/cookie')
    assert [(c.name, c.value) for c in b.cookiejar] == [('probe', 'present')]
    r = b.open('/post', data=b'\xff\x00', headers={'X-Probe': 'sent'})
    assert (b.status, b.path, b.data) == (200, '/done', b'present')
    assert r.read() == b'present'
    assert [(c.name, c.value) for c in b.cookiejar] == [('probe', 'present')]
assert calls == [(b'\xff\x00', 'present', 'sent')]
print(json.dumps({'client': client, 'handler_calls': len(calls), 'cookie': calls[0][1]}))
''', tmp_path, record_property)


def test_markdown_raw_request_bodies(tmp_path, record_property):
    from .test_browser_contract import DOCUMENT

    request_probe(DOCUMENT + r'''
namespace = {'__name__': '__example__'}
execute_fence('application.md', '##### Raw request bodies', namespace)
assert namespace['binary'].data == b'\xff\x00A'
assert namespace['text'].data == b'\xc5\xbe\xf0\x9f\x98\x80'
assert namespace['received'] == [(b'\xff\x00A', '3'), (b'\xc5\xbe\xf0\x9f\x98\x80', '6')]
print(json.dumps({'fences': hashes, 'namespace': ['__name__'], 'handler_calls': 2}))
''', tmp_path, record_property)


def test_legacy_parser_availability_is_explicit(tmp_path, record_property):
    request_probe(r'''
import importlib
availability = {}
for name in ('BeautifulSoup', 'ClientForm'):
    try:
        module = importlib.import_module(name)
    except ModuleNotFoundError as error:
        availability[name] = {'available': False, 'exception': str(error)}
    else:
        availability[name] = {'available': True, 'file': module.__file__,
                              'integration': 'NOT_CERTIFIED'}
print(json.dumps({'optional_dependencies': availability, 'installed_by_test': False,
                  'parser_fallback': False, 'legacy_integration': 'NOT_CERTIFIED'}))
''', tmp_path, record_property)
