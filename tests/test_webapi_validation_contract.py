"""Executable webapi validation documentation; unchanged runtime, real WSGI.

Fresh -I -B children avoid ThreadedDict cleanup of other tests' contexts.
Python audit/import guards are test isolation, not an OS sandbox. Only owned
SQLite :memory: connections are allowed; no deployed data or live services.
"""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import textwrap

import pytest

from .test_template_security_contract import BOOTSTRAP, WEB_ROOT, fences

DOC = WEB_ROOT / 'docs/webapi.md'
# Retain the established pre-import guard; narrowly permit owned memory SQLite.
_SQL_DENIAL = "'os.posix_spawn', 'sqlite3.connect'}"
assert BOOTSTRAP.count(_SQL_DENIAL) == 1
BOOTSTRAP = BOOTSTRAP.replace(_SQL_DENIAL, "'os.posix_spawn'}\n    if event == 'sqlite3.connect':\n        denied = args[0] != ':memory:'")


def probe(source, tmp_path, record_property):
    env = {'PATH': os.defpath, 'PYTHON_DOTENV_DISABLED': '1',
           'HOME': str(tmp_path), 'TMPDIR': str(tmp_path), 'LC_ALL': 'C'}
    program = BOOTSTRAP + '\n' + textwrap.dedent(source) + '''
assert not {'core', 'modules', 'dotenv'}.intersection(sys.modules)
print(json.dumps({'completed': True, 'isolated': sys.flags.isolated,
                  'no_bytecode': sys.dont_write_bytecode, 'web_path': web.__file__}))
'''
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


@pytest.mark.parametrize('method', ['GET', 'POST'])
def test_input_runtime_presence_defaults_and_unmodified_strings(method, tmp_path, record_property):
    probe('method = ' + repr(method) + '\n' + r'''
from urllib.parse import urlencode
snapshots = []
class Index:
    def GET(self):
        mode = web.ctx.path
        if mode == '/required':
            result = web.input('username', 'password', username='fallback')
        else:
            raw = dict(web.webapi.rawinput())
            result = web.input(required=['username', 'password'], page=1, tags=[])
            snapshots.append((raw, dict(result)))
        return json.dumps(dict(result))
    POST = GET
app = web.application(('/.*', Index), {}, autoreload=False)
def request(path, pairs):
    data = urlencode(pairs)
    return app.request(path + ('?' + data if method == 'GET' else ''), method=method,
                       data=data if method == 'POST' else None,
                       headers={'Content-Type': 'application/x-www-form-urlencoded'})
empty = request('/', [])
assert empty.status == '200 OK'
assert json.loads(empty.data) == {'required': ['username', 'password'], 'page': 1, 'tags': []}
for pairs in ([], [('username', 'a')], [('password', 'b')]):
    response = request('/required', pairs)
    assert response.status == '400 Bad Request'
blank = request('/required', [('username', ''), ('password', '')])
assert blank.status == '200 OK' and json.loads(blank.data) == {'username': '', 'password': ''}
payload = "Žluťoučký <b>&\"' OR '1'='1"
pairs = [('username', payload), ('page', 'not-an-integer'), ('tags', 'one'), ('tags', 'two'),
         ('repeat', 'first'), ('repeat', 'last'), ('blank', '')]
response = request('/', pairs)
assert response.status == '200 OK'
raw, parsed = snapshots[-1]
assert raw['username'] == [payload] and parsed['username'] == payload
assert raw['repeat'] == ['first', 'last'] and parsed['repeat'] == 'last'
assert parsed['tags'] == ['one', 'two'] and parsed['blank'] == ''
assert parsed['page'] == 'not-an-integer'
print(json.dumps({'method': method, 'raw': raw, 'parsed': parsed, 'missing_status': '400 Bad Request'}))
''', tmp_path, record_property)


