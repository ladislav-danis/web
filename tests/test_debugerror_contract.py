"""Execute error-handler Markdown in fresh offline processes, with real WSGI.

Only the mail transport alias is replaced. Source files remain available for
traceback frame/local rendering. No Core, network, SMTP or child launch in probes.
"""
import json
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
import json
from pathlib import Path
import re
import sys
import uuid

class NoMosaic(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {'core', 'modules', 'dotenv'}:
            raise AssertionError('Unexpected application import: ' + fullname)
sys.meta_path.insert(0, NoMosaic())
def offline(event, args):
    if event in {'socket.connect', 'socket.getaddrinfo', 'socket.bind',
                 'subprocess.Popen', 'os.system', 'os.posix_spawn'}:
        raise AssertionError('Forbidden probe side effect: ' + event)
sys.addaudithook(offline)
sys.path.insert(0, sys.argv[1])
import web
import importlib
debug = importlib.import_module('web.debugerror')
assert Path(web.__file__).resolve().parent == Path(sys.argv[1]) / 'web'
web.config.debug = False
mail = []
def sink(*args, **kwargs):
    mail.append((args, kwargs))
debug.sendmail = sink
exception_marker = 'exception-' + uuid.uuid4().hex
local_marker = 'local-' + uuid.uuid4().hex
class Broken:
    def GET(self):
        private_value = local_marker
        raise RuntimeError(exception_marker)

def make_app():
    return web.application(('/broken', Broken), globals(), autoreload=False)

def fence(heading, filename='debugerror.md'):
    path = Path(web.__file__).with_name('docs') / filename
    text = path.read_text(encoding='utf-8')
    # Headings are recognized only outside fences (Python comments are not headings).
    section = None
    blocks = []
    current = None
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
    assert len(blocks) == 1, (heading, len(blocks))
    source = blocks[0]
    # Exact fenced bytes, real file: debugerror reads traceback source from disk.
    target = Path.cwd() / ('example-' + str(len(hashes)) + '.py')
    target.write_text(source, encoding='utf-8')
    hashes.append(hashlib.sha256(source.encode()).hexdigest())
    return compile(source, str(target), 'exec')

hashes = []
def execute(heading, filename='debugerror.md'):
    ns = {'__name__': 'documentation_example', 'app': make_app()}
    exec(fence(heading, filename), ns)
    ns['app'].add_mapping('/broken', Broken)
    return ns

def response_contract(response, status, body=None, content_type='text/html'):
    assert response.status == status, response.status
    assert response.headers['Content-Type'] == content_type, response.headers
    if body is not None:
        assert response.data == body, response.data

def safe_email(app):
    response = app.request('/broken')
    response_contract(response, '500 Internal Server Error', b'internal server error')
    assert exception_marker.encode() not in response.data
    assert local_marker.encode() not in response.data
    assert len(mail) == 1, mail
    args, kwargs = mail[0]
    assert 'RuntimeError' in args[2] and exception_marker in args[2]
    assert '(/broken)' in args[2]
    assert 'GET http://0.0.0.0:8080/broken' in args[3]
    assert exception_marker in args[3] and 'Traceback' in args[3]
    attachment, = kwargs['attachments']
    assert attachment['filename'] == 'bug.html'
    report = web.safestr(attachment['content'])
    assert exception_marker in report and local_marker in report
    return response
'''


def probe(source, tmp_path, record_property):
    script = tmp_path / 'probe.py'
    script.write_text(BOOTSTRAP + '\n' + textwrap.dedent(source) +
                      '\nprint(json.dumps({"fence_sha256": hashes, "mail_count": len(mail)}))\n')
    result = subprocess.run(
        [sys.executable, '-I', str(script), str(WEB_ROOT.parent)],
        cwd=tmp_path, env={'PATH': os.defpath, 'HOME': str(tmp_path),
                          'TMPDIR': str(tmp_path), 'PYTHON_DOTENV_DISABLED': '1'},
        text=True, capture_output=True, timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    record_property('offline_evidence', json.dumps(json.loads(result.stdout), sort_keys=True))


@pytest.mark.parametrize('heading', ['Production Error Notification',
                                     '`emailerrors(to_address, olderror, from_address=None)`'])
def test_production_email_markdown(heading, tmp_path, record_property):
    probe('ns = execute(' + repr(heading) + ')\nsafe_email(ns["app"])', tmp_path, record_property)


def test_runtime_debugerror_is_error_and_djangoerror_is_rendered_content(tmp_path, record_property):
    probe('''
        app = make_app()
        observed = []
        def handler():
            rendered = debug.djangoerror()
            error = debug.debugerror()
            assert isinstance(rendered, web.template.TemplateResult)
            assert not isinstance(rendered, web.HTTPError)
            assert type(error) is web.webapi._InternalError
            assert isinstance(error, web.HTTPError) and not callable(error)
            assert not hasattr(web, '_InternalError')
            assert exception_marker in str(rendered) and local_marker in str(rendered)
            observed.append(error)
            return error
        app.internalerror = handler
        response = app.request('/broken')
        response_contract(response, '500 Internal Server Error')
        assert len(observed) == 1
        assert exception_marker.encode() in response.data
        assert local_marker.encode() in response.data
    ''', tmp_path, record_property)


@pytest.mark.parametrize('mode', ['default', 'explicit', 'email-explicit'])
def test_runtime_debug_false_controls_default_not_explicit_handler(mode, tmp_path, record_property):
    probe('mode = ' + repr(mode) + '\n' + textwrap.dedent('''
        app = make_app()
        if mode == 'explicit':
            app.internalerror = debug.debugerror
        elif mode == 'email-explicit':
            app.internalerror = debug.emailerrors('sink@example.invalid', debug.debugerror)
        response = app.request('/broken')
        response_contract(response, '500 Internal Server Error')
        exposed = mode != 'default'
        assert (exception_marker.encode() in response.data) == exposed
        assert (local_marker.encode() in response.data) == exposed
        assert len(mail) == int(mode == 'email-explicit')
        if not exposed:
            assert response.data == b'internal server error'
    '''), tmp_path, record_property)


@pytest.mark.parametrize('outcome', ['success', 'old-fails', 'mail-fails'])
def test_runtime_email_order_identity_and_failure_propagation(outcome, tmp_path, record_property):
    probe('outcome = ' + repr(outcome) + '\n' + textwrap.dedent('''
        events = []
        app = make_app()
        failure = ValueError('transport-or-handler-failure')
        def handler():
            error = web.HTTPError('500 Internal Server Error', {'Content-Type': 'text/html'}, 'safe')
            def old():
                events.append('old')
                if outcome == 'old-fails':
                    raise failure
                return error
            def transport(*args, **kwargs):
                events.append('send')
                if outcome == 'mail-fails':
                    raise failure
                sink(*args, **kwargs)
            debug.sendmail = transport
            wrapper = debug.emailerrors('to@example.invalid', old, 'from@example.invalid')
            assert callable(wrapper)
            if outcome == 'success':
                assert wrapper() is error
                args, kwargs = mail[0]
                assert args[0] == 'your buggy site <from@example.invalid>'
                assert args[1] == 'the bugfixer <to@example.invalid>'
                assert exception_marker in args[3]
                assert local_marker in web.safestr(kwargs['attachments'][0]['content'])
            else:
                try:
                    wrapper()
                except ValueError as caught:
                    assert caught is failure
                else:
                    raise AssertionError('Failure swallowed')
            return error
        app.internalerror = handler
        response_contract(app.request('/broken'), '500 Internal Server Error', b'safe')
        assert events == (['old'] if outcome == 'old-fails' else ['old', 'send'])
    '''), tmp_path, record_property)


@pytest.mark.parametrize('registration', ['published', 'direct-wrapper'])
def test_logging_markdown_records_real_exception(registration, tmp_path, record_property):
    probe('registration = ' + repr(registration) + '\n' + textwrap.dedent('''
        import logging
        ns = execute('Combining with Custom Logging')
        records = []
        class RecordingHandler(logging.Handler):
            def emit(self, record):
                records.append(record)
        logging.getLogger().addHandler(RecordingHandler())
        app = ns['app']
        if registration == 'direct-wrapper':
            # Isolate the wrapper's missing-import failure from registration.
            old = web.application.internalerror.__get__(app)
            app.internalerror = ns['logged_email_errors']('dev@example.com', old)
        safe_email(app)
        record, = records
        assert record.levelno == logging.ERROR
        assert record.getMessage() == 'Error occurred'
        assert record.exc_info[0] is RuntimeError
        assert str(record.exc_info[1]) == exception_marker
        assert record.exc_info[2] is not None
        rendered = logging.Formatter().format(record)
        assert exception_marker in rendered and 'Traceback' in rendered
        assert exception_marker in Path('app_errors.log').read_text()
    '''), tmp_path, record_property)


@pytest.mark.parametrize('path,status,body,hook', [
    ('/missing', '404 Not Found', b'<h1>404 - Page Not Found</h1>', 'notfound'),
    ('/broken', '500 Internal Server Error', b'<h1>500 - Internal Server Error</h1>', 'internalerror'),
])
def test_webapi_custom_error_markdown(path, status, body, hook, tmp_path, record_property):
    probe('path, status, body, hook = ' + repr((path, status, body, hook)) + '\n' + textwrap.dedent('''
        ns = execute('Custom Error Pages', 'webapi.md')
        app = ns['app']
        assert getattr(app, hook) is ns[hook]
        returned = []
        original = getattr(app, hook)
        def checked():
            value = original()
            returned.append(value)
            return value
        setattr(app, hook, checked)
        response = app.request(path)
        response_contract(response, status, body, 'text/html; charset=utf-8')
        assert len(returned) == 1  # No recursive dispatch through web.* aliases.
        assert isinstance(returned[0], web.HTTPError)
        assert exception_marker.encode() not in response.data
        assert local_marker.encode() not in response.data
        assert mail == []
    '''), tmp_path, record_property)


def test_custom_django_markdown_returns_http_error(tmp_path, record_property):
    probe('''
        ns = execute('Custom Error Handler with Django Error')
        values = []
        def checked():
            error = ns['custom_error_handler']()
            values.append(error)
            return error
        ns['app'].internalerror = checked
        response = ns['app'].request('/broken')
        assert len(values) == 1
        assert isinstance(values[0], web.HTTPError)
        response_contract(response, '500 Internal Server Error',
                          content_type='text/html; charset=utf-8')
        assert exception_marker.encode() in response.data
        assert local_marker.encode() in response.data
    ''', tmp_path, record_property)


@pytest.mark.parametrize('heading', ['`debugerror()`', 'Basic Debug Mode',
                                     'Custom Error Handler with Django Error'])
def test_development_markdown_registers_diagnostic_hook(heading, tmp_path, record_property):
    probe('ns = execute(' + repr(heading) + ')\n' + textwrap.dedent('''
        app = ns['app']
        expected = ns.get('custom_error_handler', ns.get('debugerror'))
        assert app.internalerror is expected
        response = app.request('/broken')
        assert response.status == '500 Internal Server Error'
        assert response.headers['Content-Type'].startswith('text/html')
        assert exception_marker.encode() in response.data
        assert local_marker.encode() in response.data
        assert mail == []
    '''), tmp_path, record_property)
