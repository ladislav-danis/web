"""Utils reference contracts in fresh offline interpreters (not an OS sandbox)."""
import hashlib
import textwrap

import pytest

from .test_template_security_contract import WEB_ROOT, fences, probe


def check(source, tmp_path, record_property):
    probe('from web import utils\n' + textwrap.dedent(source), tmp_path, record_property)


def test_counter_least_all_ties_and_shadow_key(tmp_path, record_property):
    check('''
        c = utils.Counter(a=2, b=1, c=1)
        assert c.least() == ['b', 'c']
        assert c.most() == ['a']
        assert c == {'a': 2, 'b': 1, 'c': 1}
        assert utils.Counter(itervalues=1, other=2).least() == ['itervalues']
        assert utils.Counter(only=0).least() == ['only']
        assert utils.Counter(a=-2, b=-2, c=-1).least() == ['a', 'b']
        raises(ValueError, utils.Counter().least)
        raises(ValueError, utils.Counter().most)
    ''', tmp_path, record_property)


@pytest.mark.parametrize('expression', ['[]', '()', "''", 'range(0)'])
def test_iterview_empty_no_output(expression, tmp_path, record_property):
    check('''
        import contextlib
        import io
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            wrapped = utils.iterview(''' + expression + ''')
            sentinel = object()
            assert next(wrapped, sentinel) is sentinel
            assert next(wrapped, sentinel) is sentinel
        assert stderr.getvalue() == ''
    ''', tmp_path, record_property)


def test_iterview_sized_lazy_progress_and_completion(tmp_path, record_property):
    check(r'''
        import contextlib
        import io
        from types import SimpleNamespace
        utils.time = SimpleNamespace(time=lambda: 100.0)
        events = []
        value = object()
        class Sized:
            def __len__(self):
                events.append('len')
                return 2
            def __iter__(self):
                events.append('iter')
                yield value
                events.append('second')
                yield None
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            wrapped = utils.iterview(Sized())
            assert events == [] and stderr.getvalue() == ''
            assert next(wrapped) is value
            first = '\r  0.0% (0/2) [>                                           ] ETA --:--:--'
            assert stderr.getvalue() == first
            assert events == ['len', 'iter']
            assert next(wrapped) is None
            second = '\r 50.0% (1/2) [======================>                     ] ETA 00:00:00'
            assert stderr.getvalue() == first + second
            assert events == ['len', 'iter', 'second']
            raises(StopIteration, lambda: next(wrapped))
            final = '\r100.0% (2/2) [============================================]     00:00:00\n'
            assert stderr.getvalue() == first + second + final
            raises(StopIteration, lambda: next(wrapped))
            assert stderr.getvalue() == first + second + final
    ''', tmp_path, record_property)


def test_iterview_unsized_fails_before_consumption(tmp_path, record_property):
    check('''
        import contextlib
        import io
        calls = []
        def values():
            calls.append('next')
            yield 1
        source = values()
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            wrapped = utils.iterview(source)
            assert calls == []
            raises(TypeError, lambda: next(wrapped))
        assert calls == [] and stderr.getvalue() == ''
        assert next(source) == 1
    ''', tmp_path, record_property)


@pytest.mark.parametrize('expression', ["['a', 'b']", "('a', 'b')", "'ab'"])
def test_listget_integer_boundaries(expression, tmp_path, record_property):
    check('''
        values = ''' + expression + '''
        default = object()
        assert utils.listget(values, -3, default) is default
        assert utils.listget(values, -1000, default) is default
        assert utils.listget(values, 2, default) is default
        assert utils.listget(values, 1000, default) is default
        assert utils.listget(values, -2) == 'a'
        assert utils.listget(values, -1) == 'b'
        assert utils.listget(values, 0) == 'a'
        assert utils.listget(values, 1) == 'b'
        assert utils.listget(values, -3) is None
        for empty in ([], (), ''):
            for index in (-1, 0, 1):
                assert utils.listget(empty, index, default) is default
        value = object()
        assert utils.listget([value], -1, default) is value
    ''', tmp_path, record_property)


def test_listget_preserves_non_index_errors_and_legacy_odd_inputs(tmp_path, record_property):
    check('''
        # Supported API: integer indexes into sized sequences. Do not redesign
        # the existing len/comparison gate for arbitrary index-like objects.
        for index in (None, '0', slice(0, 1), 0.0):
            raises(TypeError, lambda: utils.listget(['a'], index))
        default = object()
        assert utils.listget(['a'], 1.5, default) is default
        assert utils.listget(['a', 'b'], True) == 'b'
        class IndexLike:
            def __index__(self):
                return 0
        raises(TypeError, lambda: utils.listget(['a'], IndexLike()))
        raises(TypeError, lambda: utils.listget(iter(['a']), 0))
        class Broken:
            def __len__(self):
                return 1
            def __getitem__(self, index):
                raise error
        for kind in (TypeError, ValueError, KeyError, RuntimeError):
            error = kind('not an index boundary')
            assert raises(kind, lambda: utils.listget(Broken(), 0)) is error
    ''', tmp_path, record_property)


