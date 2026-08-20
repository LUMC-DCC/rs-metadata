"""Detection of template values that were never filled in.

A placeholder is worse than a missing field. A missing field is visibly
absent; a placeholder asserts a specific identifier that does not exist, and
registries harvest it as though it did — attributing software to an ORCID
nobody holds, or pointing a citation at a DOI that resolves to nothing.

Every pattern here appears verbatim in a published template or in this
project's own examples, which is exactly why people leave them behind.
"""

from __future__ import annotations

import re

from ..adapters.codemeta import FEATURE_LIST, any_feature_list_key
from ..diagnostics import Severity
from ..locate import Path as DocPath
from ..normalize import extract_doi, extract_orcid, scalarize
from ..report import Diagnostic
from ..vocabulary import agent_properties
from ..vocabulary import placeholders as placeholders_data
from .context import ProfileContext

__all__ = [
    "PLACEHOLDER_DOI_PREFIX",
    "PLACEHOLDER_HOSTS",
    "PLACEHOLDER_ORCID",
    "check_placeholders",
    "has_placeholder_host",
]

_DATA = placeholders_data()

#: The all-zero ORCID used in author examples everywhere. Its check digit is
#: wrong, but that is not the useful thing to tell someone about it.
PLACEHOLDER_ORCID: str = _DATA["orcid"]

#: Reserved by RFC 2606 for documentation. These can never be a real
#: repository, so they are errors.
PLACEHOLDER_HOSTS = frozenset(_DATA["hosts"])

#: The DOI prefix conventionally used in examples. 10.0000 is not an assigned
#: registrant prefix.
PLACEHOLDER_DOI_PREFIX: str = _DATA["doiPrefix"]

#: The repository URL used in examples. Reported only as a warning: unlike a
#: reserved domain, a real account could in principle be named `example`, so
#: this is a strong hint rather than proof.
_PLACEHOLDER_REPO_RE = re.compile(
    _DATA["patterns"]["repository"]["regex"], re.IGNORECASE
)

#: EDAM's zero terms, used in examples to stand for a real operation or topic.
_PLACEHOLDER_EDAM = re.compile(_DATA["patterns"]["edamTerm"]["regex"], re.IGNORECASE)

_URL_PROPERTIES = ("identifier", "codeRepository", "url", "issueTracker")


def has_placeholder_host(value: str) -> bool:
    """Whether a URL points at an RFC 2606 reserved example domain.

    Parameters
    ----------
    value : str
        A URL.

    Returns
    -------
    bool
        Whether its host is a reserved example domain.

    Examples
    --------
    >>> has_placeholder_host("https://example.com/mytool")
    True
    >>> has_placeholder_host("https://www.example.org/mytool")
    True

    A real host is not a placeholder, even if the path mentions examples:

    >>> has_placeholder_host("https://github.com/org/example-tool")
    False

    Nor is a domain that merely contains the word:

    >>> has_placeholder_host("https://example.lumc.nl/tool")
    False
    """
    match = re.match(r"^https?://([^/]+)", value, re.IGNORECASE)
    if not match:
        return False
    host = match.group(1).casefold().removeprefix("www.")
    return host in PLACEHOLDER_HOSTS


