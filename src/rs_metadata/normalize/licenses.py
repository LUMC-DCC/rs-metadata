"""License normalization against the vendored SPDX license list.

The SPDX list ships inside the package, so identifiers are resolved against
the real thing, including deprecations.
"""

from __future__ import annotations

import re
from typing import Any

from ..vocabulary import spdx_index
from .scalars import normalize_text, scalarize

__all__ = [
    "SPDX_OPERATORS",
    "SPDX_URL_PREFIX",
    "normalize_license",
    "spdx_identifier",
]

SPDX_URL_PREFIX = "https://spdx.org/licenses/"

_SPDX_URL_RE = re.compile(
    r"^https?://spdx\.org/licenses/([^/#?]+?)(?:\.html|\.json)?/?$", re.IGNORECASE
)

#: Operators in an SPDX license expression, uppercased when canonicalising.
#: The operators that make an SPDX expression rather than a bare identifier.
SPDX_OPERATORS = frozenset({"AND", "OR", "WITH"})


def spdx_identifier(raw: Any) -> str | None:
    """Resolve a value to a canonical SPDX identifier.

    Parameters
    ----------
    raw : Any
        An SPDX identifier, an ``spdx.org/licenses/`` URL, or a node carrying
        one.

    Returns
    -------
    str or None
        The identifier in SPDX's own capitalisation, or ``None`` if the value
        is not a recognized SPDX identifier.

    Notes
    -----
    SPDX identifiers are case-sensitive by specification, but people write
    ``apache-2.0`` constantly. Recognizing the value and reporting the
    canonical spelling is more useful than rejecting it.

    ``LicenseRef-`` identifiers name a license outside the SPDX list; they are
    returned as written, since there is nothing to canonicalise against.

    Examples
    --------
    URL and bare forms resolve alike, and casing is corrected:

    >>> spdx_identifier("https://spdx.org/licenses/Apache-2.0")
    'Apache-2.0'
    >>> spdx_identifier("apache-2.0")
    'Apache-2.0'
    >>> spdx_identifier("https://spdx.org/licenses/Apache-2.0.html")
    'Apache-2.0'

    A ``CreativeWork`` node is reduced to its URL first:

    >>> spdx_identifier({"@type": "CreativeWork", "name": "Apache License 2.0",
    ...                  "url": "https://spdx.org/licenses/Apache-2.0"})
    'Apache-2.0'

    A URL that claims SPDX but names no real license is not resolved — the
    profile reports that as an error:

    >>> spdx_identifier("https://spdx.org/licenses/Apache-2.0-only") is None
    True

    Neither is free text:

    >>> spdx_identifier("Our institutional license") is None
    True
    """
    text = scalarize(raw)
    if text is None:
        return None
    url_match = _SPDX_URL_RE.match(text)
    candidate = url_match.group(1) if url_match else text
    canonical = spdx_index().get(candidate.casefold())
    if canonical:
        return canonical
    if candidate.casefold().startswith("licenseref-"):
        return candidate
    return None


def normalize_license(raw: Any) -> str | None:
    """Normalize a license value, including simple SPDX expressions.

    Parameters
    ----------
    raw : Any
        An SPDX identifier or URL, an SPDX expression, or free text.

    Returns
    -------
    str or None
        A comparison key, or ``None`` if empty.

    Notes
    -----
    Falls back to text comparison for licenses that are not SPDX at all, so a
    custom or institutional license still compares consistently across files
    rather than being dropped.

    Expression operands are canonicalised and operators uppercased, but
    operands are **not** reordered: ``A OR B`` and ``B OR A`` mean the same
    thing, but reordering around mixed ``AND``/``OR`` precedence would not be
    safe. Multi-license records normally use a CodeMeta array, where the set
    comparison already makes order irrelevant.

    Examples
    --------
    Every spelling of one license collapses together:

    >>> spellings = [
    ...     "Apache-2.0",
    ...     "apache-2.0",
    ...     "https://spdx.org/licenses/Apache-2.0",
    ...     "http://spdx.org/licenses/Apache-2.0",
    ... ]
    >>> {normalize_license(spelling) for spelling in spellings}
    {'Apache-2.0'}

    Different licenses stay different:

    >>> normalize_license("MIT") == normalize_license("Apache-2.0")
    False

    Expressions are canonicalised:

    >>> normalize_license("mit OR apache-2.0")
    'MIT OR Apache-2.0'
    >>> normalize_license("GPL-2.0-only WITH Classpath-exception-2.0")
    'GPL-2.0-only WITH Classpath-exception-2.0'

    Unrecognized licenses fall back to text, so they still compare:

    >>> normalize_license("Our License") == normalize_license("  our license  ")
    True
    """
    single = spdx_identifier(raw)
    if single:
        return single
    text = scalarize(raw)
    if text is None:
        return None
    tokens = text.replace("(", " ( ").replace(")", " ) ").split()
    if len(tokens) > 1 and any(token.upper() in SPDX_OPERATORS for token in tokens):
        rendered: list[str] = []
        recognized = False
        for token in tokens:
            if token.upper() in SPDX_OPERATORS or token in {"(", ")"}:
                rendered.append(token.upper())
                continue
            plus = token.endswith("+")
            bare = token.rstrip("+")
            canonical = spdx_index().get(bare.casefold())
            if canonical:
                recognized = True
            rendered.append((canonical or bare) + ("+" if plus else ""))
        if recognized:
            return " ".join(rendered)
    return normalize_text(text)
