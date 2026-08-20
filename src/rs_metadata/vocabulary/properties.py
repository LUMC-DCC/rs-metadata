"""What each property's value may be.

Merged from every declared vocabulary by
``scripts/vendor_reference_data.py``. CodeMeta is authoritative where
both it and schema.org define a property, because it narrows
schema.org for its own profile; schema.org supplies the properties
CodeMeta leaves out of its context.
"""

from __future__ import annotations

from functools import cache
from typing import Any, cast

from .loader import DATA_PACKAGE, load


@cache
def codemeta_terms() -> dict[str, Any]:
    """The CodeMeta 3.1 term index derived from its JSON-LD context."""
    return load(DATA_PACKAGE, "codemeta-3.1-terms.json")


@cache
def codemeta_types() -> dict[str, dict[str, Any]]:
    """What each CodeMeta property's value may be, derived from upstream.

    Returns
    -------
    dict
        Property name mapped to ``{"range": [...], "parent": str}``, plus
        ``byParent`` for the one property CodeMeta types differently depending
        on where it appears.

    Notes
    -----
    Derived by ``scripts/vendor_reference_data.py`` from CodeMeta's own
    property table, never transcribed by hand. CodeMeta narrows schema.org for
    its own profile — ``maintainer`` is ``Person`` here but
    Person-or-Organization upstream — so its table is the authority.

    Examples
    --------
    A range containing ``Text`` means a bare string is conformant:

    >>> codemeta_types()["developmentStatus"]["range"]
    ['Text']

    A range without it means the value must be a node or an absolute URL,
    because a bare string would expand to an unresolvable relative IRI:

    >>> codemeta_types()["license"]["range"]
    ['CreativeWork', 'URL']
    >>> "Text" in codemeta_types()["author"]["range"]
    False

    ``identifier`` is typed differently inside a ``Person``:

    >>> codemeta_types()["identifier"]["byParent"]
    {'Person': ['URL']}
    """
    table = load(DATA_PACKAGE, "codemeta-3.1-types.json")
    return cast(dict[str, dict[str, Any]], table["properties"])


#: Prefixes a document may write in front of a property name. The table is
#: keyed by bare name, so a lookup strips these first.
_PREFIXES = ("schema:", "codemeta:")


def type_entry(name: str) -> dict[str, Any] | None:
    """The type table entry for a property, however it is spelled.

    Parameters
    ----------
    name : str
        Property name as written in the document, with or without a prefix.

    Returns
    -------
    dict or None
        The entry, or ``None`` when neither vocabulary defines the property.

    Notes
    -----
    ``schema:featureList`` and ``featureList`` are the same property. CodeMeta
    leaves ``featureList`` out of its context, which is exactly why this
    profile writes it prefixed, and why looking it up by the prefixed spelling
    has to work.

    Examples
    --------
    >>> type_entry("license")["range"]
    ['CreativeWork', 'URL']

    A prefixed spelling resolves to the same entry as the bare one:

    >>> type_entry("schema:featureList") == type_entry("featureList")
    True
    >>> type_entry("schema:featureList")["range"]
    ['Text', 'URL']

    A property neither vocabulary defines has no entry:

    >>> type_entry("somethingInvented") is None
    True
    """
    table = codemeta_types()
    entry = table.get(name)
    if entry is not None:
        return entry
    for prefix in _PREFIXES:
        if name.startswith(prefix):
            return table.get(name[len(prefix) :])
    return None


LITERAL_TYPES = frozenset(
    {"Text", "Date", "Datetime", "DateTime", "Number", "Integer", "Boolean"}
)


#: Range entries that make a property agent-valued.
_AGENT_TYPES = frozenset({"Person", "Organization"})


@cache
def agent_properties() -> tuple[str, ...]:
    """Every CodeMeta property whose values are people or organizations.

    Returns
    -------
    tuple of str
        Property names, in CodeMeta's own order.

    Notes
    -----
    Derived from the type table rather than listed by hand. An earlier
    hand-written list covered four properties and silently missed six that
    CodeMeta types identically, so the list is now a consequence of the data.

    Only properties CodeMeta declares on the record itself are returned.
    ``affiliation`` is Organization-valued too, but it exists on a ``Person``
    rather than on the document, so it is reached by walking into an agent
    rather than by looking for it at the top level.

    Examples
    --------
    >>> properties = agent_properties()
    >>> len(properties)
    10
    >>> "author" in properties and "funder" in properties
    True

    The six a hand-written list had missed:

    >>> sorted(set(properties) - {"author", "maintainer", "contributor",
    ...                           "copyrightHolder"})
    ['editor', 'funder', 'producer', 'provider', 'publisher', 'sponsor']

    A nested-only property is not one of them:

    >>> "affiliation" in properties
    False
    """
    return tuple(
        name
        for name, entry in codemeta_types().items()
        if _AGENT_TYPES.intersection(entry["range"]) and entry.get("parent")
    )


def allows_text(name: str) -> bool:
    """Whether a bare scalar is a conformant value for a property.

    Parameters
    ----------
    name : str
        CodeMeta property name.

    Returns
    -------
    bool
        ``True`` when the property's range includes a literal type, and for
        properties CodeMeta does not define at all — an unknown property gets
        no type complaint on top of the unknown-property one.

    Examples
    --------
    >>> allows_text("developmentStatus"), allows_text("applicationCategory")
    (True, True)
    >>> allows_text("license"), allows_text("author")
    (False, False)

    Dates and numbers are literals, so a bare value is right for them — this
    is not only about ``Text``:

    >>> allows_text("datePublished"), allows_text("copyrightYear")
    (True, True)

    ``URL`` alone does not qualify, because an arbitrary string is not a URL:

    >>> allows_text("codeRepository")
    False

    Unknown properties are not second-guessed:

    >>> allows_text("somethingInvented")
    True
    """
    entry = type_entry(name)
    return entry is None or bool(LITERAL_TYPES.intersection(entry["range"]))
