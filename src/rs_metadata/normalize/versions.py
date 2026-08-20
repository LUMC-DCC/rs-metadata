"""Version normalization.

Ecosystems spell the same release differently: a leading ``v``, a trailing
``.0``, R's dash before the final component. A version comparison that fired
on those would be useless, and one that ignored real differences would be
worse.
"""

from __future__ import annotations

import re
from typing import Any

from .scalars import normalize_text

__all__ = ["COMMIT_PREFIX_LENGTH", "normalize_version"]

#: How many characters of a commit hash are kept as the comparison key. A
#: short hash and the full hash it abbreviates then produce the same key by
#: plain equality, with a collision risk that is irrelevant at this scale.
COMMIT_PREFIX_LENGTH = 7

_VERSION_RE = re.compile(r"^v?(\d+(?:[._-]\d+)*)(.*)$", re.IGNORECASE)
_HEX_RE = re.compile(r"^[0-9a-f]+$", re.IGNORECASE)


def looks_like_commit(text: str) -> bool:
    """Distinguish a Git commit hash from a calendar version.

    A bare run of hex digits is ambiguous: ``20240101`` is a plausible CalVer
    release and a plausible abbreviated hash. Requiring either the full
    40 characters or at least one ``a``–``f`` resolves it in favor of the
    interpretation that is almost always right.

    Parameters
    ----------
    text : str
        A version string.

    Returns
    -------
    bool
        Whether to treat it as a commit hash.

    Examples
    --------
    >>> looks_like_commit("a3f8c2d1b4e7f0291a3f8c2d1b4e7f0291a3f8c2")
    True
    >>> looks_like_commit("a3f8c2d")
    True

    A CalVer release is not mistaken for a hash, even though it is valid hex:

    >>> looks_like_commit("20240101")
    False

    Nor is anything too short to be one, or not hex at all:

    >>> looks_like_commit("1.2.0")
    False
    >>> looks_like_commit("abc")
    False
    """
    if not _HEX_RE.match(text):
        return False
    if len(text) == 40:
        return True
    return 7 <= len(text) < 40 and any(char in "abcdefABCDEF" for char in text)


def normalize_version(raw: Any) -> str | None:
    """Normalize a version so equivalent spellings compare equal.

    Parameters
    ----------
    raw : Any
        A version string or number.

    Returns
    -------
    str or None
        A comparison key, prefixed ``sha:`` for commit hashes, or ``None`` if
        empty.

    Notes
    -----
    Trailing zero components are dropped because they carry no information:
    ``1.2.0`` and ``1.2`` name one release. Pre-release and build suffixes are
    kept, lower-cased with punctuation removed, because they *do* distinguish
    releases.

    Examples
    --------
    A leading ``v``, a trailing ``.0`` and R's dash are all cosmetic:

    >>> normalize_version("1.2.0") == normalize_version("v1.2.0")
    True
    >>> normalize_version("1.2.0") == normalize_version("1.2")
    True
    >>> normalize_version("1.2-3") == normalize_version("1.2.3")
    True

    Genuinely different releases stay different — note that ``1.20`` is not
    ``1.2``, which is the trap behind an unquoted YAML version:

    >>> normalize_version("1.2") == normalize_version("1.20")
    False
    >>> normalize_version("1.0.0") == normalize_version("1.0.0-rc1")
    False

    A short commit hash matches the full hash it abbreviates:

    >>> full = "a3f8c2d1b4e7f0291a3f8c2d1b4e7f0291a3f8c2"
    >>> normalize_version(full) == normalize_version(full[:7])
    True
    >>> normalize_version(full)
    'sha:a3f8c2d'

    Empty input is absence:

    >>> normalize_version("") is None
    True
    """
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None
    if looks_like_commit(text):
        return f"sha:{text[:COMMIT_PREFIX_LENGTH].lower()}"
    match = _VERSION_RE.match(text)
    if not match:
        return normalize_text(text)
    numbers = [int(part) for part in re.split(r"[._-]", match.group(1))]
    while len(numbers) > 1 and numbers[-1] == 0:
        numbers.pop()
    suffix = re.sub(r"[^a-z0-9]", "", match.group(2).lower())
    joined = ".".join(str(number) for number in numbers)
    return f"{joined}-{suffix}" if suffix else joined
