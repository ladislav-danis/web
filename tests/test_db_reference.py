"""DB reference contracts against real module exports and temporary SQLite.

Runtime characterizations do not claim new production fixes or external-driver
coverage. Markdown fences are executed from their actual bytes, never copies.
"""
import ast
from pathlib import Path
import re

import web
import pytest

from .test_readme_contract import probe


DOC = Path(__file__).resolve().parents[1] / 'docs' / 'db.md'


def test_documented_exports_match_source_and_package():
    section = DOC.read_text().split('## `__all__` Exports\n', 1)[1].split('## See Also', 1)[0]
    names = re.findall(r'^- `([\w]+)(?:\([^`]*\))?`:', section, re.M)
    tree = ast.parse(Path(web.db.__file__).read_bytes())
    source_all = next(ast.literal_eval(node.value) for node in tree.body
                      if isinstance(node, ast.Assign)
                      and any(isinstance(t, ast.Name) and t.id == '__all__' for t in node.targets))
    assert names == source_all == web.db.__all__
    namespace = {}
    exec('from web.db import *', namespace)
    assert set(namespace) - {'__builtins__'} == set(names)
    for name in names:
        assert namespace[name] is getattr(web.db, name) is getattr(web, name)
    for name in ('BaseResultSet', 'ResultSet', 'SqliteResultSet', 'Transaction',
                 'PostgresDB', 'MySQLDB', 'SqliteDB', 'FirebirdDB', 'MSSQLDB',
                 'OracleDB', 'sqlwhere', 'sqlify', 'import_driver',
                 'register_database', 'dburl2dict', 'SQLInjectionError'):
        assert hasattr(web.db, name)
        assert name not in namespace
        assert not hasattr(web, name)
    assert web.sqlparam is web.SQLParam
    assert web.sqlliteral is web.SQLLiteral


@pytest.mark.parametrize('heading', [
    '### `import_driver(drivers, preferred=None)`',
    '### `dburl2dict(url)`',
    '## `__all__` Exports',
    '#### Executable identifier and value example',
])
def test_db_markdown_fence_bytes(heading, tmp_path, record_property):
    probe('heading = ' + repr(heading) + '\n' + r'''
import hashlib
import re
path = Path(web.__file__).with_name('docs') / 'db.md'
lines = path.read_bytes().splitlines(keepends=True)
active = False
in_fence = False
section = []
for line in lines:
    if not in_fence and line.rstrip().decode() == heading:
        active = True
        continue
    if active and not in_fence and line.startswith(b'#'):
        # Subheadings are part of the section, not boundaries.
        level = len(heading) - len(heading.lstrip('#'))
        new_level = len(line) - len(line.lstrip(b'#'))
        if new_level <= level:
            break
    if active:
        section.append(line)
    if line.startswith(b'```'):
        in_fence = not in_fence
fences = re.findall(rb'^```python\n(.*?)^```', b''.join(section), re.M | re.S)
assert len(fences) == 1, (heading, len(fences))
opened = []
def memory_only(event, args):
    if event == 'sqlite3.connect':
        assert args[0] == ':memory:'
        opened.append(args[0])
sys.addaudithook(memory_only)
namespace = {'__name__': '__main__'}
if fences[0].lstrip().startswith(b'>>>'):
    # Existing URL examples use a REPL transcript; compare dictionary values,
    # not historical repr ordering. Execute the unchanged expression bytes.
    import ast
    import doctest
    from web.db import dburl2dict
    for example in doctest.DocTestParser().get_examples(fences[0].decode()):
        assert eval(example.source, {'dburl2dict': dburl2dict}) == ast.literal_eval(example.want)
else:
    exec(compile(fences[0], str(path) + ':' + heading, 'exec'), namespace)
if heading.startswith('####'):
    assert opened == [':memory:']
    assert namespace['remaining_names'] == ['updated', 'second', 'third']
    try:
        namespace['db'].ctx.db.execute('SELECT 1')
    except namespace['db'].db_module.ProgrammingError:
        pass
    else:
        raise AssertionError('example must close its SQLite connection')
else:
    assert not opened
print(json.dumps({'heading': heading, 'fence_sha256': hashlib.sha256(fences[0]).hexdigest(),
                  'databases': opened}))
''', tmp_path, record_property)


