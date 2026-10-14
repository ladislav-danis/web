"""Execute trusted local test-runner Markdown, never arbitrary input.

Real unittest/doctest execution, including failing controls. Python-level guards
are isolation, not an OS sandbox. Direct shell CLI uses a minimal environment
and a pre-import sitecustomize guard; -I -B is used for standalone fence probes.
"""
import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import textwrap

import pytest

from .test_template_security_contract import BOOTSTRAP, WEB_ROOT, fences, probe

DOC = WEB_ROOT / 'docs/test.md'
TRACE = r'''
import unittest
_executed = []
_results = []
_start = unittest.TestResult.startTest
_run = unittest.TextTestRunner.run
def traced_start(self, test):
    _executed.append(test.id())
    return _start(self, test)
def traced_run(self, suite):
    result = _run(self, suite)
    _results.append({'testsRun': result.testsRun, 'successful': result.wasSuccessful(),
                     'failures': len(result.failures), 'errors': len(result.errors)})
    return result
unittest.TestResult.startTest = traced_start
unittest.TextTestRunner.run = traced_run
import atexit
@atexit.register
def trace_report():
    print('RUNNER_EVIDENCE=' + json.dumps({'ids': _executed, 'results': _results}))
'''


def block(heading):
    matches = [b for b in fences(DOC.read_bytes()) if b[0] == heading]
    assert len(matches) == 1, (heading, len(matches))
    assert matches[0][4]
    return matches[0]


def sample_files(tmp_path):
    """Only file bytes explicitly documented as prerequisites, when present."""
    for heading, name in [('### Sample module', 'runner_sample.py'),
                          ('### Failing control', 'runner_failure.py')]:
        matches = [b for b in fences(DOC.read_bytes()) if b[0] == heading]
        if matches:
            assert len(matches) == 1 and matches[0][4]
            (tmp_path / name).write_bytes(matches[0][3])


def run_fence(heading, tmp_path, record_property, expected_exit=0):
    _, line, language, code, closed = block(heading)
    assert language == 'python' and closed
    sample_files(tmp_path)
    (tmp_path / 'fence.py').write_bytes(code)
    program = (BOOTSTRAP + TRACE + '\nsys.path.insert(0, str(Path.cwd()))\n'
               + "import runpy\nsys.argv = ['fence.py']\nrunpy.run_path('fence.py', run_name='__main__')\n")
    command = [sys.executable, '-I', '-B', '-c', program, str(WEB_ROOT.parent)]
    env = {'PATH': os.defpath, 'HOME': str(tmp_path), 'TMPDIR': str(tmp_path),
           'PYTHON_DOTENV_DISABLED': '1', 'LC_ALL': 'C'}
    result = subprocess.run(command, cwd=tmp_path, env=env, text=True,
                            capture_output=True, timeout=30)
    record_property('fence_sha256', hashlib.sha256(code).hexdigest())
    record_property('markdown_line', line)
    record_property('probe_stdout', result.stdout)
    record_property('probe_stderr', result.stderr)
    record_property('child_returncode', result.returncode)
    assert result.returncode == expected_exit, result.stdout + result.stderr
    traces = [s.removeprefix('RUNNER_EVIDENCE=') for s in result.stdout.splitlines()
              if s.startswith('RUNNER_EVIDENCE=')]
    assert len(traces) == 1
    return json.loads(traces[0])


def test_wbtest01_documented_specific_tests_are_nonzero(tmp_path, record_property):
    evidence = run_fence('### Running Specific Tests', tmp_path, record_property)
    assert evidence['results'] == [{'testsRun': 2, 'successful': True, 'failures': 0, 'errors': 0}]
    assert evidence['ids'] == ['runner_sample.SampleTests.test_add',
                               'runner_sample.SampleTests.test_upper']


