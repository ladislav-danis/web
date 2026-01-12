"""
HTTP Utilities
(from web.py)

This module provides utility functions for handling HTTP headers, URL manipulation,
and caching mechanisms.

Examples:
    >>> from web.http import expires, lastmodified
    >>> import datetime
    >>> # Set an expiration date 1 hour from now
    >>> expires(datetime.timedelta(hours=1))
    >>> # Set a last modified date
    >>> lastmodified(datetime.datetime.now())
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
    Generate a relative URL prefix for linking to parent directories.

    This function is used to create relative paths when generating links in
    nested directory structures. It calculates how many "../" prefixes are
    needed based on the current path depth.

    Args:
        base (str): Base path string to start with. Defaults to empty string.

    Returns:
        str: Relative path prefix (e.g., "./", "../", "../../").

    Examples:
        >>> from web import ctx
        >>> # Assuming ctx.path = "/foo/bar"
        >>> prefixurl()
        '../'
    """
    url = web.ctx.path.lstrip("/")
    for i in range(url.count("/")):
        base += "../"
    if not base:
        base = "./"
    return base


def expires(delta):
    """
    Output an `Expires` header for `delta` from now.

    This function sets the HTTP Expires header to indicate when a resource
    should be considered stale. The expiration time is calculated as the
    current UTC time plus the provided delta.

    Args:
        delta (datetime.timedelta or int): Time delta until expiration.
            If an integer is provided, it's interpreted as seconds.

    Examples:
        >>> import datetime
        >>> # Set expiration to 1 hour from now
        >>> expires(datetime.timedelta(hours=1))
        >>> # Set expiration to 3600 seconds from now
        >>> expires(3600)
    """
    if isinstance(delta, int):
        delta = datetime.timedelta(seconds=delta)
    date_obj = datetime.datetime.utcnow() + delta
    web.header("Expires", net.httpdate(date_obj))


def lastmodified(date_obj):
    """
    Output a `Last-Modified` header for `datetime`.

    Sets the HTTP Last-Modified header to indicate when a resource was last
    modified. This is used for cache validation.

    Args:
        date_obj (datetime.datetime): The datetime when the resource was last modified.

    Examples:
        >>> import datetime
        >>> # Set last modified time to now
        >>> lastmodified(datetime.datetime.now())
    """
    web.header("Last-Modified", net.httpdate(date_obj))


def modified(date=None, etag=None):
    """
    Check if a page has been modified since the version in the requester's cache.

    This function implements HTTP cache validation by checking the If-None-Match
    and If-Modified-Since headers. It returns True if the resource hasn't been
    modified, or raises a NotModified error if it has.

    When you publish pages, you can include `Last-Modified` and `ETag`
    with the date the page was last modified and an opaque token for
    the particular version, respectively. When readers reload the page,
    the browser sends along the modification date and etag value for
    the version it has in its cache. If the page hasn't changed,
    the server can just return `304 Not Modified` and not have to
    send the whole page again.

    Args:
        date (datetime.datetime, optional): The last modified datetime of the resource.
        etag (str, optional): An opaque token representing the version of the resource.

    Returns:
        bool: True if the resource hasn't been modified (cache is valid).

    Raises:
        web.notmodified: If the resource has been modified since the client's cache.

    Examples:
        >>> import datetime
        >>> # Check if a resource has been modified with last modified date
        >>> modified(date=datetime.datetime.now())
        True
        >>> # Check with ETag
        >>> modified(etag="abc123")
        True
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

    This function encodes a dictionary into a URL-encoded string, handling
    Unicode characters properly.

    Args:
        query (dict): Dictionary to encode.
        doseq (bool): If True, multiple values for the same key are encoded
            as separate key-value pairs.

    Returns:
        str: URL-encoded string.

    Examples:
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
    Change query parameters in the current URL.

    This function allows you to modify query parameters while preserving
    the rest of the URL. It's useful for creating links with modified
    query strings.

    Args:
        query (dict, optional): Query parameters to modify. If None,
            uses the current GET parameters.
        **kw: Keyword arguments representing new or updated query parameters.

    Returns:
        str: Modified URL with updated query parameters.

    Examples:
        >>> # Assuming current URL is /foo?a=1&b=2
        >>> changequery(a=3)
        '/foo?a=3&b=2'
        >>> # Remove a parameter
        >>> changequery(a=None)
        '/foo?b=2'
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
    Make URL by concatenating web.ctx.homepath and path with query parameters.

    This function constructs a complete URL by combining the home path,
    a given path, and optional query parameters.

    Args:
        path (str, optional): Path to append to homepath. If None, uses
            the current context path.
        doseq (bool): If True, multiple values for the same key are encoded
            as separate key-value pairs in query string.
        **kw: Additional query parameters to include.

    Returns:
        str: Complete URL with path and query parameters.

    Examples:
        >>> # Using default path and adding query parameters
        >>> url(x=1, y=2)
        '/?x=1&y=2'
        >>> # With specific path
        >>> url('/foo', a=1)
        '/foo?a=1'
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
    """
    Output basic profiling information at the bottom of each response.

    This function wraps a WSGI application to add profiling information
    to the response body. It's useful for performance debugging.

    Args:
        app (callable): The WSGI application to profile.

    Returns:
        callable: A wrapped WSGI application that includes profiling info.

    Examples:
        >>> # Wrap an application with profiling
        >>> app = profiler(my_wsgi_app)
    """
    from utils import profile

    def profile_internal(e, o):
        out, result = profile(app)(e, o)
        return list(out) + ["<pre>" + net.websafe(result) + "</pre>"]

    return profile_internal


if __name__ == "__main__":
    import doctest

    doctest.testmod()
