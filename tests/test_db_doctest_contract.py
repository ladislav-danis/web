"""DB doctest values and real CLI policy; offline guards are not an OS sandbox."""
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
    rows = [json.loads(line.removeprefix('DB_EVIDENCE=')) for line in result.stdout.splitlines()
            if line.startswith('DB_EVIDENCE=')]
    assert len(rows) == 1, result.stdout + result.stderr
    data = rows[0]
    assert data['isolated'] == 1 and data['no_bytecode'] and data['blocked'] == []
    assert data['source_path'] == str(parent / 'web/db.py')
    return result, data


FLAGS = r'''
import hashlib
import importlib
module = importlib.import_module('web.db')
def report(**data):
    print('DB_EVIDENCE=' + json.dumps(dict(
        isolated=sys.flags.isolated, no_bytecode=sys.dont_write_bytecode,
        blocked=blocked, source_path=module.__file__,
        source_sha256=hashlib.sha256(Path(module.__file__).read_bytes()).hexdigest(), **data)))
'''


def test_actual_doctests_preserve_values_and_match_repr(tmp_path, record_property):
    result, data = child(FLAGS + r'''
import ast
import doctest
cases = [t for t in doctest.DocTestFinder().find(module) if t.examples]
rows = []
for case in cases:
    for ordinal, e in enumerate(case.examples):
        want = e.want
        if case.name == 'web.db.dburl2dict' and ordinal in (5, 6):
            want = ast.literal_eval(want)
            url = ast.literal_eval(ast.parse(e.source).body[0].value.args[0])
            assert module.dburl2dict(url) == want
        rows.append(dict(name=case.name, ordinal=ordinal, source=e.source, want=want,
                         exc_msg=e.exc_msg, options=e.options))
# Exact sources, values, exceptions, options and case/ordinal identities; only
# the two SQLite want dictionaries are canonicalized for key-order comparison.
assert hashlib.sha256(json.dumps(rows, sort_keys=True).encode()).hexdigest() == '6642cafa7658369944b1f4c85f02dea9ec646b2f76bd1ab3ea6e638ea5f17905'
runner = doctest.DocTestRunner()
for case in cases:
    runner.run(case)
report(cases=[t.name for t in cases], attempted=runner.tries, failed=runner.failures)
''', tmp_path, record_property)
    assert result.returncode == 0, result.stdout + result.stderr
    assert len(data['cases']) == len(set(data['cases'])) == 23
    assert data['attempted'] == 83
    assert data['failed'] == 0, result.stdout


