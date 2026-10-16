"""Search's simple source example must be collected, not just rendered elsewhere."""
from .test_form_doctest_contract import FLAGS, child


SIMPLE = "Search(name='search', value='Search').render()\n"
ADVANCED = ("Search(name='search', value='Search', required='required', "
            "pattern='[a-z0-9]{2,30}', placeholder='Search...').render()\n")


def test_simple_search_is_collected_before_advanced(tmp_path, record_property):
    result, data = child(FLAGS + r'''
import doctest
cases = [c for c in doctest.DocTestFinder().find(module) if c.examples]
report(cases=[c.name for c in cases], examples=sum(len(c.examples) for c in cases),
       search=[dict(ordinal=i, source=e.source, exc_msg=e.exc_msg, options=e.options)
               for c in cases if c.name == 'web.form.Search'
               for i, e in enumerate(c.examples)])
''', tmp_path, record_property)
    assert result.returncode == 0, result.stdout + result.stderr
    assert data['search'] == [
        dict(ordinal=0, source=SIMPLE, exc_msg=None, options={}),
        dict(ordinal=1, source=ADVANCED, exc_msg=None, options={}),
    ], 'The exact simple Search example must be collected before the advanced example'
    assert len(data['cases']) == len(set(data['cases'])) == 22
    assert data['examples'] == 46


def test_simple_search_doctest_matches_python3_repr_and_exact_html(tmp_path, record_property):
    result, data = child(FLAGS + r'''
import ast
import doctest
cases = [c for c in doctest.DocTestFinder().find(module) if c.name == 'web.form.Search']
assert len(cases) == 1 and len(cases[0].examples) == 2
observations = []
class Capture(doctest.DocTestRunner):
    def record(self, test, example, got):
        observations.append(dict(ordinal=test.examples.index(example), source=example.source,
                                 want=example.want, got=got))
    def report_success(self, out, test, example, got):
        self.record(test, example, got)
        super().report_success(out, test, example, got)
    def report_failure(self, out, test, example, got):
        self.record(test, example, got)
        super().report_failure(out, test, example, got)
runner = Capture()
assert runner.optionflags == 0 and type(runner._checker) is doctest.OutputChecker
runner.run(cases[0])
# Historical Python 2 want: compare its literal HTML value, never a normalized DOM.
legacy = ''' + repr("u'<input id=\"search\" name=\"search\" type=\"search\" value=\"Search\"/>'") + r'''
assert observations[0]['source'] == "Search(name='search', value='Search').render()\n"
assert ast.literal_eval(legacy).encode('utf-8') == ast.literal_eval(observations[0]['got']).encode('utf-8')
assert ast.literal_eval(legacy) == ast.literal_eval(observations[0]['want'])
report(attempted=runner.tries, failed=runner.failures, observations=observations,
       legacy_html=ast.literal_eval(legacy))
''', tmp_path, record_property)
    assert result.returncode == 0, result.stdout + result.stderr
    assert data['attempted'] == len(data['observations']) == 2
    assert [row['source'] for row in data['observations']] == [SIMPLE, ADVANCED]
    assert data['failed'] == 0, result.stdout
