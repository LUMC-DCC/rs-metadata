#!/usr/bin/env python3
"""Generate the published JSON Schema from the profile definition.

``profile/lumc-codemeta.yaml`` names the vocabularies, the fields, and how many
values each takes. Everything else is read from the vocabularies themselves:
property types and definitions from CodeMeta and schema.org, class hierarchies
from schema.org. Nothing about a type is written by hand.

Node shapes are deliberately thin. Whether a node is the right *class* is
checked against the vocabulary by :mod:`rs_metadata.profile.types`, which knows
from schema.org's hierarchy that a ``ScholarlyArticle`` is a ``CreativeWork``.
JSON Schema cannot express subtyping, so it does not try.

Usage::

    poetry run python scripts/build_schema.py          # write
    poetry run python scripts/build_schema.py --check  # verify only
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from rs_metadata.vocabulary import (  # noqa: E402
    codemeta_terms,
    codemeta_types,
    codemeta_versions,
    subclasses,
    type_entry,
)

PROFILE_PATH = ROOT / "profile" / "lumc-codemeta.yaml"
SCHEMA_PATH = ROOT / "src" / "rs_metadata" / "schema" / "codemeta-lumc.schema.json"
SCHEMA_ID = (
    "https://lumc-dcc.github.io/rs-metadata/schema/{version}/codemeta-lumc.schema.json"
)

#: Range entries a bare scalar satisfies, and the schema that accepts them.
#: Anything else is a class, and therefore a node.
#:
#: The numeric and boolean entries accept a *constrained* string as well as the
#: native JSON value, because JSON-LD treats a quoted literal and a bare one
#: alike and generators differ on which they emit. Accepting a plain ``string``
#: would swallow every other branch: in ``Number or Text`` it would make the
#: text branch unreachable and let an empty string through.
SCALAR_SCHEMAS: dict[str, dict[str, Any]] = {
    "Text": {"$ref": "#/$defs/NonEmptyText"},
    "URL": {"$ref": "#/$defs/AbsoluteUri"},
    "Date": {"$ref": "#/$defs/IsoDate"},
    "DateTime": {"$ref": "#/$defs/IsoDate"},
    "Datetime": {"$ref": "#/$defs/IsoDate"},
    "Number": {"$ref": "#/$defs/Number"},
    "Integer": {"$ref": "#/$defs/Integer"},
    "Boolean": {"$ref": "#/$defs/Boolean"},
}

#: The only structural definitions. Each is about shape rather than vocabulary,
#: which is why none of them names a class.
BASE_DEFS: dict[str, dict[str, Any]] = {
    "NonEmptyText": {"type": "string", "minLength": 1},
    "AbsoluteUri": {
        "type": "string",
        "pattern": r"^[a-zA-Z][a-zA-Z0-9+.\-]*:.+$",
        "$comment": (
            "Shape only. Whether a URL has a host, and whether its scheme is "
            "real, is checked by rs_metadata.profile.formats."
        ),
    },
    "IsoDate": {
        "type": "string",
        "pattern": r"^\d{4}(-\d{2}(-\d{2}(T[0-9:.+Z\-]+)?)?)?$",
        "$comment": (
            "ISO 8601, optionally reduced to year or year-month. Shape only: "
            "whether the date exists is checked by rs_metadata.profile.formats, "
            "because no pattern over digits knows that February has 28 days."
        ),
        "examples": ["2026-06-01"],
    },
    "Number": {
        "$comment": "A number, or a string spelling one.",
        "anyOf": [
            {"type": "number"},
            {
                "type": "string",
                "pattern": r"^[+-]?(\d+\.?\d*|\.\d+)([eE][+-]?\d+)?$",
            },
        ],
    },
    "Integer": {
        "$comment": "A whole number, or a string spelling one.",
        "anyOf": [
            {"type": "integer"},
            {"type": "string", "pattern": r"^[+-]?\d+$"},
        ],
    },
    "Boolean": {
        "$comment": "A boolean, or a string spelling one.",
        "anyOf": [
            {"type": "boolean"},
            {"enum": ["true", "false", "True", "False"]},
        ],
    },
    "Node": {
        "title": "Node",
        "$comment": (
            "Any JSON-LD node. Used where a described property can hold a "
            "class the profile has no opinion about, which is most of "
            "schema.org. Its own type is still checked against the vocabulary "
            "by rs_metadata.profile.types."
        ),
        "type": "object",
        "minProperties": 1,
        "properties": {"@id": {"$ref": "#/$defs/AbsoluteUri"}},
    },
}

#: Classes a top-level record may declare.
SOFTWARE_TYPES = ["SoftwareSourceCode", "SoftwareApplication"]


def load_profile() -> dict[str, Any]:
    return dict(yaml.safe_load(PROFILE_PATH.read_text(encoding="utf-8")))


def document_key(field: str) -> str:
    """How a profile field is spelled inside the record.

    A term the base vocabulary's context defines is written bare; anything
    else keeps its prefix, because without one JSON-LD expands it to nothing
    and every consumer drops it silently.

    Examples
    --------
    >>> document_key("name")
    'name'
    >>> document_key("schema:featureList")
    'schema:featureList'
    """
    _, separator, bare = field.partition(":")
    if not separator:
        return field
    return bare if bare in codemeta_terms()["terms"] else field


def accepted_contexts() -> list[str]:
    """Context URLs a conformant record may declare, newest first."""
    versions = codemeta_versions()
    current = versions["currentMajor"]
    return sorted(
        (
            url
            for url, version in versions["contexts"].items()
            if version.split(".")[0] == current
        ),
        reverse=True,
    )


def humanize(name: str) -> str:
    """A readable label for a property name, used in diagnostics and editors.

    Examples
    --------
    >>> humanize("codemeta:codeRepository")
    'Code repository'
    >>> humanize("schema:featureList")
    'Feature list'
    """
    bare = name.split(":", 1)[-1]
    spaced = re.sub(r"(?<!^)(?=[A-Z])", " ", bare).lower()
    return spaced[:1].upper() + spaced[1:]


def _parents_of(entry: dict[str, Any]) -> list[str]:
    """Every type a property is declared on, however the table records it."""
    if entry.get("parent"):
        return [str(entry["parent"])]
    return list(entry.get("byParent") or ())


def recommended_for(class_name: str) -> set[str]:
    """The properties CodeMeta recommends on a class.

    CodeMeta's property table records which type each property is declared on,
    so it already says what belongs on a ``Person`` or a ``CreativeWork``.
    Taking that alongside the profile's own picks means a node describes what
    CodeMeta expects there, without anyone listing it twice.
    """
    return {
        name
        for name, entry in codemeta_types().items()
        if entry.get("source") == "codemeta"
        and class_name
        in {
            parent.split(":")[-1]
            for parent in (
                [entry["parent"]]
                if entry.get("parent")
                else list(entry.get("byParent") or ())
            )
        }
    }


def class_def(name: str, described: list[str], defined: set[str]) -> dict[str, Any]:
    """The definition for one node class, built from the vocabularies.

    Parameters
    ----------
    name : str
        The class, for example ``Person``.
    described : list of str
        Which of its properties to describe. schema.org gives a class its
        whole inherited property list, which runs to over a hundred entries;
        the profile picks the ones worth showing.

    Returns
    -------
    dict
        A schema fragment accepting the class or any of its subclasses.

    Notes
    -----
    ``@type`` is an enum of the class and everything schema.org says descends
    from it, so a ``ScholarlyArticle`` satisfies a property typed
    ``CreativeWork`` without the schema needing to understand subtyping. That
    puts the rule where a single ``jsonschema`` pass enforces it, rather than
    only in the validator.

    Properties not listed are left unconstrained rather than forbidden:
    ``additionalProperties`` is never set to false, so a record may carry
    anything else the vocabulary defines.
    """
    accepted = [name, *subclasses(name)]
    properties: dict[str, Any] = {
        "@id": {
            "title": "Identifier",
            "description": "An absolute IRI identifying this node.",
            "$ref": "#/$defs/AbsoluteUri",
        },
        "@type": {
            "title": "Node type",
            "description": f"{name}, or any class schema.org derives from it.",
            "enum": accepted,
        },
    }
    for prop in described:
        entry = type_entry(prop)
        if entry is None:
            raise ValueError(
                f"{name}.{prop} is named in the profile but defined by none of "
                f"the declared vocabularies."
            )
        described_prop: dict[str, Any] = {"title": humanize(prop)}
        if entry.get("description"):
            described_prop["description"] = " ".join(entry["description"].split())
        single = value_schema(entry["range"], defined)
        branches = single.get("anyOf", [single]) if len(single) == 1 else [single]
        properties[prop] = {
            **described_prop,
            "anyOf": [
                *branches,
                {"type": "array", "minItems": 1, "items": single},
            ],
        }

    return {
        "title": name,
        "$comment": (
            f"Generated by scripts/build_schema.py from the schema.org "
            f"vocabulary. Accepts {name} and its {len(accepted) - 1} "
            f"subclasses. Properties beyond those described here are allowed."
        ),
        "type": "object",
        "minProperties": 1,
        "properties": properties,
    }


def value_schema(range_: list[str], defined: set[str]) -> dict[str, Any]:
    """The schema accepting one value of a property with this range.

    ``anyOf`` rather than ``oneOf``: several branches can match one value, and
    demanding exactly one rejects values that are perfectly valid.

    A class the profile has not declared falls back to the generic node.
    Following every reachable class would pull in most of schema.org for no
    gain, and the class itself is still checked against the vocabulary.
    """
    branches: list[dict[str, Any]] = []
    for name in range_:
        branch = SCALAR_SCHEMAS.get(name) or {
            "$ref": f"#/$defs/{name}" if name in defined else "#/$defs/Node"
        }
        if branch not in branches:
            branches.append(branch)
    return branches[0] if len(branches) == 1 else {"anyOf": branches}


def property_schema(
    prefixed: str,
    cardinality: str,
    defined: set[str],
    help_text: str | None = None,
) -> dict[str, Any]:
    """The schema for one property, from its vocabulary plus its cardinality.

    ``help_text`` replaces the vocabulary's definition where the profile has
    something more useful to say. The description is what a diagnostic offers
    as remediation, and a definition is not always a fix.
    """
    entry = type_entry(document_key(prefixed))
    if entry is None:
        raise ValueError(
            f"{prefixed!r} is named in the profile but defined by none of the "
            f"declared vocabularies. Check the spelling and the prefix."
        )
    described: dict[str, Any] = {"title": humanize(prefixed)}
    description = help_text or entry.get("description")
    if description:
        described["description"] = " ".join(description.split())
    described["$comment"] = (
        f"Generated by scripts/build_schema.py. Type from the "
        f"{entry.get('source', 'codemeta')} vocabulary: "
        f"{' or '.join(entry['range'])}."
    )
    single = value_schema(entry["range"], defined)
    # A one-element array means the same thing as a bare value in JSON-LD, so
    # `one` constrains how many values there are, not how they are written.
    array: dict[str, Any] = {"type": "array", "minItems": 1, "items": single}
    if cardinality == "one":
        array["maxItems"] = 1
    # Flatten rather than nesting anyOf inside anyOf: the branches mean the
    # same either way, and one level reads far better in an editor tooltip.
    branches = single.get("anyOf", [single]) if len(single) == 1 else [single]
    return {**described, "anyOf": [*branches, array]}


def build(profile: dict[str, Any]) -> dict[str, Any]:
    """Assemble the whole schema from the profile and the vocabularies."""
    required: dict[str, str] = profile["required"]
    recommended: dict[str, str] = profile["recommended"]
    help_texts: dict[str, str] = profile.get("help") or {}
    contexts = accepted_contexts()
    fields = {**required, **recommended}

    properties: dict[str, Any] = {
        "@context": {
            "title": "JSON-LD context",
            "description": (
                "Must reference a CodeMeta 3.x context. The context is what "
                "gives the property names in this file a defined meaning."
            ),
            "anyOf": [
                {"enum": contexts},
                {
                    "type": "array",
                    "minItems": 1,
                    "items": {"type": ["string", "object"]},
                    "contains": {"enum": contexts},
                },
            ],
        },
        "@type": {
            "title": "Node type",
            "description": (
                "SoftwareSourceCode for software distributed as source, "
                "SoftwareApplication for software distributed only as an "
                "executable or a service."
            ),
            "anyOf": [
                {"enum": SOFTWARE_TYPES},
                {
                    "type": "array",
                    "minItems": 1,
                    "items": {"type": "string"},
                    "contains": {"enum": SOFTWARE_TYPES},
                },
            ],
        },
    }

    # Every class a profile field can hold needs a definition, and the profile
    # says which of its properties to describe. A class reachable but unlisted
    # is a gap, not something to paper over with a generic node.
    declared_types: dict[str, Any] = profile.get("types") or {}
    reachable = {
        name
        for prefixed in fields
        for name in (type_entry(document_key(prefixed)) or {}).get("range", ())
        if name not in SCALAR_SCHEMAS
    }
    missing = reachable - set(declared_types)
    if missing:
        raise ValueError(
            f"These classes can appear in a profile field but are not in the "
            f"`types:` section of {PROFILE_PATH.name}: {sorted(missing)}"
        )
    defined = set(declared_types)
    for prefixed, cardinality in fields.items():
        properties[document_key(prefixed)] = property_schema(
            prefixed, cardinality, set(declared_types), help_texts.get(prefixed)
        )

    class_defs = {
        name: class_def(
            name,
            sorted(set(entry.get("properties") or ()) | recommended_for(name)),
            defined,
        )
        for name, entry in declared_types.items()
    }

    vocabularies = profile["vocabularies"]
    codemeta = next(item for item in vocabularies if item["prefix"] == "codemeta")
    aliases = {
        document_key(name): list(spellings)
        for name, spellings in (profile.get("aliases") or {}).items()
    }

    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": SCHEMA_ID.format(version=profile["version"]),
        "title": profile["name"],
        "description": (
            f"A profile of CodeMeta {codemeta['version']}. Generated from "
            f"profile/lumc-codemeta.yaml by scripts/build_schema.py; edit that "
            f"file, not this one."
        ),
        "type": "object",
        "required": ["@context", "@type", *(document_key(n) for n in required)],
        "properties": properties,
        "x-lumc-profile": {
            "profileVersion": profile["version"],
            "codemetaVersion": codemeta["version"],
            "codemetaContext": contexts[0],
            "$comment": (
                "The field policy, read at runtime by rs_metadata.vocab. "
                "Generated from profile/lumc-codemeta.yaml."
            ),
            "vocabularies": vocabularies,
            "mandatory": [document_key(name) for name in required],
            "recommended": [document_key(name) for name in recommended],
            "singleValued": [
                document_key(name)
                for name, cardinality in fields.items()
                if cardinality == "one"
            ],
            "featureListAliases": aliases.get("schema:featureList", []),
        },
        "$defs": dict(sorted({**BASE_DEFS, **class_defs}.items())),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="fail if the schema does not match the profile, without writing",
    )
    args = parser.parse_args()

    updated = json.dumps(build(load_profile()), indent=2) + "\n"
    current = SCHEMA_PATH.read_text(encoding="utf-8") if SCHEMA_PATH.exists() else ""

    if args.check:
        if updated != current:
            print(
                f"{SCHEMA_PATH.name} does not match {PROFILE_PATH.name}.\n"
                f"Run: poetry run python scripts/build_schema.py",
                file=sys.stderr,
            )
            return 1
        print("Profile schema matches the profile definition.")
        return 0

    if updated == current:
        print("Profile schema is already up to date.")
        return 0
    SCHEMA_PATH.write_text(updated, encoding="utf-8")
    print(f"  wrote {SCHEMA_PATH.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
