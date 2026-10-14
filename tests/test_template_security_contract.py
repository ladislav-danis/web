"""Security documentation contracts, not a template runtime hardening patch.

Assignment limitations intentionally characterize this revision. Source hardening
must replace those cases with construction-time rejection and unchanged objects.
Fresh -I -B processes isolate Core/DB fixtures; Python guards are not an OS sandbox.
"""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import textwrap

import pytest

WEB_ROOT = Path(__file__).resolve().parents[1]
DOC = WEB_ROOT / 'docs/template.md'
BOOTSTRAP = r'''
import importlib.abc
import json
import os
from pathlib import Path
import sys

blocked = []
class NoApplication(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {'core', 'modules', 'dotenv'}:
            blocked.append('import:' + fullname)
            raise AssertionError('Application import forbidden: ' + fullname)
sys.meta_path.insert(0, NoApplication())
def offline(event, args):
    denied = (event.startswith('socket.') and event != 'socket.__new__') or event in {
        'subprocess.Popen', 'os.system', 'os.posix_spawn', 'sqlite3.connect'}
    if event == 'open' and isinstance(args[0], (str, bytes)):
        path = Path(os.fsdecode(args[0]))
        denied = denied or path.name == '.env'
        mode, flags = args[1:3]
        writing = (isinstance(mode, str) and any(c in mode for c in 'wax+')) or (
            isinstance(flags, int) and flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT))
        if writing and not path.resolve().is_relative_to(Path.cwd()):
            denied = True
    if denied:
        blocked.append(event)
        raise AssertionError('Probe operation forbidden: ' + event)
sys.addaudithook(offline)
sys.path.insert(0, sys.argv[1])
import web
from web.template import Template, Render, SecurityError
assert Path(web.__file__).resolve() == Path(sys.argv[1]) / 'web/__init__.py'
assert sys.dont_write_bytecode
assert Path.cwd() == Path(os.environ['HOME']) == Path(os.environ['TMPDIR'])
web.config.debug = False

def raises(kind, operation):
    try:
        operation()
    except kind as error:
        return error
    raise AssertionError('Expected ' + kind.__name__)
'''


def probe(source, tmp_path, record_property):
    env = {'PATH': os.defpath, 'PYTHON_DOTENV_DISABLED': '1',
           'HOME': str(tmp_path), 'TMPDIR': str(tmp_path), 'LC_ALL': 'C'}
    trailer = '''
assert not {'core', 'modules', 'dotenv'}.intersection(sys.modules)
print(json.dumps({'web_path': web.__file__, 'isolated': sys.flags.isolated,
                  'no_bytecode': sys.dont_write_bytecode, 'blocked': blocked,
                  'cwd': str(Path.cwd()), 'completed': True}))
'''
    result = subprocess.run(
        [sys.executable, '-I', '-B', '-c', BOOTSTRAP + '\n' + textwrap.dedent(source) + trailer,
         str(WEB_ROOT.parent)], cwd=tmp_path, env=env,
        text=True, capture_output=True, timeout=30)
    record_property('probe_stdout', result.stdout)
    record_property('probe_stderr', result.stderr)
    assert result.returncode == 0, result.stdout + result.stderr
    evidence = json.loads(result.stdout.splitlines()[-1])
    assert evidence['completed'] and evidence['isolated'] == 1 and evidence['no_bytecode']


def fences(raw):
    """Preserve bytes and ignore headings inside fences.

    The final legacy reference has an unrelated unclosed fence (web#15); expose
    its closed=False status rather than treating the entire page as validated.
    Executed security fences must be closed.
    """
    heading, opened = '', None
    result = []
    for line_number, line in enumerate(raw.splitlines(keepends=True), 1):
        if opened is not None:
            if line.rstrip(b'\r\n') == b'```':
                result.append((heading, opened, language, b''.join(body), True))
                opened = None
            else:
                body.append(line)
        elif line.startswith(b'```'):
            opened, language, body = line_number, line.strip()[3:].decode(), []
        elif line.startswith(b'#'):
            heading = line.decode().strip()
    if opened is not None:
        result.append((heading, opened, language, b''.join(body), False))
    return result


EXECUTABLE_HEADINGS = ['### HTML Escaping', '### AST Validation']


