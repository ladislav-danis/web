"""Eager WSGI iterable ownership with real Profile, in offline child probes."""
import pytest

from .test_http_contract import probe


def test_profiler_closes_original_before_return(tmp_path, record_property):
    probe('''
        events = []
        class Body:
            def __iter__(self):
                events.append('iter')
                return iter(['<p>Příliš</p>'.encode('utf-8')])
            def close(self):
                events.append('close')
        body = Body()
        seen = []
        def tiny_wsgi(env, start_response):
            seen.append(env)
            events.append('call')
            start_response('200 OK', [('Content-Type', 'text/html; charset=utf-8')])
            return body
        def observed(env, start_response):
            original_env = env.copy()
            result = web.profiler(tiny_wsgi)(env, start_response)
            assert seen == [env] and seen[0] is env
            assert env == original_env
            assert events == ['call', 'iter', 'close'], events
            assert type(result) is list and not hasattr(result, 'close')
            events.append('return')
            return result
        (status, headers), chunks = request_wsgi(observed)
        assert status == '200 OK'
        assert headers == [('Content-Type', 'text/html; charset=utf-8')]
        assert chunks[0] == '<p>Příliš</p>'.encode('utf-8')
        assert events == ['call', 'iter', 'close', 'return']
        assert all(type(chunk) is bytes for chunk in chunks)
        assert b'tiny_wsgi' in chunks[-1] and b'__iter__' not in chunks[-1]
    ''', tmp_path, record_property)


def test_profiler_closes_on_iteration_failure(tmp_path, record_property):
    # Direct call: deliberate body failure is not a validator success scenario.
    probe('''
        events = []
        failure = RuntimeError('owned iteration failure')
        class Body:
            def __iter__(self):
                return self
            def __next__(self):
                events.append('next')
                raise failure
            def close(self):
                events.append('close')
        body = Body()
        def tiny_wsgi(env, start_response):
            start_response('200 OK', [('Content-Type', 'text/html')])
            return body
        env = {}
        setup_testing_defaults(env)
        captured = []
        try:
            web.profiler(tiny_wsgi)(env, lambda s, h: captured.append((s, h)))
        except RuntimeError as exc:
            assert exc is failure and exc.__context__ is None
        else:
            raise AssertionError('failed iteration returned a result')
        assert events == ['next', 'close'], events
        assert captured == [('200 OK', [('Content-Type', 'text/html')])]
    ''', tmp_path, record_property)


@pytest.mark.parametrize('stage,iteration_kind,close_kind', [
    ('iter', 'RuntimeError', None),
    ('next', 'RuntimeError', None),
    ('next', 'BaseException', None),
    ('none', None, 'RuntimeError'),
    ('none', None, 'BaseException'),
    ('next', 'RuntimeError', 'RuntimeError'),
    ('next', 'BaseException', 'RuntimeError'),
    ('iter', 'RuntimeError', 'BaseException'),
])
def test_profiler_failure_identity_and_close_precedence(
        stage, iteration_kind, close_kind, tmp_path, record_property):
    # Direct calls isolate intentional failures; the WSGI validator would add
    # its own iterator/close ownership and obscure the exception boundary.
    probe('''
        stage, iteration_kind, close_kind = CASE
        events = []
        errors = {'RuntimeError': RuntimeError, 'BaseException': BaseException}
        iteration_error = errors[iteration_kind]('iteration') if iteration_kind else None
        close_error = errors[close_kind]('close') if close_kind else None
        class Body:
            def __iter__(self):
                events.append('iter')
                if stage == 'iter':
                    raise iteration_error
                return self
            def __next__(self):
                events.append('next')
                if events.count('next') == 1:
                    return b'<p>partial</p>'
                if stage == 'next':
                    raise iteration_error
                raise StopIteration
            def close(self):
                events.append('close')
                if close_error is not None:
                    raise close_error
        body = Body()
        def tiny_wsgi(env, start_response):
            start_response('200 OK', headers)
            return body
        headers = [('Content-Type', 'text/html'), ('X-Owned', 'unchanged')]
        env = {}
        setup_testing_defaults(env)
        captured = []
        try:
            web.profiler(tiny_wsgi)(env, lambda s, h: captured.append((s, h)))
        except BaseException as exc:
            expected = close_error if close_error is not None else iteration_error
            assert exc is expected, (exc, expected)
            assert exc.__context__ is (iteration_error if close_error is not None else None)
        else:
            raise AssertionError('failed materialization/close returned a result')
        assert events == (['iter', 'close'] if stage == 'iter'
                          else ['iter', 'next', 'next', 'close']), events
        assert captured == [('200 OK', headers)] and captured[0][1] is headers
    '''.replace('CASE', repr((stage, iteration_kind, close_kind))),
          tmp_path, record_property)


