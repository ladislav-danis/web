"""Browser to test web applications.
(from web.py)

This module provides browser classes for testing web applications. It includes
both a generic Browser class and an AppBrowser class specifically designed
for testing web.py applications.

Examples:
    >>> from web.browser import AppBrowser
    >>> from web import application
    
    >>> app = application(...)
    >>> b = AppBrowser(app)
    >>> b.open('/')
    >>> b.follow_link(text='Login')
    
    >>> b.select_form(name='login')
    >>> b['username'] = 'joe'
    >>> b['password'] = 'secret'
    >>> b.submit()
    
    >>> assert b.path == '/'
    >>> assert 'Welcome joe' in b.get_text()
"""

import os
import webbrowser
from http.cookiejar import CookieJar
from io import BytesIO
from urllib.parse import urljoin
from urllib.request import HTTPCookieProcessor, HTTPError, HTTPHandler, Request
from urllib.request import build_opener as urllib_build_opener
from urllib.response import addinfourl

from .net import htmlunquote
from .utils import re_compile

DEBUG = False

__all__ = ["BrowserError", "Browser", "AppBrowser", "AppHandler"]


class BrowserError(Exception):
    """Exception raised for browser-related errors.

    Examples:
        >>> try:
        ...     raise BrowserError("Test error")
        ... except BrowserError as e:
        ...     str(e)
        'Test error'
    """


