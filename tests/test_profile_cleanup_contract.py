"""Real cProfile tempfile lifetime in fresh, offline interpreters."""
import os
from pathlib import Path
import subprocess
import sys
import textwrap

import pytest


BOOTSTRAP = r'''
import cProfile
import importlib.abc
import json
import os
from pathlib import Path
import pstats
import sys
import tempfile

class NoApplication(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {'core', 'modules', 'dotenv'}:
            raise AssertionError('Unexpected application import: ' + fullname)
sys.meta_path.insert(0, NoApplication())
root = Path.cwd().resolve()
def offline(event, args):
    if event in {'socket.connect', 'socket.getaddrinfo', 'socket.bind',
                 'subprocess.Popen', 'os.system', 'os.posix_spawn'}:
        raise AssertionError('Forbidden probe side effect: ' + event)
    if event == 'open':
        path, mode, flags = args
        writing = (isinstance(mode, str) and any(c in mode for c in 'wax+')) or (
            flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND))
        if writing and not isinstance(path, int):
            assert Path(path).resolve().is_relative_to(root), path
    if event in {'os.remove', 'os.rmdir', 'os.mkdir'}:
        assert Path(args[0]).resolve().is_relative_to(root), args
sys.addaudithook(offline)
sys.path.insert(0, sys.argv[1])
import web
from web import utils
assert Path(utils.__file__).resolve() == Path(sys.argv[1]) / 'web/utils.py'
owned = root / 'owned-tempfiles'
owned.mkdir()
tempfile.tempdir = str(owned)
sentinel = root / 'unrelated'
sentinel.write_bytes(b'preserve me')

def descriptors():
    result = {}
    for entry in Path('/proc/self/fd').iterdir():
        try:
            result[entry.name] = os.readlink(entry)
        except FileNotFoundError:
            pass
    return result
before_fds = descriptors()

def released():
    files = sorted(p.name for p in owned.iterdir())
    after_fds = descriptors()
    print(json.dumps({'owned_files': files, 'fd_before': before_fds,
                      'fd_after': after_fds}), flush=True)
    assert not files, ('Profile left owned tempfile', files)
    assert after_fds == before_fds, (before_fds, after_fds)
    assert sentinel.read_bytes() == b'preserve me'

def profiled_error(error, code):
    frames = []
    tb = error.__traceback__
    while tb:
        frames.append(tb.tb_frame)
        tb = tb.tb_next
    profilers = [f.f_locals['prof'] for f in frames
                 if f.f_code is utils.Profile.__call__.__code__]
    assert len(profilers) == 1 and isinstance(profilers[0], cProfile.Profile)
    assert any(row.code is code and row.callcount == 1
               for row in profilers[0].getstats())
'''


def probe(source, tmp_path, record_property):
    script = tmp_path / 'probe.py'
    script.write_text(BOOTSTRAP + '\n' + textwrap.dedent(source))
    result = subprocess.run(
        [sys.executable, '-B', '-I', str(script),
         str(Path(__file__).resolve().parents[2])],
        cwd=tmp_path,
        env={'PATH': os.defpath, 'HOME': str(tmp_path),
             'XDG_CONFIG_HOME': str(tmp_path), 'XDG_CACHE_HOME': str(tmp_path),
             'XDG_DATA_HOME': str(tmp_path), 'TMPDIR': str(tmp_path),
             'PYTHON_DOTENV_DISABLED': '1'},
        capture_output=True, text=True, timeout=30,
    )
    record_property('probe_argv', repr(result.args))
    record_property('probe_returncode', result.returncode)
    record_property('probe_stdout', result.stdout)
    record_property('probe_stderr', result.stderr)
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stderr == ''


@pytest.mark.parametrize('alias', ['Profile', 'profile'])
def test_callable_failure_releases_tempfile(alias, tmp_path, record_property):
    probe('''
        error = RuntimeError('owned callable failure')
        argument = object()
        seen = []
        def failing(value):
            seen.append(value)
            assert len(list(owned.iterdir())) == 1
            raise error
        try:
            getattr(utils, ALIAS)(failing)(argument)
        except RuntimeError as caught:
            assert caught is error and caught.__context__ is None
            profiled_error(caught, failing.__code__)
        else:
            raise AssertionError('callable failure swallowed')
        assert len(seen) == 1 and seen[0] is argument
        released()
    '''.replace('ALIAS', repr(alias)), tmp_path, record_property)


