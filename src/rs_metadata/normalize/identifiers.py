"""Persistent identifiers: DOIs, ORCIDs, RORs, EDAM terms and dates.

Two operations live here. *Extraction* recovers a bare identifier from any of
its usual spellings, so the same DOI written four ways compares equal.
*Verification* checks an identifier's own check digits, which is possible
entirely offline and is the reason rs-metadata can call a mistyped ORCID an
error rather than merely unknown.
"""

from __future__ import annotations

import re
from typing import Any

from .scalars import normalize_text, scalarize

__all__ = [
    "EDAM_RE",
    "extract_doi",
    "extract_orcid",
    "extract_ror",
    "normalize_date",
    "orcid_checksum_valid",
    "ror_checksum_valid",
]

_DOI_PREFIX_RE = re.compile(
    r"^(?:https?://(?:dx\.)?doi\.org/|doi:|info:doi/)", re.IGNORECASE
)
_DOI_BODY_RE = re.compile(r"^10\.\d{4,9}/\S+$")

_ORCID_RE = re.compile(
    r"(?:https?://(?:www\.)?orcid\.org/)?(\d{4}-\d{4}-\d{4}-\d{3}[\dX])",
    re.IGNORECASE,
)
_ROR_RE = re.compile(
    r"(?:https?://(?:www\.)?ror\.org/)?(0[a-hj-km-np-tv-z0-9]{6}\d{2})", re.IGNORECASE
)

#: Crockford base32, the alphabet ROR identifiers are encoded in. It omits
#: I, L, O and U so that identifiers cannot be misread aloud or mistyped.
_CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"

#: A well-formed EDAM term IRI. EDAM uses ``http``, not ``https``; a term
#: written with ``https`` will not match the ontology's own identifier.
EDAM_RE = re.compile(
    r"^https?://edamontology\.org/(operation|topic|data|format)_\d{4}$",
    re.IGNORECASE,
)


def extract_doi(raw: Any) -> str | None:
    """Return the bare DOI behind any of its usual spellings.

    Parameters
    ----------
    raw : Any
        A DOI, a resolver URL, a ``doi:`` URI, or a node carrying one.

    Returns
    -------
    str or None
        The bare DOI, case-folded, or ``None`` if the value is not a DOI.

    Notes
    -----
    Matching is *anchored*, not searched. A DOI-shaped substring inside an
    unrelated URL is not a DOI, and treating it as one would silently invent
    an identifier the repository never claimed.

    DOIs are case-insensitive by specification, so the result is case-folded.

    Examples
    --------
    Every spelling yields the same identifier:

    >>> spellings = [
    ...     "10.5281/zenodo.1234567",
    ...     "https://doi.org/10.5281/zenodo.1234567",
    ...     "http://dx.doi.org/10.5281/zenodo.1234567",
    ...     "doi:10.5281/zenodo.1234567",
    ...     "10.5281/ZENODO.1234567",
    ... ]
    >>> {extract_doi(spelling) for spelling in spellings}
    {'10.5281/zenodo.1234567'}

    A ``PropertyValue`` node is reduced first:

    >>> extract_doi({"@type": "PropertyValue", "propertyID": "doi",
    ...              "value": "10.5281/zenodo.1"})
    '10.5281/zenodo.1'

    A DOI-shaped path inside another URL is *not* a DOI:

    >>> extract_doi("https://github.com/org/10.1234/repo") is None
    True

    Neither is a plain URL:

    >>> extract_doi("https://bio.tools/mytool") is None
    True
    """
    text = scalarize(raw)
    if text is None:
        return None
    stripped = _DOI_PREFIX_RE.sub("", text).strip()
    if _DOI_BODY_RE.match(stripped):
        return stripped.rstrip(".").casefold()
    return None


def extract_orcid(raw: Any) -> str | None:
    """Return the bare 16-digit ORCID from any of its usual spellings.

    Parameters
    ----------
    raw : Any
        An ORCID URL or a bare ORCID, or a node carrying one.

    Returns
    -------
    str or None
        The dashed 16-character ORCID, or ``None`` if the value is not one.

    Examples
    --------
    >>> spellings = [
    ...     "https://orcid.org/0000-0002-1825-0097",
    ...     "http://orcid.org/0000-0002-1825-0097",
    ...     "0000-0002-1825-0097",
    ... ]
    >>> {extract_orcid(spelling) for spelling in spellings}
    {'0000-0002-1825-0097'}

    Extraction says nothing about validity — that is
    :func:`orcid_checksum_valid`'s job:

    >>> extract_orcid("https://orcid.org/0000-0000-0000-0000")
    '0000-0000-0000-0000'

    A value of the wrong shape is not an ORCID:

    >>> extract_orcid("https://ror.org/05xvt9f17") is None
    True
    """
    text = scalarize(raw)
    if text is None:
        return None
    match = _ORCID_RE.fullmatch(text.strip())
    return match.group(1).upper() if match else None


