"""Executable template reference; runtime limitations are not source fixes.

Reuse the existing fresh -I -B Python-level isolation (not an OS sandbox).
Never rewrite fence bytes: standalone Python has an empty application namespace;
template fragments use only the explicitly declared sample data below.
"""
import hashlib
import os
import subprocess
import sys

import pytest

from .test_template_security_contract import BOOTSTRAP, DOC, WEB_ROOT, fences, probe


def block(heading, occurrence=0):
    selected = [b for b in fences(DOC.read_bytes()) if b[0] == heading]
    return selected[occurrence]


def documented(heading, occurrence, assertion, tmp_path, record_property, *, fragment=False, globals_source='{}', args='()'):
    _, line, language, code, closed = block(heading, occurrence)
    assert closed and language == 'python'
    record_property('fence_sha256', hashlib.sha256(code).hexdigest())
    record_property('markdown_line', line)
    record_property('mode', 'template fragment with declared sample data' if fragment else 'standalone Python')
    if fragment:
        program = 'sample_globals = ' + globals_source + '\nresult = Template(' + repr(code.decode()) + ', globals=sample_globals)' + args + '\n'
    else:
        program = "ns = {'__name__': '__main__'}\nexec(compile(" + repr(code) + ", 'docs/template.md', 'exec'), ns)\n"
    probe(program + assertion, tmp_path, record_property)


@pytest.mark.parametrize('heading', ['#### Code Blocks', '### `$code:`'])
def test_wb02_documented_code_blocks(heading, tmp_path, record_property):
    code = block(heading)[3]
    # The historical form was a template fragment; execute it without rewriting.
    if code.startswith(b'$'):
        documented(heading, 0, "assert str(result) == ''", tmp_path, record_property, fragment=True)
    else:
        documented(heading, 0, "assert str(ns['result']) == '6.0\\n'", tmp_path, record_property)


@pytest.mark.parametrize('occurrence', [0, 1])
def test_wb03_documented_assignments(occurrence, tmp_path, record_property):
    documented('### Assignments', occurrence,
               "assert result.a == 'content\\n'\nassert str(result) == '7\\ncontent\\n\\n'",
               tmp_path, record_property, fragment=True, globals_source="{'value': 7}")


def test_wb04_documented_defwith(tmp_path, record_property):
    documented('### Function Definitions', 0,
               "assert str(result) == '    template content using A and B\\n'",
               tmp_path, record_property, fragment=True,
               globals_source="{'default': 'B'}", args="('A')")


def test_wb05_documented_greeting(tmp_path, record_property):
    documented('### Basic Template', 1,
               "assert str(ns['result']) == 'Hello World!\\n'\nassert str(ns['template']('Ada')) == 'Hello Ada!\\n'",
               tmp_path, record_property)


@pytest.mark.parametrize('heading,occurrence,assertion', [
    ('### Template with Control Structures', 1,
     "from types import SimpleNamespace\nassert '<h1>Welcome, Ada!</h1>' in str(ns['template'](SimpleNamespace(name='Ada'), ['one']))\nassert '<li>one</li>' in str(ns['template'](None, ['one']))\nassert '<p>No items available</p>' in str(ns['template'](None, []))"),
    ('### Template with Functions', 0,
     "assert str(ns['template'](['one'])) == '<ul>\\n<li><strong>one</strong>\\n\\n</li>\\n</ul>\\n'\nassert '<li>' not in str(ns['template']([]))"),
], ids=['control', 'functions'])
def test_wb06_documented_first_line(heading, occurrence, assertion, tmp_path, record_property):
    documented(heading, occurrence, assertion, tmp_path, record_property)


@pytest.mark.parametrize('occurrence', [0, 2])
def test_wb07_documented_result_attributes(occurrence, tmp_path, record_property):
    assertion = ("assert result.title == 'My Page'\nassert result.content == 'Welcome'\nassert str(result) == '\\n<h1>My Page</h1>\\nWelcome\\n'"
                 if occurrence == 0 else
                 "assert ns['result'].title == 'My Website'\nassert ns['result'].author == 'John Doe'\nassert '<title>My Website</title>' in str(ns['result'])\nassert '<p>By John Doe</p>' in str(ns['result'])")
    documented('### Template with Variables', occurrence, assertion, tmp_path,
               record_property, fragment=occurrence == 0)


def test_wb08_documented_nested_loops(tmp_path, record_property):
    documented('### Nested Loops', 0,
               "assert str(ns['template'](['r1', 'r2'], ['c1', 'c2'])) == 'Row 1\\nColumn 1 (parent: 1)\\nColumn 2 (parent: 1)\\nRow 2\\nColumn 1 (parent: 2)\\nColumn 2 (parent: 2)\\n'\nassert str(ns['template']([], ['c'])) == ''",
               tmp_path, record_property)


