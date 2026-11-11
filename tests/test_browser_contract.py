"""Retained browser boundaries and web#3 limitations.

web#21 replaces the two A006 bytes cases in test_request_bytes_contract; the
original str/urllib boundary node IDs below intentionally remain unchanged.
Source repair web#22 replaces the four A-008 callable-link limitations one-to-one
with desired-success regressions. web#23 replaces A-009 one-to-one with exact
binary save, closed-file and intercepted single-launch regression coverage.
Historical tracking reference: web#3 (original browser audit).
A future source repair must replace each affected limitation assertion with a
one-to-one reconciled desired-contract regression, not silently delete coverage.
All probes use actual framework requests in fresh Core/network-denied processes.
Legacy parser dependencies are optional: the explicitly labelled parser seam
below tests real link methods but does NOT certify BeautifulSoup integration.
"""
import pytest

from .test_readme_contract import probe


APP = r'''
from web.browser import AppBrowser, Browser
class Page:
    def GET(self):
        if web.ctx.path == '/cookie':
            web.setcookie('probe', 'present', path='/')
        if web.ctx.path == '/echo-cookie':
            return web.cookies().get('probe', 'absent')
        return '<a href="/next">Next</a><a href="/other">Other</a>'
    def POST(self):
        calls.append(dict(web.input()))
        return web.input().message
calls = []
app = web.application(('/.*', Page), {}, autoreload=False)
b = app.browser()
assert type(b) is AppBrowser
'''


def test_direct_request_supported_str_and_dict(tmp_path, record_property):
    probe(APP + r'''
results = []
for body in ['message=hello+world', {'message': 'hello world'}]:
    response = app.request('/submit', method='POST', data=body,
                           headers={'Content-Type': 'application/x-www-form-urlencoded'})
    assert (response.status, response.data) == ('200 OK', b'hello world')
    results.append(response.status)
assert calls == [{'message': 'hello world'}, {'message': 'hello world'}]
print(json.dumps({'statuses': results, 'handler_calls': calls}))
''', tmp_path, record_property)


@pytest.mark.parametrize('client,body', [
    ('AppBrowser', 'message=hello'),
    ('Browser', 'message=hello'),
], ids=['appbrowser-str', 'browser-str'])
def test_pinned_limitation_a006_post_body(tmp_path, record_property, client, body):
    probe(APP + '\nclient = ' + repr(client) + '\nbody = ' + repr(body) + r'''
try:
    if client == 'request':
        app.request('/submit', method='POST', data=body)
    elif client == 'AppBrowser':
        b.open('/submit', data=body)
    else:
        Browser().open('http://127.0.0.1/submit', data=body)
except (AttributeError, TypeError) as error:
    expected = ('AttributeError', "'bytes' object has no attribute 'encode'") if isinstance(body, bytes) else (
        'TypeError', 'POST data should be bytes, an iterable of bytes, or a file object. It cannot be of type str.')
    assert (type(error).__name__, str(error)) == expected
else:
    raise AssertionError('Pinned limitation changed: reconcile A-006 with source-fix tests')
assert calls == []
print(json.dumps({'followup': 'A-006', 'client': client, 'body_type': type(body).__name__,
                  'exception': expected[0], 'message': expected[1], 'handler_calls': calls}))
''', tmp_path, record_property)


# browser.py only asks get_soup().findAll(name='a'), then tag.string/get/__getitem__.
# Parse actual response bytes with stdlib HTMLParser at that parser boundary.
# Simple flat anchors only: not a replacement for legacy BeautifulSoup semantics.
PARSER_SEAM = r'''
from html.parser import HTMLParser
class Anchor(dict):
    string = None
class FlatAnchors(HTMLParser):
    def __init__(self, data):
        super().__init__()
        self.anchors = []
        self.current = None
        self.feed(data.decode('utf-8'))
    def handle_starttag(self, tag, attrs):
        if tag == 'a':
            self.current = Anchor(attrs)
            self.anchors.append(self.current)
    def handle_data(self, data):
        if self.current is not None:
            self.current.string = (self.current.string or '') + data
    def handle_endtag(self, tag):
        if tag == 'a':
            self.current = None
    def findAll(self, name):
        assert name == 'a'
        return self.anchors
b.get_soup = lambda: FlatAnchors(b.data)
b.open('/')
'''


