"""Application-side date formatting; restricted template runtime is unchanged.

Only the actual published doctest is a documentation RED→GREEN regression.
The other cases characterize supported formatting and unsupported direct calls.
"""
import json
import os
import subprocess
import sys
import textwrap

import pytest

from .test_template_security_contract import BOOTSTRAP, WEB_ROOT


def date_probe(source, tmp_path, record_property):
    env = dict(PATH=os.defpath, HOME=str(tmp_path), TMPDIR=str(tmp_path),
               XDG_CACHE_HOME=str(tmp_path), XDG_DATA_HOME=str(tmp_path),
               XDG_CONFIG_HOME=str(tmp_path), PYTHON_DOTENV_DISABLED='1', LC_ALL='C')
    trailer = """
assert blocked == [], blocked
assert not {'core', 'modules', 'dotenv'}.intersection(sys.modules)
print('DATE_EVIDENCE=' + json.dumps(dict(python=sys.version, isolated=sys.flags.isolated,
    no_bytecode=sys.dont_write_bytecode, blocked=blocked, web_path=web.__file__)))
"""
    argv = [sys.executable, '-I', '-B', '-c',
            BOOTSTRAP + '\n' + textwrap.dedent(source) + trailer, str(WEB_ROOT.parent)]
    result = subprocess.run(argv, env=env, cwd=tmp_path, capture_output=True,
                            text=True, timeout=30)
    record_property('child_argv', json.dumps(argv))
    record_property('child_environment', json.dumps(env))
    record_property('child_returncode', result.returncode)
    record_property('probe_stdout', result.stdout)
    record_property('probe_stderr', result.stderr)
    assert result.returncode == 0, result.stdout + result.stderr
    data = json.loads(result.stdout.splitlines()[-1].removeprefix('DATE_EVIDENCE='))
    assert data['isolated'] == 1 and data['no_bytecode'] and data['blocked'] == []
    assert data['web_path'] == str(WEB_ROOT / '__init__.py')


def test_actual_datetime_doctest_keeps_successful_output(tmp_path, record_property):
    date_probe(r'''
        import doctest
        import importlib
        import io
        module = importlib.import_module('web.template')
        case = next(t for t in doctest.DocTestFinder().find(module)
                    if t.name == 'web.template.test')
        assert len(case.examples) == 66
        example = case.examples[65]
        assert example.want == "'01 2009\\n'\n"
        assert example.exc_msg is None and example.options == {}
        # Run the actual case, including its real helper and datetime import.
        # Do not copy/rewrite source or replace its desired output.
        runner = doctest.DocTestRunner()
        output = io.StringIO()
        result = runner.run(case, out=output.write)
        print(output.getvalue())
        print(json.dumps(dict(name=case.name, ordinal=65, source=example.source,
                              want=example.want, attempted=result.attempted,
                              failed=result.failed)))
        assert (result.failed, result.attempted) == (0, 66)
    ''', tmp_path, record_property)


@pytest.mark.parametrize('state', ['cold', 'warm', 'preimport'])
def test_direct_strftime_remains_unsupported(state, tmp_path, record_property):
    date_probe(r'''
        import datetime
        state = ''' + repr(state) + r'''
        date = datetime.datetime(2009, 1, 1)
        if state == 'warm':
            assert date.strftime('%m %Y') == '01 2009'
        elif state == 'preimport':
            import _strptime
            import time
            import locale
        from web.template import TEMPLATE_BUILTINS
        assert '__import__' not in TEMPLATE_BUILTINS
        error = raises(KeyError, lambda: Template(
            "$def with (date)\n$date.strftime('%m %Y')")(date))
        assert error.args == ('__import__',)
        assert blocked == []
        assert date.strftime('%m %Y') == '01 2009'
        assert str(Template('$def with (text)\n$text')(
            date.strftime('%m %Y'))) == '01 2009\n'
        print(json.dumps(dict(state=state, direct_error=repr(error),
                              application_output=date.strftime('%m %Y'))))
    ''', tmp_path, record_property)


@pytest.mark.parametrize('renderer', ['Template', 'Render'])
@pytest.mark.parametrize('suffix', ['txt', 'html'])
def test_preformatted_date_text_and_escaping(renderer, suffix, tmp_path, record_property):
    date_probe(r'''
        import datetime
        renderer, suffix = ''' + repr((renderer, suffix)) + r'''
        date = datetime.datetime(2009, 1, 1)
        text = date.strftime('%m %Y')
        assert text == '01 2009'
        source = '$def with (text)\n$text'
        name = 'date.' + suffix
        if renderer == 'Template':
            template = Template(source, filename=name)
        else:
            root = Path.cwd() / 'templates'
            root.mkdir()
            (root / name).write_text(source, encoding='utf-8')
            template = Render(str(root), cache=False).date
            assert Path(template.filename) == root / name
        assert str(template(text)) == '01 2009\n'
        decorated = '<' + text + '> & "\''
        expected = '&lt;01 2009&gt; &amp; &quot;&#39;\n' if suffix == 'html' else decorated + '\n'
        assert str(template(decorated)) == expected
        assert str(template(text)) == '01 2009\n'
        print(json.dumps(dict(renderer=renderer, suffix=suffix, output=expected)))
    ''', tmp_path, record_property)


@pytest.mark.parametrize('injection', ['argument', 'globals'])
def test_trusted_callables_keep_application_capabilities(injection, tmp_path, record_property):
    date_probe(r'''
        import datetime
        injection = ''' + repr(injection) + r'''
        calls = []
        def format_date(date):
            calls.append(date)
            return date.strftime('%m %Y')
        date = datetime.datetime(2009, 1, 1)
        if injection == 'argument':
            template = Template('$def with (format_date, date)\n$format_date(date)')
            result = template(format_date, date)
        else:
            template = Template('$def with (date)\n$format_date(date)',
                                globals={'format_date': format_date})
            result = template(date)
        assert str(result) == '01 2009\n' and calls == [date]
        from web.template import TEMPLATE_BUILTINS
        assert '__import__' not in TEMPLATE_BUILTINS
        # Supplied callables execute trusted Python and can mutate owned state;
        # restricted builtins do not turn those capabilities into a sandbox.
    ''', tmp_path, record_property)


@pytest.mark.parametrize('source', [
    '$code:\n    import datetime',
    '$def with (date)\n$date.__class__',
    "$__import__('datetime')",
], ids=['import', 'dunder-attribute', 'dunder-import'])
def test_date_examples_do_not_expand_restricted_boundary(source, tmp_path, record_property):
    date_probe('raises(SecurityError, lambda: Template(' + repr(source) + '))',
               tmp_path, record_property)