def test_storify_safestr_group_and_percent_characterizations(tmp_path, record_property):
    check('''
        outer = utils.storify({'a': [1, 2]}, a=[])
        assert isinstance(outer, utils.Storage) and outer == {'a': [1, 2]}
        assert outer.a == [1, 2]
        inner = utils.storage(value=1)
        assert utils.storify({'a': inner}, a={}).a is inner
        assert utils.storify({'a': inner}).a == 1
        raises(KeyError, lambda: utils.storify({}, 'required'))
        assert utils.safeunicode is utils.safestr
        assert utils.safestr(b'abc', encoding='not-a-codec') == "b'abc'"
        assert utils.safestr('žluťoučký') == 'žluťoučký'
        assert utils.safestr([1, 2]) == '[1, 2]'
        source = iter([1, b'abc', None])
        assert utils.safestr(source) == ['1', "b'abc'", 'None']
        assert list(source) == []
        class FalsyIterator:
            def __bool__(self): return False
            def __next__(self): raise AssertionError('must not consume')
            def __str__(self): return 'falsy iterator'
        assert utils.safestr(FalsyIterator()) == 'falsy iterator'
        assert list(utils.group([1, 2, 3], 2)) == [[1, 2], [3]]
        assert list(utils.group((1, 2, 3), 2)) == [(1, 2), (3,)]
        assert list(utils.group('abc', 2)) == ['ab', 'c']
        source = iter([1, 2])
        raises(TypeError, lambda: utils.group(source, 2))
        assert next(source) == 1
        raises(ValueError, lambda: utils.group([1], 0))
        c = utils.Counter(a=3, b=1)
        assert c.percent('a') == 0.75 and c.percent('b') == 0.25
        assert utils.Counter(a=0, b=1).percent('a') == 0.0
        assert utils.Counter(a=2, b=-1).percent('a') == 2.0
        assert utils.Counter(a=2, b=-1).percent('b') == -1.0
        raises(ZeroDivisionError, lambda: utils.Counter(a=0).percent('a'))
        raises(KeyError, lambda: c.percent('missing'))
    ''', tmp_path, record_property)


def test_exports_and_iters_exact_runtime_types(tmp_path, record_property):
    check('''
        namespace = {}
        exec('from web.utils import *', namespace)
        assert set(namespace) - {'__builtins__'} == set(utils.__all__)
        assert 'storify' in utils.__all__
        for name in utils.__all__:
            assert namespace[name] is getattr(utils, name) is getattr(web, name)
        assert isinstance(utils.iters, tuple) and type(utils.iters) is not tuple
        assert type(utils.iters).__name__ == '_hack'
        assert utils.iters == (list, tuple, set, frozenset)
        assert isinstance([], utils.iters) and not isinstance('abc', utils.iters)
        assert not isinstance(iter([]), utils.iters)
    ''', tmp_path, record_property)


DATA_HEADINGS = [
    '### `Counter`', '### `storify(mapping, *requireds, **defaults)`',
    '### `safestr(obj, encoding="utf-8")`', '### `group(seq, size)`',
    '### `iterview(x)`', '### `listget(lst, ind, default=None)`',
    '### `__all__`', '### `iters`',
]


def execute_heading(heading, tmp_path, record_property):
    selected = [b for b in fences((WEB_ROOT / 'docs/utils.md').read_bytes()) if b[0] == heading]
    assert len(selected) == 1, (heading, len(selected))
    _, line, language, code, closed = selected[0]
    assert closed and language == 'python'
    record_property('fence_sha256', hashlib.sha256(code).hexdigest())
    record_property('markdown_line', line)
    probe('namespace = {"__name__": "__main__"}\nexec(compile(' + repr(code) +
          ', "docs/utils.md", "exec"), namespace)\n', tmp_path, record_property)


@pytest.mark.parametrize('heading', DATA_HEADINGS)
def test_data_documentation_fences(heading, tmp_path, record_property):
    execute_heading(heading, tmp_path, record_property)