def test_driver_selection_real_imports():
    import importlib.util
    import sqlite3
    from web.db import import_driver
    missing = '_web5_nonexistent_driver_68241'
    assert importlib.util.find_spec(missing) is None
    assert import_driver((missing, 'sqlite3')) is sqlite3
    for falsy in (None, '', False):
        assert import_driver((missing, 'sqlite3'), preferred=falsy) is sqlite3
    with pytest.raises(ImportError, match='Unable to import ' + missing):
        import_driver(('sqlite3',), preferred=missing)
    assert import_driver((missing,), preferred='sqlite3') is sqlite3


def test_url_literal_and_encoded_values():
    from web.db import dburl2dict
    for literal, expected in [('***', '***'), ('fictitious', 'fictitious'), ('d%40y', 'd@y')]:
        assert dburl2dict('postgres://james:' + literal + '@serverfarm.example.net:5432/mygreatdb') == {
            'pw': expected, 'dbn': 'postgres', 'db': 'mygreatdb',
            'host': 'serverfarm.example.net', 'user': 'james', 'port': 5432}


def test_url_source_password_examples_are_consistent():
    # Tool displays can redact URL passwords; evaluate actual source bytes.
    import doctest
    from web.db import dburl2dict
    examples = [example for example in doctest.DocTestParser().get_examples(dburl2dict.__doc__)
                if ' == ' in example.source]
    assert len(examples) == 5
    for example in examples:
        assert example.want == 'True\n'
        assert eval(compile(example.source, web.db.__file__, 'eval'),
                    {'dburl2dict': dburl2dict}) is True


@pytest.fixture
def sqlite_db(tmp_path):
    db = web.database(dbn='sqlite', db=str(tmp_path / 'reference.db'))
    db.printing = False
    connection = db.ctx.db
    try:
        yield db
    finally:
        connection.close()


def test_identifier_grammar_matches_actual_boundaries():
    from web.db import _sql_safe_identifier, SQLInjectionError
    for name in ('users', '_private', 'User_2', '"table name"', '"user-data"',
                 '""'):
        assert _sql_safe_identifier(name) == name
    for name in ('public.users', '', None, 3, b'users', '9users', 'café',
                 '"a\nb"', 'users\nextra', 'users;DROP TABLE users',
                 '"a"; "b"', 'users\n', '"users"\n'):
        with pytest.raises(SQLInjectionError):
            _sql_safe_identifier(name)


@pytest.mark.parametrize('bad', ['public.users', '', None, 7])
@pytest.mark.parametrize('method', ['insert', 'multiple_insert', 'update', 'delete'])
def test_dml_rejected_table_before_test_return(bad, method):
    from web.db import DB, SQLInjectionError
    db = DB(None, {})  # Real builder, no driver or mocked implementation.
    calls = {
        'insert': lambda: db.insert(bad, _test=True, name='x'),
        'multiple_insert': lambda: db.multiple_insert(bad, [{'name': 'x'}], _test=True),
        'update': lambda: db.update(bad, where='id=1', _test=True, name='x'),
        'delete': lambda: db.delete(bad, where='id=1', _test=True),
    }
    # update treats non-string tables as an iterable, not one identifier.
    error = TypeError if method == 'update' and bad in (None, 7) else SQLInjectionError
    with pytest.raises(error):
        calls[method]()


@pytest.mark.parametrize('multiple', [False, True])
def test_multiple_insert_validation_and_early_returns(multiple):
    from web.db import DB, SQLInjectionError
    db = DB(None, {})
    db.supports_multiple_insert = multiple
    assert db.multiple_insert(None, [], _test=True) == []
    with pytest.raises(SQLInjectionError):
        db.multiple_insert('users', [{'bad.name': 'x'}], _test=True)
    with pytest.raises(ValueError if multiple else SQLInjectionError):
        db.multiple_insert('users', [{'name': 'x'}, {'bad.name': 'y'}], _test=True)
    # Optimized mode checks same-key equality before building any query;
    # fallback delegates each row to insert and permits different valid keys.
    if multiple:
        with pytest.raises(ValueError, match='Not all rows have the same keys'):
            db.multiple_insert('users', [{'name': 'x'}, {'other': 'y'}], _test=True)
        with pytest.raises(SQLInjectionError):
            db.multiple_insert('users', [{1: 'x'}], _test=True)
        empty_row = db.multiple_insert('users', [{}], _test=True)
        assert empty_row.query() == 'INSERT INTO users () VALUES ()'
    else:
        queries = db.multiple_insert('users', [{'name': 'x'}, {'other': 'y'}], _test=True)
        assert [q.values() for q in queries] == [['x'], ['y']]
        assert db.multiple_insert('users', [{'name': 'x'}], seqname=False, _test=True) is None
        with pytest.raises(TypeError):  # Python keyword argument boundary.
            db.multiple_insert('users', [{1: 'x'}], _test=True)
        assert db.multiple_insert('users', [{}], _test=True)[0].query() == 'INSERT INTO users DEFAULT VALUES'


