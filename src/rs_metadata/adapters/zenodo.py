"""Adapter for ``.zenodo.json``.

This file decides what a Zenodo record says the moment a release is archived,
which makes it the companion where drift matters most: a DOI minted from stale
metadata cannot be corrected in place, and the citation that results is the one
the world keeps. It is also the richest companion after CITATION.cff, carrying
creators with ORCIDs and affiliations, a license, keywords and a publication
date.

Zenodo publishes a JSON Schema for the legacy deposition record, but it is not
used here, and deliberately. It sets ``additionalProperties: false`` without
listing ``version``, a field Zenodo's own API documentation describes as
accepted. Validating against it would report a correct file as invalid, so the
structural checks below are written against what Zenodo documents instead.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..concepts import ConceptMap, ParsedSource, add, add_each, location
from ..diagnostics import Severity
from ..locate import Path as DocPath
from ..locate import json_source_map
from ..report import Diagnostic
from .base import Adapter, SourceError

#: Contributor roles Zenodo defines that CodeMeta has a property for. Zenodo's
#: vocabulary is DataCite's, which is broader than CodeMeta's; a role with no
#: CodeMeta equivalent is left unmapped rather than flattened into
#: `contributor`, so nothing is claimed that the file did not say.
CONTRIBUTOR_ROLES = {
    "ContactPerson": "maintainer",
    "DataCurator": "contributor",
    "Editor": "editor",
    "Producer": "producer",
    "ProjectLeader": "contributor",
    "ProjectManager": "contributor",
    "ProjectMember": "contributor",
    "Researcher": "contributor",
    "RightsHolder": "copyrightHolder",
    "Sponsor": "sponsor",
    "Supervisor": "contributor",
}

#: The `related_identifiers` relations CodeMeta's crosswalk gives a meaning
#: to. Zenodo's relation vocabulary is DataCite's and is much broader; a
#: relation that is not one of these says nothing about the software itself.
_RELATION_CONCEPTS = {
    "isSupplementTo": "codeRepository",
    "isIdenticalTo": "downloadUrl",
}

#: Zenodo upload types that describe software. Anything else is a dataset, a
#: paper or a poster, and comparing it against a software record would be
#: comparing two different things.
SOFTWARE_UPLOAD_TYPES = frozenset({"software"})


class ZenodoAdapter(Adapter):
    id = "zenodo"
    format = "Zenodo deposition metadata"
    role = "optional"
    filenames = (".zenodo.json",)
    mapping_name = "zenodo"

    def parse(self, path: Path, relative: str) -> ParsedSource:
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as error:
            raise SourceError(f"{relative} could not be read: {error}") from error
        try:
            document = json.loads(text)
        except json.JSONDecodeError as error:
            raise SourceError(
                f"{relative} is not valid JSON: {error.msg}", line=error.lineno
            ) from error
        if not isinstance(document, dict):
            raise SourceError(f"{relative} must contain a JSON object.")
        return ParsedSource(
            adapter_id=self.id,
            file=relative,
            format=self.format,
            document=document,
            source_map=json_source_map(text),
        )

    def validate_source(self, parsed: ParsedSource) -> list[Diagnostic]:
        """Check the record against what Zenodo documents, not its stale schema."""
        document: dict[str, Any] = parsed.document
        diagnostics: list[Diagnostic] = []

        upload_type = document.get("upload_type")
        if isinstance(upload_type, str) and upload_type not in SOFTWARE_UPLOAD_TYPES:
            diagnostics.append(
                Diagnostic(
                    code="source.invalid",
                    severity=Severity.WARNING,
                    message=(
                        f"{parsed.file} declares upload_type {upload_type!r}, but "
                        f"it accompanies a software metadata record."
                    ),
                    location=location(parsed, ("upload_type",), upload_type),
                    suggestion='Set `"upload_type": "software"`.',
                )
            )

        for index, creator in enumerate(_people(document.get("creators"))):
            if not isinstance(creator.get("name"), str) or not creator["name"].strip():
                diagnostics.append(
                    Diagnostic(
                        code="source.invalid",
                        severity=Severity.ERROR,
                        message=(
                            f"{parsed.file} has a creator with no name; Zenodo "
                            f"requires one on every creator."
                        ),
                        location=location(parsed, ("creators", index)),
                        suggestion=(
                            'Write the name as "Family, Given", the format '
                            "Zenodo expects."
                        ),
                    )
                )
        return diagnostics

    def map_to_codemeta(self, parsed: ParsedSource) -> ConceptMap:
        document: dict[str, Any] = parsed.document
        concepts: ConceptMap = {}

        add(concepts, "name", document.get("title"), ("title",))
        add(concepts, "description", document.get("description"), ("description",))
        add(concepts, "version", document.get("version"), ("version",))
        add(concepts, "license", document.get("license"), ("license",))
        add_each(concepts, "keywords", document.get("keywords"), ("keywords",))
        add(
            concepts,
            "datePublished",
            document.get("publication_date"),
            ("publication_date",),
        )
        self._add_doi(concepts, document.get("doi"))
        self._add_related(concepts, document.get("related_identifiers"))
        self._add_grants(concepts, document.get("grants"))
        self._add_people(concepts, "author", document.get("creators"), ("creators",))
        self._add_contributors(concepts, document.get("contributors"))
        return concepts

    def _add_doi(self, concepts: ConceptMap, doi: Any) -> None:
        # A `doi` in .zenodo.json is a reserved DOI for this deposition, which
        # is the same identifier codemeta.json should carry.
        add(concepts, "identifier", doi, ("doi",))

    def _add_related(self, concepts: ConceptMap, related: Any) -> None:
        """Read the source repository out of `related_identifiers`.

        Zenodo has no repository field; the convention its crosswalk records is
        an `isSupplementTo` relation pointing at the code.
        """
        if not isinstance(related, list):
            return
        for index, entry in enumerate(related):
            if not isinstance(entry, dict):
                continue
            concept = _RELATION_CONCEPTS.get(str(entry.get("relation")))
            if concept is None:
                continue
            add(
                concepts,
                concept,
                entry.get("identifier"),
                ("related_identifiers", index, "identifier"),
            )

    def _add_grants(self, concepts: ConceptMap, grants: Any) -> None:
        if not isinstance(grants, list):
            return
        for index, grant in enumerate(grants):
            value = grant.get("id") if isinstance(grant, dict) else grant
            add(concepts, "funding", value, ("grants", index))

    def _add_people(
        self, concepts: ConceptMap, concept: str, people: Any, base: DocPath
    ) -> None:
        for index, person in enumerate(_people(people)):
            add(concepts, concept, _as_agent(person), (*base, index))

    def _add_contributors(self, concepts: ConceptMap, contributors: Any) -> None:
        for index, person in enumerate(_people(contributors)):
            concept = CONTRIBUTOR_ROLES.get(str(person.get("type", "")))
            if concept is None:
                continue
            add(concepts, concept, _as_agent(person), ("contributors", index))


def _people(value: Any) -> list[dict[str, Any]]:
    """The object entries of a Zenodo people list, ignoring malformed ones."""
    if not isinstance(value, list):
        return []
    return [entry for entry in value if isinstance(entry, dict)]


def _as_agent(person: dict[str, Any]) -> dict[str, Any]:
    """Express one Zenodo creator or contributor as a CodeMeta agent.

    Zenodo writes personal names as ``Family, Given`` and carries the ORCID
    bare rather than as a URI. Both are normalized on comparison, so the value
    is passed through with only the keys CodeMeta recognizes.

    Examples
    --------
    >>> _as_agent({"name": "Doe, Jane", "orcid": "0000-0002-1825-0097",
    ...            "affiliation": "LUMC", "type": "Editor"})
    {'name': 'Doe, Jane', 'identifier': '0000-0002-1825-0097', 'affiliation': 'LUMC'}

    Absent keys are simply left out:

    >>> _as_agent({"name": "Acme Institute"})
    {'name': 'Acme Institute'}
    """
    agent: dict[str, Any] = {}
    for source_key, concept_key in (
        ("name", "name"),
        ("orcid", "identifier"),
        ("affiliation", "affiliation"),
    ):
        value = person.get(source_key)
        if isinstance(value, str) and value.strip():
            agent[concept_key] = value
    return agent
