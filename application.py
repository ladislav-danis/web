"""
Web application module.

This module provides the core web application functionality for handling HTTP requests,
routing, and processing through middleware and processors.

(from web.py)
"""

import itertools
import os
import sys
import traceback
import wsgiref.handlers
from importlib import reload
from inspect import isclass
from io import BytesIO
from urllib.parse import unquote, urlencode, urlparse

from . import browser, httpserver, utils, wsgi
from . import webapi as web
from .debugerror import debugerror
from .py3helpers import iteritems
from .utils import lstrips

__all__ = [
    "application",
    "auto_application",
    "subdir_application",
    "subdomain_application",
    "loadhook",
    "unloadhook",
    "autodelegate",
]


class application:
    """
    Application to delegate requests based on path.

    This class handles HTTP request routing and processing for web applications.
    
    Examples:
        >>> urls = ("/hello", "hello")
        >>> app = application(urls, globals())
        >>> class hello:
        ...     def GET(self): return "hello"
        >>>
        >>> app.request("/hello").data
        'hello'
    """

    # PY3DOCTEST: b'hello'

    def __init__(self, mapping=(), fvars={}, autoreload=None):
        """
        Initialize the application with URL mappings and variables.
        
        Args:
            mapping (tuple): Tuple of URL patterns and corresponding handlers.
            fvars (dict): Dictionary of global variables.
            autoreload (bool): Whether to enable auto-reloading during development.
        """
        if autoreload is None:
            autoreload = web.config.get("debug", False)
        self.init_mapping(mapping)
        self.fvars = fvars
        self.processors = []

        self.add_processor(loadhook(self._load))
        self.add_processor(unloadhook(self._unload))

        if autoreload:

            def main_module_name():
                mod = sys.modules["__main__"]
                file = getattr(
                    mod, "__file__", None
                )  # make sure this works even from python interpreter
                return file and os.path.splitext(os.path.basename(file))[0]

            def modname(fvars):
                """Find name of the module name from fvars."""
                file, name = fvars.get("__file__"), fvars.get("__name__")
                if file is None or name is None:
                    return None

                if name == "__main__":
                    # Since the __main__ module can't be reloaded, the module has
                    # to be imported using its file name.
                    name = main_module_name()
                return name

            mapping_name = utils.dictfind(fvars, mapping)
            module_name = modname(fvars)

            def reload_mapping():
                """Loadhook to reload mapping and fvars."""
                mod = __import__(module_name, None, None, [""])
                mapping = getattr(mod, mapping_name, None)
                if mapping:
                    self.fvars = mod.__dict__
                    self.init_mapping(mapping)

            self.add_processor(loadhook(Reloader()))
            if mapping_name and module_name:
                # when app is ran as part of a package, this puts the app into
                # `sys.modules` correctly, otherwise the first change to the
                # app module will not be picked up by Reloader
                reload_mapping()

                self.add_processor(loadhook(reload_mapping))

            # load __main__ module usings its filename, so that it can be reloaded.
            if main_module_name() and "__main__" in sys.argv:
                try:
                    __import__(main_module_name())
                except ImportError:
                    pass

    def _load(self):
        """
        Load the application into the context stack.
        
        This method is called when a request is being processed to set up
        the application context.
        """
        web.ctx.app_stack.append(self)

    def _unload(self):
        """
        Unload the application from the context stack.
        
        This method is called after a request has been processed to clean up
        the application context.
        """
        web.ctx.app_stack = web.ctx.app_stack[:-1]

        if web.ctx.app_stack:
            # this is a sub-application, revert ctx to earlier state.
            oldctx = web.ctx.get("_oldctx")
            if oldctx:
                web.ctx.home = oldctx.home
                web.ctx.homepath = oldctx.homepath
                web.ctx.path = oldctx.path
                web.ctx.fullpath = oldctx.fullpath

    def _cleanup(self):
        """
        Clean up thread-local state.
        
        Threads can be recycled by WSGI servers. Clearing up all thread-local 
        state to avoid interfering with subsequent requests.
        """
        utils.ThreadedDict.clear_all()

    def init_mapping(self, mapping):
        """
        Initialize URL mapping from a tuple of patterns and handlers.
        
        Args:
            mapping (tuple): Tuple of URL patterns and corresponding handlers.
        """
        self.mapping = list(utils.group(mapping, 2))

    def add_mapping(self, pattern, classname):
        """
        Add a new URL pattern and handler to the application.
        
        Args:
            pattern (str): Regular expression pattern for URL matching.
            classname (str): Handler class name or application instance.
        """
        self.mapping.append((pattern, classname))

    def add_processor(self, processor):
        """
        Adds a processor to the application.
        
        Processors are functions that wrap request handling and can modify
        the request flow. They are executed in reverse order.
        
        Args:
            processor (callable): A processor function that takes a handler 
                                  and returns a modified handler.
        
        Examples:
            >>> urls = ("/(.*)", "echo")
            >>> app = application(urls, globals())
            >>> class echo:
            ...     def GET(self, name): return name
            ...
            >>>
            >>> def hello(handler): return "hello, " +  handler()
            ...
            >>> app.add_processor(hello)
            >>> app.request("/web.py").data
            'hello, web.py'
        """
        # PY3DOCTEST: b'hello, web.py'
        self.processors.append(processor)

    def request(
        self,
        localpart="/",
        method="GET",
        data=None,
        host="0.0.0.0:8080",
        headers=None,
        https=False,
        **kw,
    ):
        """
        Makes request to this application for the specified path and method.
        Response will be a storage object with data, status and headers.
        
        Args:
            localpart (str): The URL path to request.
            method (str): HTTP method (GET, POST, etc.).
            data (dict or str): Request data.
            host (str): Host address for the request.
            headers (dict): HTTP headers to include in the request.
            https (bool): Whether to use HTTPS.
            **kw: Additional keyword arguments.
            
        Returns:
            storage: Response object with data, status and headers attributes.
            
        Examples:
            >>> urls = ("/hello", "hello")
            >>> app = application(urls, globals())
            >>> class hello:
            ...     def GET(self):
            ...         web.header('Content-Type', 'text/plain')
            ...         return "hello"
            ...
            >>> response = app.request("/hello")
            >>> response.data
            'hello'
            >>> response.status
            '200 OK'
            >>> response.headers['Content-Type']
            'text/plain'

        To use https, use https=True.

            >>> urls = ("/redirect", "redirect")
            >>> app = application(urls, globals())
            >>> class redirect:
            ...     def GET(self): raise web.seeother("/foo")
            ...
            >>> response = app.request("/redirect")
            >>> response.headers['Location']
            'http://0.0.0.0:8080/foo'
            >>> response = app.request("/redirect", https=True)
            >>> response.headers['Location']
            'https://0.0.0.0:8080/foo'

        The headers argument specifies HTTP headers as a mapping object
        such as a dict.

            >>> urls = ('/ua', 'uaprinter')
            >>> class uaprinter:
            ...     def GET(self):
            ...         return 'your user-agent is ' + web.ctx.env['HTTP_USER_AGENT']
            ...
            >>> app = application(urls, globals())
            >>> app.request('/ua', headers = {
            ...      'User-Agent': 'a small jumping bean/1.0 (compatible)'
            ... }).data
            'your user-agent is a small jumping bean/1.0 (compatible)'
        """
        # PY3DOCTEST: b'hello'
        # PY3DOCTEST: b'your user-agent is a small jumping bean/1.0 (compatible)'
        _p = urlparse(localpart)
        path = _p.path
        maybe_query = _p.query

        query = maybe_query or ""

        if "env" in kw:
            env = kw["env"]
        else:
            env = {}
        env = dict(
            env,
            HTTP_HOST=host,
            REQUEST_METHOD=method,
            PATH_INFO=path,
            QUERY_STRING=query,
            HTTPS=str(https),
        )
        headers = headers or {}

        for k, v in headers.items():
            env["HTTP_" + k.upper().replace("-", "_")] = v

        if "HTTP_CONTENT_LENGTH" in env:
            env["CONTENT_LENGTH"] = env.pop("HTTP_CONTENT_LENGTH")

        if "HTTP_CONTENT_TYPE" in env:
            env["CONTENT_TYPE"] = env.pop("HTTP_CONTENT_TYPE")

        if method not in ["HEAD", "GET"]:
            data = data or ""

            if isinstance(data, dict):
                q = urlencode(data)
            else:
                q = data

            env["wsgi.input"] = BytesIO(q.encode("utf-8"))
            # if not env.get('CONTENT_TYPE', '').lower().startswith('multipart/') and 'CONTENT_LENGTH' not in env:
            if "CONTENT_LENGTH" not in env:
                env["CONTENT_LENGTH"] = len(q)
        response = web.storage()

        def start_response(status, headers):
            response.status = status
            response.headers = dict(headers)
            response.header_items = headers

        data = self.wsgifunc()(env, start_response)
        response.data = b"".join(data)
        return response

    def browser(self):
        """
        Create a browser instance for testing.
        
        Returns:
            AppBrowser: Browser instance for simulating web requests.
        """
        return browser.AppBrowser(self)

    def handle(self):
        """
        Handle the current request by matching URL patterns and delegating to handlers.
        
        Returns:
            The result of the handler function call.
        """
        fn, args = self._match(self.mapping, web.ctx.path)
        return self._delegate(fn, self.fvars, args)

    def handle_with_processors(self):
        """
        Handle request with all registered processors applied.
        
        Returns:
            The result of the processed request handling.
        """
        def process(processors):
            try:
                if processors:
                    p, processors = processors[0], processors[1:]
                    return p(lambda: process(processors))
                else:
                    return self.handle()
            except web.HTTPError:
                raise
            except (KeyboardInterrupt, SystemExit):
                raise
            except:
                print(traceback.format_exc(), file=web.debug)
                raise self.internalerror()

        # processors must be applied in the reverse order. (??)
        return process(self.processors)

    def wsgifunc(self, *middleware):
        """
        Returns a WSGI-compatible function for this application.
        
        Args:
            *middleware: WSGI middleware to apply to the application.
            
        Returns:
            callable: A WSGI application function.
        """

        def peep(iterator):
            """Peeps into an iterator by doing an iteration
            and returns an equivalent iterator.
            """
            # wsgi requires the headers first
            # so we need to do an iteration
            # and save the result for later
            try:
                firstchunk = next(iterator)
            except StopIteration:
                firstchunk = ""

            return itertools.chain([firstchunk], iterator)

        def wsgi(env, start_resp):
            # clear threadlocal to avoid interference of previous requests
            self._cleanup()

            self.load(env)
            try:
                # allow uppercase methods only
                if web.ctx.method.upper() != web.ctx.method:
                    raise web.nomethod()

                result = self.handle_with_processors()
                if result and hasattr(result, "__next__"):
                    result = peep(result)
                else:
                    result = [result]
            except web.HTTPError as e:
                result = [e.data]

            def build_result(result):
                for r in result:
                    if isinstance(r, bytes):
                        yield r
                    else:
                        yield str(r).encode("utf-8")

            result = build_result(result)

            status, headers = web.ctx.status, web.ctx.headers
            start_resp(status, headers)

            def cleanup():
                self._cleanup()
                yield b""  # force this function to be a generator

            return itertools.chain(result, cleanup())

        for m in middleware:
            wsgi = m(wsgi)

        return wsgi

    def run(self, *middleware):
        """
        Starts handling requests. If called in a CGI or FastCGI context, it will follow
        that protocol. If called from the command line, it will start an HTTP
        server on the port named in the first command line argument, or, if there
        is no argument, on port 8080.

        `middleware` is a list of WSGI middleware which is applied to the resulting WSGI
        function.
        
        Args:
            *middleware: WSGI middleware to apply to the application.
            
        Returns:
            None: This method typically runs indefinitely until stopped.
        """
        return wsgi.runwsgi(self.wsgifunc(*middleware))

    def stop(self):
        """
        Stops the http server started by run.
        
        This method stops any HTTP server that was started by the run() method.
        """
        if httpserver.server:
            httpserver.server.stop()
            httpserver.server = None

    def cgirun(self, *middleware):
        """
        Return a CGI handler. This is mostly useful with Google App Engine.
        There you can just do:

            main = app.cgirun()
            
        Args:
            *middleware: WSGI middleware to apply to the application.
            
        Returns:
            callable: A CGI handler function.
        """
        wsgiapp = self.wsgifunc(*middleware)

        try:
            from google.appengine.ext.webapp.util import run_wsgi_app

            return run_wsgi_app(wsgiapp)
        except ImportError:
            # we're not running from within Google App Engine
            return wsgiref.handlers.CGIHandler().run(wsgiapp)

    def gaerun(self, *middleware):
        """
        Starts the program in a way that will work with Google app engine,
        no matter which version you are using (2.5 / 2.7)

        If it is 2.5, just normally start it with app.gaerun()

        If it is 2.7, make sure to change the app.yaml handler to point to the
        global variable that contains the result of app.gaerun()

        For example:

        in app.yaml (where code.py is where the main code is located)

            handlers:
            - url: /.*
              script: code.app

        Make sure that the app variable is globally accessible
            
        Args:
            *middleware: WSGI middleware to apply to the application.
            
        Returns:
            callable: A WSGI application function for Google App Engine.
        """
        wsgiapp = self.wsgifunc(*middleware)
        try:
            # check what version of python is running
            version = sys.version_info[:2]
            major = version[0]
            minor = version[1]

            if major != 2:
                raise OSError("Google App Engine only supports python 2.5 and 2.7")

            # if 2.7, return a function that can be run by gae
            if minor == 7:
                return wsgiapp
            # if 2.5, use run_wsgi_app
            elif minor == 5:
                from google.appengine.ext.webapp.util import run_wsgi_app

                return run_wsgi_app(wsgiapp)
            else:
                raise OSError("Not a supported platform, use python 2.5 or 2.7")
        except ImportError:
            return wsgiref.handlers.CGIHandler().run(wsgiapp)

    def load(self, env):
        """
        Initializes ctx using env.
        
        Args:
            env (dict): WSGI environment dictionary.
        """
        ctx = web.ctx
        ctx.clear()
        ctx.status = "200 OK"
        ctx.headers = []
        ctx.output = ""
        ctx.environ = ctx.env = env
        ctx.host = env.get("HTTP_HOST")

        if env.get("wsgi.url_scheme") in ["http", "https"]:
            ctx.protocol = env["wsgi.url_scheme"]
        elif env.get("HTTPS", "").lower() in ["on", "true", "1"]:
            ctx.protocol = "https"
        else:
            ctx.protocol = "http"
        ctx.homedomain = ctx.protocol + "://" + env.get("HTTP_HOST", "[unknown]")
        ctx.homepath = os.environ.get("REAL_SCRIPT_NAME", env.get("SCRIPT_NAME", ""))
        ctx.home = ctx.homedomain + ctx.homepath
        # @@ home is changed when the request is handled to a sub-application.
        # @@ but the real home is required for doing absolute redirects.
        ctx.realhome = ctx.home
        ctx.ip = env.get("REMOTE_ADDR")
        ctx.method = env.get("REQUEST_METHOD")
        try:
            ctx.path = bytes(env.get("PATH_INFO"), "latin1").decode("utf8")
        except UnicodeDecodeError:  # If there are Unicode characters...
            ctx.path = env.get("PATH_INFO")

        # http://trac.lighttpd.net/trac/ticket/406 requires:
        if env.get("SERVER_SOFTWARE", "").startswith(("lighttpd/", "nginx/")):
            ctx.path = lstrips(env.get("REQUEST_URI").split("?")[0], ctx.homepath)
            # Apache and CherryPy webservers unquote urls but lighttpd and nginx do not.
            # Unquote explicitly for lighttpd and nginx to make ctx.path uniform across
            # all servers.
            ctx.path = unquote(ctx.path)

        if env.get("QUERY_STRING"):
            ctx.query = "?" + env.get("QUERY_STRING", "")
        else:
            ctx.query = ""

        ctx.fullpath = ctx.path + ctx.query

        for k, v in iteritems(ctx):
            # convert all string values to unicode values and replace
            # malformed data with a suitable replacement marker.
            if isinstance(v, bytes):
                ctx[k] = v.decode("utf-8", "replace")

        # status must always be str
        ctx.status = "200 OK"

        ctx.app_stack = []

    def _delegate(self, f, fvars, args=[]):
        """
        Delegate request to appropriate handler based on the matched pattern.
        
        Args:
            f: The matched handler (class, function, or string).
            fvars (dict): Global variables dictionary.
            args (list): Arguments extracted from URL matching.
            
        Returns:
            The result of the handler call.
        """
        def handle_class(cls):
            meth = web.ctx.method
            if meth == "HEAD" and not hasattr(cls, meth):
                meth = "GET"
            if not hasattr(cls, meth):
                raise web.nomethod(cls)
            tocall = getattr(cls(), meth)
            return tocall(*args)

        if f is None:
            raise web.notfound()
        elif isinstance(f, application):
            return f.handle_with_processors()
        elif isclass(f):
            return handle_class(f)
        elif isinstance(f, str):
            if f.startswith("redirect "):
                url = f.split(" ", 1)[1]
                if web.ctx.method == "GET":
                    x = web.ctx.env.get("QUERY_STRING", "")
                    if x:
                        url += "?" + x
                raise web.redirect(url)
            elif "." in f:
                mod, cls = f.rsplit(".", 1)
                mod = __import__(mod, None, None, [""])
                cls = getattr(mod, cls)
            else:
                cls = fvars[f]
            return handle_class(cls)
        elif hasattr(f, "__call__"):
            return f()
        else:
            return web.notfound()

    def _match(self, mapping, value):
        """
        Match URL patterns against the request path.
        
        Args:
            mapping (list): List of URL pattern and handler tuples.
            value (str): The URL path to match against.
            
        Returns:
            tuple: A tuple of (handler, args) if matched, otherwise (None, None).
        """
        for pat, what in mapping:
            if isinstance(what, application):
                if value.startswith(pat):
                    f = lambda: self._delegate_sub_application(pat, what)
                    return f, None
                else:
                    continue
            elif isinstance(what, str):
                what, result = utils.re_subm(rf"^{pat}\Z", what, value)
            else:
                result = utils.re_compile(rf"^{pat}\Z").match(value)

            if result:  # it's a match
                return what, [x for x in result.groups()]
        return None, None

    def _delegate_sub_application(self, dir, app):
        """
        Delegate request to sub application rooted at the directory.
        
        Args:
            dir (str): The directory path prefix.
            app (application): The sub-application instance.
            
        Returns:
            The result of handling the sub-application request.
        """
        web.ctx._oldctx = web.storage(web.ctx)
        web.ctx.home += dir
        web.ctx.homepath += dir
        web.ctx.path = web.ctx.path[len(dir) :]
        web.ctx.fullpath = web.ctx.fullpath[len(dir) :]
        return app.handle_with_processors()

    def get_parent_app(self):
        """
        Get the parent application from the context stack.
        
        Returns:
            application: The parent application instance or None if not found.
        """
        if self in web.ctx.app_stack:
            index = web.ctx.app_stack.index(self)
            if index > 0:
                return web.ctx.app_stack[index - 1]

    def notfound(self):
        """
        Returns HTTPError with '404 not found' message.
        
        Returns:
            HTTPError: A 404 Not Found error.
        """
        parent = self.get_parent_app()
        if parent:
            return parent.notfound()
        else:
            return web._NotFound()

    def internalerror(self):
        """
        Returns HTTPError with '500 internal error' message.
        
        Returns:
            HTTPError: A 500 Internal Server Error.
        """
        parent = self.get_parent_app()
        if parent:
            return parent.internalerror()
        elif web.config.get("debug"):
            return debugerror()
        else:
            return web._InternalError()


