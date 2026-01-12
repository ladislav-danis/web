"""Test utilities for web.py.

This module provides utilities for testing web.py applications and components.
It includes functions for loading modules, creating test suites from doctests,
and running tests.

Examples:
    >>> import web.test
    >>> suite = web.test.doctest_suite(['web.utils'])
    >>> runner = unittest.TextTestRunner()
    >>> result = runner.run(suite)
    >>> result.wasSuccessful()
    True

Attributes:
    TestCase: Alias for unittest.TestCase.
    TestSuite: Alias for unittest.TestSuite.
"""

import doctest
import sys
import unittest

TestCase = unittest.TestCase
TestSuite = unittest.TestSuite


def load_modules(names):
    """Load multiple modules by name.

    Args:
        names (list[str]): List of module names to import.

    Returns:
        list: List of imported module objects.

    Examples:
        >>> modules = load_modules(['web.utils', 'web.db'])
        >>> len(modules)
        2
    """
    return [__import__(name, None, None, "x") for name in names]


def module_suite(module, classnames=None):
    """Makes a test suite from a module.

    Args:
        module: The module to create a test suite from.
        classnames (list[str], optional): List of class names to include.
            If None, uses the module's suite() method or loads all tests.

    Returns:
        unittest.TestSuite: A test suite containing tests from the module.

    Examples:
        >>> import web.test
        >>> import web.utils
        >>> suite = web.test.module_suite(web.utils)
        >>> isinstance(suite, unittest.TestSuite)
        True
    """
    if classnames:
        return unittest.TestLoader().loadTestsFromNames(classnames, module)
    elif hasattr(module, "suite"):
        return module.suite()
    else:
        return unittest.TestLoader().loadTestsFromModule(module)


def doctest_suite(module_names):
    """Makes a test suite from doctests.

    Args:
        module_names (list[str]): List of module names to extract doctests from.

    Returns:
        unittest.TestSuite: A test suite containing all doctests from the modules.

    Examples:
        >>> import web.test
        >>> suite = web.test.doctest_suite(['web.utils'])
        >>> isinstance(suite, unittest.TestSuite)
        True
    """
    suite = TestSuite()
    for mod in load_modules(module_names):
        suite.addTest(doctest.DocTestSuite(mod))
    return suite


def suite(module_names):
    """Creates a test suite from multiple modules.

    Args:
        module_names (list[str]): List of module names to include in the suite.

    Returns:
        unittest.TestSuite: A combined test suite from all specified modules.

    Examples:
        >>> import web.test
        >>> suite = web.test.suite(['web.utils'])
        >>> isinstance(suite, unittest.TestSuite)
        True
    """
    suite = TestSuite()
    for mod in load_modules(module_names):
        suite.addTest(module_suite(mod))
    return suite


def runTests(suite):
    """Run a test suite and return the results.

    Args:
        suite (unittest.TestSuite): The test suite to run.

    Returns:
        unittest.TextTestResult: The result of running the tests.

    Examples:
        >>> import web.test
        >>> import web.utils
        >>> suite = web.test.module_suite(web.utils)
        >>> result = web.test.runTests(suite)
        >>> isinstance(result, unittest.TextTestResult)
        True
    """
    runner = unittest.TextTestRunner()
    return runner.run(suite)


def main(suite=None):
    """Run tests from the command line.

    Args:
        suite (unittest.TestSuite, optional): The test suite to run.
            If None, loads tests from the __main__ module.

    Examples:
        >>> import web.test
        >>> # This would normally be called from command line
        >>> # web.test.main()
        >>> pass  # Doctest can't actually run this without sys.argv manipulation
    """
    if not suite:
        main_module = __import__("__main__")
        # allow command line switches
        args = [a for a in sys.argv[1:] if not a.startswith("-")]
        suite = module_suite(main_module, args or None)

    result = runTests(suite)
    sys.exit(not result.wasSuccessful())
