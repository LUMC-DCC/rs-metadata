"""Turning a comparison outcome into a diagnostic a maintainer can act on.

Kept apart from the engine because the two answer different questions. The
engine decides *whether* a rule was violated; this module decides *how to say
so* — which values to echo back, which file to point at, and what fix to
suggest.
"""

from __future__ import annotations

from typing import Any

from ..concepts import ConceptValue, ParsedSource, location
from ..diagnostics import Severity
from ..mapping import FieldRule, Mapping
from ..normalize import ComparisonResult, get_strategy
from ..report import Diagnostic, Location

__all__ = [
    "MAX_LISTED",
    "informational",
    "join",
    "mismatch",
    "mismatch_message",
    "mismatch_suggestion",
    "missing_from_anchor",
    "uncomparable",
]

#: How many differing values to name before summarizing the rest. A diagnostic
#: listing forty keywords is not more informative than one listing five.
MAX_LISTED = 5


def join(items: list[str]) -> str:
    """Render a list of values for a message, summarizing a long tail.

    Parameters
    ----------
    items : list of str
        Display forms of the values.

    Returns
    -------
    str
        A comma-separated rendering, truncated after :data:`MAX_LISTED`.

    Examples
    --------
    >>> join(["1.0.0"])
    '1.0.0'
    >>> join(["a", "b", "c"])
    'a, b, c'

    A long tail is summarized rather than dumped:

    >>> join(["a", "b", "c", "d", "e", "f", "g"])
    'a, b, c, d, e and 2 more'

    An empty list still reads as a sentence:

    >>> join([])
    'nothing'
    """
    if not items:
        return "nothing"
    shown = items[:MAX_LISTED]
    rendered = ", ".join(shown)
    remaining = len(items) - len(shown)
    return f"{rendered} and {remaining} more" if remaining else rendered


def is_scalar_pair(result: ComparisonResult) -> bool:
    """Whether both sides hold exactly one differing value.

    When they do, a side-by-side rendering reads far better than a list of
    differences, so the message is composed differently.

    Examples
    --------
    >>> is_scalar_pair(ComparisonResult(only_in_anchor=["1.2"],
    ...                                 only_in_source=["1.1"]))
    True
    >>> is_scalar_pair(ComparisonResult(shared=1, only_in_source=["extra"]))
    False
    """
    return (
        len(result.only_in_anchor) == 1
        and len(result.only_in_source) == 1
        and result.shared == 0
    )


def mismatch_message(
    anchor: ParsedSource,
    source: ParsedSource,
    rule: FieldRule,
    result: ComparisonResult,
) -> str:
    """Compose the sentence describing a rule violation.

    Parameters
    ----------
    anchor, source : ParsedSource
        The two files being compared.
    rule : FieldRule
        The mapping rule that was violated.
    result : ComparisonResult
        The comparison outcome.

    Returns
    -------
    str
        A complete sentence naming both files and the property.
    """
    prop = rule.property
    if rule.rule == "overlap":
        return (
            f"{prop} in {source.file} has nothing in common with {prop} in "
            f"{anchor.file}."
        )
    if rule.rule == "subset":
        return (
            f"{source.file} records {prop} that {anchor.file} does not: "
            f"{join(result.only_in_source)}."
        )
    if is_scalar_pair(result):
        return f"{prop} differs between {anchor.file} and {source.file}."
    parts = []
    if result.only_in_anchor:
        parts.append(f"only in {anchor.file}: {join(result.only_in_anchor)}")
    if result.only_in_source:
        parts.append(f"only in {source.file}: {join(result.only_in_source)}")
    return f"{prop} differs between {anchor.file} and {source.file} — " + "; ".join(
        parts
    )


def mismatch_suggestion(
    anchor: ParsedSource,
    source: ParsedSource,
    rule: FieldRule,
    result: ComparisonResult,
) -> str:
    """Compose the remediation advice for a rule violation.

    Parameters
    ----------
    anchor, source : ParsedSource
        The two files being compared.
    rule : FieldRule
        The mapping rule that was violated.
    result : ComparisonResult
        The comparison outcome.

    Returns
    -------
    str
        Concrete advice. Always names which file is canonical, because the
        commonest question on seeing a mismatch is "which one do I change?".
    """
    if rule.property == "version":
        return (
            "Update whichever file is stale so both describe the same release. "
            "Version is one of the fields that must be bumped in every "
            "metadata file at release time."
        )
    if rule.rule == "subset":
        return (
            f"Add the missing values to {anchor.file}, which is the canonical "
            f"record, or remove them from {source.file} if they are wrong."
        )
    if rule.rule == "overlap":
        return (
            f"Check that {source.file} and {anchor.file} describe the same "
            f"software; a complete absence of overlap usually means one was "
            f"copied from another project."
        )
    return (
        f"Reconcile the two files. {anchor.file} is the canonical record, so "
        f"correct {source.file} unless {anchor.file} is the stale one."
    )


# ---------------------------------------------------------------------------
# Diagnostic builders
# ---------------------------------------------------------------------------


