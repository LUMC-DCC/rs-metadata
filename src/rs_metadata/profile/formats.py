"""Lexical form of literal values, for the datatypes CodeMeta declares.

:mod:`.types` answers whether a value is the right *kind* of thing — a node, a
URL, a literal. This module answers the other half: granted that a bare value
belongs here, is what was written actually a value of that datatype? It covers
dates, datetimes, numbers, integers, booleans and URLs, and lends
:func:`valid_url` to :mod:`.types` and :mod:`.identifiers` so that every place
expecting a URL agrees on what one is.

Which properties are literal-typed is derived, like everything else, from the
vendored table. The lexical rules themselves are not: schema.org states them
only in prose ("a date value in ISO 8601 date format") and ships no
machine-readable form, so there is nothing to derive. What is implemented here
is the standard each datatype name denotes — a fixed algorithm for six
datatypes, not a per-property table that could drift.

Validity is decided by *construction*, not by pattern. This is not a detail:

* the vendored CFF schema's date pattern accepts ``2026-02-30``;
* this profile's own former pattern accepted it too, and additionally rejected
  ``2026``, which is a valid ISO 8601 date.

A regex over digits cannot know that February has 28 days. Building a
:class:`datetime.datetime` can, so that is what decides.
"""

from __future__ import annotations

import difflib
import math
import re
from collections.abc import Callable
from datetime import datetime
from typing import Any
from urllib.parse import urlsplit

from ..diagnostics import Severity
from ..locate import Path as DocPath
from ..report import Diagnostic
from ..vocabulary import type_entry
from .context import ProfileContext

__all__ = [
    "check_formats",
    "format_checked",
    "reports_on",
    "url_problem",
    "valid_literal",
    "valid_url",
]

#: Schemes whose syntax requires a host. ``mailto:`` and ``urn:`` do not, and
#: ``file:`` conventionally has an empty authority (``file:///path``), so
#: demanding a host for any of them would reject correct URLs.
_AUTHORITY_SCHEMES = frozenset(
    {"http", "https", "ftp", "ftps", "git", "ssh", "svn", "hg", "bzr"}
)

#: Schemes known to be real. A scheme in here is never second-guessed. The
#: point is not to be exhaustive — an unknown scheme is still allowed — but to
#: stop a real one being mistaken for a typo of a similar-looking web scheme,
#: which is why ``ftps`` matters here.
_KNOWN_SCHEMES = _AUTHORITY_SCHEMES | {
    "file",
    "mailto",
    "urn",
    "doi",
    "tel",
    "news",
    "data",
    "ark",
    "hdl",
    "swh",
}

_SCHEME_SHAPE = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.\-]*$")

#: The web schemes a mistyped one is measured against. Kept to these two: a
#: near-miss of ``https`` is a typo, whereas an unfamiliar scheme like ``urn``
#: or ``swh`` is somebody using a perfectly real identifier we should not
#: second-guess.
_WEB_SCHEMES = ("http", "https")


def url_problem(text: str) -> str | None:
    """What is wrong with a URL, phrased for the reader, or ``None``.

    Parameters
    ----------
    text : str
        The value as written.

    Returns
    -------
    str or None
        A phrase completing "... but ", or ``None`` when the URL is well formed.

    Notes
    -----
    Deliberately permissive about *which* scheme is used. ``git://``,
    ``ssh://`` and ``mailto:`` are all legitimate, and rejecting an unfamiliar
    scheme would be a false alarm about a real identifier. Only a near-miss of
    ``http``/``https`` is treated as a mistake, because nothing else explains
    it.

    Examples
    --------
    A well-formed URL has no problem:

    >>> url_problem("https://github.com/lumc/tool") is None
    True

    Non-web schemes are left alone:

    >>> url_problem("git+https://github.com/x") is None
    True
    >>> url_problem("mailto:someone@example.org") is None
    True

    A relative reference is not a URL at all:

    >>> url_problem("github.com/lumc/tool")
    'it has no scheme, so nothing can resolve it'

    Whitespace is always a mistake:

    >>> url_problem("https://github.com/a b")
    'it contains whitespace'

    A scheme that needs a host and has none:

    >>> url_problem("https://")
    'it has no host'

    ``file:`` conventionally has an empty authority, so it is not missing a
    host:

    >>> url_problem("file:///data/reference.fa") is None
    True

    And the typos a scheme check exists to catch:

    >>> url_problem("htp://github.com/lumc/tool")
    "its scheme 'htp' is not a real scheme; did you mean 'http'?"
    >>> url_problem("hpts://github.com/x")
    "its scheme 'hpts' is not a real scheme; did you mean 'https'?"

    A real scheme that merely resembles one is left alone:

    >>> url_problem("ftps://files.example.org/x") is None
    True
    """
    if any(character.isspace() for character in text):
        return "it contains whitespace"
    parts = urlsplit(text)
    if not parts.scheme:
        return "it has no scheme, so nothing can resolve it"
    if not _SCHEME_SHAPE.match(parts.scheme):
        return f"{parts.scheme!r} is not a valid URL scheme"

    scheme = parts.scheme.lower()
    # A composite like git+https is real if any component is. Only a scheme
    # that resembles nothing real is a candidate for being a typo.
    if not set(scheme.split("+")) & _KNOWN_SCHEMES:
        close = difflib.get_close_matches(scheme, _WEB_SCHEMES, n=1, cutoff=0.6)
        if close:
            return (
                f"its scheme {parts.scheme!r} is not a real scheme; "
                f"did you mean {close[0]!r}?"
            )
    if scheme in _AUTHORITY_SCHEMES and not parts.netloc:
        return "it has no host"
    return None