def test_wb09_documented_builtin_candidates_and_runtime(tmp_path, record_property):
    _, line, language, code, closed = block('#### `TEMPLATE_BUILTIN_NAMES`')
    assert closed and language == 'python'
    record_property('fence_sha256', hashlib.sha256(code).hexdigest())
    record_property('markdown_line', line)
    record_property('mode', 'reference literal evaluated against actual constant')
    probe('''
        import ast
        import builtins
        from web.template import TEMPLATE_BUILTIN_NAMES, TEMPLATE_BUILTINS
        names = ast.literal_eval(''' + repr(code.decode()) + ''')
        assert names == TEMPLATE_BUILTIN_NAMES
        assert set(TEMPLATE_BUILTINS) == set(names) - {'long', 'xrange', 'cmp'}
        assert all(value is getattr(builtins, name) for name, value in TEMPLATE_BUILTINS.items())
        assert '__import__' not in names and '__import__' not in TEMPLATE_BUILTINS
        for name in ('long', 'xrange', 'cmp'):
            raises(NameError, lambda: Template('$' + name)())
        assert str(Template('$min(3, 1)')()) == '1\\n'
        raises(NameError, lambda: Template('$min(3, 1)', builtins={})())
        assert str(Template('$format_value(3)', globals={'format_value': str})()) == '3\\n'
        print(json.dumps({'python': sys.version, 'active_builtins': sorted(TEMPLATE_BUILTINS)}))
    ''', tmp_path, record_property)


def test_wb10_noop_and_historical_doctests(tmp_path, record_property):
    probe('''
        import contextlib
        import doctest
        import importlib
        import io
        module = importlib.import_module('web.template')
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            assert module.test() is None
        assert output.getvalue() == ''
        runner = doctest.DocTestRunner()
        for test in doctest.DocTestFinder().find(module):
            runner.run(test, out=output.write)
        outcome = runner.summarize(verbose=False)
        assert outcome.attempted > 0 and outcome.failed > 0
        assert "u'" in output.getvalue()
        assert 'TemplateResult' in output.getvalue()
        assert (outcome.failed, outcome.attempted) == (60, 124)
        # Separate an actual runtime limitation from obsolete repr expectations.
        import datetime
        date = datetime.datetime(2009, 1, 1)
        error = raises(KeyError, lambda: Template("$def with (date)\\n$date.strftime('%m %Y')")(date))
        assert error.args == ('__import__',)
        formatted = date.strftime('%m %Y')
        assert str(Template('$def with (value)\\n$value')(formatted)) == '01 2009\\n'
        print(output.getvalue())
        print(json.dumps({'historical_doctests': dict(runner._stats), 'attempted': outcome.attempted, 'failed': outcome.failed}))
    ''', tmp_path, record_property)


def test_wb10_documented_runner_reports_real_failure_exit(tmp_path, record_property):
    _, line, language, code, closed = block('#### `test()`')
    assert closed and language == 'python'
    record_property('fence_sha256', hashlib.sha256(code).hexdigest())
    record_property('markdown_line', line)
    record_property('mode', 'standalone Python; expected historical doctest failure exit 1')
    program = BOOTSTRAP + "\nns = {'__name__': '__main__'}\nexec(compile(" + repr(code) + ", 'docs/template.md', 'exec'), ns)\n"
    result = subprocess.run([sys.executable, '-I', '-B', '-c', program, str(WEB_ROOT.parent)],
                            cwd=tmp_path, env={'PATH': os.defpath, 'HOME': str(tmp_path),
                            'TMPDIR': str(tmp_path), 'PYTHON_DOTENV_DISABLED': '1', 'LC_ALL': 'C'},
                            text=True, capture_output=True, timeout=30)
    record_property('probe_stdout', result.stdout)
    record_property('probe_stderr', result.stderr)
    record_property('child_returncode', result.returncode)
    assert result.returncode == 1, result.stdout + result.stderr
    assert 'TestResults(failed=60, attempted=124)' in result.stdout
    assert result.stderr == "<doctest web.template.test[44]>:1: SyntaxWarning: invalid escape sequence '\\$'\n  t(\"Stop, \\$money isn't evaluated.\")()\n"
    assert "KeyError: '__import__'" in result.stdout