class Browser:
    """Browser class for testing web applications.

    This class provides methods to simulate browser actions like opening URLs,
    following links, filling forms, and submitting data.

    Attributes:
        cookiejar: CookieJar instance for managing cookies.
        form: Currently selected form object.
        url: Current URL being viewed.
        path: Current path component of the URL.
        status: HTTP status code of the last request.
        data: Response data from the last request.
        _response: Internal response object.
        _forms: Cached forms from the current document.
    """

    def __init__(self):
        """Initializes a new Browser instance."""
        self.cookiejar = CookieJar()
        self._cookie_processor = HTTPCookieProcessor(self.cookiejar)
        self.form = None

        self.url = "http://0.0.0.0:8080/"
        self.path = "/"

        self.status = None
        self.data = None
        self._response = None
        self._forms = None

    @property
    def text(self):
        """str: Returns the response data as a UTF-8 decoded string."""
        return self.data.decode("utf-8")

    def reset(self):
        """Clears all cookies and history."""
        self.cookiejar.clear()

    def build_opener(self):
        """Builds the opener using (urllib2/urllib.request).build_opener.

        Subclasses can override this function to provide custom openers.

        Returns:
            An opener object suitable for making HTTP requests.
        """
        return urllib_build_opener()

    def do_request(self, req):
        """Performs an HTTP request with the given request object.

        Args:
            req: A Request object containing the details of the request.

        Returns:
            The response object from the request.
        """
        if DEBUG:
            print("requesting", req.get_method(), req.get_full_url())

        opener = self.build_opener()
        opener.add_handler(self._cookie_processor)
        try:
            self._response = opener.open(req)
        except HTTPError as e:
            self._response = e

        self.url = self._response.geturl()
        self.path = Request(self.url).selector
        self.data = self._response.read()
        self.status = self._response.code
        self._forms = None
        self.form = None

        return self.get_response()

    def open(self, url, data=None, headers={}):
        """Opens the specified URL.

        Args:
            url (str): The URL to open.
            data: Data to send with the request.
            headers (dict): HTTP headers to include in the request.

        Returns:
            The response object from the request.
        """
        url = urljoin(self.url, url)
        req = Request(url, data, headers)

        return self.do_request(req)

    def show(self):
        """Opens the current page in a real web browser."""
        f = open("page.html", "w")
        f.write(self.data)
        f.close()

        url = "file://" + os.path.abspath("page.html")
        webbrowser.open(url)

    def get_response(self):
        """Returns a copy of the current response.

        Returns:
            A copy of the current HTTP response.
        """
        return addinfourl(
            BytesIO(self.data), self._response.info(), self._response.geturl()
        )

    def get_soup(self):
        """Returns beautiful soup of the current document.

        Returns:
            BeautifulSoup object representing the current document.
        """
        import BeautifulSoup

        return BeautifulSoup.BeautifulSoup(self.data)

    def get_text(self, e=None):
        """Returns content of e or the current document as plain text.

        Args:
            e: Element to extract text from. If None, uses entire document.

        Returns:
            str: Plain text content.
        """
        e = e or self.get_soup()
        return "".join(
            [htmlunquote(c) for c in e.recursiveChildGenerator() if isinstance(c, str)]
        )

    def _get_links(self):
        """Returns all links in the current document.

        Returns:
            list: List of link elements.
        """
        soup = self.get_soup()
        return [a for a in soup.findAll(name="a")]

    def get_links(
        self, text=None, text_regex=None, url=None, url_regex=None, predicate=None
    ):
        """Returns all links in the document.

        Args:
            text (str): Filter by link text.
            text_regex (str): Filter by regex pattern in link text.
            url (str): Filter by URL.
            url_regex (str): Filter by regex pattern in URL.
            predicate (callable): Custom filter function.

        Returns:
            list: List of matching links.
        """
        return self._filter_links(
            self._get_links(),
            text=text,
            text_regex=text_regex,
            url=url,
            url_regex=url_regex,
            predicate=predicate,
        )

    def follow_link(
        self,
        link=None,
        text=None,
        text_regex=None,
        url=None,
        url_regex=None,
        predicate=None,
    ):
        """Follows a link in the current document.

        Args:
            link: Specific link to follow.
            text (str): Text of the link to follow.
            text_regex (str): Regex pattern matching link text.
            url (str): URL of the link to follow.
            url_regex (str): Regex pattern matching link URL.
            predicate (callable): Custom filter function.

        Returns:
            The response from following the link.

        Raises:
            BrowserError: If no matching link is found.
        """
        if link is None:
            links = self._filter_links(
                self.get_links(),
                text=text,
                text_regex=text_regex,
                url=url,
                url_regex=url_regex,
                predicate=predicate,
            )
            link = links and links[0]

        if link:
            return self.open(link["href"])
        else:
            raise BrowserError("No link found")

    def find_link(
        self, text=None, text_regex=None, url=None, url_regex=None, predicate=None
    ):
        """Finds a link in the current document.

        Args:
            text (str): Text of the link to find.
            text_regex (str): Regex pattern matching link text.
            url (str): URL of the link to find.
            url_regex (str): Regex pattern matching link URL.
            predicate (callable): Custom filter function.

        Returns:
            The first matching link or None if not found.
        """
        links = self._filter_links(
            self.get_links(),
            text=text,
            text_regex=text_regex,
            url=url,
            url_regex=url_regex,
            predicate=predicate,
        )
        return links and links[0] or None

    def _filter_links(
        self,
        links,
        text=None,
        text_regex=None,
        url=None,
        url_regex=None,
        predicate=None,
    ):
        """Filters links based on criteria.

        Args:
            links (list): List of link elements to filter.
            text (str): Filter by link text.
            text_regex (str): Filter by regex pattern in link text.
            url (str): Filter by URL.
            url_regex (str): Filter by regex pattern in URL.
            predicate (callable): Custom filter function.

        Returns:
            list: Filtered list of links.
        """
        predicates = []
        if text is not None:
            predicates.append(lambda link: link.string == text)
        if text_regex is not None:
            predicates.append(
                lambda link: re_compile(text_regex).search(link.string or "")
            )
        if url is not None:
            predicates.append(lambda link: link.get("href") == url)
        if url_regex is not None:
            predicates.append(
                lambda link: re_compile(url_regex).search(link.get("href", ""))
            )
        if predicate:
            predicate.append(predicate)

        def f(link):
            for p in predicates:
                if not p(link):
                    return False
            return True

        return [link for link in links if f(link)]

    def get_forms(self):
        """Returns all forms in the current document.

        The returned form objects implement the ClientForm.HTMLForm interface.

        Returns:
            list: List of form objects.
        """
        if self._forms is None:
            import ClientForm

            self._forms = ClientForm.ParseResponse(
                self.get_response(), backwards_compat=False
            )
        return self._forms

    def select_form(self, name=None, predicate=None, index=0):
        """Selects the specified form.

        Args:
            name (str): Name of the form to select.
            predicate (callable): Custom filter function.
            index (int): Index of the form to select if multiple match.

        Returns:
            The selected form object.

        Raises:
            BrowserError: If no matching form is found.
        """
        forms = self.get_forms()

        if name is not None:
            forms = [f for f in forms if f.name == name]
        if predicate:
            forms = [f for f in forms if predicate(f)]

        if forms:
            self.form = forms[index]
            return self.form
        else:
            raise BrowserError("No form selected.")

    def submit(self, **kw):
        """Submits the currently selected form.

        Args:
            **kw: Keyword arguments to pass to the form submission.

        Returns:
            The response from submitting the form.

        Raises:
            BrowserError: If no form is currently selected.
        """
        if self.form is None:
            raise BrowserError("No form selected.")
        req = self.form.click(**kw)
        return self.do_request(req)

    def __getitem__(self, key):
        """Gets a form field value.

        Args:
            key (str): The name of the form field.

        Returns:
            The value of the form field.
        """
        return self.form[key]

    def __setitem__(self, key, value):
        """Sets a form field value.

        Args:
            key (str): The name of the form field.
            value: The value to set for the form field.
        """
        self.form[key] = value


