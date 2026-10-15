"""Compiled helpers belong to each template, not the last file in a module.

Real compile/import/render in fresh offline -I -B children. The reused Python
policy permits owned compiler writes; it is not an OS sandbox.
"""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import textwrap

import pytest

from .test_template_security_contract import BOOTSTRAP, WEB_ROOT


COMPILER = r'''
import hashlib
import importlib.util
from web.template import CompiledTemplate, compile_templates, GAE_Render
print(json.dumps({'bootstrap': True, 'isolated': sys.flags.isolated,
                  'no_bytecode': sys.dont_write_bytecode,
                  'source_path': str(Path(web.__file__).parent / 'template.py'),
                  'source_sha256': hashlib.sha256((Path(web.__file__).parent / 'template.py').read_bytes()).hexdigest()}))

def compiled(files, order, label='templates'):
    root = Path.cwd() / label
    root.mkdir()
    for name, text in files.items():
        (root / name).write_text(text, encoding='utf-8', newline='')
    assert set(order) == set(files) and len(order) == len(files)
    walk = os.walk
    seen = []
    def ordered(path):
        assert Path(path) == root
        for directory, directories, names in walk(path):
            assert Path(directory) == root and not directories
            assert set(names) == set(order)
            names[:] = order
            seen.append(names[:])
            yield directory, directories, names
    os.walk = ordered
    try:
        compile_templates(str(root))
    finally:
        os.walk = walk
    assert seen == [order]
    generated = root / '__init__.py'
    raw = generated.read_bytes()
    spec = importlib.util.spec_from_file_location('owned_' + label, generated)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    print(json.dumps({'compile_order': seen, 'templates': files,
                      'generated_path': str(generated), 'generated_source': raw.decode(),
                      'generated_sha256': hashlib.sha256(raw).hexdigest()}))
    return module
'''


def probe(source, tmp_path, record_property):
    env = {'PATH': os.defpath, 'PYTHON_DOTENV_DISABLED': '1', 'LC_ALL': 'C'}
    env.update({key: str(tmp_path) for key in
                ['HOME', 'TMPDIR', 'XDG_CACHE_HOME', 'XDG_DATA_HOME', 'XDG_CONFIG_HOME']})
    trailer = '''
assert blocked == []
assert not {'core', 'modules', 'dotenv'}.intersection(sys.modules)
print(json.dumps({'completed': True, 'isolated': sys.flags.isolated,
                  'no_bytecode': sys.dont_write_bytecode}))
'''
    program = BOOTSTRAP + COMPILER + '\n' + textwrap.dedent(source) + trailer
    argv = [sys.executable, '-I', '-B', '-c', program, str(WEB_ROOT.parent)]
    result = subprocess.run(argv, cwd=tmp_path, env=env, capture_output=True,
                            text=True, timeout=30)
    for key, value in [('child_argv', json.dumps(argv)), ('child_environment', json.dumps(env)),
                       ('program_sha256', hashlib.sha256(program.encode()).hexdigest()),
                       ('child_returncode', result.returncode), ('probe_stdout', result.stdout),
                       ('probe_stderr', result.stderr)]:
        record_property(key, value)
    assert result.returncode == 0, result.stdout + result.stderr
    boot = json.loads(result.stdout.splitlines()[0])
    assert boot == {'bootstrap': True, 'isolated': 1, 'no_bytecode': True,
                    'source_path': str(WEB_ROOT / 'template.py'),
                    'source_sha256': hashlib.sha256((WEB_ROOT / 'template.py').read_bytes()).hexdigest()}
    assert json.loads(result.stdout.splitlines()[-1]) == {
        'completed': True, 'isolated': 1, 'no_bytecode': True}


