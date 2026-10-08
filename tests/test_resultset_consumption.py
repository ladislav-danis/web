"""Forward-only result consumption on real, owned SQLite cursors.

The db.query path is primary. BaseResultSet/ResultSet cursor cases exercise
shared consumption only, not PostgreSQL/MySQL or their rowcount semantics.
All iterator probes use a fixed number of next calls, never unbounded list(r).
"""
import sqlite3

import pytest

import web
from web.db import BaseResultSet, ResultSet, SqliteResultSet


@pytest.fixture
def query(tmp_path):
    database = web.database(dbn="sqlite", db=str(tmp_path / "resultset.db"))
    database.printing = False
    database.query("CREATE TABLE rows (n INTEGER PRIMARY KEY, label TEXT)")
    for n in (1, 2, 3, 4):
        database.insert("rows", n=n, label="row-%s" % n)

    def select(count=4):
        result = database.query(
            "SELECT n, label FROM rows WHERE n <= $count ORDER BY n",
            vars={"count": count},
        )
        assert isinstance(result, SqliteResultSet)
        return result

    try:
        yield select
    finally:
        database.ctx.db.close()


@pytest.fixture(params=["db-query", "base-sqlite-cursor", "result-sqlite-cursor"])
def result_factory(request, query):
    if request.param == "db-query":
        yield query
    else:
        connection = sqlite3.connect(":memory:")
        cls = BaseResultSet if request.param == "base-sqlite-cursor" else ResultSet

        def select(count=4):
            cursor = connection.execute(
                "SELECT n, 'row-' || n AS label FROM "
                "(SELECT 1 AS n UNION ALL SELECT 2 UNION ALL SELECT 3 UNION ALL SELECT 4) "
                "WHERE n <= ? ORDER BY n", (count,)
            )
            return cls(cursor)

        try:
            yield select
        finally:
            connection.close()


def test_forward_index_leap_consumes_exact_rows(result_factory):
    result = result_factory()
    assert result[2] == {"n": 3, "label": "row-3"}
    assert result._index == 3
    assert next(result) == {"n": 4, "label": "row-4"}
    assert result._index == 4
    with pytest.raises(IndexError):
        result[4]
    assert result._index == 4


def test_list_includes_buffered_head_exactly_once(query):
    result = query()
    assert bool(result)
    assert [row.n for row in result.list()] == [1, 2, 3, 4]
    assert result._index == 4
    assert result.list() == []
    assert result._index == 4
    assert not result
    with pytest.raises(StopIteration):
        next(result)
    assert result._index == 4


def test_next_alias_obeys_buffer_and_mixed_access(query):
    result = query()
    assert bool(result)
    assert result.next() == {"n": 1, "label": "row-1"}
    assert result._index == 1
    assert bool(result)
    assert result[1] == {"n": 2, "label": "row-2"}
    assert result._index == 2
    assert bool(result)
    assert result.first() == {"n": 3, "label": "row-3"}
    assert result._index == 3
    assert bool(result)
    assert result.list() == [{"n": 4, "label": "row-4"}]
    assert result._index == 4
    assert not result
    with pytest.raises(StopIteration):
        result.next()
    assert result._index == 4


@pytest.mark.parametrize("count,expected", [
    (0, []),
    (1, [{"n": 1, "label": "row-1"}]),
    (4, [{"n": 1, "label": "row-1"}, {"n": 2, "label": "row-2"},
         {"n": 3, "label": "row-3"}, {"n": 4, "label": "row-4"}]),
])
def test_list_remaining_and_repeated_exhaustion(result_factory, count, expected):
    result = result_factory(count)
    assert result.list() == expected
    assert result._index == count
    for _ in range(2):
        assert result.list() == []
        assert result.first() is None
        sentinel = object()
        assert result.first(sentinel) is sentinel
        with pytest.raises(StopIteration):
            next(result)
        with pytest.raises(StopIteration):
            result.next()
        with pytest.raises(IndexError):
            result[count]
        assert result._index == count


