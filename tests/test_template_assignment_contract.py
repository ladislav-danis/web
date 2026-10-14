"""Benign assignment validation regressions, not an untrusted-template sandbox.

Use real Template construction/rendering in the existing guarded -I -B child.
Only new owned namespaces/lists and inert private/name markers are supplied.
"""
import pytest

from .test_template_security_contract import probe


def rejected(statement, tmp_path, record_property, *, private=1, diagnostic="attribute 'x'"):
    probe(r'''
        from types import SimpleNamespace
        statement, private, diagnostic = ''' + repr((statement, private, diagnostic)) + r'''
        box = SimpleNamespace(x=1, _private=private, items=[1])
        alias, items, private_alias = box, box.items, box._private
        before = (box.x, list(items), list(private) if isinstance(private, list) else private)
        source = '$def with(a)\n$code:\n    total = 1\n    ' + statement + '\n$total'
        try:
            error = raises(SecurityError, lambda: Template(source, globals={'__review_marker': 1}))
            assert diagnostic in str(error), str(error)
        finally:
            assert box is alias and box.items is items and box._private is private_alias
            assert (box.x, list(items), list(private) if isinstance(private, list) else private) == before
        print(json.dumps({'statement': statement, 'construction_rejected': True, 'rendered': False,
                          'owned_unchanged': True, 'identity_preserved': True}))
    ''', tmp_path, record_property)


def test_augmented_attribute_target_rejected_at_construction(tmp_path, record_property):
    rejected('a.x += 1', tmp_path, record_property)


@pytest.mark.parametrize('statement', [
    '(a.x, y) = (2, 3)',
    '((a.x, y), z) = ((4, 3), 5)',
    '[a.x, y] = [2, 3]',
    '[x, [y, a.x]] = [2, [3, 4]]',
    '([x, a.x], z) = ([2, 3], 4)',
    'local = (a.x, y) = (2, 3)',
], ids=['tuple', 'nested-tuple', 'list', 'nested-list', 'mixed', 'chained'])
def test_unpacking_attribute_target_rejected_at_construction(statement, tmp_path, record_property):
    rejected(statement, tmp_path, record_property)


@pytest.mark.parametrize('statement,private,diagnostic', [
    ('total += a._private', 1, "attribute '_private'"),
    ('total += __review_marker', 1, "name '__review_marker'"),
    ('a._private[0] += 1', [1], "attribute '_private'"),
    ('a.items[a._private] += 1', 0, "attribute '_private'"),
    ('a.items[__review_marker] += 1', 1, "name '__review_marker'"),
    ('a.items[0] += a._private', 1, "attribute '_private'"),
    ('total += (value := 1)', 1, "'NamedExpr'"),
    ('__review_marker += 1', 1, "name '__review_marker'"),
], ids=['local-private-rhs', 'local-name-rhs', 'private-target-container',
        'private-target-index', 'name-target-index', 'subscript-private-rhs',
        'disallowed-rhs-node', 'restricted-target-name'])
def test_augmented_assignment_visits_children(statement, private, diagnostic, tmp_path, record_property):
    rejected(statement, tmp_path, record_property, private=private, diagnostic=diagnostic)


@pytest.mark.parametrize('syntax', ['code', 'assignment'])
@pytest.mark.parametrize('statement,output', [
    ('total = a.x + 1', '$total'),
    ('first = total = a.x + 1', '$first'),
    ('total, other = (2, 3)', '$total'),
    ('[total, other] = [2, 3]', '$total'),
    ('((total, other), last) = ((2, 3), 4)', '$total'),
    ('[other, (total, last)] = [3, (2, 4)]', '$total'),
], ids=['single', 'chained', 'tuple', 'list', 'nested-tuple', 'mixed'])
def test_local_assignment_and_unpacking_render(statement, output, syntax, tmp_path, record_property):
    probe(r'''
        from types import SimpleNamespace
        statement, output, syntax = ''' + repr((statement, output, syntax)) + r'''
        box = SimpleNamespace(x=1)
        source = '$def with(a)\n' + ('$code:\n    ' if syntax == 'code' else '$ ') + statement + '\n' + output
        template = Template(source)
        assert box.x == 1
        assert str(template(box)) == '2\n'
        assert box.x == 1
    ''', tmp_path, record_property)


