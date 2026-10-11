"""Single-token DML identifier contracts on isolated, owned SQLite.

These tests do not certify external driver dialects or arbitrary raw SQL.
"""
import json
import os
import subprocess
import sys
import textwrap

import pytest

from .test_readme_contract import BOOTSTRAP, WEB_ROOT


SQLITE_SETUP = r'''
from web.db import SQLInjectionError

def owned_sqlite(event, args):
    if event == 'sqlite3.connect':
        assert args[0] == ':memory:', args[0]
    if event in {'socket.gethostbyname', 'socket.gethostbyaddr', 'socket.sendto'}:
        raise AssertionError('Standalone SQL probe attempted network: ' + event)
sys.addaudithook(owned_sqlite)
db = web.database(dbn='sqlite', db=':memory:')
db.printing = False
connection = db.ctx.db
connection.executescript("CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT);"
                         "INSERT INTO users VALUES (1, 'first'), (2, 'second');")
def rows():
    return connection.execute('SELECT id, name FROM users ORDER BY id').fetchall()
before = rows()
assert before == [(1, 'first'), (2, 'second')]
trace = []
connection.set_trace_callback(trace.append)
def business_dml():
    return [sql for sql in trace if sql.lstrip().upper().startswith(
        ('INSERT ', 'UPDATE ', 'DELETE ', 'REPLACE '))]
'''


def sqlite_probe(source, tmp_path, record_property):
    for name in ('data', 'logs', 'home', 'cache'):
        (tmp_path / name).mkdir(exist_ok=True)
    env = {'PATH': os.defpath, 'PYTHON_DOTENV_DISABLED': '1',
           'TMPDIR': str(tmp_path), 'HOME': str(tmp_path / 'home'),
           'XDG_CACHE_HOME': str(tmp_path / 'cache'),
           'DATA_DIR': str(tmp_path / 'data'), 'LOG_DIR': str(tmp_path / 'logs'),
           'SALT': 'identifier-contract-only', 'SESSION_SECRET_KEY': 'identifier-contract-only',
           'API_URL': 'https://external.invalid', 'API_KEY': 'identifier-contract-only',
           'API_TOKEN': 'identifier-contract-only'}
    program = (BOOTSTRAP + SQLITE_SETUP + '\ntry:\n' +
               textwrap.indent(textwrap.dedent(source), '    ') +
               '\nfinally:\n    connection.close()\n')
    result = subprocess.run([sys.executable, '-I', '-B', '-c', program,
                             str(WEB_ROOT.parent)], cwd=tmp_path, env=env,
                            text=True, capture_output=True, timeout=30)
    record_property('sqlite_probe', json.dumps({'returncode': result.returncode,
                    'stdout': result.stdout, 'stderr': result.stderr}, sort_keys=True))
    assert result.returncode == 0, result.stdout + result.stderr


def test_delete_rejects_quoted_where_bypass_and_preserves_rows(tmp_path, record_property):
    sqlite_probe(r'''
        assert db.delete('users', where='id=999') == 0
        assert rows() == before
        trace.clear()
        error = None
        affected = None
        try:
            affected = db.delete('"users" WHERE 1=1 --"', where='id=999')
        except SQLInjectionError as exc:
            error = type(exc).__name__
        after = rows()
        print(json.dumps({'error': error, 'affected': affected, 'before': before,
                          'after': after, 'trace': trace, 'dml': business_dml()}))
        assert error == 'SQLInjectionError', 'quoted WHERE bypass was not rejected'
        assert after == before
        assert business_dml() == []
    ''', tmp_path, record_property)


@pytest.mark.parametrize('name', ['users\n', '"users"\n'])
def test_delete_rejects_trailing_newline_before_sql(name, tmp_path, record_property):
    sqlite_probe('name = ' + repr(name) + '\n' + textwrap.dedent(r'''
        error = None
        try:
            db.delete(name, where='id=999')
        except SQLInjectionError as exc:
            error = type(exc).__name__
        after = rows()
        print(json.dumps({'name': name, 'error': error, 'after': after,
                          'trace': trace, 'dml': business_dml()}))
        assert error == 'SQLInjectionError', 'trailing newline reached SQL execution'
        assert after == before
        assert business_dml() == []
    '''), tmp_path, record_property)


@pytest.mark.parametrize('test_mode', [False, True])
def test_delete_rejects_nul_with_identifier_error(test_mode, tmp_path, record_property):
    sqlite_probe('test_mode = ' + repr(test_mode) + '\n' + textwrap.dedent(r'''
        error = None
        try:
            db.delete('"users\x00"', where='id=999', _test=test_mode)
        except Exception as exc:
            error = type(exc).__name__
        after = rows()
        print(json.dumps({'test_mode': test_mode, 'error': error,
                          'after': after, 'trace': trace, 'dml': business_dml()}))
        assert error == 'SQLInjectionError', 'NUL was not rejected by identifier validation'
        assert after == before
        assert business_dml() == []
    '''), tmp_path, record_property)


