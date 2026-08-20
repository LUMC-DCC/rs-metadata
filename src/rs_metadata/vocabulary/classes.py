"""schema.org's class hierarchy.

The hierarchy is what makes subtyping possible. CodeMeta types
``citation`` as ``CreativeWork``; schema.org says a
``ScholarlyArticle`` is an ``Article`` is a ``CreativeWork``, so one
belongs there. Without this, accepting only the exact class name is a
false alarm about correct metadata.
"""

from __future__ import annotations

from functools import cache
from typing import Any, cast

from .loader import DATA_PACKAGE, load


@cache
def schema_org_classes() -> dict[str, Any]:
    """schema.org's class hierarchy, and the properties of the classes in use.

    Returns
    -------
    dict
        Class name mapped to ``ancestors``, and for classes any range names, a
        ``properties`` map from property name to its range.

    Examples
    --------
    >>> schema_org_classes()["ScholarlyArticle"]["ancestors"]
    ['Article', 'CreativeWork', 'Thing']
    """
    return cast(
        dict[str, Any], load(DATA_PACKAGE, "schema-org-classes.json")["classes"]
    )


@cache
def subclasses(name: str) -> tuple[str, ...]:
    """Every class schema.org derives from this one, directly or not.

    Parameters
    ----------
    name : str
        A class name, for example ``CreativeWork``.

    Returns
    -------
    tuple of str
        Descendant class names, sorted.

    Notes
    -----
    Used to express subtyping in the generated schema: a property typed
    ``CreativeWork`` accepts an ``@type`` from this list, so one ``jsonschema``
    pass enforces what would otherwise need the validator.

    Examples
    --------
    >>> "ScholarlyArticle" in subclasses("CreativeWork")
    True
    >>> "Person" in subclasses("CreativeWork")
    False
    >>> subclasses("ComputerLanguage")
    ()
    """
    return tuple(
        sorted(
            child
            for child, entry in schema_org_classes().items()
            if name in entry.get("ancestors", ())
        )
    )


def satisfies(declared: str, expected: str) -> bool:
    """Whether a node of class ``declared`` can stand where ``expected`` is asked for.

    Parameters
    ----------
    declared : str
        The node's own ``@type``.
    expected : str
        A class named in the property's range.

    Returns
    -------
    bool
        ``True`` when the classes are the same, or when ``declared`` is a
        subclass of ``expected``.

    Notes
    -----
    CodeMeta types ``citation`` as ``CreativeWork``. schema.org says a
    ``ScholarlyArticle`` is an ``Article`` is a ``CreativeWork``, so one
    belongs there. Comparing the names alone would reject it, which is a false
    alarm about correct metadata.

    Examples
    --------
    >>> satisfies("CreativeWork", "CreativeWork")
    True
    >>> satisfies("ScholarlyArticle", "CreativeWork")
    True
    >>> satisfies("SoftwareSourceCode", "CreativeWork")
    True

    Subtyping runs one way only, and unrelated classes stay unrelated:

    >>> satisfies("CreativeWork", "ScholarlyArticle")
    False
    >>> satisfies("Person", "Organization")
    False
    """
    if declared == expected:
        return True
    entry = schema_org_classes().get(declared)
    if entry is None:
        return False
    return expected in entry.get("ancestors", ())


#: CodeMeta range entries that are literals rather than nodes. A bare scalar
#: is a conformant value for any of these. ``URL`` is deliberately absent: it
#: is a literal too, but only an *absolute* IRI satisfies it, so it needs the
#: extra check in :mod:`rs_metadata.profile.types`.
