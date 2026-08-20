"""JSON-LD vocabulary checks: the context, prefixes and property names.

These catch the failures where a file *looks* right and is silently wrong.
A record with no context is not CodeMeta at all; a property written without
a prefix it needs expands to nothing and is discarded by every consumer,
while remaining perfectly visible in the file to whoever wrote it.
"""

from __future__ import annotations

import difflib

from .. import CODEMETA_CONTEXT
from ..adapters.codemeta import (
    BARE_FEATURE_LIST,
    FEATURE_LIST,
    FEATURE_LIST_ALIASES,
    context_entries,
    declared_codemeta_version,
    feature_list_key,
)
from ..diagnostics import Severity
from ..report import Diagnostic
from ..vocabulary import codemeta_terms, codemeta_versions
from .context import ProfileContext

__all__ = ["check_context", "check_feature_list", "check_unknown_properties"]

#: Minimum similarity for a "did you mean" suggestion. Set high on purpose:
#: a wrong suggestion is worse than none, because it sends the reader off to
#: change a property that was never the problem.
_TYPO_CUTOFF = 0.85


def check_context(ctx: ProfileContext) -> list[Diagnostic]:
    """Check that ``@context`` declares a recognized CodeMeta vocabulary.

    Parameters
    ----------
    ctx : ProfileContext
        The record under validation.

    Returns
    -------
    list of Diagnostic
        Findings about the context.

    Notes
    -----
    Without a context, property names in the file have no globally defined
    meaning: ``name`` could denote anything. This is reported as its own
    diagnostic rather than as a generic missing field.

    Every ``3.x`` context is current: 3.0 and 3.1 resolve to byte-identical
    documents, so warning about 3.0 would fire on files the common generators
    produce while telling the reader nothing.

    Anything that is not a CodeMeta 3.x context is an **error**, and
    :func:`~rs_metadata.profile.validate` stops after it. Earlier CodeMeta
    renamed properties, so every later check would judge the record against the
    wrong dictionary and report valid terms as unknown.

    Examples
    --------
    A well-formed context produces nothing:

    >>> ctx = ProfileContext.for_document(
    ...     {"@context": ["https://w3id.org/codemeta/3.1"]}
    ... )
    >>> check_context(ctx)
    []

    A missing context is an error, and not a `profile.required-field` one:

    >>> [d.code for d in check_context(ProfileContext.for_document({}))]
    ['profile.invalid-context']

    So is a context that references something other than CodeMeta:

    >>> ctx = ProfileContext.for_document({"@context": "https://example.org/x"})
    >>> [d.code for d in check_context(ctx)]
    ['profile.invalid-context']

    A 3.0 context is the current vocabulary, so it produces nothing:

    >>> check_context(ProfileContext.for_document(
    ...     {"@context": "https://w3id.org/codemeta/3.0"}))
    []

    So is an earlier CodeMeta, which this profile does not build on:

    >>> ctx = ProfileContext.for_document(
    ...     {"@context": "https://doi.org/10.5063/schema/codemeta-2.0"}
    ... )
    >>> [d.code for d in check_context(ctx)]
    ['profile.invalid-context']
    """
    if "@context" not in ctx.document:
        return [
            ctx.diagnostic(
                "profile.invalid-context",
                Severity.ERROR,
                f"{ctx.file} has no @context, so its property names have no "
                f"defined meaning and no consumer can interpret it as CodeMeta.",
                suggestion=(
                    '"@context": ["https://w3id.org/codemeta/3.1", '
                    '{"schema": "https://schema.org/"}]'
                ),
                prop="@context",
            )
        ]

    version = declared_codemeta_version(ctx.document)
    if version is None:
        return [_unrecognized_context(ctx)]
    versions = codemeta_versions()
    if version.split(".")[0] == versions["currentMajor"]:
        # 3.0 and 3.1 resolve to byte-identical context documents, so a 3.0
        # record uses the current vocabulary. Saying otherwise would fire on
        # every file the common generators produce.
        return []
    return [_unrecognized_context(ctx)]