def valid_url(text: str) -> bool:
    """Whether a string is a usable absolute URL.

    Examples
    --------
    >>> valid_url("https://github.com/lumc/tool")
    True
    >>> valid_url("htp://github.com/x"), valid_url("https://")
    (False, False)
    """
    return url_problem(text) is None


#: ISO 8601 calendar dates, including the reduced precisions the standard
#: allows. Shape only — the calendar itself is checked by ``strptime``.
_DATE_SHAPE = re.compile(r"^\d{4}(-\d{2}(-\d{2})?)?$")
_DATE_FORMATS = {4: "%Y", 7: "%Y-%m", 10: "%Y-%m-%d"}


def _valid_date(text: str) -> bool:
    """Whether a string is an ISO 8601 calendar date that exists.

    Examples
    --------
    >>> _valid_date("2026-06-01")
    True

    Reduced precision is valid ISO 8601, so it is accepted:

    >>> _valid_date("2026"), _valid_date("2026-06")
    (True, True)

    A date that never happened is not, however well-formed it looks:

    >>> _valid_date("2026-02-30"), _valid_date("2025-02-29")
    (False, False)
    >>> _valid_date("2026-13-01")
    False

    Neither is an ambiguous or non-ISO spelling:

    >>> _valid_date("01/06/2026"), _valid_date("June 1, 2026")
    (False, False)

    ISO 8601 requires zero padding:

    >>> _valid_date("2026-6-1")
    False
    """
    if not _DATE_SHAPE.match(text):
        return False
    fmt = _DATE_FORMATS.get(len(text))
    if fmt is None:  # pragma: no cover - unreachable given the shape
        return False
    try:
        datetime.strptime(text, fmt)
    except ValueError:
        return False
    return True


def _valid_datetime(text: str) -> bool:
    """Whether a string is an ISO 8601 date with a time part.

    Examples
    --------
    >>> _valid_datetime("2026-06-01T10:30:00")
    True
    >>> _valid_datetime("2026-06-01T10:30:00+02:00")
    True

    A trailing ``Z`` is accepted on every supported Python, which
    ``datetime.fromisoformat`` itself only learned in 3.11:

    >>> _valid_datetime("2026-06-01T10:30:00Z")
    True

    >>> _valid_datetime("2026-06-01T25:00:00")
    False
    """
    candidate = f"{text[:-1]}+00:00" if text.endswith("Z") else text
    try:
        datetime.fromisoformat(candidate)
    except ValueError:
        return False
    return True


def _valid_number(text: str) -> bool:
    """Whether a string spells a finite number.

    Examples
    --------
    >>> _valid_number("2026"), _valid_number("1.5"), _valid_number("-3")
    (True, True, True)
    >>> _valid_number("two thousand"), _valid_number("nan"), _valid_number("inf")
    (False, False, False)
    """
    try:
        value = float(text)
    except ValueError:
        return False
    return math.isfinite(value)


def _valid_integer(text: str) -> bool:
    """Whether a string spells a whole number.

    Examples
    --------
    >>> _valid_integer("3"), _valid_integer("-3")
    (True, True)
    >>> _valid_integer("3.5"), _valid_integer("third")
    (False, False)
    """
    try:
        int(text)
    except ValueError:
        return False
    return True


def _valid_boolean(text: str) -> bool:
    """Whether a string spells a boolean.

    Examples
    --------
    >>> _valid_boolean("true"), _valid_boolean("False")
    (True, True)
    >>> _valid_boolean("yes"), _valid_boolean("1")
    (False, False)
    """
    return text.casefold() in {"true", "false"}


#: Deliberately loose. RFC 5322 permits quoted local parts, comments and
#: bracketed address literals, and a regex that chases all of it rejects real
#: addresses far more often than it catches bad ones. This asks only what a
#: typo actually violates: one ``@``, something either side, a dotted domain,
#: no spaces.
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s.]+$")


