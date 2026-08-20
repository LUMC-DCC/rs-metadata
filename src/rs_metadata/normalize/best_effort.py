"""Comparison for CodeMeta properties with no strategy of their own.

The dedicated strategies each know something about their concept: that a
version is ordered, that an SPDX identifier has synonyms, that two spellings of
a person's name may denote the same person. That knowledge is what makes them
strict enough to be worth failing a build over.

CodeMeta has sixty-odd record-level properties and the profile speaks to
twenty-five of them. The rest are still worth *comparing* — a `citation` or a
`dateModified` that two files disagree about is worth showing someone — but
there is no concept-specific knowledge to apply, and inventing some would be
guessing.

So this strategy is deliberately shallow. It compares what it can reduce to a
stable key and, crucially, **declines rather than guesses**: a value it cannot
reduce is reported as not comparable, which the report renders as "seen, not
judged". That is the honest answer for a property nobody has thought about
carefully, and it is why every rule built on this strategy is informational.

The one thing it does know is JSON-LD's shape. A bare string, a node with an
``@id``, and a node with a ``name`` are all ordinary ways to write the same
value, so it reduces each the same way the rest of the package does.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from .scalars import IDENTITY_FIRST, normalize_text, scalarize
from .strategies import ComparisonResult, Strategy

__all__ = ["BestEffortStrategy"]


def _date_key(text: str) -> str | None:
    """An ISO date reduced to its calendar day, ignoring any time part.

    GitHub timestamps a repository to the second while a metadata file records
    the day. Comparing the two literally would differ every time.
    """
    head = text.strip().replace("Z", "+00:00")
    for parse in (dt.datetime.fromisoformat, dt.date.fromisoformat):
        try:
            parsed = parse(head)
        except ValueError:
            continue
        return (
            parsed.date() if isinstance(parsed, dt.datetime) else parsed
        ).isoformat()
    return None


class BestEffortStrategy(Strategy):
    """Shape-aware, meaning-agnostic comparison.

    Examples
    --------
    Scalars compare on normalized text, so incidental spacing and case do not
    register as a disagreement:

    >>> strategy = BestEffortStrategy()
    >>> strategy.compare(["Some  Value"], ["some value"]).identical
    True

    A node is reduced the way JSON-LD intends, so the bare and node forms of
    one value agree:

    >>> strategy.compare(
    ...     ["https://example.org/x"],
    ...     [{"@id": "https://example.org/x", "name": "X"}],
    ... ).identical
    True

    Dates agree on the calendar day, because one file records a day and
    another a timestamp:

    >>> strategy.compare(["2026-06-01"], ["2026-06-01T09:31:07Z"]).identical
    True

    A value it cannot reduce is declined rather than guessed at, which the
    report shows as considered but not judged:

    >>> strategy.compare([{"unexpected": ["shape"]}], [{"other": 1}]).comparable
    False
    """

    name = "best-effort"

    def key(self, value: Any) -> str | None:
        scalar = scalarize(value, IDENTITY_FIRST)
        if scalar is None:
            return None
        date = _date_key(scalar)
        if date is not None:
            return date
        return normalize_text(scalar)

    def compare(self, anchor: list[Any], source: list[Any]) -> ComparisonResult:
        result = super().compare(anchor, source)
        # A property this strategy could not reduce on either side is not a
        # disagreement, it is a shape nobody taught it about. Saying so is
        # more useful than reporting a difference between two things it never
        # understood.
        if result.uncomparable_anchor and result.uncomparable_source:
            return ComparisonResult(
                uncomparable_anchor=result.uncomparable_anchor,
                uncomparable_source=result.uncomparable_source,
            )
        return result
