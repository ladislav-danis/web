"""Conservative response policy, real Profile and offline WSGI boundaries."""
import pytest

from .test_http_contract import probe


def test_profiler_bypasses_head_without_adding_body(tmp_path, record_property):
    probe(r'''
        headers = [('Content-Type', 'text/html')]
        events = []
        class Body:
            def __iter__(self):
                events.append('iter')
                return iter([])
            def close(self):
                events.append('close')
        def tiny_wsgi(env, start_response):
            start_response('200 OK', headers)
            return Body()
        env = {'REQUEST_METHOD': 'HEAD'}
        captured = []
        chunks = web.profiler(tiny_wsgi)(env, lambda s, h: captured.append((s, h)))
        assert chunks == [], chunks
        assert captured == [('200 OK', headers)] and captured[0][1] is headers
        assert events == ['iter', 'close']
    ''', tmp_path, record_property)


def test_profiler_bypasses_content_length(tmp_path, record_property):
    probe(r'''
        headers = [('Content-Type', 'text/html'), ('Content-Length', '3')]
        chunks = [b'a', b'bc']
        captured = []
        def tiny_wsgi(env, start_response):
            start_response('200 OK', headers)
            return chunks
        result = web.profiler(tiny_wsgi)(
            {'REQUEST_METHOD': 'GET'}, lambda s, h: captured.append((s, h)))
        assert result == chunks
        assert all(a is b for a, b in zip(result, chunks))
        assert captured == [('200 OK', headers)] and captured[0][1] is headers
    ''', tmp_path, record_property)


@pytest.mark.parametrize('media,append', [
    ('text/html', True), ('text/html; charset=utf-8', True),
    (' \tTeXt/HtMl ; CHARSET = "UTF-8" \t', True),
    (None, False), ('application/json', False), ('application/octet-stream', False),
    ('text/plain', False), ('application/xhtml+xml', False),
    ('text/html; charset=iso-8859-1', False), ('text/html; charset=utf-16', False),
    ('text/html; charset=utf-8; charset=utf-8', False),
    ('text/html; charset=utf-8; charset=latin1', False),
    ('text/html, text/html', False), ('text/html;', False),
    ('text/html; charset=', False), ('text/html; charset="utf-8', False),
    ('text/html; boundary=abc', False), ('text/html\r\n', False),
])
def test_profiler_requires_unambiguous_utf8_html(media, append, tmp_path, record_property):
    probe(r'''
        media, append = CASE
        headers = [] if media is None else [('cOnTeNt-TyPe', media)]
        original = [b'<p>body</p>']
        captured = []
        def tiny_wsgi(env, start_response):
            start_response('200 OK', headers)
            return original
        result = web.profiler(tiny_wsgi)(
            {'REQUEST_METHOD': 'GET'}, lambda s, h: captured.append((s, h)))
        assert captured == [('200 OK', headers)] and captured[0][1] is headers
        assert result[:1] == original and result[0] is original[0]
        if append:
            assert len(result) == 2 and result[-1].startswith(b'<pre>')
            assert b'tiny_wsgi' in result[-1] and b'function calls' in result[-1]
        else:
            assert result == original
    '''.replace('CASE', repr((media, append))), tmp_path, record_property)


@pytest.mark.parametrize('method,status', [
    ('HEAD', '200 OK'), ('POST', '200 OK'), ('PUT', '200 OK'),
    ('DELETE', '200 OK'), ('OPTIONS', '200 OK'), ('get', '200 OK'),
    (None, '200 OK'), ('GET', '100 Continue'), ('GET', '101 Switching Protocols'),
    ('GET', '199 Informational'), ('GET', '204 No Content'), ('GET', '205 Reset Content'),
    ('GET', '304 Not Modified'), ('GET', '206 Partial Content'),
    ('GET', '302 Found'), ('GET', '404 Not Found'), ('GET', '500 Internal Server Error'),
    ('GET', '200 Other'),
])
def test_profiler_bypasses_other_methods_and_statuses(method, status, tmp_path, record_property):
    # Deliberately preserve even invalid underlying no-body payloads; not an HTTP repair.
    probe(r'''
        method, status = CASE
        for original in ([], [b'underlying', b'body']):
            headers = [('Content-Type', 'text/html')]
            seen = []
            def tiny_wsgi(env, start_response):
                start_response(status, headers)
                return original
            env = {} if method is None else {'REQUEST_METHOD': method}
            result = web.profiler(tiny_wsgi)(env, lambda s, h: seen.append((s, h)))
            assert result == original
            assert all(a is b for a, b in zip(result, original))
            assert seen == [(status, headers)] and seen[0][1] is headers
    '''.replace('CASE', repr((method, status))), tmp_path, record_property)


