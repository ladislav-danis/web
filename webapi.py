"""
Web API (wrapper around WSGI)
(from web.py)

This module provides a web framework built on top of WSGI with utilities for
handling HTTP requests and responses.
"""

import pprint
import sys
import urllib
from http.cookies import CookieError, Morsel, SimpleCookie
from urllib.parse import parse_qs, quote, unquote, urljoin

import multipart

from .utils import dictadd, intget, safestr, storage, storify, threadeddict

__all__ = [
    "config",
    "header",
    "debug",
    "input",
    "data",
    "setcookie",
    "cookies",
    "ctx",
    "HTTPError",
    # 200, 201, 202, 204
    "OK",
    "Created",
    "Accepted",
    "NoContent",
    "ok",
    "created",
    "accepted",
    "nocontent",
    # 301, 302, 303, 304, 307
    "Redirect",
    "Found",
    "SeeOther",
    "NotModified",
    "TempRedirect",
    "redirect",
    "found",
    "seeother",
    "notmodified",
    "tempredirect",
    # 400, 401, 403, 404, 405, 406, 409, 410, 412, 415, 451
    "BadRequest",
    "Unauthorized",
    "Forbidden",
    "NotFound",
    "NoMethod",
    "NotAcceptable",
    "Conflict",
    "Gone",
    "PreconditionFailed",
    "UnsupportedMediaType",
    "UnavailableForLegalReasons",
    "badrequest",
    "unauthorized",
    "forbidden",
    "notfound",
    "nomethod",
    "notacceptable",
    "conflict",
    "gone",
    "preconditionfailed",
    "unsupportedmediatype",
    "unavailableforlegalreasons",
    # 500
    "InternalError",
    "internalerror",
]

config = storage()
config.__doc__ = """
A configuration object for various aspects of web.py.

Args:
    debug (bool): When True, enables reloading, disables template caching and
        sets internalerror to debugerror.

Examples:
    >>> config.debug = True
    >>> print(config.debug)
    True
"""


class HTTPError(Exception):
    """
    Base exception class for HTTP errors.

    Args:
        status (str): The HTTP status code and message (e.g., "404 Not Found").
        headers (dict): HTTP headers to include in the response.
        data (str): The response body data.

    Examples:
        >>> try:
        ...     raise HTTPError("404 Not Found")
        ... except HTTPError as e:
        ...     print(e.args[0])
        '404 Not Found'
    """

    def __init__(self, status, headers={}, data=""):
        ctx.status = status
        for k, v in headers.items():
            header(k, v)
        self.data = data
        Exception.__init__(self, status)


def _status_code(status, data=None, classname=None, docstring=None):
    """
    Creates a new HTTP status code class.

    Args:
        status (str): The HTTP status code and message (e.g., "200 OK").
        data (str): The default response body for this status.
        classname (str): The name of the class to create.
        docstring (str): The docstring for the new class.

    Returns:
        type: A new HTTPError subclass for the given status code.

    Examples:
        >>> status_class = _status_code("201 Created")
        >>> print(status_class.__name__)
        'Created'
    """
    if data is None:
        data = status.split(" ", 1)[1]
    classname = status.split(" ", 1)[1].replace(
        " ", ""
    )  # 304 Not Modified -> NotModified
    docstring = docstring or "`%s` status" % status

    def __init__(self, data=data, headers={}):
        HTTPError.__init__(self, status, headers, data)

    # trick to create class dynamically with dynamic docstring.
    return type(
        classname, (HTTPError, object), {"__doc__": docstring, "__init__": __init__}
    )


ok = OK = _status_code("200 OK", data="")
created = Created = _status_code("201 Created")
accepted = Accepted = _status_code("202 Accepted")
nocontent = NoContent = _status_code("204 No Content")


