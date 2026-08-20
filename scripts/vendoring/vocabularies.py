"""Parsers for the controlled vocabularies a few profile fields draw on.

Each of these is published by the community that governs it, so each is fetched
rather than transcribed. A term added upstream then arrives on the next
refresh instead of the next time somebody notices.
"""

from __future__ import annotations

from typing import Any

from .sources import SOURCES


def parse_repostatus(document: dict[str, Any]) -> list[str]:
    """The repostatus.org terms, from its own SKOS vocabulary.

    Each concept's ``@id`` ends in the term a record writes, so the fragment is
    the value. ``developmentStatus`` is typed ``Text``, which is why the bare
    term rather than the URL is what belongs in a document.
    """
    graph = document.get("@graph", [])
    terms = [
        node["@id"].split("#", 1)[-1]
        for node in graph
        if isinstance(node, dict)
        and node.get("@type") == "Concept"
        and "#" in node.get("@id", "")
    ]
    return sorted(terms)


def parse_biotools_tool_types(document: dict[str, Any]) -> list[str]:
    """The bio.tools tool-type vocabulary, from its published JSON Schema."""
    node = document.get("definitions", {}).get("tool", {})
    enum = node.get("properties", {}).get("toolType", {}).get("items", {}).get("enum")
    if not enum:
        raise ValueError("bio.tools schema no longer declares toolType as an enum")
    return sorted(str(value) for value in enum)


def build_vocabularies(
    repostatus: dict[str, Any], biotools: dict[str, Any]
) -> dict[str, Any]:
    """The controlled vocabularies, each fetched from its own publisher."""
    return {
        "developmentStatus": {
            "source": SOURCES["repostatus"].url,
            "description": (
                "repostatus.org vocabulary, used by CodeMeta for developmentStatus."
            ),
            "closed": True,
            "terms": parse_repostatus(repostatus),
        },
        "applicationCategory": {
            "source": SOURCES["biotools-tool-type"].url,
            "description": (
                "The bio.tools toolType vocabulary. Preferred for "
                "applicationCategory; free text is permitted when no term fits."
            ),
            "closed": False,
            "terms": parse_biotools_tool_types(biotools),
        },
    }
