"""The recommended-field check.

Separate from the mandatory-field check because the two exist for different
reasons and behave differently: a missing mandatory field is an error about
one field, while missing recommendations are a single piece of advice about
the record as a whole.
"""

from __future__ import annotations

from ..diagnostics import Severity
from ..report import Diagnostic
from .context import ProfileContext

__all__ = ["check_recommendations", "missing_recommendations"]


def missing_recommendations(ctx: ProfileContext) -> list[str]:
    """List the recommended fields the record does not have.

    Parameters
    ----------
    ctx : ProfileContext
        The record under validation.

    Returns
    -------
    list of str
        Absent recommended fields, in the profile's own order.

    Examples
    --------
    >>> ctx = ProfileContext.for_document({"keywords": ["genomics"]})
    >>> "keywords" in missing_recommendations(ctx)
    False
    >>> "datePublished" in missing_recommendations(ctx)
    True
    """
    return [name for name in ctx.policy["recommended"] if name not in ctx.document]


def check_recommendations(ctx: ProfileContext) -> list[Diagnostic]:
    """Report absent recommended fields as one finding, not fifteen.

    Parameters
    ----------
    ctx : ProfileContext
        The record under validation.

    Returns
    -------
    list of Diagnostic
        At most one warning, naming every absent field.

    Notes
    -----
    Aggregation is deliberate. The profile recommends fifteen fields, and a
    minimal-but-valid record is missing most of them; emitting one warning
    each would bury the errors that actually need attention and train people
    to ignore warnings altogether.

    Recommendations never fail a build unless the run is configured with
    ``--fail-on warning``.

    Examples
    --------
    A record missing recommendations gets exactly one finding:

    >>> ctx = ProfileContext.for_document({"name": "MyTool"})
    >>> findings = check_recommendations(ctx)
    >>> len(findings)
    1
    >>> findings[0].code, findings[0].severity.value
    ('recommendation.missing', 'warning')

    The message names them all, so the advice is actionable:

    >>> "datePublished" in findings[0].message and "keywords" in findings[0].message
    True

    A record with every recommendation produces nothing:

    >>> complete = {name: "x" for name in ctx.policy["recommended"]}
    >>> check_recommendations(ProfileContext.for_document(complete))
    []
    """
    missing = missing_recommendations(ctx)
    if not missing:
        return []
    return [
        ctx.diagnostic(
            "recommendation.missing",
            Severity.WARNING,
            f"{ctx.file} omits {len(missing)} recommended "
            f"{'field' if len(missing) == 1 else 'fields'}: "
            f"{', '.join(missing)}.",
            suggestion=(
                "These are not required by the LUMC profile, but several are "
                "required by registries such as the Research Software "
                "Directory and bio.tools. See docs/using/profile.md for what "
                "each one is for."
            ),
        )
    ]
