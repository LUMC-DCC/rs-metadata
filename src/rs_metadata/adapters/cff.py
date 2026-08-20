"""Adapter for ``CITATION.cff``.

CITATION.cff is required alongside codemeta.json, so it is the one
optional-looking file whose absence is an error: GitHub reads it for the "Cite
this repository" button and Zenodo reads it when archiving a release, so
without it the software is not citable through either. It is validated
against the official Citation File Format 1.2.0 JSON Schema, vendored into the
package, before any comparison is attempted: comparing against a file that is
not valid CFF would produce findings about the wrong problem.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import jsonschema
import yaml

from ..concepts import ConceptMap, ParsedSource, add, add_each, dig, location
from ..diagnostics import Severity
from ..locate import format_path, yaml_source_map
from ..normalize import as_list
from ..report import Diagnostic, Location
from ..vocabulary import cff_schema
from .base import Adapter, SourceError

#: The filename GitHub and Zenodo look for. Any other casing is invisible to
#: them even though the file parses perfectly.
CANONICAL_FILENAME = "CITATION.cff"

SUPPORTED_VERSIONS = {"1.2.0"}


class _CffLoader(yaml.SafeLoader):
    """A YAML loader that leaves dates as written.

    PyYAML resolves ``date-released: 2026-06-01`` to a ``datetime.date``,
    but the Citation File Format specifies that field as a *string* in
    ISO 8601 form. Resolving it would make a valid file fail its own schema.
    """


_CffLoader.yaml_implicit_resolvers = {
    key: [
        (tag, regexp)
        for tag, regexp in resolvers
        if tag != "tag:yaml.org,2002:timestamp"
    ]
    for key, resolvers in _CffLoader.yaml_implicit_resolvers.items()
}


def _raw_top_level_scalars(text: str) -> dict[str, str]:
    """Recover the text of top-level scalars exactly as it was written.

    An unquoted ``version: 1.20`` is a YAML float, and ``1.20`` and ``1.2``
    are the same float. Reading the original scalar avoids silently comparing
    a version the author never wrote.
    """
    try:
        root = yaml.compose(text, Loader=_CffLoader)
    except yaml.YAMLError:
        return {}
    if not isinstance(root, yaml.MappingNode):
        return {}
    return {
        key.value: value.value
        for key, value in root.value
        if isinstance(key, yaml.ScalarNode) and isinstance(value, yaml.ScalarNode)
    }


class CffAdapter(Adapter):
    id = "cff"
    format = "Citation File Format"
    role = "required"
    filenames = (CANONICAL_FILENAME,)
    mapping_name = "cff-1.2.0"

    def parse(self, path: Path, relative: str) -> ParsedSource:
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as error:
            raise SourceError(f"{relative} could not be read: {error}") from error
        try:
            document = yaml.load(text, Loader=_CffLoader)
        except yaml.YAMLError as error:
            mark = getattr(error, "problem_mark", None)
            raise SourceError(
                f"{relative} is not valid YAML: {error}",
                line=(mark.line + 1) if mark else None,
            ) from error
        if not isinstance(document, dict):
            raise SourceError(
                f"{relative} must contain a YAML mapping of citation fields."
            )

        raw = _raw_top_level_scalars(text)
        # Prefer the version exactly as written over PyYAML's interpretation.
        if "version" in document and "version" in raw:
            document["version"] = raw["version"]

        return ParsedSource(
            adapter_id=self.id,
            file=relative,
            format=self.format,
            format_version=str(document.get("cff-version") or "") or None,
            document=document,
            source_map=yaml_source_map(text),
        )

    # -- source validation ------------------------------------------------

    def validate_source(self, parsed: ParsedSource) -> list[Diagnostic]:
        document: dict[str, Any] = parsed.document
        diagnostics: list[Diagnostic] = []

        if Path(parsed.file).name != CANONICAL_FILENAME:
            diagnostics.append(
                Diagnostic(
                    code="source.invalid",
                    severity=Severity.WARNING,
                    message=(
                        f"{parsed.file} is spelled differently from "
                        f"{CANONICAL_FILENAME}. GitHub and Zenodo match the "
                        f"filename exactly, so this file will not produce a "
                        f'"Cite this repository" button.'
                    ),
                    location=Location(file=parsed.file),
                    suggestion=f"Rename the file to {CANONICAL_FILENAME}.",
                )
            )

        declared = str(document.get("cff-version") or "").strip()
        if not declared:
            diagnostics.append(
                Diagnostic(
                    code="source.invalid",
                    severity=Severity.ERROR,
                    message=(
                        f"{parsed.file} does not declare cff-version, so its "
                        f"format cannot be determined."
                    ),
                    location=location(parsed, ("cff-version",)),
                    suggestion="Add `cff-version: 1.2.0` as the first line.",
                )
            )
            return diagnostics

        if declared not in SUPPORTED_VERSIONS:
            diagnostics.append(
                Diagnostic(
                    code="source.invalid",
                    severity=Severity.ERROR,
                    message=(
                        f"{parsed.file} declares cff-version {declared}, but "
                        f"rs-metadata validates version "
                        f"{', '.join(sorted(SUPPORTED_VERSIONS))}."
                    ),
                    location=location(parsed, ("cff-version",), declared),
                    suggestion=(
                        "Upgrade the file to CFF 1.2.0, the version the LUMC "
                        "guide and current tooling expect."
                    ),
                )
            )
            return diagnostics

        diagnostics.extend(self._schema_diagnostics(parsed))

        kind = document.get("type")
        if kind is not None and kind != "software":
            diagnostics.append(
                Diagnostic(
                    code="source.invalid",
                    severity=Severity.WARNING,
                    message=(
                        f"{parsed.file} declares type {kind!r}, but it accompanies "
                        f"a software metadata record."
                    ),
                    location=location(parsed, ("type",), kind),
                    suggestion="Set `type: software`.",
                )
            )
        return diagnostics

    def _schema_diagnostics(self, parsed: ParsedSource) -> list[Diagnostic]:
        validator = jsonschema.Draft7Validator(cff_schema())
        diagnostics = []
        for error in sorted(validator.iter_errors(parsed.document), key=str):
            path = tuple(error.absolute_path)
            diagnostics.append(
                Diagnostic(
                    code="source.invalid",
                    severity=Severity.ERROR,
                    message=(
                        f"{parsed.file} does not satisfy the Citation File "
                        f"Format 1.2.0 schema"
                        f"{' at ' + format_path(path) if path else ''}: "
                        f"{error.message}"
                    ),
                    location=location(parsed, path),
                    suggestion=(
                        "See the CFF schema guide: https://github.com/"
                        "citation-file-format/citation-file-format/blob/main/"
                        "schema-guide.md"
                    ),
                )
            )
        return diagnostics

    # -- mapping ----------------------------------------------------------

    def map_to_codemeta(self, parsed: ParsedSource) -> ConceptMap:
        document: dict[str, Any] = parsed.document
        concepts: ConceptMap = {}

        add(concepts, "name", document.get("title"), ("title",))
        add(concepts, "description", document.get("abstract"), ("abstract",))
        add(concepts, "version", document.get("version"), ("version",))
        add_each(concepts, "author", document.get("authors"), ("authors",))
        add(
            concepts,
            "codeRepository",
            document.get("repository-code"),
            ("repository-code",),
        )
        add(concepts, "url", document.get("url"), ("url",))
        add(
            concepts,
            "downloadUrl",
            document.get("repository-artifact"),
            ("repository-artifact",),
        )
        add(
            concepts,
            "datePublished",
            document.get("date-released"),
            ("date-released",),
        )
        add_each(concepts, "keywords", document.get("keywords"), ("keywords",))

        # `license` may be a single SPDX identifier or a list of them.
        # `license-url` is a fallback rather than an additional value: adding
        # both would invent a second license the file never claimed.
        if document.get("license") is not None:
            add_each(concepts, "license", document.get("license"), ("license",))
        elif document.get("license-url") is not None:
            add(concepts, "license", document.get("license-url"), ("license-url",))

        add(concepts, "identifier", document.get("doi"), ("doi",))
        for index, entry in enumerate(as_list(document.get("identifiers"))):
            if isinstance(entry, dict) and entry.get("value") is not None:
                add(
                    concepts,
                    "identifier",
                    entry.get("value"),
                    ("identifiers", index, "value"),
                )

        preferred = document.get("preferred-citation")
        if isinstance(preferred, dict) and preferred.get("doi"):
            add(
                concepts,
                "referencePublication",
                preferred.get("doi"),
                ("preferred-citation", "doi"),
            )
            # The same work, under the concept CodeMeta uses for "cite this
            # rather than the software itself".
            add(
                concepts,
                "citation",
                preferred.get("doi"),
                ("preferred-citation", "doi"),
            )

        # A CFF `identifiers` entry of type `url` is another address for this
        # same work, which is what sameAs means.
        for index, entry in enumerate(as_list(document.get("identifiers"))):
            if isinstance(entry, dict) and entry.get("type") == "url":
                add(
                    concepts,
                    "sameAs",
                    entry.get("value"),
                    ("identifiers", index, "value"),
                )

        contacts = dig(document, "contact")
        if isinstance(contacts, list):
            add_each(concepts, "maintainer", contacts, ("contact",))

        # Extracted only so the report can say the field was seen and
        # deliberately not compared. The mapping marks it `comparable: false`
        # because CFF references are a bibliography, not a dependency list.
        add_each(
            concepts,
            "softwareRequirements",
            document.get("references"),
            ("references",),
        )

        return concepts