@pytest.mark.parametrize('extra', [
    [('Content-Length', '0')], [('content-length', '')], [('CONTENT-LENGTH', 'bad')],
    [('Content-Encoding', 'gzip')], [('Content-Encoding', 'identity')],
    [('Content-Encoding', '')], [('Content-Range', 'bytes 0-2/9')],
    [('ETag', '"v1"')], [('Last-Modified', 'Wed, 01 Jan 2025 00:00:00 GMT')],
    [('Content-MD5', 'abc')], [('Digest', 'sha-256=abc')],
    [('Content-Digest', 'sha-256=:abc:')], [('Repr-Digest', 'sha-256=:abc:')],
    [('Content-Disposition', 'attachment; filename="x.html"')],
    [('Content-Disposition', 'inline')],
    [('Content-Type', 'text/html')], [('content-type', 'text/plain')],
    [('X-Header', 'a'), ('x-header', 'b')], [('Bad Header', 'x')],
    [('X-Header', 'bad\r\nvalue')], [('X-Header', '\x00')],
])
def test_profiler_preserves_body_dependent_or_ambiguous_headers(extra, tmp_path, record_property):
    probe(r'''
        headers = [('Content-Type', 'text/html')] + EXTRA
        before = list(headers)
        original = [b'\x1f', b'compressed-or-original']
        captured = []
        def tiny_wsgi(env, start_response):
            start_response('200 OK', headers)
            return original
        result = web.profiler(tiny_wsgi)(
            {'REQUEST_METHOD': 'GET'}, lambda s, h: captured.append((s, h)))
        assert result == original and all(a is b for a, b in zip(result, original))
        assert headers == before
        assert captured == [('200 OK', headers)] and captured[0][1] is headers
    '''.replace('EXTRA', repr(extra)), tmp_path, record_property)


@pytest.mark.parametrize('request_headers,response_headers,append', [
    ({'HTTP_RANGE': 'bytes=0-2'}, [], False), ({'HTTP_RANGE': ''}, [], False),
    ({'HTTP_IF_RANGE': '"v1"'}, [], False),
    ({}, [('Cache-Control', 'no-transform')], False),
    ({}, [('Cache-Control', 'private, No-Transform')], False),
    ({'HTTP_CACHE_CONTROL': 'max-age=0, no-transform'}, [], False),
    ({}, [('Cache-Control', 'no-transform=1')], False),
    ({}, [('Cache-Control', 'private,,max-age=0')], False),
    ({}, [('Cache-Control', 'private="x,y"')], False),
    ({}, [('Cache-Control', '')], False),
    ({'HTTP_CACHE_CONTROL': 'broken;directive'}, [], False),
    ({}, [('Cache-Control', 'private, max-age=0')], True),
    ({'HTTP_CACHE_CONTROL': 'no-cache'}, [('Cache-Control', 'no-store')], True),
    ({}, [('X-Trace', 'owned')], True),
])
def test_profiler_respects_range_and_transform_policy(
        request_headers, response_headers, append, tmp_path, record_property):
    probe(r'''
        request_headers, response_headers, append = CASE
        headers = [('Content-Type', 'text/html')] + response_headers
        env = dict(REQUEST_METHOD='GET', **request_headers)
        before = env.copy()
        captured = []
        def tiny_wsgi(env, start_response):
            start_response('200 OK', headers)
            return [b'body']
        result = web.profiler(tiny_wsgi)(env, lambda s, h: captured.append((s, h)))
        assert env == before and captured == [('200 OK', headers)]
        assert captured[0][1] is headers
        assert result[0] == b'body' and len(result) == (2 if append else 1)
        if append:
            assert b'tiny_wsgi' in result[-1]
    '''.replace('CASE', repr((request_headers, response_headers, append))), tmp_path, record_property)


