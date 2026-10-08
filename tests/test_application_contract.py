"""Execute application.md fences in fresh offline framework-only processes.

The shared README probe denies Core/dotenv imports and all network operations;
process isolation keeps web.py's ThreadedDict cleanup out of other fixtures.
Runner stubs below characterize dispatch, not CGI/Google deployment.
"""
import pytest

from .test_readme_contract import probe


DOCUMENT = r'''
import hashlib
import re

document = Path(web.__file__).with_name('docs') / 'application.md'
def fence(heading):
    section = document.read_bytes().split(heading.encode() + b'\n', 1)[1]
    section = re.split(rb'^#{1,5} ', section, maxsplit=1, flags=re.M)[0]
    blocks = re.findall(rb'^```python\n(.*?)^```', section, flags=re.M | re.S)
    assert len(blocks) == 1, (heading, len(blocks))
    return blocks[0]
'''


def test_example_usage_fence_routes_hello_and_missing_paths(tmp_path, record_property):
    probe(DOCUMENT + r'''
source = fence('## Example Usage')
started = []
original_run = web.application.run
# Only intercept the indefinite server entry point; keep all fenced bytes.
web.application.run = lambda app, *args, **kwargs: started.append(app)
namespace = {'__name__': '__main__'}
try:
    exec(compile(source, str(document) + ':Example Usage', 'exec'), namespace)
finally:
    web.application.run = original_run
app = namespace['app']
assert started == [app]
hello = app.request('/hello')
assert (hello.status, hello.data) == ('200 OK', b'Hello, world!')
paths = ('/', '/missing', '/missing/nested', '/hello/extra', '/missing?q=value')
statuses = {path: app.request(path).status for path in paths}
assert set(statuses.values()) == {'404 Not Found'}, statuses
print(json.dumps({'hello': hello.status, 'missing': statuses,
                  'fence_sha256': hashlib.sha256(source).hexdigest(),
                  'server_entry_calls': len(started)}))
''', tmp_path, record_property)


@pytest.mark.parametrize('provided_symbol', [False, True], ids=['standalone', 'real-symbol'])
def test_metaclass_fence_creates_class_with_actual_metaclass(
    tmp_path, record_property, provided_symbol
):
    # The real-symbol variant distinguishes the old base-factory TypeError
    # from its separate missing-import NameError; neither rewrites the fence.
    probe(DOCUMENT + '\nprovided_symbol = ' + repr(provided_symbol) + r'''
from web.application import with_metaclass
source = fence('### `with_metaclass(mcls)`')
namespace = {'__name__': 'documented_metaclass'}
if provided_symbol:
    namespace['with_metaclass'] = with_metaclass
exec(compile(source, str(document) + ':with_metaclass', 'exec'), namespace)
assert namespace['with_metaclass'] is with_metaclass
assert type(namespace['MyClass']) is namespace['MyMeta']
assert namespace['MyClass'].__module__ == 'documented_metaclass'
assert type(namespace['MyClass']()) is namespace['MyClass']
print(json.dumps({'metaclass': type(namespace['MyClass']).__name__,
                  'provided_symbol': provided_symbol,
                  'fence_sha256': hashlib.sha256(source).hexdigest()}))
''', tmp_path, record_property)


