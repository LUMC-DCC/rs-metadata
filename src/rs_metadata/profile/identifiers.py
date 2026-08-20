"""Checks on people, organizations and persistent identifiers.

ORCID and ROR both carry check digits, so a mistyped identifier is an
**error** without asking whether the person or institution exists: the
string cannot be a valid identifier either way.
"""

from __future__ import annotations

from typing import Any

from ..diagnostics import Severity
from ..locate import Path as DocPath
from ..normalize import (
    as_list,
    extract_doi,
    extract_orcid,
    extract_ror,
    orcid_checksum_valid,
    ror_checksum_valid,
)
from ..report import Diagnostic
from ..vocabulary import agent_properties
from .context import ProfileContext
from .formats import url_problem
from .placeholders import PLACEHOLDER_ORCID

__all__ = ["agent_label", "check_agents", "check_identifiers"]


def agent_label(value: dict[str, Any]) -> str:
    """Name an agent for use in a message.

    Parameters
    ----------
    value : dict
        A ``Person`` or ``Organization`` node.

    Returns
    -------
    str
        The best available human-readable name.

    Examples
    --------
    >>> agent_label({"givenName": "Jane", "familyName": "Doe"})
    'Jane Doe'
    >>> agent_label({"@type": "Organization", "name": "LUMC"})
    'LUMC'
    >>> agent_label({"familyName": "Doe"})
    'Doe'

    A node with nothing to name it still yields a usable phrase, so the
    message never reads "... given for ." :

    >>> agent_label({})
    'an unnamed agent'
    """
    parts = [value.get("givenName"), value.get("familyName")]
    joined = " ".join(str(part) for part in parts if part)
    return joined or str(value.get("name") or "an unnamed agent")


def check_identifiers(ctx: ProfileContext) -> list[Diagnostic]:
    """Check the record's persistent identifiers.

    Parameters
    ----------
    ctx : ProfileContext
        The record under validation.

    Returns
    -------
    list of Diagnostic
        At most one informational finding.

    Notes
    -----
    Only the absence of a DOI is reported, and only as **information**. It
    explicitly accepts a Git tag URL for software that will never
    be formally published, so a missing DOI cannot be an error — but a DOI is
    what makes a release citable, so it is worth saying.

    Examples
    --------
    A DOI in any spelling satisfies the check:

    >>> ctx = ProfileContext.for_document(
    ...     {"identifier": "https://doi.org/10.5281/zenodo.1"}
    ... )
    >>> check_identifiers(ctx)
    []

    A Git tag URL is accepted, with a note:

    >>> ctx = ProfileContext.for_document(
    ...     {"identifier": "https://github.com/org/tool/tree/v1.0.0"}
    ... )
    >>> [(d.code, d.severity.value) for d in check_identifiers(ctx)]
    [('recommendation.incomplete', 'info')]

    A DOI among several identifiers is enough:

    >>> ctx = ProfileContext.for_document({
    ...     "identifier": ["https://bio.tools/x", "10.5281/zenodo.1"]
    ... })
    >>> check_identifiers(ctx)
    []

    Absence is left to the mandatory-field check:

    >>> check_identifiers(ProfileContext.for_document({}))
    []
    """
    values = ctx.values("identifier")
    if not values:
        return []
    if any(extract_doi(value) for value, _ in values):
        return []
    return [
        ctx.diagnostic(
            "recommendation.incomplete",
            Severity.INFO,
            f"{ctx.file} records no DOI among its identifiers. A DOI is what "
            f"makes a specific release citable and is required by most "
            f"archives.",
            path=("identifier",),
            suggestion=(
                "Mint one by enabling the Zenodo–GitHub integration and "
                "publishing a release. A Git tag URL is acceptable for "
                "internal tools that will never be formally published."
            ),
            prop="identifier",
        )
    ]


