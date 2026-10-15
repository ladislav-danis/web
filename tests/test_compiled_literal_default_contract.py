"""Exact compiler compatibility: literal indentation and helper defaults."""
import pytest

from .test_compiled_escape_contract import probe


@pytest.mark.parametrize('prefix', ['f', 'rf'])
def test_compiled_fstring_without_fields_keeps_literal_value(prefix, tmp_path, record_property):
    probe(r'''
        prefix = ''' + repr(prefix) + r'''
        source = '$code:\n    value = '+prefix+'"""first\n    <&>\n    last"""\n$:value'
        expected = 'first\n    <&>\n    last\n'
        assert str(Template(source, filename='page.html')()) == expected
        module = compiled({'page.html': source}, ['page.html'])
        actual = str(module.page())
        print(json.dumps({'actual': actual, 'expected': expected}))
        assert actual == expected, (actual, expected)
    ''', tmp_path, record_property)


@pytest.mark.parametrize('expression,expected', [
    ('escape_("<&>", True)', '&lt;&amp;&gt;\n'),
    ('join_("ab")', 'ab\n'),
], ids=['escape-default', 'join-default'])
def test_compiled_helper_default_evaluates_before_function_creation(expression, expected, tmp_path, record_property):
    probe(r'''
        expression, expected = ''' + repr((expression, expected)) + r'''
        source = '$def with (value='+expression+')\n$:value'
        assert str(Template(source, filename='page.html')()) == expected
        module = compiled({'anchor.html': 'anchor', 'page.html': source},
                          ['anchor.html', 'page.html'])
        actual = str(module.page())
        print(json.dumps({'actual': actual, 'expected': expected}))
        assert actual == expected, (actual, expected)
        assert module.page.t.__defaults__ == (expected[:-1],)
    ''', tmp_path, record_property)


@pytest.mark.parametrize('literal,expected', [
    ('"""first\n    last""" + "END"', 'first\n    lastEND\n'),
    ('f"""first\n    last""" + "END"', 'first\n    lastEND\n'),
    ('rf"""first\n    last""" + "END"', 'first\n    lastEND\n'),
    ('"first\\\n    last"', 'first    last\n'),
    ('f"""first\n    """ + "END"', 'first\n    END\n'),
    ('rf"""first\n    {{}}\\n\n    last"""', 'first\n    {}\\n\n    last\n'),
], ids=['ordinary-trailing', 'f-trailing', 'rf-trailing', 'continued', 'closing-empty-line', 'raw-escaped-braces'])
def test_compiled_literal_boundaries_preserve_exact_values(literal, expected, tmp_path, record_property):
    probe(r'''
        literal, expected = ''' + repr((literal, expected)) + r'''
        source = '$code:\n    value = '+literal+'\n$:value'
        assert str(Template(source, filename='page.html')()) == expected
        module = compiled({'page.html': source}, ['page.html'])
        assert str(module.page()) == expected
    ''', tmp_path, record_property)


@pytest.mark.parametrize('prefix', ['', 'f', 'rf'], ids=['ordinary', 'f', 'rf'])
def test_compiled_nested_function_multiline_value(prefix, tmp_path, record_property):
    probe(r'''
        prefix = ''' + repr(prefix) + r'''
        source = '$code:\n    def inner():\n        return '+prefix+'"""first\n        <&>\n        last"""\n    value = inner()\n$:value'
        expected = 'first\n        <&>\n        last\n'
        assert str(Template(source, filename='page.html')()) == expected
        module = compiled({'page.html': source}, ['page.html'])
        assert str(module.page()) == expected
    ''', tmp_path, record_property)


@pytest.mark.parametrize('reverse', [False, True], ids=['forward', 'reverse'])
@pytest.mark.parametrize('anchor_suffix', ['html', 'txt'], ids=['html-anchor', 'txt-anchor'])
def test_compiled_defaults_use_own_suffix_and_retain_owner(anchor_suffix, reverse, tmp_path, record_property):
    probe(r'''
        anchor_suffix, reverse = ''' + repr((anchor_suffix, reverse)) + r'''
        text = '$def with (value=escape_("<&>", True), helper=escape_, *, joined=join_("ab"), joiner=join_)\n$:value|$:helper("<&>", True)|$:joined|$:joiner("c", "d")'
        files = {'anchor.'+anchor_suffix: 'anchor', 'page.html': text,
                 'plain.txt': text, 'data.xml': text}
        order = list(files)
        if reverse:
            order.reverse()
        module = compiled(files, order)
        for name, suffix, expected in [('page', 'html', '&lt;&amp;&gt;'),
                                       ('plain', 'txt', '<&>'), ('data', 'xml', '&lt;&amp;&gt;')]:
            template = getattr(module, name)
            assert str(template()) == expected+'|'+expected+'|ab|cd\n'
            assert str(Template(text, filename=name+'.'+suffix)()) == str(template())
            assert template.t.__defaults__[0] == expected
            assert template.t.__defaults__[1].__self__ is template
            assert template.t.__kwdefaults__['joiner'].__self__ is template
            assert template.t.__globals__ is module.__dict__
            template.filter = lambda value: 'custom'+value
            assert str(template()) == expected+'|custom<&>|ab|cd\n'
        assert str(module.plain()) == '<&>|custom<&>|ab|cd\n'
    ''', tmp_path, record_property)


@pytest.mark.parametrize('source,kind', [
    ('$code:\n    value = f"""first\n    {1}\n    last"""\n$:value', 'SecurityError'),
    ('$__template__', 'SecurityError'),
    ('$def with (value=join_(["a", "b"]))\n$:value', 'TypeError'),
], ids=['formatted-field', 'reserved-dunder', 'invalid-join-default'])
def test_compiled_correction_keeps_rejected_language_boundaries(source, kind, tmp_path, record_property):
    probe(r'''
        source, kind = ''' + repr((source, kind)) + r'''
        error = {'SecurityError': SecurityError, 'TypeError': TypeError}[kind]
        raises(error, lambda: Template(source, filename='page.html'))
        root = Path.cwd()/'rejected'; root.mkdir()
        (root/'page.html').write_text(source)
        raises(error, lambda: compile_templates(str(root)))
        assert '__import__' not in web.template.TEMPLATE_BUILTINS
    ''', tmp_path, record_property)