@pytest.mark.parametrize('html_last', [False, True], ids=['plain-last', 'html-last'])
def test_mixed_compilation_owns_helpers_in_both_orders(html_last, tmp_path, record_property):
    probe(r'''
        html_last = ''' + repr(html_last) + r'''
        files = {name: '$def with (value)\n$value'
                 for name in ['page.html', 'card.html', 'plain.txt', 'note.txt']}
        order = list(files)
        if html_last:
            order.reverse()
        module = compiled(files, order)
        outputs = [(name, str(getattr(module, name)('<&>')))
                   for name in ['page', 'plain', 'card', 'note', 'page', 'note', 'card', 'plain']]
        expected = [(name, '&lt;&amp;&gt;\n' if name in ['page', 'card'] else '<&>\n')
                    for name, _ in outputs]
        print(json.dumps({'actual': outputs, 'expected': expected}))
        assert outputs == expected, (outputs, expected)
    ''', tmp_path, record_property)


@pytest.mark.parametrize('filename,escaped,content_type', [
    ('page.html', True, 'text/html; charset=utf-8'),
    ('page.xhtml', True, 'application/xhtml+xml; charset=utf-8'),
    ('page.xml', True, None), ('page.txt', False, 'text/plain'),
    ('page.unknown', False, None), ('page.HTML', False, None),
    ('page', False, None), ('page.htm', False, None),
])
def test_compiled_suffix_raw_and_content_type_policy(filename, escaped, content_type, tmp_path, record_property):
    probe(r'''
        filename, escaped, content_type = ''' + repr((filename, escaped, content_type)) + r'''
        text = '$def with (value)\n$value|$:value'
        module = compiled({filename: text}, [filename])
        value = '<&>"\''
        safe = '&lt;&amp;&gt;&quot;&#39;' if escaped else value
        assert str(module.page(value)) == safe + '|' + value + '\n'
        assert str(module.page(value)) == str(Template(text, filename=filename)(value))
        assert module.page.content_type == content_type
        assert Path(module.page.filename).name == filename
        from web import webapi
        webapi.ctx.headers = []
        module.page(value)
        assert webapi.ctx.headers == ([('Content-Type', content_type)] if content_type else [])
        webapi.ctx.clear()
    ''', tmp_path, record_property)


@pytest.mark.parametrize('value,plain,html', [
    (None, '', ''), ('Žluťoučký <&>', 'Žluťoučký <&>', 'Žluťoučký &lt;&amp;&gt;'),
    (b'<&>', "b'<&>'", 'b&#39;&lt;&amp;&gt;&#39;'),
    (0, '0', '0'), (False, 'False', 'False'),
])
def test_compiled_conversion_keeps_direct_template_policy(value, plain, html, tmp_path, record_property):
    probe(r'''
        value, plain, html = ''' + repr((value, plain, html)) + r'''
        text = '$def with (value)\n$value|$:value'
        module = compiled({'page.html': text, 'plain.txt': text}, ['page.html', 'plain.txt'])
        assert str(module.page(value)) == html + '|' + plain + '\n'
        assert str(module.plain(value)) == plain + '|' + plain + '\n'
        assert str(Template(text, filename='page.html')(value)) == str(module.page(value))
        assert str(Render(str(Path.cwd()/'templates'), cache=False).plain(value)) == str(module.plain(value))
    ''', tmp_path, record_property)


@pytest.mark.parametrize('prefix', ['\ufeff', '\xef\xbb\xbf', ''])
def test_compiler_normalization_and_result_attributes(prefix, tmp_path, record_property):
    probe(r'''
        prefix = ''' + repr(prefix) + r'''
        text = prefix + '$def with (value)\r\n$var title: $value\r$for item in [value]:\r\n\t$item'
        module = compiled({'page.html': text, 'plain.txt': text}, ['page.html', 'plain.txt'])
        for name, suffix, escaped in [('page','.html','&lt;&amp;&gt;'),('plain','.txt','<&>')]:
            result = getattr(module,name)('<&>')
            assert result.title == escaped
            assert str(result) == '    ' + escaped + '\n'
            expected = Template(text, filename=name+suffix)('<&>')
            assert result.title == expected.title and str(result) == str(expected)
    ''', tmp_path, record_property)