def test_close_error_after_real_close_still_removes_tempfile(tmp_path, record_property):
    # This models an exception AFTER real close, not arbitrary OS close failure.
    probe('''
        original_close = os.close
        failure = RuntimeError('injected after real close')
        calls = []
        def close_then_fail(fd):
            original_close(fd)
            try:
                os.fstat(fd)
            except OSError:
                pass
            else:
                raise AssertionError('real descriptor not closed')
            calls.append(fd)
            raise failure
        os.close = close_then_fail
        def must_not_run():
            raise AssertionError('profiling started after close failure')
        try:
            utils.Profile(must_not_run)()
        except RuntimeError as caught:
            assert caught is failure and caught.__context__ is None
        else:
            raise AssertionError('close failure swallowed')
        finally:
            os.close = original_close
        assert len(calls) == 1
        released()
    ''', tmp_path, record_property)


@pytest.mark.parametrize('method', ['strip_dirs', 'sort_stats', 'print_stats', 'print_callers'])
@pytest.mark.parametrize('error_kind', ['RuntimeError', 'BaseException'])
def test_report_failure_releases_tempfile(method, error_kind, tmp_path, record_property):
    probe('''
        method, error_kind = CASE
        failure = {'RuntimeError': RuntimeError, 'BaseException': BaseException}[error_kind]('report')
        original = getattr(pstats.Stats, method)
        seen = []
        def profiled_work():
            return 42
        def fail_report(self, *args, **kwargs):
            # The real cProfile was consumed by real pstats before injection.
            assert any(key[2] == 'profiled_work' and value[1] == 1
                       for key, value in self.stats.items())
            seen.append(method)
            raise failure
        setattr(pstats.Stats, method, fail_report)
        try:
            utils.profile(profiled_work)()
        except BaseException as caught:
            assert caught is failure and caught.__context__ is None
        else:
            raise AssertionError('report failure swallowed')
        finally:
            setattr(pstats.Stats, method, original)
        assert seen == [method]
        released()
    '''.replace('CASE', repr((method, error_kind))), tmp_path, record_property)


def test_stats_construction_failure_releases_tempfile(tmp_path, record_property):
    probe('''
        original = pstats.Stats
        failure = RuntimeError('stats construction')
        seen = []
        def work():
            return 1
        def construct_then_fail(*args, **kwargs):
            stats = original(*args, **kwargs)
            assert any(k[2] == 'work' for k in stats.stats)
            seen.append(stats)
            raise failure
        pstats.Stats = construct_then_fail
        try:
            utils.Profile(work)()
        except RuntimeError as caught:
            assert caught is failure and caught.__context__ is None
        else:
            raise AssertionError('stats failure swallowed')
        finally:
            pstats.Stats = original
        assert len(seen) == 1
        released()
    ''', tmp_path, record_property)


@pytest.mark.parametrize('error_kind', ['RuntimeError', 'BaseException'])
def test_wsgi_failure_before_iterable_acquisition(error_kind, tmp_path, record_property):
    probe('''
        failure = {'RuntimeError': RuntimeError, 'BaseException': BaseException}[KIND]('WSGI before return')
        events = []
        env = {'REQUEST_METHOD': 'GET'}
        def start_response(*args):
            raise AssertionError('unexpected start_response')
        def failing_wsgi(received_env, received_start):
            assert received_env is env
            # http.profiler supplies its policy wrapper, not the raw callback.
            assert callable(received_start)
            events.append('call')
            raise failure
        try:
            web.profiler(failing_wsgi)(env, start_response)
        except BaseException as caught:
            assert caught is failure and caught.__context__ is None
            profiled_error(caught, failing_wsgi.__code__)
        else:
            raise AssertionError('WSGI failure swallowed')
        assert events == ['call'] and env == {'REQUEST_METHOD': 'GET'}
        released()
    '''.replace('KIND', repr(error_kind)), tmp_path, record_property)


