"""Structural validation, and the translation of schema errors into English.

The JSON Schema decides what is structurally valid. This module decides what
the reader sees, which is a separate job: ``jsonschema``'s own
messages are written for schema authors and say things like *"is not valid
under any of the given schemas"*, which tells a maintainer nothing about their
``codemeta.json``.
"""

from __future__ import annotations

import json
import re
from typing import Any

import jsonschema
from jsonschema import ValidationError
from jsonschema.exceptions import best_match

from ..adapters.codemeta import FEATURE_LIST, any_feature_list_key
from ..concepts import location
from ..diagnostics import Severity
from ..locate import Path as DocPath
from ..locate import format_path
from ..report import Diagnostic
from .context import ProfileContext
from .formats import reports_on as format_reports_on
from .types import reports_on as type_reports_on

__all__ = ["check_schema", "json_type", "missing_property"]


def missing_property(error: ValidationError) -> str | None:
    """Extract the property name from a ``required`` validation error.

    Parameters
    ----------
    error : ValidationError
        A ``jsonschema`` error with validator ``required``.

    Returns
    -------
    str or None
        The missing property name, or ``None`` if the message is not in the
        expected form.

    Examples
    --------
    >>> from jsonschema import ValidationError
    >>> missing_property(ValidationError("'license' is a required property"))
    'license'
    >>> missing_property(ValidationError("something else")) is None
    True
    """
    match = re.match(r"^'([^']+)' is a required property$", error.message)
    return match.group(1) if match else None


def json_type(value: Any) -> str:
    """Name a value's JSON type, for a message a user will read.

    Parameters
    ----------
    value : Any
        A parsed JSON value.

    Returns
    -------
    str
        The JSON type name.

    Examples
    --------
    >>> json_type("MyTool"), json_type(1), json_type(1.5)
    ('string', 'number', 'number')
    >>> json_type([]), json_type({}), json_type(None)
    ('array', 'object', 'null')

    ``bool`` is checked before ``int``, which it subclasses in Python:

    >>> json_type(True)
    'boolean'
    """
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    return {
        int: "number",
        float: "number",
        str: "string",
        list: "array",
        dict: "object",
    }.get(type(value), type(value).__name__)


def _is_small(value: Any) -> bool:
    """Whether a value is worth echoing back in a diagnostic."""
    return isinstance(value, (str, int, float, bool)) or value is None


def _is_empty(value: Any) -> bool:
    """Whether a value is an empty string, list or object.

    Examples
    --------
    >>> _is_empty(""), _is_empty("   "), _is_empty([]), _is_empty({})
    (True, True, True, True)
    >>> _is_empty("x"), _is_empty([1]), _is_empty(0)
    (False, False, False)
    """
    return isinstance(value, (str, list, dict)) and not (
        value.strip() if isinstance(value, str) else value
    )


