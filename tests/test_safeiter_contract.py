"""Bounded safeiter contracts; subprocess guards are not an OS sandbox."""
import hashlib
import textwrap

import pytest

from .test_template_security_contract import WEB_ROOT, fences, probe

# Cap both retry observations and diagnostic output even on the broken baseline.
# A BaseException raised by the test-owned print boundary escapes its bare except.
BOUNDED = r'''
import sys
import traceback
from web.utils import safeiter
class BudgetAbort(BaseException):
    pass
class LimitedOutput:
    def __init__(self, target):
        self.target = target
        self.remaining = 12000
    def write(self, text):
        self.remaining -= len(text)
        if self.remaining < 0:
            raise BudgetAbort('test output budget')
        return self.target.write(text)
    def flush(self):
        self.target.flush()
sys.stderr = LimitedOutput(sys.stderr)
logs = []
events = []
real_print_exc = traceback.print_exc
def bounded_print_exc():
    if len(logs) >= 8:
        raise BudgetAbort('test traceback budget')
    logs.append(sys.exception())
    events.append('log')
    real_print_exc()
traceback.print_exc = bounded_print_exc
class Script:
    def __init__(self, *steps):
        self.steps = iter(steps)
        self.calls = 0
        self.iters = 0
    def __iter__(self):
        self.iters += 1
        return self
    def __next__(self):
        self.calls += 1
        events.append('next')
        step = next(self.steps)
        if isinstance(step, BaseException):
            raise step
        return step
'''


def check(source, tmp_path, record_property):
    probe(BOUNDED + '\n' + textwrap.dedent(source), tmp_path, record_property)


def test_values_are_lazy_and_preserved(tmp_path, record_property):
    check('''
        value = object()
        source = Script(value, None)
        wrapped = safeiter(source)
        assert source.iters == source.calls == 0
        actual = []
        try:
            actual.append(next(wrapped))
            assert source.calls == 1
            actual.append(next(wrapped))
        except BudgetAbort:
            pass
        assert actual == [value, None], actual
        assert actual[0] is value and source.iters == 1
        assert logs == []
    ''', tmp_path, record_property)


@pytest.mark.parametrize('ignore', [True, False])
def test_error_cleanup_precedes_policy(ignore, tmp_path, record_property):
    check('''
        ignore = ''' + repr(ignore) + '''
        error = ValueError('recoverable-step')
        source = Script(10, error, 20)
        cleaned = []
        def cleanup():
            cleaned.append(source.calls)
            events.append('cleanup')
        wrapped = safeiter(source, cleanup, ignore)
        assert next(wrapped) == 10
        if ignore:
            assert next(wrapped) == 20
            assert logs == [error]
            assert events == ['next', 'next', 'cleanup', 'log', 'next']
            raises(StopIteration, lambda: next(wrapped))
        else:
            assert raises(ValueError, lambda: next(wrapped)) is error
            assert logs == []
            assert events == ['next', 'next', 'cleanup']
            assert source.calls == 2
        assert cleaned == [2]
    ''', tmp_path, record_property)


@pytest.mark.parametrize('kind', ['list', 'tuple', 'generator', 'self'])
def test_finite_iterables_preserve_values_and_termination(kind, tmp_path, record_property):
    check('''
        kind = ''' + repr(kind) + '''
        values = [0, False, '', None, 'žluťoučký']
        sources = {'list': values, 'tuple': tuple(values),
                   'generator': (x for x in values), 'self': Script(*values)}
        cleaned = []
        wrapped = safeiter(sources[kind], lambda: cleaned.append(True))
        actual = [next(wrapped) for _ in range(5)]
        assert actual == values
        for _ in range(2):
            assert raises(StopIteration, lambda: next(wrapped)).value is None
        assert cleaned == logs == []
    ''', tmp_path, record_property)


@pytest.mark.parametrize('ignore', [True, False])
def test_iter_conversion_failure_is_lazy_and_outside_handler(ignore, tmp_path, record_property):
    check('''
        error = ValueError('iter failed')
        calls = []
        cleaned = []
        class BadIterable:
            def __iter__(self):
                calls.append('iter')
                raise error
        wrapped = safeiter(BadIterable(), lambda: cleaned.append(True), ''' + repr(ignore) + ''')
        assert calls == []
        assert raises(ValueError, lambda: next(wrapped)) is error
        assert calls == ['iter'] and cleaned == logs == []
        raises(StopIteration, lambda: next(wrapped))
    ''', tmp_path, record_property)