def test_validated_columns_tables_using_and_empty_values():
    from web.db import DB, SQLInjectionError
    db = DB(None, {})
    for bad in ('', 'public.name'):
        with pytest.raises(SQLInjectionError):
            db.insert('users', _test=True, **{bad: 'x'})
        with pytest.raises(SQLInjectionError):
            db.update('users', where='id=1', _test=True, **{bad: 'x'})
        with pytest.raises(SQLInjectionError):
            db.update(['users', bad], where='id=1', _test=True, name='x')
        with pytest.raises(SQLInjectionError):
            db.delete('users', where='id=1', using=['users', bad], _test=True)
    with pytest.raises(SQLInjectionError):
        db.delete('users', where='id=1', using=1, _test=True)
    for using in (None, '', [], (), 0):
        assert str(db.delete('users', where='', using=using, _test=True)) == 'DELETE FROM users'
    assert db.delete('users', where={}, _test=True) == 'DELETE FROM users'
    assert str(db.delete('users', where='', using=['other', 'third'], _test=True)) == 'DELETE FROM users USING other, third'
    assert db.insert('users', _test=True).query() == 'INSERT INTO users DEFAULT VALUES'
    assert db.update('users', where='', _test=True).query() == 'UPDATE users SET  WHERE '
    assert db.update([], where='1=0', _test=True, name='x').query() == 'UPDATE  SET name = %s WHERE 1=0'
    for method in (db.update, db.delete):
        with pytest.raises(AttributeError):
            method('users', where=None, _test=True)
    with pytest.raises(TypeError):
        db.update('users', where={}, name='x', _test=True)


def test_raw_select_where_and_literal_are_not_identifier_validation():
    from web.db import DB, SQLLiteral, sqlwhere
    db = DB(None, {})
    query = db.select('public.users AS u', what='u.name, count(*)',
                      where='u.name=$name OR 1=1', vars={'name': "O'Reilly"},
                      group='u.name', order='u.name DESC', limit=2, offset=1, _test=True)
    assert query.query() == 'SELECT u.name, count(*) FROM public.users AS u WHERE u.name=%s OR 1=1 GROUP BY u.name ORDER BY u.name DESC LIMIT %s OFFSET %s'
    assert query.values() == ["O'Reilly", 2, 1]
    assert db.select('users', where={}, _test=True).query() == 'SELECT * FROM users WHERE'
    assert db.select('users', where=None, _test=True).query() == 'SELECT * FROM users'
    assert db.where('users', _test=True).query() == 'SELECT * FROM users'
    assert db.where('public.users', _test=True, **{'id + 0': 3}).query() == 'SELECT * FROM public.users WHERE id + 0 = %s'
    for method in (db.update, db.delete):
        query = method('users', where={'id + 0': 3}, _test=True, **({'name': 'x'} if method == db.update else {}))
        assert 'WHERE id + 0 = %s' in query.query()
    assert sqlwhere((('id + 0', 3),)).query() == 'id + 0 = %s'
    query = db.insert('users', name=SQLLiteral('upper(\'literal\')'), _test=True)
    assert query.query() == "INSERT INTO users (name) VALUES (upper('literal'))"
    assert query.values() == []


@pytest.mark.parametrize('multiple', [False, True])
def test_real_sqlite_identifiers_and_bound_values(sqlite_db, multiple):
    db = sqlite_db
    db.query('CREATE TABLE "user data" (id INTEGER PRIMARY KEY, "display name" TEXT)')
    payload = "O'Reilly'); DROP TABLE users; --"
    query = db.insert('"user data"', **{'"display name"': payload}, _test=True)
    assert query.query('qmark') == 'INSERT INTO "user data" ("display name") VALUES (?)'
    assert query.values() == [payload]
    assert db.insert('"user data"', **{'"display name"': payload}) == 1
    db.supports_multiple_insert = multiple
    db.multiple_insert('"user data"', [{'"display name"': 'second'}, {'"display name"': 'third'}])
    assert [r['display name'] for r in db.select('"user data"', order='id')] == [payload, 'second', 'third']
    assert db.update('"user data"', where='id=$id', vars={'id': 1}, **{'"display name"': 'updated'}) == 1
    assert db.delete('"user data"', where='"display name"=$name', vars={'name': 'second'}) == 1
    assert [r['display name'] for r in db.select('"user data"', order='id')] == ['updated', 'third']