def _unrecognized_context(ctx: ProfileContext) -> Diagnostic:
    """Report a context this profile does not build on.

    Only CodeMeta 3.x is recognized. Earlier CodeMeta renamed several
    properties, so the same record means different things under each, and this
    profile is defined against 3.x.
    """
    return ctx.diagnostic(
        "profile.invalid-context",
        Severity.ERROR,
        f"The @context of {ctx.file} does not reference a CodeMeta 3.x "
        f"context, so this profile cannot interpret the record. Earlier "
        f"CodeMeta versions renamed properties and are not accepted.",
        path=("@context",),
        value=ctx.document.get("@context"),
        suggestion=f'Set the context to "{CODEMETA_CONTEXT}".',
        prop="@context",
    )


def declared_prefixes(ctx: ProfileContext) -> set[str]:
    """Prefixes usable in this document: CodeMeta's own plus any inline ones.

    Parameters
    ----------
    ctx : ProfileContext
        The record under validation.

    Returns
    -------
    set of str
        Prefix names that can be expanded.

    Examples
    --------
    The CodeMeta context supplies two prefixes on its own, which is why
    ``schema:featureList`` needs no extra declaration:

    >>> ctx = ProfileContext.for_document(
    ...     {"@context": "https://w3id.org/codemeta/3.1"}
    ... )
    >>> sorted(declared_prefixes(ctx))
    ['codemeta', 'schema']

    An inline object adds to them:

    >>> ctx = ProfileContext.for_document({
    ...     "@context": [
    ...         "https://w3id.org/codemeta/3.1",
    ...         {"lumc": "https://lumc.nl/terms/"},
    ...     ]
    ... })
    >>> sorted(declared_prefixes(ctx))
    ['codemeta', 'lumc', 'schema']
    """
    prefixes = set(codemeta_terms()["prefixes"])
    for entry in context_entries(ctx.document):
        if isinstance(entry, dict):
            prefixes.update(
                key
                for key, value in entry.items()
                if isinstance(value, str) and not key.startswith("@")
            )
    return prefixes


def check_feature_list(ctx: ProfileContext) -> list[Diagnostic]:
    """Check how the operations property is spelled.

    Parameters
    ----------
    ctx : ProfileContext
        The record under validation.

    Returns
    -------
    list of Diagnostic
        Findings about the spelling of ``schema:featureList``.

    Notes
    -----
    CodeMeta 3.1 does not define ``featureList`` in its own vocabulary. Written
    bare it expands to nothing and JSON-LD processors discard it silently, so
    the operations look present in the file and are invisible to every
    consumer. This is the failure this check exists for.

    The absolute-IRI spellings are correct JSON-LD and are accepted with a
    note, since every worked example uses the prefixed form.

    Examples
    --------
    The canonical spelling produces nothing:

    >>> ctx = ProfileContext.for_document({"schema:featureList": ["x"]})
    >>> check_feature_list(ctx)
    []

    The unprefixed spelling is an error, because the data is silently lost:

    >>> ctx = ProfileContext.for_document({"featureList": ["x"]})
    >>> [(d.code, d.severity.value) for d in check_feature_list(ctx)]
    [('profile.unprefixed-term', 'error')]

    An absolute IRI works, and is merely non-canonical:

    >>> ctx = ProfileContext.for_document({"https://schema.org/featureList": ["x"]})
    >>> [(d.code, d.severity.value) for d in check_feature_list(ctx)]
    [('profile.non-canonical-value', 'warning')]
    """
    diagnostics: list[Diagnostic] = []

    if BARE_FEATURE_LIST in ctx.document:
        diagnostics.append(
            ctx.diagnostic(
                "profile.unprefixed-term",
                Severity.ERROR,
                f'{ctx.file} uses "featureList", which CodeMeta 3.1 does not '
                f"define. Without a prefix it expands to nothing, so the "
                f"operations recorded here are silently discarded by JSON-LD "
                f"consumers.",
                path=(BARE_FEATURE_LIST,),
                suggestion=(
                    f'Rename the property to "{FEATURE_LIST}". The "schema" '
                    f"prefix is already declared by the CodeMeta 3.1 context, "
                    f"so no other change is needed."
                ),
                prop=FEATURE_LIST,
            )
        )

    used = feature_list_key(ctx.document)
    if used in FEATURE_LIST_ALIASES:
        diagnostics.append(
            ctx.diagnostic(
                "profile.non-canonical-value",
                Severity.WARNING,
                f'{ctx.file} writes operations as "{used}". That is correct '
                f"JSON-LD, but every worked example uses the "
                f"prefixed form.",
                path=(used,),
                suggestion=f'Rename the property to "{FEATURE_LIST}".',
                prop=FEATURE_LIST,
            )
        )
    return diagnostics


