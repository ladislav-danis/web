"""Utilities for making the code run both on Python 2 and Python 3.

This module provides backward-compatible functions for dictionary iteration
that work in both Python versions.

Examples:
    >>> d = {'a': 1, 'b': 2}
    >>> list(iterkeys(d))
    ['a', 'b']
    >>> list(itervalues(d))
    [1, 2]
    >>> list(iteritems(d))
    [('a', 1), ('b', 2)]
"""

# Dictionary iteration
iterkeys = lambda d: iter(d.keys())
"""Iterator over dictionary keys.

Args:
    d (dict): The dictionary to iterate over.

Returns:
    iterator: An iterator over the dictionary's keys.
"""

itervalues = lambda d: iter(d.values())
"""Iterator over dictionary values.

Args:
    d (dict): The dictionary to iterate over.

Returns:
    iterator: An iterator over the dictionary's values.
"""

iteritems = lambda d: iter(d.items())
"""Iterator over dictionary items.

Args:
    d (dict): The dictionary to iterate over.

Returns:
    iterator: An iterator over the dictionary's items (key-value pairs).
"""