@pytest.mark.parametrize('error_type', ['SystemExit', 'KeyboardInterrupt', 'GeneratorExit'])
@pytest.mark.parametrize('ignore', [True, False])
def test_baseexception_propagates_without_cleanup(error_type, ignore, tmp_path, record_property):
    check('''
        error = ''' + error_type + '''('control')
        source = Script(error, 2)
        cleaned = []
        wrapped = safeiter(source, lambda: cleaned.append(True), ''' + repr(ignore) + ''')
        assert raises(type(error), lambda: next(wrapped)) is error
        assert source.calls == 1 and cleaned == logs == []
        raises(StopIteration, lambda: next(wrapped))
    ''', tmp_path, record_property)


@pytest.mark.parametrize('action', ['close', 'throw'])
@pytest.mark.parametrize('ignore', [True, False])
def test_suspended_yield_is_outside_error_handler(action, ignore, tmp_path, record_property):
    check('''
        source = Script(1, 2)
        cleaned = []
        wrapped = safeiter(source, lambda: cleaned.append(True), ''' + repr(ignore) + ''')
        assert next(wrapped) == 1
        if ''' + repr(action) + ''' == 'close':
            assert wrapped.close() is None
        else:
            error = ValueError('injected at yield')
            assert raises(ValueError, lambda: wrapped.throw(error)) is error
        assert source.calls == 1 and cleaned == logs == []
        raises(StopIteration, lambda: next(wrapped))
        assert next(source) == 2
    ''', tmp_path, record_property)


@pytest.mark.parametrize('ignore', [True, False])
def test_cleanup_failure_propagates_once_without_logging(ignore, tmp_path, record_property):
    check('''
        original = ValueError('next failure')
        failure = RuntimeError('cleanup failure')
        source = Script(original, 2)
        cleaned = []
        def cleanup():
            cleaned.append(source.calls)
            raise failure
        wrapped = safeiter(source, cleanup, ''' + repr(ignore) + ''')
        caught = raises(RuntimeError, lambda: next(wrapped))
        assert caught is failure and caught.__context__ is original
        assert cleaned == [1] and logs == [] and source.calls == 1
        raises(StopIteration, lambda: next(wrapped))
    ''', tmp_path, record_property)


def test_falsy_callable_cleanup_repairs_state_before_retry(tmp_path, record_property):
    check('''
        error = ValueError('needs repair')
        class Repairable:
            ready = False
            calls = 0
            def __iter__(self): return self
            def __next__(self):
                self.calls += 1
                if self.calls > 3: raise BudgetAbort('bounded iterator')
                events.append('next')
                if not self.ready: raise error
                if self.calls == 2: return 42
                raise StopIteration
        source = Repairable()
        class Cleanup:
            calls = 0
            def __bool__(self): return False
            def __call__(self):
                self.calls += 1
                events.append('cleanup')
                source.ready = True
        cleanup = Cleanup()
        wrapped = safeiter(source, cleanup)
        assert next(wrapped) == 42
        raises(StopIteration, lambda: next(wrapped))
        assert cleanup.calls == 1 and logs == [error]
        assert events == ['next', 'cleanup', 'log', 'next', 'next']
    ''', tmp_path, record_property)


def test_noncallable_cleanup_fails_only_on_error(tmp_path, record_property):
    check('''
        wrapped = safeiter([1], cleanup=False)
        assert next(wrapped) == 1
        raises(StopIteration, lambda: next(wrapped))
        error = ValueError('next failure')
        source = Script(error, 2)
        wrapped = safeiter(source, cleanup=False)
        caught = raises(TypeError, lambda: next(wrapped))
        assert caught.__context__ is error
        assert source.calls == 1 and logs == []
    ''', tmp_path, record_property)


def test_multiple_errors_without_cleanup_keep_real_tracebacks(tmp_path, record_property):
    check('''
        import contextlib
        import io
        first, second = ValueError('first-step'), LookupError('second-step')
        source = Script(first, 1, second, 2)
        wrapped = safeiter(source)
        with contextlib.redirect_stderr(LimitedOutput(io.StringIO())) as stream:
            assert next(wrapped) == 1
            assert next(wrapped) == 2
            raises(StopIteration, lambda: next(wrapped))
        text = stream.target.getvalue()
        assert logs == [first, second]
        assert text.count('Traceback (most recent call last):') == 2
        assert 'ValueError: first-step' in text and 'LookupError: second-step' in text
        assert 'in __next__' in text and 'in safeiter' in text
        assert source.calls == 5
    ''', tmp_path, record_property)