def orcid_checksum_valid(orcid: str) -> bool:
    """Verify an ORCID's ISO 7064 MOD 11-2 check digit.

    Parameters
    ----------
    orcid : str
        A bare ORCID, with or without dashes.

    Returns
    -------
    bool
        Whether the final character is the correct check digit.

    Notes
    -----
    The check digit is part of the ORCID specification, so a failure means the
    identifier is mistyped or invented rather than merely unknown. That is
    what makes it safe to verify offline and report as an error.

    Examples
    --------
    ORCID publishes ``0000-0002-1825-0097`` (Josiah Carberry) for
    documentation, and it verifies:

    >>> orcid_checksum_valid("0000-0002-1825-0097")
    True

    Changing one digit breaks it, which is the point:

    >>> orcid_checksum_valid("0000-0002-1825-0098")
    False

    The all-zero placeholder used in documentation examples is not a valid
    ORCID at all:

    >>> orcid_checksum_valid("0000-0000-0000-0000")
    False

    Malformed input is rejected rather than raising:

    >>> orcid_checksum_valid("0000-0002-1825-009")
    False
    >>> orcid_checksum_valid("000A-0002-1825-0097")
    False
    """
    digits = orcid.replace("-", "").upper()
    if len(digits) != 16:
        return False
    total = 0
    for char in digits[:15]:
        if not char.isdigit():
            return False
        total = (total + int(char)) * 2
    expected = (12 - total % 11) % 11
    return digits[15] == ("X" if expected == 10 else str(expected))


def extract_ror(raw: Any) -> str | None:
    """Return the bare ROR identifier from any of its usual spellings.

    Parameters
    ----------
    raw : Any
        A ROR URL or a bare ROR, or a node carrying one.

    Returns
    -------
    str or None
        The nine-character ROR, lower-cased, or ``None`` if not one.

    Examples
    --------
    >>> extract_ror("https://ror.org/05xvt9f17")
    '05xvt9f17'
    >>> extract_ror("05xvt9f17")
    '05xvt9f17'
    >>> extract_ror("https://orcid.org/0000-0002-1825-0097") is None
    True
    """
    text = scalarize(raw)
    if text is None:
        return None
    match = _ROR_RE.fullmatch(text.strip())
    return match.group(1).lower() if match else None


def ror_checksum_valid(ror: str) -> bool:
    """Verify a ROR identifier's ISO 7064 MOD 97-10 check digits.

    Parameters
    ----------
    ror : str
        A bare nine-character ROR identifier.

    Returns
    -------
    bool
        Whether the final two digits are the correct checksum.

    Notes
    -----
    The first seven characters are Crockford base32; decoded as an integer,
    multiplied by 100, the checksum is ``98 - (value mod 97)``.

    Examples
    --------
    LUMC's own ROR verifies:

    >>> ror_checksum_valid("05xvt9f17")
    True

    Changing the check digits breaks it:

    >>> ror_checksum_valid("05xvt9f18")
    False

    So does the wrong length, or characters outside the alphabet:

    >>> ror_checksum_valid("05xvt9f1")
    False
    >>> ror_checksum_valid("05xvt9fxx")
    False
    """
    if len(ror) != 9:
        return False
    body, check = ror[:-2].upper(), ror[-2:]
    if not check.isdigit():
        return False
    value = 0
    for char in body:
        position = _CROCKFORD.find(char)
        if position < 0:
            return False
        value = value * 32 + position
    return int(check) == 98 - (value * 100) % 97


def normalize_date(raw: Any) -> str | None:
    """Reduce a date or timestamp to its ISO calendar date.

    Parameters
    ----------
    raw : Any
        An ISO 8601 date or timestamp, or a node carrying one.

    Returns
    -------
    str or None
        The ``YYYY-MM-DD`` date part, or a text key if the value is not a
        date at all.

    Examples
    --------
    A timestamp and the bare date name the same day:

    >>> normalize_date("2026-06-01T09:30:00Z")
    '2026-06-01'
    >>> normalize_date("2026-06-01")
    '2026-06-01'

    Anything that is not a date falls back to text comparison rather than
    being discarded:

    >>> normalize_date("Spring 2026")
    'spring 2026'
    """
    text = scalarize(raw)
    if text is None:
        return None
    match = re.match(r"^(\d{4}-\d{2}-\d{2})", text.strip())
    return match.group(1) if match else normalize_text(text)