@pytest.mark.parametrize('method', ['_filter_links', 'get_links', 'find_link', 'follow_link'])
def test_callable_links_desired_contract(tmp_path, record_property, method):
    from .test_link_predicate_contract import predicate_probe

    predicate_probe(APP + r'''
gets = []
original_get = Page.GET
def tracked_get(self):
    gets.append([web.ctx.method, web.ctx.path])
    return original_get(self)
Page.GET = tracked_get
''' + PARSER_SEAM + '\nmethod = ' + repr(method) + r'''
# Retain one parsed response so object identity, not just equal hrefs, is tested.
soup = b.get_soup()
b.get_soup = lambda: soup
anchors = soup.anchors
visited = []
def predicate(link):
    visited.append(link)
    return link.get('href') == '/next'
if method == '_filter_links':
    assert b._filter_links([], predicate=predicate) == []
    assert visited == []
    result = b._filter_links(anchors, predicate=predicate)
else:
    result = getattr(b, method)(predicate=predicate)
assert len(visited) == 2 and all(a is e for a, e in zip(visited, anchors))
if method in ('_filter_links', 'get_links'):
    assert len(result) == 1 and result[0] is anchors[0]
elif method == 'find_link':
    assert result is anchors[0]
else:
    assert result.read() == b.data == b'<a href="/next">Next</a><a href="/other">Other</a>'
    assert result.geturl() == b.url == 'http://0.0.0.0:8080/next'
    assert b.path == '/next' and b.status == 200
assert gets == ([['GET', '/'], ['GET', '/next']] if method == 'follow_link' else [['GET', '/']])
assert b.path == ('/next' if method == 'follow_link' else '/')
print(json.dumps({'repair': 'A-008', 'method': method, 'predicate_calls': len(visited),
                  'GETs': gets, 'selected_href': '/next',
                  'scope': 'real link methods; stdlib parser seam; limited integration'}))
''', tmp_path, record_property)


def test_show_bytes_desired_save_closed_single_launch(tmp_path, record_property):
    from .test_show_bytes_contract import EXACT_SAVE, SETUP, show_probe

    show_probe(SETUP + EXACT_SAVE, tmp_path, record_property)


def test_reset_clears_actual_cookies_only(tmp_path, record_property):
    probe(APP + DOCUMENT + r'''
b.open('/cookie')
assert [(c.name, c.value) for c in b.cookiejar] == [('probe', 'present')]
b.open('/echo-cookie')
assert b.data == b'present'
# No ClientForm installed/claimed: selected form is a state-identity sentinel.
b.form = object()
b._forms = [b.form]
attributes = ('path', 'url', '_response', 'data', 'status', 'form', '_forms')
before = {name: getattr(b, name) for name in attributes}
jar = b.cookiejar
b.reset()
assert b.cookiejar is jar and list(jar) == []
assert all(getattr(b, name) is value for name, value in before.items())
assert b.get_response().read() == b'present'
b.open('/echo-cookie')
assert b.data == b'absent'
fresh = app.browser()
assert fresh.path == '/' and fresh.url == 'http://0.0.0.0:8080/'
assert all(getattr(fresh, name) is None for name in ('_response', 'data', 'status', 'form', '_forms'))
assert list(fresh.cookiejar) == []
b.open('/cookie')
assert len(list(b.cookiejar)) == 1
state_before_example = {name: getattr(b, name) for name in attributes}
namespace = {'b': b, 'app': app}
execute_fence('browser.md', '### Cookie Management', namespace)
assert list(b.cookiejar) == []
assert all(getattr(b, name) is value for name, value in state_before_example.items())
assert namespace['b'] is not b and namespace['b'].app is app
assert namespace['b'].data is None and namespace['b'].form is None
print(json.dumps({'cookies_before': 1, 'cookies_after': 0,
                  'preserved_by_identity': list(before), 'next_request_cookie': 'absent',
                  'new_instance_initial_state': True, 'fences': hashes}))
''', tmp_path, record_property)


