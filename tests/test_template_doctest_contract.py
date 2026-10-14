"""Python 3 doctest contracts with application-side date formatting.

Real runners in fresh -I -B children; Python guards are not an OS sandbox.
"""
from .test_template_security_contract import probe


def test_python_lookahead_doctest_matches_real_parser(tmp_path, record_property):
    probe('''
        import doctest
        import importlib
        module = importlib.import_module('web.template')
        case = next(t for t in doctest.DocTestFinder().find(module)
                    if t.name == 'web.template.Parser.python_lookahead')
        assert len(case.examples) == 4
        runner = doctest.DocTestRunner()
        result = runner.run(case)
        assert (result.failed, result.attempted) == (0, 4)
    ''', tmp_path, record_property)


def test_doctest_helper_repr_is_a_python_string_literal(tmp_path, record_property):
    probe(r'''
        import doctest
        import importlib
        module = importlib.import_module('web.template')
        case = next(t for t in doctest.DocTestFinder().find(module)
                    if t.name == 'web.template.test')
        assert len(case.examples) == 66
        namespace = case.globs.copy()
        for example in case.examples[:2]:
            exec(compile(example.source, '<actual doctest helper>', 'exec'), namespace)
        t = namespace['t']
        assert repr(t('1')()) == "'1\\n'"
        assert repr(t('$def with (a)\n$a')(u'\u203d')) == "'‽\\n'"
        result = t('$var title: hello\nbody')()
        assert result.title == 'hello' and str(result.t) == 'body\n'
    ''', tmp_path, record_property)


RUN_DOCTESTS = r'''
import doctest
import importlib
import io
module = importlib.import_module('web.template')
cases = [t for t in doctest.DocTestFinder().find(module) if t.examples]
assert len(cases) == 18 and sum(len(t.examples) for t in cases) == 124
failures = []
class Capture(doctest.DocTestRunner):
    def report_failure(self, out, test, example, got):
        failures.append((test.name, test.examples.index(example), example, got))
        super().report_failure(out, test, example, got)
    def report_unexpected_exception(self, out, test, example, exc_info):
        failures.append((test.name, test.examples.index(example), example, repr(exc_info[1])))
        super().report_unexpected_exception(out, test, example, exc_info)
runner = Capture()
output = io.StringIO()
for case in cases:
    runner.run(case, out=output.write)
assert runner.tries == 124
print(output.getvalue())
'''


def test_python3_repr_expectations_match_actual_results(tmp_path, record_property):
    # Exception wording and the date example have separate contracts.
    probe(RUN_DOCTESTS + r'''
remaining_repr = [(name, ordinal, e.want, got) for name, ordinal, e, got in failures
                  if e.exc_msg is None and not (name == 'web.template.test' and ordinal == 65)]
assert remaining_repr == [], remaining_repr
''', tmp_path, record_property)


def test_doctest_exception_expectations_match_python3(tmp_path, record_property):
    probe(RUN_DOCTESTS + r'''
expected_exceptions = [e for case in cases for e in case.examples if e.exc_msg]
assert len(expected_exceptions) == 4
assert all(e.options == {} for e in expected_exceptions)
wrong_exceptions = [(name, ordinal, e.exc_msg, got) for name, ordinal, e, got in failures if e.exc_msg]
assert wrong_exceptions == [], wrong_exceptions
''', tmp_path, record_property)


def test_dollar_escape_example_compiles_without_warning(tmp_path, record_property):
    probe(r'''
        import ast
        import doctest
        import importlib
        import warnings
        module = importlib.import_module('web.template')
        case = next(t for t in doctest.DocTestFinder().find(module)
                    if t.name == 'web.template.test')
        example = case.examples[44]
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter('always')
            parsed = ast.parse(example.source)
        assert caught == [], [str(w.message) for w in caught]
        literal = parsed.body[0].value.func.args[0].value
        assert literal == "Stop, \\$money isn't evaluated."
        assert str(Template(literal)()) == "Stop, $money isn't evaluated.\n"
        assert example.options == {}
    ''', tmp_path, record_property)