def test_wb11_parser_consumption_shapes(tmp_path, record_property):
    probe(r'''
        import web.template as t
        p = t.Parser()
        assert p.read_defwith('$def with (name)\n$name') == ('def with (name)', '$name')
        assert p.read_defwith('hello') == ('', 'hello')
        cases = [
            ('read_section', 'hello\nrest', t.LineNode, 'rest'),
            ('readline', 'hello $name\nrest', t.LineNode, 'rest'),
            ('read_node', '$name!', t.ExpressionNode, '!'),
            ('read_text', 'hello $name', t.TextNode, '$name'),
            ('read_assignment', ' a = 2\nrest', t.AssignmentNode, 'rest'),
            ('read_var', 'var name: title\nrest', t.VarNode, 'rest'),
            ('read_keyword', 'pass\nrest', t.StatementNode, 'rest'),
            ('read_block_section', 'if True:\n    hello\nrest', t.IfNode, 'rest'),
        ]
        for method, source, cls, remaining in cases:
            result = getattr(p, method)(source)
            assert isinstance(result, tuple) and len(result) == 2
            node, rest = result
            assert isinstance(node, cls) and rest == remaining, (method, result)
        suite = p.read_suite('hello\nworld\n')
        assert isinstance(suite, t.SuiteNode) and len(suite.sections) == 2
        assert p.read_statement('if True: hello') == ('if True:', ' hello')
        assert p.read_indented_block('    hello\nrest', '    ') == ('hello\n', 'rest')
        root = p.parse('$def with (name)\n$name')
        assert isinstance(root, t.DefwithNode) and isinstance(root.suite, t.SuiteNode)
    ''', tmp_path, record_property)


def test_wb11_documented_expression_consumption(tmp_path, record_property):
    documented('##### `read_expr(text, escape=True)`', 0,
               "assert ns['rest'] == ' and rest'\nassert ns['node'].value == 'name'\nassert ns['node'].escape is False",
               tmp_path, record_property)


@pytest.mark.parametrize('sized', [True, False], ids=['sized', 'unsized'])
def test_wb12_loop_length_and_parent_characterization(sized, tmp_path, record_property):
    probe(r'''
        from web.template import ForLoop, ForLoopContext
        sized = ''' + repr(sized) + r'''
        loop = ForLoop()
        values = ['a', 'b'] if sized else iter(['a', 'b'])
        rows = []
        for item in loop.setup(values):
            outer = loop._ctx
            assert isinstance(outer, ForLoopContext) and outer.parent is None
            rows.append((item, loop.length, loop.index, loop.index0, loop.first,
                         loop.last, loop.revindex, loop.revindex0, loop.parity, loop.odd, loop.even))
            children = []
            for child in loop.setup([1, 2]):
                assert loop.parent is outer
                children.append((loop.index, loop.parent.index, loop.last))
            assert children == [(1, outer.index, False), (2, outer.index, True)]
            assert loop._ctx is outer
        expected = [('a', 2, 1, 0, True, False, 2, 1, 'odd', True, False),
                    ('b', 2, 2, 1, False, True, 1, 0, 'even', False, True)] if sized else [
                    ('a', 0, 1, 0, True, False, 0, -1, 'odd', True, False),
                    ('b', 0, 2, 1, False, False, -1, -2, 'even', False, True)]
        assert rows == expected, rows
        assert loop._ctx is None
        raises(AttributeError, lambda: loop.index)
        assert list(loop.setup([])) == [] and loop._ctx is None
        print(json.dumps({'sized': sized, 'rows': rows}))
    ''', tmp_path, record_property)


def test_wb12_documented_loop_helpers(tmp_path, record_property):
    documented('### Using Loop Helpers', 0,
               "assert str(ns['result']).count('Last: True') == 1\nassert str(ns['result']).count('Last: False') == 4\nassert 'Index: 5' in str(ns['result'])",
               tmp_path, record_property)


def test_wb13_pinned_unicode_bom_limitation(tmp_path, record_property):
    probe(r'''
        from tempfile import TemporaryDirectory
        assert Template.normalize_text('\ufeffhello') == 'hello\n'
        assert str(Template('\ufeffhello')()) == 'hello\n'
        assert str(Template('\ufeff$def with(name)\n$name')('Ada')) == 'Ada\n'
        assert Template.normalize_text('\xef\xbb\xbfhello') == 'hello\n'
        assert Template.normalize_text('a\r\nb\rc\tX') == 'a\nb\nc       X\n'
        assert Template.normalize_text('a\\$b') == 'a$$b\n'
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'bom.txt').write_bytes(b'\xef\xbb\xbfhello')
            (root / 'legacy.txt').write_text('\xef\xbb\xbfhello', encoding='utf-8')
            (root / 'args.txt').write_bytes(b'\xef\xbb\xbf$def with(name)\n$name')
            render = Render(directory, cache=False)
            assert str(render.bom()) == 'hello\n'
            assert str(render.legacy()) == 'hello\n'
            assert str(render.args('Ada')) == 'Ada\n'
        assert not root.exists()
    ''', tmp_path, record_property)