RUNNER_BOUNDARIES = r'''
import builtins
import io
from types import SimpleNamespace
import wsgiref.handlers
from wsgiref.util import setup_testing_defaults

class Hello:
    def GET(self):
        return 'runner boundary'
app = web.application(('/hello', Hello), {}, autoreload=False)
events = []
wrapped = []
runner_calls = []
sentinel = object()

def middleware(name):
    def wrap(inner):
        events.append('wrap:' + name)
        def dispatch(environ, start_response):
            events.append('request:' + name)
            return inner(environ, start_response)
        wrapped.append(dispatch)
        return dispatch
    return wrap
middleware1 = middleware('one')
middleware2 = middleware('two')

# Replace only the two external runner boundaries. Import interception makes
# legacy Google availability deterministic; no Google SDK is installed/used.
def google_runner(wsgi_app):
    runner_calls.append(('google', wsgi_app))
    return sentinel

def cgi_runner(self, wsgi_app):
    assert isinstance(self, wsgiref.handlers.CGIHandler)
    runner_calls.append(('cgi', wsgi_app))
    return sentinel
wsgiref.handlers.CGIHandler.run = cgi_runner
real_import = builtins.__import__
def runner_import(name, globals=None, locals=None, fromlist=(), level=0):
    if name == 'google.appengine.ext.webapp.util':
        if not google_available:
            raise ImportError('No legacy Google runner in this offline probe')
        return SimpleNamespace(run_wsgi_app=google_runner)
    return real_import(name, globals, locals, fromlist, level)
builtins.__import__ = runner_import

def exercise(wsgi_app):
    env = {}
    setup_testing_defaults(env)
    env.update(PATH_INFO='/hello', REQUEST_METHOD='GET',
               **{'wsgi.input': io.BytesIO(b'')})
    responses = []
    result = wsgi_app(env, lambda status, headers: responses.append((status, headers)))
    try:
        assert b''.join(result) == b'runner boundary'
    finally:
        if hasattr(result, 'close'):
            result.close()
    assert len(responses) == 1 and responses[0][0] == '200 OK'
    assert events == ['wrap:one', 'wrap:two', 'request:two', 'request:one'], events
'''


@pytest.mark.parametrize('google_available', [False, True], ids=['cgi-fallback', 'legacy-google'])
def test_cgirun_executes_selected_runner_and_forwards_middleware(
    tmp_path, record_property, google_available
):
    probe('google_available = ' + repr(google_available) + '\n' + RUNNER_BOUNDARIES + r'''
assert runner_calls == []
result = app.cgirun(middleware1, middleware2)
expected = 'google' if google_available else 'cgi'
assert result is sentinel and not callable(result)
assert runner_calls == [(expected, wrapped[-1])]
assert events == ['wrap:one', 'wrap:two']
exercise(runner_calls[0][1])
assert runner_calls == [(expected, wrapped[-1])]
print(json.dumps({'runner': expected, 'calls': len(runner_calls),
                  'returned_runner_result': True, 'middleware': events,
                  'scope': 'offline runner-boundary characterization'}))
''', tmp_path, record_property)


def test_gaerun_rejects_actual_python3_without_running_external_handler(tmp_path, record_property):
    probe('google_available = True\n' + RUNNER_BOUNDARIES + r'''
assert sys.version_info.major == 3
try:
    app.gaerun(middleware1, middleware2)
except OSError as error:
    message = str(error)
    assert message == 'Google App Engine only supports python 2.5 and 2.7'
else:
    raise AssertionError('gaerun did not reject the real Python 3 runtime')
assert runner_calls == []
# gaerun constructs the middleware-wrapped callable before rejecting Python 3.
assert events == ['wrap:one', 'wrap:two']
print(json.dumps({'exception': 'OSError', 'message': message,
                  'python': list(sys.version_info[:3]), 'runner_calls': 0,
                  'middleware': events}))
''', tmp_path, record_property)


def test_wsgifunc_fence_returns_real_callable_without_running_external_handler(tmp_path, record_property):
    probe(DOCUMENT + '\ngoogle_available = True\n' + RUNNER_BOUNDARIES + r'''
source = fence('##### `wsgifunc(*middleware)`')
namespace = {'app': app, 'middleware1': middleware1, 'middleware2': middleware2}
exec(compile(source, str(document) + ':wsgifunc', 'exec'), namespace)
wsgi_app = namespace['wsgi_app']
assert callable(wsgi_app) and wsgi_app is wrapped[-1]
assert runner_calls == []
assert events == ['wrap:one', 'wrap:two']
exercise(wsgi_app)
assert runner_calls == []
print(json.dumps({'callable': True, 'runner_calls': 0, 'middleware': events,
                  'fence_sha256': hashlib.sha256(source).hexdigest()}))
''', tmp_path, record_property)