def module_cli(tmp_path, record_property, *, source_parent=None, arguments=('-v',)):
    """Execute the real __main__ via runpy after the pre-import offline guard.

    This is an isolated module-entry subprocess, not a literal shell -m recipe.
    Neither doctest.testmod nor its result is replaced.
    """
    import json
    import os
    import subprocess
    import sys
    from .test_template_security_contract import BOOTSTRAP, WEB_ROOT

    source_parent = WEB_ROOT.parent if source_parent is None else source_parent
    program = BOOTSTRAP + r'''
import atexit
import doctest
import hashlib
import runpy
@atexit.register
def cli_evidence():
    runner = doctest.master
    print('CLI_EVIDENCE=' + json.dumps({
        'isolated': sys.flags.isolated, 'no_bytecode': sys.dont_write_bytecode,
        'web_path': web.__file__, 'blocked': blocked,
        'source_sha256': hashlib.sha256((Path(web.__file__).parent / 'template.py').read_bytes()).hexdigest(),
        'attempted': runner.tries if runner else 0,
        'failed': runner.failures if runner else 0,
        'cases': {name: list(stats) for name, stats in runner._stats.items() if stats[1]} if runner else {},
    }))
''' + '\nsys.argv = ' + repr(['web.template', *arguments]) + "\nrunpy.run_module('web.template', run_name='__main__', alter_sys=True)\n"
    env = {'PATH': os.defpath, 'HOME': str(tmp_path), 'TMPDIR': str(tmp_path),
           'XDG_CACHE_HOME': str(tmp_path), 'XDG_DATA_HOME': str(tmp_path),
           'XDG_CONFIG_HOME': str(tmp_path), 'PYTHON_DOTENV_DISABLED': '1', 'LC_ALL': 'C'}
    argv = [sys.executable, '-I', '-B', '-c', program, str(source_parent)]
    result = subprocess.run(argv, cwd=tmp_path, env=env, capture_output=True, text=True, timeout=30)
    record_property('child_argv', json.dumps(argv))
    record_property('child_environment', json.dumps(env))
    record_property('probe_stdout', result.stdout)
    record_property('probe_stderr', result.stderr)
    record_property('child_returncode', result.returncode)
    rows = [json.loads(line.removeprefix('CLI_EVIDENCE=')) for line in result.stdout.splitlines()
            if line.startswith('CLI_EVIDENCE=')]
    assert len(rows) == 1, result.stdout + result.stderr
    data = rows[0]
    assert data['isolated'] == 1 and data['no_bytecode'] and data['blocked'] == []
    assert data['web_path'] == str(source_parent / 'web/__init__.py')
    assert 'SyntaxWarning' not in result.stderr
    return result, data


def test_module_cli_propagates_real_doctest_failure(tmp_path, record_property):
    # Historical ID retained: repository doctests now pass; the owned fault
    # control below still proves real failure propagation without mocking.
    result, data = module_cli(tmp_path, record_property)
    assert (data['failed'], data['attempted'], len(data['cases'])) == (0, 124, 18)
    assert data['cases']['__main__.test'][:2] == [0, 66]
    assert all(stats[0] == 0 and (len(stats) < 3 or stats[2] == 0) for stats in data['cases'].values())
    assert "KeyError: '__import__'" not in result.stdout
    assert '124 passed.\nTest passed.' in result.stdout
    assert result.returncode == 0, result.stdout + result.stderr