DOCUMENT = r'''
import hashlib
import re
hashes = {}
def execute_fence(filename, heading, namespace):
    document = Path(web.__file__).with_name('docs') / filename
    contents = document.read_bytes()
    marker = heading.encode() + b'\n'
    assert marker in contents, 'Missing documented workaround: ' + heading
    section = contents.split(marker, 1)[1]
    # Heading-like Python comments inside a fence are not Markdown headings.
    lines = []
    fenced = False
    for line in section.splitlines(keepends=True):
        if line.startswith(b'```'):
            fenced = not fenced
        elif not fenced and re.match(rb'^#{1,6} ', line):
            break
        lines.append(line)
    section = b''.join(lines)
    blocks = re.findall(rb'^```python\n(.*?)^```', section, flags=re.M | re.S)
    assert len(blocks) == 1, (heading, len(blocks))
    source = blocks[0]
    hashes[filename + ':' + heading] = hashlib.sha256(source).hexdigest()
    exec(compile(source, str(document) + ':' + heading, 'exec'), namespace)
'''


def test_markdown_direct_post_workaround(tmp_path, record_property):
    probe(DOCUMENT + r'''
namespace = {}
execute_fence('application.md', '##### Direct POST workaround', namespace)
assert namespace['response'].data == b'hello world'
assert namespace['raw_response'].data == b'hello world'
assert namespace['received'] == [{'message': 'hello world'}, {'message': 'hello world'}]
print(json.dumps({'fences': hashes, 'handler_inputs': namespace['received']}))
''', tmp_path, record_property)


def test_markdown_browser_get_and_direct_post(tmp_path, record_property):
    probe(DOCUMENT + r'''
namespace = {}
execute_fence('browser.md', '### Basic Usage', namespace)
from web.browser import AppBrowser
assert type(namespace['b']) is AppBrowser
assert (namespace['b'].path, namespace['b'].status, namespace['b'].data) == ('/', 200, b'Hello, world!')
execute_fence('browser.md', '### Working with Forms', namespace)
assert namespace['response'].status == '200 OK'
assert namespace['response'].data == b'hello world'
print(json.dumps({'fences': hashes, 'GET': namespace['b'].status, 'POST': namespace['response'].status}))
''', tmp_path, record_property)


def test_markdown_bounded_link_filters_with_parser_seam(tmp_path, record_property):
    probe(APP + PARSER_SEAM + DOCUMENT + r'''
namespace = {'b': b}
execute_fence('browser.md', '### Working with Links', namespace)
assert [link['href'] for link in namespace['links']] == ['/next']
assert [link['href'] for link in namespace['selected']] == ['/next']
assert namespace['link']['href'] == '/next'
assert b.path == '/next' and b.status == 200
# Additional real method boundaries: no match, exact AND regex, explicit link.
assert b.get_links(text='missing') == []
assert b.find_link(url='/missing') is None
assert len(b.get_links(text_regex='^Next$', url='/next')) == 1
from web.browser import BrowserError
try:
    b.follow_link(text='missing')
except BrowserError as error:
    assert str(error) == 'No link found'
else:
    raise AssertionError('No-match link unexpectedly followed')
print(json.dumps({'fences': hashes, 'path': b.path,
                  'scope': 'real methods; stdlib flat-anchor parser seam; limited integration'}))
''', tmp_path, record_property)


def test_markdown_binary_preview_workaround_without_launch(tmp_path, record_property):
    probe(APP + DOCUMENT + r'''
import webbrowser
launches = []
def deny_launch(*args, **kwargs):
    launches.append(args)
    raise AssertionError('Desktop launch prohibited')
webbrowser.open = deny_launch
b.open('/')
namespace = {'b': b}
execute_fence('browser.md', '### Saving a Response Without Launching a Browser', namespace)
assert namespace['saved_bytes'] == b.data
assert namespace['preview_uri'].startswith('file:')
assert not namespace['preview'].exists()
assert launches == []
print(json.dumps({'fences': hashes, 'bytes_sha256': hashlib.sha256(namespace['saved_bytes']).hexdigest(),
                  'owned_preview_cleaned': True, 'browser_launches': len(launches)}))
''', tmp_path, record_property)
