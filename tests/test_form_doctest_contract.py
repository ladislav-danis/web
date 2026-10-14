"""Form source doctests and real CLI policy; Python guards are not an OS sandbox."""
import hashlib
import json
import os
import subprocess
import sys

import pytest

from .test_template_security_contract import BOOTSTRAP, WEB_ROOT


def child(source, tmp_path, record_property, source_parent=None):
    parent = WEB_ROOT.parent if source_parent is None else source_parent
    argv = [sys.executable, '-I', '-B', '-c', BOOTSTRAP + source, str(parent)]
    env = {'PATH': os.defpath, 'HOME': str(tmp_path), 'TMPDIR': str(tmp_path),
           'XDG_CACHE_HOME': str(tmp_path), 'XDG_DATA_HOME': str(tmp_path),
           'XDG_CONFIG_HOME': str(tmp_path), 'PYTHON_DOTENV_DISABLED': '1', 'LC_ALL': 'C'}
    result = subprocess.run(argv, cwd=tmp_path, env=env, capture_output=True,
                            text=True, timeout=30)
    for key, value in [('child_argv', json.dumps(argv)), ('child_environment', json.dumps(env)),
                       ('probe_stdout', result.stdout), ('probe_stderr', result.stderr),
                       ('child_returncode', result.returncode)]:
        record_property(key, value)
    rows = [json.loads(line.removeprefix('FORM_EVIDENCE=')) for line in result.stdout.splitlines()
            if line.startswith('FORM_EVIDENCE=')]
    assert len(rows) == 1, result.stdout + result.stderr
    data = rows[0]
    assert data['isolated'] == 1 and data['no_bytecode'] and data['blocked'] == []
    assert data['source_path'] == str(parent / 'web/form.py')
    return result, data


FLAGS = r'''
import hashlib
import importlib
module = importlib.import_module('web.form')
def report(**data):
    print('FORM_EVIDENCE=' + json.dumps(dict(
        isolated=sys.flags.isolated, no_bytecode=sys.dont_write_bytecode,
        blocked=blocked, source_path=module.__file__,
        source_sha256=hashlib.sha256(Path(module.__file__).read_bytes()).hexdigest(), **data)))
'''


def test_actual_doctests_preserve_html_and_match_repr(tmp_path, record_property):
    result, data = child(FLAGS + r'''
import ast
import doctest
cases = [t for t in doctest.DocTestFinder().find(module) if t.examples]
rows = []
for case in cases:
    for ordinal, e in enumerate(case.examples):
        want = e.want
        if want.startswith(("u'<", "'<")):
            want = ast.literal_eval(want)
        rows.append(dict(name=case.name, ordinal=ordinal, source=e.source, want=want,
                         exc_msg=e.exc_msg, options=e.options))
# Pin all identities, preparatory sources, exceptions and options. Only the
# display of the 39 HTML string wants is canonicalized to its exact value;
# the actual runner below still uses the unmodified default output checker.
assert hashlib.sha256(json.dumps(rows, sort_keys=True).encode()).hexdigest() == '9c084d2220596e5f45262b6a1696c673b0493ad9071c48e7ec09b0cd66d7afd0'
observed = []
class Capture(doctest.DocTestRunner):
    def record(self, test, example, got):
        if example.want.startswith(("u'<", "'<")):
            expected = ast.literal_eval(example.want)
            actual = ast.literal_eval(got)
            assert type(actual) is str and actual.encode('utf-8') == expected.encode('utf-8')
        observed.append(dict(name=test.name, ordinal=test.examples.index(example), got=got))
    def report_success(self, out, test, example, got):
        self.record(test, example, got)
        super().report_success(out, test, example, got)
    def report_failure(self, out, test, example, got):
        self.record(test, example, got)
        super().report_failure(out, test, example, got)
runner = Capture()
assert runner.optionflags == 0 and type(runner._checker) is doctest.OutputChecker
for case in cases:
    runner.run(case)
report(cases=[t.name for t in cases], attempted=runner.tries, failed=runner.failures,
       observations=observed)
''', tmp_path, record_property)
    assert result.returncode == 0, result.stdout + result.stderr
    assert len(data['cases']) == len(set(data['cases'])) == 22
    assert data['attempted'] == len(data['observations']) == 45
    assert data['failed'] == 0, result.stdout


def module_cli(tmp_path, record_property, source_parent=None, arguments=()):
    """Guard-first runpy module entry, not literal shell -m; real doctest runner."""
    return child(FLAGS + r'''
import atexit
import doctest
import runpy
@atexit.register
def cli_report():
    runner = doctest.master
    report(attempted=runner.tries if runner else 0, failed=runner.failures if runner else 0,
           cases={name: list(stats) for name, stats in runner._stats.items() if stats[1]} if runner else {})
''' + '\nsys.argv = ' + repr(['web.form', *arguments]) +
        "\nrunpy.run_module('web.form', run_name='__main__', alter_sys=True)\n",
        tmp_path, record_property, source_parent)


def copy_package(tmp_path):
    package = tmp_path / 'source/web'
    package.mkdir(parents=True)
    manifest = {}
    for source in sorted(WEB_ROOT.glob('*.py')):
        assert not source.is_symlink()
        raw = source.read_bytes()
        (package / source.name).write_bytes(raw)
        manifest[source.name] = hashlib.sha256(raw).hexdigest()
    return package, manifest


