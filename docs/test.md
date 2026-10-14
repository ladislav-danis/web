# Web Test Utilities Documentation

`web.test` wraps Python's `unittest` and `doctest`; it is not pytest discovery
and does not automatically combine the two kinds of tests. Import it explicitly.
A successful result with **zero executed tests is not evidence of coverage**.
Check both the intended selection and the result.

## Functions

### `load_modules(names)`

Accepts iterable module names and returns a list of module objects in order.
Dotted names resolve to the named submodule, not just the top-level package.
Imports execute module-level code; import errors propagate. This example only
imports modules, **it does not run tests**:

```python
import web.test

modules = web.test.load_modules(['web.db', 'web.template'])
assert [module.__name__ for module in modules] == ['web.db', 'web.template']
```

### `module_suite(module, classnames=None)`

Accepts an imported module. Selection precedence is:

1. A **truthy** `classnames` collection goes to
   `unittest.TestLoader().loadTestsFromNames(classnames, module)`. Names may
   identify classes or dotted methods relative to the module, e.g.
   `['SampleTests.test_add']`.
2. Otherwise, if the module has a `suite` attribute, call `module.suite()`.
3. Otherwise, use `unittest.TestLoader().loadTestsFromModule(module)`.

An empty list therefore does not mean “select nothing”: it follows steps 2–3.
The custom factory controls its returned suite; exceptions propagate. Invalid
selectors can produce unittest error cases that fail when run, rather than an
immediate loader exception. This does not discover pytest-style free functions
or automatically add docstrings.

### `suite(module_names)`

Imports each named module, calls `module_suite(module)`, and adds its result to a
new `TestSuite`. **This is the unittest/custom-suite path, not doctest loading.**
In particular, `suite(['web.db', 'web.template'])` currently contains zero cases.
Use actual TestCase-bearing modules, as in the sample below, or explicitly use
`doctest_suite` for docstrings.

### `doctest_suite(module_names)`

Imports each named module and adds `doctest.DocTestSuite(module)` to a new
`TestSuite`. Each discovered doctest-bearing docstring contributes a
`DocTestCase`, which may contain several `>>>` examples. `countTestCases()` and
`result.testsRun` count these unittest cases, **not individual doctest examples**.
Building a suite does not execute it or establish that its expectations pass.

### `runTests(suite)`

Constructs a default `unittest.TextTestRunner()` and returns its real result
(normally `unittest.TextTestResult`). It prints the normal runner report, by
default to stderr. Inspect `testsRun`, `failures`, `errors` and `wasSuccessful()`.
It does **not** exit the process on failed tests. For a script/CI gate, explicitly
raise `SystemExit(1)` on an unsuccessful result, as the examples do.
Construct a fresh suite for each run; unittest may consume its case references.

### `main(suite=None)`

With a truthy supplied suite, runs that suite without interpreting CLI selectors.
With a falsy value (including the default `None`), imports `__main__`, removes
all argument tokens starting with `-`, and passes the remaining tokens (or
`None` if empty) to `module_suite`. An ordinary empty `unittest.TestSuite()` is
truthy: it is run as zero tests, not replaced by discovery.

This is **not unittest's full option parser**: `-v`, `-q`, `--help` and other
hyphen-prefixed tokens are discarded, not implemented as options. A separate
value following a discarded token remains a selector. No switch here changes
TextTestRunner verbosity. Use only the class/method selectors shown below.
After the runner returns, `main` calls `sys.exit(not result.wasSuccessful())`:
exit 0 for success, 1 for reported failures/errors. Import or suite-construction
exceptions may propagate before a result exists. A zero-test suite can also
exit 0, so inspect selection counts rather than relying on the exit code alone.

## Classes

`TestCase` is exactly `unittest.TestCase`; `TestSuite` is exactly
`unittest.TestSuite`, not framework-specific subclasses.

## Usage Examples

### Sample module

Save this exact code as `runner_sample.py` in a disposable working directory.
Use an environment where this checkout's `web` package is importable (from the
Core root, set `PYTHONPATH` to the absolute `src` path). Run later examples from
that directory so `runner_sample` is importable. No application configuration,
database or optional database driver is needed. Each later Python block is a
separate script with its own imports; no interactive namespace is assumed.