def test_wb13_documented_normalization_and_owned_files(tmp_path, record_property):
    documented('##### Text normalization and UTF-8 BOM', 0,
               "assert not ns['root'].exists()", tmp_path, record_property)


def test_wb15_documented_length_is_mapping_size(tmp_path, record_property):
    line = next(line for line in DOC.read_bytes().splitlines() if line.startswith(b'- `__len'))
    name = line.split(b'`')[1].split(b'(')[0].decode()
    record_property('raw_method_line_hex', line.hex())
    probe(r'''
        from web.template import TemplateResult
        method = getattr(TemplateResult, ''' + repr(name) + r''')
        result = TemplateResult()
        assert method(result) == len(result) == 1
        assert set(result) == {'__body__'}
        result.title = 'Title'
        result.extend(['long', ' body'])
        assert len(result) == 2
        assert set(result.keys()) == {'__body__', 'title'}
        assert str(result) == result['__body__'] == 'long body'
        assert len(result) == 2
        del result.title
        assert len(result) == 1 and str(result) == 'long body'
    ''', tmp_path, record_property)


@pytest.mark.parametrize('heading', ['#### `splitline(text)`', '#### `frender(path, **keywords)`',
                                     '### Rendering from Directory', '### Using Base Templates'])
def test_remaining_standalone_recipes(heading, tmp_path, record_property):
    assertion = ("assert ns['splitline']('foo\\nbar') == ('foo\\n', 'bar')"
                 if heading == '#### `splitline(text)`' else "assert not ns['root'].exists()")
    documented(heading, 0, assertion, tmp_path, record_property)


# Every setup here is explicitly described in the page's fragment sample table.
FRAGMENTS = [
    ('### Expressions', 0,
     "dict(varname='V', object=web.storage(attribute='A', method=lambda: web.storage(attr='M')), list=['L'], func=lambda *args: sum(args), x=1, y=2, items=['a', 'b'])", '()',
     "assert [s.split(' #')[0].rstrip() for s in str(result).splitlines()] == ['V', 'A', 'L', '6', 'M', '3', '2']"),
    ('#### If Statements', 0, "dict(condition=False, other_condition=True)", '()',
     "assert str(result).split() == ['content']"),
    ('#### For Loops', 0, "dict(items=['a', 'b'])", '()',
     "assert str(result) == 'a\\n\\nb\\n\\n0: a\\n1: b\\n'"),
    ('#### While Loops', 0, "dict(condition=False)", '()', "assert str(result) == ''"),
    ('### Variables Declaration', 0, "dict(value=7)", '()', "assert result.name == 7 and str(result) == ''"),
    ('### Basic Template', 0, '{}', "('Ada')", "assert str(result) == 'Hello Ada!\\n'"),
    ('### Template with Control Structures', 0, '{}', "(['a', 'b'])",
     "assert str(result) == '<ul>\\n<li>a</li>\\n<li>b</li>\\n</ul>\\n'"),
    ('### Expressions', 1, "dict(func=lambda *args: sum(args), obj=web.storage(attr='A'), list=['L'], dict={'key': 'D'}, items=['a', 'b'])", '()',
     "assert [s.split(' #')[0].rstrip() for s in str(result).splitlines()] == ['3', 'A', 'L', 'D', '2']"),
    ('### Control Structures', 0, "dict(condition=False, items=['a', 'b'])", '()',
     "assert str(result).split() == ['content', 'content']"),
    ('### Comments', 0, '{}', '()', "assert str(result) == '\\n'"),
    ('### `$def with (...)`', 0, '{}', "('Ada')", "assert str(result) == 'Hello Ada, you are 25 years old.\\n'"),
    ('### `$var name: value`', 0, '{}', '()', "assert result.title == 'My Page' and result.content == 'Welcome' and str(result) == ''"),
    ('### `$pass`, `$break`, `$continue`, `$return`', 0, "dict(items=iter([None, 'stop', 'after']))", '()',
     "assert str(result) == ''\nassert next(sample_globals['items']) == 'after'"),
]


@pytest.mark.parametrize('heading,occurrence,globals_source,args,assertion', FRAGMENTS,
                         ids=['expressions-syntax', 'if', 'for', 'while-false', 'var-declaration',
                              'greeting-fragment', 'list-fragment', 'expressions-reference',
                              'control-reference', 'comment', 'def-directive', 'var-directive', 'statements'])
def test_remaining_template_fragments(heading, occurrence, globals_source, args, assertion, tmp_path, record_property):
    documented(heading, occurrence, assertion, tmp_path, record_property,
               fragment=True, globals_source=globals_source, args=args)


def test_all_markdown_fences_are_closed():
    assert all(block[4] for block in fences(DOC.read_bytes()))