@pytest.mark.parametrize('chunks', [[], [b'<p>one</p>', b'<p>two</p>']])
def test_profiler_closes_empty_and_multichunk_bodies(chunks, tmp_path, record_property):
    probe('''
        original = CHUNKS
        events = []
        class Body:
            def __iter__(self):
                events.append('iter')
                return iter(original)
            def close(self):
                events.append('close')
        body = Body()
        def tiny_wsgi(env, start_response):
            start_response('200 OK', [('Content-Type', 'text/html')])
            return body
        def observed(env, start_response):
            result = web.profiler(tiny_wsgi)(env, start_response)
            assert events == ['iter', 'close'], events
            assert type(result) is list
            return result
        (_, _), result = request_wsgi(observed)
        assert result[:-1] == original
        assert result[-1].startswith(b'<pre>') and result[-1].endswith(b'</pre>')
        assert events == ['iter', 'close']
    '''.replace('CHUNKS', repr(chunks)), tmp_path, record_property)


@pytest.mark.parametrize('close_attribute', ['absent', 'none', 'noncallable'])
def test_profiler_accepts_body_without_callable_close(close_attribute, tmp_path, record_property):
    probe('''
        class Body:
            def __iter__(self):
                return iter([b'<p>body</p>'])
        body = Body()
        if KIND != 'absent':
            body.close = None if KIND == 'none' else 'not callable'
        def tiny_wsgi(env, start_response):
            start_response('200 OK', [('Content-Type', 'text/html')])
            return body
        (_, _), result = request_wsgi(web.profiler(tiny_wsgi))
        assert result[0] == b'<p>body</p>'
        assert result[-1].startswith(b'<pre>') and b'tiny_wsgi' in result[-1]
    '''.replace('KIND', repr(close_attribute)), tmp_path, record_property)


def test_profiler_owns_iterable_not_distinct_iterator(tmp_path, record_property):
    probe('''
        events = []
        class Iterator:
            def __iter__(self):
                return self
            def __next__(self):
                events.append('next')
                if events.count('next') == 1:
                    return b'<p>body</p>'
                raise StopIteration
            def close(self):
                events.append('iterator-close')
        iterator = Iterator()
        class Body:
            def __iter__(self):
                events.append('iter')
                return iterator
            def close(self):
                events.append('body-close')
        body = Body()
        def tiny_wsgi(env, start_response):
            start_response('200 OK', [('Content-Type', 'text/html')])
            return body
        def observed(env, start_response):
            result = web.profiler(tiny_wsgi)(env, start_response)
            assert events == ['iter', 'next', 'next', 'body-close'], events
            return result
        (_, _), result = request_wsgi(observed)
        assert result[0] == b'<p>body</p>'
        assert events == ['iter', 'next', 'next', 'body-close']
    ''', tmp_path, record_property)


def test_profiler_closes_before_real_report_encoding(tmp_path, record_property):
    probe('''
        events = []
        class Body:
            def __iter__(self):
                events.append('iter')
                return iter([b'<p>body</p>'])
            def close(self):
                events.append('close')
        body = Body()
        ns = {'body': body, 'events': events}
        source = "def tiny_wsgi(env, start_response):\\n    events.append('call')\\n    start_response('200 OK', [('Content-Type', 'text/html')])\\n    return body\\n"
        exec(compile(source, '<Příliš&tag>.py', 'exec'), ns)
        real_websafe = web.net.websafe
        def observe_report(report):
            # Observe the real escaping boundary, without replacing Profile.
            assert events == ['call', 'iter', 'close'], events
            events.append('report')
            return real_websafe(report)
        web.net.websafe = observe_report
        try:
            (_, _), result = request_wsgi(web.profiler(ns['tiny_wsgi']))
        finally:
            web.net.websafe = real_websafe
        assert events == ['call', 'iter', 'close', 'report']
        assert '&lt;Příliš&amp;tag&gt;.py'.encode('utf-8') in result[-1]
        assert '<Příliš&tag>.py'.encode('utf-8') not in result[-1]
        assert b'tiny_wsgi' in result[-1]
        assert b'__iter__' not in result[-1] and b'close)' not in result[-1]
    ''', tmp_path, record_property)