def _valid_email(text: str) -> bool:
    """Whether a string is plausibly an email address.

    Examples
    --------
    >>> _valid_email("jane.doe@lumc.nl"), _valid_email("j+tag@sub.example.org")
    (True, True)

    The mistakes that actually happen:

    >>> _valid_email("not an email"), _valid_email("jane@@example.org")
    (False, False)
    >>> _valid_email("jane.doe.lumc.nl"), _valid_email("jane@localhost")
    (False, False)

    A ``mailto:`` prefix is tolerated, since it is common and unambiguous:

    >>> _valid_email("mailto:jane.doe@lumc.nl")
    True
    """
    return bool(_EMAIL.match(text.removeprefix("mailto:").strip()))


#: Properties CodeMeta types as ``Text`` that nonetheless have a real form.
#: This is a profile rule: CodeMeta permits any text, but a malformed address
#: helps nobody and is nearly always a typo rather than a choice.
_TEXT_FORMATS: dict[str, tuple[Callable[[str], bool], str]] = {
    "email": (_valid_email, "an email address such as jane.doe@lumc.nl"),
}

#: The datatypes this module can check, and how. A CodeMeta range naming
#: anything absent from here is not format-checked at all.
CHECKERS: dict[str, Callable[[str], bool]] = {
    "Date": _valid_date,
    "Datetime": _valid_datetime,
    "DateTime": _valid_datetime,
    "Number": _valid_number,
    "Integer": _valid_integer,
    "Boolean": _valid_boolean,
}

#: What each datatype should look like, for the message. Prose, because the
#: reader needs to know what to write, not what the regex was.
_EXPECTED: dict[str, str] = {
    "Date": "an ISO 8601 date such as 2026-06-01",
    "Datetime": "an ISO 8601 date and time such as 2026-06-01T10:30:00Z",
    "DateTime": "an ISO 8601 date and time such as 2026-06-01T10:30:00Z",
    "Number": "a number",
    "Integer": "a whole number",
    "Boolean": "true or false",
}


def format_checked(name: str) -> bool:
    """Whether a property's values have a checkable lexical form.

    Parameters
    ----------
    name : str
        CodeMeta property name.

    Returns
    -------
    bool
        ``True`` only when every type in the property's range is a datatype
        this module knows how to check.

    Notes
    -----
    A range containing ``Text`` is never checked: ``Text`` accepts anything, so
    there is no form to be wrong. A range naming a node type belongs to
    :mod:`.types`, which decides kind.

    Examples
    --------
    >>> format_checked("datePublished"), format_checked("copyrightYear")
    (True, True)

    ``version`` is ``Number or Text``, and the ``Text`` branch means ``1.0.0``
    is a perfectly good value:

    >>> format_checked("version")
    False

    Node- and URL-typed properties are :mod:`.types`' business:

    >>> format_checked("author"), format_checked("codeRepository")
    (False, False)
    """
    if name in _TEXT_FORMATS:
        return True
    entry = type_entry(name)
    if entry is None:
        return False
    declared = set(entry["range"])
    return bool(declared) and declared <= set(CHECKERS)


def valid_literal(value: Any, allowed: list[str]) -> bool:
    """Whether a value is a well-formed literal of any type in a range.

    Parameters
    ----------
    value : Any
        The value as written — a JSON string, number, or boolean.
    allowed : list of str
        The datatypes the property permits.

    Returns
    -------
    bool
        Whether the value satisfies at least one of them.

    Notes
    -----
    A year written as ``"2026"`` is accepted where a ``Number`` is expected.
    JSON-LD treats a quoted literal and a bare one alike, and generators differ
    on which they emit, so rejecting the quoted form would be a false alarm
    about something no consumer would notice.

    Examples
    --------
    >>> valid_literal("2026-06-01", ["Date"])
    True
    >>> valid_literal("2026-02-30", ["Date"])
    False

    A range offering two datatypes accepts either:

    >>> valid_literal("2026-06-01", ["Date", "Datetime"])
    True
    >>> valid_literal("2026-06-01T10:30:00", ["Date", "Datetime"])
    True

    Numbers are accepted quoted or bare:

    >>> valid_literal(2026, ["Number"]), valid_literal("2026", ["Number"])
    (True, True)
    >>> valid_literal(True, ["Boolean"]), valid_literal("true", ["Boolean"])
    (True, True)

    A node where a literal belongs is not a literal at all:

    >>> valid_literal({"@type": "Organization"}, ["Date"])
    False
    """
    if isinstance(value, bool):
        return "Boolean" in allowed
    if isinstance(value, (int, float)):
        return bool({"Number", "Integer"}.intersection(allowed))
    if not isinstance(value, str):
        return False
    text = value.strip()
    if not text:
        return False
    return any(CHECKERS[name](text) for name in allowed if name in CHECKERS)