def test_input_get_post_selection_and_body_precedence(tmp_path, record_property):
    probe(r'''
class Index:
    def POST(self):
        return json.dumps([dict(web.input()), dict(web.input(_method='get')),
                           dict(web.input(_method='post'))])
app = web.application(('/', Index), {}, autoreload=False)
response = app.request('/?same=query&query=Q', method='POST', data='same=body&body=B',
                       headers={'Content-Type': 'application/x-www-form-urlencoded'})
assert response.status == '200 OK'
assert json.loads(response.data) == [{'same': 'body', 'query': 'Q', 'body': 'B'},
                                    {'same': 'query', 'query': 'Q'}, {'same': 'body', 'body': 'B'}]
''', tmp_path, record_property)


def test_security_prose_does_not_promise_input_injection_protection():
    prose = DOC.read_text()
    assert 'Input data is processed safely to prevent injection attacks' not in prose
    for boundary in ('parameter binding', 'HTML text', 'JavaScript', 'CSS', 'URL'):
        assert boundary in prose


def test_security_documented_sql_binding_and_html_contexts(tmp_path, record_property):
    source = documented('### Parsing is not injection protection', record_property)
    probe(source + r'''
from urllib.parse import urlencode
from html.parser import HTMLParser
class TextAndTitle(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tags, self.titles, self.text = [], [], []
    def handle_starttag(self, tag, attrs):
        self.tags.append(tag)
        self.titles.extend(value for key, value in attrs if key == 'title')
    def handle_data(self, data):
        self.text.append(data)
app = namespace['app']
for method in ('GET', 'POST'):
    def request(value):
        data = urlencode({'name': value})
        return app.request('/' + ('?' + data if method == 'GET' else ''), method=method,
                           data=data if method == 'POST' else None,
                           headers={'Content-Type': 'application/x-www-form-urlencoded'})
    for value, matches, escaped in [
        ('Alice', 1, 'Alice'),
        ("O'Reilly <b>&\"", 1, 'O&#x27;Reilly &lt;b&gt;&amp;&quot;'),
        ("' OR '1'='1", 0, '&#x27; OR &#x27;1&#x27;=&#x27;1'),
        ('<b>literal</b>', 0, '&lt;b&gt;literal&lt;/b&gt;'),
    ]:
        response = request(value)
        assert response.status == '200 OK'
        expected = '<p title="' + escaped + '">' + escaped + '</p><p>Matches: ' + str(matches) + '</p>'
        assert response.data == expected.encode(), response.data
        parser = TextAndTitle()
        parser.feed(response.data.decode())
        assert parser.tags == ['p', 'p'] and parser.titles == [value]
        assert parser.text == [value, 'Matches: ' + str(matches)]
assert app.request('/').status == '400 Bad Request'
''', tmp_path, record_property)


def test_probe_guards_keep_sqlite_allowlist_narrow(tmp_path, record_property):
    probe(r'''
import importlib
import socket
import sqlite3
for name in ('core', 'modules', 'dotenv'):
    raises(AssertionError, lambda: importlib.import_module(name))
raises(AssertionError, lambda: open('.env'))
for database in ('blocked.db', 'file::memory:?cache=shared', '/unowned/prohibited.db'):
    raises(AssertionError, lambda: sqlite3.connect(database))
with sqlite3.connect(':memory:') as db:
    assert db.execute('select ?', ("O'Reilly",)).fetchone() == ("O'Reilly",)
db.close()
raises(AssertionError, lambda: socket.getaddrinfo('example.invalid', 443))
assert not Path('blocked.db').exists()
''', tmp_path, record_property)