@pytest.mark.parametrize('test_mode', [False, True])
@pytest.mark.parametrize('operation', [
    'insert-table', 'insert-default-table', 'insert-column',
    'multiple-fallback-table', 'multiple-fallback-column',
    'multiple-optimized-table', 'multiple-optimized-column',
    'update-table', 'update-list', 'update-tuple', 'update-column',
    'delete-table', 'delete-using-string', 'delete-using-list', 'delete-using-tuple',
])
def test_dml_rejects_malformed_token_before_statement(operation, test_mode,
                                                     tmp_path, record_property):
    sqlite_probe('operation = ' + repr(operation) + '\ntest_mode = ' + repr(test_mode)
                 + '\n' + textwrap.dedent(r'''
        from web.db import DB
        target = DB(None, {}) if test_mode else db
        target.supports_multiple_insert = 'optimized' in operation
        observations = []
        for bad in ('"users" WHERE 1=1 --"', '"a"; "b"', 'users\n', '"users"\n',
                    '"users\x00"', '"users', '"us"ers"', '"users" /*tail*/',
                    '"users" ', '"users"\r', '"us\ners"'):
            trace.clear()
            calls = {
                'insert-table': lambda: target.insert(tablename=bad, name='x', _test=test_mode),
                'insert-default-table': lambda: target.insert(tablename=bad, _test=test_mode),
                'insert-column': lambda: target.insert('users', **{bad: 'x'}, _test=test_mode),
                'multiple-fallback-table': lambda: target.multiple_insert(tablename=bad, values=[{'name': 'x'}], _test=test_mode),
                'multiple-fallback-column': lambda: target.multiple_insert('users', [{bad: 'x'}], _test=test_mode),
                'multiple-optimized-table': lambda: target.multiple_insert(tablename=bad, values=[{'name': 'x'}], _test=test_mode),
                'multiple-optimized-column': lambda: target.multiple_insert('users', [{bad: 'x'}], _test=test_mode),
                'update-table': lambda: target.update(tables=bad, where='id=999', name='x', _test=test_mode),
                'update-list': lambda: target.update(['users', bad], where='id=999', name='x', _test=test_mode),
                'update-tuple': lambda: target.update(('users', bad), where='id=999', name='x', _test=test_mode),
                'update-column': lambda: target.update('users', where='id=999', **{bad: 'x'}, _test=test_mode),
                'delete-table': lambda: target.delete(table=bad, where='id=999', _test=test_mode),
                'delete-using-string': lambda: target.delete('users', where='id=999', using=bad, _test=test_mode),
                'delete-using-list': lambda: target.delete('users', where='id=999', using=['users', bad], _test=test_mode),
                'delete-using-tuple': lambda: target.delete('users', where='id=999', using=('users', bad), _test=test_mode),
            }
            try:
                calls[operation]()
            except SQLInjectionError:
                pass
            else:
                raise AssertionError((operation, bad, 'accepted malformed identifier'))
            assert business_dml() == [], (operation, bad, trace)
            assert rows() == before
            observations.append({'bad': bad, 'dml': business_dml(), 'rows': rows()})
        print(json.dumps({'operation': operation, 'test_mode': test_mode,
                          'observations': observations}))
    '''), tmp_path, record_property)


@pytest.mark.parametrize('token', [
    '""', '"table name"', '"user-data"', '"a"";--"', '"a/*comment*/;"',
    '""""', '"café東京"', '"cr\rname"', '"tab\tname"', '"control\x01"',
    '"line\u2028separator"',
])
def test_quoted_table_and_column_are_one_sqlite_name(token, tmp_path, record_property):
    sqlite_probe('token = ' + repr(token) + '\n' + textwrap.dedent(r'''
        from web.db import _sql_safe_identifier
        assert _sql_safe_identifier(token) is token
        decoded = token[1:-1].replace('""', '"')
        db.query('CREATE TABLE ' + token + ' (id INTEGER PRIMARY KEY, ' + token + ' TEXT)')
        assert connection.execute('SELECT name FROM sqlite_master WHERE type="table" ORDER BY name').fetchall() == sorted([(decoded,), ('users',)])
        payload = "O'Reilly'); DELETE FROM users; --\x00"
        built = db.insert(token, **{token: payload}, _test=True)
        assert built.query('qmark') == 'INSERT INTO ' + token + ' (' + token + ') VALUES (?)'
        assert built.values() == [payload]
        assert db.insert(token, **{token: payload}) == 1
        assert connection.execute('SELECT ' + token + ' FROM ' + token).fetchall() == [(payload,)]
        assert db.update([token], where='id=$id', vars={'id': 1}, **{token: 'updated'}) == 1
        assert connection.execute('SELECT ' + token + ' FROM ' + token).fetchall() == [('updated',)]
        assert db.delete(token, where='id=999') == 0
        assert db.delete(token, where='id=$id', vars={'id': 1}) == 1
        assert connection.execute('SELECT * FROM ' + token).fetchall() == []
        assert rows() == before
        print(json.dumps({'token': token, 'decoded': decoded, 'bound_value': payload,
                          'users': rows(), 'dml': business_dml()}))
    '''), tmp_path, record_property)