def test_first_means_next_remaining_and_default_only_when_empty(result_factory):
    result = result_factory()
    sentinel = object()
    assert result.first(sentinel) == {"n": 1, "label": "row-1"}
    assert result._index == 1
    assert result.first() == {"n": 2, "label": "row-2"}
    assert result._index == 2
    assert result.next() == {"n": 3, "label": "row-3"}
    assert result._index == 3
    assert result.list() == [{"n": 4, "label": "row-4"}]
    assert result.first(sentinel) is sentinel
    assert result._index == 4


def test_index_rejects_negative_repeated_backward_and_past_end(result_factory):
    result = result_factory()
    with pytest.raises(IndexError):
        result[-1]
    assert result._index == 0
    assert result[0] == {"n": 1, "label": "row-1"}
    assert result._index == 1
    for index in (-1, 0):
        with pytest.raises(IndexError):
            result[index]
        assert result._index == 1
    assert result[2] == {"n": 3, "label": "row-3"}
    assert result._index == 3
    for index in (0, 1, 2):
        with pytest.raises(IndexError):
            result[index]
        assert result._index == 3
    with pytest.raises(IndexError):
        result[9]
    assert result._index == 4  # The last real row was consumed, not nine rows.
    with pytest.raises(IndexError):
        result[9]
    assert result._index == 4
    assert result.list() == []


@pytest.mark.parametrize("access", ["next", "alias", "first", "index", "list"])
def test_single_buffered_row_consumed_by_each_access(query, access):
    result = query(1)
    assert [bool(result), bool(result)] == [True, True]
    assert result._index == 0
    operations = {
        "next": lambda: next(result),
        "alias": result.next,
        "first": result.first,
        "index": lambda: result[0],
        "list": lambda: result.list()[0],
    }
    assert operations[access]() == {"n": 1, "label": "row-1"}
    assert result._index == 1
    assert [bool(result), bool(result)] == [False, False]
    assert result.list() == []
    assert result.first("empty") == "empty"
    with pytest.raises(StopIteration):
        next(result)
    assert result._index == 1


def test_repeated_bool_on_empty_never_consumes(query):
    result = query(0)
    for _ in range(3):
        assert not result
        assert result._index == 0
        assert result.first("empty") == "empty"
        assert result.list() == []
        with pytest.raises(StopIteration):
            result.next()
        assert result._index == 0


def test_peek_index_leap_and_list_keep_remaining_order(query):
    result = query()
    assert bool(result)
    with pytest.raises(IndexError):
        result[-1]
    assert result._index == 0
    assert result[2] == {"n": 3, "label": "row-3"}
    assert result._index == 3
    assert [bool(result), bool(result)] == [True, True]
    with pytest.raises(IndexError):
        result[2]
    assert result._index == 3
    assert result.list() == [{"n": 4, "label": "row-4"}]
    assert result.list() == []
    assert result._index == 4
    assert not result


def test_sqlite_len_remains_unsupported_and_does_not_consume(query):
    result = query()
    assert bool(result)
    with pytest.raises(TypeError):
        len(result)
    assert result._index == 0
    assert next(result).n == 1


def test_resultset_sqlite_cursor_rowcount_is_not_a_backend_count():
    # A real SQLite SELECT exposes -1: this is not MySQL/PostgreSQL coverage.
    connection = sqlite3.connect(":memory:")
    try:
        result = ResultSet(connection.execute("SELECT 1 AS n"))
        assert result.cursor.rowcount == -1
        assert result.__len__() == -1
        with pytest.raises(ValueError):
            len(result)
        assert result._index == 0
        assert next(result) == {"n": 1}
        assert result.__len__() == -1
        assert result._index == 1
    finally:
        connection.close()


def test_repeated_bool_then_bounded_next_consumes_head_once(query):
    result = query(3)
    assert iter(result) is result
    assert [bool(result), bool(result)] == [True, True]
    assert result._index == 0
    assert [next(result) for _ in range(3)] == [
        {"n": 1, "label": "row-1"},
        {"n": 2, "label": "row-2"},
        {"n": 3, "label": "row-3"},
    ]
    assert result._index == 3
    for _ in range(2):
        with pytest.raises(StopIteration):
            next(result)
        assert not result
        assert result._index == 3