def reports_on(name: str, value: Any) -> bool:
    """Whether :func:`check_formats` will report on this value.

    Used by :mod:`.schema_checks` to stay quiet where a better message is
    coming, so one mistake produces one diagnostic. The schema's pattern can
    only say the value did not match it; this module says what a date should
    look like, and does not mistake ``2026-02-30`` for one.

    Examples
    --------
    >>> reports_on("dateCreated", "01/06/2026")
    True
    >>> reports_on("datePublished", "2026-06-01")
    False

    A property with no checkable form is never claimed:

    >>> reports_on("version", "1.0.0-rc1")
    False
    """
    if not format_checked(name):
        return False
    items = value if isinstance(value, list) else [value]
    if name in _TEXT_FORMATS:
        checker, _ = _TEXT_FORMATS[name]
        return any(not (isinstance(i, str) and checker(i)) for i in items)
    entry = type_entry(name)
    if entry is None:  # pragma: no cover - guarded by format_checked
        return False
    allowed = list(entry["range"])
    return any(not valid_literal(item, allowed) for item in items)


def check_formats(ctx: ProfileContext) -> list[Diagnostic]:
    """Check that literal values are well-formed for their declared datatype.

    Parameters
    ----------
    ctx : ProfileContext
        The record under validation.

    Returns
    -------
    list of Diagnostic
        One error per malformed literal, naming the expected form.

    Examples
    --------
    A real date passes:

    >>> check_formats(ProfileContext.for_document({"datePublished": "2026-06-01"}))
    []

    A date that never happened does not, however well-formed it looks:

    >>> ctx = ProfileContext.for_document({"datePublished": "2026-02-30"})
    >>> finding = check_formats(ctx)[0]
    >>> finding.code, finding.severity.value
    ('profile.invalid-value', 'error')
    >>> "ISO 8601 date such as 2026-06-01" in finding.suggestion
    True

    Neither does an ambiguous spelling, which is the mistake worth catching —
    nothing downstream can tell 1 June from 6 January:

    >>> [d.severity.value for d in check_formats(
    ...     ProfileContext.for_document({"dateCreated": "01/06/2026"}))]
    ['error']

    Reduced precision is valid ISO 8601 and passes:

    >>> check_formats(ProfileContext.for_document({"datePublished": "2026"}))
    []

    Properties whose range includes ``Text`` are not format-checked, so a
    version string is left alone:

    >>> check_formats(ProfileContext.for_document({"version": "1.0.0-rc1"}))
    []

    Nested nodes are checked too, which is where CodeMeta puts ``startDate``:

    >>> ctx = ProfileContext.for_document({"author": [{
    ...     "@type": "Role", "startDate": "not-a-date"}]})
    >>> [d.property for d in check_formats(ctx)]
    ['startDate']
    """
    diagnostics: list[Diagnostic] = []
    for name in ctx.document:
        if name.startswith("@"):
            continue
        for value, path in ctx.values(name):
            if format_checked(name):
                diagnostics.extend(_check_value(ctx, name, value, path))
            elif isinstance(value, dict):
                diagnostics.extend(_check_node(ctx, value, path))
    return diagnostics


def _check_node(
    ctx: ProfileContext, node: dict[str, Any], path: DocPath
) -> list[Diagnostic]:
    """Check the literal-typed properties of a nested node."""
    diagnostics: list[Diagnostic] = []
    for key, item, item_path in ctx.node_values(node, path):
        if format_checked(key):
            diagnostics.extend(_check_value(ctx, key, item, item_path))
    return diagnostics


def _check_value(
    ctx: ProfileContext, name: str, value: Any, path: DocPath
) -> list[Diagnostic]:
    """Report one value whose written form is not valid for its datatype."""
    if name in _TEXT_FORMATS:
        checker, expected = _TEXT_FORMATS[name]
        if isinstance(value, str) and checker(value):
            return []
        if not isinstance(value, (str, dict, list)):
            return []
    else:
        entry = type_entry(name)
        if entry is None:  # pragma: no cover - guarded by format_checked
            return []
        allowed = list(entry["range"])
        if valid_literal(value, allowed):
            return []
        expected = " or ".join(_EXPECTED[t] for t in allowed if t in _EXPECTED)
    if isinstance(value, dict):
        given = f"a {value.get('@type', 'node')} node"
        shown = None
    elif isinstance(value, list):
        given = "an array"
        shown = None
    else:
        given = repr(value)
        shown = value if isinstance(value, (str, int, float, bool)) else None

    return [
        ctx.diagnostic(
            "profile.invalid-value",
            Severity.ERROR,
            f"{ctx.file}: {name} must be {expected}, but {given} was given. "
            f"A value that is not well formed for its datatype cannot be "
            f"compared, sorted or resolved by anything that reads the record.",
            path=path,
            value=shown,
            suggestion=f"Write it as {expected}.",
            prop=name,
        )
    ]
