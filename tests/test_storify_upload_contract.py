"""storify upload contracts in fresh guard-first -I -B children.

Real multipart HTTP requests are distinct from direct Python-list/default probes.
The guards isolate these tests; they are not an OS sandbox.
"""
import hashlib
import json
import os
import subprocess
import sys
import textwrap

import pytest

from .test_template_security_contract import BOOTSTRAP, WEB_ROOT


def probe(source, tmp_path, record_property):
    env = {'PATH': os.defpath, 'PYTHON_DOTENV_DISABLED': '1', 'LC_ALL': 'C'}
    for key in ('HOME', 'TMPDIR', 'XDG_CACHE_HOME', 'XDG_DATA_HOME', 'XDG_CONFIG_HOME'):
        env[key] = str(tmp_path)
    program = BOOTSTRAP + '\n' + textwrap.dedent(source) + '''
assert not {'core', 'modules', 'dotenv'}.intersection(sys.modules)
assert not blocked
print(json.dumps({'completed': True, 'isolated': sys.flags.isolated,
                  'no_bytecode': sys.dont_write_bytecode}))
'''
    argv = [sys.executable, '-I', '-B', '-c', program, str(WEB_ROOT.parent)]
    result = subprocess.run(argv, cwd=tmp_path, env=env, text=True,
                            capture_output=True, timeout=30)
    record_property('child_argv', json.dumps(argv))
    record_property('child_environment', json.dumps(env))
    record_property('program_sha256', hashlib.sha256(program.encode()).hexdigest())
    record_property('probe_stdout', result.stdout)
    record_property('probe_stderr', result.stderr)
    record_property('child_returncode', result.returncode)
    assert result.returncode == 0, result.stdout + result.stderr
    outcome = json.loads(result.stdout.splitlines()[-1])
    assert outcome == {'completed': True, 'isolated': 1, 'no_bytecode': True}


MULTIPART = r'''
def multipart(parts):
    body = b''
    for name, filename, value in parts:
        disposition = 'Content-Disposition: form-data; name="' + name + '"'
        if filename is not None:
            disposition += '; filename="' + filename + '"'
        body += b'--owned-boundary\r\n' + disposition.encode('ascii')
        body += b'\r\n\r\n' + value + b'\r\n'
    return body + b'--owned-boundary--\r\n'
HEADERS = {'Content-Type': 'multipart/form-data; boundary=owned-boundary'}
'''


def test_required_upload_preserves_optional_http_bytes(tmp_path, record_property):
    probe(MULTIPART + r'''
class Upload:
    def POST(self):
        values = web.input('name') if web.ctx.path == '/required' else web.input()
        return json.dumps({'type': type(values.name).__name__, 'hex': values.name.hex()})
app = web.application(('/.*', Upload), {}, autoreload=False)
body = multipart([('name', 'owned.txt', b'Alice')])
rows = []
for path in ['/optional', '/required']:
    response = app.request(path, method='POST', data=body, headers=HEADERS)
    rows.append({'path': path, 'status': response.status, 'parsed': json.loads(response.data)})
print(json.dumps(rows))
assert all(row['status'] == '200 OK' for row in rows)
assert rows[0]['parsed'] == {'type': 'bytes', 'hex': b'Alice'.hex()}
assert rows[1]['parsed'] == rows[0]['parsed'], rows
assert dict(web.ctx.items()) == {}
''', tmp_path, record_property)


@pytest.mark.parametrize('payload', [b'Z\xc3\xa9Z', b'\xff\x00\xfe', b''],
                         ids=['utf8', 'nonutf8-nul', 'empty'])
@pytest.mark.parametrize('required', [(), ('name',), ('name', 'name', 'name')],
                         ids=['optional', 'required', 'repeated-required'])
def test_multipart_exact_bytes(payload, required, tmp_path, record_property):
    probe(MULTIPART + 'payload, required = ' + repr((payload, required)) + '\n' + r'''
class Upload:
    def POST(self):
        value = web.input(*required).name
        assert type(value) is bytes
        return value
app = web.application(('/', Upload), {}, autoreload=False)
response = app.request('/', method='POST', data=multipart([('name', 'owned.bin', payload)]),
                       headers=HEADERS)
print(json.dumps({'status': response.status, 'hex': response.data.hex()}))
assert (response.status, response.data) == ('200 OK', payload)
''', tmp_path, record_property)