def run_cli(heading, index, tmp_path, record_property):
    _, line, language, code, closed = block(heading)
    assert closed and language == 'bash'
    commands = [s for s in code.decode().splitlines() if s.strip() and not s.startswith('#')]
    command = commands[index]
    sample_files(tmp_path)
    guard = tmp_path / 'guard'
    guard.mkdir()
    # -I would suppress this sitecustomize: direct CLI instead has a fresh,
    # minimal environment and guard-first PYTHONPATH. No user's config is read.
    bootstrap = BOOTSTRAP.replace('sys.argv[1]', repr(str(WEB_ROOT.parent)))
    (guard / 'sitecustomize.py').write_text(bootstrap + TRACE + "\nprint('CLI_GUARD_READY', flush=True)\n")
    # Preserve the venv executable's location: a new symlink outside that venv
    # loses pyvenv.cfg discovery and silently selects the system site-packages.
    env = {'PATH': str(Path(sys.executable).parent), 'HOME': str(tmp_path), 'TMPDIR': str(tmp_path),
           'PYTHONPATH': str(guard) + os.pathsep + str(WEB_ROOT.parent),
           'PYTHONDONTWRITEBYTECODE': '1', 'PYTHON_DOTENV_DISABLED': '1', 'LC_ALL': 'C'}
    result = subprocess.run(['/bin/sh', '-c', command], cwd=tmp_path, env=env,
                            text=True, capture_output=True, timeout=30)
    record_property('fence_sha256', hashlib.sha256(code).hexdigest())
    record_property('markdown_line', line)
    record_property('shell_command', command)
    record_property('shell_argv', json.dumps(['/bin/sh', '-c', command]))
    record_property('documented_python_argv', json.dumps(shlex.split(command)))
    record_property('child_environment', json.dumps(env))
    record_property('probe_stdout', result.stdout)
    record_property('probe_stderr', result.stderr)
    record_property('child_returncode', result.returncode)
    assert result.stdout.count('CLI_GUARD_READY') == 1, result.stdout + result.stderr
    assert 'Error in sitecustomize' not in result.stderr
    traces = [s.removeprefix('RUNNER_EVIDENCE=') for s in result.stdout.splitlines()
              if s.startswith('RUNNER_EVIDENCE=')]
    assert len(traces) == 1
    return result, json.loads(traces[0])


def test_wbtest02_documented_cli_selects_real_class(tmp_path, record_property):
    result, evidence = run_cli('### Command Line Usage', 1, tmp_path, record_property)
    assert result.returncode == 0, result.stdout + result.stderr
    assert evidence['ids'] == ['__main__.SampleTests.test_add', '__main__.SampleTests.test_upper']
    assert evidence['results'] == [{'testsRun': 2, 'successful': True, 'failures': 0, 'errors': 0}]


@pytest.mark.parametrize('heading,ids,exitcode', [
    ('### Sample module', ['__main__.SampleTests.test_add', '__main__.SampleTests.test_upper'], 0),
    ('### Using Doctests', ['runner_sample.double'], 0),
    ('### Custom Test Suite', ['runner_sample.SampleTests.test_add', 'runner_sample.SampleTests.test_upper', 'runner_sample.double'], 0),
    ('### Failing control', ['__main__.FailureTests.test_failure'], 1),
    ('### `load_modules(names)`', [], 0),
    ('### Inventory is not execution', [], 0),
])
def test_remaining_documented_python(heading, ids, exitcode, tmp_path, record_property):
    evidence = run_fence(heading, tmp_path, record_property, expected_exit=exitcode)
    assert evidence['ids'] == ids
    if ids:
        assert evidence['results'] == [{'testsRun': len(ids), 'successful': not exitcode,
                                        'failures': int(bool(exitcode)), 'errors': 0}]
    else:
        assert evidence['results'] == []


@pytest.mark.parametrize('index,methods', [(0, ['test_add', 'test_upper']), (2, ['test_add'])])
def test_documented_cli_default_and_method(index, methods, tmp_path, record_property):
    result, evidence = run_cli('### Command Line Usage', index, tmp_path, record_property)
    assert result.returncode == 0, result.stdout + result.stderr
    assert evidence['ids'] == ['__main__.SampleTests.' + m for m in methods]
    assert evidence['results'] == [{'testsRun': len(methods), 'successful': True, 'failures': 0, 'errors': 0}]