class Redirect(HTTPError):
    """
    A `301 Moved Permanently` redirect.

    Args:
        url (str): The URL to redirect to.
        status (str): The HTTP status code for the redirect (default: "301 Moved Permanently").
        absolute (bool): Whether to use an absolute URL (default: False).

    Examples:
        >>> redirect = Redirect("/new-page")
        >>> print(redirect.args[0])
        '301 Moved Permanently'
    """

    def __init__(self, url, status="301 Moved Permanently", absolute=False):
        """
        Returns a `status` redirect to the new URL.
        `url` is joined with the base URL so that things like
        `redirect("about") will work properly.

        Args:
            url (str): The URL to redirect to.
            status (str): The HTTP status code for the redirect.
            absolute (bool): Whether to use an absolute URL.
        """
        newloc = urljoin(ctx.path, url)

        if newloc.startswith("/"):
            if absolute:
                home = ctx.realhome
            else:
                home = ctx.home
            newloc = home + newloc

        headers = {"Content-Type": "text/html", "Location": newloc}
        HTTPError.__init__(self, status, headers, "")


redirect = Redirect


class Found(Redirect):
    """
    A `302 Found` redirect.

    Args:
        url (str): The URL to redirect to.
        absolute (bool): Whether to use an absolute URL (default: False).

    Examples:
        >>> found = Found("/new-page")
        >>> print(found.args[0])
        '302 Found'
    """

    def __init__(self, url, absolute=False):
        Redirect.__init__(self, url, "302 Found", absolute=absolute)


found = Found


class SeeOther(Redirect):
    """
    A `303 See Other` redirect.

    Args:
        url (str): The URL to redirect to.
        absolute (bool): Whether to use an absolute URL (default: False).

    Examples:
        >>> see_other = SeeOther("/new-page")
        >>> print(see_other.args[0])
        '303 See Other'
    """

    def __init__(self, url, absolute=False):
        Redirect.__init__(self, url, "303 See Other", absolute=absolute)


seeother = SeeOther


class NotModified(HTTPError):
    """
    A `304 Not Modified` status.

    Examples:
        >>> not_modified = NotModified()
        >>> print(not_modified.args[0])
        '304 Not Modified'
    """

    def __init__(self):
        HTTPError.__init__(self, "304 Not Modified")


notmodified = NotModified


class TempRedirect(Redirect):
    """
    A `307 Temporary Redirect` redirect.

    Args:
        url (str): The URL to redirect to.
        absolute (bool): Whether to use an absolute URL (default: False).

    Examples:
        >>> temp_redirect = TempRedirect("/new-page")
        >>> print(temp_redirect.args[0])
        '307 Temporary Redirect'
    """

    def __init__(self, url, absolute=False):
        Redirect.__init__(self, url, "307 Temporary Redirect", absolute=absolute)


tempredirect = TempRedirect


class BadRequest(HTTPError):
    """
    `400 Bad Request` error.

    Args:
        message (str): The error message (default: "bad request").

    Examples:
        >>> bad_request = BadRequest()
        >>> print(bad_request.args[0])
        '400 Bad Request'
    """

    message = "bad request"

    def __init__(self, message=None):
        status = "400 Bad Request"
        headers = {"Content-Type": "text/html"}
        HTTPError.__init__(self, status, headers, message or self.message)


badrequest = BadRequest


class Unauthorized(HTTPError):
    """
    `401 Unauthorized` error.

    Args:
        message (str): The error message (default: "unauthorized").

    Examples:
        >>> unauthorized = Unauthorized()
        >>> print(unauthorized.args[0])
        '401 Unauthorized'
    """

    message = "unauthorized"

    def __init__(self, message=None):
        status = "401 Unauthorized"
        headers = {"Content-Type": "text/html"}
        HTTPError.__init__(self, status, headers, message or self.message)


unauthorized = Unauthorized


class Forbidden(HTTPError):
    """
    `403 Forbidden` error.

    Args:
        message (str): The error message (default: "forbidden").

    Examples:
        >>> forbidden = Forbidden()
        >>> print(forbidden.args[0])
        '403 Forbidden'
    """

    message = "forbidden"

    def __init__(self, message=None):
        status = "403 Forbidden"
        headers = {"Content-Type": "text/html"}
        HTTPError.__init__(self, status, headers, message or self.message)


forbidden = Forbidden