def check_schema(ctx: ProfileContext) -> list[Diagnostic]:
    """Validate the record against the profile schema and translate the errors.

    Parameters
    ----------
    ctx : ProfileContext
        The record under validation.

    Returns
    -------
    list of Diagnostic
        Structural findings, ordered by position in the document.

    Notes
    -----
    Three classes of error are suppressed here because a dedicated check
    reports them better:

    * a missing ``@context``, which :func:`~.jsonld.check_context` explains;
    * a missing ``schema:featureList`` when the document spells the property
      some other way, which :func:`~.jsonld.check_feature_list` explains;
    * a value of the wrong kind in a property CodeMeta does not type as
      ``Text``, which :func:`~.types.check_types` explains — it names the
      required node form and prints a corrected value, where the schema can
      only say the value matched no accepted shape.

    Reporting any of them twice would present one mistake as two problems.

    Examples
    --------
    A missing mandatory field is named, with the schema's own description as
    remediation:

    >>> ctx = ProfileContext.for_document({"name": "MyTool"})
    >>> findings = {d.property: d.code for d in check_schema(ctx)}
    >>> findings["license"]
    'profile.required-field'
    >>> findings["version"]
    'profile.required-field'

    A wrong type says what was expected and what was found:

    >>> ctx = ProfileContext.for_document({"name": 42})
    >>> next(d.message for d in check_schema(ctx) if d.property == "name")
    'codemeta.json: name must be string, but a number was given.'

    Software has one name, so two of them is an error about cardinality, not
    about the type of either:

    >>> ctx = ProfileContext.for_document({"name": ["a", "b"]})
    >>> next(d.message for d in check_schema(ctx) if d.property == "name")
    'codemeta.json: name takes a single value, but 2 were given.'

    A one-element array is the same as a bare value in JSON-LD, and passes:

    >>> ctx = ProfileContext.for_document({"name": ["MyTool"]})
    >>> [d for d in check_schema(ctx) if d.property == "name"]
    []

    An empty value is reported as empty, not as "matches no accepted shape":

    >>> ctx = ProfileContext.for_document({"funding": []})
    >>> next(d.message for d in check_schema(ctx) if d.property == "funding")
    'codemeta.json: funding is empty. Leave the property out...value.'

    A missing ``@context`` is left to the context check:

    >>> ctx = ProfileContext.for_document({"name": "MyTool"})
    >>> [d for d in check_schema(ctx) if d.property == "@context"]
    []
    """
    validator = jsonschema.Draft202012Validator(ctx.schema)
    mandatory = set(ctx.policy["mandatory"])
    # A document that spells the property some other way has a specific, more
    # useful diagnostic already; adding "the field is missing" on top would
    # report one mistake twice.
    alias_present = any_feature_list_key(ctx.document) is not None
    diagnostics: list[Diagnostic] = []

    for error in sorted(validator.iter_errors(ctx.document), key=lambda e: str(e.path)):
        if error.validator == "required":
            missing = missing_property(error)
            if missing is None:
                continue
            if missing == "@context":
                continue
            if missing == FEATURE_LIST and alias_present:
                continue
            if not error.path and missing in mandatory:
                diagnostics.append(_required_field(ctx, missing))
                continue
        if _owned_by_a_value_check(error):
            continue
        diagnostics.append(_translate(ctx, error))
    return diagnostics


def _owned_by_a_value_check(error: ValidationError) -> bool:
    """Whether a dedicated value check will report this failure better.

    Those checks know the required node form, or what a date should look like,
    and can print a corrected value; the schema can only say the value matched
    no branch or no pattern. The decision is delegated to the checks themselves
    so they cannot disagree about which failures are covered.

    Examples
    --------
    A bare string where a node is required is left to the type check:

    >>> from jsonschema import Draft202012Validator
    >>> from ..vocabulary import profile_schema
    >>> def owned(document):
    ...     errors = Draft202012Validator(profile_schema()).iter_errors(document)
    ...     return [_owned_by_a_value_check(e) for e in errors if e.path]
    >>> owned({"license": "Apache-2.0"})
    [True]

    So is a date the schema's pattern rejects, which :mod:`.formats` explains
    in terms of ISO 8601 rather than of a regex:

    >>> owned({"datePublished": "01/06/2026"})
    [True]

    A structural failure is still the schema's to report — nothing else would
    mention an empty array, so suppressing it would lose the finding entirely:

    >>> owned({"author": []})
    [False]
    >>> owned({"name": ["a", "b"]})
    [False]
    """
    if not error.absolute_path:
        return False
    if error.validator not in {"oneOf", "anyOf", "type", "pattern", "format"}:
        return False
    name = str(error.absolute_path[0])
    return type_reports_on(name, error.instance) or format_reports_on(
        name, error.instance
    )


def _required_field(ctx: ProfileContext, name: str) -> Diagnostic:
    """Build the diagnostic for an absent mandatory field."""
    return ctx.diagnostic(
        "profile.required-field",
        Severity.ERROR,
        f'{ctx.file} is missing the mandatory property "{name}" '
        f"({ctx.title(name).lower()}).",
        suggestion=_required_field_hint(ctx, name),
        prop=name,
    )


def _required_field_hint(ctx: ProfileContext, name: str) -> str:
    """Remediation for a missing field, taken from the schema's own text."""
    entry = ctx.schema.get("properties", {}).get(name, {})
    description = entry.get("description")
    examples = entry.get("examples") or []
    if description and examples:
        return f"{description} Example: {json.dumps(examples[0])}"
    return description or "See docs/using/profile.md for the accepted value shapes."


def _too_many_values(error: ValidationError) -> bool:
    """Whether an array failed only because the property takes one value.

    Cardinality is the profile's own rule, so the message should say so rather
    than complain about the type: each item may be perfectly valid.
    """
    if not isinstance(error.instance, list) or len(error.instance) < 2:
        return False
    branches = error.validator_value
    if not isinstance(branches, list):
        return False
    return any(
        isinstance(branch, dict) and branch.get("maxItems") == 1 for branch in branches
    )