@pytest.mark.parametrize('index,expected_id,failures,errors', [
    (0, '__main__.FailureTests.test_failure', 1, 0),
    (1, 'unittest.loader._FailedTest.NoSuchClass', 0, 1),
])
def test_documented_cli_failure_and_invalid_selector(index, expected_id, failures, errors, tmp_path, record_property):
    result, evidence = run_cli('### Negative CLI controls', index, tmp_path, record_property)
    assert result.returncode == 1, result.stdout + result.stderr
    assert evidence['ids'] == [expected_id]
    assert evidence['results'] == [{'testsRun': 1, 'successful': False, 'failures': failures, 'errors': errors}]


def test_runtime_aliases_imports_and_loader_precedence(tmp_path, record_property):
    probe('''
        import types
        import unittest
        import web.test as t
        assert t.TestCase is unittest.TestCase and t.TestSuite is unittest.TestSuite
        assert [m.__name__ for m in t.load_modules(['web.db', 'web.template'])] == ['web.db', 'web.template']
        raises(ModuleNotFoundError, lambda: t.load_modules(['web16_nonexistent_module']))
        m = types.ModuleType('owned_contract_module')
        class Checks(t.TestCase):
            def test_first(self): self.assertEqual(1, 1)
            def test_second(self): self.assertTrue(True)
        m.Checks = Checks
        assert t.module_suite(m).countTestCases() == 2
        assert t.module_suite(m, ['Checks']).countTestCases() == 2
        result = t.runTests(t.module_suite(m, ['Checks.test_second']))
        assert result.testsRun == 1 and result.wasSuccessful()
        called = []
        def custom():
            called.append(True)
            return t.TestSuite([Checks('test_first')])
        m.suite = custom
        for names in (None, [], ()):
            assert t.module_suite(m, names).countTestCases() == 1
        assert len(called) == 3
        assert t.module_suite(m, ['Checks']).countTestCases() == 2
        assert len(called) == 3
        result = t.runTests(t.module_suite(m, ['Missing']))
        assert result.testsRun == 1 and len(result.errors) == 1 and not result.wasSuccessful()
        print('loader errors are results; runTests itself did not exit')
    ''', tmp_path, record_property)


@pytest.mark.parametrize('supplied', ['none', 'false', 'empty', 'truthy'])
def test_runtime_main_suite_truthiness_and_argv_policy(supplied, tmp_path, record_property):
    probe('''
        import types
        import web.test as t
        m = types.ModuleType('__main__')
        class Checks(t.TestCase):
            def test_first(self): self.assertTrue(True)
            def test_second(self): self.assertTrue(True)
        m.Checks = Checks
        sys.modules['__main__'] = m
        sys.argv = ['owned.py', '-v', 'Checks.test_second', '--not-an-option']
        supplied = ''' + repr(supplied) + '''
        selected = {'none': None, 'false': False, 'empty': t.TestSuite(), 'truthy': t.TestSuite([Checks('test_first')])}[supplied]
        seen = []
        original = t.runTests
        def observed(suite):
            def flatten(s):
                for case in s:
                    if isinstance(case, t.TestSuite): yield from flatten(case)
                    else: yield case.id()
            seen.extend(flatten(suite))
            return original(suite)
        t.runTests = observed
        error = raises(SystemExit, lambda: t.main(selected))
        assert error.code == 0
        assert len(seen) == (0 if supplied == 'empty' else 1)
        if seen:
            assert seen[0].endswith('test_first' if supplied == 'truthy' else 'test_second')
        sys.argv = ['owned.py', '--pattern', 'not_a_test']
        error = raises(SystemExit, t.main)
        assert error.code == 1 and seen[-1].endswith('not_a_test')
        print(json.dumps({'supplied': supplied, 'executed_selection_ids': seen}))
    ''', tmp_path, record_property)


def test_runtime_unit_vs_doctest_counts_and_failures(tmp_path, record_property):
    probe('''
        import doctest
        import types
        import web.test as t
        m = types.ModuleType('owned_doctest')
        m.__doc__ = '>>> 2 + 3\\n5\\n>>> 2 * 3\\n6\\n'
        sys.modules[m.__name__] = m
        assert t.suite([m.__name__]).countTestCases() == 0
        selected = t.doctest_suite([m.__name__])
        assert selected.countTestCases() == 1
        assert sum(len(d.examples) for d in doctest.DocTestFinder().find(m)) == 2
        result = t.runTests(selected)
        assert result.testsRun == 1 and result.wasSuccessful()
        m.__doc__ = '>>> 2 + 3\\n999\\n'
        result = t.runTests(t.doctest_suite([m.__name__]))
        assert result.testsRun == 1 and len(result.failures) == 1 and not result.wasSuccessful()
        print('deliberate failing doctest is a negative control, not a green doctest')
    ''', tmp_path, record_property)


