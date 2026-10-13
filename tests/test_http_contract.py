"""HTTP helpers and exact reference examples in fresh offline interpreters."""
import os
from pathlib import Path
import subprocess
import sys
import textwrap

import pytest

WEB_ROOT = Path(__file__).resolve().parents[1]
BOOTSTRAP = r'''
import importlib.abc
import hashlib
import io
import json
from pathlib import Path
import sys
from wsgiref.util import setup_testing_defaults
from wsgiref.validate import validator

class NoApplication(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {'core', 'modules', 'dotenv'}:
            raise AssertionError('Unexpected application import: ' + fullname)
sys.meta_path.insert(0, NoApplication())
def offline(event, args):
    if event in {'socket.connect', 'socket.getaddrinfo', 'socket.bind',
                 'subprocess.Popen', 'os.system', 'os.posix_spawn'}:
        raise AssertionError('Forbidden probe side effect: ' + event)
sys.addaudithook(offline)
sys.path.insert(0, sys.argv[1])
import web
assert Path(web.__file__).resolve().parent == Path(sys.argv[1]) / 'web'
web.config.debug = False
hashes = []

def execute(heading):
    text = Path(web.__file__).with_name('docs').joinpath('http.md').read_text()
    section, current, blocks = None, None, []
    for line in text.splitlines(keepends=True):
        if current is not None:
            if line.startswith('```'):
                if section == heading:
                    blocks.append(''.join(current))
                current = None
            else:
                current.append(line)
        elif line.startswith('```python'):
            current = []
        elif line.startswith('#'):
            section = line.lstrip('#').strip()
    if current is not None and section == heading:
        blocks.append(''.join(current))  # preserve historical unclosed fence
    assert len(blocks) == 1, (heading, len(blocks))
    source = blocks[0]
    hashes.append(hashlib.sha256(source.encode()).hexdigest())
    ns = {'__name__': 'documentation_example'}
    exec(compile(source, '<http.md: ' + heading + '>', 'exec'), ns)
    return ns

def request_wsgi(app, method='GET'):
    env = {}
    setup_testing_defaults(env)
    env.update(PATH_INFO='/', QUERY_STRING='', REQUEST_METHOD=method,
               HTTP_HOST='example.test', **{'wsgi.input': io.BytesIO()})
    captured = []
    def start_response(status, headers, exc_info=None):
        captured.append((status, headers))
    body = validator(app)(env, start_response)
    try:
        chunks = list(body)
    finally:
        body.close()
    assert len(captured) == 1
    return captured[0], chunks
'''