def with_metaclass(mcls):
    """
    Create a metaclass decorator for Python 2/3 compatibility.
    
    Args:
        mcls: The metaclass to use.
        
    Returns:
        callable: A decorator function.
    """
    def decorator(cls):
        body = vars(cls).copy()
        # clean out class body
        body.pop("__dict__", None)
        body.pop("__weakref__", None)
        return mcls(cls.__name__, cls.__bases__, body)

    return decorator


class auto_application(application):
    """
    Application similar to `application` but urls are constructed
    automatically using metaclass.
    
    Examples:
        >>> app = auto_application()
        >>> class hello(app.page):
        ...     def GET(self): return "hello, world"
        ...
        >>> class foo(app.page):
        ...     path = '/foo/.*'
        ...     def GET(self): return "foo"
        >>> app.request("/hello").data
        'hello, world'
        >>> app.request('/foo/bar').data
        'foo'
    """

    # PY3DOCTEST: b'hello, world'
    # PY3DOCTEST: b'foo'

    def __init__(self):
        """
        Initialize the auto application.
        """
        application.__init__(self)

        class metapage(type):
            def __init__(klass, name, bases, attrs):
                type.__init__(klass, name, bases, attrs)
                path = attrs.get("path", "/" + name)

                # path can be specified as None to ignore that class
                # typically required to create a abstract base class.
                if path is not None:
                    self.add_mapping(path, klass)

        @with_metaclass(metapage)  # little hack needed for Py2 and Py3 compatibility
        class page:
            path = None

        self.page = page