def test_strict_error_identity_and_original_traceback_without_cleanup(tmp_path, record_property):
    check('''
        error = ValueError('strict-step')
        source = Script(error, 2)
        wrapped = safeiter(source, ignore_errors=False)
        caught = raises(ValueError, lambda: next(wrapped))
        assert caught is error and logs == [] and source.calls == 1
        names = [f.name for f in traceback.extract_tb(caught.__traceback__)]
        assert 'safeiter' in names and '__next__' in names
        raises(StopIteration, lambda: next(wrapped))
    ''', tmp_path, record_property)


def test_repeat_error_has_no_implicit_budget(tmp_path, record_property):
    check('''
        error = ValueError('persistent')
        bailout = BudgetAbort('test-owned bailout after three failures')
        class Repeating:
            calls = 0
            def __iter__(self): return self
            def __next__(self):
                self.calls += 1
                if self.calls == 4: raise bailout
                raise error
        source = Repeating()
        cleaned = []
        wrapped = safeiter(source, lambda: cleaned.append(source.calls))
        assert raises(BudgetAbort, lambda: next(wrapped)) is bailout
        assert source.calls == 4 and cleaned == [1, 2, 3]
        assert logs == [error, error, error]
    ''', tmp_path, record_property)


def test_failed_generator_is_not_resurrected(tmp_path, record_property):
    check('''
        error = ValueError('generator stopped')
        def values():
            yield 1
            raise error
            yield 2
        cleaned = []
        wrapped = safeiter(values(), lambda: cleaned.append('cleanup'))
        assert next(wrapped) == 1
        raises(StopIteration, lambda: next(wrapped))
        assert cleaned == ['cleanup'] and logs == [error]
    ''', tmp_path, record_property)


def test_signature_and_defaults_remain_public(tmp_path, record_property):
    check('''
        import inspect
        assert str(inspect.signature(safeiter)) == '(it, cleanup=None, ignore_errors=True)'
        assert web.safeiter is safeiter
        assert inspect.isgeneratorfunction(safeiter)
    ''', tmp_path, record_property)


@pytest.mark.parametrize('origin', ['iter', 'cleanup', 'throw'])
def test_stopiteration_outside_advancement_obeys_pep479(origin, tmp_path, record_property):
    check('''
        origin = ''' + repr(origin) + '''
        end = StopIteration('not normal advancement')
        cleaned = []
        if origin == 'iter':
            class BadIterable:
                def __iter__(self): raise end
            wrapped = safeiter(BadIterable(), lambda: cleaned.append(True))
            operation = lambda: next(wrapped)
        elif origin == 'cleanup':
            def cleanup():
                cleaned.append(True)
                raise end
            wrapped = safeiter(Script(ValueError('step failed')), cleanup)
            operation = lambda: next(wrapped)
        else:
            wrapped = safeiter([1, 2], lambda: cleaned.append(True))
            assert next(wrapped) == 1
            operation = lambda: wrapped.throw(end)
        caught = raises(RuntimeError, operation)
        assert caught.__cause__ is end
        assert cleaned == ([True] if origin == 'cleanup' else [])
        assert logs == []
        raises(StopIteration, lambda: next(wrapped))
    ''', tmp_path, record_property)


@pytest.mark.parametrize('index', [0, 1])
def test_documented_safeiter_example(index, tmp_path, record_property):
    blocks = [b for b in fences((WEB_ROOT / 'docs/utils.md').read_bytes())
              if b[0] == '### `safeiter(it, cleanup=None, ignore_errors=True)`']
    assert len(blocks) == 2
    _, line, language, code, closed = blocks[index]
    assert closed and language == 'python'
    record_property('fence_sha256', hashlib.sha256(code).hexdigest())
    record_property('markdown_line', line)
    check("namespace = {'__name__': '__main__'}\nexec(compile(" + repr(code)
          + ", 'docs/utils.md', 'exec'), namespace)\n", tmp_path, record_property)


def test_empty_ends_normally_repeatedly(tmp_path, record_property):
    check('''
        wrapped = safeiter([])
        ended = False
        try:
            next(wrapped)
        except StopIteration:
            ended = True
        except BudgetAbort:
            pass
        assert ended, 'empty iterator must terminate normally'
        assert raises(StopIteration, lambda: next(wrapped)).value is None
        assert logs == []
    ''', tmp_path, record_property)