def test_probe_guards_deny_application_env_db_network_and_process(tmp_path, record_property):
    probe('''
        import importlib
        import socket
        import sqlite3
        import subprocess
        for name in ('core', 'modules', 'dotenv'):
            raises(AssertionError, lambda: importlib.import_module(name))
        raises(AssertionError, lambda: Path('.env').read_text())
        raises(AssertionError, lambda: sqlite3.connect(':memory:'))
        raises(AssertionError, lambda: socket.getaddrinfo('example.invalid', 80))
        raises(AssertionError, lambda: subprocess.run([sys.executable, '-c', 'pass']))
        assert len(blocked) == 7
    ''', tmp_path, record_property)


def test_all_fences_have_an_execution_mode():
    blocks = fences(DOC.read_bytes())
    expected = {
        '### `load_modules(names)`': 'python', '### Sample module': 'python',
        '### Running Specific Tests': 'python', '### Using Doctests': 'python',
        '### Custom Test Suite': 'python', '### Failing control': 'python',
        '### Inventory is not execution': 'python',
        '### Command Line Usage': 'bash', '### Negative CLI controls': 'bash',
    }
    assert len(blocks) == len(expected)
    assert {heading: language for heading, _, language, _, _ in blocks} == expected
    assert all(closed for _, _, _, _, closed in blocks)


@pytest.mark.parametrize('name,cases,examples', [('web.db', 23, 83), ('web.template', 18, 124), ('web.form', 22, 45)])
def test_pinned_framework_doctests_are_failing_diagnostics(name, cases, examples, tmp_path, record_property):
    # Historical ID retained: template passes; db/form remain failing diagnostics.
    source = '''
        import doctest
        import importlib
        import web.test as t
        name, cases, examples = ''' + repr((name, cases, examples)) + '''
        module = importlib.import_module(name)
        assert t.suite([name]).countTestCases() == 0
        selected = t.doctest_suite([name])
        assert selected.countTestCases() == cases
        assert sum(len(d.examples) for d in doctest.DocTestFinder().find(module)) == examples
        result = t.runTests(selected)
        if name == 'web.template':
            assert result.testsRun == cases and not result.failures and not result.errors
            assert result.wasSuccessful()
        else:
            assert result.testsRun == cases and result.failures and not result.errors
            assert not result.wasSuccessful()
            assert len(result.failures) == {'web.db': 1, 'web.form': 21}[name]
        print(json.dumps({'module': name, 'executed_cases': result.testsRun,
                          'failed_case_ids': [case.id() for case, _ in result.failures],
                          'compiled_examples': examples, 'nested_doctests_passed': result.wasSuccessful()}))
        raise SystemExit(not result.wasSuccessful())
    '''
    result = subprocess.run([sys.executable, '-I', '-B', '-c', BOOTSTRAP + textwrap.dedent(source), str(WEB_ROOT.parent)],
                            cwd=tmp_path, env={'PATH': os.defpath, 'HOME': str(tmp_path), 'TMPDIR': str(tmp_path),
                                              'PYTHON_DOTENV_DISABLED': '1', 'LC_ALL': 'C'},
                            text=True, capture_output=True, timeout=30)
    record_property('probe_stdout', result.stdout)
    record_property('probe_stderr', result.stderr)
    record_property('child_returncode', result.returncode)
    assert result.returncode == (0 if name == 'web.template' else 1), result.stdout + result.stderr
    evidence = json.loads(result.stdout.splitlines()[-1])
    assert evidence['module'] == name and evidence['executed_cases'] == cases
    if name == 'web.template':
        assert evidence['failed_case_ids'] == [] and evidence['nested_doctests_passed'] is True
    else:
        assert evidence['failed_case_ids'] and evidence['nested_doctests_passed'] is False
        assert len(evidence['failed_case_ids']) == {'web.db': 1, 'web.form': 21}[name]
