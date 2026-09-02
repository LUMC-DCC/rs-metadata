"""The vocabularies the profile is built on, and everything derived from them.

A vocabulary answers three questions about a property: what its value may be,
what it means, and — for a class — what it descends from. rs-metadata never
answers any of those itself. They are fetched from upstream by
``scripts/vendor_reference_data.py``, stored in ``data/``, and read here.

============================ ==========================================
Module                       Holds
============================ ==========================================
:mod:`.loader`               Reading a packaged file
:mod:`.properties`           Per-property value types and definitions
:mod:`.classes`              schema.org's class hierarchy and subtyping
:mod:`.documents`            Schemas, controlled vocabularies, rule data
============================ ==========================================

Adding a vocabulary means adding an entry to ``profile/lumc-codemeta.yaml``
and a loader to the vendoring script. Nothing in this package names a
particular vocabulary except where the data itself does.
"""

from __future__ import annotations

from .classes import satisfies, schema_org_classes, subclasses
from .documents import (
    PROJECT_OWNED_DATA,
    biotools_schema,
    cff_schema,
    codemeta_crosswalks,
    codemeta_versions,
    concept_order,
    format_hints,
    placeholders,
    profile_field_policy,
    profile_schema,
    provenance,
    report_schema,
    spdx_index,
    spdx_licenses,
    vocabularies,
)
from .properties import (
    LITERAL_TYPES,
    agent_properties,
    allows_text,
    codemeta_terms,
    codemeta_types,
    type_entry,
)

__all__ = [
    "LITERAL_TYPES",
    "PROJECT_OWNED_DATA",
    "agent_properties",
    "allows_text",
    "biotools_schema",
    "cff_schema",
    "codemeta_crosswalks",
    "codemeta_terms",
    "codemeta_types",
    "codemeta_versions",
    "concept_order",
    "format_hints",
    "placeholders",
    "profile_field_policy",
    "profile_schema",
    "provenance",
    "report_schema",
    "satisfies",
    "schema_org_classes",
    "spdx_index",
    "spdx_licenses",
    "subclasses",
    "type_entry",
    "vocabularies",
]