def test_documented_html_usage_example(tmp_path, record_property):
    selected = [b for b in fences(DOC.read_bytes()) if b'html = template(' in b[3]]
    assert len(selected) == 1
    heading, line, language, code, closed = selected[0]
    assert closed and language == 'python'
    record_property('fence_sha256', hashlib.sha256(code).hexdigest())
    record_property('markdown_line', line)
    probe('''
        namespace = {'__name__': '__main__'}
        exec(compile(''' + repr(code) + ''', 'docs/template.md', 'exec'), namespace)
        value = '<b>&"\\\''
        output = str(namespace['template'](value, [value]))
        escaped = '&lt;b&gt;&amp;&quot;&#39;'
        assert '<title>' + escaped + '</title>' in output, output
        assert '<p>' + escaped + '</p>' in output, output
        assert value not in output
    ''', tmp_path, record_property)


@pytest.mark.parametrize('heading', EXECUTABLE_HEADINGS)
def test_documented_security_example(heading, tmp_path, record_property):
    selected = [b for b in fences(DOC.read_bytes()) if b[0] == heading]
    assert len(selected) == 1, heading
    _, line, language, code, closed = selected[0]
    assert closed and language == 'python'
    record_property('fence_sha256', hashlib.sha256(code).hexdigest())
    record_property('markdown_line', line)
    probe('''
        namespace = {'__name__': '__main__'}
        exec(compile(''' + repr(code) + ''', 'docs/template.md', 'exec'), namespace)
    ''', tmp_path, record_property)


def test_documented_variable_fragment(tmp_path, record_property):
    selected = [b for b in fences(DOC.read_bytes()) if b[0] == '### Variables']
    assert len(selected) == 1
    _, line, language, code, closed = selected[0]
    assert closed and language == 'python'
    record_property('fence_sha256', hashlib.sha256(code).hexdigest())
    record_property('markdown_line', line)
    probe(r'''
        code = ''' + repr(code) + r'''
        # Syntax fragment: supply only its declared sample variables, retain
        # every byte including literal inline comments and whitespace.
        template = Template('$def with(name, expression)\n' + code.decode(), filename='page.html')
        output = str(template('<b>', '<b>'))
        expected_values = ['&lt;b&gt;', '<b>', '&lt;b&gt;', '&lt;b&gt;']
        expected = ''.join(value + row[row.index(' '):] for value, row in zip(expected_values, code.decode().splitlines(keepends=True)))
        assert output == expected, output
    ''', tmp_path, record_property)


SUFFIXES = [
    ('page.html', True, 'text/html; charset=utf-8'),
    ('page.xhtml', True, 'application/xhtml+xml; charset=utf-8'),
    ('page.xml', True, None), ('page.txt', False, 'text/plain'),
    ('page', False, None), ('page.unknown', False, None),
    ('page.HTML', False, None), ('<template>', False, None),
]


@pytest.mark.parametrize('filename,escaped,content_type', SUFFIXES)
def test_direct_filename_selects_filter(filename, escaped, content_type, tmp_path, record_property):
    probe(r'''
        filename, escaped, content_type = ''' + repr((filename, escaped, content_type)) + r'''
        source = '$def with(value)\n$value'
        template = Template(source) if filename == '<template>' else Template(source, filename=filename)
        value = '<b>&"\''
        expected = '&lt;b&gt;&amp;&quot;&#39;\n' if escaped else value + '\n'
        assert str(template(value)) == expected
        assert template.content_type == content_type
        print(json.dumps({'filename': filename, 'output': expected}))
    ''', tmp_path, record_property)


@pytest.mark.parametrize('filename,escaped,content_type', SUFFIXES[:-1])
def test_render_uses_real_file_suffix(filename, escaped, content_type, tmp_path, record_property):
    probe(r'''
        from tempfile import TemporaryDirectory
        filename, escaped, content_type = ''' + repr((filename, escaped, content_type)) + r'''
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / filename).write_text('$def with(value)\n$value', encoding='utf-8')
            template = Render(str(root), cache=False).page
            value = '<b>&"\''
            expected = '&lt;b&gt;&amp;&quot;&#39;\n' if escaped else value + '\n'
            assert str(template(value)) == expected
            assert Path(template.filename) == root / filename
            assert template.content_type == content_type
        assert not root.exists()
        print(json.dumps({'render_filename': filename, 'output': expected}))
    ''', tmp_path, record_property)


@pytest.mark.parametrize('filter_value', [None, False])
def test_falsy_filter_keeps_html_extension_default(filter_value, tmp_path, record_property):
    probe(r'''
        template = Template('$def with(value)\n$value', filename='page.html', filter=''' + repr(filter_value) + r''')
        assert str(template('<&')) == '&lt;&amp;\n'
    ''', tmp_path, record_property)


