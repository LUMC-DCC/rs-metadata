"""Parsers for the schema.org vocabulary dump.

schema.org publishes both halves of what typing a value needs: which class a
property belongs to and what it may range over, and how the classes relate to
each other. The second half is what lets a `ScholarlyArticle` be accepted where
a `CreativeWork` is asked for, without anyone writing that relationship down.
"""

from __future__ import annotations

from typing import Any

from .sources import SOURCES

RECORD_CLASSES = ("SoftwareSourceCode", "SoftwareApplication")


def document_parents(classes: dict[str, Any]) -> frozenset[str]:
    """Which parent types in the property table describe the record itself.

    A property declared on one of these applies to the document; one declared
    on anything else, such as ``Person`` or ``Role``, only applies inside a
    nested node and is recorded under ``byParent``.

    Derived from schema.org's hierarchy rather than listed: a record is a
    SoftwareSourceCode or a SoftwareApplication, so the classes that describe
    it are those two and everything they inherit from. The property table
    writes them with a prefix, and either prefix means the same class.
    """
    names = set(RECORD_CLASSES)
    for record_class in RECORD_CLASSES:
        names.update(classes.get(record_class, {}).get("ancestors", ()))
    return frozenset(
        f"{prefix}:{name}" for name in names for prefix in ("schema", "codemeta")
    )


