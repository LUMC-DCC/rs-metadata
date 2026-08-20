"""Value-type conformance, driven by CodeMeta's own property table.

This is the single place value types are enforced. The types themselves are
never written down here — they are derived from upstream by
``scripts/vendor_reference_data.py`` from CodeMeta's property table and
schema.org, and read through :func:`~rs_metadata.vocab.type_entry`, so a change
upstream arrives by regenerating the data rather than by editing Python.

The rule is mechanical, which is what makes it safe to apply to every
property at once:

    A property whose declared range includes ``Text`` may be written as a bare
    string. A property whose range does not must be a node or an absolute URL.

The second half is the one that matters. JSON-LD does not reject a wrong type;
it silently coerces. A bare ``"Apache-2.0"`` where ``CreativeWork or URL`` is
expected expands to a *relative* IRI, which resolves against the document base
into a meaningless URL or is dropped outright. Nothing errors anywhere in the
chain — the value simply stops being recognizable to anything that ingests the
file. That is the same failure as the unprefixed ``featureList``, and it is why
these are errors rather than warnings.
"""

from __future__ import annotations

import json
from typing import Any

from ..diagnostics import Severity
from ..locate import Path as DocPath
from ..report import Diagnostic
from ..vocabulary import LITERAL_TYPES, allows_text, satisfies, type_entry
from .context import ProfileContext
from .formats import url_problem, valid_url

__all__ = ["check_types", "example_for", "reports_on", "required_form"]

#: Properties whose type violations a more specialised check reports better.
#: ``license`` is the only one: :mod:`.licenses` can resolve a bare identifier
#: against the SPDX list and name the exact URL to use, where this module could
#: only say "a CreativeWork node or an absolute URL".
_OWNED_ELSEWHERE = frozenset({"license"})

#: Range entries a bare string can satisfy without being a node. ``URL`` needs
#: the value to be an absolute IRI; the rest accept any scalar.
_SCALAR_TYPES = LITERAL_TYPES | {"URL"}

#: How to build each node type, used to show a correction rather than merely
#: naming one. Keyed by the range entry the property declares.
_NODE_EXAMPLES: dict[str, dict[str, Any]] = {
    "CreativeWork": {
        "@type": "CreativeWork",
        "name": "Name of the work",
        "url": "https://example.org/the-work",
    },
    "Person": {
        "@type": "Person",
        "givenName": "Given",
        "familyName": "Family",
        "@id": "https://orcid.org/0000-0002-1825-0097",
    },
    "Organization": {
        "@type": "Organization",
        "name": "Name of the organization",
        "@id": "https://ror.org/05xvt9f17",
    },
    "SoftwareSourceCode": {
        "@type": "SoftwareSourceCode",
        "name": "package-name",
        "version": ">=1.0",
    },
    "SoftwareApplication": {
        "@type": "SoftwareApplication",
        "name": "application-name",
    },
    "ScholarlyArticle": {
        "@type": "ScholarlyArticle",
        "name": "Title of the article",
        "@id": "https://doi.org/10.5281/zenodo.0000000",
    },
    "PropertyValue": {
        "@type": "PropertyValue",
        "propertyID": "doi",
        "value": "10.5281/zenodo.0000000",
    },
    "Review": {"@type": "Review", "reviewBody": "…", "reviewAspect": "…"},
    "MediaObject": {"@type": "MediaObject", "contentUrl": "https://example.org/file"},
    "DataFeed": {"@type": "DataFeed", "name": "Name of the dataset"},
    "ComputerLanguage": {"@type": "ComputerLanguage", "name": "Python"},
    "PostalAddress": {"@type": "PostalAddress", "addressLocality": "Leiden"},
}


def required_form(name: str) -> str:
    """Describe, in prose, what a property's value has to be.

    Parameters
    ----------
    name : str
        CodeMeta property name.

    Returns
    -------
    str
        A phrase naming the accepted forms, for use in a diagnostic.

    Examples
    --------
    >>> required_form("license")
    'a CreativeWork node or an absolute URL'
    >>> required_form("author")
    'an Organization or Person node'
    >>> required_form("codeRepository")
    'an absolute URL'
    >>> required_form("softwareRequirements")
    'a SoftwareSourceCode node'
    """
    entry = type_entry(name)
    if entry is None:  # pragma: no cover - guarded by the caller
        return "a node or an absolute URL"
    nodes = [item for item in entry["range"] if item not in _SCALAR_TYPES]
    parts: list[str] = []
    if nodes:
        article = "an" if nodes[0][:1] in "AEIOU" else "a"
        parts.append(f"{article} {' or '.join(nodes)} node")
    if "URL" in entry["range"]:
        parts.append("an absolute URL")
    return " or ".join(parts)


