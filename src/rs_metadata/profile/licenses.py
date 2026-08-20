"""License checks against the vendored SPDX list.

The SPDX list ships inside the package, so an identifier is resolved against
the real thing, including deprecations.

A license value must be an **SPDX license URL** or a **CreativeWork node**.

The first half is CodeMeta's own typing: ``license`` is *CreativeWork or URL*,
so a bare ``"Apache-2.0"`` expands to a relative IRI and stops naming anything.
The second half is this profile being stricter than CodeMeta, which permits any
URL — a bare link says where to read the license but not which one it is, so
nothing can map it to terms. An institutional license is still expressible, as
a ``CreativeWork`` carrying its name and URL; every message that relies on the
profile rule rather than on CodeMeta says so.
"""

from __future__ import annotations

import difflib

from ..diagnostics import Severity
from ..locate import Path as DocPath
from ..normalize import SPDX_OPERATORS, SPDX_URL_PREFIX, scalarize, spdx_identifier
from ..report import Diagnostic
from ..vocabulary import spdx_index, spdx_licenses
from .context import ProfileContext

__all__ = ["check_licenses", "spdx_suggestion"]

_SPDX_URL_PREFIXES = ("https://spdx.org/licenses/", "http://spdx.org/licenses/")


def spdx_suggestion(candidate: str) -> str:
    """Suggest SPDX identifiers close to what the author wrote.

    Parameters
    ----------
    candidate : str
        The unrecognized license string.

    Returns
    -------
    str
        A "did you mean" sentence naming up to three candidates, or generic
        advice when nothing is close enough to be worth guessing at.

    Examples
    --------
    A near miss gets concrete suggestions. The exact set depends on the
    vendored SPDX list, so only the leading candidate is asserted here:

    >>> suggestion = spdx_suggestion("Apache-2.0-only")
    >>> suggestion.startswith("Did you mean https://spdx.org/licenses/Apache-2.0")
    True

    Something with no close match gets the general advice instead of a bad
    guess:

    >>> spdx_suggestion("Our institutional license").startswith("Use an SPDX")
    True
    """
    close = difflib.get_close_matches(
        candidate.casefold(), sorted(spdx_index()), n=3, cutoff=0.7
    )
    if close:
        canonical = [spdx_index()[item] for item in close]
        options = ", ".join(f"{SPDX_URL_PREFIX}{item}" for item in canonical)
        return f"Did you mean {options}?"
    return (
        f"Use an SPDX identifier URL, for example {SPDX_URL_PREFIX}Apache-2.0. "
        f"The full list is at https://spdx.org/licenses/."
    )