class _NotFound(HTTPError):
    """
    `404 Not Found` error.

    Args:
        message (str): The error message (default: "not found").

    Examples:
        >>> not_found = _NotFound()
        >>> print(not_found.args[0])
        '404 Not Found'
    """

    message = "not found"

    def __init__(self, message=None):
        status = "404 Not Found"
        headers = {"Content-Type": "text/html; charset=utf-8"}
        HTTPError.__init__(self, status, headers, message or self.message)


def NotFound(message=None):
    """
    Returns HTTPError with '404 Not Found' error from the active application.

    Args:
        message (str): The error message to display (optional).

    Returns:
        HTTPError: A 404 Not Found error.

    Examples:
        >>> error = NotFound()
        >>> print(error.args[0])
        '404 Not Found'
    """
    if message:
        return _NotFound(message)
    elif ctx.get("app_stack"):
        return ctx.app_stack[-1].notfound()
    else:
        return _NotFound()


notfound = NotFound


class NoMethod(HTTPError):
    """
    A `405 Method Not Allowed` error.

    Args:
        cls (object): The class to check for allowed methods (optional).

    Examples:
        >>> no_method = NoMethod()
        >>> print(no_method.args[0])
        '405 Method Not Allowed'
    """

    message = "method not allowed"

    def __init__(self, cls=None):
        status = "405 Method Not Allowed"
        headers = {}
        headers["Content-Type"] = "text/html"

        methods = ["GET", "HEAD", "POST", "PUT", "DELETE"]
        if cls:
            methods = [method for method in methods if hasattr(cls, method)]

        headers["Allow"] = ", ".join(methods)
        HTTPError.__init__(self, status, headers, self.message)


nomethod = NoMethod


class NotAcceptable(HTTPError):
    """
    `406 Not Acceptable` error.

    Args:
        message (str): The error message (default: "not acceptable").

    Examples:
        >>> not_acceptable = NotAcceptable()
        >>> print(not_acceptable.args[0])
        '406 Not Acceptable'
    """

    message = "not acceptable"

    def __init__(self, message=None):
        status = "406 Not Acceptable"
        headers = {"Content-Type": "text/html"}
        HTTPError.__init__(self, status, headers, message or self.message)


notacceptable = NotAcceptable


class Conflict(HTTPError):
    """
    `409 Conflict` error.

    Args:
        message (str): The error message (default: "conflict").

    Examples:
        >>> conflict = Conflict()
        >>> print(conflict.args[0])
        '409 Conflict'
    """

    message = "conflict"

    def __init__(self, message=None):
        status = "409 Conflict"
        headers = {"Content-Type": "text/html"}
        HTTPError.__init__(self, status, headers, message or self.message)


conflict = Conflict


class Gone(HTTPError):
    """
    `410 Gone` error.

    Args:
        message (str): The error message (default: "gone").

    Examples:
        >>> gone = Gone()
        >>> print(gone.args[0])
        '410 Gone'
    """

    message = "gone"

    def __init__(self, message=None):
        status = "410 Gone"
        headers = {"Content-Type": "text/html"}
        HTTPError.__init__(self, status, headers, message or self.message)


gone = Gone


class PreconditionFailed(HTTPError):
    """
    `412 Precondition Failed` error.

    Args:
        message (str): The error message (default: "precondition failed").

    Examples:
        >>> precondition_failed = PreconditionFailed()
        >>> print(precondition_failed.args[0])
        '412 Precondition Failed'
    """

    message = "precondition failed"

    def __init__(self, message=None):
        status = "412 Precondition Failed"
        headers = {"Content-Type": "text/html"}
        HTTPError.__init__(self, status, headers, message or self.message)


preconditionfailed = PreconditionFailed


class UnsupportedMediaType(HTTPError):
    """
    `415 Unsupported Media Type` error.

    Args:
        message (str): The error message (default: "unsupported media type").

    Examples:
        >>> unsupported_media_type = UnsupportedMediaType()
        >>> print(unsupported_media_type.args[0])
        '415 Unsupported Media Type'
    """

    message = "unsupported media type"

    def __init__(self, message=None):
        status = "415 Unsupported Media Type"
        headers = {"Content-Type": "text/html"}
        HTTPError.__init__(self, status, headers, message or self.message)