def mismatch(
    anchor: ParsedSource,
    anchor_values: list[ConceptValue],
    source: ParsedSource,
    source_values: list[ConceptValue],
    mapping: Mapping,
    rule: FieldRule,
    *,
    severity: Severity,
    message: str,
    anchor_value: Any,
    source_value: Any,
    suggestion: str,
) -> Diagnostic:
    """Build a ``consistency.mismatch`` diagnostic.

    Carries both sides with their own file, path and line, so a renderer can
    show them side by side and CI can annotate the anchor.
    """
    return Diagnostic(
        code="consistency.mismatch",
        severity=severity,
        message=message,
        property=rule.property,
        anchor=_location(anchor, anchor_values, anchor_value),
        source=_location(source, source_values, source_value, rule.source),
        strategy=rule.strategy,
        rule=rule.rule,
        mapping=mapping.reference,
        suggestion=suggestion,
    )


def informational(
    anchor: ParsedSource,
    anchor_values: list[ConceptValue],
    source: ParsedSource,
    source_values: list[ConceptValue],
    mapping: Mapping,
    rule: FieldRule,
    result: ComparisonResult,
) -> Diagnostic:
    """Build a ``consistency.incomplete`` diagnostic for an informational rule.

    Used when the mapping asked for differences to be reported without
    judgement, so the message states the difference and the suggestion
    explains why it is not being judged.
    """
    parts = []
    if result.only_in_source:
        parts.append(f"only in {source.file}: {join(result.only_in_source)}")
    if result.only_in_anchor:
        parts.append(f"only in {anchor.file}: {join(result.only_in_anchor)}")
    return Diagnostic(
        code="consistency.incomplete",
        severity=rule.severity,
        message=(
            f"{rule.property} is recorded differently in {anchor.file} and "
            f"{source.file} — " + "; ".join(parts) + "."
        ),
        property=rule.property,
        anchor=_location(anchor, anchor_values, None),
        source=_location(source, source_values, None, rule.source),
        strategy=rule.strategy,
        rule=rule.rule,
        mapping=mapping.reference,
        suggestion=(
            rule.note.strip()
            if rule.note
            else (
                f"No action is required. Add the values to {anchor.file} if "
                f"they belong in the canonical record."
            )
        ),
    )


def missing_from_anchor(
    anchor: ParsedSource,
    source: ParsedSource,
    mapping: Mapping,
    rule: FieldRule,
    source_values: list[ConceptValue],
) -> Diagnostic:
    """Build a ``consistency.incomplete`` diagnostic for a one-sided value.

    The source records something the anchor omits. Not a contradiction, but
    occasionally it reveals metadata that was never copied across.
    """
    rendered = join(
        [get_strategy(rule.strategy).display(value.raw) for value in source_values]
    )
    return Diagnostic(
        code="consistency.incomplete",
        severity=Severity.INFO,
        message=(
            f"{source.file} records {rule.property} ({rendered}) but "
            f"{anchor.file} does not."
        ),
        property=rule.property,
        source=_location(source, source_values, rendered, rule.source),
        strategy=rule.strategy,
        rule=rule.rule,
        mapping=mapping.reference,
        suggestion=(
            f"Consider adding {rule.property} to {anchor.file}, which is the "
            f"record registries and archives harvest."
        ),
    )


def uncomparable(
    anchor: ParsedSource,
    source: ParsedSource,
    mapping: Mapping,
    rule: FieldRule,
    source_values: list[ConceptValue],
    reason: str | None,
) -> Diagnostic:
    """Build a ``consistency.uncomparable`` diagnostic.

    Reported so the report is a complete account of what was and was not
    checked: a reader can tell "these agree" from "these were never compared".
    """
    return Diagnostic(
        code="consistency.uncomparable",
        severity=Severity.INFO,
        message=(
            f"{rule.property} was not compared between {anchor.file} and "
            f"{source.file}. "
            + (reason.strip() if reason else "The mapping loses too much information.")
        ),
        property=rule.property,
        source=_location(source, source_values, None, rule.source),
        strategy=rule.strategy,
        rule=rule.rule,
        mapping=mapping.reference,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _location(
    parsed: ParsedSource,
    values: list[ConceptValue],
    value: Any,
    fallback_path: str | None = None,
) -> Location:
    """Build a location for one side of a comparison.

    Falls back to the mapping's declared source label when the concept value
    carries no path of its own, so the report still says *where* in the source
    format the value lives.
    """
    if values:
        built = location(parsed, values[0].path, value)
        if built.path:
            return built
        return Location(
            file=built.file,
            path=fallback_path or None,
            line=built.line,
            column=built.column,
            value=value,
        )
    return Location(file=parsed.file, path=fallback_path or None, value=value)


def render_values(
    values: list[ConceptValue], result: ComparisonResult, *, side: str
) -> str:
    """Choose which values to echo back for one side of a mismatch.

    Prefers the *differing* values, since those are what the reader needs to
    see; falls back to everything when the difference is not per-value.

    Parameters
    ----------
    values : list of ConceptValue
        All values on this side.
    result : ComparisonResult
        The comparison outcome.
    side : {"anchor", "source"}
        Which side to render.

    Returns
    -------
    str
        The rendering for the diagnostic's ``value`` field.
    """
    differing = result.only_in_anchor if side == "anchor" else result.only_in_source
    if differing:
        return join(differing)
    return join([str(value.raw) for value in values])