def test_callable_wrapper_construction_capture_and_real_profile(tmp_path, record_property):
    check(r'''
        import tempfile
        from pathlib import Path
        assert utils.capturestdout is utils.CaptureStdout
        assert utils.profile is utils.Profile
        calls = []
        def output(value, *, suffix):
            calls.append(value)
            print(value + suffix)
            return 'not the captured result'
        wrapper = utils.capturestdout(output)
        assert isinstance(wrapper, utils.CaptureStdout) and callable(wrapper)
        assert calls == []
        stdout = sys.stdout
        assert wrapper('foo', suffix='!') == 'foo!\n'
        assert calls == ['foo'] and sys.stdout is stdout
        error = ValueError('capture failure')
        def failure(): raise error
        assert raises(ValueError, utils.capturestdout(failure)) is error
        assert sys.stdout is stdout
        value = object()
        calls = []
        def function(argument):
            calls.append(argument)
            return argument
        wrapper = utils.profile(function)
        assert isinstance(wrapper, utils.Profile) and callable(wrapper)
        assert calls == []
        # Real cProfile with a disposable directory; no exceptional Profile
        # invocation (known web#27 tempfile leak is outside this source repair).
        old_tempdir = tempfile.tempdir
        with tempfile.TemporaryDirectory() as work:
            try:
                tempfile.tempdir = work
                result, report = wrapper(value)
                assert result is value and calls == [value]
                assert isinstance(report, str)
                assert 'took ' in report and 'function calls' in report
                assert 'function' in report
                assert list(Path(work).iterdir()) == []
            finally:
                tempfile.tempdir = old_tempdir
        assert not Path(work).exists()
    ''', tmp_path, record_property)


@pytest.mark.parametrize('smtp,engine,path,expected', [
    ('smtp.invalid', 'aws', None, 'smtp'),
    ('', 'aws', None, 'aws'),
    (False, 'aws', None, 'aws'),
    (None, 'AWS', None, 'sendmail'),
    ('', '', '/owned-inert/sendmail', 'sendmail'),
])
def test_email_actual_dispatch_with_inert_transports(smtp, engine, path, expected, tmp_path, record_property):
    check(r'''
        import importlib.util
        import io
        import smtplib
        from email import message_from_string
        from types import ModuleType
        from unittest.mock import patch
        smtp, engine, path, expected = ''' + repr((smtp, engine, path, expected)) + r'''
        # Check real optional availability BEFORE installing the inert module.
        boto_available = importlib.util.find_spec('boto') is not None
        print(json.dumps({'optional_boto_available': boto_available,
                          'coverage': 'inert transport seam, not live certification'}))
        events = []
        payloads = []
        class SMTP:
            def __init__(self, server, port): events.append(('smtp', server, port))
            def set_debuglevel(self, level): events.append(('debug', level))
            def ehlo(self): events.append(('ehlo',))
            def starttls(self): events.append(('starttls',))
            def login(self, user, password): events.append(('login', user, password))
            def sendmail(self, sender, recipients, payload):
                payloads.append((sender, recipients, payload))
            def quit(self): events.append(('quit',))
        class SES:
            def __init__(self, **kw): events.append(('aws', kw))
            def send_raw_email(self, payload, sender, recipients):
                payloads.append((sender, recipients, payload))
        class Sink(io.BytesIO):
            def close(self):
                payloads.append(('from@example.invalid', recipients, self.getvalue().decode('utf-8')))
                super().close()
        class Process:
            def __init__(self, command, stdin):
                assert stdin is utils.subprocess.PIPE
                events.append(('sendmail', command))
                self.stdin = Sink()
            def wait(self): events.append(('wait',)); return 0
        boto = ModuleType('boto')
        ses = ModuleType('boto.ses')
        ses.SESConnection = SES
        boto.ses = ses
        config = utils.Storage(email_engine=engine, smtp_port=2525,
            smtp_debuglevel=1, smtp_starttls=True,
            smtp_username='synthetic-user', smtp_password='synthetic-password',
            aws_access_key_id='synthetic-key', aws_secret_access_key='synthetic-secret')
        if smtp is not None:
            config.smtp_server = smtp
        if path is not None:
            config.sendmail_path = path
        recipients = ['to@example.invalid', 'cc@example.invalid', 'bcc@example.invalid']
        with patch.object(web.webapi, 'config', config), patch.object(smtplib, 'SMTP', SMTP), \
             patch.dict(sys.modules, {'boto': boto, 'boto.ses': ses}), \
             patch.object(utils.subprocess, 'Popen', Process):
            result = utils.sendmail('Example <from@example.invalid>', 'to@example.invalid',
                'Synthetic subject', 'Synthetic body', cc='cc@example.invalid',
                bcc='bcc@example.invalid', attachments=[{'filename': 'sample.bin',
                'content': b'harmless', 'content_type': 'application/octet-stream'}])
        assert result is None and len(payloads) == 1
        assert payloads[0][:2] == ('from@example.invalid', recipients)
        message = message_from_string(payloads[0][2])
        assert str(message['Subject']) == 'Synthetic subject'
        assert message['To'] == 'to@example.invalid' and message['Cc'] == 'cc@example.invalid'
        assert message['Bcc'] is None and message.is_multipart()
        parts = message.get_payload()
        assert parts[0].get_payload(decode=True) == b'Synthetic body'
        assert parts[1].get_filename() == 'sample.bin'
        assert parts[1].get_payload(decode=True) == b'harmless'
        if expected == 'smtp':
            assert events == [('smtp', 'smtp.invalid', 2525), ('debug', 1), ('ehlo',),
                ('starttls',), ('ehlo',), ('login', 'synthetic-user', 'synthetic-password'), ('quit',)]
        elif expected == 'aws':
            assert events == [('aws', {'aws_access_key_id': 'synthetic-key',
                                      'aws_secret_access_key': 'synthetic-secret'})]
        else:
            assert events == [('sendmail', [path or '/usr/sbin/sendmail', '-f',
                                           'from@example.invalid'] + recipients), ('wait',)]
        print(json.dumps({'backend': expected, 'recorded_events': events, 'real_send': False}))
    ''', tmp_path, record_property)


