"""Executable net.md and pinned helper contracts, without application imports.

Probes use fresh isolated interpreters, synthetic HOME/CWD and pre-import Python
network/import guards. These are test isolation, not an operating-system sandbox.
"""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import textwrap

import pytest


WEB_ROOT = Path(__file__).resolve().parents[1]
DOC = WEB_ROOT / "docs/net.md"
BOOTSTRAP = r'''
import importlib.abc
import json
from pathlib import Path
import sys

class NoApplication(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {'core', 'modules', 'dotenv'}:
            raise AssertionError('Framework probe imported ' + fullname)
sys.meta_path.insert(0, NoApplication())

def offline(event, args):
    if event.startswith('socket.') and event != 'socket.__new__':
        raise AssertionError('Framework probe attempted network: ' + event)
sys.addaudithook(offline)
sys.path.insert(0, sys.argv[1])
import web
assert Path(web.__file__).resolve().parent == Path(sys.argv[1]) / 'web'
from web import net
'''


def probe(source, tmp_path, record_property):
    env = {"PATH": os.defpath, "PYTHON_DOTENV_DISABLED": "1",
           "HOME": str(tmp_path), "TMPDIR": str(tmp_path), "LC_ALL": "C"}
    result = subprocess.run(
        [sys.executable, "-I", "-c", BOOTSTRAP + "\n" + textwrap.dedent(source),
         str(WEB_ROOT.parent)], env=env, cwd=tmp_path,
        text=True, capture_output=True, timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    record_property("probe_stdout", result.stdout)


def fences(raw):
    """Keep literal fence bytes; headings inside code are never section markers."""
    heading = ""
    opened = None
    result = []
    for number, line in enumerate(raw.splitlines(keepends=True), 1):
        if opened is not None:
            if line.rstrip(b"\r\n") == b"```":
                result.append((heading, opened, b"".join(body)))
                opened = None
            else:
                body.append(line)
        elif line.startswith(b"```"):
            assert line.rstrip(b"\r\n") == b"```python", (number, line)
            opened, body = number, []
        elif line.startswith(b"#"):
            heading = line.decode("utf-8").strip()
    assert opened is None, "Unclosed Markdown fence"
    assert result, "No executable examples"
    return result


def execute_fences(selected, tmp_path, record_property):
    assert selected
    record_property("markdown_sha256", hashlib.sha256(DOC.read_bytes()).hexdigest())
    payload = [(heading, line, code.decode("utf-8")) for heading, line, code in selected]
    probe('''
        import doctest
        import hashlib
        import io
        examples = ''' + repr(payload) + '''
        results = []
        failures = []
        for heading, line, code in examples:
            # The page documents this shared import setup. Nothing else (such
            # as date_header or datetime) is supplied to individual fences.
            namespace = {'__name__': '__main__'}
            exec('from web.net import *', namespace)
            if '>>>' in code:
                runner = doctest.DocTestRunner()
                test = doctest.DocTestParser().get_doctest(
                    code, namespace, heading, 'docs/net.md', line)
                log = io.StringIO()
                outcome = runner.run(test, out=log.write)
                assert outcome.attempted > 0
                if outcome.failed:
                    failures.append(log.getvalue())
                attempted = outcome.attempted
            else:
                exec(compile(code, 'docs/net.md:' + str(line), 'exec'), namespace)
                attempted = 0
            results.append({'heading': heading, 'line': line,
                            'sha256': hashlib.sha256(code.encode('utf-8')).hexdigest(),
                            'doctest_attempted': attempted})
        print(json.dumps(results))
        assert not failures, '\\n'.join(failures)
    ''', tmp_path, record_property)


@pytest.mark.parametrize("variable", ["safe_html", "safe_output"], ids=["htmlquote", "websafe"])
def test_html_usage_markdown(variable, tmp_path, record_property):
    selected = [item for item in fences(DOC.read_bytes())
                if (">>> " + variable + " =").encode() in item[2]]
    assert len(selected) == 1
    execute_fences(selected, tmp_path, record_property)


@pytest.mark.parametrize("index", [0, 1], ids=["format", "parse"])
def test_http_usage_markdown(index, tmp_path, record_property):
    selected = [item for item in fences(DOC.read_bytes())
                if item[0] == "### HTTP Date Handling"]
    assert len(selected) == 2
    execute_fences([selected[index]], tmp_path, record_property)


def test_httpdate_formats_fields_without_timezone_conversion(tmp_path, record_property):
    probe(r'''
        import datetime as dt
        import locale
        previous = locale.setlocale(locale.LC_TIME)
        try:
            locale.setlocale(locale.LC_TIME, 'C')
            utc = dt.datetime(2026, 2, 6, 9, 1, 6, 987654, tzinfo=dt.timezone.utc)
            assert net.httpdate(utc) == 'Fri, 06 Feb 2026 09:01:06 GMT'
            assert net.httpdate(utc.replace(tzinfo=None)) == 'Fri, 06 Feb 2026 09:01:06 GMT'
            offset = dt.datetime(2026, 2, 6, 0, 1, 6,
                                 tzinfo=dt.timezone(dt.timedelta(hours=2)))
            assert net.httpdate(offset) == 'Fri, 06 Feb 2026 00:01:06 GMT'
            converted = offset.astimezone(dt.timezone.utc)
            assert net.httpdate(converted) == 'Thu, 05 Feb 2026 22:01:06 GMT'
            negative = dt.datetime(2026, 2, 6, 23, 1, 6,
                                   tzinfo=dt.timezone(dt.timedelta(hours=-3)))
            assert net.httpdate(negative) == 'Fri, 06 Feb 2026 23:01:06 GMT'
            assert net.httpdate(negative.astimezone(dt.timezone.utc)) == 'Sat, 07 Feb 2026 02:01:06 GMT'
            parsed = net.parsehttpdate('Fri, 06 Feb 2026 09:01:06 GMT')
            assert parsed == dt.datetime(2026, 2, 6, 9, 1, 6)
            assert parsed.tzinfo is None
            assert net.parsehttpdate('not an HTTP date') is None
        finally:
            locale.setlocale(locale.LC_TIME, previous)
        print(json.dumps({'UTC': 'Fri, 06 Feb 2026 09:01:06 GMT',
                          'offset_conversion': False, 'parsed_tzinfo': None}))
    ''', tmp_path, record_property)


def test_httpdate_delegates_locale_sensitive_format(tmp_path, record_property):
    probe(r'''
        import datetime as dt
        class ObservedDate(dt.datetime):
            def strftime(self, fmt):
                formats.append(fmt)
                return 'locale-dependent-format-result'
        formats = []
        actual = net.httpdate(ObservedDate(2026, 2, 6))
        assert formats == ['%a, %d %b %Y %H:%M:%S GMT']
        assert actual == 'locale-dependent-format-result'
        print(json.dumps({'strftime_formats': formats,
                          'note': 'delegation boundary, not a foreign-locale execution'}))
    ''', tmp_path, record_property)


def test_ipv4_accepts_tolerant_integer_components(tmp_path, record_property):
    probe(r'''
        accepted = ['0.0.0.0', '255.255.255.255', '192.168.1.1',
                    '+1.2.3.4', '001.002.003.004', '1.2.3.\t4',
                    '\t1.2.3.4', '1.2.3.4\n', '-0.2.3.4',
                    '1_0.2.3.4', '\u0661.2.3.4', '\u00a01.2.3.4']
        for address in accepted:
            assert net.validipaddr(address) is True, repr(address)
        # Parsing preserves the accepted spelling, rather than canonicalizing.
        assert net.validip('+1.002.3.4:80') == ('+1.002.3.4', 80)
        print(json.dumps({'accepted': accepted}))
    ''', tmp_path, record_property)


def test_ipv4_rejects_spaces_count_syntax_and_range(tmp_path, record_property):
    probe(r'''
        rejected = ['', '1.2.3', '1.2.3.4.5', '.2.3.4', '1..3.4',
                    '1.2.3.', ' 1.2.3.4', '1.2.3.4 ', '1.2. 3.4',
                    '-1.2.3.4', '256.2.3.4', '1.2.3.999',
                    '0x1.2.3.4', '1e1.2.3.4', 'one.2.3.4',
                    '+.2.3.4', '1_.2.3.4', '1.2.3.4/24']
        for address in rejected:
            assert net.validipaddr(address) is False, repr(address)
        print(json.dumps({'rejected': rejected}))
    ''', tmp_path, record_property)


def test_html_five_entity_mapping_and_inversion(tmp_path, record_property):
    probe(r'''
        import itertools
        pairs = [('"', '&quot;'), ("'", '&#39;'), ('>', '&gt;'),
                 ('<', '&lt;'), ('&', '&amp;')]
        for plain, quoted in pairs:
            assert net.htmlquote(plain) == quoted
            assert net.htmlunquote(quoted) == plain
        assert net.htmlquote('&<>\'"') == '&amp;&lt;&gt;&#39;&quot;'
        assert net.htmlunquote('&quot;&#39;&gt;&lt;&amp;') == '"\'><&'
        checked = 0
        for size in range(4):
            for chars in itertools.product('&<>\'"', repeat=size):
                text = ''.join(chars)
                assert net.htmlunquote(net.htmlquote(text)) == text
                checked += 1
        for text in ['&lt;', '&#60;', '&apos;', '&nbsp;', '&amp;lt;', 'žluťoučký']:
            assert net.htmlunquote(net.htmlquote(text)) == text
        print(json.dumps({'pairs': pairs, 'bounded_roundtrips': checked}))
    ''', tmp_path, record_property)


def test_htmlunquote_is_not_general_or_recursive_decoder(tmp_path, record_property):
    probe(r'''
        untouched = '&#60; &#x3c; &apos; &nbsp; &AMP; &#039; &lt'
        assert net.htmlunquote(untouched) == untouched
        assert net.htmlunquote('&amp;quot;&amp;#39;&amp;gt;&amp;lt;&amp;amp;') == '&quot;&#39;&gt;&lt;&amp;'
        assert net.htmlunquote('&amp;lt;script&amp;gt;') == '&lt;script&gt;'
        print(json.dumps({'unrecognized': untouched, 'ampersand_replaced_last': True}))
    ''', tmp_path, record_property)


def test_html_and_url_escaping_have_context_boundaries(tmp_path, record_property):
    probe(r'''
        text = '<script>alert("xss")</script>'
        expected = '&lt;script&gt;alert(&quot;xss&quot;)&lt;/script&gt;'
        assert net.htmlquote(text) == expected
        assert net.websafe(text) == expected
        assert net.websafe(None) == ''
        assert net.websafe(42) == '42'
        assert net.websafe('ž<&'.encode('utf-8')) == 'ž&lt;&amp;'
        assert net.htmlquote('javascript:alert(1)') == 'javascript:alert(1)'
        assert net.websafe('javascript:alert(1)') == 'javascript:alert(1)'
        assert net.urlquote('a/b ?x=1&y=2#z') == 'a/b%20%3Fx%3D1%26y%3D2%23z'
        print(json.dumps({'HTML': expected, 'URL_slash_preserved': True,
                          'HTML_is_not_URL_validation': True}))
    ''', tmp_path, record_property)


def test_all_net_markdown_fences_execute(tmp_path, record_property):
    raw = DOC.read_bytes()
    assert b'`from web.net import *`' in raw, "Document the shared import setup"
    examples = fences(raw)
    assert len(examples) == 21
    assert sum(b'>>>' in code for _, _, code in examples) == 20
    execute_fences(examples, tmp_path, record_property)


def test_fence_extractor_keeps_code_headings_and_requires_closure():
    raw = b'## Section\n```python\n# code comment\nassert True\n```\n'
    assert fences(raw) == [('## Section', 2, b'# code comment\nassert True\n')]
    with pytest.raises(AssertionError, match='Unclosed Markdown fence'):
        fences(b'## Section\n```python\nassert True\n')