def schema_org_ranges(document: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Extract every schema.org property's declared range.

    Returns
    -------
    dict
        Property name mapped to the type names it accepts.

    Notes
    -----
    Only the property-to-range mapping is kept. The full vocabulary is over a
    megabyte and describes classes, enumerations and documentation that the
    validator has no use for.
    """
    ranges: dict[str, dict[str, Any]] = {}
    for node in document.get("@graph", []):
        node_id = node.get("@id", "")
        if not node_id.startswith("schema:"):
            continue
        node_types = node.get("@type")
        node_types = node_types if isinstance(node_types, list) else [node_types]
        if "rdf:Property" not in node_types:
            continue
        declared = node.get("schema:rangeIncludes")
        if not declared:
            continue
        comment = node.get("rdfs:comment")
        if isinstance(comment, dict):
            comment = comment.get("@value")
        declared = declared if isinstance(declared, list) else [declared]
        names = sorted(
            {
                item["@id"].split(":", 1)[-1]
                for item in declared
                if isinstance(item, dict) and "@id" in item
            }
        )
        if names:
            entry: dict[str, Any] = {"range": names}
            if isinstance(comment, str) and comment.strip():
                entry["description"] = " ".join(comment.split())
            ranges[node_id.split(":", 1)[-1]] = entry
    return dict(sorted(ranges.items()))


def schema_org_classes(document: dict[str, Any], detailed: set[str]) -> dict[str, Any]:
    """Extract the class hierarchy, and the properties of the classes we use.

    Parameters
    ----------
    document : dict
        The schema.org vocabulary.
    detailed : set of str
        Classes to record properties for. Every class gets its ancestry, which
        is small; only these get the full property list.

    Returns
    -------
    dict
        Class name mapped to ``ancestors``, and for the detailed ones a
        ``properties`` map of property name to its range.

    Notes
    -----
    The ancestry is what makes subtype checking possible. CodeMeta types
    ``citation`` as ``CreativeWork``; schema.org says ``ScholarlyArticle`` is
    an ``Article`` is a ``CreativeWork``, so a ScholarlyArticle satisfies it.
    Without the hierarchy that is a false alarm, and there is no way to know
    it without asking schema.org.
    """
    parents: dict[str, list[str]] = {}
    domains: dict[str, list[str]] = {}
    ranges: dict[str, list[str]] = {}

    for node in document.get("@graph", []):
        node_id = node.get("@id", "")
        if not node_id.startswith("schema:"):
            continue
        name = node_id.split(":", 1)[-1]
        node_types = node.get("@type")
        node_types = node_types if isinstance(node_types, list) else [node_types]

        if "rdfs:Class" in node_types:
            declared = node.get("rdfs:subClassOf")
            declared = declared if isinstance(declared, list) else [declared]
            parents[name] = [
                item["@id"].split(":", 1)[-1]
                for item in declared
                if isinstance(item, dict) and item.get("@id", "").startswith("schema:")
            ]

        if "rdf:Property" in node_types:
            for key, target in (
                ("schema:domainIncludes", domains),
                ("schema:rangeIncludes", ranges),
            ):
                declared = node.get(key)
                declared = declared if isinstance(declared, list) else [declared]
                names = [
                    item["@id"].split(":", 1)[-1]
                    for item in declared
                    if isinstance(item, dict)
                ]
                if key.endswith("rangeIncludes"):
                    if names:
                        ranges[name] = sorted(set(names))
                else:
                    for owner in names:
                        target.setdefault(owner, []).append(name)

    def ancestry(name: str) -> list[str]:
        chain: list[str] = []
        stack = list(parents.get(name, ()))
        while stack:
            parent = stack.pop(0)
            if parent in chain:
                continue
            chain.append(parent)
            stack.extend(parents.get(parent, ()))
        return chain

    classes: dict[str, Any] = {}
    for name in sorted(parents):
        entry: dict[str, Any] = {"ancestors": ancestry(name)}
        if name in detailed:
            entry["properties"] = {
                prop: ranges.get(prop, [])
                for prop in sorted(set(domains.get(name, ())))
            }
        classes[name] = entry

    return {
        "$comment": (
            "schema.org's class hierarchy, and the properties of the classes "
            "any vocabulary range names. The ancestry is what lets a "
            "ScholarlyArticle satisfy a property typed CreativeWork."
        ),
        "source": SOURCES["schema-org"].url,
        "classes": classes,
    }


def merge_types(
    codemeta: dict[str, dict[str, Any]],
    schema_org: dict[str, dict[str, Any]],
    term_iris: dict[str, str],
) -> dict[str, Any]:
    """Combine both vocabularies into the table the validator reads.

    CodeMeta wins wherever both define a property, because CodeMeta narrows
    schema.org for its own profile: ``maintainer`` is a Person here and a
    Person-or-Organization upstream, and honoring the wider range would accept
    records CodeMeta itself does not.

    schema.org fills the gaps. CodeMeta leaves ``featureList`` out of its
    context on purpose, which is why this profile writes it as
    ``schema:featureList``; without this layer that property would carry no
    type at all.

    The two are matched by the IRI CodeMeta's context expands a term to, not
    by name. Twelve CodeMeta terms are CodeMeta's own, and schema.org defines
    same-named properties for some of them, so a name match there would merge
    two different properties into one.
    """
    borrowed = {
        name
        for name, iri in term_iris.items()
        if iri.startswith(("schema:", "http://schema.org/", "https://schema.org/"))
    }
    merged: dict[str, dict[str, Any]] = {}
    for name, declared in schema_org.items():
        if name in term_iris and name not in borrowed:
            continue
        merged[name] = {**declared, "source": "schema.org"}
    for name, entry in codemeta.items():
        # CodeMeta wins on type. Where it gives no description of its own, the
        # schema.org one still describes the same property.
        fallback = merged.get(name, {})
        merged[name] = {
            **(
                {"description": fallback["description"]}
                if "description" in fallback
                else {}
            ),
            **entry,
            **({"id": term_iris[name]} if name in term_iris else {}),
        }
    return {
        "codemetaVersion": "3.1",
        "sources": {
            "codemeta": SOURCES["codemeta-properties"].url,
            "schema.org": SOURCES["schema-org"].url,
        },
        "$comment": (
            "Per-property value types. CodeMeta's own property table is "
            "authoritative because it narrows schema.org; schema.org supplies "
            "the properties CodeMeta leaves out of its context. A property "
            "whose range omits a literal type must be a node or an absolute "
            "URL, because a bare string there expands to an unresolvable "
            "relative IRI."
        ),
        "properties": dict(sorted(merged.items())),
    }