def module_cli(tmp_path, record_property, source_parent=None, arguments=()):
    """Guard-first runpy entry, not literal shell -m; no mocked doctest runner."""
    return child(FLAGS + r'''
import atexit
import doctest
import runpy
calls = []
def observe(frame, event, arg):
    if (event == 'call' and frame.f_globals.get('__name__') == '__main__'
            and frame.f_code.co_name in ('test_parser', 'test_safeeval')):
        assert frame.f_code.co_filename == module.__file__
        calls.append(dict(name=frame.f_code.co_name,
                          attempted=doctest.master.tries, failed=doctest.master.failures))
sys.setprofile(observe)
@atexit.register
def cli_report():
    sys.setprofile(None)
    runner = doctest.master
    report(attempted=runner.tries if runner else 0, failed=runner.failures if runner else 0,
           cases={name: list(stats) for name, stats in runner._stats.items() if stats[1]} if runner else {},
           calls=calls)
''' + '\nsys.argv = ' + repr(['web.db', *arguments]) +
        "\nrunpy.run_module('web.db', run_name='__main__', alter_sys=True)\n",
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


def check_run(data, failures, helpers=('test_parser', 'test_safeeval')):
    assert (data['attempted'], data['failed'], len(data['cases'])) == (83, failures, 23)
    assert sum(stats[1] for stats in data['cases'].values()) == 83
    assert sum(stats[0] for stats in data['cases'].values()) == failures
    assert all(len(stats) < 3 or stats[2] == 0 for stats in data['cases'].values())
    assert data['calls'] == [dict(name=name, attempted=83, failed=failures) for name in helpers]


WRONG_OLD = b"        {'dbn': 'sqlite', 'db': 'mygreatdb.db'}\n"
WRONG_NEW = b"        {'dbn': 'sqlite', 'db': 'WRONG EXPECTED CONTROL'}\n"


@pytest.mark.parametrize('arguments', [(), ('TestDatabase',)], ids=['noargs', 'ignored-selector'])
def test_cli_real_failure_then_exact_restore(arguments, tmp_path, record_property):
    package, manifest = copy_package(tmp_path)
    path = package / 'db.py'
    original = path.read_bytes()
    positive, good = module_cli(tmp_path, lambda k, v: record_property('positive_' + k, v),
                                package.parent, arguments)
    check_run(good, 0)
    assert good['source_sha256'] == manifest['db.py']
    assert positive.returncode == 0, positive.stdout + positive.stderr
    assert original.count(WRONG_OLD) == 1 and WRONG_NEW not in original
    fixture = original.replace(WRONG_OLD, WRONG_NEW)
    assert fixture.replace(WRONG_NEW, WRONG_OLD) == original
    path.write_bytes(fixture)
    try:
        negative, bad = module_cli(tmp_path, lambda k, v: record_property('negative_' + k, v),
                                   package.parent, arguments)
        check_run(bad, 1)
        assert bad['source_sha256'] == hashlib.sha256(fixture).hexdigest()
        assert {k: v[1] for k, v in good['cases'].items()} == {k: v[1] for k, v in bad['cases'].items()}
        assert bad['cases']['__main__.dburl2dict'][:2] == [1, 7]
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
    record_property('fixture_manifest', json.dumps(manifest, sort_keys=True))
    record_property('fixture_change', json.dumps(dict(old=WRONG_OLD.decode(), new=WRONG_NEW.decode(),
                                                    negative_sha256=hashlib.sha256(fixture).hexdigest())))


@pytest.mark.parametrize('arguments', [(), ('TestDatabase',)], ids=['noargs', 'ignored-selector'])
def test_repository_cli_executes_all_examples(arguments, tmp_path, record_property):
    result, data = module_cli(tmp_path, record_property, arguments=arguments)
    check_run(data, 0)
    assert data['source_sha256'] == hashlib.sha256((WEB_ROOT / 'db.py').read_bytes()).hexdigest()
    assert result.returncode == 0, result.stdout + result.stderr
    # Preserve the real duplicate-import warning; it is not a doctest failure.
    assert "RuntimeWarning: 'web.db' found in sys.modules" in result.stderr


@pytest.mark.parametrize('helper', ['test_parser', 'test_safeeval'])
@pytest.mark.parametrize('failed_doctest', [False, True], ids=['passing-doctests', 'failing-doctest'])
def test_real_helper_assertion_propagates(helper, failed_doctest, tmp_path, record_property):
    package, manifest = copy_package(tmp_path)
    path = package / 'db.py'
    original = path.read_bytes()
    old, new = {
        'test_parser': (b'f("Hello", [_Node("text", "Hello")])',
                        b'f("Hello", [_Node("text", "WRONG HELPER CONTROL")])'),
        'test_safeeval': (b'assert f("WHERE id=$id", {"id": 1}).items == ["WHERE id=", sqlparam(1)]',
                          b'assert f("WHERE id=$id", {"id": 1}).items == ["WHERE id=", sqlparam(2)]'),
    }[helper]
    assert original.count(old) == 1 and new not in original
    fixture = original.replace(old, new)
    if failed_doctest:
        assert fixture.count(WRONG_OLD) == 1
        fixture = fixture.replace(WRONG_OLD, WRONG_NEW)
    path.write_bytes(fixture)
    try:
        result, data = module_cli(tmp_path, record_property, package.parent)
        reached = ('test_parser',) if helper == 'test_parser' else ('test_parser', 'test_safeeval')
        check_run(data, int(failed_doctest), reached)
        assert data['source_sha256'] == hashlib.sha256(fixture).hexdigest()
        assert result.returncode == 1, result.stdout + result.stderr
        assert 'Traceback (most recent call last)' in result.stderr
        assert 'AssertionError' in result.stderr and 'in ' + helper in result.stderr
    finally:
        path.write_bytes(original)
    assert {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in package.glob('*.py')} == manifest
    record_property('fixture_manifest', json.dumps(manifest, sort_keys=True))
    record_property('helper_change', json.dumps(dict(helper=helper, old=old.decode(), new=new.decode(),
                                                   doctest_fault=failed_doctest,
                                                   fixture_sha256=hashlib.sha256(fixture).hexdigest())))


def test_url_unicode_and_encoded_values_are_unchanged(tmp_path, record_property):
    result, data = child(FLAGS + r'''
values = []
for url in ['sqlite:///žluťoučký.db', 'sqlite:///%C5%BElu%C5%A5ou%C4%8Dk%C3%BD.db']:
    value = module.dburl2dict(url)
    assert value == {'dbn': 'sqlite', 'db': 'žluťoučký.db'}
    values.append(value)
report(values=values)
''', tmp_path, record_property)
    assert result.returncode == 0, result.stdout + result.stderr
    assert data['values'] == [{'dbn': 'sqlite', 'db': 'žluťoučký.db'}] * 2
