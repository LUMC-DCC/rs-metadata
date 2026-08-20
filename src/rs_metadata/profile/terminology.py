"""EDAM terms and the controlled vocabularies CodeMeta properties draw on.

EDAM terms are checked for *shape* and for *branch*, never for existence:
confirming a term exists would need a network lookup, while an operation term
sitting in the topics list is detectable offline and is a real mistake.

``developmentStatus`` must use
repostatus.org, so anything else is a warning. ``applicationCategory`` merely
*prefers* bio.tools tool types and explicitly permits free text, so a
non-vocabulary value is only informational.
"""

from __future__ import annotations

from ..adapters.codemeta import FEATURE_LIST, any_feature_list_key
from ..diagnostics import Severity
from ..normalize import EDAM_RE, scalarize
from ..report import Diagnostic
from ..vocabulary import vocabularies
from .context import ProfileContext

__all__ = ["check_edam", "check_vocabularies"]

_EDAM_BROWSER = "https://edamontology.github.io/edam-browser/"


def check_edam(ctx: ProfileContext) -> list[Diagnostic]:
    """Check EDAM terms in the operations and topics properties.

    Parameters
    ----------
    ctx : ProfileContext
        The record under validation.

    Returns
    -------
    list of Diagnostic
        Findings about EDAM usage.

    Notes
    -----
    Three things are checked, and one is deliberately not:

    * a value that *looks* like EDAM but is malformed is an **error**;
    * an ``operation_`` term in the topics list, or a ``topic_`` term in the
      operations list, is an **error** — the two describe different things;
    * ``https://edamontology.org/...`` is a **warning**, because EDAM's own
      identifiers use ``http`` and the ``https`` form will not match them;
    * whether the term *exists* is not checked, because that needs a network
      lookup and CI must be deterministic.

    Free text is explicitly permitted, so a property with no EDAM
    terms at all is only an informational nudge.

    Examples
    --------
    A well-formed operation term produces nothing:

    >>> ctx = ProfileContext.for_document(
    ...     {"schema:featureList": ["http://edamontology.org/operation_0292"]}
    ... )
    >>> check_edam(ctx)
    []

    A topic in the operations list is an error, and says where it belongs:

    >>> ctx = ProfileContext.for_document(
    ...     {"schema:featureList": ["http://edamontology.org/topic_0622"]}
    ... )
    >>> finding = check_edam(ctx)[0]
    >>> finding.code, finding.severity.value
    ('profile.invalid-value', 'error')
    >>> finding.suggestion
    'Move this term to "applicationSubCategory".'

    The `https` spelling will not match EDAM's own identifiers:

    >>> ctx = ProfileContext.for_document(
    ...     {"schema:featureList": ["https://edamontology.org/operation_0292"]}
    ... )
    >>> finding = check_edam(ctx)[0]
    >>> finding.code
    'profile.non-canonical-value'
    >>> finding.suggestion
    'Use "http://edamontology.org/operation_0292".'

    A malformed term is an error. The nudge follows it because the property
    still contains no *usable* EDAM term:

    >>> ctx = ProfileContext.for_document(
    ...     {"schema:featureList": ["http://edamontology.org/operation_92"]}
    ... )
    >>> [d.code for d in check_edam(ctx)]
    ['profile.invalid-value', 'recommendation.incomplete']

    Free text is allowed, with a nudge towards EDAM:

    >>> ctx = ProfileContext.for_document(
    ...     {"schema:featureList": ["Aligning reads to a reference"]}
    ... )
    >>> [(d.code, d.severity.value) for d in check_edam(ctx)]
    [('recommendation.incomplete', 'info')]
    """
    return _check_branch(ctx, FEATURE_LIST, "operation", "operations") + _check_branch(
        ctx, "applicationSubCategory", "topic", "topics"
    )


def _check_branch(
    ctx: ProfileContext, prop: str, branch: str, label: str
) -> list[Diagnostic]:
    """Check one EDAM-bearing property against the branch it should draw on."""
    key = any_feature_list_key(ctx.document) if prop == FEATURE_LIST else prop
    if key is None:
        return []
    values = ctx.values(key)
    if not values:
        return []

    other = "topic" if branch == "operation" else "operation"
    diagnostics: list[Diagnostic] = []
    found_edam = False

    for value, path in values:
        scalar = scalarize(value)
        if scalar is None or "edamontology.org" not in scalar.lower():
            continue
        if not EDAM_RE.match(scalar):
            diagnostics.append(
                ctx.diagnostic(
                    "profile.invalid-value",
                    Severity.ERROR,
                    f"{ctx.file}: {scalar!r} looks like an EDAM term but is "
                    f"not a well-formed EDAM URI.",
                    path=path,
                    value=scalar,
                    suggestion=(
                        f"EDAM URIs have the form "
                        f"http://edamontology.org/{branch}_1234. Search for "
                        f"the term at {_EDAM_BROWSER}."
                    ),
                    prop=prop,
                )
            )
            continue

        found_edam = True
        if f"/{other}_" in scalar.lower():
            target = "applicationSubCategory" if other == "topic" else FEATURE_LIST
            diagnostics.append(
                ctx.diagnostic(
                    "profile.invalid-value",
                    Severity.ERROR,
                    f"{ctx.file}: {scalar!r} is an EDAM {other}, but "
                    f'"{prop}" records {label}.',
                    path=path,
                    value=scalar,
                    suggestion=f'Move this term to "{target}".',
                    prop=prop,
                )
            )
        elif scalar.lower().startswith("https://"):
            diagnostics.append(
                ctx.diagnostic(
                    "profile.non-canonical-value",
                    Severity.WARNING,
                    f"{ctx.file}: EDAM term IRIs use http, not https. "
                    f"{scalar!r} will not match the ontology's own identifier.",
                    path=path,
                    value=scalar,
                    suggestion=f'Use "{scalar.replace("https://", "http://", 1)}".',
                    prop=prop,
                )
            )

    if not found_edam:
        diagnostics.append(
            ctx.diagnostic(
                "recommendation.incomplete",
                Severity.INFO,
                f'{ctx.file}: "{prop}" records only free text. EDAM {label} '
                f"enable semantic search in bio.tools and ELIXIR "
                f"infrastructure.",
                path=(key,),
                suggestion=(
                    f"Find terms at {_EDAM_BROWSER} and keep the free-text "
                    f"entries alongside them."
                ),
                prop=prop,
            )
        )
    return diagnostics


