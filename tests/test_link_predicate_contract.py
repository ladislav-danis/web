"""A-008 callable filtering contracts, isolated from Core and network.

Public methods parse actual AppBrowser response bytes at the get_soup seam with
stdlib HTMLParser (flat anchors only). This is limited integration, not legacy
BeautifulSoup/ClientForm certification. No request or filtering method is faked.
"""
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from .test_readme_contract import BOOTSTRAP, WEB_ROOT
from .test_browser_contract import APP, PARSER_SEAM


def predicate_probe(source, tmp_path, record_property):
    result = subprocess.run(
        [sys.executable, '-I', '-B', '-c', BOOTSTRAP + '\n' + source,
         str(WEB_ROOT.parent)],
        cwd=tmp_path,
        env={'PATH': os.defpath, 'PYTHON_DOTENV_DISABLED': '1',
             'TMPDIR': str(tmp_path), 'HOME': str(tmp_path)},
        text=True, capture_output=True, timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    evidence = json.loads(result.stdout)
    record_property('standalone_result', json.dumps(evidence, sort_keys=True))
    return evidence


ANCHORS = r'''
from web.browser import Browser
class Anchor(dict):
    def __init__(self, text, href=None):
        super().__init__({} if href is None else {'href': href})
        self.string = text
b = Browser()
def same(actual, expected):
    assert len(actual) == len(expected)
    assert all(a is e for a, e in zip(actual, expected))
'''


def test_empty_list_never_calls_predicate(tmp_path, record_property):
    predicate_probe(ANCHORS + r'''
visited = []
result = b._filter_links([], predicate=lambda link: visited.append(link) or True)
assert result == [] and visited == []
print(json.dumps({'result': result, 'predicate_calls': len(visited)}))
''', tmp_path, record_property)


def test_callable_preserves_order_duplicate_identity_and_truthiness(tmp_path, record_property):
    predicate_probe(ANCHORS + r'''
first, rejected, equal_but_distinct = [Anchor('Next', '/next') for _ in range(3)]
links = [first, rejected, equal_but_distinct, first]
visited = []
def accept(link):
    visited.append(link)
    return [] if link is rejected else ['truthy, not necessarily bool']
result = b._filter_links(links, predicate=accept)
same(result, [first, equal_but_distinct, first])
same(visited, links)
same(links, [first, rejected, equal_but_distinct, first])
assert result is not links
print(json.dumps({'accepted_indices': [0, 2, 0], 'predicate_calls': len(visited),
                  'input_order_unchanged': True, 'duplicate_identity_preserved': True}))
''', tmp_path, record_property)


@pytest.mark.parametrize('criteria', [
    {'text': 'Next'}, {'text_regex': '^Next$'},
    {'url': '/next'}, {'url_regex': '^/next$'},
    {'text': 'Next', 'text_regex': '^Next$', 'url': '/next', 'url_regex': '^/next$'},
], ids=['text', 'text-regex', 'url', 'url-regex', 'all-four'])
def test_builtin_filters_and_callable_short_circuit(tmp_path, record_property, criteria):
    predicate_probe(ANCHORS + '\ncriteria = ' + repr(criteria) + r'''
accepted = Anchor('Next', '/next')
rejected_by_callable = Anchor('Next', '/next')
wrong_text = Anchor('Other', '/next')
wrong_url = Anchor('Next', '/other')
links = [wrong_text, accepted, wrong_url, rejected_by_callable, accepted]
visited = []
def accept(link):
    visited.append(link)
    return link is accepted
result = b._filter_links(links, predicate=accept, **criteria)
same(result, [accepted, accepted])
expected = [accepted, rejected_by_callable, accepted]
if not any(k.startswith('text') for k in criteria):
    expected.insert(0, wrong_text)
if not any(k.startswith('url') for k in criteria):
    expected = [accepted, wrong_url, rejected_by_callable, accepted]
same(visited, expected)
# An earlier criterion rejects every candidate: callable must not run at all.
visited.clear()
assert b._filter_links(links, text='missing', predicate=accept) == []
assert visited == []
print(json.dumps({'criteria': criteria, 'accepted_count': len(result),
                  'expected_candidate_calls': len(expected), 'nonmatch_calls': len(visited)}))
''', tmp_path, record_property)


def test_regex_search_and_absent_anchor_values(tmp_path, record_property):
    predicate_probe(ANCHORS + r'''
missing = Anchor(None)
matching = Anchor('prefix Next suffix', '/prefix/next?q=1')
visited = []
result = b._filter_links([missing, matching], text_regex='Next', url_regex='/next',
                        predicate=lambda link: visited.append(link) or True)
same(result, [matching])
same(visited, [matching])
print(json.dumps({'regex_uses_search': True, 'missing_values_rejected': True,
                  'predicate_calls': len(visited)}))
''', tmp_path, record_property)


@pytest.mark.parametrize('boundary', ['none', 'falsy-callable'])
def test_retained_predicate_truthiness_boundary(tmp_path, record_property, boundary):
    predicate_probe(ANCHORS + '\nboundary = ' + repr(boundary) + r'''
class FalsyCallable:
    def __bool__(self):
        return False
    def __call__(self, link):
        raise AssertionError('Existing falsy-predicate boundary must stay unchanged')
links = [Anchor('Next', '/next'), Anchor('Other', '/other')]
predicate = None if boundary == 'none' else FalsyCallable()
same(b._filter_links(links, predicate=predicate), links)
same(b._filter_links(links, text='Next', predicate=predicate), links[:1])
print(json.dumps({'retained_boundary': boundary, 'predicate_calls': 0}))
''', tmp_path, record_property)


@pytest.mark.parametrize('method', ['_filter_links', 'get_links', 'find_link', 'follow_link'])
def test_predicate_exception_propagates_unchanged(tmp_path, record_property, method):
    predicate_probe(APP + PARSER_SEAM + '\nmethod = ' + repr(method) + r'''
soup = b.get_soup()
b.get_soup = lambda: soup
anchors = soup.anchors
visited = []
class PredicateFailure(Exception):
    pass
failure = PredicateFailure('owned predicate sentinel')
def fail_on_second(link):
    visited.append(link)
    if link is anchors[1]:
        raise failure
    return False
before = (b.path, b.url, b.data, b.status, b._response)
try:
    getattr(b, method)(*([anchors] if method == '_filter_links' else []),
                       predicate=fail_on_second)
except PredicateFailure as error:
    assert error is failure
else:
    raise AssertionError('Predicate exception swallowed')
assert len(visited) == 2 and all(a is e for a, e in zip(visited, anchors))
assert all(a is e for a, e in zip((b.path, b.url, b.data, b.status, b._response), before))
print(json.dumps({'method': method, 'exception_identity': True, 'predicate_calls': 2,
                  'navigation_state_unchanged': True, 'scope': 'flat-anchor parser seam'}))
''', tmp_path, record_property)


@pytest.mark.parametrize('method', ['get_links', 'find_link', 'follow_link'])
@pytest.mark.parametrize('empty', [False, True], ids=['rejected-links', 'empty-page'])
def test_public_no_match_does_not_navigate(tmp_path, record_property, method, empty):
    predicate_probe(APP + '\nempty = ' + repr(empty) + r'''
gets = []
original_get = Page.GET
def tracked_get(self):
    gets.append([web.ctx.method, web.ctx.path])
    return '' if empty else original_get(self)
Page.GET = tracked_get
''' + PARSER_SEAM + '\nmethod = ' + repr(method) + r'''
from web.browser import BrowserError
soup = b.get_soup()
b.get_soup = lambda: soup
visited = []
def reject(link):
    visited.append(link)
    return False
if method == 'follow_link':
    try:
        b.follow_link(predicate=reject)
    except BrowserError as error:
        assert str(error) == 'No link found'
    else:
        raise AssertionError('Followed a missing link')
else:
    result = getattr(b, method)(predicate=reject)
    assert result == ([] if method == 'get_links' else None)
assert len(visited) == (0 if empty else 2)
assert all(a is e for a, e in zip(visited, soup.anchors))
assert gets == [['GET', '/']]
assert b.path == '/' and b.status == 200
print(json.dumps({'method': method, 'empty': empty, 'predicate_calls': len(visited),
                  'GETs': gets, 'scope': 'actual AppBrowser, flat-anchor parser seam'}))
''', tmp_path, record_property)