# The application class already has the required functionality of subdir_application
subdir_application = application


class subdomain_application(application):
    """
    Application to delegate requests based on the host.
    
    Examples:
        >>> urls = ("/hello", "hello")
        >>> app = application(urls, globals())
        >>> class hello:
        ...     def GET(self): return "hello"
        >>>
        >>> mapping = (r"hello\.example\.com", app)
        >>> app2 = subdomain_application(mapping)
        >>> app2.request("/hello", host="hello.example.com").data
        'hello'
        >>> response = app2.request("/hello", host="something.example.com")
        >>> response.status
        '404 Not Found'
        >>> response.data
        'not found'
    """

    # PY3DOCTEST: b'hello'
    # PY3DOCTEST: b'not found'

    def handle(self):
        """
        Handle the current request by matching host patterns.
        
        Returns:
            The result of the handler function call.
        """
        host = web.ctx.host.split(":")[0]  # strip port
        fn, args = self._match(self.mapping, host)
        return self._delegate(fn, self.fvars, args)

    def _match(self, mapping, value):
        """
        Match host patterns against the request host.
        
        Args:
            mapping (list): List of host pattern and handler tuples.
            value (str): The host to match against.
            
        Returns:
            tuple: A tuple of (handler, args) if matched, otherwise (None, None).
        """
        for pat, what in mapping:
            if isinstance(what, str):
                what, result = utils.re_subm("^" + pat + "$", what, value)
            else:
                result = utils.re_compile("^" + pat + "$").match(value)

            if result:  # it's a match
                return what, [x for x in result.groups()]
        return None, None


