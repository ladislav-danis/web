"""Form reference examples and constructor contracts on real, offline web.py.

Each probe starts a fresh framework-only interpreter. Markdown execution gets
no injected imports or application; request examples use real in-process WSGI.
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
import contextlib
import doctest
import hashlib
import io
import json
from pathlib import Path
import sys

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
from web import form
assert Path(web.__file__).resolve().parent == Path(sys.argv[1]) / 'web'
web.config.debug = False
hashes = []

def fence(heading, index=0, path=None):
    text = (Path(path) if path else Path(web.__file__).with_name('docs') / 'form.md').read_text()
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
    # Historical final fence is unclosed; preserve its exact contents for RED.
    if current is not None and section == heading:
        blocks.append(''.join(current))
    assert blocks, heading
    source = blocks[index]
    hashes.append(hashlib.sha256(source.encode()).hexdigest())
    return source

def execute(heading, index=0):
    ns = {'__name__': 'documentation_example'}
    with contextlib.redirect_stdout(io.StringIO()):
        exec(compile(fence(heading, index), '<form.md: ' + heading + '>', 'exec'), ns)
    return ns

def request_example(heading, query):
    captured = []
    class Example:
        def GET(self):
            ns = execute(heading)
            captured.append(ns)
            return ns['f'].render()
    app = web.application(('/', Example), locals(), autoreload=False)
    response = app.request('/' + query)
    assert response.status == '200 OK', response.status
    assert len(captured) == 1
    return captured[0], response
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


def test_markdown_age_validation(tmp_path, record_property):
    probe('''
        for value, expected in [('not a number', False), ('-1', False),
                                ('151', False), ('0', True), ('150', True),
                                ('42', True), ('', False), (None, False),
                                (42, False), (1.5, False), ('1.5', False)]:
            ns = execute('Custom Validation')
            f = ns['f']
            assert f.validates({'age': value}) is expected, (value, f.note)
            assert f.d.age == value
            assert len(f.age.validators) == 3
            assert 'validators' not in f.age.attrs
            if not expected:
                assert f.note
                assert 'class="wrong"' in f.render()
        assert ns['is_valid_age']('150') is True
        assert ns['is_valid_age']('151') is False
    ''', tmp_path, record_property)


def test_markdown_password_validation(tmp_path, record_property):
    probe('''
        for password, expected in [('x', False), ('12345', False),
                                   ('123456', True), ('a long password', True),
                                   ('', False), (None, False)]:
            f = execute('Form with Multiple Inputs')['f']
            data = {'username': 'alice', 'password': password, 'email': 'a@example.com'}
            assert f.validates(data) is expected
            assert 'validators' not in f.password.attrs
            if not expected:
                assert f.password.note
        f = execute('Form with Multiple Inputs')['f']
        assert not f.validates({'username': '', 'password': '123456'})
        assert f.username.note == 'Required'
    ''', tmp_path, record_property)


@pytest.mark.parametrize('mapping', ['dict', 'web.storage'])
def test_markdown_form_level_validation(mapping, tmp_path, record_property):
    probe('''
        for confirm, expected in [('abcdef', True), ('different', False)]:
            f = execute('Form with Form-Level Validators')['f']
            source = MAPPING(password='abcdef', confirm_password=confirm, extra='retained')
            assert f.validates(source) is expected
            assert f.value is source
            assert f.value['extra'] == 'retained'
            assert f.d == {'password': 'abcdef', 'confirm_password': confirm}
            assert all(isinstance(v, form.Validator) for v in f.validators)
            if not expected:
                assert f.note == 'Passwords must match'
        f = execute('Form with Form-Level Validators')['f']
        calls = []
        f.validators.append(form.Validator('spy', lambda source: calls.append(source) or True))
        assert not f.validates(MAPPING(password='', confirm_password=''))
        assert calls == []
        assert 'value' not in f.__dict__  # _validate was short-circuited
        assert f.password.note == 'Required'
    '''.replace('MAPPING', mapping), tmp_path, record_property)


@pytest.mark.parametrize('query,expected', [
    ('?submit=1&email=alice%40example.com', True),
    ('?submit=1&email=not-an-email', False),
    ('?submit=1&email=alice%40example.org', False),
    ('?submit=1&email=alice%40example.com.evil', False),
    ('?submit=1', False),
    ('?email=ignored%40example.com', None),
])
def test_markdown_conditional_request(query, expected, tmp_path, record_property):
    probe(f'''
        ns, response = request_example('Conditional Form Rendering', {query!r})
        f = ns['f']
        assert not f.validators
        if {expected!r} is None:
            assert f.email.value is None
            assert f.note is None
            assert b'value=' not in response.data
        else:
            assert f.valid is {expected!r}
            assert bool(f.email.note) is (not {expected!r})
            assert (b'class="wrong"' in response.data) is (not {expected!r})
    ''', tmp_path, record_property)


@pytest.mark.parametrize('heading', ['Usage', 'Basic Form Creation',
    'Form Validation', 'Using Form with web.input()', 'Rendering Form with CSS',
    'Accessing Form Values', 'Pre-filling Form Data'])
def test_markdown_self_contained_examples(heading, tmp_path, record_property):
    probe(f'''
        heading = {heading!r}
        if heading in ('Usage', 'Form Validation', 'Using Form with web.input()'):
            ns, response = request_example(heading, '?username=alice&password=abcdef&name=Alice')
            assert ns['f'].valid is True
            if heading == 'Using Form with web.input()':
                assert ns['f'].d.name == 'Alice'
            else:
                assert ns['f'].d.username == 'alice'
        else:
            ns = execute(heading)
            assert isinstance(ns['f'], form.Form)
            assert '<input ' in ns['f'].render()
            if heading in ('Accessing Form Values', 'Pre-filling Form Data'):
                assert ns['f'].d.email == 'john@example.com'
    ''', tmp_path, record_property)


def test_markdown_grouped_example(tmp_path, record_property):
    probe('''
        ns = execute('`GroupedDropdown`', 1)
        field = ns['car_type']
        assert isinstance(field, form.GroupedDropdown)
        assert '<optgroup label="Swedish Cars">' in field.render()
        assert '<option selected="selected" value="Audi">Audi</option>' in field.render()
    ''', tmp_path, record_property)


def test_markdown_render_css_repr(tmp_path, record_property):
    probe('''
        example = doctest.DocTestParser().get_doctest(
            fence('`render_css()`'), {}, 'render_css', None, 0)
        runner = doctest.DocTestRunner()
        output = io.StringIO()
        result = runner.run(example, out=output.write)
        assert result.failed == 0, output.getvalue()
        assert result.attempted >= 2
    ''', tmp_path, record_property)


@pytest.mark.parametrize('count', [0, 1, 2])
def test_grouped_dropdown_positional_validators(count, tmp_path, record_property):
    probe(f'''
        groups = [('numbers', [('1', 'One'), ('2', 'Two')])]
        calls = []
        first = form.Validator('not one', lambda v: calls.append(('first', v)) or v == '1')
        second = form.Validator('not two', lambda v: calls.append(('second', v)) or v == '2')
        validators = (first, second)[:{count}]
        field = form.GroupedDropdown('number', groups, *validators, description='Number', class_='choice')
        assert field.args is groups
        assert field.validators == validators
        assert field.description == 'Number'
        assert field.attrs['class'] == 'choice'
        assert field.validate('1') is ({count} < 2)
        assert calls == [('first', '1'), ('second', '1')][:{count}]
        assert '<option selected="selected" value="1">One</option>' in field.render()
        if {count} == 2:
            assert field.note == 'not two'
        calls.clear()
        assert field.validate('2') is ({count} == 0)
        assert calls == ([('first', '2')] if {count} else [])
        if {count}:
            assert field.note == 'not one'
    ''', tmp_path, record_property)


@pytest.mark.parametrize('value,selected', [('a', ['a']), (['a', 'b'], ['a', 'b']),
                                          (('a', 'b'), ['a', 'b']), (None, []),
                                          (7, ['7'])])
def test_grouped_dropdown_keyword_options_selection(value, selected, tmp_path, record_property):
    probe(f'''
        from html.parser import HTMLParser
        class Options(HTMLParser):
            def __init__(self):
                super().__init__()
                self.selected = []
            def handle_starttag(self, tag, attrs):
                attrs = dict(attrs)
                if tag == 'option' and 'selected' in attrs:
                    self.selected.append(attrs['value'])
        field = form.GroupedDropdown(name='choice', args=[('plain', ['a', 'b']),
            ('pairs', [(7, 'Seven')])], value={value!r}, multiple='multiple')
        parser = Options()
        parser.feed(field.render())
        assert parser.selected == {selected!r}
        assert 'multiple="multiple"' in field.render()
    ''', tmp_path, record_property)


def test_grouped_dropdown_escaping_and_empty(tmp_path, record_property):
    probe('''
        field = form.GroupedDropdown('n<&"', [('g<&"', [('v<&"', 'label<&"')]), ('empty', [])],
            id='id<&"', title='title<&"', value='v<&"')
        html = field.render()
        assert 'name="n&lt;&amp;&quot;"' in html
        assert 'id="id&lt;&amp;&quot;"' in html
        assert 'title="title&lt;&amp;&quot;"' in html
        assert '<optgroup label="g&lt;&amp;&quot;">' in html
        assert '<option selected="selected" value="v&lt;&amp;&quot;">label&lt;&amp;&quot;</option>' in html
        assert '<optgroup label="empty">\\n  </optgroup>' in html
        assert form.GroupedDropdown('empty', []).render() == '<select id="empty" name="empty">\\n</select>\\n'
        assert field.name == 'n<&"' and field.id == 'id<&"'
    ''', tmp_path, record_property)


def test_grouped_dropdown_form_fill_validate_clone(tmp_path, record_property):
    probe('''
        groups = [('letters', ['a', 'b'])]
        template = form.Form(form.GroupedDropdown('letter', groups, form.notnull))
        filled = template()
        assert filled is not template and filled.letter is not template.letter
        assert filled.fill({'letter': 'b'}) is True
        assert filled.d.letter == 'b'
        assert '<option selected="selected" value="b">b</option>' in filled.render()
        assert template.d.letter is None
        assert filled.validates({'letter': 'a'}) is True
        assert filled.d.letter == 'a'
        invalid = template({'letter': ''})
        assert invalid.valid is False and invalid.letter.note == 'Required'
        assert template.valid is True and template.letter.note is None
        # fill deliberately bypasses validation; options are not a membership policy.
        empty = template()
        assert empty.fill({'letter': ''}) is True
        assert empty.letter.note is None
        unknown = template()
        assert unknown.validates({'letter': 'unknown'}) is True
        assert 'selected=' not in unknown.render()
        clone = template({'letter': ['a', 'b']})
        assert clone.d.letter == ['a', 'b']
        assert clone.render().count('selected="selected"') == 2
        clone.letter.args.append(('more', ['c']))
        assert template.letter.args == groups
    ''', tmp_path, record_property)


def test_input_validator_contract_unchanged(tmp_path, record_property):
    probe('''
        # Characterization, not a fix: keywords remain HTML attrs on Input.
        field = form.Textbox('value', validators=[form.notnull])
        assert field.validators == ()
        assert field.validate('') is True
        assert 'validators=' in field.render()
        field = form.Textbox('value', form.notnull)
        assert field.validate('') is False
        assert field.validate('present') is True
        # The original source mapping (not transformed f.d) reaches form validators.
        seen = []
        f = form.Form(form.Checkbox('flag'), validators=[form.Validator('capture',
            lambda source: seen.append(source) or True)])
        source = web.storage(flag='yes', extra='unfiltered')
        assert f.validates(source)
        assert seen == [source] and seen[0] is source
        assert source.flag == 'yes' and f.d.flag is True
        assert 'extra' not in f.d
    ''', tmp_path, record_property)


def test_grouped_dropdown_construct_render(tmp_path, record_property):
    probe('''
        groups = [('Cars', ['Volvo', ('a', 'Audi')])]
        field = form.GroupedDropdown('car', groups, value='a')
        assert field.args is groups
        assert field.validators == ()
        assert field.render() == ('<select id="car" name="car">\\n'
            '  <optgroup label="Cars">\\n'
            '    <option value="Volvo">Volvo</option>\\n'
            '    <option selected="selected" value="a">Audi</option>\\n'
            '  </optgroup>\\n</select>\\n')
    ''', tmp_path, record_property)