def check_licenses(ctx: ProfileContext) -> list[Diagnostic]:
    """Check every license value against the SPDX list.

    Parameters
    ----------
    ctx : ProfileContext
        The record under validation.

    Returns
    -------
    list of Diagnostic
        Findings about license values.

    Notes
    -----
    CodeMeta types ``license`` as **CreativeWork or URL**, so a bare identifier
    is not a conformant value: it expands to a relative IRI and no consumer can
    tell which license it names. This check owns that error rather than
    :mod:`.types`, because it can resolve the text against the SPDX list and
    name the exact URL to use.

    Requiring an *SPDX* URL specifically is a profile rule, stricter than
    CodeMeta: a bare link says where to read the license but not which one it
    is. The message says so, so nobody hunts for a spec line that does not
    exist.

    Examples
    --------
    The canonical form produces nothing:

    >>> ctx = ProfileContext.for_document(
    ...     {"license": "https://spdx.org/licenses/Apache-2.0"}
    ... )
    >>> check_licenses(ctx)
    []

    A bare identifier is understood, and the exact URL is named:

    >>> ctx = ProfileContext.for_document({"license": "Apache-2.0"})
    >>> finding = check_licenses(ctx)[0]
    >>> finding.code, finding.severity.value
    ('profile.invalid-type', 'error')
    >>> finding.suggestion
    'Use "https://spdx.org/licenses/Apache-2.0".'

    An SPDX expression cannot survive as one value, so the array form is named:

    >>> ctx = ProfileContext.for_document({"license": "MIT OR Apache-2.0"})
    >>> "List each license as its own SPDX URL" in check_licenses(ctx)[0].suggestion
    True

    A URL that claims SPDX but names no real license is an error:

    >>> ctx = ProfileContext.for_document(
    ...     {"license": "https://spdx.org/licenses/Apache-2.0-only"}
    ... )
    >>> [(d.code, d.severity.value) for d in check_licenses(ctx)]
    [('profile.invalid-value', 'error')]

    So is a URL that identifies no license at all:

    >>> ctx = ProfileContext.for_document(
    ...     {"license": "https://opensource.org/licenses/MIT"}
    ... )
    >>> [(d.code, d.severity.value) for d in check_licenses(ctx)]
    [('profile.invalid-value', 'error')]

    A ``CreativeWork`` is how a custom or institutional license is expressed:

    >>> ctx = ProfileContext.for_document({"license": {
    ...     "@type": "CreativeWork", "name": "LUMC internal license",
    ...     "url": "https://example.org/lumc-license",
    ... }})
    >>> check_licenses(ctx)
    []

    but one with nothing to resolve earns a warning:

    >>> ctx = ProfileContext.for_document({"license": {
    ...     "@type": "CreativeWork", "name": "LUMC internal license"}})
    >>> [(d.code, d.severity.value) for d in check_licenses(ctx)]
    [('profile.invalid-value', 'warning')]

    A deprecated identifier is flagged separately:

    >>> ctx = ProfileContext.for_document(
    ...     {"license": "https://spdx.org/licenses/GPL-3.0"}
    ... )
    >>> [d.code for d in check_licenses(ctx)]
    ['profile.deprecated-value']
    """
    licenses = spdx_licenses()["licenses"]
    diagnostics: list[Diagnostic] = []

    for value, path in ctx.values("license"):
        scalar = scalarize(value)
        if scalar is None:
            continue
        identifier = spdx_identifier(value)
        is_url = scalar.lower().startswith(("http://", "https://"))
        is_spdx_url = scalar.lower().startswith(_SPDX_URL_PREFIXES)

        is_node = isinstance(value, dict)

        if identifier is None:
            if is_spdx_url:
                diagnostics.append(
                    ctx.diagnostic(
                        "profile.invalid-value",
                        Severity.ERROR,
                        f"{ctx.file}: the license URL {scalar!r} is not an SPDX "
                        f"identifier. The SPDX license list has no such entry.",
                        path=path,
                        value=scalar,
                        suggestion=spdx_suggestion(scalar.rsplit("/", 1)[-1]),
                        prop="license",
                    )
                )
            elif is_node:
                # A CreativeWork is a conformant license value; it just has to
                # point somewhere, or a consumer learns only that a license
                # exists.
                if not (value.get("url") or value.get("@id")):
                    diagnostics.append(
                        ctx.diagnostic(
                            "profile.invalid-value",
                            Severity.WARNING,
                            f"{ctx.file}: the license node names "
                            f"{scalar!r} but carries no url or @id, so there is "
                            f"nothing for a consumer to resolve.",
                            path=path,
                            value=scalar,
                            suggestion=(
                                'Add "url" pointing at the license text, or '
                                '"@id" with its SPDX URL.'
                            ),
                            prop="license",
                        )
                    )
            elif not is_url:
                diagnostics.append(_bare_license_error(ctx, scalar, path))
            else:
                diagnostics.append(_plain_url_error(ctx, scalar, path))
            continue

        if not is_url and not is_node:
            # A recognized identifier written bare: the value is still not a
            # CreativeWork or a URL, so it is the same type violation, but we
            # know exactly which URL was meant.
            diagnostics.append(_bare_license_error(ctx, scalar, path, identifier))
            continue

        if licenses.get(identifier, {}).get("deprecated"):
            diagnostics.append(
                ctx.diagnostic(
                    "profile.deprecated-value",
                    Severity.WARNING,
                    f"{ctx.file}: SPDX has deprecated the license identifier "
                    f"{identifier!r}.",
                    path=path,
                    value=scalar,
                    suggestion=(
                        "Replace it with its current SPDX identifier; see "
                        "https://spdx.org/licenses/."
                    ),
                    prop="license",
                )
            )
        if not is_url:
            # A node naming a license SPDX already has an identifier for. The
            # node is conformant, but the SPDX URL says the same thing in the
            # form registries can resolve, so it is worth a nudge rather than
            # an error.
            diagnostics.append(
                ctx.diagnostic(
                    "profile.non-canonical-value",
                    Severity.WARNING,
                    f"{ctx.file}: the license is given as a node naming "
                    f"{scalar!r}, which SPDX already has an identifier for. "
                    f"The SPDX URL carries the same meaning in a form "
                    f"registries resolve automatically.",
                    path=path,
                    value=scalar,
                    suggestion=f'Use "{SPDX_URL_PREFIX}{identifier}".',
                    prop="license",
                )
            )
    return diagnostics


