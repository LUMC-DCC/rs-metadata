"""Loading of the declarative crosswalk mappings.

A mapping file answers two questions per CodeMeta property: which part of the
source format corresponds to it, and how strictly the two should be expected
to agree. Keeping that as data rather than as code means a new rule is a
reviewable diff in a YAML file, and means the report can state exactly which
crosswalk produced a finding and whether that crosswalk came from CodeMeta
upstream or from rs-metadata.

The mapping never decides *whether* two values are equivalent. That is the
normalization layer's job, and it is shared across all formats.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from functools import cache
from importlib import resources
from typing import Any

import yaml

from .diagnostics import Severity
from .report import MappingRef


class Rule(StrEnum):
    """How strictly a concept is expected to agree across two files.

    A :class:`~enum.StrEnum` rather than a validated string, matching
    :class:`~rs_metadata.diagnostics.Severity`:
    ``Rule(value)`` rejects an unknown rule on its own, and a typo in a mapping
    file fails at load time rather than silently comparing as something else.

    Examples
    --------
    >>> Rule("subset")
    <Rule.SUBSET: 'subset'>
    >>> Rule.EQUAL == "equal"
    True

    An unknown rule is rejected without any extra validation code:

    >>> Rule("nearly")
    Traceback (most recent call last):
        ...
    ValueError: 'nearly' is not a valid Rule
    """

    EQUAL = "equal"
    SUBSET = "subset"
    OVERLAP = "overlap"
    INFORMATIONAL = "informational"

    @property
    def label(self) -> str:
        """How this rule reads in a report or a crosswalk table.

        Examples
        --------
        >>> Rule.SUBSET.label
        'source ⊆ anchor'
        """
        return {
            Rule.EQUAL: "must be equal",
            Rule.SUBSET: "source ⊆ anchor",
            Rule.OVERLAP: "must overlap",
            Rule.INFORMATIONAL: "reported only",
        }[self]


class Origin(StrEnum):
    """Where a crosswalk came from.

    A finding carries this so a reader can tell a mapping CodeMeta publishes
    from one this project decided on.
    """

    UPSTREAM = "codemeta-upstream"
    RS_METADATA = "rs-metadata"
    MIXED = "mixed"

    @property
    def label(self) -> str:
        """How this origin reads in a crosswalk table.

        Examples
        --------
        >>> Origin.UPSTREAM.label
        'CodeMeta upstream crosswalk'
        """
        return {
            Origin.UPSTREAM: "CodeMeta upstream crosswalk",
            Origin.RS_METADATA: "defined by rs-metadata",
            Origin.MIXED: "upstream crosswalk, extended by rs-metadata",
        }[self]


_MAPPINGS_PACKAGE = "rs_metadata.mappings"


@dataclass(frozen=True)
class FieldRule:
    """The comparison policy for one CodeMeta concept in one source format."""

    property: str
    source: str
    strategy: str = "text"
    rule: Rule = Rule.EQUAL
    severity: Severity = Severity.ERROR
    comparable: bool = True
    reason: str | None = None
    note: str | None = None
    #: Anchor concepts this source property is compared against. Usually just
    #: ``property``, but ecosystems draw role boundaries differently: npm's
    #: `author` may legitimately appear as a CodeMeta `maintainer`.
    anchor_properties: tuple[str, ...] = ()

    def anchors(self) -> tuple[str, ...]:
        """Which anchor concepts this source property is compared against.

        Returns
        -------
        tuple of str
            The declared anchor properties, or just :attr:`property`.

        Examples
        --------
        By default a concept is compared against itself:

        >>> FieldRule(property="version", source="version").anchors()
        ('version',)

        Ecosystems that draw a role boundary differently declare both sides,
        so an npm ``author`` can legitimately be a CodeMeta ``maintainer``:

        >>> FieldRule(property="author", source="author",
        ...           anchor_properties=("author", "maintainer")).anchors()
        ('author', 'maintainer')
        """
        return self.anchor_properties or (self.property,)


@dataclass(frozen=True)
class Mapping:
    """One crosswalk between a source format and CodeMeta."""

    id: str
    format: str
    format_version: str | None
    reference: MappingRef
    fields: dict[str, FieldRule]
    notes: str | None = None

    def rule_for(self, concept: str) -> FieldRule | None:
        return self.fields.get(concept)


def _parse_field(entry: dict[str, Any]) -> FieldRule:
    severity = entry.get("severity", "error")
    return FieldRule(
        property=entry["property"],
        source=entry.get("source", ""),
        strategy=entry.get("strategy", "text"),
        rule=Rule(entry.get("rule", "equal")),
        severity=Severity(severity),
        comparable=bool(entry.get("comparable", True)),
        reason=entry.get("reason"),
        note=entry.get("note"),
        anchor_properties=tuple(entry.get("anchorProperties", ())),
    )


def _parse(document: dict[str, Any]) -> Mapping:
    provenance = document.get("provenance", {})
    reference = MappingRef(
        id=document["id"],
        origin=Origin(provenance.get("origin", "rs-metadata")),
        version=document.get("formatVersion"),
        source=provenance.get("source"),
        retrieved=provenance.get("retrieved"),
    )
    fields = {}
    for entry in document.get("fields", []):
        rule = _parse_field(entry)
        if rule.property in fields:
            raise ValueError(
                f"Mapping {document['id']!r} defines property {rule.property!r} twice."
            )
        fields[rule.property] = rule
    return Mapping(
        id=document["id"],
        format=document["format"],
        format_version=document.get("formatVersion"),
        reference=reference,
        fields=fields,
        notes=provenance.get("notes"),
    )


@cache
def load(name: str) -> Mapping:
    """Load a crosswalk mapping by file stem.

    Parameters
    ----------
    name : str
        Mapping file stem, for example ``cff-1.2.0``.

    Returns
    -------
    Mapping
        The parsed crosswalk. Cached, since mappings are immutable.

    Raises
    ------
    ValueError
        If the mapping declares a property twice, or uses an unknown rule.

    Examples
    --------
    >>> mapping = load("cff-1.2.0")
    >>> mapping.format, mapping.format_version
    ('Citation File Format', '1.2.0')

    Provenance travels with the mapping onto every finding it produces:

    >>> mapping.reference.origin
    <Origin.UPSTREAM: 'codemeta-upstream'>

    Rules are addressed by CodeMeta concept:

    >>> rule = mapping.rule_for("version")
    >>> rule.source, rule.strategy, rule.rule.value, rule.severity.value
    ('version', 'version', 'equal', 'error')

    A concept the format has no field for simply has no rule:

    >>> mapping.rule_for("programmingLanguage") is None
    True
    """
    text = (
        resources.files(_MAPPINGS_PACKAGE)
        .joinpath(f"{name}.yaml")
        .read_text(encoding="utf-8")
    )
    return _parse(yaml.safe_load(text))


def available() -> list[str]:
    """Every mapping shipped with the package, for tests and documentation."""
    return sorted(
        entry.name.removesuffix(".yaml")
        for entry in resources.files(_MAPPINGS_PACKAGE).iterdir()
        if entry.name.endswith(".yaml")
    )
