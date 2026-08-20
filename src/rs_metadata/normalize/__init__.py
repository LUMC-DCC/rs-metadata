"""Normalization and comparison strategies.

A crosswalk says *which* concepts correspond. This package decides **when two
representations of a concept are the same thing**, which is a separate and much
harder question: ``https://spdx.org/licenses/Apache-2.0`` and ``Apache-2.0``
are the same license, ``https://doi.org/10.5281/zenodo.1`` and
``10.5281/zenodo.1`` are the same DOI, and ``J. Doe`` and ``Jane Doe`` are
probably the same person.

Getting this wrong in the lenient direction hides real problems; getting it
wrong in the strict direction produces false alarms, and a validator that
cries wolf gets removed from CI. Where a judgement is genuinely ambiguous the
strategy reports *not comparable* rather than guessing.

One module per kind of value, because the rules have nothing in common:

======================= =================================================
Module                  Concern
======================= =================================================
:mod:`.scalars`         Reducing nodes to scalars; text and name keys
:mod:`.versions`        Release identity, including commit hashes
:mod:`.uris`            URL spellings that address one resource
:mod:`.licenses`        SPDX identifiers and expressions
:mod:`.identifiers`     DOIs, ORCIDs, RORs, EDAM terms, dates
:mod:`.people`          Author matching, the hardest case
:mod:`.requirements`    Dependency notations across ecosystems
:mod:`.strategies`      The strategy registry the engine drives
======================= =================================================

Examples
--------
>>> normalize_license("apache-2.0") == normalize_license(
...     "https://spdx.org/licenses/Apache-2.0"
... )
True
>>> get_strategy("version").compare(["1.2.0"], ["v1.2"]).identical
True
"""

from __future__ import annotations

from .best_effort import BestEffortStrategy
from .identifiers import (
    EDAM_RE,
    extract_doi,
    extract_orcid,
    extract_ror,
    normalize_date,
    orcid_checksum_valid,
    ror_checksum_valid,
)
from .licenses import (
    SPDX_OPERATORS,
    SPDX_URL_PREFIX,
    normalize_license,
    spdx_identifier,
)
from .people import (
    PersonRecord,
    given_names_compatible,
    people_match,
    person_record,
    split_full_name,
)
from .requirements import Requirement, constraints_equivalent, parse_requirement
from .scalars import (
    IDENTITY_FIRST,
    LABEL_FIRST,
    as_list,
    normalize_loose_name,
    normalize_package_name,
    normalize_text,
    scalarize,
)
from .strategies import (
    STRATEGIES,
    ComparisonResult,
    Conflict,
    Strategy,
    get_strategy,
)
from .uris import normalize_uri
from .versions import looks_like_commit, normalize_version

__all__ = [
    "EDAM_RE",
    "IDENTITY_FIRST",
    "LABEL_FIRST",
    "SPDX_OPERATORS",
    "SPDX_URL_PREFIX",
    "STRATEGIES",
    "BestEffortStrategy",
    "ComparisonResult",
    "Conflict",
    "PersonRecord",
    "Requirement",
    "Strategy",
    "as_list",
    "constraints_equivalent",
    "extract_doi",
    "extract_orcid",
    "extract_ror",
    "get_strategy",
    "given_names_compatible",
    "looks_like_commit",
    "normalize_date",
    "normalize_license",
    "normalize_loose_name",
    "normalize_package_name",
    "normalize_text",
    "normalize_uri",
    "normalize_version",
    "orcid_checksum_valid",
    "parse_requirement",
    "people_match",
    "person_record",
    "ror_checksum_valid",
    "scalarize",
    "spdx_identifier",
    "split_full_name",
]

# Registered here rather than in `strategies`, which `best_effort` builds on
# and therefore cannot import. Importing any submodule runs this first, so the
# registry is always complete by the time `get_strategy` is called.

STRATEGIES.setdefault(BestEffortStrategy.name, BestEffortStrategy())
