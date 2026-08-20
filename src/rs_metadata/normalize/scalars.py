"""Reducing JSON-LD values to comparable scalars, and normalizing text.

Every other module in this package builds on these two operations: pull a
single string out of whatever shape a metadata format wrote the value in, then
reduce that string to a form where cosmetic differences have been discarded.
"""

from __future__ import annotations

import re
from typing import Any

__all__ = [
    "IDENTITY_FIRST",
    "LABEL_FIRST",
    "as_list",
    "normalize_loose_name",
    "normalize_package_name",
    "normalize_text",
    "scalarize",
]

#: Preference order when reducing a JSON-LD node to a comparable scalar for an
#: *identifier-like* property, where the IRI is what identifies the thing.
IDENTITY_FIRST = ("@id", "url", "value", "identifier", "name")

#: Preference order for a *descriptive* property, where the human-readable
#: label is what matters. Using IDENTITY_FIRST here would compare a
#: ComputerLanguage node by its homepage URL rather than by "Python".
LABEL_FIRST = ("name", "value", "@id", "url", "identifier")

_WHITESPACE = re.compile(r"\s+")


def scalarize(value: Any, prefer: tuple[str, ...] = IDENTITY_FIRST) -> str | None:
    """Reduce a value or JSON-LD node to a single comparable string.

    Parameters
    ----------
    value : Any
        A scalar, or a JSON-LD node such as a ``Person``, ``CreativeWork`` or
        ``PropertyValue``.
    prefer : tuple of str, optional
        Key preference order. Use :data:`IDENTITY_FIRST` (the default) when
        the IRI identifies the thing, :data:`LABEL_FIRST` when the label does.

    Returns
    -------
    str or None
        The chosen string, stripped, or ``None`` when the value carries
        nothing comparable.

    Examples
    --------
    Plain scalars pass through, stripped:

    >>> scalarize("  Apache-2.0  ")
    'Apache-2.0'
    >>> scalarize(2)
    '2'

    A node is reduced by the preference order, which is why the same node can
    compare as an identifier or as a label:

    >>> language = {"@type": "ComputerLanguage", "name": "Python",
    ...             "url": "https://python.org"}
    >>> scalarize(language)
    'https://python.org'
    >>> scalarize(language, LABEL_FIRST)
    'Python'

    A ``PropertyValue`` yields its value, and a license ``CreativeWork`` its
    URL:

    >>> scalarize({"@type": "PropertyValue", "propertyID": "doi",
    ...            "value": "10.5281/zenodo.1"})
    '10.5281/zenodo.1'
    >>> scalarize({"@type": "CreativeWork", "name": "Apache License 2.0",
    ...            "url": "https://spdx.org/licenses/Apache-2.0"})
    'https://spdx.org/licenses/Apache-2.0'

    Values carrying nothing comparable become ``None``, which callers treat as
    "not comparable" rather than as an empty value:

    >>> scalarize({}) is None
    True
    >>> scalarize("   ") is None
    True
    >>> scalarize(True) is None
    True
    """
    if isinstance(value, dict):
        for key in prefer:
            candidate = value.get(key)
            if isinstance(candidate, str) and candidate.strip():
                return candidate.strip()
            if isinstance(candidate, dict):
                nested = scalarize(candidate, prefer)
                if nested:
                    return nested
            if isinstance(candidate, list) and candidate:
                nested = scalarize(candidate[0], prefer)
                if nested:
                    return nested
        return None
    if isinstance(value, bool):
        # A boolean is never a metadata value here, and str(True) would
        # silently become the comparable string "True".
        return None
    if isinstance(value, (str, int, float)):
        text = str(value).strip()
        return text or None
    return None


def as_list(value: Any) -> list[Any]:
    """Lift CodeMeta's scalar-or-array cardinality into a list.

    CodeMeta permits a single value to be written either bare or as a
    one-element array; the two are identical in meaning, so everything
    downstream works on lists only.

    Parameters
    ----------
    value : Any
        A scalar, a list, or ``None``.

    Returns
    -------
    list
        The values, with ``None`` entries dropped.

    Examples
    --------
    >>> as_list("Python")
    ['Python']
    >>> as_list(["Python", "C++"])
    ['Python', 'C++']

    Absence yields an empty list rather than ``[None]``:

    >>> as_list(None)
    []
    >>> as_list([None, "Python"])
    ['Python']
    """
    if value is None:
        return []
    if isinstance(value, list):
        return [item for item in value if item is not None]
    return [value]


def normalize_text(raw: Any) -> str | None:
    """Case-fold, collapse whitespace and drop trailing sentence punctuation.

    Parameters
    ----------
    raw : Any
        Any value; non-strings are rendered with :func:`str`.

    Returns
    -------
    str or None
        The comparison key, or ``None`` if nothing remains.

    Examples
    --------
    Case, internal whitespace and a trailing full stop are all cosmetic:

    >>> normalize_text("  A  Tool.  ") == normalize_text("a tool")
    True
    >>> normalize_text("Read Alignment")
    'read alignment'

    Genuinely different text stays different:

    >>> normalize_text("genomics") == normalize_text("proteomics")
    False

    Empty and whitespace-only values are absence, not the empty string:

    >>> normalize_text("   ") is None
    True
    >>> normalize_text(None) is None
    True
    """
    if raw is None:
        return None
    text = _WHITESPACE.sub(" ", str(raw)).strip()
    text = text.strip(" .;,")
    return text.casefold() or None


def normalize_package_name(raw: Any) -> str | None:
    """Normalize a distribution name the way PEP 503 does.

    Used where the identity of a *package* matters, such as matching
    dependencies across ecosystems. For comparing a software *name* across the
    display-name/package-name divide, use :func:`normalize_loose_name`.

    Parameters
    ----------
    raw : Any
        A package name.

    Returns
    -------
    str or None
        The normalized name, or ``None`` if empty.

    Examples
    --------
    Runs of ``-``, ``_`` and ``.`` collapse to a single dash, and case is
    discarded — every Python packaging tool treats these as one package:

    >>> normalize_package_name("My_Tool") == normalize_package_name("my-tool")
    True
    >>> normalize_package_name("ruamel.yaml")
    'ruamel-yaml'

    Separators are collapsed but not removed, so distinct packages stay
    distinct:

    >>> normalize_package_name("my-tool") == normalize_package_name("mytool")
    False
    """
    if raw is None:
        return None
    return re.sub(r"[-_.]+", "-", str(raw).strip()).casefold() or None


def normalize_loose_name(raw: Any) -> str | None:
    """Compare software names across the display/package-name divide.

    ``codemeta.json`` carries the name as it should appear in a citation
    (``MyTool``) while packaging files carry a distribution name
    (``my-tool``). Treating those as a mismatch would fire on almost every
    well-maintained repository, so separators are dropped entirely here.

    Parameters
    ----------
    raw : Any
        A software name in any convention.

    Returns
    -------
    str or None
        The comparison key, or ``None`` if empty.

    Examples
    --------
    >>> normalize_loose_name("MyTool") == normalize_loose_name("my-tool")
    True
    >>> normalize_loose_name("Read_Aligner") == normalize_loose_name("read.aligner")
    True

    Different software still compares different:

    >>> normalize_loose_name("my-tool") == normalize_loose_name("my-tool-2")
    False
    """
    if raw is None:
        return None
    return re.sub(r"[-_.\s]+", "", str(raw).strip()).casefold() or None
