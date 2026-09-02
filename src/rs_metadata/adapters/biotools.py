"""Adapter for ``biotools.json``.

bio.tools describes computational tools in the life sciences. Its JSON format
is an array of tool records, even when a file describes only one tool. This
adapter validates that array against the upstream schema and translates the
parts that correspond to CodeMeta concepts.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import jsonschema

from ..concepts import ConceptMap, ParsedSource, add, add_each, location
from ..diagnostics import Severity
from ..locate import Path as DocPath
from ..locate import format_path, json_source_map
from ..normalize import as_list
from ..report import Diagnostic
from ..vocabulary import biotools_schema
from .base import Adapter, SourceError

SCHEMA_VERSION = "3.3.0"

_CREDIT_CONCEPTS = {
    "Contributor": "contributor",
    "Developer": "contributor",
    "Documentor": "contributor",
    "Maintainer": "maintainer",
    "Primary contact": "maintainer",
    "Provider": "provider",
}

_LINK_CONCEPTS = {
    "Issue tracker": "issueTracker",
    "Repository": "codeRepository",
}


class BiotoolsAdapter(Adapter):
    """Read and validate bio.tools registry metadata."""

    id = "biotools"
    format = "bio.tools metadata"
    role = "optional"
    filenames = ("biotools.json",)
    mapping_name = "biotools"

    def parse(self, path: Path, relative: str) -> ParsedSource:
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as error:
            raise SourceError(f"{relative} could not be read: {error}") from error
        try:
            document = json.loads(text)
        except json.JSONDecodeError as error:
            raise SourceError(
                f"{relative} is not valid JSON: {error.msg} "
                f"(line {error.lineno}, column {error.colno}).",
                line=error.lineno,
            ) from error
        if not isinstance(document, list):
            raise SourceError(f"{relative} must contain an array of bio.tools records.")
        return ParsedSource(
            adapter_id=self.id,
            file=relative,
            format=self.format,
            format_version=SCHEMA_VERSION,
            document=document,
            source_map=json_source_map(text),
        )

    def validate_source(self, parsed: ParsedSource) -> list[Diagnostic]:
        """Validate the document with the vendored bio.tools schema."""
        validator = jsonschema.Draft4Validator(biotools_schema())
        diagnostics = []
        for error in sorted(validator.iter_errors(parsed.document), key=str):
            path = tuple(error.absolute_path)
            diagnostics.append(
                Diagnostic(
                    code="source.invalid",
                    severity=Severity.ERROR,
                    message=(
                        f"{parsed.file} does not satisfy the bio.tools "
                        f"{SCHEMA_VERSION} schema"
                        f"{' at ' + format_path(path) if path else ''}: "
                        f"{error.message}"
                    ),
                    location=location(parsed, path),
                    suggestion=(
                        "Check the bio.tools schema documentation: "
                        "https://github.com/bio-tools/biotoolsSchema/tree/"
                        "main/jsonschema"
                    ),
                )
            )
        return diagnostics

    def map_to_codemeta(self, parsed: ParsedSource) -> ConceptMap:
        concepts: ConceptMap = {}
        for index, tool in enumerate(_objects(parsed.document)):
            base: DocPath = (index,)
            self._add_tool(concepts, tool, base)
        return concepts

    def _add_tool(
        self, concepts: ConceptMap, tool: dict[str, Any], base: DocPath
    ) -> None:
        add(concepts, "name", tool.get("name"), (*base, "name"))
        add(
            concepts,
            "description",
            tool.get("description"),
            (*base, "description"),
        )
        add(concepts, "url", tool.get("homepage"), (*base, "homepage"))
        add_each(concepts, "version", tool.get("version"), (*base, "version"))
        add_each(
            concepts,
            "programmingLanguage",
            tool.get("language"),
            (*base, "language"),
        )
        add_each(
            concepts,
            "operatingSystem",
            tool.get("operatingSystem"),
            (*base, "operatingSystem"),
        )
        add(concepts, "license", tool.get("license"), (*base, "license"))
        add_each(
            concepts,
            "applicationCategory",
            tool.get("toolType"),
            (*base, "toolType"),
        )
        add(
            concepts,
            "developmentStatus",
            tool.get("maturity"),
            (*base, "maturity"),
        )

        self._add_topics(concepts, tool.get("topic"), (*base, "topic"))
        self._add_operations(concepts, tool.get("function"), (*base, "function"))
        self._add_links(concepts, tool.get("link"), (*base, "link"))
        self._add_urls(
            concepts,
            "downloadUrl",
            tool.get("download"),
            (*base, "download"),
        )
        self._add_urls(
            concepts,
            "softwareHelp",
            tool.get("documentation"),
            (*base, "documentation"),
        )
        self._add_publications(
            concepts, tool.get("publication"), (*base, "publication")
        )
        self._add_credits(concepts, tool.get("credit"), (*base, "credit"))

    def _add_topics(self, concepts: ConceptMap, topics: Any, base: DocPath) -> None:
        for index, topic in enumerate(_objects(topics)):
            add(concepts, "keywords", topic.get("term"), (*base, index, "term"))

    def _add_operations(
        self, concepts: ConceptMap, functions: Any, base: DocPath
    ) -> None:
        for function_index, function in enumerate(_objects(functions)):
            for operation_index, operation in enumerate(
                _objects(function.get("operation"))
            ):
                value = operation.get("uri") or operation.get("term")
                key = "uri" if operation.get("uri") else "term"
                add(
                    concepts,
                    "schema:featureList",
                    value,
                    (*base, function_index, "operation", operation_index, key),
                )

    def _add_links(self, concepts: ConceptMap, links: Any, base: DocPath) -> None:
        for index, link in enumerate(_objects(links)):
            roles = {
                _LINK_CONCEPTS[kind]
                for kind in as_list(link.get("type"))
                if kind in _LINK_CONCEPTS
            }
            for concept in roles:
                add(concepts, concept, link.get("url"), (*base, index, "url"))

    def _add_urls(
        self, concepts: ConceptMap, concept: str, entries: Any, base: DocPath
    ) -> None:
        for index, entry in enumerate(_objects(entries)):
            add(concepts, concept, entry.get("url"), (*base, index, "url"))

    def _add_publications(
        self, concepts: ConceptMap, publications: Any, base: DocPath
    ) -> None:
        for index, publication in enumerate(_objects(publications)):
            add(
                concepts,
                "citation",
                publication.get("doi"),
                (*base, index, "doi"),
            )

    def _add_credits(self, concepts: ConceptMap, credits: Any, base: DocPath) -> None:
        for index, credit in enumerate(_objects(credits)):
            agent = _as_agent(credit)
            roles = {
                _CREDIT_CONCEPTS[role]
                for role in as_list(credit.get("typeRole"))
                if role in _CREDIT_CONCEPTS
            }
            for concept in roles:
                add(concepts, concept, agent, (*base, index))


def _objects(value: Any) -> list[dict[str, Any]]:
    """Return the object entries in a JSON array."""
    if not isinstance(value, list):
        return []
    return [entry for entry in value if isinstance(entry, dict)]


def _as_agent(credit: dict[str, Any]) -> dict[str, Any]:
    """Translate a bio.tools credit into a CodeMeta agent shape.

    >>> _as_agent({
    ...     "name": "Josiah Carberry",
    ...     "email": "j@example.org",
    ...     "orcidid": "https://orcid.org/0000-0002-1825-0097",
    ...     "typeRole": ["Maintainer"],
    ... })
    {'name': 'Josiah Carberry', 'email': 'j@example.org', 'identifier': 'https://orcid.org/0000-0002-1825-0097'}
    """
    agent: dict[str, Any] = {}
    for source_key, concept_key in (
        ("name", "name"),
        ("email", "email"),
        ("url", "url"),
    ):
        value = credit.get(source_key)
        if isinstance(value, str) and value.strip():
            agent[concept_key] = value
    for key in ("orcidid", "rorid", "gridid", "fundrefid"):
        value = credit.get(key)
        if isinstance(value, str) and value.strip():
            agent["identifier"] = value
            break
    return agent