@pytest.mark.parametrize('mode', ['scalar', 'list', 'dict'])
@pytest.mark.parametrize('required', [(), ('name', 'name')], ids=['optional', 'required'])
def test_repeated_multipart_preserves_parser_last_part_and_raw_identity(
        mode, required, tmp_path, record_property):
    probe(MULTIPART + 'mode, required = ' + repr((mode, required)) + '\n' + r'''
trace = []
class ObservedFile:
    def __init__(self, handle): self.handle = handle
    def read(self, *args):
        trace.append('read')
        return self.handle.read(*args)
    def seek(self, *args):
        trace.append('seek')
        return self.handle.seek(*args)
    def tell(self): return self.handle.tell()
    def close(self): return self.handle.close()
class Upload:
    def POST(self):
        raw = web.webapi.rawinput()
        part = raw.name
        assert not isinstance(part, list)
        assert part.filename == 'last.bin' and part.file.tell() == 0
        part.file = ObservedFile(part.file)
        defaults = {'name': []} if mode == 'list' else {'name': {}} if mode == 'dict' else {}
        try:
            value = web.input(*required, **defaults).name
            if mode == 'dict':
                assert value is part
                assert trace == [] and part.file.tell() == 0  # no premature read
                value = part.file.read()
            elif mode == 'list':
                assert value == [b'last\xff\x00'] and type(value[0]) is bytes
                value = value[0]
            else:
                assert type(value) is bytes
            assert value == b'last\xff\x00'
            return value
        finally:
            part.close()
app = web.application(('/', Upload), {}, autoreload=False)
response = app.request('/', method='POST', headers=HEADERS,
    data=multipart([('name', 'first.bin', b'first'), ('name', 'last.bin', b'last\xff\x00')]))
assert (response.status, response.data) == ('200 OK', b'last\xff\x00')
print(json.dumps({'mode': mode, 'trace': trace, 'hex': response.data.hex()}))
''', tmp_path, record_property)


@pytest.mark.parametrize('defaults', [{}, {'name': 'fallback'}, {'name': []},
                                     {'name': {}}, {'name': ()}],
                         ids=['absent', 'scalar', 'list', 'dict', 'tuple'])
def test_missing_required_multipart_remains_http400(defaults, tmp_path, record_property):
    probe(MULTIPART + 'defaults = ' + repr(defaults) + '\n' + r'''
accepted = []
class Upload:
    def POST(self):
        web.input('name', 'name', **defaults)
        accepted.append(True)
        return 'accepted'
app = web.application(('/', Upload), {}, autoreload=False)
response = app.request('/', method='POST', headers=HEADERS,
                       data=multipart([('other', 'owned.bin', b'Alice')]))
assert (response.status, response.data) == ('400 Bad Request', b'bad request')
assert accepted == [] and dict(web.ctx.items()) == {}
print(json.dumps({'status': response.status, 'body': response.data.decode()}))
''', tmp_path, record_property)


def test_multipart_neighbor_text_and_repeated_query_conversion_order(tmp_path, record_property):
    probe(MULTIPART + r'''
converted = []
def convert(value):
    converted.append(value)
    return value.upper()
class Upload:
    def POST(self):
        values = web.input('name', 'text', 'name', text='fallback',
                           query=[], repeated=[], absent=7, _unicode=convert)
        assert list(values) == ['name', 'text', 'query', 'repeated', 'absent']
        assert values == {'name': b'Alice', 'text': 'ZÉZ', 'query': ['ONE', 'TWO'],
                          'repeated': ['LAST'], 'absent': 7}
        assert converted == ['ZéZ', 'one', 'two', 'last'], converted
        return values.name
app = web.application(('/.*', Upload), {}, autoreload=False)
response = app.request('/?query=one&query=two', method='POST', headers=HEADERS,
    data=multipart([('name', 'owned.txt', b'Alice'), ('text', None, 'ZéZ'.encode()),
                    ('repeated', None, b'first'), ('repeated', None, b'last')]))
assert (response.status, response.data) == ('200 OK', b'Alice')
''', tmp_path, record_property)


@pytest.mark.parametrize('mode', ['false', 'true', 'callable'])
def test_mapping_getters_required_first_once_and_unicode_policy(mode, tmp_path, record_property):
    probe('mode = ' + repr(mode) + '\n' + r'''
from collections.abc import Mapping
trace = []
class Value:
    def __init__(self, value): self.stored = value
    @property
    def value(self):
        trace.append(('value', self.stored))
        return self.stored
class Values(Mapping):
    def __iter__(self):
        trace.append(('keys',))
        return iter(['a', 'b', 'c', 'items'])
    def __len__(self): return 4
    def __getitem__(self, key):
        trace.append(('get', key))
        return Value({'a': 'alpha', 'b': 'beta', 'c': b'\xff', 'items': 'method-key'}[key])
def convert(value):
    trace.append(('convert', value))
    return value.upper()
policy = {'false': False, 'true': True, 'callable': convert}[mode]
result = web.storify(Values(), 'b', 'a', 'b', _unicode=policy)
assert list(result) == ['b', 'a', 'c', 'items']
expected = [('keys',)]
for key, value in [('b', 'beta'), ('a', 'alpha'), ('c', b'\xff'), ('items', 'method-key')]:
    expected += [('get', key), ('value', value)]
    if mode == 'callable' and isinstance(value, str): expected.append(('convert', value))
assert trace == expected, trace
assert result['c'] == b'\xff' and type(result['c']) is bytes
assert result['a'] == ('ALPHA' if mode == 'callable' else 'alpha')
assert result['items'] == ('METHOD-KEY' if mode == 'callable' else 'method-key')
print(repr(trace))
''', tmp_path, record_property)


