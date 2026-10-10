"""Executable Python 3 documentation and real dictionary-iterator contracts.

Each probe uses a fresh interpreter and pre-import guards; these are Python-level
isolation, not an OS sandbox. No Python 2 interpreter is used or certified.
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
DOC = WEB_ROOT / "docs/py3helpers.md"
BOOTSTRAP = r'''
import importlib.abc
import json
from pathlib import Path
import sys

class NoApplication(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {'core', 'modules', 'dotenv'}:
            raise AssertionError('Framework probe imported ' + fullname)
sys.meta_path.insert(0, NoApplication())

def offline(event, args):
    if event.startswith('socket.') and event != 'socket.__new__':
        raise AssertionError('Framework probe attempted network: ' + event)
    if event in {'subprocess.Popen', 'os.system', 'os.posix_spawn'}:
        raise AssertionError('Framework probe attempted process: ' + event)
sys.addaudithook(offline)
sys.path.insert(0, sys.argv[1])
import web
from web import py3helpers
assert Path(web.__file__).resolve().parent == Path(sys.argv[1]) / 'web'
assert Path(py3helpers.__file__).resolve() == Path(sys.argv[1]) / 'web/py3helpers.py'
assert sys.version_info.major == 3
assert sys.dont_write_bytecode
'''


def probe(source, tmp_path, record_property):
    env = {"PATH": os.defpath, "PYTHON_DOTENV_DISABLED": "1",
           "HOME": str(tmp_path), "TMPDIR": str(tmp_path), "LC_ALL": "C"}
    result = subprocess.run(
        [sys.executable, "-I", "-B", "-c", BOOTSTRAP + "\n" + textwrap.dedent(source),
         str(WEB_ROOT.parent)], env=env, cwd=tmp_path,
        text=True, capture_output=True, timeout=30,
    )
    record_property("probe_stdout", result.stdout)
    record_property("probe_stderr", result.stderr)
    assert result.returncode == 0, result.stdout + result.stderr


def fences(raw):
    """Preserve raw code bytes and ignore code comments when finding headings."""
    heading, opened = "", None
    result = []
    for number, line in enumerate(raw.splitlines(keepends=True), 1):
        if opened is not None:
            if line.rstrip(b"\r\n") == b"```":
                result.append((heading, opened, b"".join(body)))
                opened = None
            else:
                body.append(line)
        elif line.startswith(b"```"):
            assert line.rstrip(b"\r\n") == b"```python", (number, line)
            opened, body = number, []
        elif line.startswith(b"#"):
            heading = line.decode("utf-8").strip()
    assert opened is None, "Unclosed Markdown fence"
    assert result, "No executable examples"
    return result


def execute_fences(selected, tmp_path, record_property, expected_output=None):
    assert selected
    record_property("markdown_sha256", hashlib.sha256(DOC.read_bytes()).hexdigest())
    payload = [(heading, line, code.decode("utf-8")) for heading, line, code in selected]
    probe('''
        import contextlib
        import hashlib
        import io
        examples = ''' + repr(payload) + '''
        expected_output = ''' + repr(expected_output) + '''
        results = []
        for heading, line, code in examples:
            namespace = {'__name__': '__main__'}
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                exec(compile(code, 'docs/py3helpers.md:' + str(line), 'exec'), namespace)
            if expected_output is not None:
                assert output.getvalue() == expected_output, output.getvalue()
            results.append({'heading': heading, 'line': line,
                            'sha256': hashlib.sha256(code.encode('utf-8')).hexdigest(),
                            'stdout': output.getvalue()})
        print(json.dumps(results))
    ''', tmp_path, record_property)


@pytest.mark.parametrize("name,expected", [
    ("iterkeys", "a\nb\n"), ("itervalues", "1\n2\n"), ("iteritems", "a 1\nb 2\n"),
])
def test_function_markdown_is_self_contained(name, expected, tmp_path, record_property):
    selected = [item for item in fences(DOC.read_bytes()) if item[0] == f"### `{name}(d)`"]
    assert len(selected) == 1
    execute_fences(selected, tmp_path, record_property, expected)


@pytest.mark.parametrize("method,expected", [
    ("keys", ["a", "b"]), ("values", [1, 2]), ("items", [("a", 1), ("b", 2)]),
])
def test_dictionary_views_are_repeatable_not_iterators(method, expected, tmp_path, record_property):
    probe('''
        data = {'a': 1, 'b': 2}
        view = getattr(data, ''' + repr(method) + ''')()
        expected = ''' + repr(expected) + '''
        assert list(view) == expected
        assert list(view) == expected
        assert iter(view) is not view
        try:
            next(view)
        except TypeError:
            pass
        else:
            raise AssertionError('A dictionary view is not an iterator')
        print(json.dumps({'method': ''' + repr(method) + ''', 'repeatable_view': True,
                          'next_view': 'TypeError'}))
    ''', tmp_path, record_property)


@pytest.mark.parametrize("name,expected", [
    ("iterkeys", ["a", "b"]), ("itervalues", [1, 2]), ("iteritems", [("a", 1), ("b", 2)]),
])
@pytest.mark.parametrize("empty", [False, True], ids=["populated", "empty"])
def test_real_helpers_consume_once_and_fresh_calls_are_independent(
        name, expected, empty, tmp_path, record_property):
    probe('''
        helper = getattr(py3helpers, ''' + repr(name) + ''')
        data = {} if ''' + repr(empty) + ''' else {'a': 1, 'b': 2}
        expected = [] if ''' + repr(empty) + ''' else ''' + repr(expected) + '''
        first, second = helper(data), helper(data)
        assert first is not second
        assert iter(first) is first and iter(second) is second
        if expected:
            assert next(first) == expected[0]
            assert list(first) == expected[1:]
        for _ in range(2):
            try:
                next(first)
            except StopIteration:
                pass
            else:
                raise AssertionError('Iterator did not remain exhausted')
        assert list(first) == []
        assert list(second) == expected
        assert list(helper(data)) == expected
        print(json.dumps({'helper': helper.__module__ + '.' + ''' + repr(name) + ''',
                          'empty': ''' + repr(empty) + ''', 'one_shot': True,
                          'fresh_calls_independent': True}))
    ''', tmp_path, record_property)


def test_migration_markdown_uses_dictionary_instance(tmp_path, record_property):
    selected = [item for item in fences(DOC.read_bytes())
                if item[0] == "### Migration from Python 2 to 3"]
    assert len(selected) == 1
    execute_fences(selected, tmp_path, record_property, "a\nb\n")


def test_all_py3helpers_markdown_fences_execute(tmp_path, record_property):
    examples = fences(DOC.read_bytes())
    assert len(examples) == 7
    execute_fences(examples, tmp_path, record_property)


def test_current_python3_usage_output(tmp_path, record_property):
    selected = [item for item in fences(DOC.read_bytes())
                if item[0] == "### Current Python 3 Dictionary Iteration"]
    assert len(selected) == 1
    execute_fences(selected, tmp_path, record_property,
                   "name\nage\ncity\nJohn\n30\nNew York\n"
                   "name: John\nage: 30\ncity: New York\n")


def test_implementation_illustration_matches_real_source():
    # This is source-description parity, not execution coverage of real helpers.
    selected = [item for item in fences(DOC.read_bytes())
                if item[0] == "## Implementation Details"]
    assert len(selected) == 1
    actual = (WEB_ROOT / "py3helpers.py").read_bytes()
    assert selected[0][2] == b"".join(line for line in actual.splitlines(keepends=True)
                                    if line.startswith(b"iter"))


def test_fence_extractor_keeps_comments_and_requires_closure():
    raw = b'## Section\n```python\n# code comment\nassert True\n```\n'
    assert fences(raw) == [('## Section', 2, b'# code comment\nassert True\n')]
    with pytest.raises(AssertionError, match="Unclosed Markdown fence"):
        fences(b'## Section\n```python\nassert True\n')