def test_callable_baseexception_releases_tempfile(tmp_path, record_property):
    probe('''
        failure = BaseException('not an Exception')
        def stop():
            raise failure
        try:
            utils.Profile(stop)()
        except BaseException as caught:
            assert caught is failure and caught.__context__ is None
            profiled_error(caught, stop.__code__)
        else:
            raise AssertionError('BaseException swallowed')
        released()
    ''', tmp_path, record_property)


@pytest.mark.parametrize('active_error', [False, True])
@pytest.mark.parametrize('cleanup_kind', ['OSError', 'RuntimeError', 'BaseException'])
def test_remove_failure_policy(active_error, cleanup_kind, tmp_path, record_property):
    probe('''
        active_error, cleanup_kind = CASE
        operation_error = RuntimeError('callable') if active_error else None
        cleanup_error = {'OSError': OSError, 'RuntimeError': RuntimeError,
                         'BaseException': BaseException}[cleanup_kind]('remove')
        original_remove = os.remove
        removed = []
        value = object()
        def work():
            if operation_error is not None:
                raise operation_error
            return value
        def fail_remove(filename):
            assert Path(filename).parent == owned
            assert Path(filename).is_file()
            assert descriptors() == before_fds
            removed.append(filename)
            raise cleanup_error
        os.remove = fail_remove
        try:
            try:
                result, report = utils.Profile(work)()
            except BaseException as caught:
                expected = operation_error if cleanup_kind == 'OSError' else cleanup_error
                assert caught is expected
                assert caught.__context__ is (operation_error if cleanup_kind != 'OSError' else None)
            else:
                assert not active_error and cleanup_kind == 'OSError'
                assert result is value and 'work' in report and 'function calls' in report
            assert len(removed) == 1
            # A failed unlink can leave the file; no promise of impossible cleanup.
            assert sorted(owned.iterdir()) == [Path(removed[0])]
        finally:
            os.remove = original_remove
            for path in removed:
                original_remove(path)
        released()
    '''.replace('CASE', repr((active_error, cleanup_kind))), tmp_path, record_property)


@pytest.mark.parametrize('alias', ['Profile', 'profile'])
def test_success_alias_arguments_real_stats_and_repeated_calls(alias, tmp_path, record_property):
    probe('''
        assert utils.profile is utils.Profile
        assert web.profile is utils.Profile and web.Profile is utils.Profile
        seen = []
        values = [object(), object(), object()]
        def profiled_work(*args):
            seen.append(args)
            assert len(list(owned.iterdir())) == 1
            assert descriptors() == before_fds
            return args[-1] if args else values[0]
        wrapper = getattr(utils, ALIAS)(profiled_work)
        assert seen == []
        for args in [(), (values[1],), tuple(values)]:
            result, report = wrapper(*args)
            assert result is (args[-1] if args else values[0])
            assert seen[-1] == args
            assert isinstance(report, str) and report.startswith('\\n\\ntook ')
            assert ' seconds\\n' in report and 'function calls' in report
            assert 'profiled_work' in report and 'Ordered by: internal time, call count' in report
            assert '<-' in report  # real print_callers output
            released()
        assert len(seen) == 3
        try:
            wrapper(keyword=values[0])
        except TypeError:
            pass
        else:
            raise AssertionError('keyword policy unexpectedly changed')
        assert len(seen) == 3
        released()
    '''.replace('ALIAS', repr(alias)), tmp_path, record_property)


def test_mkstemp_failure_does_not_run_callable_or_cleanup(tmp_path, record_property):
    probe('''
        original = tempfile.mkstemp
        original_remove = os.remove
        failure = OSError('creation failed before acquisition')
        def fail_create():
            raise failure
        def forbidden(*args):
            raise AssertionError('unowned cleanup or callable invoked')
        tempfile.mkstemp = fail_create
        os.remove = forbidden
        try:
            utils.Profile(forbidden)()
        except OSError as caught:
            assert caught is failure and caught.__context__ is None
        else:
            raise AssertionError('creation failure swallowed')
        finally:
            tempfile.mkstemp = original
            os.remove = original_remove
        released()
    ''', tmp_path, record_property)