```python
import web.test


def double(value):
    """Double a number.

    >>> double(3)
    6
    >>> double(-1)
    -2
    """
    return value * 2


class SampleTests(web.test.TestCase):
    def test_add(self):
        self.assertEqual(2 + 3, 5)

    def test_upper(self):
        self.assertEqual('web'.upper(), 'WEB')


if __name__ == '__main__':
    web.test.main()
```

### Running Specific Tests

This selects two real unittest methods, not the doctests in `double`.

```python
import web.test
import runner_sample

selected = web.test.module_suite(runner_sample, ['SampleTests'])
assert selected.countTestCases() == 2
result = web.test.runTests(selected)
if not result.wasSuccessful():
    raise SystemExit(1)
assert result.testsRun == 2
```

### Using Doctests

This runs the one `runner_sample.double` DocTestCase containing two examples;
it does not run `SampleTests`.

```python
import web.test

selected = web.test.doctest_suite(['runner_sample'])
assert selected.countTestCases() == 1
result = web.test.runTests(selected)
if not result.wasSuccessful():
    raise SystemExit(1)
assert result.testsRun == 1
```

### Custom Test Suite

Explicitly combine two unittest methods and one DocTestCase. The report is
three cases, not four; the two doctest examples belong to one case.

```python
import web.test

selected = web.test.suite(['runner_sample'])
assert selected.countTestCases() == 2
selected.addTest(web.test.doctest_suite(['runner_sample']))
assert selected.countTestCases() == 3
result = web.test.runTests(selected)
if not result.wasSuccessful():
    raise SystemExit(1)
assert result.testsRun == 3
```

### Command Line Usage

Run these commands in the sample directory with the same Python environment.
They execute respectively two, two and one unittest methods. The method selector
is relative to the script's `__main__` module.

```bash
python runner_sample.py
python runner_sample.py SampleTests
python runner_sample.py SampleTests.test_add
```

`python -m web.db TestDatabase` is **not** a class selector. That module's
entry point calls `doctest.testmod()`, `test_parser()` and `test_safeeval()`
directly; it does not call `web.test.main()` or use that argument. Its current
doctest failures also do not force a nonzero process exit. Do not use it as a
class-selection recipe or a green CI gate.

### Failing control

Save as `runner_failure.py` alongside the sample. This is deliberately wrong:
running it must report one failed unittest and exit 1. It is a negative control,
not part of the successful sample suite.

```python
import web.test


class FailureTests(web.test.TestCase):
    def test_failure(self):
        self.assertEqual(2 + 2, 5)


if __name__ == '__main__':
    web.test.main()
```

### Negative CLI controls

Run each independently and inspect its exit status. The first runs the deliberate
failure (one failure, exit 1). The second selects an absent class (one loader
error case, exit 1), not zero silently successful tests.

```bash
python runner_failure.py FailureTests.test_failure
python runner_sample.py NoSuchClass
```

### Inventory is not execution

This diagnostic only builds suites and counts examples; it does not run them.
On this pinned revision, `web.db` has 23 DocTestCases / 83 examples,
`web.template` 18 / 124, and `web.form` 22 / 45. Thus the old db+template unit
suite is empty, while their doctest suite has 41 cases, not 41 examples. The old
custom suite only ran the added form doctests. Counts may change with source.

```python
import doctest
import web.test

for module in web.test.load_modules(['web.db', 'web.template', 'web.form']):
    units = web.test.module_suite(module).countTestCases()
    docs = web.test.doctest_suite([module.__name__]).countTestCases()
    examples = sum(len(test.examples) for test in doctest.DocTestFinder().find(module))
    print(module.__name__, 'unit cases:', units,
          'doctest cases:', docs, 'doctest examples:', examples)
```

On the audited Python 3.13 environment, the DB doctests now pass all 83 examples
in 23 DocTestCases ([web#34](https://git.home.arpa/mosaic-ai/web/issues/34)).
Template doctests pass all 124 examples in 18 cases after
[web#32](https://git.home.arpa/mosaic-ai/web/issues/32) and application-side date
formatting in [web#33](https://git.home.arpa/mosaic-ai/web/issues/33); direct
restricted-template `strftime` remains unsupported. These results do not make
all framework docstrings a green quickstart: form still has 21 failing cases
out of 22 (45 examples inventoried), tracked in
[web#35](https://git.home.arpa/mosaic-ai/web/issues/35).
Failing cases and failing examples are different units. The DB module CLI now
returns 1 for doctest failure and 0 for success, after its parser and safe-eval
checks; `TestDatabase` is still ignored, not a class selector.
