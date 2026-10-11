"""A-009: actual response bytes, owned files and intercepted desktop boundary.

Standalone children deny Core/dotenv/network; only file-error boundaries are
injected. These tests never launch a native browser or certify URL safety.
"""
import json
import os
import subprocess
import sys

import pytest

from .test_readme_contract import BOOTSTRAP, WEB_ROOT


def show_probe(source, tmp_path, record_property):
    result = subprocess.run(
        [sys.executable, '-I', '-B', '-c', BOOTSTRAP + '\n' + source,
         str(WEB_ROOT.parent)], cwd=tmp_path,
        env={'PATH': os.defpath, 'PYTHON_DOTENV_DISABLED': '1',
             'TMPDIR': str(tmp_path), 'HOME': str(tmp_path)},
        text=True, capture_output=True, timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    evidence = json.loads(result.stdout)
    record_property('standalone_result', json.dumps(evidence, sort_keys=True))
    return evidence


SETUP = r'''
import builtins
import os
import webbrowser
from web.browser import AppBrowser, Browser
owned = Path(os.environ['TMPDIR']).resolve()
assert Path.cwd().resolve() == owned
page = owned / 'page.html'
assert page.resolve().is_relative_to(owned)
# Audit both builtins.open and pathlib/io writes before the OS open boundary.
def owned_writes(event, args):
    if event == 'open':
        name, mode, flags = args
        if (mode and any(c in mode for c in 'wax+')) or flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC):
            assert isinstance(name, (str, bytes, os.PathLike)), name
            assert Path(name).resolve().is_relative_to(owned), name
sys.addaudithook(owned_writes)
payload = 'žluťoučký 😀'.encode('utf-8') + b'\x00\xff\xfe'
gets = []
class Page:
    def GET(self):
        gets.append([web.ctx.method, web.ctx.path])
        return payload
app = web.application(('/.*', Page), {}, autoreload=False)
b = app.browser()
assert type(b) is AppBrowser and AppBrowser.show is Browser.show
response = b.open('/preview?value=1')
assert b.status == 200 and b.path == '/preview?value=1'
assert response.read() == b.data == payload
assert gets == [['GET', '/preview']]
attributes = ('data', 'status', 'path', 'url', '_response', 'form', '_forms')
before = {name: getattr(b, name) for name in attributes}
def unchanged():
    assert all(getattr(b, name) is value for name, value in before.items())
    assert b.get_response().read() == payload
    assert gets == [['GET', '/preview']]
handles, writes, launches = [], [], []
real_open = builtins.open
def owned_open(file, mode='r', *args, **kwargs):
    assert Path(file).resolve() == page
    assert page.is_relative_to(owned)
    handle = real_open(file, mode, *args, **kwargs)
    handles.append(handle)
    writes.append([str(page), mode])
    return handle
def launch(url, *args, **kwargs):
    assert not args and not kwargs
    assert handles and all(handle.closed for handle in handles)
    assert page.read_bytes() == payload
    assert url == 'file://' + os.path.abspath('page.html')
    launches.append(url)
    return True
# Intercept before any show call, including an unexpectedly early launch.
webbrowser.open = launch
'''


FAILURE = r'''
page.write_bytes(b'owned sentinel')
error = OSError('injected ' + stage + ' failure')
events = []
class FileBoundary:
    def __init__(self, raw):
        self.raw = raw
    @property
    def closed(self):
        return self.raw.closed
    def write(self, data):
        assert data is b.data
        events.append('write')
        if stage == 'write':
            # A real partial write demonstrates that this is not atomic saving.
            self.raw.write(data[:1])
            raise error
        return self.raw.write(data)
    def close(self):
        events.append('close')
        self.raw.close()
        if stage == 'close':
            raise error
    def __enter__(self):
        return self
    def __exit__(self, *exc):
        self.close()
def failing_open(file, mode='r', *args, **kwargs):
    assert Path(file).resolve() == page and page.is_relative_to(owned)
    events.append('open')
    if stage == 'open':
        raise error
    raw = owned_open(file, mode, *args, **kwargs)
    return FileBoundary(raw)
def forbidden_launch(*args, **kwargs):
    launches.append(args)
    raise AssertionError('Launch before successful write AND close')
webbrowser.open = forbidden_launch
builtins.open = failing_open
try:
    try:
        b.show()
    except OSError as caught:
        assert caught is error
    else:
        raise AssertionError('Expected injected failure')
    assert launches == []
    assert all(handle.closed for handle in handles), 'show leaked file after write failure'
    assert events == (['open'] if stage == 'open' else ['open', 'write', 'close'])
    assert page.read_bytes() == (b'owned sentinel' if stage == 'open' else
                                payload[:1] if stage == 'write' else payload)
    unchanged()
finally:
    builtins.open = real_open
    # Close raw handles only after the closure oracle, including baseline RED.
    for handle in handles:
        handle.close()
print(json.dumps({'stage': stage, 'events': events, 'error_identity': True,
                  'closed': True, 'browser_launches_intercepted': len(launches),
                  'saved_hex': page.read_bytes().hex(), 'caller_state_preserved': True}))
'''


@pytest.mark.parametrize('stage', ['open', 'close'])
def test_file_failure_propagates_without_launch(tmp_path, record_property, stage):
    show_probe(SETUP + '\nstage = ' + repr(stage) + '\n' + FAILURE,
               tmp_path, record_property)


@pytest.mark.parametrize('body', [b'', b'ASCII', 'ž 😀'.encode('utf-8'),
                                  b'\xff\xfe\x80', b'a\x00b'],
                         ids=['empty', 'ascii', 'utf8', 'non-utf8', 'nul'])
def test_exact_response_bytes(tmp_path, record_property, body):
    setup = SETUP.replace("payload = 'žluťoučký 😀'.encode('utf-8') + b'\\x00\\xff\\xfe'",
                          'payload = ' + repr(body))
    assert setup != SETUP
    show_probe(setup + EXACT_SAVE, tmp_path, record_property)


def test_repeated_calls_overwrite_each_current_response(tmp_path, record_property):
    show_probe(SETUP + r'''
for index, body in enumerate([payload, b'x', b'']):
    payload = body
    b.open('/preview?value=1')
    assert b.data == payload and b.status == 200
    before = {name: getattr(b, name) for name in attributes}
    builtins.open = owned_open
    try:
        assert b.show() is None
    finally:
        builtins.open = real_open
    assert page.read_bytes() == payload
    assert len(launches) == len(handles) == index + 1
    assert all(handle.closed for handle in handles)
    assert all(getattr(b, name) is value for name, value in before.items())
assert writes == [[str(page), 'wb']] * 3
assert gets == [['GET', '/preview']] * 4
print(json.dumps({'calls': 3, 'saved_hex': page.read_bytes().hex(),
                  'closed_before_each_launch': True, 'overwritten_without_tail': True}))
''', tmp_path, record_property)


@pytest.mark.parametrize('outcome', ['false', 'exception'])
def test_desktop_boundary_after_close_preserves_response(tmp_path, record_property, outcome):
    show_probe(SETUP + '\noutcome = ' + repr(outcome) + r'''
error = RuntimeError('desktop boundary failure')
def desktop(url):
    launch(url)  # Exact saved bytes and closed handles checked before boundary.
    if outcome == 'exception':
        raise error
    return False
webbrowser.open = desktop
builtins.open = owned_open
try:
    if outcome == 'exception':
        try:
            b.show()
        except RuntimeError as caught:
            assert caught is error
        else:
            raise AssertionError('Desktop exception swallowed')
    else:
        assert b.show() is None  # Retain the existing return policy.
finally:
    builtins.open = real_open
assert len(launches) == 1 and len(handles) == 1 and handles[0].closed
assert page.read_bytes() == payload
unchanged()
print(json.dumps({'outcome': outcome, 'intercepted_launches': len(launches),
                  'saved_before_launch': True, 'caller_state_preserved': True}))
''', tmp_path, record_property)


def test_write_failure_closes_file_without_launch(tmp_path, record_property):
    show_probe(SETUP + "\nstage = 'write'\n" + FAILURE, tmp_path, record_property)


def test_exact_manual_preview_fence_in_owned_directory(tmp_path, record_property):
    from .test_browser_contract import DOCUMENT

    show_probe(SETUP + DOCUMENT + r'''
def forbidden_launch(*args, **kwargs):
    launches.append(args)
    raise AssertionError('Manual preview must not launch a browser')
webbrowser.open = forbidden_launch
namespace = {'b': b}  # Exactly the initial namespace declared in Markdown.
execute_fence('browser.md', '### Saving a Response Without Launching a Browser', namespace)
assert namespace['saved_bytes'] == payload == b.data
assert namespace['preview'].resolve().is_relative_to(owned)
assert namespace['preview_uri'] == namespace['preview'].as_uri()
assert not namespace['preview'].exists() and not namespace['preview'].parent.exists()
assert not page.exists() and launches == []
unchanged()
print(json.dumps({'fences': hashes, 'initial_namespace': ['b'],
                  'saved_hex': namespace['saved_bytes'].hex(), 'owned_cleanup': True,
                  'intercepted_launches': 0}))
''', tmp_path, record_property)


EXACT_SAVE = r'''
page.write_bytes(b'owned sentinel with a tail much longer than the response' * 4)
builtins.open = owned_open
try:
    assert b.show() is None
finally:
    builtins.open = real_open
    # Cleanup does not conceal the success oracle: launch checked closure first.
    for handle in handles:
        handle.close()
assert writes == [[str(page), 'wb']]
assert len(handles) == 1 and handles[0].closed
assert page.read_bytes() == payload
assert launches == ['file://' + os.path.abspath('page.html')]
unchanged()
print(json.dumps({'repair': 'A-009', 'saved_hex': page.read_bytes().hex(),
                  'closed_before_launch': True, 'browser_launches_intercepted': len(launches),
                  'writes': writes, 'caller_state_preserved': True}))
'''
