"""Running every profile check over one record.

Kept out of ``__init__`` so the package's namespace is only re-exports, and so
the ordering and early-exit policy have an obvious home.
"""

from __future__ import annotations

from ..concepts import ParsedSource
from ..report import Diagnostic
from .context import ProfileContext
from .formats import check_formats
from .identifiers import check_agents, check_identifiers
from .jsonld import check_context, check_feature_list, check_unknown_properties
from .licenses import check_licenses
from .placeholders import check_placeholders
from .recommendations import check_recommendations
from .schema_checks import check_schema
from .terminology import check_edam, check_vocabularies
from .types import check_types

__all__ = ["CHECKS", "validate"]


#: Every check, in the order their findings read best.
#:
#: Order matters for the reader, not for correctness: structural problems come
#: before value-level ones, because a record with no ``@context`` has bigger
#: problems than a non-canonical license URL. Diagnostics are re-sorted by
#: severity before rendering, so this is a tiebreak rather than a guarantee.
CHECKS = (
    check_context,
    check_feature_list,
    check_schema,
    check_types,
    check_formats,
    check_unknown_properties,
    check_licenses,
    check_identifiers,
    check_agents,
    check_edam,
    check_vocabularies,
    check_placeholders,
    check_recommendations,
)


def validate(parsed: ParsedSource) -> list[Diagnostic]:
    """Validate an anchor record against the LUMC profile.

    Parameters
    ----------
    parsed : ParsedSource
        The parsed ``codemeta.json``, carrying its source map so findings can
        report line numbers.

    Returns
    -------
    list of Diagnostic
        Every finding, in check order. The caller sorts by severity before
        rendering.

    See Also
    --------
    rs_metadata.core.validate : The full pipeline, including consistency.

    Examples
    --------
    >>> from rs_metadata.concepts import ParsedSource
    >>> record = {
    ...     "@context": ["https://w3id.org/codemeta/3.1"],
    ...     "@type": "SoftwareSourceCode",
    ...     "name": "MyTool",
    ...     "description": "A tool.",
    ...     "version": "1.0.0",
    ...     "identifier": "https://doi.org/10.5281/zenodo.1",
    ...     "author": [{"@type": "Person",
    ...                 "@id": "https://orcid.org/0000-0002-1825-0097",
    ...                 "givenName": "Josiah", "familyName": "Carberry"}],
    ...     "license": "https://spdx.org/licenses/Apache-2.0",
    ...     "codeRepository": "https://github.com/lumc/mytool",
    ...     "programmingLanguage": ["Python"],
    ...     "applicationCategory": "Command-line tool",
    ...     "schema:featureList": ["http://edamontology.org/operation_0292"],
    ... }
    >>> source = ParsedSource(
    ...     adapter_id="codemeta", file="codemeta.json", format="CodeMeta",
    ...     document=record,
    ... )
    >>> findings = validate(source)

    A record satisfying the profile raises no errors:

    >>> [d for d in findings if d.severity.value == "error"]
    []

    Recommendations are still reported, as one aggregated warning:

    >>> [d.code for d in findings if d.severity.value == "warning"]
    ['recommendation.missing']

    Break one thing and it is named precisely:

    >>> del record["license"]
    >>> next(d.message for d in validate(source)
    ...      if d.code == "profile.required-field")
    'codemeta.json is missing the mandatory property "license" (license).'
    """
    ctx = ProfileContext(parsed=parsed)
    context_findings = check_context(ctx)
    if any(finding.code == "profile.invalid-context" for finding in context_findings):
        # The record's vocabulary is not one this profile understands, so every
        # later check would be judging it against the wrong dictionary. Running
        # them anyway buries the one message that matters under a page of
        # complaints about properties that are perfectly valid where they came
        # from. Consistency checks against companion files still run: they do
        # not depend on the vocabulary being current.
        return context_findings
    return context_findings + [
        diagnostic
        for check in CHECKS
        if check is not check_context
        for diagnostic in check(ctx)
    ]