def test_compiled_callable_api_retains_identity_closure_and_errors(tmp_path, record_property):
    probe(r'''
        from functools import partial
        sentinel = object()
        def factory():
            closed = sentinel
            def f(value=3, *, named=4):
                return (closed, value, named)
            return f
        f = factory()
        template = CompiledTemplate(f, 'page.html')
        assert template.t is f and template.t.__globals__ is f.__globals__
        assert template.t.__closure__ is f.__closure__
        assert template.t.__defaults__ == (3,) and template.t.__kwdefaults__ == {'named':4}
        assert template() == (sentinel,3,4) and template(5,named=6) == (sentinel,5,6)
        assert raises(TypeError, lambda:template(1,2)).args == raises(TypeError, lambda:f(1,2)).args
        class Callable:
            def __call__(self, value=sentinel): return value
        c = Callable(); wrapped = CompiledTemplate(c, 'plain.txt')
        assert wrapped.t is c and wrapped() is sentinel
        assert CompiledTemplate(partial(c,7), 'plain.txt')() == 7
        assert CompiledTemplate(c.__call__, 'plain.txt')(8) == 8
        failure = ValueError('owned error')
        def fail(): raise failure
        assert raises(ValueError, CompiledTemplate(fail,'x')) is failure
        namespace = {'value':1,'escape_':lambda v,escape:'caller-owned'}
        exec('def f(x=2, *, y=3): return (value, escape_(x, True), y)',namespace)
        t = CompiledTemplate(namespace['f'],'page.html')
        namespace['value']=9
        t.filter = lambda value:'custom'+value
        assert t()==(9,'caller-owned',3) and t.t.__globals__ is namespace
        assert t._escape('<',True)=='custom<'
    ''', tmp_path, record_property)


def test_compiled_globals_are_live_and_nested_callees_replaceable(tmp_path, record_property):
    probe(r'''
        files = {
            'outer.html': '$def with (value)\n$:inner(value)\n$label|$template|$callback(value)',
            'inner.txt': '$def with (value)\n$value',
        }
        module = compiled(files, list(files))
        old = Template.globals.copy()
        Template.globals['label'] = 'shared'
        try:
            render = GAE_Render(module, globals={'template':'global', 'callback':lambda value:value})
            assert module.outer.t.__globals__ is module.inner.t.__globals__ is module.__dict__
            assert str(render.outer('<&>')) == '<&>\n\nshared|global|&lt;&amp;&gt;\n'
            module.label='changed';module.callback=lambda value:'B'+value
            module.inner=lambda value:'replacement'
            assert str(render.outer('<&>')) == 'replacement\nchanged|global|B&lt;&amp;&gt;\n'
        finally:
            Template.globals.clear();Template.globals.update(old)
    ''', tmp_path, record_property)


def test_cross_module_calls_do_not_change_either_filter(tmp_path, record_property):
    probe(r'''
        first = compiled({'outer.html':'$def with (value)\n$:other(value)\n$value'}, ['outer.html'], 'first')
        second = compiled({'plain.txt':'$def with (value)\n$value'}, ['plain.txt'], 'second')
        first.other = second.plain
        assert str(first.outer('<&>')) == '<&>\n\n&lt;&amp;&gt;\n'
        assert str(second.plain('<&>')) == '<&>\n'
        second.plain.filter=lambda value:'P'+value
        assert str(first.outer('<&>')) == 'P<&>\n\n&lt;&amp;&gt;\n'
        assert first.outer.t.__globals__ is first.__dict__
        assert second.plain.t.__globals__ is second.__dict__
    ''', tmp_path, record_property)