class AppBrowser(Browser):
    """Browser interface to test web.py apps.

    This class provides a browser interface specifically designed for testing
    web.py applications by directly interfacing with the application object.

    Examples:
        >>> from web.browser import AppBrowser
        >>> from web import application
        
        >>> app = application(...)
        >>> b = AppBrowser(app)
        >>> b.open('/')
        >>> b.follow_link(text='Login')
        
        >>> b.select_form(name='login')
        >>> b['username'] = 'joe'
        >>> b['password'] = 'secret'
        >>> b.submit()
        
        >>> assert b.path == '/'
        >>> assert 'Welcome joe' in b.get_text()
    """

    def __init__(self, app):
        """Initializes an AppBrowser instance.

        Args:
            app: The web.py application to test.
        """
        Browser.__init__(self)
        self.app = app

    def build_opener(self):
        """Builds an opener for the web.py application.

        Returns:
            An opener object suitable for making requests to the web.py app.
        """
        return urllib_build_opener(AppHandler(self.app))


class AppHandler(HTTPHandler):
    """urllib2 handler to handle requests using web.py application.

    This class handles HTTP requests by routing them through a web.py
    application instance instead of making actual HTTP calls.

    Attributes:
        handler_order: Order in which this handler should be called.
        https_request: Method for handling HTTPS requests.
    """

    handler_order = 100
    https_request = HTTPHandler.do_request_

    def __init__(self, app):
        """Initializes an AppHandler instance.

        Args:
            app: The web.py application to handle requests for.
        """
        self.app = app

    def http_open(self, req):
        """Handles HTTP requests by routing them through the web.py app.

        Args:
            req: The HTTP request object.

        Returns:
            The response from the web.py application.
        """
        result = self.app.request(
            localpart=req.selector,
            method=req.get_method(),
            host=req.host,
            data=req.data,
            headers=dict(req.header_items()),
            https=(req.type == "https"),
        )
        return self._make_response(result, req.get_full_url())

    def https_open(self, req):
        """Handles HTTPS requests by routing them through the web.py app.

        Args:
            req: The HTTPS request object.

        Returns:
            The response from the web.py application.
        """
        return self.http_open(req)

    def _make_response(self, result, url):
        """Creates an HTTP response object from a web.py result.

        Args:
            result: The result from the web.py application.
            url (str): The URL of the request.

        Returns:
            An HTTP response object.
        """
        data = "\r\n".join([f"{k}: {v}" for k, v in result.header_items])

        import email

        headers = email.message_from_string(data)

        response = addinfourl(BytesIO(result.data), headers, url)
        code, msg = result.status.split(None, 1)
        response.code, response.msg = int(code), msg
        return response