@pytest.mark.parametrize('mode', ['keyword', 'positional', 'generator'])
def test_cookie_required_pinned_limitation(mode, tmp_path, record_property):
    probe('mode = ' + repr(mode) + '\n' + r'''
import contextlib
import io
observed = []
class Index:
    def GET(self):
        if mode == 'keyword':
            return json.dumps(dict(web.cookies(required=['session_id', 'user_id'])))
        if mode == 'generator':
            def body():
                web.cookies('session_id', 'user_id')
                yield 'ok'
            return body()
        try:
            result = web.cookies('session_id', 'user_id', session_id='fallback')
        except web.BadRequest:
            observed.append(web.ctx.status)
            raise
        return json.dumps(dict(result))
app = web.application(('/', Index), {}, autoreload=False)
with contextlib.redirect_stderr(io.StringIO()) as log:
    if mode == 'generator':
        response = app.request('/')
        assert response.status == '400 Bad Request'
        assert response.data == b'bad request'
        assert log.getvalue() == ''
        print(json.dumps({'mode': mode, 'status': response.status}))
    else:
        response = app.request('/')
        if mode == 'keyword':
            assert response.status == '200 OK'
            assert json.loads(response.data) == {'required': ['session_id', 'user_id']}
        else:
            assert observed == ['400 Bad Request']
            assert response.status == '400 Bad Request'
            assert response.data == b'bad request'
            assert log.getvalue() == ''
        print(json.dumps({'mode': mode, 'status': response.status, 'observed': observed}))
for header in ('session_id=; user_id=', 'session_id=example; user_id=7'):
    response = app.request('/', headers={'Cookie': header})
    assert response.status == '200 OK'
''', tmp_path, record_property)


def test_cookies_documented_presence_and_nonempty_policy(tmp_path, record_property):
    source = documented('### `cookies(*requireds, **defaults)`', record_property)
    probe(source + r'''
app = namespace['app']
for header in ('', 'session_id=example', 'user_id=7', 'session_id=; user_id=7',
               'session_id=example; user_id='):
    response = app.request('/', headers={'Cookie': header})
    assert response.status == '400 Bad Request', (header, response.status)
response = app.request('/', headers={'Cookie': 'session_id=example; user_id=7'})
assert response.status == '200 OK' and response.data == b'Cookie fields present'
''', tmp_path, record_property)


@pytest.mark.parametrize('method', ['GET', 'POST'])
def test_handling_input_documented_validation(method, tmp_path, record_property):
    source = documented('### Handling Input Data', record_property)
    probe(source + 'method = ' + repr(method) + '\n' + r'''
from urllib.parse import urlencode
app = namespace['app']
def request(pairs):
    data = urlencode(pairs)
    return app.request('/' + ('?' + data if method == 'GET' else ''), method=method,
                       data=data if method == 'POST' else None,
                       headers={'Content-Type': 'application/x-www-form-urlencoded'})
valid = [('username', ' Alice '), ('password', ' example ')]
for pairs in ([], [('username', 'Alice')], [('password', 'example')],
              [('username', ''), ('password', 'x')], [('username', '  '), ('password', 'x')],
              [('username', 'Alice'), ('password', '')]):
    assert request(pairs).status == '400 Bad Request', pairs
for page in ('', 'oops', '1.5', '0', '-1', '101'):
    assert request(valid + [('page', page)]).status == '400 Bad Request', page
for page in ('1', '100'):
    response = request(valid + [('page', page)])
    assert response.status == '200 OK'
    assert json.loads(response.data) == {'username': ' Alice ', 'page': int(page)}
response = request(valid)
assert json.loads(response.data) == {'username': ' Alice ', 'page': 1}
# This example's explicit password policy is nonempty, not whitespace trimming.
response = request([('username', 'Alice'), ('password', ' ')])
assert response.status == '200 OK'
assert request(valid + [('username', '')]).status == '400 Bad Request'
''', tmp_path, record_property)


def test_input_presence_documented_example(tmp_path, record_property):
    source = documented('### `input(*requireds, **defaults)`', record_property)
    probe(source + r'''
app = namespace['app']
for method in ('GET', 'POST'):
    def request(data):
        return app.request('/' + ('?' + data if method == 'GET' else ''), method=method,
                           data=data if method == 'POST' else None,
                           headers={'Content-Type': 'application/x-www-form-urlencoded'})
    for data in ('', 'username=a', 'password=b'):
        assert request(data).status == '400 Bad Request'
    valid = request('username=Alice&password=example')
    assert valid.status == '200 OK'
    assert json.loads(valid.data) == {'username': 'Alice', 'name': 'Anonymous', 'page': 1}
    blank = request('username=&password=&page=oops')
    assert blank.status == '200 OK'
    assert json.loads(blank.data) == {'username': '', 'name': 'Anonymous', 'page': 'oops'}
''', tmp_path, record_property)