def probe(source, tmp_path, record_property):
    script = tmp_path / 'probe.py'
    script.write_text(BOOTSTRAP + '\n' + textwrap.dedent(source) +
                      '\nprint(json.dumps({"fence_sha256": hashes}))\n')
    result = subprocess.run(
        [sys.executable, '-I', str(script), str(WEB_ROOT.parent)],
        cwd=tmp_path, env={'PATH': os.defpath, 'HOME': str(tmp_path),
                          'TMPDIR': str(tmp_path), 'PYTHON_DOTENV_DISABLED': '1'},
        text=True, capture_output=True, timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    record_property('offline_evidence', result.stdout.strip())
    record_property('probe_stderr', result.stderr)


@pytest.mark.parametrize('style', ['middleware', 'wrapped'])
def test_profiler_html_is_valid_wsgi_bytes(style, tmp_path, record_property):
    probe('''
        class Page:
            def GET(self):
                web.header('Content-Type', 'text/html; charset=utf-8')
                web.ctx.profile_cleanup_marker = 'owned request'
                return '<h1>Příliš</h1>'
        app = web.application(('/', Page), locals(), autoreload=False)
        wsgi = (app.wsgifunc(web.profiler) if STYLE == 'middleware'
                else web.profiler(app.wsgifunc()))
        (status, headers), chunks = request_wsgi(wsgi)
        assert status == '200 OK'
        assert headers == [('Content-Type', 'text/html; charset=utf-8')]
        assert all(type(chunk) is bytes for chunk in chunks)
        body = b''.join(chunks)
        assert body.startswith('<h1>Příliš</h1>'.encode())
        assert b'<pre>' in body and body.endswith(b'</pre>')
        assert b'function calls' in body and b'GET' in body
        assert 'profile_cleanup_marker' not in web.ctx
    '''.replace('STYLE', repr(style)), tmp_path, record_property)


def test_prefixurl_request_depth(tmp_path, record_property):
    probe('''
        expected = {'': './', '/': './', '/foo': './', '/foo/': '../',
                    '/foo/bar': '../', '/foo/bar/': '../../',
                    '/foo/bar/baz': '../../'}
        class Page:
            def GET(self):
                value = web.prefixurl()
                assert value == expected[web.ctx.path]
                assert web.prefixurl('static/') == 'static/' + ('' if value == './' else value)
                return value
        app = web.application(('.*', Page), locals(), autoreload=False)
        for path, value in expected.items():
            response = app.request(path)
            assert response.status == '200 OK'
            assert response.data == value.encode()
    ''', tmp_path, record_property)


def test_modified_request_validators(tmp_path, record_property):
    probe('''
        import datetime as dt
        date = dt.datetime(2023, 1, 1, 0, 0, 0, 500000)
        generated = []
        class Page:
            def GET(self):
                assert web.modified(date=date, etag='v1') is True
                generated.append(True)
                return 'generated'
        app = web.application(('/', Page), locals(), autoreload=False)
        cases = [({}, False), ({'If-None-Match': '"other"'}, False),
                 ({'If-None-Match': '"v1"'}, True),
                 ({'If-None-Match': '"other", "v1"'}, True),
                 ({'If-None-Match': '*'}, True),
                 ({'If-None-Match': 'W/"v1"'}, False),
                 ({'If-Modified-Since': 'Sun, 01 Jan 2023 00:00:00 GMT'}, True),
                 ({'If-Modified-Since': 'Sun, 01 Jan 2023 00:00:00 GMT; length=10'}, True),
                 ({'If-Modified-Since': 'Sat, 31 Dec 2022 23:59:59 GMT'}, False),
                 ({'If-Modified-Since': 'invalid'}, False),
                 ({'If-Modified-Since': 'Sun, 01 Jan 2023 00:00:01 GMT'}, True),
                 ({'If-None-Match': '"other"', 'If-Modified-Since': 'Sun, 01 Jan 2023 00:00:00 GMT'}, True),
                 ({'If-None-Match': '"v1"', 'If-Modified-Since': 'Sat, 31 Dec 2022 23:59:59 GMT'}, True)]
        for headers, unchanged in cases:
            before = len(generated)
            response = app.request('/', headers=headers)
            assert response.status == ('304 Not Modified' if unchanged else '200 OK'), (headers, response)
            assert response.data == (b'' if unchanged else b'generated')
            assert len(generated) == before + (not unchanged)
            assert response.headers['ETag'] == '"v1"'
            assert response.headers['Last-Modified'] == 'Sun, 01 Jan 2023 00:00:00 GMT'
        # The grace is <= one second, not just truncation of subsecond dates.
        date = dt.datetime(2023, 1, 1, 0, 0, 1)
        assert app.request('/', headers={'If-Modified-Since': 'Sun, 01 Jan 2023 00:00:00 GMT'}).status == '304 Not Modified'
        date += dt.timedelta(microseconds=1)
        assert app.request('/', headers={'If-Modified-Since': 'Sun, 01 Jan 2023 00:00:00 GMT'}).status == '200 OK'
        class Unvalidated:
            def GET(self):
                assert web.modified() is True
                return 'body'
        response = web.application(('/', Unvalidated), locals(), autoreload=False).request('/', headers={'If-None-Match': '*'})
        assert response.status == '200 OK' and response.data == b'body'
        assert 'ETag' not in response.headers and 'Last-Modified' not in response.headers
    ''', tmp_path, record_property)


def test_expires_integer_timedelta_and_float_boundary(tmp_path, record_property):
    probe('''
        import datetime as dt
        from email.utils import parsedate_to_datetime
        for delta, seconds in [(0, 0), (3600, 3600), (-1, -1),
                               (dt.timedelta(seconds=1.5), 1.5)]:
            class Page:
                def GET(self):
                    assert web.expires(delta) is None
                    return 'ok'
            app = web.application(('/', Page), locals(), autoreload=False)
            before = dt.datetime.now(dt.timezone.utc) + dt.timedelta(seconds=seconds)
            response = app.request('/')
            after = dt.datetime.now(dt.timezone.utc) + dt.timedelta(seconds=seconds)
            assert response.status == '200 OK' and response.data == b'ok'
            value = parsedate_to_datetime(response.headers['Expires'])
            assert before.replace(microsecond=0) <= value <= after.replace(microsecond=0)
            assert value.utcoffset() == dt.timedelta(0) and value.microsecond == 0
        class FloatPage:
            def GET(self):
                try:
                    web.expires(1.5)
                except TypeError:
                    assert web.ctx.headers == []
                    return 'float unsupported'
                raise AssertionError('float unexpectedly accepted')
        response = web.application(('/', FloatPage), locals(), autoreload=False).request('/')
        assert response.status == '200 OK' and response.data == b'float unsupported'
    ''', tmp_path, record_property)


def test_url_real_root_mount_host_and_query(tmp_path, record_property):
    probe('''
        from urllib.parse import parse_qs, urlsplit
        class Page:
            def GET(self):
                mount = web.ctx.env['SCRIPT_NAME']
                assert web.ctx.homepath == mount
                assert web.ctx.homedomain == 'https://example.test:8443'
                assert web.url('/api/users', limit=10) == mount + '/api/users?limit=10'
                assert web.url() == mount + '/current'  # Does not copy current query.
                assert web.url('relative', q='a b') == 'relative?q=a+b'
                assert web.url('') == ''
                assert web.url(doseq=True, tags=['python', 'web']) == mount + '/current?tags=python&tags=web'
                assert parse_qs(urlsplit(web.url('/x', tags=['python', 'web'])).query) == {'tags': ["['python', 'web']"]}
                return web.ctx.homedomain + web.url('/api/users', limit=10)
        app = web.application(('/current', Page), locals(), autoreload=False)
        for mount in ('', '/mount'):
            response = app.request('/current?old=1', host='example.test:8443', https=True, env={'SCRIPT_NAME': mount})
            assert response.status == '200 OK'
            assert response.data == ('https://example.test:8443' + mount + '/api/users?limit=10').encode()
    ''', tmp_path, record_property)


def test_profiler_materializes_after_profile_and_closes_original(tmp_path, record_property):
    probe('''
        events = []
        class Body:
            def __iter__(self):
                return self
            def __next__(self):
                events.append('iteration')
                if events.count('iteration') == 1:
                    return b'<p>body</p>'
                raise StopIteration
            def close(self):
                events.append('close')
        body = Body()
        def tiny_wsgi(env, start_response):
            events.append('call')
            start_response('200 OK', [('Content-Type', 'text/html')])
            return body
        (status, headers), chunks = request_wsgi(web.profiler(tiny_wsgi))
        assert status == '200 OK'
        assert chunks[0] == b'<p>body</p>'
        assert events == ['call', 'iteration', 'iteration', 'close']
        # Actual cProfile output excludes work deferred to body iteration.
        assert b'tiny_wsgi' in chunks[-1] and b'__next__' not in chunks[-1]
        # Materialization closes the original once, before the list is consumed.
        assert events.count('close') == 1
    ''', tmp_path, record_property)


def test_profiler_preserves_length_and_no_body_limitations(tmp_path, record_property):
    probe('''
        for method, status in [('GET', '200 OK'), ('HEAD', '200 OK'),
                               ('GET', '204 No Content'), ('GET', '304 Not Modified')]:
            headers = [('Content-Length', '0')]
            if status == '200 OK':
                headers.append(('Content-Type', 'text/html'))
            def empty_wsgi(env, start_response):
                start_response(status, headers)
                return []
            env = {}
            setup_testing_defaults(env)
            env.update(REQUEST_METHOD=method, QUERY_STRING='')
            captured = []
            chunks = web.profiler(empty_wsgi)(env, lambda s, h: captured.append((s, h)))
            assert captured == [(status, headers)]  # No header adjustment.
            assert len(chunks) == 1 and chunks[0].startswith(b'<pre>')
            assert len(b''.join(chunks)) > int(dict(headers)['Content-Length'])
            # This is evidence of unsupported HTTP cases, not valid WSGI claims.
    ''', tmp_path, record_property)


def test_profiler_escapes_real_profile_report(tmp_path, record_property):
    probe('''
        namespace = {}
        source = "def tiny_wsgi(env, start_response):\\n    start_response('200 OK', [('Content-Type', 'text/html')])\\n    return [b'<p>ok</p>']\\n"
        exec(compile(source, '<danger&tag>.py', 'exec'), namespace)
        (_, _), chunks = request_wsgi(web.profiler(namespace['tiny_wsgi']))
        report = chunks[-1]
        assert b'&lt;danger&amp;tag&gt;.py' in report
        assert b'<danger&tag>.py' not in report
    ''', tmp_path, record_property)


@pytest.mark.parametrize('heading', ['`prefixurl(base="")`',
                                     '`modified(date=None, etag=None)`',
                                     'Handling Conditional Requests',
                                     '`expires(delta)`', '`lastmodified(date_obj)`',
                                     'Setting Cache Headers',
                                     '`url(path=None, doseq=False, **kw)`',
                                     'URL Manipulation',
                                     '`changequery(query=None, **kw)`',
                                     '`urlencode(query, doseq=False)`', 'URL Encoding',
                                     '`profiler(app)`'])
def test_markdown_example(heading, tmp_path, record_property):
    probe('''
        ns = execute(HEADING)
        if 'GET' in ns:  # Historical standalone method: run its actual bytes.
            page = type('Page', (), {'GET': ns['GET']})
            app = web.application(('/', page), {}, autoreload=False)
            response = app.request('/')
            assert response.status == '200 OK', response
    '''.replace('HEADING', repr(heading)), tmp_path, record_property)


def test_profiler_imports_package_local_profile(tmp_path, record_property):
    probe('''
        assert 'utils' not in sys.modules
        app = web.application((), {}, autoreload=False)
        assert not callable(app)
        assert callable(app.wsgifunc(web.profiler))
        assert 'utils' not in sys.modules
    ''', tmp_path, record_property)