unsupportedmediatype = UnsupportedMediaType


class _UnavailableForLegalReasons(HTTPError):
    """
    `451 Unavailable For Legal Reasons` error.

    Args:
        message (str): The error message (default: "unavailable for legal reasons").

    Examples:
        >>> unavailable_for_legal_reasons = _UnavailableForLegalReasons()
        >>> print(unavailable_for_legal_reasons.args[0])
        '451 Unavailable For Legal Reasons'
    """

    message = "unavailable for legal reasons"

    def __init__(self, message=None):
        status = "451 Unavailable For Legal Reasons"
        headers = {"Content-Type": "text/html"}
        HTTPError.__init__(self, status, headers, message or self.message)


def UnavailableForLegalReasons(message=None):
    """
    Returns HTTPError with '415 Unavailable For Legal Reasons' error from the active application.

    Args:
        message (str): The error message to display (optional).

    Returns:
        HTTPError: A 451 Unavailable For Legal Reasons error.

    Examples:
        >>> error = UnavailableForLegalReasons()
        >>> print(error.args[0])
        '451 Unavailable For Legal Reasons'
    """
    if message:
        return _UnavailableForLegalReasons(message)
    elif ctx.get("app_stack"):
        return ctx.app_stack[-1].unavailableforlegalreasons()
    else:
        return _UnavailableForLegalReasons()


unavailableforlegalreasons = UnavailableForLegalReasons


class _InternalError(HTTPError):
    """
    500 Internal Server Error`.

    Args:
        message (str): The error message (default: "internal server error").

    Examples:
        >>> internal_error = _InternalError()
        >>> print(internal_error.args[0])
        '500 Internal Server Error'
    """

    message = "internal server error"

    def __init__(self, message=None):
        status = "500 Internal Server Error"
        headers = {"Content-Type": "text/html"}
        HTTPError.__init__(self, status, headers, message or self.message)


def InternalError(message=None):
    """
    Returns HTTPError with '500 internal error' error from the active application.

    Args:
        message (str): The error message to display (optional).

    Returns:
        HTTPError: A 500 Internal Server Error.

    Examples:
        >>> error = InternalError()
        >>> print(error.args[0])
        '500 Internal Server Error'
    """
    if message:
        return _InternalError(message)
    elif ctx.get("app_stack"):
        return ctx.app_stack[-1].internalerror()
    else:
        return _InternalError()


internalerror = InternalError


def header(hdr, value, unique=False):
    """
    Adds the header `hdr: value` with the response.

    If `unique` is True and a header with that name already exists,
    it doesn't add a new one.

    Args:
        hdr (str): The header name.
        value (str): The header value.
        unique (bool): Whether to only add the header if it doesn't exist yet.

    Raises:
        ValueError: If the header or value contains invalid characters.

    Examples:
        >>> header("Content-Type", "text/html")
        >>> print(ctx.headers[-1])
        ('Content-Type', 'text/html')
    """
    hdr, value = safestr(hdr), safestr(value)
    # protection against HTTP response splitting attack
    if "\n" in hdr or "\r" in hdr or "\n" in value or "\r" in value:
        raise ValueError("invalid characters in header")
    if unique is True:
        for h, v in ctx.headers:
            if h.lower() == hdr.lower():
                return

    ctx.headers.append((hdr, value))