def check_placeholders(ctx: ProfileContext) -> list[Diagnostic]:
    """Report template values that were copied but never replaced.

    Parameters
    ----------
    ctx : ProfileContext
        The record under validation.

    Returns
    -------
    list of Diagnostic
        One finding per placeholder found.

    Notes
    -----
    Severity is calibrated to how certain the detection is. A reserved
    ``example.com`` host, a ``10.0000/`` DOI, the all-zero ORCID and EDAM's
    zero terms cannot be real, so they are **errors**. A
    ``github.com/example/`` repository is only a **warning**, because an
    account could in principle really be named ``example``.

    Examples
    --------
    The guide's placeholder DOI cannot be real:

    >>> ctx = ProfileContext.for_document(
    ...     {"identifier": "https://doi.org/10.0000/example.mytool.1"}
    ... )
    >>> [(d.code, d.severity.value) for d in check_placeholders(ctx)]
    [('profile.placeholder-value', 'error')]

    Nor can a reserved example domain:

    >>> ctx = ProfileContext.for_document(
    ...     {"codeRepository": "https://example.com/mytool"}
    ... )
    >>> [d.severity.value for d in check_placeholders(ctx)]
    ['error']

    A `github.com/example/` repository is a hint, not proof:

    >>> ctx = ProfileContext.for_document(
    ...     {"codeRepository": "https://github.com/example/mytool"}
    ... )
    >>> [d.severity.value for d in check_placeholders(ctx)]
    ['warning']

    The all-zero ORCID is caught wherever an agent appears:

    >>> ctx = ProfileContext.for_document({
    ...     "author": [{"@id": "https://orcid.org/0000-0000-0000-0000",
    ...                 "familyName": "Doe"}]
    ... })
    >>> [d.code for d in check_placeholders(ctx)]
    ['profile.placeholder-value']

    So is EDAM's zero operation, even when the property is misspelled — the
    reader should see every problem at once rather than a second round after
    renaming it:

    >>> ctx = ProfileContext.for_document(
    ...     {"featureList": ["http://edamontology.org/operation_0000"]}
    ... )
    >>> [d.code for d in check_placeholders(ctx)]
    ['profile.placeholder-value']

    Real values produce nothing:

    >>> ctx = ProfileContext.for_document({
    ...     "identifier": "https://doi.org/10.5281/zenodo.0000000",
    ...     "codeRepository": "https://github.com/lumc/rs-metadata",
    ... })
    >>> check_placeholders(ctx)
    []
    """
    diagnostics: list[Diagnostic] = []

    for prop in _URL_PROPERTIES:
        for value, path in ctx.values(prop):
            scalar = scalarize(value)
            if scalar is None:
                continue
            doi = extract_doi(scalar)
            if doi and doi.startswith(PLACEHOLDER_DOI_PREFIX):
                diagnostics.append(_placeholder(ctx, prop, path, scalar, "DOI"))
            elif has_placeholder_host(scalar):
                diagnostics.append(_placeholder(ctx, prop, path, scalar, "URL"))
            elif _PLACEHOLDER_REPO_RE.match(scalar):
                diagnostics.append(
                    _placeholder(
                        ctx, prop, path, scalar, "repository URL", Severity.WARNING
                    )
                )

    for prop in agent_properties():
        for value, path in ctx.values(prop):
            if not isinstance(value, dict):
                continue
            if extract_orcid(value.get("@id")) == PLACEHOLDER_ORCID:
                diagnostics.append(
                    _placeholder(
                        ctx, prop, (*path, "@id"), str(value.get("@id")), "ORCID"
                    )
                )

    key = any_feature_list_key(ctx.document)
    for prop in ([key] if key else []) + ["applicationSubCategory"]:
        for value, path in ctx.values(prop):
            scalar = scalarize(value)
            if scalar and _PLACEHOLDER_EDAM.match(scalar):
                diagnostics.append(
                    _placeholder(
                        ctx,
                        FEATURE_LIST if prop == key else prop,
                        path,
                        scalar,
                        "EDAM term",
                    )
                )

    return diagnostics


def _placeholder(
    ctx: ProfileContext,
    prop: str,
    path: DocPath,
    value: str,
    kind: str,
    severity: Severity = Severity.ERROR,
) -> Diagnostic:
    """Build a placeholder diagnostic naming the kind of value involved."""
    return ctx.diagnostic(
        "profile.placeholder-value",
        severity,
        f"{ctx.file}: the {kind} {value!r} is a placeholder from the "
        f"documentation examples and does not identify anything real.",
        path=path,
        value=value,
        suggestion=f"Replace it with this software's actual {kind}.",
        prop=prop,
    )