def _bare_license_error(
    ctx: ProfileContext, scalar: str, path: DocPath, identifier: str | None = None
) -> Diagnostic:
    """Build the error for a license written as a bare string.

    A bare string is not a ``CreativeWork`` and not a URL, so JSON-LD expands
    it to a relative IRI. The remediation depends on what the string turned out
    to be: a known identifier has an exact URL, an SPDX expression needs the
    array form, and anything else needs a ``CreativeWork``.
    """
    if identifier is not None:
        fix = f'Use "{SPDX_URL_PREFIX}{identifier}".'
    elif _looks_like_expression(scalar):
        parts = [
            f'"{SPDX_URL_PREFIX}{spdx_index()[token.casefold()]}"'
            for token in scalar.replace("(", " ").replace(")", " ").split()
            if token.casefold() in spdx_index()
        ]
        listed = ", ".join(parts) or f'"{SPDX_URL_PREFIX}MIT"'
        fix = (
            f"List each license as its own SPDX URL: [{listed}]. CodeMeta has "
            f"no place for an SPDX expression, so the operator cannot be kept."
        )
    else:
        fix = (
            f"Use the SPDX URL if one applies, or a node: "
            f'{{"@type": "CreativeWork", "name": {scalar!r}, '
            f'"url": "https://example.org/license"}}. {spdx_suggestion(scalar)}'
        )
    return ctx.diagnostic(
        "profile.invalid-type",
        Severity.ERROR,
        f"{ctx.file}: the license {scalar!r} is a bare string. CodeMeta types "
        f"license as CreativeWork or URL, so this expands to a relative IRI "
        f"and no consumer can tell which license it names.",
        path=path,
        value=scalar,
        suggestion=fix,
        prop="license",
    )


def _plain_url_error(ctx: ProfileContext, scalar: str, path: DocPath) -> Diagnostic:
    """Build the error for a license URL that is not an SPDX identifier.

    A URL is a conformant CodeMeta value, so this is a *profile* rule: a bare
    link says where to read the license but not which one it is, and nothing
    can map it to terms. Saying so is the point of the message.
    """
    return ctx.diagnostic(
        "profile.invalid-value",
        Severity.ERROR,
        f"{ctx.file}: the license URL {scalar!r} is not an SPDX identifier, so "
        f"registries cannot determine the license terms from it. CodeMeta "
        f"permits any URL here; this profile requires one that identifies the "
        f"license.",
        path=path,
        value=scalar,
        suggestion=(
            f"Use the SPDX URL if one applies, or keep this link inside a node "
            f'that names the license: {{"@type": "CreativeWork", "name": '
            f'"<license name>", "url": {scalar!r}}}.'
        ),
        prop="license",
    )


def _looks_like_expression(text: str) -> bool:
    """Whether a string is an SPDX license expression rather than one license.

    Examples
    --------
    >>> _looks_like_expression("MIT OR Apache-2.0")
    True
    >>> _looks_like_expression("GPL-2.0-only WITH Classpath-exception-2.0")
    True
    >>> _looks_like_expression("Apache-2.0")
    False
    """
    return any(
        token.upper() in SPDX_OPERATORS for token in text.replace("(", " ").split()
    )