def rawinput(method=None):
    """
    Returns storage object with GET or POST arguments.

    Args:
        method (str): The HTTP method to get input for ("both", "get", "post", "put", "patch").

    Returns:
        storage: A storage object containing the request parameters.

    Examples:
        >>> # Get all input
        >>> input_data = rawinput()
        >>> # Get only POST data
        >>> post_data = rawinput("post")
    """
    method = method or "both"

    def dictify(fs):
        return {k: fs[k] for k in fs}

    env = ctx.env.copy()
    post_req = get_req = {}

    if method.lower() in ["both", "post", "put", "patch"]:
        if env["REQUEST_METHOD"] in ["POST", "PUT", "PATCH"]:
            if env.get("CONTENT_TYPE", "").lower().startswith("multipart/"):
                # since wsgi.input is directly passed to multipart,
                # it can not be called multiple times. Saving the result
                # object in ctx to allow calling web.input multiple times.
                post_req = ctx.get(
                    "_fieldstorage"
                )  # TODO: Rename? is this visible anywhere else?
                if not post_req:
                    try:
                        # This returns two dicts, forms & files.
                        forms, files = multipart.parse_form_data(environ=env)
                        post_req = dictadd(forms, files)
                        ctx._fieldstorage = post_req
                    except IndexError:
                        post_req = {}

            else:
                post_data = data().decode("utf-8")
                post_req = parse_qs(post_data, keep_blank_values=True)
            post_req = dictify(post_req)

    if method.lower() in ["both", "get"]:
        env["REQUEST_METHOD"] = "GET"
        get_req = dict(
            urllib.parse.parse_qs(env.get("QUERY_STRING", ""), keep_blank_values=True)
        )

    def process_values(values):
        if isinstance(values, list):
            return [process_values(x) for x in values]
        elif hasattr(values, "filename") and values.filename is None:
            return values.value
        else:
            return values

    return storage(
        [(k, process_values(v)) for k, v in dictadd(get_req, post_req).items()]
    )


def input(*requireds, **defaults):
    """
    Returns a `storage` object with the GET and POST arguments.

    See `storify` for how `requireds` and `defaults` work.

    Args:
        *requireds: Required parameter names.
        **defaults: Default values for parameters.

    Returns:
        storage: A storage object containing the request parameters.

    Examples:
        >>> # Get all input
        >>> input_data = input()
        >>> # Get input with defaults
        >>> input_with_defaults = input(_method="post", name="default_name")
    """
    _method = defaults.pop("_method", "both")
    out = rawinput(_method)
    try:
        defaults.setdefault("_unicode", True)  # force unicode conversion by default.
        return storify(out, *requireds, **defaults)
    except KeyError:
        raise badrequest()


def data():
    """
    Returns the data sent with the request.

    Returns:
        bytes: The raw request body data.

    Examples:
        >>> request_data = data()
        >>> print(type(request_data))
        <class 'bytes'>
    """
    if "data" not in ctx:
        if ctx.env.get("HTTP_TRANSFER_ENCODING") == "chunked":
            ctx.data = ctx.env["wsgi.input"].read()
        else:
            cl = intget(ctx.env.get("CONTENT_LENGTH"), 0)
            ctx.data = ctx.env["wsgi.input"].read(cl)
    return ctx.data


def setcookie(
    name,
    value,
    expires="",
    domain=None,
    secure=False,
    httponly=False,
    path=None,
    samesite=None,
):
    """
    Sets a cookie.

    Args:
        name (str): The cookie name.
        value (str): The cookie value.
        expires (str or int): Expiration date for the cookie.
        domain (str): Domain for which the cookie is valid.
        secure (bool): Whether the cookie should only be sent over HTTPS.
        httponly (bool): Whether the cookie should be HTTP-only.
        path (str): Path for which the cookie is valid.
        samesite (str): SameSite attribute value ("strict", "lax", or "none").

    Examples:
        >>> setcookie("session_id", "abc123")
        >>> print(ctx.headers[-1])
        ('Set-Cookie', 'session_id=abc123; Path=/')
    """
    morsel = Morsel()
    name, value = safestr(name), safestr(value)
    morsel.set(name, value, quote(value))
    if isinstance(expires, int) and expires < 0:
        expires = -1000000000
    morsel["expires"] = expires
    morsel["path"] = path or ctx.homepath + "/"
    if domain:
        morsel["domain"] = domain
    if secure:
        morsel["secure"] = secure
    if httponly:
        morsel["httponly"] = True
    value = morsel.OutputString()
    if samesite and samesite.lower() in ("strict", "lax", "none"):
        value += "; SameSite=%s" % samesite
    header("Set-Cookie", value)


