"""Parsers for CodeMeta's own published documents.

CodeMeta ships two machine-readable artifacts: the JSON-LD context, which says
which terms exist, and a property table, which says what each term's value may
be. Between them they describe the vocabulary completely, so nothing about
CodeMeta is written by hand here.
"""

from __future__ import annotations

import csv
import io
from typing import Any

from .sources import SOURCES

#: Contexts rs-metadata recognizes, and the version each denotes. 3.0 and 3.1
#: serve byte-identical documents, so both are the current vocabulary.
CONTEXT_VERSIONS = {
    "https://w3id.org/codemeta/3.1": "3.1",
    "https://w3id.org/codemeta/3.0": "3.0",
}


def parse_type_range(text: str) -> list[str]:
    """Split CodeMeta's ``Type`` column into the types it permits.

    The column is prose-ish but highly regular — every value is either one
    type name or several joined by ``or``.

    >>> parse_type_range("CreativeWork or URL")
    ['CreativeWork', 'URL']
    >>> parse_type_range("Text")
    ['Text']
    >>> parse_type_range("Organization or Person")
    ['Organization', 'Person']
    """
    return [part.strip() for part in text.split(" or ") if part.strip()]


def build_codemeta_terms(context_document: dict[str, Any]) -> dict[str, Any]:
    """Derive the CodeMeta 3.1 term index from its JSON-LD context.

    The validator needs three things from the context: the set of defined
    terms (to flag likely typos), the prefixes it declares (to tell whether a
    ``prefix:term`` in a document can actually be expanded), and the class
    names, so ``@type`` can be checked.
    """
    context = context_document["@context"]

    prefixes: dict[str, str] = {}
    terms: dict[str, dict[str, Any]] = {}
    classes: list[str] = []

    for key, value in context.items():
        if key.startswith("@"):
            continue
        if isinstance(value, str):
            # A bare string value in a context is a prefix (or a keyword alias
            # such as ``"type": "@type"``, which we deliberately skip).
            if not value.startswith("@"):
                prefixes[key] = value
            continue
        if not isinstance(value, dict):
            continue
        entry: dict[str, Any] = {"id": value.get("@id")}
        if "@type" in value:
            entry["type"] = value["@type"]
        if "@container" in value:
            entry["container"] = value["@container"]
        # JSON-LD has no formal class/property distinction, but CodeMeta
        # follows the schema.org convention of capitalizing class names.
        if key[:1].isupper():
            classes.append(key)
        else:
            terms[key] = entry

    return {
        "codemetaVersion": "3.1",
        "context": SOURCES["codemeta"].url,
        "$comment": (
            "Accepted contexts are listed here rather than in a file of their "
            "own: 3.0 and 3.1 resolve to byte-identical documents, and nothing "
            "before 3.x is recognized, so the whole set is two URLs."
        ),
        "currentMajor": "3",
        "contexts": dict(sorted(CONTEXT_VERSIONS.items())),
        "prefixes": dict(sorted(prefixes.items())),
        "classes": sorted(classes),
        "terms": dict(sorted(terms.items())),
    }


def term_iris(context_document: dict[str, Any]) -> dict[str, str]:
    """Map each CodeMeta property to the IRI its context expands it to.

    Most CodeMeta terms are schema.org properties under their own name, but
    twelve are CodeMeta's own, and schema.org happens to define properties
    called ``maintainer`` and ``funding`` too. Those are different properties
    that share a name, so merging a range across them would be wrong. Reading
    the IRI rather than comparing names is what tells the two apart.

    Examples
    --------
    >>> context = {"@context": {
    ...     "maintainer": {"@id": "codemeta:maintainer"},
    ...     "author": {"@id": "schema:author"}}}
    >>> term_iris(context)
    {'author': 'schema:author', 'maintainer': 'codemeta:maintainer'}
    """
    return {
        key: value["@id"]
        for key, value in context_document["@context"].items()
        if not key.startswith("@")
        and not key[:1].isupper()
        and isinstance(value, dict)
        and isinstance(value.get("@id"), str)
    }


def build_codemeta_types(csv_text: str, parents: frozenset[str]) -> dict[str, Any]:
    """Derive the per-property type table from CodeMeta's property table.

    The result is what the validator uses to decide whether a bare string is
    acceptable: a property whose range includes ``Text`` may be written as a
    plain string, and one whose range does not must be a node or an absolute
    URL. Storing the range alone is deliberate — any "does this allow text?"
    flag would just be a second copy of ``"Text" in range``, free to drift.

    ``identifier`` is the only property CodeMeta types differently depending on
    where it appears (``PropertyValue or URL`` on a Thing, ``URL`` on a
    Person), so the nested-node cases go under ``byParent``.
    """
    rows = list(csv.DictReader(io.StringIO(csv_text)))
    properties: dict[str, dict[str, Any]] = {}

    for row in rows:
        name = (row.get("Property") or "").strip()
        parent = (row.get("Parent Type") or "").strip()
        type_text = (row.get("Type") or "").strip()
        if not name or not type_text:
            continue
        entry = properties.setdefault(name, {})
        description = " ".join((row.get("Description") or "").split())
        if description and parent in parents:
            entry["description"] = description
        if parent in parents:
            entry["range"] = parse_type_range(type_text)
            entry["parent"] = parent
        else:
            entry.setdefault("byParent", {})[parent.removeprefix("schema:")] = (
                parse_type_range(type_text)
            )

    # A property declared only on a nested type still needs a range, so that a
    # caller never has to special-case its absence.
    for entry in properties.values():
        if "range" not in entry:
            by_parent: dict[str, list[str]] = entry.get("byParent") or {}
            first: list[str] = next(iter(by_parent.values()), [])
            entry["range"] = list(first)

    for entry in properties.values():
        entry["source"] = "codemeta"
    return properties