@pytest.mark.parametrize('required', [(), ('a', 'a')], ids=['optional', 'required'])
def test_plain_lists_dict_tuple_scalar_and_absent_defaults(required, tmp_path, record_property):
    probe('required = ' + repr(required) + '\n' + r'''
from io import BytesIO
inner = web.storage(value='inside')
first, last = web.storage(value='first'), web.storage(value='last')
assert web.storify({'a': [first, last]}, *required).a == 'last'
assert web.storify({'a': [first, last]}, *required, a={}).a is last
assert web.storify({'a': [first, last]}, *required, a=[]).a == ['first', 'last']
assert web.storify({'a': inner}, *required, a={}).a is inner
assert web.storify({'a': inner}, *required, a=[]).a == ['inside']
assert web.storify({'a': inner}, *required, a=()).a == ('inside',)
assert web.storify({'a': ('x', 'y')}, *required, a=()).a == ('x', 'y')
assert web.storify({'a': 'kept'}, *required, a=('not-empty',)).a == 'kept'
assert web.storify({'a': '7'}, *required, a=0).a == '7'
assert web.storify({'a': ''}, *required, a='fallback').a == ''
assert web.storify({'a': None}, *required, a='fallback').a is None
assert web.storify({'a': []}, *required, a=[]).a == []
raises(IndexError, lambda: web.storify({'a': []}, *required))
missing_list, missing_dict = [], {}
result = web.storify({}, a=missing_list, b=missing_dict, c=(), d=7, e=None)
assert result == {'a': [], 'b': {}, 'c': (), 'd': 7, 'e': None}
assert result.a is missing_list and result.b is missing_dict
for default in [[], {}, (), 'fallback']:
    error = raises(KeyError, lambda: web.storify({}, 'a', a=default))
    assert error.args == ('a',)
''', tmp_path, record_property)


@pytest.mark.parametrize('kind', ['bytesio', 'disk', 'nonseekable'])
@pytest.mark.parametrize('as_list', [False, True])
def test_real_stream_current_position_read_once_without_seek(kind, as_list, tmp_path, record_property):
    probe('kind, as_list = ' + repr((kind, as_list)) + '\n' + r'''
from io import BytesIO
trace = []
if kind == 'disk':
    handle = open('owned.bin', 'w+b')
    handle.write(b'prefix-Alice\xff\x00')
else:
    handle = BytesIO(b'prefix-Alice\xff\x00')
handle.seek(7)
class Reader:
    def read(self, *args):
        trace.append('read')
        return handle.read(*args)
class SeekableReader(Reader):
    def seek(self, *args):
        trace.append('seek')
        return handle.seek(*args)
reader = Reader() if kind == 'nonseekable' else SeekableReader()
value = web.storage(file=reader, raw=True)
try:
    result = web.storify({'name': [value] if as_list else value},
                         'name', 'name', name=[] if as_list else None).name
    assert result == ([b'Alice\xff\x00'] if as_list else b'Alice\xff\x00'), result
    assert trace == ['read'], trace
    assert handle.tell() == len(b'prefix-Alice\xff\x00')
    assert not handle.closed
finally:
    handle.close()
''', tmp_path, record_property)


@pytest.mark.parametrize('mode', ['last', 'list', 'dict'])
@pytest.mark.parametrize('required', [(), ('name', 'name')], ids=['optional', 'required'])
def test_plain_upload_list_conversion_and_identity(mode, required, tmp_path, record_property):
    probe('mode, required = ' + repr((mode, required)) + '\n' + r'''
from io import BytesIO
handles = [BytesIO(b'first'), BytesIO(b'last')]
reads = [0, 0]
class Reader:
    def __init__(self, index): self.index = index
    def read(self):
        reads[self.index] += 1
        return handles[self.index].read()
parts = [web.storage(file=Reader(i), raw=True) for i in range(2)]
try:
    defaults = {'name': []} if mode == 'list' else {'name': {}} if mode == 'dict' else {}
    value = web.storify({'name': parts}, *required, **defaults).name
    if mode == 'dict':
        assert value is parts[-1] and reads == [0, 0]
    elif mode == 'list':
        assert value == [b'first', b'last'] and reads == [1, 1], (value, reads)
    else:
        assert value == b'last' and reads == [0, 1], (value, reads)
finally:
    for handle in handles: handle.close()
''', tmp_path, record_property)