@pytest.mark.parametrize('header', [
    [('Content-Type', None)], [('Content-Type', b'text/html')], [(None, 'text/html')],
    [('Content-Type', 'text/html'), ('Cache-Control', 'max-age=0, max-age=1')],
])
def test_profiler_omits_report_on_malformed_or_ambiguous_metadata(header, tmp_path, record_property):
    # A permissive callback is not proof of valid WSGI; policy must not rewrite it.
    probe(r'''
        headers = HEADERS
        captured = []
        def tiny_wsgi(env, start_response):
            start_response('200 OK', headers)
            return [b'body']
        result = web.profiler(tiny_wsgi)(
            {'REQUEST_METHOD': 'GET'}, lambda s, h: captured.append((s, h)))
        assert result == [b'body']
        assert captured == [('200 OK', headers)] and captured[0][1] is headers
    '''.replace('HEADERS', repr(header)), tmp_path, record_property)


@pytest.mark.parametrize('append,lazy', [(True, False), (True, True), (False, False), (False, True)])
def test_profiler_real_write_and_iterable_order(append, lazy, tmp_path, record_property):
    probe(r'''
        from wsgiref.handlers import SimpleHandler
        append, lazy = CASE
        headers = [('Content-Type', 'text/html' if append else 'text/plain')]
        output, errors = io.BytesIO(), io.StringIO()
        env = {}
        setup_testing_defaults(env)
        env['QUERY_STRING'] = ''
        handler = SimpleHandler(io.BytesIO(), output, errors, env)
        events, returned = [], []
        real_start = handler.start_response
        def observed_start(*args, **kwargs):
            write = real_start(*args, **kwargs)
            returned.append(write)
            return write
        handler.start_response = observed_start
        class Body:
            def __iter__(self):
                events.append('iter')
                if lazy:
                    begin()
                yield b'iterated-one'
                yield b'iterated-two'
            def close(self):
                events.append('close')
        def begin():
            write = start('200 OK', headers)
            assert write is returned[-1]
            write(b'written-first')
            events.append('write')
        def tiny_wsgi(env, start_response):
            global start
            start = start_response
            if not lazy:
                begin()
            return Body()
        handler.run(web.profiler(tiny_wsgi))
        assert not errors.getvalue(), errors.getvalue()
        wire = output.getvalue()
        head, body = wire.split(b'\r\n\r\n', 1)
        assert b'200 OK' in head
        prefix = b'written-firstiterated-oneiterated-two'
        assert body.startswith(prefix)
        if append:
            assert body[len(prefix):].startswith(b'<pre>') and body.endswith(b'</pre>')
            assert b'tiny_wsgi' in body and b'__iter__' not in body
        else:
            assert body == prefix
        assert events == (['iter', 'write', 'close'] if lazy else ['write', 'iter', 'close'])
    '''.replace('CASE', repr((append, lazy))), tmp_path, record_property)


@pytest.mark.parametrize('first,last', [
    ('html', 'plain'), ('plain', 'html'), ('html', 'no-content'), ('no-content', 'html'),
])
def test_profiler_successful_exc_info_retry_uses_new_response(first, last, tmp_path, record_property):
    probe(r'''
        from wsgiref.handlers import SimpleHandler
        first, last = CASE
        variants = {
            'html': ('200 OK', [('Content-Type', 'text/html')]),
            'plain': ('200 OK', [('Content-Type', 'text/plain')]),
            'no-content': ('204 No Content', []),
        }
        output, errors = io.BytesIO(), io.StringIO()
        env = {}
        setup_testing_defaults(env)
        env['QUERY_STRING'] = ''
        handler = SimpleHandler(io.BytesIO(), output, errors, env)
        seen = []
        original_start = handler.start_response
        def observe(*args):
            seen.append(args)
            return original_start(*args)
        handler.start_response = observe
        marker = RuntimeError('retry')
        def tiny_wsgi(env, start_response):
            start_response(*variants[first])
            try:
                raise marker
            except RuntimeError:
                info = sys.exc_info()
                start_response(*variants[last], info)
                assert seen[-1][2] is info
            return [] if last == 'no-content' else [b'body']
        handler.run(web.profiler(tiny_wsgi))
        assert not errors.getvalue(), errors.getvalue()
        assert len(seen) == 2 and len(seen[0]) == 2 and len(seen[1]) == 3
        for call, variant in zip(seen, (first, last)):
            assert call[0] == variants[variant][0] and call[1] is variants[variant][1]
        head, body = output.getvalue().split(b'\r\n\r\n', 1)
        assert variants[last][0].encode() in head
        assert (b'<pre>' in body) is (last == 'html')
        if last == 'plain':
            assert body == b'body'
        if last == 'no-content':
            assert body == b''
    '''.replace('CASE', repr((first, last))), tmp_path, record_property)


