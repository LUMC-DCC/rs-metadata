"""Comparison strategies: how two sets of values are judged equivalent.

A crosswalk says *which* concepts correspond. A strategy decides *when two
representations of a concept are the same thing*, which is the separate and
much harder question this module answers.

Each strategy exposes three operations:

``key(value)``
    A comparison key, or ``None`` when the value carries nothing comparable.
``display(value)``
    A short human-readable rendering for the report.
``compare(anchor, source)``
    Set-level comparison, returning a :class:`ComparisonResult`.

The default :meth:`Strategy.compare` is key equality, which covers most
concepts. Only the two with real internal structure — people and dependencies
— override it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from .identifiers import extract_doi, normalize_date
from .licenses import normalize_license
from .people import people_match, person_record
from .requirements import constraints_equivalent, parse_requirement
from .scalars import (
    LABEL_FIRST,
    normalize_loose_name,
    normalize_text,
    scalarize,
)
from .uris import normalize_uri
from .versions import normalize_version

__all__ = [
    "STRATEGIES",
    "ComparisonResult",
    "Conflict",
    "Strategy",
    "get_strategy",
]


@dataclass(frozen=True)
class Conflict:
    """Two values that address the same thing but disagree about it.

    Distinct from a value present on one side only: a conflict is a
    contradiction, whereas a one-sided value is merely incompleteness.

    Attributes
    ----------
    subject : str
        What the two values are about, such as a package name.
    anchor, source : str
        The disagreeing values, as written.
    """

    subject: str
    anchor: str
    source: str


@dataclass
class ComparisonResult:
    """What a strategy found when comparing two sets of values.

    Deliberately richer than a boolean: the consistency engine turns the same
    result into different diagnostics depending on whether the mapping asked
    for equality, a subset or an overlap, and the report echoes the specific
    values involved.

    Attributes
    ----------
    shared : int
        Number of values matched on both sides.
    only_in_anchor, only_in_source : list of str
        Display forms of the unmatched values on each side.
    conflicts : list of Conflict
        Same subject, disagreeing values.
    uncomparable_anchor, uncomparable_source : list of str
        Values that yielded no comparison key at all.
    """

    shared: int = 0
    only_in_anchor: list[str] = field(default_factory=list)
    only_in_source: list[str] = field(default_factory=list)
    conflicts: list[Conflict] = field(default_factory=list)
    uncomparable_anchor: list[str] = field(default_factory=list)
    uncomparable_source: list[str] = field(default_factory=list)

    @property
    def comparable(self) -> bool:
        """Whether anything at all could be compared.

        Examples
        --------
        >>> ComparisonResult(shared=1).comparable
        True
        >>> ComparisonResult(uncomparable_source=["dynamic"]).comparable
        False
        """
        return bool(
            self.shared or self.only_in_anchor or self.only_in_source or self.conflicts
        )

    @property
    def identical(self) -> bool:
        """Whether the two sides agree completely.

        Examples
        --------
        >>> ComparisonResult(shared=2).identical
        True
        >>> ComparisonResult(shared=1, only_in_source=["extra"]).identical
        False
        """
        return not (self.only_in_anchor or self.only_in_source or self.conflicts)


class Strategy:
    """Base strategy: comparison by normalized key equality.

    Subclasses normally override only :meth:`key`. Override :meth:`compare`
    when the concept has structure that key equality cannot express.
    """

    name = "text"

    def key(self, value: Any) -> str | None:
        """Comparison key for one value, or ``None`` if not comparable."""
        return normalize_text(scalarize(value, LABEL_FIRST))

    def display(self, value: Any) -> str:
        """Human-readable rendering of one value, for the report."""
        scalar = scalarize(value, LABEL_FIRST)
        return scalar if scalar is not None else str(value)

    def compare(self, anchor: list[Any], source: list[Any]) -> ComparisonResult:
        """Compare two sets of values by key equality.

        Parameters
        ----------
        anchor : list
            Values from ``codemeta.json``, the canonical record.
        source : list
            Values from the companion file.

        Returns
        -------
        ComparisonResult
            The outcome. Order is never significant: values are compared as
            sets, and a duplicate key collapses to its first occurrence.

        Examples
        --------
        >>> strategy = get_strategy("text")
        >>> strategy.compare(["genomics"], ["Genomics"]).identical
        True

        Order does not matter:

        >>> strategy.compare(["a", "b"], ["b", "a"]).identical
        True

        Differences are reported per side:

        >>> result = strategy.compare(["a", "b"], ["b", "c"])
        >>> result.shared, result.only_in_anchor, result.only_in_source
        (1, ['a'], ['c'])
        """
        result = ComparisonResult()
        anchor_keys: dict[str, str] = {}
        source_keys: dict[str, str] = {}

        for value in anchor:
            key = self.key(value)
            if key is None:
                result.uncomparable_anchor.append(self.display(value))
            else:
                anchor_keys.setdefault(key, self.display(value))
        for value in source:
            key = self.key(value)
            if key is None:
                result.uncomparable_source.append(self.display(value))
            else:
                source_keys.setdefault(key, self.display(value))

        result.shared = len(anchor_keys.keys() & source_keys.keys())
        result.only_in_anchor = [
            display for key, display in anchor_keys.items() if key not in source_keys
        ]
        result.only_in_source = [
            display for key, display in source_keys.items() if key not in anchor_keys
        ]
        return result


class TextStrategy(Strategy):
    """Free text, compared ignoring case, whitespace and trailing stops."""

    name = "text"


class NameStrategy(Strategy):
    """Software names, compared across the display/package-name divide.

    Examples
    --------
    >>> strategy = get_strategy("name")
    >>> strategy.compare(["MyTool"], ["my-tool"]).identical
    True
    >>> strategy.compare(["MyTool"], ["other-tool"]).identical
    False
    """

    name = "name"

    def key(self, value: Any) -> str | None:
        return normalize_loose_name(scalarize(value, LABEL_FIRST))


class VersionStrategy(Strategy):
    """Versions, compared semantically rather than textually.

    Examples
    --------
    >>> strategy = get_strategy("version")
    >>> strategy.compare(["1.2.0"], ["v1.2"]).identical
    True
    >>> strategy.compare(["1.2"], ["1.20"]).identical
    False
    """

    name = "version"

    def key(self, value: Any) -> str | None:
        return normalize_version(scalarize(value, LABEL_FIRST))


class UriStrategy(Strategy):
    """URLs, compared ignoring scheme, ``www.``, trailing slash and ``.git``.

    Examples
    --------
    >>> strategy = get_strategy("uri")
    >>> strategy.compare(
    ...     ["https://github.com/org/tool"],
    ...     ["git+https://github.com/org/tool.git"],
    ... ).identical
    True
    """

    name = "uri"

    def key(self, value: Any) -> str | None:
        return normalize_uri(scalarize(value), expand_shorthand=True)


class SpdxStrategy(Strategy):
    """Licenses, resolved against the vendored SPDX list.

    Examples
    --------
    >>> strategy = get_strategy("spdx")
    >>> strategy.compare(["https://spdx.org/licenses/MIT"], ["mit"]).identical
    True
    >>> strategy.compare(["MIT"], ["Apache-2.0"]).identical
    False
    """

    name = "spdx"

    def key(self, value: Any) -> str | None:
        return normalize_license(value)


class DoiStrategy(Strategy):
    """DOIs, compared regardless of resolver prefix or case.

    Examples
    --------
    >>> strategy = get_strategy("doi")
    >>> strategy.compare(
    ...     ["https://doi.org/10.5281/zenodo.1"], ["10.5281/ZENODO.1"]
    ... ).identical
    True
    """

    name = "doi"

    def key(self, value: Any) -> str | None:
        return extract_doi(value)


class IdentifierStrategy(Strategy):
    """Identifiers of mixed kinds: DOIs, resolver URLs, registry URLs.

    A DOI written three ways is one identifier; a DOI and a bio.tools URL are
    two. Keys are namespaced so a DOI can never collide with a URL.

    Examples
    --------
    >>> strategy = get_strategy("identifier")
    >>> strategy.compare(
    ...     ["https://doi.org/10.5281/zenodo.1", "https://bio.tools/mytool"],
    ...     ["10.5281/zenodo.1"],
    ... ).only_in_anchor
    ['https://bio.tools/mytool']
    """

    name = "identifier"

    def key(self, value: Any) -> str | None:
        doi = extract_doi(value)
        if doi:
            return f"doi:{doi}"
        scalar = scalarize(value)
        if scalar is None:
            return None
        if "://" in scalar:
            uri = normalize_uri(scalar)
            return f"uri:{uri}" if uri else None
        return f"text:{normalize_text(scalar)}"


class DateStrategy(Strategy):
    """Dates, compared by calendar day.

    Examples
    --------
    >>> strategy = get_strategy("date")
    >>> strategy.compare(["2026-06-01"], ["2026-06-01T09:30:00Z"]).identical
    True
    """

    name = "date"

    def key(self, value: Any) -> str | None:
        return normalize_date(value)


class LanguageStrategy(Strategy):
    """Programming languages, ignoring any pinned version.

    ``Python`` and ``Python 3.11`` are the same language; a version difference
    between a packaging file and ``codemeta.json`` is not a metadata
    contradiction.

    Examples
    --------
    >>> strategy = get_strategy("language")
    >>> node = {"@type": "ComputerLanguage", "name": "Python", "version": "3.12"}
    >>> strategy.compare([node], ["Python"]).identical
    True
    >>> strategy.compare(["Python 3.11"], ["Python"]).identical
    True
    """

    name = "language"

    def key(self, value: Any) -> str | None:
        scalar = scalarize(value, LABEL_FIRST)
        if scalar is None:
            return None
        stripped = re.sub(r"\s*[\d.]+\s*$", "", scalar).strip()
        return normalize_text(stripped or scalar)


class PeopleStrategy(Strategy):
    """Authors and maintainers, matched semantically rather than by serialization.

    Matching is greedy and one-to-one: each anchor entry claims at most one
    source entry, so two identically-named authors cannot both be satisfied by
    a single counterpart.

    Examples
    --------
    >>> strategy = get_strategy("people")

    An ORCID matches across differing names and abbreviated given names:

    >>> anchor = [{"@id": "https://orcid.org/0000-0002-1825-0097",
    ...            "givenName": "Josiah", "familyName": "Carberry"}]
    >>> source = [{"orcid": "0000-0002-1825-0097",
    ...            "given-names": "J.", "family-names": "Karberri"}]
    >>> strategy.compare(anchor, source).identical
    True

    Matching is one-to-one, so a duplicate on one side is reported:

    >>> twice = [{"givenName": "Jane", "familyName": "Doe"}] * 2
    >>> once = [{"given-names": "Jane", "family-names": "Doe"}]
    >>> result = strategy.compare(twice, once)
    >>> result.shared, result.only_in_anchor
    (1, ['Jane Doe'])
    """

    name = "people"

    def key(self, value: Any) -> str | None:  # pragma: no cover - unused
        record = person_record(value)
        return record.orcid or record.name

    def display(self, value: Any) -> str:
        return person_record(value).display

    def compare(self, anchor: list[Any], source: list[Any]) -> ComparisonResult:
        """Match two author lists semantically.

        Parameters
        ----------
        anchor, source : list
            Author entries in any supported format.

        Returns
        -------
        ComparisonResult
            Entries carrying no identifying information at all land in the
            ``uncomparable_*`` lists rather than being reported as missing.
        """
        result = ComparisonResult()
        anchor_records = [person_record(value) for value in anchor]
        source_records = [person_record(value) for value in source]

        unmatched_source = list(range(len(source_records)))
        for record in anchor_records:
            if not (record.orcid or record.family or record.name):
                result.uncomparable_anchor.append(record.display)
                continue
            match = next(
                (
                    position
                    for position in unmatched_source
                    if people_match(record, source_records[position])
                ),
                None,
            )
            if match is None:
                result.only_in_anchor.append(record.display)
            else:
                unmatched_source.remove(match)
                result.shared += 1

        for position in unmatched_source:
            record = source_records[position]
            if not (record.orcid or record.family or record.name):
                result.uncomparable_source.append(record.display)
            else:
                result.only_in_source.append(record.display)
        return result


class DependencySetStrategy(Strategy):
    """Dependencies, matched by package name so version constraints can differ.

    A package listed in one file and not the other is incompleteness; the same
    package pinned to incompatible constraints in both is a contradiction.
    Only the latter becomes a :class:`Conflict`, which is what lets the
    engine report dependencies without drowning the user in noise.

    Examples
    --------
    >>> strategy = get_strategy("dependency-set")
    >>> result = strategy.compare(
    ...     [{"name": "numpy", "version": ">=2.0"}, {"name": "scipy"}],
    ...     ["numpy>=1.24", "pandas"],
    ... )

    The shared package with incompatible pins is a conflict:

    >>> [conflict.subject for conflict in result.conflicts]
    ['numpy']

    while one-sided packages are merely one-sided:

    >>> result.only_in_anchor, result.only_in_source
    (['scipy'], ['pandas'])

    A constraint on one side only is not a conflict — absence is not
    disagreement:

    >>> strategy.compare([{"name": "numpy"}], ["numpy>=1.24"]).conflicts
    []
    """

    name = "dependency-set"

    def display(self, value: Any) -> str:
        requirement = parse_requirement(value)
        return requirement.display if requirement else str(value)

    def compare(self, anchor: list[Any], source: list[Any]) -> ComparisonResult:
        """Match two dependency lists by package name.

        Parameters
        ----------
        anchor, source : list
            Dependency declarations in any supported notation.

        Returns
        -------
        ComparisonResult
            With ``conflicts`` populated for packages present on both sides
            whose constraints differ.
        """
        result = ComparisonResult()
        anchor_requirements: dict[str, Any] = {}
        source_requirements: dict[str, Any] = {}

        for value in anchor:
            requirement = parse_requirement(value)
            if requirement is None:
                result.uncomparable_anchor.append(self.display(value))
            else:
                anchor_requirements.setdefault(requirement.name, requirement)
        for value in source:
            requirement = parse_requirement(value)
            if requirement is None:
                result.uncomparable_source.append(self.display(value))
            else:
                source_requirements.setdefault(requirement.name, requirement)

        for name, requirement in anchor_requirements.items():
            other = source_requirements.get(name)
            if other is None:
                result.only_in_anchor.append(requirement.display)
                continue
            result.shared += 1
            if (
                requirement.constraint
                and other.constraint
                and not constraints_equivalent(requirement.constraint, other.constraint)
            ):
                result.conflicts.append(
                    Conflict(
                        subject=name,
                        anchor=requirement.display,
                        source=other.display,
                    )
                )
        for name, requirement in source_requirements.items():
            if name not in anchor_requirements:
                result.only_in_source.append(requirement.display)
        return result


#: The concept-specific strategies. ``best-effort``, which builds on
#: :class:`Strategy` and so cannot be imported from here, is registered by the
#: package's ``__init__`` once both modules have loaded.
STRATEGIES: dict[str, Strategy] = {
    strategy.name: strategy
    for strategy in (
        TextStrategy(),
        NameStrategy(),
        VersionStrategy(),
        UriStrategy(),
        SpdxStrategy(),
        DoiStrategy(),
        IdentifierStrategy(),
        DateStrategy(),
        LanguageStrategy(),
        PeopleStrategy(),
        DependencySetStrategy(),
    )
}


def get_strategy(name: str) -> Strategy:
    """Look up a comparison strategy by the name a mapping file uses.

    Parameters
    ----------
    name : str
        Strategy name, as written in a mapping file's ``strategy`` key.

    Returns
    -------
    Strategy
        The registered strategy.

    Raises
    ------
    KeyError
        If no strategy is registered under that name. The message lists the
        available names, since this can only be reached through a typo in a
        mapping file.

    Examples
    --------
    >>> get_strategy("version").name
    'version'

    An unknown name fails loudly rather than silently comparing as text:

    >>> get_strategy("nonexistent")
    Traceback (most recent call last):
        ...
    KeyError: "Unknown comparison strategy 'nonexistent'. Available...version."
    """
    try:
        return STRATEGIES[name]
    except KeyError:  # pragma: no cover - guards mapping-file typos
        raise KeyError(
            f"Unknown comparison strategy {name!r}. Available strategies: "
            f"{', '.join(sorted(STRATEGIES))}."
        ) from None
