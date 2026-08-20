"""The comparison engine: applying a mapping's rules to two sets of concepts.

One engine serves every format. It knows nothing about CFF, TOML or npm — only
about concepts, the rule a mapping attached to each, and the strategy that
decides equivalence. That is what keeps the number of comparators linear in the
number of supported formats.
"""

from __future__ import annotations

from ..concepts import ConceptMap, ConceptValue, ParsedSource, concept_sort_key
from ..diagnostics import Severity
from ..mapping import FieldRule, Mapping
from ..normalize import ComparisonResult, get_strategy
from ..report import Diagnostic
from .messages import (
    informational,
    mismatch,
    mismatch_message,
    mismatch_suggestion,
    missing_from_anchor,
    render_values,
    uncomparable,
)

__all__ = ["apply_rule", "compare", "rule_violated"]


def compare(
    anchor: ParsedSource,
    anchor_concepts: ConceptMap,
    source: ParsedSource,
    source_concepts: ConceptMap,
    mapping: Mapping,
) -> tuple[list[Diagnostic], int]:
    """Compare one metadata source against the anchor record.

    Parameters
    ----------
    anchor : ParsedSource
        The parsed ``codemeta.json``.
    anchor_concepts : ConceptMap
        Concepts extracted from the anchor.
    source : ParsedSource
        The parsed companion file.
    source_concepts : ConceptMap
        Concepts extracted from the companion.
    mapping : Mapping
        The crosswalk relating the companion's format to CodeMeta.

    Returns
    -------
    tuple
        ``(diagnostics, checks)`` — the findings, and how many comparisons
        were actually evaluated. The count feeds the report's summary, so a
        reader can tell a thorough run from a shallow one.

    Notes
    -----
    A concept the source does not record at all is skipped **silently**.
    ``CITATION.cff`` has no field for a programming language and never will;
    saying so on every run would be noise. Only concepts the source actually
    carries are checked.

    Concepts are visited in a fixed field order, so two runs of
    the same repository produce diagnostics in the same order.
    """
    diagnostics: list[Diagnostic] = []
    checks = 0

    for concept in sorted(mapping.fields, key=concept_sort_key):
        rule = mapping.fields[concept]
        source_values = source_concepts.get(concept, [])
        anchor_values = [
            value for name in rule.anchors() for value in anchor_concepts.get(name, [])
        ]

        if not source_values:
            continue

        if not rule.comparable:
            diagnostics.append(
                uncomparable(anchor, source, mapping, rule, source_values, rule.reason)
            )
            continue

        checks += 1

        if not anchor_values:
            diagnostics.append(
                missing_from_anchor(anchor, source, mapping, rule, source_values)
            )
            continue

        strategy = get_strategy(rule.strategy)
        result = strategy.compare(
            [value.raw for value in anchor_values],
            [value.raw for value in source_values],
        )

        if not result.comparable:
            diagnostics.append(
                uncomparable(
                    anchor,
                    source,
                    mapping,
                    rule,
                    source_values,
                    "Neither file expresses this property in a form the "
                    f"{rule.strategy} comparison can interpret.",
                )
            )
            continue

        diagnostics.extend(
            apply_rule(
                anchor, anchor_values, source, source_values, mapping, rule, result
            )
        )

    return diagnostics, checks