#: Keys that configure an editor rather than describe the software. They are
#: not CodeMeta properties and never will be, but they are the documented way
#: to get schema completion in a JSON file, and this project recommends them.
#: Warning about a key we tell people to add would be a false alarm of our own
#: making. JSON-LD ignores them, since they expand to nothing.
_EDITOR_KEYS = frozenset({"$schema"})


def check_unknown_properties(ctx: ProfileContext) -> list[Diagnostic]:
    """Flag properties CodeMeta does not define, and undeclared prefixes.

    Parameters
    ----------
    ctx : ProfileContext
        The record under validation.

    Returns
    -------
    list of Diagnostic
        Findings about property names.

    Notes
    -----
    The profile deliberately allows extra properties, so an unrecognized term
    is a **warning**: consumers ignore what they do not understand, which is
    not fatal. It is reported at all because it is nearly always a typo, and a
    typo means a mandatory field is quietly missing.

    An *undeclared prefix* is different and is an error: the property cannot be
    expanded to an IRI at all, so it is malformed rather than merely unknown.

    Examples
    --------
    A CodeMeta property is fine, and so is an absolute IRI:

    >>> check_unknown_properties(ProfileContext.for_document({"name": "x"}))
    []
    >>> ctx = ProfileContext.for_document({"https://example.org/terms/x": "y"})
    >>> check_unknown_properties(ctx)
    []

    A typo is caught, with the correction suggested:

    >>> ctx = ProfileContext.for_document({"programingLanguage": ["Python"]})
    >>> finding = check_unknown_properties(ctx)[0]
    >>> finding.code, finding.severity.value
    ('profile.unknown-property', 'warning')
    >>> finding.suggestion
    'Did you mean "programmingLanguage"?'

    An editor's `$schema` pointer is not a CodeMeta property, but it describes
    the file rather than the software, and is how editors are told which
    schema to complete against:

    >>> check_unknown_properties(ProfileContext.for_document({"$schema": "x"}))
    []

    A prefixed term is accepted once its prefix is declared:

    >>> undeclared = ProfileContext.for_document({"lumc:internalId": "RSE-1"})
    >>> [d.code for d in check_unknown_properties(undeclared)]
    ['profile.invalid-context']
    >>> declared = ProfileContext.for_document({
    ...     "@context": [
    ...         "https://w3id.org/codemeta/3.1",
    ...         {"lumc": "https://lumc.nl/terms/"},
    ...     ],
    ...     "lumc:internalId": "RSE-1",
    ... })
    >>> check_unknown_properties(declared)
    []
    """
    terms = codemeta_terms()["terms"]
    prefixes = declared_prefixes(ctx)
    known = set(terms) | set(FEATURE_LIST_ALIASES) | {FEATURE_LIST, BARE_FEATURE_LIST}
    diagnostics: list[Diagnostic] = []

    for key in ctx.document:
        if key.startswith("@") or key in known or key in _EDITOR_KEYS:
            continue
        if key.startswith(("http://", "https://")):
            continue
        if ":" in key:
            prefix = key.split(":", 1)[0]
            if prefix not in prefixes:
                diagnostics.append(
                    ctx.diagnostic(
                        "profile.invalid-context",
                        Severity.ERROR,
                        f'{ctx.file} uses the prefix "{prefix}:" in "{key}", '
                        f"but no @context entry declares it, so the property "
                        f"cannot be expanded to an IRI.",
                        path=(key,),
                        suggestion=(
                            f"Declare the prefix in @context, for example "
                            f'{{"{prefix}": "https://example.org/terms/"}}.'
                        ),
                        prop=key,
                    )
                )
            continue
        close = difflib.get_close_matches(key, sorted(terms), n=1, cutoff=_TYPO_CUTOFF)
        diagnostics.append(
            ctx.diagnostic(
                "profile.unknown-property",
                Severity.WARNING,
                f'{ctx.file} contains "{key}", which is not a CodeMeta 3.1 '
                f"property. Consumers will ignore it.",
                path=(key,),
                suggestion=(
                    f'Did you mean "{close[0]}"?'
                    if close
                    else (
                        "Correct the spelling, or write it as a prefixed term "
                        "with the prefix declared in @context if the extension "
                        "is intentional."
                    )
                ),
                prop=key,
            )
        )
    return diagnostics