def test_custom_filter_reentrancy_and_raw_interpolation(tmp_path, record_property):
    probe(r'''
        text = '$def with (value)\n$value|$:value'
        module = compiled({'page.html':text,'plain.txt':text}, ['page.html','plain.txt'])
        calls=[]
        def page_filter(value):
            calls.append(('page',value))
            nested = str(module.plain(value))
            return 'H['+nested.rstrip('\n')+']'
        def plain_filter(value):
            calls.append(('plain',value))
            return 'P'+value
        module.page.filter=page_filter;module.plain.filter=plain_filter
        assert str(module.page('<&>')) == 'H[P<&>|<&>]|<&>\n'
        assert calls == [('page','<&>'),('plain','<&>')]
        module.page.filter=None
        assert str(module.page('<&>')) == '<&>|<&>\n'
        assert str(module.plain('<&>')) == 'P<&>|<&>\n'
    ''', tmp_path, record_property)


def test_simultaneous_compiled_renders_have_instance_helpers(tmp_path, record_property):
    probe(r'''
        from concurrent.futures import ThreadPoolExecutor
        from threading import Barrier
        text='$def with (value)\n$value'
        module=compiled({'page.html':text,'plain.txt':text},['page.html','plain.txt'])
        barrier=Barrier(2)
        def filtered(prefix):
            def f(value):
                barrier.wait(timeout=5)
                return prefix+value
            return f
        module.page.filter=filtered('H');module.plain.filter=filtered('P')
        with ThreadPoolExecutor(max_workers=2) as pool:
            first=pool.submit(lambda:str(module.page('<&>')))
            second=pool.submit(lambda:str(module.plain('<&>')))
            assert first.result(timeout=10)=='H<&>\n'
            assert second.result(timeout=10)=='P<&>\n'
    ''', tmp_path, record_property)


def test_generated_nested_functions_join_and_default_arguments(tmp_path, record_property):
    probe(r'''
        text = '$def with (value="<&>", *args, named="N", **kw)\n$def inner(x):\n    $x\n$var title: $value\n$:inner(value)\n$named|$args[0]|$kw["extra"]'
        module=compiled({'page.html':text,'plain.txt':text},['page.html','plain.txt'])
        for name, escaped in [('page','&lt;&amp;&gt;'),('plain','<&>')]:
            t=getattr(module,name)
            result=t('<&>', 'A', named='B', extra='C')
            assert result.title==escaped
            assert str(result)==escaped+'\n\nB|A|C\n'
            assert t.t.__defaults__==('<&>',) and t.t.__kwdefaults__=={'named':'N'}
            assert raises(IndexError,lambda:t(extra='C'))
            assert raises(KeyError,lambda:t('<&>','A')).args==('extra',)
    ''', tmp_path, record_property)


def test_join_helper_bound_to_its_compiled_owner(tmp_path, record_property):
    probe(r'''
        old=CompiledTemplate._join
        def join(self,*values):
            return Path(self.filename).suffix+old(self,*values)
        CompiledTemplate._join=join
        try:
            text='$def with (value)\n$var title: $value\nbody'
            module=compiled({'page.html':text,'plain.txt':text},['page.html','plain.txt'])
            assert module.page('<&>').title=='.html&lt;&amp;&gt;'
            assert module.plain('<&>').title=='.txt<&>'
        finally:
            CompiledTemplate._join=old
    ''', tmp_path, record_property)


@pytest.mark.parametrize('source,kind', [
    ('$code:\n    import os\ntext', 'SecurityError'),
    ('$def with (obj)\n$ obj.secret = 1\ntext', 'SecurityError'),
    ('$def with (\ntext', 'SyntaxError'),
])
def test_compiler_keeps_template_validation(source, kind, tmp_path, record_property):
    probe(r'''
        source, kind = ''' + repr((source,kind)) + r'''
        root=Path.cwd()/'rejected';root.mkdir()
        (root/'page.html').write_text(source)
        error=raises({'SecurityError':SecurityError,'SyntaxError':SyntaxError}[kind], lambda:compile_templates(str(root)))
        assert type(error).__name__==kind
        assert '__import__' not in web.template.TEMPLATE_BUILTINS
    ''', tmp_path, record_property)