def example_for(name: str) -> str | None:
    """A ready-to-paste node showing the accepted form of a property.

    Parameters
    ----------
    name : str
        CodeMeta property name.

    Returns
    -------
    str or None
        Compact JSON for the first node type in the property's range, or
        ``None`` when the range is URL-only and there is nothing to build.

    Examples
    --------
    >>> example_for("softwareRequirements")
    '{"@type": "SoftwareSourceCode", "name": "package-name", "version": ">=1.0"}'

    A URL-only property has no node form to show:

    >>> example_for("codeRepository") is None
    True
    """
    entry = type_entry(name)
    if entry is None:
        return None
    for item in entry["range"]:
        template = _NODE_EXAMPLES.get(item)
        if template is not None:
            return json.dumps(template)
    return None


def _is_conformant(value: Any, allowed: list[str]) -> bool:
    """Whether one value satisfies a range that does not include ``Text``.

    A node is judged on its ``@type`` only. Whether it carries the right keys
    is the schema's business; whether it is the right *kind* of thing is this
    check's, because that is what the range says.

    A node with no ``@type`` is accepted: it is a node where a node belongs,
    and common generators omit the key. Guessing its kind would risk rejecting
    correct metadata.
    """
    if isinstance(value, dict):
        nodes = [item for item in allowed if item not in _SCALAR_TYPES]
        if not nodes:
            # The range offers no node type at all, so a node cannot satisfy
            # it however it is labelled: downloadUrl is a URL, and an object
            # there is not a mislabelled URL, it is the wrong thing entirely.
            return False
        declared = value.get("@type")
        if not isinstance(declared, str):
            return True
        # Subclasses count. A ScholarlyArticle is a CreativeWork, and rejecting
        # one where CreativeWork is named would be a false alarm.
        return any(satisfies(declared, expected) for expected in nodes)
    if isinstance(value, str):
        return "URL" in allowed and valid_url(value.strip())
    return False


def reports_on(name: str, value: Any) -> bool:
    """Whether a dedicated value-type check will report on this value.

    Used by :mod:`.schema_checks` to stay quiet where a better message is
    coming, so one mistake produces one diagnostic. Sharing this predicate
    rather than re-deriving it is what keeps the two in step.

    Parameters
    ----------
    name : str
        CodeMeta property name.
    value : Any
        The property's value, as written — a scalar, a node, or an array.

    Returns
    -------
    bool
        ``True`` only when the value actually contains something a type check
        will complain about.

    Examples
    --------
    A bare string where a node is required is reported:

    >>> reports_on("license", "Apache-2.0")
    True
    >>> reports_on("author", ["Jane Doe"])
    True

    Conformant values are not:

    >>> reports_on("author", [{"@type": "Person", "familyName": "Doe"}])
    False
    >>> reports_on("developmentStatus", "active")
    False

    Neither is a structural problem, which stays the schema's to report — an
    empty array has no value to be the wrong type:

    >>> reports_on("author", [])
    False
    """
    if allows_text(name):
        return False
    allowed = _range_for(name, parent=None)
    if allowed is None:
        return False
    items = value if isinstance(value, list) else [value]
    return any(not _is_conformant(item, allowed) for item in items)


def _range_for(name: str, parent: str | None) -> list[str] | None:
    """The range that applies to a property in a given position."""
    entry = type_entry(name)
    if entry is None:
        return None
    if parent is not None:
        by_parent = entry.get("byParent") or {}
        if parent in by_parent:
            return list(by_parent[parent])
    return list(entry["range"])


