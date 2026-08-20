"""Matching authors and maintainers across metadata formats.

The hardest comparison in the project, and the one most likely to produce a
false alarm. Formats disagree about everything: CodeMeta writes ``givenName``
and CFF writes ``given-names``; packaging files often give only a single
display string; one file abbreviates a given name that another spells out; and
someone's surname may legitimately change between releases.

The rule is that an ORCID is authoritative in **both** directions — two
different ORCIDs are two different people even if the names match exactly —
and that names are only consulted when at least one side has no ORCID.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from nameparser import HumanName

from .identifiers import extract_orcid
from .scalars import as_list, normalize_text

__all__ = [
    "PersonRecord",
    "people_match",
    "person_record",
    "split_full_name",
]

_WHITESPACE = re.compile(r"\s+")

#: Name particles that belong to the family name rather than to the given
#: names. Essential for Dutch and German names, which are common at LUMC:
#: splitting "Jan van der Berg" on whitespace alone gets the family name wrong.


@dataclass(frozen=True)
class PersonRecord:
    """A person or organization reduced to what can be matched across formats.

    Attributes
    ----------
    orcid : str or None
        Bare ORCID, if the entry carries one.
    family, given : str or None
        Normalized name parts.
    name : str or None
        Normalized full name, used for organizations and as a fallback.
    display : str
        Human-readable rendering for the report.
    """

    orcid: str | None
    family: str | None
    given: str | None
    name: str | None
    display: str


def split_full_name(full: str) -> tuple[str | None, str | None]:
    """Split a single name string into given and family parts.

    Parameters
    ----------
    full : str
        A name as one string, in either ``Given Family`` or ``Family, Given``
        order.

    Returns
    -------
    tuple
        ``(given, family)``, either of which may be ``None``.

    Notes
    -----
    A heuristic by nature: formats that offer only one name field give us no
    better information. ``nameparser`` does the splitting, which is why
    particles land with the family name — an earlier version kept its own list
    of prefixes, which handled neither the locale-dependent capitalization nor
    the compound forms.

    Examples
    --------
    >>> split_full_name("Jane Doe")
    ('Jane', 'Doe')

    Particles stay with the family name, across locales:

    >>> split_full_name("Jan van der Berg")
    ('Jan', 'van der Berg')
    >>> split_full_name("Ludwig von Mises")
    ('Ludwig', 'von Mises')
    >>> split_full_name("Maria de la Cruz")
    ('Maria', 'de la Cruz')

    ``Family, Given`` order is understood:

    >>> split_full_name("Doe, Jane")
    ('Jane', 'Doe')

    A mononym is treated as a family name, since that is what citation styles
    do with it:

    >>> split_full_name("Cher")
    (None, 'Cher')
    """
    text = _WHITESPACE.sub(" ", full).strip()
    if not text:
        return None, None
    if "," in text:
        family, _, given = text.partition(",")
        return given.strip() or None, family.strip() or None
    if " " not in text:
        return None, text
    parsed = HumanName(text)
    family = " ".join(part for part in (parsed.last, parsed.suffix) if part).strip()
    given = " ".join(part for part in (parsed.first, parsed.middle) if part).strip()
    return given or None, family or None


def person_record(value: Any) -> PersonRecord:
    """Reduce an author entry from any supported format to a comparable record.

    Parameters
    ----------
    value : Any
        A CodeMeta ``Person``/``Organization`` node, a CFF author entry, a
        packaging ``{"name": ..., "email": ...}`` table, or a bare string.

    Returns
    -------
    PersonRecord
        The comparable form.

    Examples
    --------
    Both naming conventions reduce identically, which is what lets a CodeMeta
    author be compared with a CFF one:

    >>> codemeta = person_record({"givenName": "Jane", "familyName": "Doe"})
    >>> cff = person_record({"given-names": "Jane", "family-names": "Doe"})
    >>> (codemeta.given, codemeta.family) == (cff.given, cff.family)
    True

    An ORCID is picked up from ``@id``, ``orcid`` or ``identifier``:

    >>> person_record({"@id": "https://orcid.org/0000-0002-1825-0097",
    ...                "familyName": "Carberry"}).orcid
    '0000-0002-1825-0097'
    >>> person_record({"orcid": "0000-0002-1825-0097"}).orcid
    '0000-0002-1825-0097'

    A single display string is split:

    >>> record = person_record("Jan van der Berg")
    >>> record.given, record.family
    ('jan', 'van der berg')

    An organization has a name but no name parts:

    >>> record = person_record({"@type": "Organization", "name": "LUMC"})
    >>> record.name, record.family
    ('lumc', None)
    """
    if isinstance(value, str):
        given, family = split_full_name(value)
        return PersonRecord(
            orcid=None,
            family=normalize_text(family),
            given=normalize_text(given),
            name=normalize_text(value),
            display=value.strip(),
        )
    if not isinstance(value, dict):
        return PersonRecord(None, None, None, None, str(value))

    orcid = None
    for key in ("@id", "orcid", "identifier"):
        candidate = value.get(key)
        for item in as_list(candidate):
            orcid = extract_orcid(item)
            if orcid:
                break
        if orcid:
            break

    family = value.get("familyName") or value.get("family-names")
    given = value.get("givenName") or value.get("given-names")
    name = value.get("name")

    # An organization has a name, not name parts. Splitting "Leiden University
    # Medical Center" into given and family names would be meaningless, so
    # organizations are matched on their name alone.
    if not family and value.get("@type") != "Organization" and isinstance(name, str):
        split_given, split_family = split_full_name(name)
        family = split_family
        given = given or split_given

    display = (
        " ".join(
            part
            for part in [str(given or "").strip(), str(family or "").strip()]
            if part
        )
        or str(name or "").strip()
        or (orcid or "?")
    )
    if orcid:
        display = f"{display} <{orcid}>" if display != orcid else orcid

    return PersonRecord(
        orcid=orcid,
        family=normalize_text(family),
        given=normalize_text(given),
        name=normalize_text(name)
        or normalize_text(f"{given or ''} {family or ''}".strip()),
        display=display,
    )


def given_names_compatible(left: str | None, right: str | None) -> bool:
    """Treat initials as compatible with the given names they abbreviate.

    Parameters
    ----------
    left, right : str or None
        Normalized given names. A missing side is compatible with anything,
        since absence is not disagreement.

    Returns
    -------
    bool
        Whether the two could name the same person.

    Examples
    --------
    An initial matches the name it abbreviates:

    >>> given_names_compatible("josiah", "j.")
    True
    >>> given_names_compatible("j", "josiah")
    True

    Two different names do not, however similar:

    >>> given_names_compatible("jane", "john")
    False

    A middle name present on one side only is not a disagreement:

    >>> given_names_compatible("jane m", "jane")
    True

    Neither is a missing given name:

    >>> given_names_compatible(None, "jane")
    True
    """
    if not left or not right:
        return True
    if left == right:
        return True
    left_parts = [part for part in re.split(r"[\s.]+", left) if part]
    right_parts = [part for part in re.split(r"[\s.]+", right) if part]
    if not left_parts or not right_parts:
        return True
    # Compare only the given names both sides supply; a middle name present
    # in one file and omitted in the other is not a disagreement.
    for a, b in zip(left_parts, right_parts, strict=False):
        if a == b:
            continue
        if len(a) == 1 and b.startswith(a):
            continue
        if len(b) == 1 and a.startswith(b):
            continue
        return False
    return True


def people_match(left: PersonRecord, right: PersonRecord) -> bool:
    """Decide whether two entries denote the same person or organization.

    Parameters
    ----------
    left, right : PersonRecord
        Records to compare.

    Returns
    -------
    bool
        Whether they denote the same agent.

    Notes
    -----
    Resolution order: ORCIDs when both sides have one, then family name with
    compatible given names, then normalized full name. ORCIDs are decisive in
    both directions, so a name coincidence cannot merge two real people.

    Examples
    --------
    A shared ORCID outranks differing names — someone's surname may change
    between releases:

    >>> a = person_record({"@id": "https://orcid.org/0000-0002-1825-0097",
    ...                    "givenName": "Josiah", "familyName": "Carberry"})
    >>> b = person_record({"orcid": "0000-0002-1825-0097",
    ...                    "given-names": "J.", "family-names": "Karberri"})
    >>> people_match(a, b)
    True

    Differing ORCIDs outrank identical names:

    >>> a = person_record({"@id": "https://orcid.org/0000-0002-1825-0097",
    ...                    "givenName": "Jane", "familyName": "Doe"})
    >>> b = person_record({"orcid": "0000-0001-5109-3700",
    ...                    "given-names": "Jane", "family-names": "Doe"})
    >>> people_match(a, b)
    False

    Without ORCIDs, names decide, and an initial is accepted:

    >>> people_match(person_record({"givenName": "Josiah", "familyName": "Carberry"}),
    ...              person_record({"given-names": "J.", "family-names": "Carberry"}))
    True
    >>> people_match(person_record({"givenName": "Jane", "familyName": "Doe"}),
    ...              person_record({"given-names": "John", "family-names": "Doe"}))
    False

    Organizations match on name:

    >>> people_match(person_record({"@type": "Organization", "name": "LUMC"}),
    ...              person_record({"name": "lumc"}))
    True
    """
    if left.orcid and right.orcid:
        return left.orcid == right.orcid
    if left.family and right.family:
        return left.family == right.family and given_names_compatible(
            left.given, right.given
        )
    if left.name and right.name:
        return left.name == right.name
    return False