@pytest.mark.parametrize('caught', [False, True])
def test_profiler_failed_lazy_start_keeps_exception_and_closes(caught, tmp_path, record_property):
    probe(r'''
        caught = CAUGHT
        failure = BaseException('start failed')
        events, seen = [], []
        headers = [('Content-Type', 'text/html')]
        write = lambda data: None
        def callback(*args, **kwargs):
            seen.append((args, kwargs))
            if len(seen) == 2:
                raise failure
            return write
        class Body:
            def __iter__(self):
                events.append('iter')
                try:
                    start('200 OK', headers, None)
                except BaseException as exc:
                    assert exc is failure and exc.__context__ is None
                    if not caught:
                        raise
                yield b'body'
            def close(self):
                events.append('close')
        def tiny_wsgi(env, start_response):
            global start
            start = start_response
            assert start(status='200 OK', headers=headers) is write
            return Body()
        try:
            result = web.profiler(tiny_wsgi)({'REQUEST_METHOD': 'GET'}, callback)
        except BaseException as exc:
            assert not caught and exc is failure and exc.__context__ is None
        else:
            assert caught and result == [b'body']
        assert events == ['iter', 'close']
        assert seen == [((), {'status': '200 OK', 'headers': headers}),
                        (('200 OK', headers, None), {})]
        assert seen[0][1]['headers'] is headers and seen[1][0][1] is headers
    '''.replace('CAUGHT', repr(caught)), tmp_path, record_property)


@pytest.mark.parametrize('iteration,closing', [(False, False), (True, False), (False, True), (True, True)])
def test_profiler_bypass_keeps_original_close_owner_and_failure_context(
        iteration, closing, tmp_path, record_property):
    probe(r'''
        iteration, closing = CASE
        iteration_error, close_error = BaseException('iteration'), BaseException('close')
        events = []
        class Iterator:
            def __iter__(self):
                return self
            def __next__(self):
                events.append('next')
                if events.count('next') == 1:
                    return b'body'
                if iteration:
                    raise iteration_error
                raise StopIteration
            def close(self):
                raise AssertionError('not the close owner')
        class Body:
            def __iter__(self):
                events.append('iter')
                return Iterator()
            def close(self):
                events.append('close')
                if closing:
                    raise close_error
        def tiny_wsgi(env, start_response):
            start_response('200 OK', [('Content-Type', 'application/octet-stream')])
            return Body()
        try:
            result = web.profiler(tiny_wsgi)({'REQUEST_METHOD': 'GET'}, lambda s, h: None)
        except BaseException as exc:
            assert exc is (close_error if closing else iteration_error)
            assert exc.__context__ is (iteration_error if closing and iteration else None)
        else:
            assert not iteration and not closing and result == [b'body']
        assert events == ['iter', 'next', 'next', 'close']
    '''.replace('CASE', repr((iteration, closing))), tmp_path, record_property)


def test_profiler_real_exc_info_after_write_propagates_original(tmp_path, record_property):
    probe(r'''
        from wsgiref.handlers import SimpleHandler
        output = io.BytesIO()
        env = {}
        setup_testing_defaults(env)
        handler = SimpleHandler(io.BytesIO(), output, io.StringIO(), env)
        handler.setup_environ()
        marker = RuntimeError('headers already sent')
        events = []
        class Body:
            def __iter__(self):
                try:
                    raise marker
                except RuntimeError:
                    start('500 Internal Server Error', [('Content-Type', 'text/plain')], sys.exc_info())
                yield b'never'
            def close(self):
                events.append('close')
        def tiny_wsgi(env, start_response):
            global start
            start = start_response
            write = start('200 OK', [('Content-Type', 'text/html')])
            write(b'already-written')
            return Body()
        try:
            web.profiler(tiny_wsgi)(env, handler.start_response)
        except RuntimeError as exc:
            assert exc is marker and exc.__context__ is None
        else:
            raise AssertionError('failed retry returned a response')
        assert events == ['close']
        head, body = output.getvalue().split(b'\r\n\r\n', 1)
        assert b'200 OK' in head and body == b'already-written'
    ''', tmp_path, record_property)