def check_run(data, failures):
    assert (data['attempted'], data['failed'], len(data['cases'])) == (45, failures, 22)
    assert sum(stats[1] for stats in data['cases'].values()) == 45
    assert sum(stats[0] for stats in data['cases'].values()) == failures
    assert all(len(stats) < 3 or stats[2] == 0 for stats in data['cases'].values())


WRONG_OLD = b'    \'<button id="save" name="save">save</button>\'\n'
WRONG_NEW = b'    \'<button id="save" name="save">WRONG EXPECTED CONTROL</button>\'\n'


@pytest.mark.parametrize('arguments', [(), ('Form',)], ids=['noargs', 'ignored-selector'])
def test_cli_real_failure_then_exact_restore(arguments, tmp_path, record_property):
    package, manifest = copy_package(tmp_path)
    path = package / 'form.py'
    original = path.read_bytes()
    positive, good = module_cli(tmp_path, lambda k, v: record_property('positive_' + k, v),
                                package.parent, arguments)
    check_run(good, 0)
    assert good['source_sha256'] == manifest['form.py']
    assert positive.returncode == 0, positive.stdout + positive.stderr
    assert original.count(WRONG_OLD) == 1 and WRONG_NEW not in original
    fixture = original.replace(WRONG_OLD, WRONG_NEW)
    assert fixture.replace(WRONG_NEW, WRONG_OLD) == original
    record_property('fixture_manifest', json.dumps(manifest, sort_keys=True))
    record_property('fixture_change', json.dumps(dict(old=WRONG_OLD.decode(), new=WRONG_NEW.decode(),
                                                    negative_sha256=hashlib.sha256(fixture).hexdigest())))
    path.write_bytes(fixture)
    try:
        negative, bad = module_cli(tmp_path, lambda k, v: record_property('negative_' + k, v),
                                   package.parent, arguments)
        check_run(bad, 1)
        assert bad['source_sha256'] == hashlib.sha256(fixture).hexdigest()
        assert {k: v[1] for k, v in good['cases'].items()} == {k: v[1] for k, v in bad['cases'].items()}
        assert bad['cases']['__main__.Button'][:2] == [1, 2]
        assert 'Expected:' in negative.stdout and 'WRONG EXPECTED CONTROL' in negative.stdout
        assert negative.returncode == 1, negative.stdout + negative.stderr
    finally:
        path.write_bytes(original)
    restored, restored_data = module_cli(tmp_path, lambda k, v: record_property('restored_' + k, v),
                                         package.parent, arguments)
    check_run(restored_data, 0)
    assert restored_data == good
    assert restored.returncode == 0, restored.stdout + restored.stderr
    assert {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in package.glob('*.py')} == manifest


@pytest.mark.parametrize('arguments', [(), ('Form',)], ids=['noargs', 'ignored-selector'])
def test_repository_cli_executes_all_examples(arguments, tmp_path, record_property):
    result, data = module_cli(tmp_path, record_property, arguments=arguments)
    check_run(data, 0)
    assert data['source_sha256'] == hashlib.sha256((WEB_ROOT / 'form.py').read_bytes()).hexdigest()
    assert result.returncode == 0, result.stdout + result.stderr
    # Preserve the real preimport warning rather than hiding module-entry stderr.
    assert "RuntimeWarning: 'web.form' found in sys.modules" in result.stderr


def test_unicode_escaping_html_and_validation_characterization(tmp_path, record_property):
    # This already passed on the original runtime; it is not a runtime repair.
    result, data = child(FLAGS + r'''
value = 'žluť<&"\''
escaped = 'žluť&lt;&amp;&quot;&#39;'
textbox = module.Textbox('field', value=value, title=value, class_='control')
assert textbox.render() == ('<input class="control" id="field" name="field" title="' + escaped
                            + '" type="text" value="' + escaped + '"/>')
assert textbox.value == value
textarea = module.Textarea('field', value=value)
assert textarea.render() == '<textarea id="field" name="field">' + escaped + '</textarea>'
dropdown = module.Dropdown('field', [(value, value)], value=value)
assert dropdown.render() == ('<select id="field" name="field">\n  <option selected="selected" value="'
                             + escaped + '">' + escaped + '</option>\n</select>\n')
grouped = module.GroupedDropdown('field', [(value, [(value, value)])], value=value)
assert grouped.render() == ('<select id="field" name="field">\n  <optgroup label="' + escaped
                            + '">\n    <option selected="selected" value="' + escaped + '">'
                            + escaped + '</option>\n  </optgroup>\n</select>\n')
form = module.Form(module.Textbox('field', module.notnull, value=value, description=value))
assert form.render() == ('<table>\n    <tr><th><label for="field">' + escaped
                         + '</label></th><td><input id="field" name="field" type="text" value="'
                         + escaped + '"/></td></tr>\n</table>')
assert form.render_css() == ('<label for="field">' + escaped
                             + '</label><input id="field" name="field" type="text" value="'
                             + escaped + '"/>\n')
assert form.validates({'field': value}) and form.d.field == value
assert not form.validates({'field': ''}) and form.note == 'Required'
assert form.rendernote(value) == '<strong class="wrong">' + escaped + '</strong>'
report(characterization=True, values=[textbox.render(), textarea.render(), dropdown.render(),
                                     grouped.render(), form.render(), form.render_css(), form.rendernote(value)])
''', tmp_path, record_property)
    assert result.returncode == 0, result.stdout + result.stderr
    assert data['characterization'] is True and len(data['values']) == 7