def rule_violated(rule: str, result: ComparisonResult) -> bool:
    """Decide whether a comparison outcome violates a mapping rule.

    Parameters
    ----------
    rule : {"equal", "subset", "overlap", "informational"}
        The rule the mapping attached to this concept.
    result : ComparisonResult
        The comparison outcome.

    Returns
    -------
    bool
        Whether to report a mismatch.

    Notes
    -----
    ``subset`` is asymmetric by design: the anchor is allowed to be richer
    than a companion, but a companion may not claim something the anchor does
    not. That is what lets ``codemeta.json`` carry extra identifiers without
    every companion having to repeat them.

    Examples
    --------
    >>> agree = ComparisonResult(shared=1)
    >>> all(not rule_violated(rule, agree)
    ...     for rule in ["equal", "subset", "overlap", "informational"])
    True

    Equality is violated by a difference on either side:

    >>> rule_violated("equal", ComparisonResult(only_in_anchor=["1.2"]))
    True
    >>> rule_violated("equal", ComparisonResult(only_in_source=["1.1"]))
    True

    Subset tolerates a richer anchor but not a richer source:

    >>> rule_violated("subset", ComparisonResult(shared=1, only_in_anchor=["extra"]))
    False
    >>> rule_violated("subset", ComparisonResult(shared=1, only_in_source=["extra"]))
    True

    Overlap only fires when the two share nothing at all:

    >>> rule_violated("overlap", ComparisonResult(shared=1, only_in_source=["x"]))
    False
    >>> rule_violated("overlap", ComparisonResult(only_in_anchor=["a"],
    ...                                           only_in_source=["b"]))
    True

    An informational rule is never violated:

    >>> rule_violated("informational", ComparisonResult(only_in_source=["x"]))
    False
    """
    return {
        "equal": bool(result.only_in_anchor or result.only_in_source),
        "subset": bool(result.only_in_source),
        "overlap": result.shared == 0,
        "informational": False,
    }[rule]


def apply_rule(
    anchor: ParsedSource,
    anchor_values: list[ConceptValue],
    source: ParsedSource,
    source_values: list[ConceptValue],
    mapping: Mapping,
    rule: FieldRule,
    result: ComparisonResult,
) -> list[Diagnostic]:
    """Turn one comparison outcome into diagnostics.

    Parameters
    ----------
    anchor, source : ParsedSource
        The two files being compared.
    anchor_values, source_values : list of ConceptValue
        The values on each side, with their paths.
    mapping : Mapping
        The crosswalk in use, recorded on every diagnostic as provenance.
    rule : FieldRule
        The rule and severity for this concept.
    result : ComparisonResult
        The comparison outcome.

    Returns
    -------
    list of Diagnostic
        Zero or more findings.

    Notes
    -----
    Conflicts are reported even under an informational rule, and never below
    warning level. A package pinned to incompatible constraints in two files
    is a genuine contradiction: one of them is telling users something untrue,
    which is different from one file merely listing fewer dependencies.
    """
    diagnostics: list[Diagnostic] = []

    if result.conflicts:
        severity = (
            Severity.WARNING
            if rule.rule == "informational" and rule.severity is Severity.INFO
            else rule.severity
        )
        for conflict in result.conflicts:
            diagnostics.append(
                mismatch(
                    anchor,
                    anchor_values,
                    source,
                    source_values,
                    mapping,
                    rule,
                    severity=severity,
                    message=(
                        f"{anchor.file} and {source.file} pin "
                        f"{conflict.subject!r} to different versions."
                    ),
                    anchor_value=conflict.anchor,
                    source_value=conflict.source,
                    suggestion=(
                        f"Align the version constraint for {conflict.subject!r} "
                        f"in both files, or drop it from {anchor.file} if the "
                        f"packaging file is authoritative."
                    ),
                )
            )

    if rule_violated(rule.rule, result):
        diagnostics.append(
            mismatch(
                anchor,
                anchor_values,
                source,
                source_values,
                mapping,
                rule,
                severity=rule.severity,
                message=mismatch_message(anchor, source, rule, result),
                anchor_value=render_values(anchor_values, result, side="anchor"),
                source_value=render_values(source_values, result, side="source"),
                suggestion=mismatch_suggestion(anchor, source, rule, result),
            )
        )
    elif rule.rule == "informational" and (
        result.only_in_anchor or result.only_in_source
    ):
        diagnostics.append(
            informational(
                anchor, anchor_values, source, source_values, mapping, rule, result
            )
        )

    return diagnostics