def test_profiler_without_successful_start_does_not_add_report(tmp_path, record_property):
    probe(r'''
        def invalid_wsgi(env, start_response):
            return [b'original']
        result = web.profiler(invalid_wsgi)({'REQUEST_METHOD': 'GET'}, lambda s, h: None)
        assert result == [b'original']  # Does not claim to repair the invalid app.
    ''', tmp_path, record_property)


def test_profiler_snapshots_length_before_consuming_callback(tmp_path, record_property):
    probe(r'''
        from wsgiref.handlers import SimpleHandler
        headers = [('Content-Type', 'text/html'), ('Content-Length', '3')]
        output, errors = io.BytesIO(), io.StringIO()
        env = {}
        setup_testing_defaults(env)
        handler = SimpleHandler(io.BytesIO(), output, errors, env)
        real_start = handler.start_response
        writes, events = [], []
        def consuming_start(status, supplied):
            assert supplied is headers
            write = real_start(status, supplied[:])
            supplied.remove(('Content-Length', '3'))
            writes.append(write)
            return write
        handler.start_response = consuming_start
        class Body:
            def __iter__(self):
                events.append('iter')
                yield b'abc'
            def close(self):
                events.append('close')
        def tiny_wsgi(env, start_response):
            assert start_response('200 OK', headers) is writes[-1]
            return Body()
        handler.run(web.profiler(tiny_wsgi))
        assert errors.getvalue() == ''
        assert events == ['iter', 'close']
        head, body = output.getvalue().split(b'\r\n\r\n', 1)
        assert b'Content-Length: 3' in head
        assert headers == [('Content-Type', 'text/html')]
        assert body == b'abc', 'consumed Content-Length must still prevent a report'
    ''', tmp_path, record_property)


@pytest.mark.parametrize('lazy', [False, True])
@pytest.mark.parametrize('protected', [
    ('Content-Length', '3'), ('Content-Encoding', 'identity'),
    ('ETag', '"original"'), ('Cache-Control', 'no-transform'), None,
])
def test_profiler_snapshots_consumed_headers(protected, lazy, tmp_path, record_property):
    probe(r'''
        from wsgiref.handlers import SimpleHandler
        protected, lazy = CASE
        headers = [('Content-Type', 'text/html')]
        if protected is not None:
            headers.append(protected)
        offered = headers[:]
        output, errors = io.BytesIO(), io.StringIO()
        env = {}
        setup_testing_defaults(env)
        handler = SimpleHandler(io.BytesIO(), output, errors, env)
        real_start = handler.start_response
        writes, events, calls = [], [], []
        def consuming_start(*args, **kwargs):
            assert args == () and set(kwargs) == {'status', 'headers'}
            assert kwargs['headers'] is headers
            accepted = headers[:]
            write = real_start(kwargs['status'], accepted)
            # Discard protected metadata, or consume the entire eligible list.
            if protected is None:
                headers.clear()
            else:
                headers.remove(protected)
            calls.append(accepted)
            writes.append(write)
            return write
        handler.start_response = consuming_start
        def begin():
            assert start(status='200 OK', headers=headers) is writes[-1]
        class Body:
            def __iter__(self):
                events.append('iter')
                if lazy:
                    begin()
                yield b'abc'
            def close(self):
                events.append('close')
        def tiny_wsgi(env, start_response):
            global start
            start = start_response
            if not lazy:
                begin()
            return Body()
        handler.run(web.profiler(tiny_wsgi))
        assert errors.getvalue() == ''
        assert events == ['iter', 'close'] and len(calls) == 1
        head, body = output.getvalue().split(b'\r\n\r\n', 1)
        for name, value in offered:
            assert (name + ': ' + value).encode() in head
        if protected is not None:
            assert body == b'abc', 'consumed protected metadata must prevent a report'
        else:
            assert headers == []
            assert body.startswith(b'abc<pre>') and body.endswith(b'</pre>')
            assert b'tiny_wsgi' in body and b'function calls' in body
            assert b'__iter__' not in body
    '''.replace('CASE', repr((protected, lazy))), tmp_path, record_property)