def test_custom_filter_conversion_raw_and_literal_boundaries(tmp_path, record_property):
    probe(r'''
        seen = []
        def custom(value):
            seen.append(value)
            return '[' + value + ']'
        template = Template('$def with(value)\n<i>$value</i>|$:value', filename='page.html', filter=custom)
        assert str(template('<&')) == '<i>[<&]</i>|<&\n'
        assert str(template(None)) == '<i>[]</i>|\n'
        assert str(template(42)) == '<i>[42]</i>|42\n'
        assert seen == ['<&', '', '42']
        plain = Template('$def with(value)\n$value', filter=web.websafe)
        assert str(plain('<&')) == '&lt;&amp;\n'
        assert plain.content_type is None
    ''', tmp_path, record_property)


def test_html_text_quoted_attribute_and_raw_contexts(tmp_path, record_property):
    probe(r'''
        value = '<b>&"\''
        template = Template('$def with(value)\n<p title="$value">$(value)</p>|$:value', filename='page.html')
        escaped = '&lt;b&gt;&amp;&quot;&#39;'
        assert str(template(value)) == '<p title="' + escaped + '">' + escaped + '</p>|' + value + '\n'
        # Escaping is not URL-scheme validation. No browser/navigation involved.
        link = Template('$def with(value)\n<a href="$value">link</a>', filename='page.html')
        assert str(link('custom:example')) == '<a href="custom:example">link</a>\n'
        assert str(template(None)) == '<p title=""></p>|\n'
    ''', tmp_path, record_property)


def test_braces_and_parentheses_apply_selected_filter(tmp_path, record_property):
    probe(r'''
        template = Template('$def with(value)\n${value}', filename='page.html')
        assert str(template('<b>')) == '&lt;b&gt;\n'
        grouped = Template('$def with(value)\n$(value)', filename='page.html')
        assert str(grouped('<b>')) == '&lt;b&gt;\n'
    ''', tmp_path, record_property)


def test_direct_attribute_assignment_rejected_before_mutation(tmp_path, record_property):
    probe(r'''
        from types import SimpleNamespace
        box = SimpleNamespace(x=1)
        error = raises(SecurityError, lambda: Template('$def with(a)\n$code:\n    a.x = 3\n$a.x'))
        assert "attribute 'x'" in str(error)
        assert box.x == 1
    ''', tmp_path, record_property)


@pytest.mark.parametrize('statement,expected', [
    ('a.x += 1', 2), ('(a.x, y) = (2, 3)', 2),
    ('((a.x, y), z) = ((4, 3), 5)', 4),
])
def test_pinned_assignment_limitation_mutates_owned_object(statement, expected, tmp_path, record_property):
    probe(r'''
        from types import SimpleNamespace
        box = SimpleNamespace(x=1)
        statement, expected = ''' + repr((statement, expected)) + r'''
        error = raises(SecurityError, lambda: Template('$def with(a)\n$code:\n    ' + statement + '\n$a.x'))
        assert "attribute 'x'" in str(error)
        assert box.x == 1  # rejected during construction; never render
        print(json.dumps({'rejected_assignment': statement, 'obsolete_expected': expected, 'after': box.x}))
    ''', tmp_path, record_property)


@pytest.mark.parametrize('source', ['$def with(a)\n$a._private', '$__private', '$code:\n    import math'])
def test_retained_ast_rejection_controls(source, tmp_path, record_property):
    probe('raises(SecurityError, lambda: Template(' + repr(source) + '))', tmp_path, record_property)


def test_supplied_callable_is_an_application_capability(tmp_path, record_property):
    probe(r'''
        from types import SimpleNamespace
        box = SimpleNamespace(x=1)
        def increment():
            box.x += 1
            return box.x
        template = Template('$increment()', globals={'increment': increment})
        assert str(template()) == '2\n'
        assert box.x == 2
    ''', tmp_path, record_property)


def test_probe_isolation_guards(tmp_path, record_property):
    probe(r'''
        import importlib
        import socket
        import sqlite3
        import subprocess
        for name in ('core', 'modules', 'dotenv'):
            raises(AssertionError, lambda: importlib.import_module(name))
        raises(AssertionError, lambda: Path('.env').read_bytes())
        raises(AssertionError, lambda: sqlite3.connect(':memory:'))
        with socket.socket() as sock:
            raises(AssertionError, lambda: sock.connect(('127.0.0.1', 9)))
        raises(AssertionError, lambda: subprocess.run([sys.executable, '-c', 'pass']))
        assert set(blocked) == {'import:core', 'import:modules', 'import:dotenv', 'open',
                                'sqlite3.connect', 'socket.connect', 'subprocess.Popen'}
    ''', tmp_path, record_property)