@pytest.mark.parametrize('heading', ['### `capturestdout(func)`', '### `profile(func)`', '### Email Sending'])
def test_wrapper_email_documentation_fences(heading, tmp_path, record_property):
    execute_heading(heading, tmp_path, record_property)


def test_iterview_zero_length_does_not_start_iteration(tmp_path, record_property):
    check('''
        import contextlib
        import io
        events = []
        class Empty:
            def __len__(self):
                events.append('len')
                return 0
            def __iter__(self):
                raise AssertionError('zero length must return before iteration')
        stderr = io.StringIO()
        wrapped = utils.iterview(Empty())
        assert events == []
        with contextlib.redirect_stderr(stderr):
            assert list(wrapped) == []
        assert events == ['len'] and stderr.getvalue() == ''
        error = RuntimeError('length error')
        class BadLength:
            def __len__(self): raise error
            def __iter__(self): raise AssertionError('must not iterate')
        assert raises(RuntimeError, lambda: next(utils.iterview(BadLength()))) is error
        assert utils.Counter(a=2, b=2, c=1).most() == ['a', 'b']
    ''', tmp_path, record_property)


def test_documented_export_list_matches_runtime(tmp_path, record_property):
    raw = (WEB_ROOT / 'docs/utils.md').read_text()
    section = raw.split('### `__all__`\n', 1)[1].split('### `iters`', 1)[0]
    listed = [name.strip() for line in section.splitlines() if line.startswith('- ')
              for name in line[2:].split(',')]
    assert listed and len(listed) == len(set(listed))
    check('assert utils.__all__ == ' + repr(listed), tmp_path, record_property)


def test_email_explicit_none_and_backend_error_do_not_fallback(tmp_path, record_property):
    check('''
        from unittest.mock import patch
        calls = []
        error = RuntimeError('inert failure')
        def fail(mail, text):
            calls.append('aws')
            raise error
        def forbidden(mail, text):
            raise AssertionError('wrong backend/fallback')
        with patch.object(web.webapi, 'config', utils.Storage(smtp_server=None, email_engine='aws')), \\
             patch.object(utils._EmailMessage, 'send_with_aws', fail), \\
             patch.object(utils._EmailMessage, 'send_with_smtp', forbidden), \\
             patch.object(utils._EmailMessage, 'default_email_sender', forbidden):
            assert raises(RuntimeError, lambda: utils.sendmail('a@example.invalid',
                'b@example.invalid', 'Synthetic', 'Harmless')) is error
        assert calls == ['aws']
    ''', tmp_path, record_property)


def test_standalone_guards_deny_application_env_db_network_process(tmp_path, record_property):
    check('''
        import importlib
        import socket
        import sqlite3
        import subprocess
        for name in ('core', 'modules', 'dotenv'):
            raises(AssertionError, lambda: importlib.import_module(name))
        raises(AssertionError, lambda: open('.env'))
        raises(AssertionError, lambda: sqlite3.connect(':memory:'))
        raises(AssertionError, lambda: socket.getaddrinfo('denied.invalid', 443))
        raises(AssertionError, lambda: subprocess.run([sys.executable, '-c', 'pass']))
        assert len(blocked) == 7
    ''', tmp_path, record_property)