def loadhook(h):
    """
    Converts a load hook into an application processor.
    
    Args:
        h (callable): The load hook function to convert.
        
    Returns:
        callable: A processor function that wraps the hook.
        
    Examples:
        >>> app = auto_application()
        >>> def f(): "something done before handling request"
        ...
        >>> app.add_processor(loadhook(f))
    """

    def processor(handler):
        h()
        return handler()

    return processor


def unloadhook(h):
    """
    Converts an unload hook into an application processor.
    
    Args:
        h (callable): The unload hook function to convert.
        
    Returns:
        callable: A processor function that wraps the hook.
        
    Examples:
        >>> app = auto_application()
        >>> def f(): "something done after handling request"
        ...
        >>> app.add_processor(unloadhook(f))
    """

    def processor(handler):
        try:
            result = handler()
        except:
            # run the hook even when handler raises some exception
            h()
            raise

        if result and hasattr(result, "__next__"):
            return wrap(result)
        else:
            h()
            return result

    def wrap(result):
        def next_hook():
            try:
                return next(result)
            except:
                # call the hook at the and of iterator
                h()
                raise

        result = iter(result)
        while True:
            try:
                yield next_hook()
            except StopIteration:
                return

    return processor


def autodelegate(prefix=""):
    """
    Returns a method that takes one argument and calls the method named prefix+arg,
    calling `notfound()` if there isn't one. Example:

        urls = ('/prefs/(.*)', 'prefs')

        class prefs:
            GET = autodelegate('GET_')
            def GET_password(self): pass
            def GET_privacy(self): pass

    `GET_password` would get called for `/prefs/password` while `GET_privacy` for
    `GET_privacy` gets called for `/prefs/privacy`.

    If a user visits `/prefs/password/change` then `GET_password(self, '/change')`
    is called.
    
    Args:
        prefix (str): The method name prefix to use for delegation.
        
    Returns:
        callable: A delegate function that handles the routing.
    """

    def internal(self, arg):
        if "/" in arg:
            first, rest = arg.split("/", 1)
            func = prefix + first
            args = ["/" + rest]
        else:
            func = prefix + arg
            args = []

        if hasattr(self, func):
            try:
                return getattr(self, func)(*args)
            except TypeError:
                raise web.notfound()
        else:
            raise web.notfound()

    return internal


