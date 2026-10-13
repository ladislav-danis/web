"""
HTTP Utilities
(from web.py)
"""

__all__ = [
    "expires",
    "lastmodified",
    "prefixurl",
    "modified",
    "changequery",
    "url",
    "profiler",
]

import datetime
from urllib.parse import urlencode as urllib_urlencode

from . import net, utils
from . import webapi as web
from .py3helpers import iteritems


def prefixurl(base=""):
    """
    Sorry, this function is really difficult to explain.
    Maybe some other time.
    """
    url = web.ctx.path.lstrip("/")
    for i in range(url.count("/")):
        base += "../"
    if not base:
        base = "./"
    return base


def expires(delta):
    """
    Outputs an `Expires` header for `delta` from now.
    `delta` is a `timedelta` object or an integer number of seconds.
    """
    if isinstance(delta, int):
        delta = datetime.timedelta(seconds=delta)
    date_obj = datetime.datetime.utcnow() + delta
    web.header("Expires", net.httpdate(date_obj))


def lastmodified(date_obj):
    """Outputs a `Last-Modified` header for `datetime`."""
    web.header("Last-Modified", net.httpdate(date_obj))


def modified(date=None, etag=None):
    """
    Checks to see if the page has been modified since the version in the
    requester's cache.

    When you publish pages, you can include `Last-Modified` and `ETag`
    with the date the page was last modified and an opaque token for
    the particular version, respectively. When readers reload the page,
    the browser sends along the modification date and etag value for
    the version it has in its cache. If the page hasn't changed,
    the server can just return `304 Not Modified` and not have to
    send the whole page again.

    This function takes the last-modified date `date` and the ETag `etag`
    and checks the request headers. A matching validator raises NotModified;
    otherwise it returns `True` so normal response generation can continue.
    It sets the supplied `Last-Modified` and `ETag` output headers in either
    case. Either validator may match (OR semantics); dates allow one second
    of grace because HTTP dates have no sub-second precision.
    """
    n = {x.strip('" ') for x in web.ctx.env.get("HTTP_IF_NONE_MATCH", "").split(",")}
    m = net.parsehttpdate(web.ctx.env.get("HTTP_IF_MODIFIED_SINCE", "").split(";")[0])
    validate = False
    if etag:
        if "*" in n or etag in n:
            validate = True
    if date and m:
        # we subtract a second because
        # HTTP dates don't have sub-second precision
        if date - datetime.timedelta(seconds=1) <= m:
            validate = True

    if date:
        lastmodified(date)
    if etag:
        web.header("ETag", '"' + etag + '"')
    if validate:
        raise web.notmodified()
    else:
        return True


def urlencode(query, doseq=0):
    """
    Same as urllib.urlencode, but supports unicode strings.

        >>> urlencode({'text':'foo bar'})
        'text=foo+bar'
        >>> urlencode({'x': [1, 2]}, doseq=True)
        'x=1&x=2'
    """

    def convert(value, doseq=False):
        if doseq and isinstance(value, list):
            return [convert(v) for v in value]
        else:
            return utils.safestr(value)

    query = {k: convert(v, doseq) for k, v in query.items()}
    return urllib_urlencode(query, doseq=doseq)


def changequery(query=None, **kw):
    """
    Imagine you're at `/foo?a=1&b=2`. Then `changequery(a=3)` will return
    `/foo?a=3&b=2` -- the same URL but with the arguments you requested
    changed.
    """
    if query is None:
        query = web.rawinput(method="get")
    for k, v in iteritems(kw):
        if v is None:
            query.pop(k, None)
        else:
            query[k] = v
    out = web.ctx.path
    if query:
        out += "?" + urlencode(query, doseq=True)
    return out


def url(path=None, doseq=False, **kw):
    """
    Makes url by concatenating web.ctx.homepath and path and the
    query string created using the arguments.
    """
    if path is None:
        path = web.ctx.path
    if path.startswith("/"):
        out = web.ctx.homepath + path
    else:
        out = path

    if kw:
        out += "?" + urlencode(kw, doseq=doseq)

    return out


def profiler(app):
    """Append a UTF-8 report only to eligible development GET/200 HTML.

    Profiles the callable invocation, not deferred iteration; materializes the
    body and eagerly calls its callable close(), even on iteration failure.
    Other responses bypass report insertion with status/headers/chunks intact.
    This is not streaming middleware or a repair of invalid underlying HTTP;
    see docs/http.md for the conservative policy and remaining caller constraints.
    """
    import re

    from .utils import profile

    # Deliberately a narrow allowlist, not a general MIME parser.
    html_type = re.compile(
        r'[ \t]*text/html[ \t]*(?:;[ \t]*charset[ \t]*=[ \t]*(?:utf-8|"utf-8")[ \t]*)?',
        re.IGNORECASE | re.ASCII,
    )

    token = r"[!#$%&'*+.^_`|~0-9A-Za-z-]+"
    protected = {
        "content-length", "content-encoding", "content-range", "etag",
        "last-modified", "content-md5", "digest", "content-digest",
        "repr-digest", "content-disposition",
    }

    def eligible(e, status, headers):
        if (e.get("REQUEST_METHOD") != "GET" or status != "200 OK"
                or "HTTP_RANGE" in e or "HTTP_IF_RANGE" in e):
            return False
        fields = {}
        for name, value in headers:
            if (not isinstance(name, str) or not isinstance(value, str)
                    or not re.fullmatch(token, name)
                    or any(ord(c) < 32 and c != "\t" or ord(c) == 127 for c in value)):
                return False
            name = name.lower()
            if name in fields or name in protected:
                return False
            fields[name] = value
        for mapping, key in ((fields, "cache-control"), (e, "HTTP_CACHE_CONTROL")):
            if key in mapping:
                seen = set()
                for directive in mapping[key].split(","):
                    directive = directive.strip(" \t")
                    name = directive.split("=", 1)[0].strip(" \t").lower()
                    if (not re.fullmatch(token + r"(?:[ \t]*=[ \t]*" + token + r")?", directive)
                            or name == "no-transform" or name in seen):
                        return False
                    seen.add(name)
        return html_type.fullmatch(fields.get("content-type", "")) is not None

    def profile_internal(e, o):
        append_report = False

        def start_response(*args, **kwargs):
            nonlocal append_report
            append_report = False
            status = args[0] if args else kwargs["status"]
            headers = args[1] if len(args) > 1 else kwargs["headers"]
            # The server owns the offered list and may consume or mutate it.
            offered_eligible = eligible(e, status, headers)
            write = o(*args, **kwargs)
            append_report = offered_eligible
            return write

        out, result = profile(app)(e, start_response)
        try:
            body = list(out)
        finally:
            close = getattr(out, "close", None)
            if callable(close):
                close()
        if e.get("REQUEST_METHOD") == "HEAD" or not append_report:
            return body
        return body + [("<pre>" + net.websafe(result) + "</pre>").encode("utf-8")]

    return profile_internal


if __name__ == "__main__":
    import doctest

    doctest.testmod()