@pytest.mark.parametrize('lazy', [False, True])
@pytest.mark.parametrize('last_eligible', [False, True])
def test_profiler_snapshots_consumed_retry_headers(last_eligible, lazy, tmp_path, record_property):
    probe(r'''
        from wsgiref.handlers import SimpleHandler
        last_eligible, lazy = CASE
        eligible = [('Content-Type', 'text/html')]
        protected = [('Content-Type', 'text/html'), ('Content-Length', '3')]
        first, last = (protected, eligible) if last_eligible else (eligible, protected)
        offered_last = last[:]
        output, errors = io.BytesIO(), io.StringIO()
        env = {}
        setup_testing_defaults(env)
        handler = SimpleHandler(io.BytesIO(), output, errors, env)
        real_start = handler.start_response
        writes, calls, events = [], [], []
        marker = RuntimeError('replace response')
        def consuming_start(*args, **kwargs):
            assert not kwargs
            supplied = args[1]
            assert supplied is (first if not calls else last)
            write = real_start(args[0], supplied[:], *args[2:])
            supplied.clear()
            calls.append(args)
            writes.append(write)
            return write
        handler.start_response = consuming_start
        def begin():
            assert start('200 OK', first) is writes[-1]
            try:
                raise marker
            except RuntimeError:
                info = sys.exc_info()
                assert start('200 OK', last, info) is writes[-1]
                assert calls[-1][2] is info
        class Body:
            def __iter__(self):
                events.append('iter')
                if lazy:
                    begin()
                yield b'abc'
            def close(self):
                events.append('close')
        def tiny_wsgi(env, start_response):
            global start
            start = start_response
            if not lazy:
                begin()
            return Body()
        handler.run(web.profiler(tiny_wsgi))
        assert errors.getvalue() == ''
        assert events == ['iter', 'close'] and len(calls) == 2
        assert first == last == [] and len(calls[0]) == 2 and len(calls[1]) == 3
        head, body = output.getvalue().split(b'\r\n\r\n', 1)
        for name, value in offered_last:
            assert (name + ': ' + value).encode() in head
        if last_eligible:
            assert body.startswith(b'abc<pre>') and b'tiny_wsgi' in body
        else:
            assert body == b'abc'
    '''.replace('CASE', repr((last_eligible, lazy))), tmp_path, record_property)


@pytest.mark.parametrize('lazy', [False, True])
@pytest.mark.parametrize('recover', [False, True])
def test_profiler_consuming_callback_failure_clears_policy(recover, lazy, tmp_path, record_property):
    probe(r'''
        from wsgiref.handlers import SimpleHandler
        recover, lazy = CASE
        first, failed, retry = [[('Content-Type', 'text/html')] for _ in range(3)]
        output, errors = io.BytesIO(), io.StringIO()
        env = {}
        setup_testing_defaults(env)
        handler = SimpleHandler(io.BytesIO(), output, errors, env)
        real_start = handler.start_response
        writes, calls, events = [], [], []
        failure = BaseException('consumed then rejected')
        def consuming_start(*args, **kwargs):
            supplied = args[1]
            assert supplied is (first, failed, retry)[len(calls)]
            calls.append(args)
            if supplied is failed:
                supplied.clear()
                raise failure
            write = real_start(args[0], supplied[:], *args[2:])
            supplied.clear()
            writes.append(write)
            return write
        handler.start_response = consuming_start
        def begin():
            assert start('200 OK', first) is writes[-1]
            try:
                start('200 OK', failed, None)
            except BaseException as exc:
                assert exc is failure and exc.__context__ is None
                if recover:
                    info = sys.exc_info()
                    assert start('200 OK', retry, info) is writes[-1]
                    assert calls[-1][2] is info
            else:
                raise AssertionError('callback failure was swallowed')
        class Body:
            def __iter__(self):
                events.append('iter')
                if lazy:
                    begin()
                yield b'abc'
            def close(self):
                events.append('close')
        def tiny_wsgi(env, start_response):
            global start
            start = start_response
            if not lazy:
                begin()
            return Body()
        handler.run(web.profiler(tiny_wsgi))
        assert errors.getvalue() == ''
        assert events == ['iter', 'close'] and len(calls) == (3 if recover else 2)
        assert first == failed == []
        head, body = output.getvalue().split(b'\r\n\r\n', 1)
        assert b'200 OK' in head and b'Content-Type: text/html' in head
        if recover:
            assert retry == [] and body.startswith(b'abc<pre>') and b'tiny_wsgi' in body
        else:
            assert body == b'abc', 'failed callback must clear previous eligibility'
    '''.replace('CASE', repr((recover, lazy))), tmp_path, record_property)
