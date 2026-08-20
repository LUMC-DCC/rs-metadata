"""Validation of ``codemeta.json`` against the LUMC profile.

Three layers, deliberately separated:

*Types* come from CodeMeta's own property table, vendored into
``data/codemeta-3.1-types.json`` and enforced by :mod:`.types`. They are
derived from upstream, never transcribed, because hand-reading the terms table
got several properties wrong.

*Structure* is checked by the JSON Schema in
``schema/codemeta-lumc.schema.json``, which is also usable on its own — point
an editor at it and get completion and inline errors while writing the file.

*Meaning* is checked by the remaining modules, because no schema can verify an
ORCID's check digit, tell an EDAM operation from an EDAM topic, or produce an
error message a person would want to read. Every schema error is translated
into a diagnostic that names the field, shows the value and says what to do.

Each check family is a plain function over a :class:`~.context.ProfileContext`,
so it can be exercised on a bare dictionary with no files and no pipeline:

============================ ==========================================
Module                       Checks
============================ ==========================================
:mod:`.jsonld`               ``@context``, prefixes, property spelling
:mod:`.types`                Value kinds, from CodeMeta's type table
:mod:`.formats`              Lexical form of dates and numbers
:mod:`.schema_checks`        Structure, and readable schema errors
:mod:`.identifiers`          ORCID and ROR check digits, DOI presence
:mod:`.licenses`             SPDX identifiers and deprecations
:mod:`.terminology`          EDAM terms and controlled vocabularies
:mod:`.placeholders`         Template values never filled in
:mod:`.recommendations`      Absent recommended fields, aggregated
============================ ==========================================

Examples
--------
Run the whole profile over a record:

>>> from rs_metadata.concepts import ParsedSource
>>> record = {"@context": "https://w3id.org/codemeta/3.1", "name": "MyTool"}
>>> source = ParsedSource(
...     adapter_id="codemeta", file="codemeta.json", format="CodeMeta",
...     document=record,
... )
>>> codes = {diagnostic.code for diagnostic in validate(source)}
>>> "profile.required-field" in codes
True

Or run one family in isolation, which is how the checks are tested:

>>> ctx = ProfileContext.for_document({"license": "Apache-2.0"})
>>> [diagnostic.code for diagnostic in check_licenses(ctx)]
['profile.invalid-type']
"""

from __future__ import annotations

from .context import ProfileContext
from .formats import check_formats
from .identifiers import check_agents, check_identifiers
from .jsonld import check_context, check_feature_list, check_unknown_properties
from .licenses import check_licenses
from .placeholders import check_placeholders
from .recommendations import check_recommendations
from .runner import CHECKS, validate
from .schema_checks import check_schema
from .terminology import check_edam, check_vocabularies
from .types import check_types

__all__ = [
    "CHECKS",
    "ProfileContext",
    "check_agents",
    "check_context",
    "check_edam",
    "check_feature_list",
    "check_formats",
    "check_identifiers",
    "check_licenses",
    "check_placeholders",
    "check_recommendations",
    "check_schema",
    "check_types",
    "check_unknown_properties",
    "check_vocabularies",
    "validate",
]
