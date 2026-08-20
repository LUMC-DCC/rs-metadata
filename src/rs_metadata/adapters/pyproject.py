"""Adapter for ``pyproject.toml``.

Supports PEP 621 ``[project]`` metadata and, as a fallback, the legacy
``[tool.poetry]`` table that Poetry used before it adopted PEP 621. Many
research repositories are still on the legacy layout, and refusing to read
them would silently skip the comparison that would have caught a stale
version.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path
from typing import Any

from ..concepts import ConceptMap, ParsedSource, add, add_each, dig
from ..locate import Path as DocPath
from ..locate import TomlSourceMap
from ..normalize import as_list
from ..vocabulary import format_hints
from .base import Adapter, SourceError


def _compact(label: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", label.casefold())


#: Which CodeMeta concept each well-known PEP 753 label corresponds to. This
#: half is the crosswalk and belongs to rs-metadata; the spellings that count
#: as each label come from PEP 753 itself. A label with no CodeMeta equivalent
#: is left out and simply not mapped.
PEP_LABEL_CONCEPTS = {
    "homepage": "url",
    "source": "codeRepository",
    "issues": "issueTracker",
    "documentation": "softwareHelp",
    "changelog": "releaseNotes",
    "releasenotes": "releaseNotes",
    "funding": "funding",
    "download": "downloadUrl",
}


def _url_roles() -> dict[str, set[str]]:
    """CodeMeta concept mapped to every label spelling that denotes it.

    ``project.urls`` is a free-form label-to-URL table, so a label has to be
    interpreted. PEP 753 defines the well-known labels and their aliases, and
    prescribes comparing them case-folded with non-alphanumerics removed —
    which is also what makes Poetry's spellings, such as ``Repository`` or
    ``Bug Tracker``, land on the same label.
    """
    labels = format_hints()["pyprojectUrlRoles"]["labels"]
    roles: dict[str, set[str]] = {}
    for label, spellings in labels.items():
        concept = PEP_LABEL_CONCEPTS.get(label)
        if concept is None:
            continue
        roles.setdefault(concept, set()).update(
            _compact(spelling) for spelling in spellings
        )
    return roles


URL_ROLES: dict[str, set[str]] = _url_roles()


class PyprojectAdapter(Adapter):
    id = "pyproject"
    format = "Python project metadata"
    role = "optional"
    filenames = ("pyproject.toml",)
    mapping_name = "pyproject-pep621"

    def parse(self, path: Path, relative: str) -> ParsedSource:
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as error:
            raise SourceError(f"{relative} could not be read: {error}") from error
        try:
            document = tomllib.loads(text)
        except tomllib.TOMLDecodeError as error:
            raise SourceError(f"{relative} is not valid TOML: {error}") from error

        style = "PEP 621" if isinstance(document.get("project"), dict) else None
        if style is None and isinstance(dig(document, "tool", "poetry"), dict):
            style = "Poetry (legacy)"

        return ParsedSource(
            adapter_id=self.id,
            file=relative,
            format=self.format,
            format_version=style,
            document=document,
            source_map=TomlSourceMap(text),
        )

    def map_to_codemeta(self, parsed: ParsedSource) -> ConceptMap:
        document: dict[str, Any] = parsed.document
        if isinstance(document.get("project"), dict):
            return self._map_pep621(document["project"])
        poetry = dig(document, "tool", "poetry")
        if isinstance(poetry, dict):
            return self._map_poetry(poetry)
        # A pyproject.toml with only build configuration carries no metadata.
        return {}

    # -- PEP 621 ----------------------------------------------------------

    def _map_pep621(self, project: dict[str, Any]) -> ConceptMap:
        concepts: ConceptMap = {}
        base: DocPath = ("project",)
        dynamic = set(as_list(project.get("dynamic")))

        add(concepts, "name", project.get("name"), (*base, "name"))
        # Extracted only so the report can say the field was seen and
        # deliberately not compared: PEP 621's `description` is the one-line
        # summary, not CodeMeta's abstract.
        add(concepts, "description", project.get("description"), (*base, "description"))
        # A dynamic version is computed at build time; the file does not
        # contain one, so there is nothing to compare against.
        if "version" not in dynamic:
            add(concepts, "version", project.get("version"), (*base, "version"))

        self._add_license(concepts, project, base)
        add_each(concepts, "author", project.get("authors"), (*base, "authors"))
        add_each(
            concepts, "maintainer", project.get("maintainers"), (*base, "maintainers")
        )
        add_each(concepts, "keywords", project.get("keywords"), (*base, "keywords"))
        self._add_urls(concepts, project.get("urls"), (*base, "urls"))
        self._add_dependencies(
            concepts, project.get("dependencies"), (*base, "dependencies")
        )
        self._add_classifiers(
            concepts, project.get("classifiers"), (*base, "classifiers")
        )
        # `requires-python` is the interpreter the software runs on, which is
        # what npm's `engines` and Julia's `compat.julia` say for theirs.
        requires = project.get("requires-python")
        if isinstance(requires, str) and requires.strip():
            add(
                concepts,
                "runtimePlatform",
                f"Python {requires.strip()}",
                (*base, "requires-python"),
            )
        _add_python_fallback(concepts, base)
        return concepts

    def _add_license(
        self, concepts: ConceptMap, project: dict[str, Any], base: DocPath
    ) -> None:
        license_value = project.get("license")
        path = (*base, "license")
        if isinstance(license_value, str):
            # PEP 639: an SPDX license expression.
            add(concepts, "license", license_value, path)
        elif isinstance(license_value, dict) and isinstance(
            license_value.get("text"), str
        ):
            add(concepts, "license", license_value["text"], (*path, "text"))
        # `{file = "LICENSE"}` names a file, not a license: nothing there
        # identifies which license it is, so nothing is mapped.

    def _add_urls(self, concepts: ConceptMap, urls: Any, base: DocPath) -> None:
        if not isinstance(urls, dict):
            return
        for label, value in urls.items():
            compact = _compact(str(label))
            for concept, aliases in URL_ROLES.items():
                if compact in aliases:
                    add(concepts, concept, value, (*base, label))
                    break

    def _add_dependencies(
        self, concepts: ConceptMap, dependencies: Any, base: DocPath
    ) -> None:
        if isinstance(dependencies, list):
            add_each(concepts, "softwareRequirements", dependencies, base)

    def _add_classifiers(
        self, concepts: ConceptMap, classifiers: Any, base: DocPath
    ) -> None:
        if not isinstance(classifiers, list):
            return
        for index, classifier in enumerate(classifiers):
            if not isinstance(classifier, str):
                continue
            parts = [part.strip() for part in classifier.split("::")]
            if len(parts) < 2:
                continue
            head, tail = parts[0], parts[-1]
            path = (*base, index)
            if head == "Programming Language":
                # `Programming Language :: Python :: 3.11` names the language
                # in the second segment; the third is a version.
                add(concepts, "programmingLanguage", parts[1], path)
            elif head == "Development Status":
                add(concepts, "developmentStatus", tail, path)
            elif head == "Operating System" and tail != "OS Independent":
                add(concepts, "operatingSystem", tail, path)

    # -- legacy Poetry ----------------------------------------------------

    def _map_poetry(self, poetry: dict[str, Any]) -> ConceptMap:
        concepts: ConceptMap = {}
        base: DocPath = ("tool", "poetry")

        add(concepts, "name", poetry.get("name"), (*base, "name"))
        add(concepts, "description", poetry.get("description"), (*base, "description"))
        add(concepts, "version", poetry.get("version"), (*base, "version"))
        add(concepts, "license", poetry.get("license"), (*base, "license"))
        add_each(concepts, "author", poetry.get("authors"), (*base, "authors"))
        add_each(
            concepts, "maintainer", poetry.get("maintainers"), (*base, "maintainers")
        )
        add_each(concepts, "keywords", poetry.get("keywords"), (*base, "keywords"))
        add(concepts, "codeRepository", poetry.get("repository"), (*base, "repository"))
        add(concepts, "url", poetry.get("homepage"), (*base, "homepage"))
        add(
            concepts,
            "softwareHelp",
            poetry.get("documentation"),
            (*base, "documentation"),
        )
        self._add_urls(concepts, poetry.get("urls"), (*base, "urls"))
        self._add_classifiers(
            concepts, poetry.get("classifiers"), (*base, "classifiers")
        )

        dependencies = poetry.get("dependencies")
        if isinstance(dependencies, dict):
            for name, constraint in dependencies.items():
                if name.casefold() == "python":
                    continue  # an interpreter requirement, not a dependency
                add(
                    concepts,
                    "softwareRequirements",
                    {"name": name, "version": _poetry_constraint(constraint)},
                    (*base, "dependencies", name),
                )

        _add_python_fallback(concepts, base)
        return concepts


def _add_python_fallback(concepts: ConceptMap, base: DocPath) -> None:
    """Record Python as the language, unless a classifier already said so.

    A pyproject.toml is itself evidence that the software is Python. But
    `Programming Language :: Python :: 3.11` says the same thing and says it
    at a specific line, so adding both would report one fact twice and leave
    the finding pointing at whichever happened to be recorded first.
    """
    if "programmingLanguage" not in concepts:
        add(concepts, "programmingLanguage", "Python", base)


def _poetry_constraint(constraint: Any) -> Any:
    """Reduce Poetry's dependency spellings to a version constraint string."""
    if isinstance(constraint, dict):
        return constraint.get("version")
    if isinstance(constraint, list):  # multiple constraints for one package
        return None
    return constraint