def check_agents(ctx: ProfileContext) -> list[Diagnostic]:
    """Check authors, maintainers and their affiliations.

    Parameters
    ----------
    ctx : ProfileContext
        The record under validation.

    Returns
    -------
    list of Diagnostic
        Findings about agent identifiers.

    Notes
    -----
    Verifies ORCID and ROR check digits, detects one ORCID used for two
    different people, and notes authors and affiliations that carry no
    identifier at all.

    The all-zero placeholder ORCID is deliberately **not** reported here even
    though its check digit fails; :mod:`.placeholders` gives it a message that
    explains the real problem.

    Examples
    --------
    A well-formed author produces nothing:

    >>> author = {
    ...     "@type": "Person",
    ...     "@id": "https://orcid.org/0000-0002-1825-0097",
    ...     "givenName": "Josiah",
    ...     "familyName": "Carberry",
    ...     "affiliation": {
    ...         "@type": "Organization",
    ...         "@id": "https://ror.org/05xvt9f17",
    ...         "name": "Leiden University Medical Center",
    ...     },
    ... }
    >>> check_agents(ProfileContext.for_document({"author": [author]}))
    []

    A mistyped ORCID fails its check digit, and that is an error:

    >>> broken = dict(author, **{"@id": "https://orcid.org/0000-0002-1825-0098"})
    >>> finding = check_agents(ProfileContext.for_document({"author": [broken]}))[0]
    >>> finding.code, finding.severity.value
    ('profile.invalid-value', 'error')
    >>> "check digit" in finding.message
    True

    So does a mistyped ROR:

    >>> bad_ror = dict(author)
    >>> bad_ror["affiliation"] = dict(author["affiliation"],
    ...                               **{"@id": "https://ror.org/05xvt9f18"})
    >>> ctx = ProfileContext.for_document({"author": [bad_ror]})
    >>> [d.code for d in check_agents(ctx)]
    ['profile.invalid-value']

    One ORCID for two people is a warning:

    >>> other = dict(author, givenName="Someone", familyName="Else")
    >>> ctx = ProfileContext.for_document({"author": [author, other]})
    >>> [(d.code, d.severity.value) for d in check_agents(ctx)]
    [('profile.invalid-value', 'warning')]

    An author with no ORCID gets an informational nudge, but an organization
    does not — organizations do not have ORCIDs:

    >>> anonymous = {"@type": "Person", "givenName": "Jane", "familyName": "Doe"}
    >>> ctx = ProfileContext.for_document({"author": [anonymous]})
    >>> [d.code for d in check_agents(ctx)]
    ['recommendation.incomplete']
    >>> org = {"@type": "Organization", "@id": "https://ror.org/05xvt9f17",
    ...        "name": "LUMC"}
    >>> check_agents(ProfileContext.for_document({"author": [org]}))
    []
    """
    diagnostics: list[Diagnostic] = []
    seen_orcids: dict[str, str] = {}
    for prop in agent_properties():
        for value, path in ctx.values(prop):
            if not isinstance(value, dict):
                continue
            diagnostics.extend(_check_agent_id(ctx, prop, value, path, seen_orcids))
            diagnostics.extend(_check_affiliation(ctx, prop, value, path))
    return diagnostics


