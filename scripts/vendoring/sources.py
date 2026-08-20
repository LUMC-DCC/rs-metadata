"""The upstream sources, declared once, and the code that downloads them.

Every vendored file traces back to an entry here. Declaring a source as data
rather than as another block of fetch-and-hash statements is what keeps
provenance honest: the URL a file was built from, the checksum recorded beside
it and the license attributed to it all come from the same record, so they
cannot drift apart.
"""

from __future__ import annotations

import json
import urllib.request
from dataclasses import dataclass
from functools import cached_property
from hashlib import sha256
from typing import Any, cast

USER_AGENT = (
    "rs-metadata-vendoring-script/1.0 (+https://github.com/LUMC-DCC/rs-metadata)"
)

JSON_LD = "application/ld+json"


@dataclass(frozen=True)
class Source:
    """One upstream document rs-metadata vendors."""

    #: Key used in ``provenance.json`` and in an artifact's source list.
    key: str
    #: Human-readable name, used only in the script's progress output.
    label: str
    url: str
    #: Upstream version, as that upstream expresses it.
    version: str
    #: License the upstream publishes under, recorded for attribution.
    license: str
    #: Some servers need to be told what we want. w3id.org in particular
    #: serves the CodeMeta context by content negotiation, and without an
    #: explicit JSON-LD Accept header it redirects to HTML documentation.
    accept: str = "*/*"


@dataclass(frozen=True)
class Download:
    """A fetched source: the bytes, and the views a parser wants of them."""

    source: Source
    raw: bytes

    @cached_property
    def text(self) -> str:
        return self.raw.decode("utf-8", "replace")

    @cached_property
    def json(self) -> Any:
        return json.loads(self.raw)

    @cached_property
    def sha256(self) -> str:
        return sha256(self.raw).hexdigest()


