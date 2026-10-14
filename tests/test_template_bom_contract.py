"""Bounded Unicode BOM contracts; guarded fresh processes, owned UTF-8 files."""
import pytest

from .test_template_security_contract import probe


@pytest.mark.parametrize('route', ['Template', 'Render'])
def test_unicode_bom_argument_declaration(route, tmp_path, record_property):
    probe(r'''
        from tempfile import TemporaryDirectory
        route = ''' + repr(route) + r'''
        raw = b'\xef\xbb\xbf$def with(name)\nHello $name!'
        source = raw.decode('utf-8')
        assert raw[:3].hex() == 'efbbbf' and ord(source[0]) == 0xfeff
        print(json.dumps({'raw_hex': raw.hex(), 'first_codepoint': ord(source[0]), 'route': route}), flush=True)
        with TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / 'hello.txt'
            path.write_bytes(raw)
            assert path.read_bytes() == raw
            template = Template(source) if route == 'Template' else Render(directory, cache=False).hello
            assert str(template('Ada')) == 'Hello Ada!\n'
        assert not root.exists()
    ''', tmp_path, record_property)


# Passing characterizations after the single normalizer fix, not extra RED slices.
@pytest.mark.parametrize('source,expected', [
    ('hello', 'hello\n'),
    ('\ufeffhello', 'hello\n'),
    ('\xef\xbb\xbfhello', 'hello\n'),
    ('', '\n'),
    ('\ufeff', '\n'),
    ('\xef\xbb\xbf', '\n'),
    ('hello\n', 'hello\n'),
    ('he\ufeffllo', 'he\ufeffllo\n'),
    (' \ufeffhello', ' \ufeffhello\n'),
    ('\ufeff\ufeffhello', '\ufeffhello\n'),
    ('\xef\xbb\xbf\xef\xbb\xbfhello', '\xef\xbb\xbfhello\n'),
    ('\ufeff\xef\xbb\xbfhello', '\xef\xbb\xbfhello\n'),
    ('\xef\xbb\xbf\ufeffhello', '\ufeffhello\n'),
    ('\ufeffa\r\nb\rc\tX', 'a\nb\nc       X\n'),
    ('\ufeff\tX', '       X\n'),
], ids=['no-bom', 'unicode', 'legacy', 'empty', 'unicode-only', 'legacy-only',
        'newline', 'interior', 'whitespace', 'double-unicode', 'double-legacy',
        'unicode-legacy', 'legacy-unicode', 'line-tab', 'tab-before-strip'])
def test_normalization_single_prefix(source, expected, tmp_path, record_property):
    probe('source, expected = ' + repr((source, expected)) + '''
assert Template.normalize_text(source) == expected
assert str(Template(source)()) == expected
print(json.dumps({'source_codepoints': list(map(ord, source)), 'normalized': expected}))
''', tmp_path, record_property)


def test_legacy_escape_and_input_type_policy(tmp_path, record_property):
    probe(r'''
        assert Template.normalize_text('\ufeffa\\$b') == 'a$$b\n'
        assert str(Template('\ufeffa\\$b')()) == 'a$b\n'
        for value, kind in [(b'hello', TypeError), (None, AttributeError), (1, AttributeError)]:
            raises(kind, lambda: Template.normalize_text(value))
            raises(kind, lambda: Template(value))
        # A second explicit call is a second normalization, not idempotence.
        once = Template.normalize_text('\ufeff\ufeffhello')
        assert once == '\ufeffhello\n'
        assert Template.normalize_text(once) == 'hello\n'
    ''', tmp_path, record_property)


