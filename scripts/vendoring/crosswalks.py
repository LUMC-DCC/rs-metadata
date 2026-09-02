"""Parser for CodeMeta's published crosswalk tables.

CodeMeta maintains a crosswalk per ecosystem under ``crosswalks/`` in its own
repository: a CSV whose rows are ``CodeMeta property, source field``. They say
which field corresponds to which, and nothing about how strictly the two should
be expected to agree — that judgement is the mapping files' job, and stays
there.

Vendoring them is what makes a mapping's provenance checkable rather than
asserted. A claim that a correspondence is rs-metadata's own invention can then
be tested against the upstream table instead of taken on trust.

A row's property name may repeat, because the tables describe nested agent
fields (a person's ``name`` and ``email``) in the same flat list as the
software's own. Values are therefore collected per property rather than
overwriting.
"""

from __future__ import annotations

import csv
import io
from typing import Any

from .sources import SOURCES


def parse_crosswalk(csv_text: str) -> dict[str, list[str]]:
    """Read one crosswalk CSV into ``{property: [source fields]}``.

    Examples
    --------
    >>> parse_crosswalk("Property,Cargo\\nname,package.name\\nreview,\\n")
    {'name': ['package.name']}

    A property named twice keeps both correspondences, which is how the tables
    describe an agent's own fields alongside the software's:

    >>> parse_crosswalk("Property,X\\nname,title\\nname,person.name\\n")
    {'name': ['title', 'person.name']}
    """
    properties: dict[str, list[str]] = {}
    for row in csv.reader(io.StringIO(csv_text)):
        if len(row) < 2:
            continue
        name, value = row[0].strip(), row[1].strip()
        if not name or not value or name.casefold() == "property":
            continue
        properties.setdefault(name, [])
        if value not in properties[name]:
            properties[name].append(value)
    return properties


def build_crosswalks(downloads: dict[str, Any]) -> dict[str, Any]:
    """Index every vendored crosswalk by the mapping id that uses it."""
    tables = {}
    for mapping_id, key in CROSSWALK_SOURCES.items():
        source = SOURCES[key]
        tables[mapping_id] = {
            "source": source.url,
            "format": source.label,
            "properties": parse_crosswalk(downloads[key].text),
        }
    return {
        "$comment": (
            "CodeMeta's own crosswalk tables, one per mapping that has an "
            "upstream. They state which source field corresponds to which "
            "CodeMeta property; the comparison policy for each is decided in "
            "src/rs_metadata/mappings and is not upstream."
        ),
        "crosswalks": dict(sorted(tables.items())),
    }


#: Mapping id in ``src/rs_metadata/mappings`` mapped to the source key of the
#: CodeMeta crosswalk it derives from. A mapping with no entry here has no
#: upstream table, and says so in its own provenance.
CROSSWALK_SOURCES = {
    "cff-1.2.0": "crosswalk-cff",
    "biotools": "crosswalk-biotools",
    "zenodo": "crosswalk-zenodo",
    "pyproject-pep621": "crosswalk-python",
    "package-json": "crosswalk-nodejs",
    "r-description": "crosswalk-r",
    "cargo": "crosswalk-cargo",
    "github": "crosswalk-github",
    "julia-project": "crosswalk-julia",
}