def check_vocabularies(ctx: ProfileContext) -> list[Diagnostic]:
    """Check properties that draw on a controlled vocabulary.

    Parameters
    ----------
    ctx : ProfileContext
        The record under validation.

    Returns
    -------
    list of Diagnostic
        Findings about vocabulary usage.

    Notes
    -----
    Strictness follows the vocabulary's own ``closed`` flag in the vendored
    data: repostatus.org is a closed
    vocabulary for ``developmentStatus``, while bio.tools tool types are
    merely preferred for ``applicationCategory``.

    Examples
    --------
    A repostatus term is accepted:

    >>> ctx = ProfileContext.for_document({"developmentStatus": "active"})
    >>> check_vocabularies(ctx)
    []

    The vocabulary is closed, so anything else is an error and the message
    lists every accepted term:

    >>> ctx = ProfileContext.for_document(
    ...     {"developmentStatus": "actively maintained"}
    ... )
    >>> finding = check_vocabularies(ctx)[0]
    >>> finding.code, finding.severity.value
    ('profile.invalid-value', 'error')
    >>> "abandoned, active" in finding.suggestion
    True

    A bio.tools tool type is accepted:

    >>> ctx = ProfileContext.for_document(
    ...     {"applicationCategory": "Command-line tool"}
    ... )
    >>> check_vocabularies(ctx)
    []

    That includes the repostatus.org URL: the property is typed as Text, so
    the bare term is the only member of the vocabulary.

    >>> ctx = ProfileContext.for_document(
    ...     {"developmentStatus": "https://www.repostatus.org/#active"}
    ... )
    >>> [d.severity.value for d in check_vocabularies(ctx)]
    ['error']

    Free text in applicationCategory is conformant CodeMeta but not what this
    profile expects, so it is a warning rather than an error:

    >>> ctx = ProfileContext.for_document({"applicationCategory": "Notebook"})
    >>> [(d.code, d.severity.value) for d in check_vocabularies(ctx)]
    [('profile.invalid-value', 'warning')]
    """
    catalog = vocabularies()
    diagnostics: list[Diagnostic] = []

    status = catalog["developmentStatus"]
    allowed_status = {term.casefold() for term in status["terms"]}
    for value, path in ctx.values("developmentStatus"):
        scalar = scalarize(value)
        if scalar and scalar.strip().casefold() not in allowed_status:
            diagnostics.append(
                ctx.diagnostic(
                    "profile.invalid-value",
                    Severity.ERROR,
                    f"{ctx.file}: {scalar!r} is not a repostatus.org term. "
                    f"CodeMeta types developmentStatus as Text and points at "
                    f"that vocabulary; this profile closes it to those terms, "
                    f"so nothing else is accepted.",
                    path=path,
                    value=scalar,
                    suggestion=(
                        f"Use one of: {', '.join(status['terms'])}. Write the "
                        f"bare term, not the repostatus.org URL — the property "
                        f"is typed as Text, so the URL is not a member of the "
                        f"vocabulary."
                    ),
                    prop="developmentStatus",
                )
            )

    category = catalog["applicationCategory"]
    allowed_category = {term.casefold() for term in category["terms"]}
    for value, path in ctx.values("applicationCategory"):
        scalar = scalarize(value, ("name", "value", "@id", "url"))
        if scalar and scalar.strip().casefold() not in allowed_category:
            diagnostics.append(
                ctx.diagnostic(
                    "profile.invalid-value",
                    Severity.WARNING,
                    f"{ctx.file}: {scalar!r} is not a bio.tools tool type. "
                    f"CodeMeta permits free text here; this profile expects a "
                    f"vocabulary term so the record is discoverable in that "
                    f"registry.",
                    path=path,
                    value=scalar,
                    suggestion=f"Preferred values: {', '.join(category['terms'])}.",
                    prop="applicationCategory",
                )
            )
    return diagnostics