def _check_agent_id(
    ctx: ProfileContext,
    prop: str,
    value: dict[str, Any],
    path: DocPath,
    seen_orcids: dict[str, str],
) -> list[Diagnostic]:
    """Check one agent's identifier, tracking ORCIDs already seen.

    An ORCID or ROR may be written as the node's ``@id`` or as its
    ``identifier``. Both are correct JSON-LD and both appear in the wild, so
    both are checked; the comparison layer already reads either.
    """
    name = agent_label(value)
    node_id = _agent_identifier(value)

    if node_id is None:
        if prop == "author" and value.get("@type") != "Organization":
            return [
                ctx.diagnostic(
                    "recommendation.incomplete",
                    Severity.INFO,
                    f"{ctx.file}: author {name} has no ORCID, so the person "
                    f"cannot be disambiguated from others with the same name.",
                    path=path,
                    suggestion=(
                        'Add "@id": "https://orcid.org/0000-0000-0000-0000" '
                        "with the author's real ORCID."
                    ),
                    prop=prop,
                )
            ]
        return []

    orcid = extract_orcid(node_id)
    if orcid is not None:
        if orcid == PLACEHOLDER_ORCID:
            # Reported by the placeholder check, which explains the real
            # problem. Its check digit is wrong too, but saying so twice
            # helps nobody.
            return []
        if not orcid_checksum_valid(orcid):
            return [
                ctx.diagnostic(
                    "profile.invalid-value",
                    Severity.ERROR,
                    f"{ctx.file}: the ORCID {node_id!r} given for {name} fails "
                    f"its check digit, so it is mistyped or invented.",
                    path=(*path, "@id"),
                    value=node_id,
                    suggestion=(
                        "Look the author up at https://orcid.org/ and copy the "
                        "identifier exactly."
                    ),
                    prop=prop,
                )
            ]
        if orcid in seen_orcids and seen_orcids[orcid] != name:
            return [
                ctx.diagnostic(
                    "profile.invalid-value",
                    Severity.WARNING,
                    f"{ctx.file}: the ORCID {orcid} is used for both "
                    f"{seen_orcids[orcid]} and {name}. An ORCID identifies one "
                    f"person.",
                    path=(*path, "@id"),
                    value=node_id,
                    suggestion="Give each author their own ORCID.",
                    prop=prop,
                )
            ]
        seen_orcids.setdefault(orcid, name)
        return []

    ror = extract_ror(node_id)
    if ror is not None:
        # An organization's own @id is checked here; affiliations are checked
        # by _check_affiliation. Both are RORs and both can be mistyped.
        if not ror_checksum_valid(ror):
            return [
                ctx.diagnostic(
                    "profile.invalid-value",
                    Severity.ERROR,
                    f"{ctx.file}: the ROR identifier {node_id!r} given for "
                    f"{name} fails its check digits, so it is mistyped.",
                    path=(*path, "@id"),
                    value=node_id,
                    suggestion="Look the organization up at https://ror.org/search.",
                    prop=prop,
                )
            ]
        return []
    # Any absolute IRI identifies globally, not only an http one: urn: and
    # doi: identifiers are perfectly good @id values, and a startswith check
    # on "http" both rejected those and let "https://" through with no host.
    problem = url_problem(str(node_id).strip())
    if problem is not None:
        return [
            ctx.diagnostic(
                "profile.invalid-value",
                Severity.ERROR,
                f"{ctx.file}: the @id {node_id!r} of {name} cannot identify "
                f"anyone, because {problem}.",
                path=(*path, "@id"),
                value=node_id,
                suggestion=(
                    "Use the person's ORCID URL, or the organization's ROR URL. "
                    "Any absolute IRI is accepted if neither applies."
                ),
                prop=prop,
            )
        ]
    return []


def _agent_identifier(value: dict[str, Any]) -> Any:
    """The identifier a node carries, from ``@id`` or from ``identifier``.

    ``@id`` is the JSON-LD-native place and is preferred, but a record may put
    the ORCID in ``identifier`` instead. Reading only ``@id`` meant a mistyped
    ORCID there was reported as *no* ORCID rather than a broken one.
    """
    node_id = value.get("@id")
    if node_id is not None:
        return node_id
    for candidate in as_list(value.get("identifier")):
        if extract_orcid(candidate) or extract_ror(candidate):
            return candidate
    return None


def _check_affiliation(
    ctx: ProfileContext, prop: str, value: dict[str, Any], path: DocPath
) -> list[Diagnostic]:
    """Check an agent's affiliations for a well-formed ROR."""
    diagnostics: list[Diagnostic] = []
    for index, affiliation in enumerate(as_list(value.get("affiliation"))):
        if not isinstance(affiliation, dict):
            continue
        base = (*path, "affiliation")
        affiliation_path = (
            (*base, index) if isinstance(value.get("affiliation"), list) else base
        )
        node_id = affiliation.get("@id")
        label = affiliation.get("name") or "an affiliation"

        if node_id is None:
            diagnostics.append(
                ctx.diagnostic(
                    "recommendation.incomplete",
                    Severity.INFO,
                    f"{ctx.file}: the affiliation {label!r} has no ROR "
                    f"identifier, so it cannot be matched to an institution "
                    f"automatically.",
                    path=affiliation_path,
                    suggestion=(
                        'Add "@id" with the organization\'s ROR URL; look it '
                        "up at https://ror.org/search."
                    ),
                    prop=prop,
                )
            )
            continue

        ror = extract_ror(node_id)
        if ror is not None and not ror_checksum_valid(ror):
            diagnostics.append(
                ctx.diagnostic(
                    "profile.invalid-value",
                    Severity.ERROR,
                    f"{ctx.file}: the ROR identifier {node_id!r} given for "
                    f"{label!r} fails its check digits, so it is mistyped.",
                    path=(*affiliation_path, "@id"),
                    value=node_id,
                    suggestion="Look the organization up at https://ror.org/search.",
                    prop=prop,
                )
            )
    return diagnostics