class Reloader:
    """
    Checks to see if any loaded modules have changed on disk and,
    if so, reloads them.
    """

    """File suffix of compiled modules."""
    if sys.platform.startswith("java"):
        SUFFIX = "$py.class"
    else:
        SUFFIX = ".pyc"

    def __init__(self):
        """
        Initialize the reloader with an empty modification time cache.
        """
        self.mtimes = {}

    def __call__(self):
        """
        Check all loaded modules for changes and reload if necessary.
        """
        sys_modules = list(sys.modules.values())
        for mod in sys_modules:
            self.check(mod)

    def check(self, mod):
        """
        Check a specific module for modifications.
        
        Args:
            mod: The module to check.
        """
        # jython registers java packages as modules but they either
        # don't have a __file__ attribute or its value is None
        if not (mod and hasattr(mod, "__file__") and mod.__file__):
            return

        try:
            mtime = os.stat(mod.__file__).st_mtime
        except OSError:
            return
        if mod.__file__.endswith(self.__class__.SUFFIX) and os.path.exists(
            mod.__file__[:-1]
        ):
            mtime = max(os.stat(mod.__file__[:-1]).st_mtime, mtime)

        if mod not in self.mtimes:
            self.mtimes[mod] = mtime
        elif self.mtimes[mod] < mtime:
            try:
                reload(mod)
                self.mtimes[mod] = mtime
            except ImportError:
                pass


if __name__ == "__main__":
    import doctest

    doctest.testmod()