def check_types(ctx: ProfileContext) -> list[Diagnostic]:
    """Check every value against the type CodeMeta declares for its property.

    Parameters
    ----------
    ctx : ProfileContext
        The record under validation.

    Returns
    -------
    list of Diagnostic
        One error per non-conformant value, each naming the required form and
        showing a corrected value.

    Notes
    -----
    Only the *kind* of value is checked here — bare string versus node versus
    URL. Whether a node has the right keys is the schema's job, and whether a
    conformant value is a good one is the job of the license, vocabulary and
    identifier checks.

    Nested nodes are checked one level down for the properties CodeMeta types
    differently by parent, which today is ``identifier`` inside a ``Person``.

    Examples
    --------
    A range including ``Text`` accepts a bare string:

    >>> check_types(ProfileContext.for_document({"developmentStatus": "active"}))
    []
    >>> check_types(ProfileContext.for_document({"keywords": ["genomics"]}))
    []

    A range without it does not, and the message shows the fix:

    >>> ctx = ProfileContext.for_document({"referencePublication": "Doe 2026"})
    >>> finding = check_types(ctx)[0]
    >>> finding.code, finding.severity.value
    ('profile.invalid-type', 'error')
    >>> "a ScholarlyArticle node" in finding.message
    True

    An absolute URL satisfies a range containing ``URL``:

    >>> check_types(ProfileContext.for_document(
    ...     {"codeRepository": "https://github.com/org/tool"}))
    []

    but not one without it — a dependency has to be a node:

    >>> ctx = ProfileContext.for_document({"softwareRequirements": ["numpy>=1.24"]})
    >>> print(check_types(ctx)[0].suggestion)
    Write it as {"@type": "SoftwareSourceCode", "name": "package-name", ...}.

    Nodes are accepted wherever a node is expected:

    >>> check_types(ProfileContext.for_document({"softwareRequirements": [
    ...     {"@type": "SoftwareSourceCode", "name": "numpy", "version": ">=1.24"}]}))
    []
    >>> check_types(ProfileContext.for_document({"author": [
    ...     {"@type": "Person", "familyName": "Doe"}]}))
    []

    Properties CodeMeta does not define are left to the unknown-property
    check rather than also drawing a type complaint:

    >>> check_types(ProfileContext.for_document({"somethingInvented": "x"}))
    []

    ``license`` is absent here too: :mod:`.licenses` reports it, because it can
    resolve the text against SPDX and name the exact URL to use.

    >>> check_types(ProfileContext.for_document({"license": "Apache-2.0"}))
    []
    """
    diagnostics: list[Diagnostic] = []
    for name in ctx.document:
        if name.startswith("@"):
            continue
        if allows_text(name):
            continue
        allowed = _range_for(name, parent=None)
        if allowed is None:
            continue
        # A property another check owns still gets its nested nodes walked.
        # :mod:`.licenses` has an opinion about the license value itself, not
        # about whether a CreativeWork's url is a URL.
        owned = name in _OWNED_ELSEWHERE
        for value, path in ctx.values(name):
            if _is_conformant(value, allowed):
                diagnostics.extend(_check_nested(ctx, name, value, path))
            elif not owned:
                diagnostics.append(_type_error(ctx, name, value, path))
    return diagnostics


def _check_nested(
    ctx: ProfileContext, name: str, value: Any, path: DocPath
) -> list[Diagnostic]:
    """Check a node's own properties where CodeMeta types them by parent."""
    if not isinstance(value, dict):
        return []
    parent = value.get("@type")
    if not isinstance(parent, str):
        return []
    diagnostics: list[Diagnostic] = []
    for key, item, item_path in ctx.node_values(value, path):
        allowed = _range_for(key, parent=parent)
        if allowed is None or LITERAL_TYPES.intersection(allowed):
            continue
        if not _is_conformant(item, allowed):
            diagnostics.append(_type_error(ctx, key, item, item_path, parent=parent))
    return diagnostics


def _type_error(
    ctx: ProfileContext,
    name: str,
    value: Any,
    path: DocPath,
    parent: str | None = None,
) -> Diagnostic:
    """Build the diagnostic for a value CodeMeta could not resolve."""
    shown = value if isinstance(value, (str, int, float, bool)) else None
    where = f" inside a {parent}" if parent else ""
    example = example_for(name)
    allowed = _range_for(name, parent) or []
    fix = (
        f"Write it as {example}."
        if example
        else "Use an absolute URL, including the scheme."
    )

    if isinstance(value, dict):
        # A node of the wrong kind: say which kind it is, since the fix is to
        # change @type or move the value to a property that accepts it.
        declared = str(value.get("@type"))
        article = "an" if declared[:1] in "AEIOU" else "a"
        clause = f"{article} {declared} node was given"
        shown = str(value.get("name") or value.get("@id") or "")[:80] or None
    elif isinstance(value, str):
        problem = url_problem(value.strip()) if "URL" in allowed else None
        if problem is not None:
            # It was meant to be a URL and nearly is one. Naming the actual
            # defect beats repeating that a URL was expected.
            clause = f"{value.strip()!r} was given, and {problem}"
            fix = "Give a URL that resolves, including its scheme and host."
        else:
            clause = (
                "a bare string was given. CodeMeta types this property so that "
                "a bare string expands to a relative IRI, which consumers "
                "cannot resolve"
            )
    else:
        clause = f"a {type(value).__name__} was given"

    return ctx.diagnostic(
        "profile.invalid-type",
        Severity.ERROR,
        f"{ctx.file}: {name}{where} must be {required_form(name)}, but {clause}"
        f"{'' if clause.endswith('?') else '.'}",
        path=path,
        value=shown,
        suggestion=fix,
        prop=name,
    )
