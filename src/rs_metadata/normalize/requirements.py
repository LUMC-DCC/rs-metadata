"""Parsing dependency declarations across packaging ecosystems.

PEP 508, npm and CRAN each spell a requirement differently, and CodeMeta
expresses one as a node with ``name`` and ``version``. Reducing all four to a
name and a constraint string is what lets the comparison engine tell
*incompleteness* — a package listed in one file and not the other — apart from
a genuine *conflict*, where both files pin the same package incompatibly.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from packaging.version import InvalidVersion, Version

from .scalars import normalize_package_name

__all__ = ["Requirement", "constraints_equivalent", "parse_requirement"]

#: Matches one comparison in a constraint, e.g. ``>=1.24`` or ``!= 2.0``.
_SPECIFIER = re.compile(r"(===|==|!=|<=|>=|~=|<|>)\s*([^,\s]+)")


def constraints_equivalent(left: str, right: str) -> bool:
    """Whether two version constraints say the same thing.

    Parameters
    ----------
    left, right : str
        Normalized constraint strings, as carried on :class:`Requirement`.

    Returns
    -------
    bool
        ``True`` when the two constrain versions identically.

    Notes
    -----
    A plain string comparison reports ``>=1.24`` and ``>=1.24.0`` as a
    conflict, which is a false alarm: they admit exactly the same releases.
    Comparing parsed versions instead makes the two equal, because PEP 440
    says they are.

    Falls back to the string comparison whenever a version does not parse.
    Ecosystems outside Python put things here that PEP 440 does not
    describe — R writes ``1.2-3``, and some records pin a commit hash — and
    guessing at those would trade one false alarm for another.

    Examples
    --------
    Trailing zeros do not change what a constraint admits:

    >>> constraints_equivalent(">=1.24", ">=1.24.0")
    True
    >>> constraints_equivalent(">=1.24", ">=1.24.0.0")
    True

    Genuinely different constraints stay different:

    >>> constraints_equivalent(">=1.24", ">=1.25")
    False
    >>> constraints_equivalent(">=1.24", "<1.24")
    False

    Multiple comparisons are compared as a set, so order does not matter:

    >>> constraints_equivalent(">=1.0,<2.0", "<2.0,>=1.0")
    True

    Anything PEP 440 cannot read is compared as text, unchanged:

    >>> constraints_equivalent(">=1.2-3", ">=1.2-3")
    True
    >>> constraints_equivalent("==a1b2c3d", "==e4f5g6h")
    False
    """
    if left == right:
        return True

    def parsed(text: str) -> set[tuple[str, Version]] | None:
        found = _SPECIFIER.findall(text)
        if not found or "".join(f"{op}{ver}" for op, ver in found) != text.replace(
            ",", ""
        ).replace(" ", ""):
            return None
        try:
            return {(op, Version(ver)) for op, ver in found}
        except InvalidVersion:
            return None

    first, second = parsed(left), parsed(right)
    if first is None or second is None:
        return False
    return first == second


_REQUIREMENT_RE = re.compile(
    r"^\s*(?P<name>[A-Za-z0-9][A-Za-z0-9._\-]*)\s*"
    r"(?:\[(?P<extras>[^\]]*)\])?\s*"
    r"(?P<constraint>.*)$"
)


@dataclass(frozen=True)
class Requirement:
    """One dependency, reduced to a comparable form.

    Attributes
    ----------
    name : str
        Package name, normalized per PEP 503.
    constraint : str
        Version constraint with whitespace removed, or ``""`` when the
        requirement is unpinned.
    display : str
        The requirement as written, for the report.
    """

    name: str
    constraint: str
    display: str


def _normalize_constraint(raw: Any) -> str:
    """Reduce a version constraint to a comparable string.

    Strips enclosing parentheses (R's spelling) and all whitespace, and drops
    a leading ``=``/``==`` so that ``1.0`` and ``==1.0`` compare equal.
    """
    if raw is None:
        return ""
    text = str(raw).strip().strip("()").strip()
    text = re.sub(r"\s+", "", text)
    return text.lstrip("=") if re.match(r"^={1,3}[^=]", text) else text


def parse_requirement(value: Any) -> Requirement | None:
    """Parse a dependency from any supported dependency notation.

    Parameters
    ----------
    value : Any
        A PEP 508 string, an R ``Depends`` entry, or a mapping with ``name``
        and ``version`` — the form npm and CodeMeta are flattened into by
        their adapters.

    Returns
    -------
    Requirement or None
        The parsed requirement, or ``None`` if the value carries no package
        name.

    Notes
    -----
    PEP 508 environment markers are discarded: a dependency that applies only
    on old Python is still the same dependency, and ``codemeta.json`` has
    nowhere to record the marker.

    Examples
    --------
    The four notations reduce to the same requirement:

    >>> for value in ["numpy>=1.24", "numpy >= 1.24", "numpy (>= 1.24)",
    ...               {"name": "numpy", "version": ">=1.24"}]:
    ...     requirement = parse_requirement(value)
    ...     print(requirement.name, requirement.constraint)
    numpy >=1.24
    numpy >=1.24
    numpy >=1.24
    numpy >=1.24

    Extras and environment markers are stripped:

    >>> parse_requirement("numpy[extra]>=1.24").constraint
    '>=1.24'
    >>> parse_requirement('numpy>=1.24; python_version < "3.11"').constraint
    '>=1.24'

    An unpinned requirement has an empty constraint, which the comparison
    engine treats as "no opinion" rather than as a disagreement:

    >>> parse_requirement("matplotlib").constraint
    ''

    Names are normalized per PEP 503:

    >>> parse_requirement("Ruamel.YAML>=0.18").name
    'ruamel-yaml'

    A value with no package name is not a requirement:

    >>> parse_requirement({"version": ">=1.0"}) is None
    True
    >>> parse_requirement("") is None
    True
    """
    if isinstance(value, dict):
        name = value.get("name")
        if not isinstance(name, str) or not name.strip():
            return None
        constraint = value.get("version")
        return Requirement(
            name=normalize_package_name(name) or name,
            constraint=_normalize_constraint(constraint),
            display=f"{name.strip()}{(' ' + str(constraint)) if constraint else ''}",
        )
    if not isinstance(value, str):
        return None
    text = value.split(";")[0].strip()
    if not text:
        return None
    match = _REQUIREMENT_RE.match(text)
    if not match:
        return None
    name = match.group("name")
    return Requirement(
        name=normalize_package_name(name) or name,
        constraint=_normalize_constraint(match.group("constraint")),
        display=text,
    )