def _one_json_type(error: ValidationError) -> str | None:
    """The single JSON type an ``anyOf`` accepts, when there is only one.

    A generated property is ``anyOf: [<value>, <array of value>]``, so a value
    of the wrong kind fails every branch and ``jsonschema`` can only say it
    matched none of them. When the branches agree on a JSON type, the useful
    message is that one.
    """
    branches = error.validator_value
    if not isinstance(branches, list):
        return None
    named: set[str] = set()
    for branch in branches:
        if not isinstance(branch, dict):
            return None
        if branch.get("type") == "array":
            named.add("array")
        elif isinstance(branch.get("type"), str):
            named.add(branch["type"])
        elif "$ref" in branch:
            named.add(
                {"NonEmptyText": "string", "AbsoluteUri": "string"}.get(
                    str(branch["$ref"]).rsplit("/", 1)[-1], ""
                )
            )
        else:
            return None
    named.discard("array")
    if len(named) == 1 and next(iter(named)):
        return next(iter(named))
    return None


def _translate(ctx: ProfileContext, error: ValidationError) -> Diagnostic:
    """Render one ``jsonschema`` error as a diagnostic a maintainer can act on."""
    path: DocPath = tuple(error.absolute_path)
    prop = str(path[0]) if path else None
    rendered = format_path(path) or "the document root"
    value = error.instance if _is_small(error.instance) else None

    if _is_empty(error.instance):
        # Checked before the validator kind: an empty value nested inside a
        # oneOf otherwise surfaces as "does not match any shape", which buries
        # the actual problem.
        message = (
            f"{ctx.file}: {rendered} is empty. Leave the property out entirely "
            f"rather than recording an empty value."
        )
        code, severity = "profile.invalid-value", Severity.ERROR
    elif error.validator == "required":
        message = (
            f"{ctx.file}: {rendered} is missing the required property "
            f'"{missing_property(error)}".'
        )
        code, severity = "profile.invalid-value", Severity.ERROR
    elif error.validator == "anyOf" and _too_many_values(error):
        given = error.instance if isinstance(error.instance, list) else []
        message = (
            f"{ctx.file}: {rendered} takes a single value, but {len(given)} were given."
        )
        code, severity = "profile.invalid-value", Severity.ERROR
    elif error.validator == "anyOf" and _one_json_type(error):
        # Every branch accepts the same JSON type, so the value is simply the
        # wrong kind of thing. Saying which beats "matches no accepted shape".
        message = (
            f"{ctx.file}: {rendered} must be {_one_json_type(error)}, but a "
            f"{json_type(error.instance)} was given."
        )
        code, severity = "profile.invalid-type", Severity.ERROR
    elif error.validator == "type":
        expected = error.validator_value
        expected_text = (
            " or ".join(expected) if isinstance(expected, list) else str(expected)
        )
        message = (
            f"{ctx.file}: {rendered} must be {expected_text}, but a "
            f"{json_type(error.instance)} was given."
        )
        code, severity = "profile.invalid-type", Severity.ERROR
    elif error.validator in {"oneOf", "anyOf"}:
        detail = best_match([error])
        reason = detail.message if detail is not error else ""
        message = (
            f"{ctx.file}: {rendered} does not match any shape the profile "
            f"accepts for this property{'. ' + reason if reason else '.'}"
        )
        code, severity = "profile.invalid-type", Severity.ERROR
    elif error.validator in {"minLength", "minItems"}:
        message = (
            f"{ctx.file}: {rendered} is empty. Leave the property out entirely "
            f"rather than recording an empty value."
        )
        code, severity = "profile.invalid-value", Severity.ERROR
    elif error.validator in {"enum", "const"}:
        allowed = error.validator_value
        allowed_list = allowed if isinstance(allowed, list) else [allowed]
        message = (
            f"{ctx.file}: {rendered} must be one of "
            f"{', '.join(repr(item) for item in allowed_list)}."
        )
        code, severity = "profile.invalid-value", Severity.ERROR
    else:
        message = f"{ctx.file}: {rendered} is not valid — {error.message}"
        code, severity = "profile.invalid-value", Severity.ERROR

    return Diagnostic(
        code=code,
        severity=severity,
        message=message,
        property=prop,
        location=location(ctx.parsed, path, value),
        suggestion=ctx.description(str(path[0])) if path else None,
    )