def parse_cookies(http_cookie):
    """
    Parse a HTTP_COOKIE header and return dict of cookie names and decoded values.

    Args:
        http_cookie (str): The HTTP_COOKIE header string.

    Returns:
        dict: A dictionary mapping cookie names to their decoded values.

    Examples:
        >>> sorted(parse_cookies('').items())
        []
        >>> sorted(parse_cookies('a=1').items())
        [('a', '1')]
        >>> sorted(parse_cookies('a=1%202').items())
        [('a', '1 2')]
        >>> sorted(parse_cookies('a=Z%C3%A9Z').items())
        [('a', 'Z\xc3\xa9Z')]
        >>> sorted(parse_cookies('a=1; b=2; c=3').items())
        [('a', '1'), ('b', '2'), ('c', '3')]
    """
    # print "parse_cookies"
    if '"' in http_cookie:
        # HTTP_COOKIE has quotes in it, use slow but correct cookie parsing
        cookie = SimpleCookie()
        try:
            cookie.load(http_cookie)
        except CookieError:
            # If HTTP_COOKIE header is malformed, try at least to load the cookies we can by
            # first splitting on ';' and loading each attr=value pair separately
            cookie = SimpleCookie()
            for attr_value in http_cookie.split(";"):
                try:
                    cookie.load(attr_value)
                except CookieError:
                    pass
        cookies = {k: unquote(v.value) for k, v in cookie.items()}
    else:
        # HTTP_COOKIE doesn't have quotes, use fast cookie parsing
        cookies = {}
        for key_value in http_cookie.split(";"):
            key_value = key_value.split("=", 1)
            if len(key_value) == 2:
                key, value = key_value
                cookies[key.strip()] = unquote(value.strip())
    return cookies


def cookies(*requireds, **defaults):
    """
    Returns a `storage` object with all the request cookies in it.

    See `storify` for how `requireds` and `defaults` work.

    This is forgiving on bad HTTP_COOKIE input, it tries to parse at least
    the cookies it can.

    The values are converted to unicode if _unicode=True is passed.

    Args:
        *requireds: Required cookie names.
        **defaults: Default values for cookies.

    Returns:
        storage: A storage object containing the request cookies.

    Examples:
        >>> # Get all cookies
        >>> all_cookies = cookies()
        >>> # Get specific cookies with defaults
        >>> specific_cookies = cookies("session_id", user="guest")
    """
    # parse cookie string and cache the result for next time.
    if "_parsed_cookies" not in ctx:
        http_cookie = ctx.env.get("HTTP_COOKIE", "")
        ctx._parsed_cookies = parse_cookies(http_cookie)

    try:
        return storify(ctx._parsed_cookies, *requireds, **defaults)
    except KeyError:
        badrequest()
        raise StopIteration()


def debug(*args):
    """
    Prints a prettyprinted version of `args` to stderr.

    Args:
        *args: Arguments to print.

    Examples:
        >>> debug("Hello", {"key": "value"})
    """
    try:
        out = ctx.environ["wsgi.errors"]
    except:
        out = sys.stderr
    for arg in args:
        print(pprint.pformat(arg), file=out)
    return ""


def _debugwrite(x):
    """
    Writes to the debug output stream.

    Args:
        x (str): The string to write.
    """
    try:
        out = ctx.environ["wsgi.errors"]
    except:
        out = sys.stderr
    out.write(x)


debug.write = _debugwrite

ctx = context = threadeddict()

ctx.__doc__ = """
A `storage` object containing various information about the request:

environ (aka env)
   : A dictionary containing the standard WSGI environment variables.

host
   : The domain (`Host` header) requested by the user.

home
   : The base path for the application.

ip
   : The IP address of the requester.

method
   : The HTTP method used.

path
   : The path request.

query
   : If there are no query arguments, the empty string. Otherwise, a `?` followed
     by the query string.

fullpath
   : The full path requested, including query arguments (`== path + query`).

### Response Data

status (default: "200 OK")
   : The status code to be used in the response.

headers
   : A list of 2-tuples to be used in the response.

output
   : A string to be used as the response.

Examples:
    >>> print(ctx.method)
    'GET'
    >>> print(ctx.path)
    '/'
"""

if __name__ == "__main__":
    import doctest

    doctest.testmod()