SOURCES: dict[str, Source] = {
    source.key: source
    for source in (
        Source(
            key="codemeta",
            label="CodeMeta 3.1 context",
            url="https://w3id.org/codemeta/3.1",
            version="3.1",
            license="Apache-2.0",
            accept=JSON_LD,
        ),
        # CodeMeta's own property table is the authoritative statement of what
        # each property's value may be: CodeMeta narrows schema.org for its own
        # profile (`maintainer` is Person here but Person-or-Organization
        # upstream, `softwareRequirements` is SoftwareSourceCode here but
        # includes Text upstream). It covers every property the 3.1 context
        # defines; properties CodeMeta leaves out of that context, such as
        # `featureList`, come from schema.org instead.
        Source(
            key="codemeta-properties",
            label="CodeMeta property table",
            url=(
                "https://raw.githubusercontent.com/codemeta/codemeta/3.1/"
                "properties_description.csv"
            ),
            version="3.1",
            license="Apache-2.0",
        ),
        # CodeMeta narrows schema.org and is therefore authoritative wherever
        # both define a property, but CodeMeta deliberately leaves some
        # properties out of its context, and those have to be typed from
        # somewhere. This is that somewhere.
        Source(
            key="schema-org",
            label="schema.org vocabulary",
            url="https://schema.org/version/latest/schemaorg-current-https.jsonld",
            version="current",
            license="CC-BY-SA-3.0",
            accept=JSON_LD,
        ),
        # repostatus.org publishes its vocabulary as SKOS. The bare term after
        # the fragment is the value `developmentStatus` takes.
        Source(
            key="repostatus",
            label="repostatus vocabulary",
            url="https://www.repostatus.org/badges/latest/ontology.jsonld",
            version="latest",
            license="CC-BY-SA-4.0",
            accept=JSON_LD,
        ),
        # bio.tools publishes its tool-type list inside its JSON Schema.
        # Fetching it rather than copying it is how "Mobile application"
        # arrived without anyone noticing it had been added upstream.
        Source(
            key="biotools-tool-type",
            label="bio.tools schema",
            url=(
                "https://raw.githubusercontent.com/bio-tools/biotoolsSchema/"
                "main/jsonschema/biotoolsj.json"
            ),
            version="main",
            license="CC-BY-4.0",
        ),
        # R ships the authoritative mapping from the license strings CRAN
        # accepts to SPDX identifiers, in the same file `tools::analyze_license`
        # reads.
        Source(
            key="r-licenses",
            label="R license database",
            url=(
                "https://raw.githubusercontent.com/wch/r-source/trunk/share/"
                "licenses/license.db"
            ),
            version="r-devel",
            license="GPL-2.0-or-later",
        ),
        # PEP 753 defines the well-known `[project.urls]` labels and their
        # aliases. The table is the normative one; the canonical spec on
        # packaging.python.org is generated from this same PEP.
        Source(
            key="pep-753",
            label="PEP 753",
            url="https://raw.githubusercontent.com/python/peps/main/peps/pep-0753.rst",
            version="PEP 753",
            license="CC0-1.0",
        ),
        Source(
            key="citation-file-format",
            label="CFF 1.2.0 schema",
            url=(
                "https://raw.githubusercontent.com/citation-file-format/"
                "citation-file-format/1.2.0/schema.json"
            ),
            version="1.2.0",
            license="CC-BY-4.0",
        ),
        # CodeMeta maintains a crosswalk per ecosystem. These say which
        # source field corresponds to which CodeMeta property; the comparison
        # policy built on top of them is rs-metadata's own.
        Source(
            key="crosswalk-cff",
            label="CodeMeta crosswalk: Citation File Format",
            url=(
                "https://raw.githubusercontent.com/codemeta/codemeta/master/crosswalks/"
                "Citation%20File%20Format%201.2.0.csv"
            ),
            version="master",
            license="Apache-2.0",
        ),
        Source(
            key="crosswalk-zenodo",
            label="CodeMeta crosswalk: Zenodo",
            url=(
                "https://raw.githubusercontent.com/codemeta/codemeta/master/crosswalks/"
                "Zenodo.csv"
            ),
            version="master",
            license="Apache-2.0",
        ),
        Source(
            key="crosswalk-python",
            label="CodeMeta crosswalk: Python PKG-INFO",
            url=(
                "https://raw.githubusercontent.com/codemeta/codemeta/master/crosswalks/"
                "Python%20PKG-INFO.csv"
            ),
            version="master",
            license="Apache-2.0",
        ),
        Source(
            key="crosswalk-nodejs",
            label="CodeMeta crosswalk: NodeJS",
            url=(
                "https://raw.githubusercontent.com/codemeta/codemeta/master/crosswalks/"
                "NodeJS.csv"
            ),
            version="master",
            license="Apache-2.0",
        ),
        Source(
            key="crosswalk-r",
            label="CodeMeta crosswalk: R Package Description",
            url=(
                "https://raw.githubusercontent.com/codemeta/codemeta/master/crosswalks/"
                "R%20Package%20Description.csv"
            ),
            version="master",
            license="Apache-2.0",
        ),
        Source(
            key="crosswalk-github",
            label="CodeMeta crosswalk: GitHub",
            url=(
                "https://raw.githubusercontent.com/codemeta/codemeta/master/"
                "crosswalks/GitHub.csv"
            ),
            version="master",
            license="Apache-2.0",
        ),
        Source(
            key="crosswalk-cargo",
            label="CodeMeta crosswalk: Cargo",
            url=(
                "https://raw.githubusercontent.com/codemeta/codemeta/master/crosswalks/"
                "Cargo.csv"
            ),
            version="master",
            license="Apache-2.0",
        ),
        Source(
            key="crosswalk-julia",
            label="CodeMeta crosswalk: Julia Project.toml",
            url=(
                "https://raw.githubusercontent.com/codemeta/codemeta/master/crosswalks/"
                "Julia%20Project.csv"
            ),
            version="master",
            license="Apache-2.0",
        ),
        Source(
            key="spdx-license-list",
            label="SPDX license list",
            url=(
                "https://raw.githubusercontent.com/spdx/license-list-data/"
                "main/json/licenses.json"
            ),
            version="main",
            license="CC0-1.0",
        ),
    )
}


def fetch(source: Source) -> Download:
    """Download one source. The only network access in the whole project."""
    request = urllib.request.Request(
        source.url, headers={"User-Agent": USER_AGENT, "Accept": source.accept}
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        return Download(source=source, raw=cast(bytes, response.read()))


def fetch_all(announce: bool = True) -> dict[str, Download]:
    """Download every declared source, keyed the same way :data:`SOURCES` is."""
    downloads = {}
    for key, source in SOURCES.items():
        if announce:
            print(f"Fetching {source.label} from {source.url}")
        downloads[key] = fetch(source)
    return downloads
