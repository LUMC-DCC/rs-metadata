"""The common representation every metadata source is mapped into.

Comparison is deliberately star-shaped rather than pairwise: each adapter maps
its own format into CodeMeta concepts, and the engine compares those concepts
against ``codemeta.json``. Adding an eighth supported format therefore costs
one adapter, not seven new comparators.

A *concept* is named by its CodeMeta property (``name``, ``author``,
``license``). A :class:`ConceptValue` is one value for a concept together with
the path it came from, so a finding can always point back at the exact place
in the original file.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .locate import Path as DocPath
from .locate import SourceMap, format_path
from .report import Location
from .vocabulary import concept_order

#: Concepts extracted by more than one adapter, in a stable reporting order
#: that puts identity first, then provenance, then the technical detail.
CONCEPT_ORDER = concept_order()


def concept_sort_key(concept: str) -> tuple[int, str]:
    try:
        return (CONCEPT_ORDER.index(concept), "")
    except ValueError:
        return (len(CONCEPT_ORDER), concept)


@dataclass(frozen=True)
class ConceptValue:
    """One value of one concept, with the path it was read from."""

    raw: Any
    path: DocPath = ()

    def display_path(self) -> str:
        return format_path(self.path)


#: An adapter's output: CodeMeta property name to the values it found.
ConceptMap = dict[str, list[ConceptValue]]


@dataclass
class ParsedSource:
    """Everything one adapter learned from one file.

    Kept together so the consistency engine can resolve a value's line number
    without re-reading or re-parsing the file.
    """

    adapter_id: str
    file: str
    format: str
    format_version: str | None = None
    document: Any = None
    source_map: SourceMap = field(default_factory=SourceMap)
    concepts: ConceptMap = field(default_factory=dict)

    def locate(self, path: DocPath) -> tuple[int, int] | None:
        return self.source_map.locate(path)


def add(concepts: ConceptMap, name: str, raw: Any, path: DocPath) -> None:
    """Record one concept value, skipping empty ones.

    Parameters
    ----------
    concepts : ConceptMap
        The map being built, mutated in place.
    name : str
        CodeMeta property this value belongs to.
    raw : Any
        The value as the source file wrote it.
    path : DocPath
        Where in the source document it came from. This is what becomes the
        line number in a CI annotation, so it should be as precise as the
        format allows.

    Notes
    -----
    Empty strings and empty collections are *absence*, not disagreement: a
    ``description: ""`` in one file must never be reported as contradicting a
    real description in another.

    Examples
    --------
    >>> concepts = {}
    >>> add(concepts, "name", "MyTool", ("title",))
    >>> [(value.raw, value.path) for value in concepts["name"]]
    [('MyTool', ('title',))]

    Repeated calls accumulate, which is how a format with several sources for
    one concept is handled:

    >>> add(concepts, "name", "my-tool", ("Package",))
    >>> [value.raw for value in concepts["name"]]
    ['MyTool', 'my-tool']

    Empty values are skipped entirely rather than recorded as blanks:

    >>> concepts = {}
    >>> for empty in [None, "", "   ", [], {}]:
    ...     add(concepts, "description", empty, ("abstract",))
    >>> concepts
    {}
    """
    if raw is None:
        return
    if isinstance(raw, str) and not raw.strip():
        return
    if isinstance(raw, (list, dict)) and not raw:
        return
    concepts.setdefault(name, []).append(ConceptValue(raw=raw, path=path))


def add_each(concepts: ConceptMap, name: str, values: Any, path: DocPath) -> None:
    """Record a property that may be written either bare or as an array.

    Parameters
    ----------
    concepts : ConceptMap
        The map being built, mutated in place.
    name : str
        CodeMeta property these values belong to.
    values : Any
        A single value or a list of them.
    path : DocPath
        Path of the property itself. List entries have their index appended,
        so each value keeps its own position in the file.

    Examples
    --------
    A list yields one value per entry, each with its own indexed path:

    >>> concepts = {}
    >>> add_each(concepts, "keywords", ["genomics", "alignment"], ("keywords",))
    >>> [(v.raw, v.path) for v in concepts["keywords"]]
    [('genomics', ('keywords', 0)), ('alignment', ('keywords', 1))]

    A bare value is equivalent to a one-element list, per CodeMeta's
    cardinality rule, and keeps the unindexed path:

    >>> concepts = {}
    >>> add_each(concepts, "keywords", "genomics", ("keywords",))
    >>> [(v.raw, v.path) for v in concepts["keywords"]]
    [('genomics', ('keywords',))]
    """
    if values is None:
        return
    if isinstance(values, list):
        for index, item in enumerate(values):
            add(concepts, name, item, (*path, index))
    else:
        add(concepts, name, values, path)


def location(parsed: ParsedSource, path: DocPath = (), value: Any = None) -> Location:
    """Build a report :class:`Location` for a path inside a parsed source."""
    position = parsed.locate(path)
    return Location(
        file=parsed.file,
        path=format_path(path) or None,
        line=position[0] if position else None,
        column=position[1] if position else None,
        value=value,
    )


def dig(document: Any, *keys: Any) -> Any:
    """Follow a path into nested mappings and sequences, or return ``None``.

    Parameters
    ----------
    document : Any
        The structure to descend into.
    *keys : str or int
        Mapping keys and sequence indices, applied in order.

    Returns
    -------
    Any
        The value at that path, or ``None`` if any step is missing. Never
        raises, so adapters can probe optional structures without guarding
        each level.

    Examples
    --------
    >>> document = {"tool": {"poetry": {"name": "my-tool"}}}
    >>> dig(document, "tool", "poetry", "name")
    'my-tool'

    A missing step yields ``None`` rather than raising:

    >>> dig(document, "tool", "hatch", "name") is None
    True

    Sequences are indexed, including from the end:

    >>> dig({"authors": [{"name": "Jane"}, {"name": "John"}]}, "authors", 1, "name")
    'John'
    >>> dig({"authors": [{"name": "Jane"}]}, "authors", 5) is None
    True

    Descending into a scalar stops rather than raising:

    >>> dig({"name": "MyTool"}, "name", "first") is None
    True
    """
    current = document
    for key in keys:
        if isinstance(current, dict):
            current = current.get(key)
        elif isinstance(current, list) and isinstance(key, int):
            if not -len(current) <= key < len(current):
                return None
            current = current[key]
        else:
            return None
        if current is None:
            return None
    return current