def test_distinct_keys_alias_one_stream_are_not_rewound(tmp_path, record_property):
    probe(r'''
from io import BytesIO
handle = BytesIO(b'Alice')
value = web.storage(file=handle, raw=True)
try:
    result = web.storify({'first': value, 'second': value})
    assert result == {'first': b'Alice', 'second': b''}
    assert handle.tell() == 5
finally:
    handle.close()
''', tmp_path, record_property)


def test_raw_getter_behavior_and_dict_bypass_are_preserved(tmp_path, record_property):
    probe(r'''
from io import BytesIO
trace = []
class Part:
    def __init__(self): self.file = BytesIO(b'Alice')
    @property
    def raw(self):
        trace.append('raw-getter')
        return b'marker'
part = Part()
try:
    assert web.storify({'name': part}, 'name', 'name', name={}).name is part
    assert trace == [] and part.file.tell() == 0
    assert web.storify({'name': part}).name == b'Alice'
    assert trace == ['raw-getter']
finally:
    part.file.close()
''', tmp_path, record_property)


@pytest.mark.parametrize('stage', ['mapping', 'value', 'raw', 'read'])
@pytest.mark.parametrize('kind', ['key', 'io', 'base'])
def test_original_exception_identity_and_no_later_conversion(stage, kind, tmp_path, record_property):
    probe('stage, kind = ' + repr((stage, kind)) + '\n' + r'''
from collections.abc import Mapping
from io import BytesIO
class Signal(BaseException): pass
error = {'key': KeyError('owned'), 'io': OSError('owned'), 'base': Signal('owned')}[kind]
trace = []
handle = BytesIO(b'Alice')
class Reader:
    def read(self):
        trace.append('read')
        assert handle.read(1) == b'A'
        raise error
class Part:
    file = Reader()
    @property
    def raw(self):
        trace.append('raw')
        if stage == 'raw': raise error
        return True
class Value:
    @property
    def value(self):
        trace.append('value')
        raise error
class Values(Mapping):
    def __iter__(self): return iter(['name', 'later'])
    def __len__(self): return 2
    def __getitem__(self, key):
        trace.append(('get', key))
        assert key == 'name'
        if stage == 'mapping': raise error
        return Value() if stage == 'value' else Part()
try:
    actual = raises(type(error), lambda: web.storify(Values(), 'name', 'name'))
    assert actual is error
    assert trace == [('get', 'name')] + {'mapping': [], 'value': ['value'],
                                       'raw': ['raw'], 'read': ['raw', 'read']}[stage]
finally:
    handle.close()
''', tmp_path, record_property)


@pytest.mark.parametrize('kind', ['key', 'io'])
def test_input_keeps_existing_read_error_boundary(kind, tmp_path, record_property):
    probe(MULTIPART + 'kind = ' + repr(kind) + '\n' + r'''
original = KeyError('owned read') if kind == 'key' else OSError('owned read')
observed = []
class Upload:
    def POST(self):
        part = web.webapi.rawinput().name
        handle = part.file
        class Reader:
            def tell(self): return handle.tell()
            def seek(self, *args): return handle.seek(*args)
            def read(self, *args):
                handle.read(1)
                raise original
            def close(self): handle.close()
        part.file = Reader()
        try:
            return web.input('name').name
        except Exception as error:
            observed.append(error)
            raise
        finally:
            part.close()
app = web.application(('/', Upload), {}, autoreload=False)
response = app.request('/', method='POST', headers=HEADERS,
                       data=multipart([('name', 'owned.bin', b'Alice')]))
if kind == 'key':
    assert (response.status, response.data) == ('400 Bad Request', b'bad request')
    assert len(observed) == 1 and isinstance(observed[0], web.BadRequest)
    assert observed[0].__context__ is original
else:
    assert response.status == '500 Internal Server Error'
    assert observed == [original] and observed[0] is original
print(json.dumps({'status': response.status, 'kind': kind}))
''', tmp_path, record_property)


def test_file_raw_shape_fallbacks_and_none_file_error(tmp_path, record_property):
    probe(r'''
from io import BytesIO
handle = BytesIO(b'Alice')
try:
    file_only = web.storage(file=handle)
    raw_only = web.storage(raw=True)
    assert web.storify({'a': file_only}, 'a').a is file_only
    assert web.storify({'a': raw_only}, 'a').a is raw_only
    assert web.storify({'a': web.storage(file=handle, value='text')}).a == 'text'
    assert web.storify({'a': web.storage(raw=True, value='text')}).a == 'text'
    assert handle.tell() == 0
    raises(AttributeError, lambda: web.storify({'a': web.storage(file=None, raw=True)}))
finally:
    handle.close()
''', tmp_path, record_property)
