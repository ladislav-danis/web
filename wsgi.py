"""
WSGI Utilities
(from web.py)

This module provides utilities for running WSGI applications in various environments
including FastCGI, SCGI, and standard HTTP servers.
"""

import os
import sys

from . import httpserver
from . import webapi as web
from .net import validaddr
from .utils import intget, listget


def runfcgi(func, addr=("localhost", 8000)):
    """
    Runs a WSGI function as a FastCGI server.

    Args:
        func: WSGI application function to run.
        addr: Tuple of (host, port) for the server address. Defaults to ("localhost", 8000).

    Returns:
        The result of the FastCGI server execution.

    Examples:
        >>> def app(environ, start_response):
        ...     status = '200 OK'
        ...     headers = [('Content-type', 'text/plain')]
        ...     start_response(status, headers)
        ...     return [b'Hello World']
        >>> # runfcgi(app, ("localhost", 8000))
    """
    import flup.server.fcgi as flups

    return flups.WSGIServer(func, multiplexed=True, bindAddress=addr, debug=False).run()


def runscgi(func, addr=("localhost", 4000)):
    """
    Runs a WSGI function as an SCGI server.

    Args:
        func: WSGI application function to run.
        addr: Tuple of (host, port) for the server address. Defaults to ("localhost", 4000).

    Returns:
        The result of the SCGI server execution.

    Examples:
        >>> def app(environ, start_response):
        ...     status = '200 OK'
        ...     headers = [('Content-type', 'text/plain')]
        ...     start_response(status, headers)
        ...     return [b'Hello World']
        >>> # runscgi(app, ("localhost", 4000))
    """
    import flup.server.scgi as flups

    return flups.WSGIServer(func, bindAddress=addr, debug=False).run()


def runwsgi(func):
    """
    Runs a WSGI-compatible `func` using FCGI, SCGI, or a simple web server,
    as appropriate based on context and `sys.argv`.

    Args:
        func: WSGI application function to run.

    Returns:
        The result of the server execution based on the environment.

    Examples:
        >>> def app(environ, start_response):
        ...     status = '200 OK'
        ...     headers = [('Content-type', 'text/plain')]
        ...     start_response(status, headers)
        ...     return [b'Hello World']
        >>> # runwsgi(app)
    """

    if "SERVER_SOFTWARE" in os.environ:  # cgi
        os.environ["FCGI_FORCE_CGI"] = "Y"

    # PHP_FCGI_CHILDREN is used by lighttpd fastcgi
    if "PHP_FCGI_CHILDREN" in os.environ or "SERVER_SOFTWARE" in os.environ:
        return runfcgi(func, None)

    if "fcgi" in sys.argv or "fastcgi" in sys.argv:
        args = sys.argv[1:]
        if "fastcgi" in args:
            args.remove("fastcgi")
        elif "fcgi" in args:
            args.remove("fcgi")

        if args:
            return runfcgi(func, validaddr(args[0]))
        else:
            return runfcgi(func, None)

    if "scgi" in sys.argv:
        args = sys.argv[1:]
        args.remove("scgi")
        if args:
            return runscgi(func, validaddr(args[0]))
        else:
            return runscgi(func)

    server_addr = validaddr(listget(sys.argv, 1, ""))
    if "PORT" in os.environ:  # e.g. Heroku
        server_addr = ("0.0.0.0", intget(os.environ["PORT"]))

    return httpserver.runsimple(func, server_addr)


def _is_dev_mode():
    """
    Determines if the application is running in development mode.

    Returns:
        bool: True if running in development mode, False otherwise.

    Examples:
        >>> _is_dev_mode()
        True
    """
    # Some embedded python interpreters won't have sys.arv
    # For details, see https://github.com/webpy/webpy/issues/87
    argv = getattr(sys, "argv", [])

    # quick hack to check if the program is running in dev mode.
    if (
        "SERVER_SOFTWARE" in os.environ
        or "PHP_FCGI_CHILDREN" in os.environ
        or "fcgi" in argv
        or "fastcgi" in argv
        or "mod_wsgi" in argv
    ):
        return False
    return True


# When running the builtin-server, enable debug mode if not already set.
web.config.setdefault("debug", _is_dev_mode())