@pytest.mark.parametrize('multiple', [False, True])
def test_quoted_multiple_insert_binding_and_default_insert(multiple, tmp_path, record_property):
    sqlite_probe('multiple = ' + repr(multiple) + '\n' + textwrap.dedent(r'''
        table, column = '"batch"";--"', '"value""--"'
        db.query('CREATE TABLE ' + table + ' (id INTEGER PRIMARY KEY, ' + column + " TEXT DEFAULT 'default')")
        assert db.insert(table) == 1
        db.supports_multiple_insert = multiple
        payload = "x'); DELETE FROM users; --"
        values = [{column: payload}, {column: 'last'}]
        built = db.multiple_insert(table, values, _test=True)
        queries = [built] if multiple else built
        assert [value for query in queries for value in query.values()] == [payload, 'last']
        assert list(db.multiple_insert(table, values)) == [2, 3]
        assert connection.execute('SELECT ' + column + ' FROM ' + table + ' ORDER BY id').fetchall() == [('default',), (payload,), ('last',)]
        assert db.update(table, where='id=$id', vars={'id': 2}, **{column: 'new'}) == 1
        assert db.delete(table, where='id=$id', vars={'id': 3}) == 1
        assert connection.execute('SELECT ' + column + ' FROM ' + table + ' ORDER BY id').fetchall() == [('default',), ('new',)]
        assert rows() == before
        print(json.dumps({'multiple': multiple, 'dml': business_dml(), 'users': rows()}))
    '''), tmp_path, record_property)


@pytest.mark.parametrize('multiple', [False, True])
def test_later_invalid_batch_column_preserves_validation_order(multiple, tmp_path, record_property):
    sqlite_probe('multiple = ' + repr(multiple) + '\n' + textwrap.dedent(r'''
        db.supports_multiple_insert = multiple
        try:
            db.multiple_insert('users', [{'name': 'prior-valid'}, {'"name"; "other"': 'bad'}])
        except (SQLInjectionError, ValueError) as exc:
            error = type(exc).__name__
        else:
            raise AssertionError('later malformed column was accepted')
        assert error == ('ValueError' if multiple else 'SQLInjectionError')
        # Fallback commits a valid earlier statement; no whole-batch guarantee.
        expected = before if multiple else before + [(3, 'prior-valid')]
        assert rows() == expected
        dml = business_dml()
        assert len(dml) == (0 if multiple else 1), dml
        if not multiple:
            assert dml == ["INSERT INTO users (name) VALUES ('prior-valid')"]
        print(json.dumps({'multiple': multiple, 'error': error, 'rows': rows(), 'dml': dml}))
    '''), tmp_path, record_property)


@pytest.mark.parametrize('test_mode', [False, True])
def test_using_wrong_types_reject_before_statement(test_mode, tmp_path, record_property):
    sqlite_probe('test_mode = ' + repr(test_mode) + '\n' + textwrap.dedent(r'''
        for using in (1, b'users', ['users', 1], ('users', None)):
            trace.clear()
            try:
                db.delete('users', where='id=999', using=using, _test=test_mode)
            except SQLInjectionError:
                pass
            else:
                raise AssertionError(('invalid using accepted', using))
            assert business_dml() == []
            assert rows() == before
        print(json.dumps({'test_mode': test_mode, 'rows': rows(), 'dml': business_dml()}))
    '''), tmp_path, record_property)


def test_builder_retains_valid_using_default_helper_and_raw_boundaries():
    from web.db import DB, SQLInjectionError, SQLLiteral, _sql_safe_identifier
    db = DB(None, {})
    token = '"a"";--"'
    for using in (token, [token], (token,)):
        assert db.delete('users', where='id=999', using=using, _test=True).query() == (
            'DELETE FROM users USING ' + token + ' WHERE id=999')
    assert db._get_insert_default_values_query(token) == 'INSERT INTO ' + token + ' DEFAULT VALUES'
    with pytest.raises(SQLInjectionError):
        db._get_insert_default_values_query('"users" WHERE 1=1 --"')
    for bad in (None, False, 3, b'users', [], {}, '', '9users', 'café', 'public.users'):
        with pytest.raises(SQLInjectionError):
            _sql_safe_identifier(bad)
    raw = db.select('users AS u', where='1=1 -- raw', order='u.id DESC', _test=True)
    assert raw.query() == 'SELECT * FROM users AS u WHERE 1=1 -- raw ORDER BY u.id DESC'
    literal = db.insert('users', name=SQLLiteral("upper('raw')"), seqname='raw.sequence', _test=True)
    assert literal.query() == "INSERT INTO users (name) VALUES (upper('raw'))"
    assert literal.values() == []