@pytest.mark.parametrize('operator,value,expected', [
    ('+=', 3, '11'), ('-=', 3, '5'), ('*=', 3, '24'), ('/=', 2, '4.0'),
    ('//=', 3, '2'), ('%=', 3, '2'), ('**=', 2, '64'), ('<<=', 1, '16'),
    ('>>=', 1, '4'), ('&=', 3, '0'), ('|=', 3, '11'), ('^=', 3, '11'),
])
def test_local_augmented_operators_render(operator, value, expected, tmp_path, record_property):
    probe(r'''
        operator, value, expected = ''' + repr((operator, value, expected)) + r'''
        template = Template('$def with(value)\n$ total = 8\n$ total ' + operator + ' value\n$total')
        assert str(template(value)) == expected + '\n'
    ''', tmp_path, record_property)


@pytest.mark.parametrize('statement', ['a.x = 3', 'a.x += 1', '(a.x, y) = (2, 3)', '[y, (z, a.x)] = [2, (3, 4)]'])
def test_assignment_line_rejects_attribute_targets(statement, tmp_path, record_property):
    probe(r'''
        from types import SimpleNamespace
        box = SimpleNamespace(x=1)
        statement = ''' + repr(statement) + r'''
        error = raises(SecurityError, lambda: Template('$def with(a)\n$ ' + statement + '\n$a.x'))
        assert "attribute 'x'" in str(error)
        assert box.x == 1
    ''', tmp_path, record_property)


def test_attribute_target_rejection_does_not_stop_rhs_validation(tmp_path, record_property):
    # Additional characterization: both independent diagnostics must be present.
    probe(r'''
        from types import SimpleNamespace
        box = SimpleNamespace(x=1, _private=2)
        error = raises(SecurityError, lambda: Template('$def with(a)\n$ a.x += a._private\n$a.x'))
        assert "attribute 'x'" in str(error) and "attribute '_private'" in str(error)
        assert box.x == 1 and box._private == 2
    ''', tmp_path, record_property)


@pytest.mark.parametrize('statement', [
    'first, *rest = [1, 2, 3]',
    '(first, [second, *rest]) = (1, [2, 3])',
    'first, *a.x = [1, 2, 3]',
])
def test_starred_unpacking_remains_disallowed(statement, tmp_path, record_property):
    rejected(statement, tmp_path, record_property, diagnostic="'Starred'")


@pytest.mark.parametrize('statement', [
    'total = a._private',
    'total = __review_marker',
    '(total, other) = (a._private, 2)',
    '[total, __review_marker] = [1, 2]',
    'a.items[a._private] = 2',
])
def test_plain_assignment_retains_subtree_restrictions(statement, tmp_path, record_property):
    diagnostic = "name '__review_marker'" if '__review_marker' in statement else "attribute '_private'"
    rejected(statement, tmp_path, record_property, private=0, diagnostic=diagnostic)


@pytest.mark.parametrize('statement', [
    'a.items[0] = 2',
    'a.items[0] += a.x',
    'a.items[0], local = (2, 3)',
    '[local, (a.items[0], other)] = [3, (2, 4)]',
    'a.items[:] = [2]',
])
def test_public_item_assignment_capability_is_retained(statement, tmp_path, record_property):
    probe(r'''
        from types import SimpleNamespace
        box = SimpleNamespace(x=1, items=[1])
        alias, items = box, box.items
        statement = ''' + repr(statement) + r'''
        template = Template('$def with(a)\n$code:\n    ' + statement + '\n$a.items[0]')
        assert box.items is items and items == [1]
        assert str(template(box)) == '2\n'
        assert box is alias and box.items is items and items == [2] and box.x == 1
    ''', tmp_path, record_property)