def test_nested_package_import_boundary_unchanged(tmp_path, record_property):
    probe(r'''
        root=Path.cwd()/'nested';(root/'child').mkdir(parents=True)
        (root/'child'/'page.html').write_text('$def with (value)\n$value')
        (root/'child'/'plain.txt').write_text('$def with (value)\n$value')
        compile_templates(str(root))
        spec=importlib.util.spec_from_file_location('owned_nested',root/'__init__.py')
        module=importlib.util.module_from_spec(spec)
        error=raises(ModuleNotFoundError,lambda:spec.loader.exec_module(module))
        assert error.name=='child'
        sys.path.insert(0,str(root))
        try:
            spec.loader.exec_module(module)
            render=GAE_Render(module)
            assert str(render.child.page('<&>'))=='&lt;&amp;&gt;\n'
            assert str(render.child.plain('<&>'))=='<&>\n'
        finally:
            sys.path.remove(str(root));sys.modules.pop('child',None)
    ''', tmp_path, record_property)


@pytest.mark.parametrize('html_last', [False, True], ids=['plain-last','html-last'])
def test_cli_compile_mixed_files_without_doctests(html_last, tmp_path, record_property):
    probe(r'''
        import doctest
        import runpy
        html_last='''+repr(html_last)+r'''
        root=Path.cwd()/'cli';root.mkdir()
        files=['page.html','plain.txt']
        if html_last: files.reverse()
        for name in files: (root/name).write_text('$def with (value)\n$value')
        walk=os.walk;seen=[]
        def ordered(path):
            assert Path(path)==root
            for directory,dirs,names in walk(path):
                assert Path(directory)==root and set(names)==set(files)
                names[:]=files;seen.append(names[:]);yield directory,dirs,names
        os.walk=ordered
        sys.argv=['web.template','--compile',str(root)]
        try:
            runpy.run_module('web.template',run_name='__main__',alter_sys=True)
        finally:
            os.walk=walk
        assert seen==[files] and doctest.master is None
        path=root/'__init__.py'
        spec=importlib.util.spec_from_file_location('owned_cli',path)
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        assert str(module.page('<&>'))=='&lt;&amp;&gt;\n'
        assert str(module.plain('<&>'))=='<&>\n'
        print(json.dumps({'cli':'module-entry --compile','attempted':0,'compile_order':seen,
                          'generated_source':path.read_text(),'generated_sha256':hashlib.sha256(path.read_bytes()).hexdigest()}))
    ''', tmp_path, record_property)


@pytest.mark.parametrize('literal', [
    '"""first\\nsecond"""',
    '"""first\n    <&>\n    last"""',
    'r"""first\n    \\n<&>\n    last"""',
    '"first\\\n    <&>"',
])
def test_compiler_preserves_multiline_literal_values(literal, tmp_path, record_property):
    probe(r'''
        literal='''+repr(literal)+r'''
        text='$code:\n    value = '+literal+'\n$:value'
        direct=Template(text,filename='page.html')
        module=compiled({'page.html':text},['page.html'])
        assert str(module.page())==str(direct())
        assert '<&>' in str(module.page()) or str(module.page())=='first\nsecond\n'
        assert module.page.t.__name__==module.page.t.__qualname__=='page'
    ''', tmp_path, record_property)


def test_same_name_global_lookup_is_not_captured_by_factory(tmp_path, record_property):
    probe(r'''
        text='$def with (value)\n$:page(value)'
        module=compiled({'page.html':text},['page.html'])
        original=module.page
        module.page=lambda value:'replacement '+value
        assert str(original('<&>'))=='replacement <&>\n'
        assert original.t.__globals__ is module.__dict__
        assert original.t.__name__==original.t.__qualname__=='page'
        error=raises(TypeError,lambda:original())
        assert str(error)=="page() missing 1 required positional argument: 'value'"
    ''', tmp_path, record_property)