def test_module_cli_real_success_and_restored_failure_control(tmp_path, record_property):
    """Real success → one owned wrong expectation → exact restored success.

    Historical ID retained. The negative control is an output mismatch, not a
    reintroduction of unsupported runtime strftime or a mocked doctest result.
    """
    import hashlib
    import json
    from .test_template_security_contract import WEB_ROOT

    exported = tmp_path / 'source'
    package = exported / 'web'
    package.mkdir(parents=True)
    manifest = {}
    for source in sorted(WEB_ROOT.glob('*.py')):
        assert not source.is_symlink()
        raw = source.read_bytes()
        (package / source.name).write_bytes(raw)
        manifest[source.name] = hashlib.sha256(raw).hexdigest()
    path = package / 'template.py'
    original = path.read_bytes()
    positive, good = module_cli(tmp_path, lambda k, v: record_property('positive_' + k, v),
                                source_parent=exported)
    assert good['source_sha256'] == manifest['template.py']
    assert (good['failed'], good['attempted'], len(good['cases'])) == (0, 124, 18)
    assert all(stats[0] == 0 and (len(stats) < 3 or stats[2] == 0) for stats in good['cases'].values())
    assert '124 passed.\nTest passed.' in positive.stdout
    assert positive.returncode == 0, positive.stdout + positive.stderr
    old = b"        '01 2009\\n'\n"
    new = b"        'WRONG DATE CONTROL\\n'\n"
    assert original.count(old) == 1 and new not in original
    fixture = original.replace(old, new)
    assert fixture.replace(new, old) == original
    path.write_bytes(fixture)
    try:
        negative, bad = module_cli(tmp_path, lambda k, v: record_property('negative_' + k, v),
                                   source_parent=exported)
        assert bad['source_sha256'] == hashlib.sha256(fixture).hexdigest()
        assert (bad['failed'], bad['attempted'], len(bad['cases'])) == (1, 124, 18)
        assert {k: v[1] for k, v in good['cases'].items()} == {k: v[1] for k, v in bad['cases'].items()}
        assert bad['cases']['__main__.test'][:2] == [1, 66]
        assert 'Expected:' in negative.stdout and 'WRONG DATE CONTROL' in negative.stdout
        assert "KeyError: '__import__'" not in negative.stdout
        assert '123 passed and 1 failed.' in negative.stdout
        assert negative.returncode == 1, negative.stdout + negative.stderr
    finally:
        path.write_bytes(original)
    restored, restored_data = module_cli(tmp_path, lambda k, v: record_property('restored_' + k, v),
                                         source_parent=exported)
    assert restored_data['source_sha256'] == manifest['template.py']
    assert restored_data['cases'] == good['cases']
    assert (restored_data['failed'], restored_data['attempted']) == (0, 124)
    assert restored.returncode == 0 and '124 passed.\nTest passed.' in restored.stdout
    assert {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in package.glob('*.py')} == manifest
    record_property('fixture_source_manifest', json.dumps(manifest, sort_keys=True))
    record_property('fixture_exact_change', json.dumps({'old': old.decode(), 'new': new.decode(),
                                                       'negative_sha256': hashlib.sha256(fixture).hexdigest()}))


def test_module_compile_owned_templates_unchanged_path(tmp_path, record_property):
    import hashlib
    from .test_template_security_contract import WEB_ROOT

    templates = tmp_path / 'templates'
    templates.mkdir()
    (templates / 'greeting.txt').write_bytes(b'\xef\xbb\xbf$def with (name)\nHello $name')
    (templates / 'page.html').write_text('$def with (name)\n<p>$name</p>', encoding='utf-8')
    result, data = module_cli(tmp_path, record_property, arguments=('--compile', str(templates)))
    assert result.returncode == 0, result.stdout + result.stderr
    assert data['attempted'] == data['failed'] == 0 and data['cases'] == {}
    assert data['source_sha256'] == hashlib.sha256((WEB_ROOT / 'template.py').read_bytes()).hexdigest()
    generated = templates / '__init__.py'
    assert generated.is_file() and generated.stat().st_size > 0
    probe(r'''
        import importlib.util
        path = Path.cwd() / 'templates/__init__.py'
        spec = importlib.util.spec_from_file_location('owned_compiled', path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        assert str(module.greeting('Ada')) == 'Hello Ada\n'
        assert str(module.page('<Ada>')) == '<p>&lt;Ada&gt;</p>\n'
    ''', tmp_path, lambda k, v: record_property('compiled_' + k, v))


def test_module_compile_keeps_real_syntax_failure(tmp_path, record_property):
    templates = tmp_path / 'bad_templates'
    templates.mkdir()
    (templates / 'bad.txt').write_text('$def with (\nhello', encoding='utf-8')
    result, data = module_cli(tmp_path, record_property, arguments=('--compile', str(templates)))
    assert result.returncode == 1 and 'SyntaxError' in result.stderr
    assert data['attempted'] == data['failed'] == 0 and data['cases'] == {}


def test_remaining_strftime_failure_keeps_desired_output(tmp_path, record_property):
    # The historical ID now checks the supported example plus the separately
    # unsupported direct call, rather than retaining a failing published recipe.
    probe(RUN_DOCTESTS + r'''
assert failures == [] and runner.failures == 0
case = next(t for t in cases if t.name == 'web.template.test')
example = case.examples[65]
assert example.want == "'01 2009\\n'\n"
assert example.exc_msg is None and example.options == {}
import datetime
error = raises(KeyError, lambda: Template("$def with (date)\n$date.strftime('%m %Y')")(
    datetime.datetime(2009, 1, 1)))
assert error.args == ('__import__',)
assert '__import__' not in module.TEMPLATE_BUILTINS
assert module.test() is None
assert blocked == []
''', tmp_path, record_property)