@pytest.mark.parametrize('cache', [False, True], ids=['uncached', 'cached'])
@pytest.mark.parametrize('suffix', ['txt', 'html'])
def test_real_render_plain_arguments_and_filename(cache, suffix, tmp_path, record_property):
    probe(r'''
        from tempfile import TemporaryDirectory
        cache, suffix = ''' + repr((cache, suffix)) + r'''
        with TemporaryDirectory() as directory:
            root = Path(directory)
            plain = root / ('plain.' + suffix)
            args = root / ('args.' + suffix)
            plain.write_bytes(b'\xef\xbb\xbfhello')
            args.write_bytes(b'\xef\xbb\xbf$def with(value)\n$value')
            render = Render(directory, cache=cache)
            assert str(render.plain()) == 'hello\n'
            first = render.args
            assert Path(first.filename) == args
            expected = '&lt;&amp;\n' if suffix == 'html' else '<&\n'
            assert str(first('<&')) == expected
            assert str(Template(args.read_text(encoding='utf-8'), filename=str(args))('<&')) == expected
            assert first.content_type == ('text/html; charset=utf-8' if suffix == 'html' else 'text/plain')
            assert (render.args is first) is cache
            plain.write_bytes(b'\xef\xbb\xbfreplaced')
            assert str(render.plain()) == ('hello\n' if cache else 'replaced\n')
            print(json.dumps({'plain_hex': plain.read_bytes().hex(), 'args_hex': args.read_bytes().hex(), 'cache': cache, 'suffix': suffix}))
        assert not root.exists()
    ''', tmp_path, record_property)


def test_file_helpers_normalize_original_once(tmp_path, record_property):
    probe(r'''
        from tempfile import TemporaryDirectory
        from web.template import frender, compile_templates
        with TemporaryDirectory() as directory:
            root = Path(directory)
            raw = b'\xef\xbb\xbf$def with(name)\nHello $name!'
            (root / 'args.txt').write_bytes(raw)
            (root / 'double.txt').write_bytes(b'\xef\xbb\xbf\xef\xbb\xbfhello')
            assert str(frender(str(root / 'args.txt'))('Ada')) == 'Hello Ada!\n'
            assert str(frender(str(root / 'double.txt'))()) == '\ufeffhello\n'
            assert str(Render(directory, cache=False).double()) == '\ufeffhello\n'
            compile_templates(directory)
            namespace = {'__name__': 'owned_compiled_templates'}
            generated = (root / '__init__.py').read_bytes()
            exec(compile(generated, str(root / '__init__.py'), 'exec'), namespace)
            assert str(namespace['args']('Ada')) == 'Hello Ada!\n'
            assert str(namespace['double']()) == '\ufeffhello\n'
            assert (root / 'args.txt').read_bytes() == raw
        assert not root.exists()
    ''', tmp_path, record_property)


def test_bom_does_not_hide_invalid_syntax(tmp_path, record_property):
    probe(r'''
        from tempfile import TemporaryDirectory
        with TemporaryDirectory() as directory:
            root = Path(directory)
            for index, source in enumerate([
                '\ufeff$code:\n    value =\n',
                '\ufeff\ufeff$def with(name)\n$name',
                '\ufeff\xef\xbb\xbf$def with(name)\n$name',
            ]):
                path = root / ('bad' + str(index) + '.txt')
                path.write_bytes(source.encode('utf-8'))
                raises(SyntaxError, lambda: Template(source))
                raises(SyntaxError, lambda: getattr(Render(directory, cache=False), path.stem))
        assert not root.exists()
    ''', tmp_path, record_property)


@pytest.mark.parametrize('source', [
    '$code:\n    item.public = 1\n',
    '$code:\n    local = 0\n    local += item._marker\n',
    '$code:\n    a, item.public = (1, 2)\n',
], ids=['attribute-assignment', 'augassign-private-rhs', 'unpacking-attribute'])
def test_bom_keeps_construction_rejection(source, tmp_path, record_property):
    probe('source = ' + repr(source) + r'''
from tempfile import TemporaryDirectory
from types import SimpleNamespace
item = SimpleNamespace(public=9, _marker=1)
with TemporaryDirectory() as directory:
    root = Path(directory)
    for prefix in ('', '\ufeff'):
        text = prefix + source
        path = root / 'restricted.txt'
        path.write_bytes(text.encode('utf-8'))
        raises(SecurityError, lambda: Template(text, globals={'item': item}))
        raises(SecurityError, lambda: Render(directory, cache=False, globals={'item': item}).restricted)
        assert vars(item) == {'public': 9, '_marker': 1}
assert not root.exists()
''', tmp_path, record_property)
