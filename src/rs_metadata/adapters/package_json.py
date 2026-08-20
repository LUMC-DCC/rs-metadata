"""Adapter for npm's ``package.json``.

npm accepts several shorthand spellings for the same information — a
repository may be ``user/repo``, ``github:user/repo`` or a
``git+https://…​.git`` URL, and an author may be a structured object or a
single ``Name <email> (url)`` string. All of them are expanded here so the
comparison engine sees one consistent shape.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from ..concepts import ConceptMap, ParsedSource, add, add_each
from ..locate import Path as DocPath
from ..locate import json_source_map
from ..normalize import as_list
from .base import Adapter, SourceError

_AUTHOR_STRING_RE = re.compile(
    r"^\s*(?P<name>[^<(]*?)\s*"
    r"(?:<(?P<email>[^>]*)>)?\s*"
    r"(?:\((?P<url>[^)]*)\))?\s*$"
)


def parse_person(value: Any) -> dict[str, Any] | None:
    """Normalize npm's two author spellings into one mapping.

    Parameters
    ----------
    value : Any
        Either a structured object, or npm's shorthand
        ``"Name <email> (url)"`` string.

    Returns
    -------
    dict or None
        A mapping with at least ``name``, or ``None`` if there is no name.

    Examples
    --------
    The shorthand string is decomposed:

    >>> parse_person("Josiah Carberry <j@example.org> (https://example.org)")
    {'name': 'Josiah Carberry', 'email': 'j@example.org', 'url': 'https://example.org'}

    Its optional parts really are optional:

    >>> parse_person("Josiah Carberry")
    {'name': 'Josiah Carberry'}
    >>> parse_person("Josiah Carberry <j@example.org>")
    {'name': 'Josiah Carberry', 'email': 'j@example.org'}

    A structured object passes through unchanged:

    >>> parse_person({"name": "Josiah Carberry", "email": "j@example.org"})
    {'name': 'Josiah Carberry', 'email': 'j@example.org'}

    Anything with no name is not a person:

    >>> parse_person({"email": "j@example.org"}) is None
    True
    >>> parse_person("") is None
    True
    """
    if isinstance(value, dict):
        return value if value.get("name") else None
    if not isinstance(value, str) or not value.strip():
        return None
    match = _AUTHOR_STRING_RE.match(value)
    if not match or not (match.group("name") or "").strip():
        return {"name": value.strip()}
    person = {"name": match.group("name").strip()}
    if match.group("email"):
        person["email"] = match.group("email").strip()
    if match.group("url"):
        person["url"] = match.group("url").strip()
    return person


def repository_url(value: Any) -> str | None:
    """Extract a repository URL from any of npm's accepted forms.

    Parameters
    ----------
    value : Any
        A URL string, an npm shorthand, or a ``{"type": ..., "url": ...}``
        object.

    Returns
    -------
    str or None
        The URL as written, or ``None`` if none is present. Shorthand
        expansion and scheme normalization happen later, in
        :func:`~rs_metadata.normalize.normalize_uri`.

    Examples
    --------
    >>> repository_url("https://github.com/org/tool")
    'https://github.com/org/tool'
    >>> repository_url({"type": "git",
    ...                 "url": "git+https://github.com/org/tool.git"})
    'git+https://github.com/org/tool.git'

    Shorthand is returned as written; the comparison layer expands it:

    >>> repository_url("org/tool")
    'org/tool'

    An object with no URL yields nothing:

    >>> repository_url({"type": "git"}) is None
    True
    >>> repository_url(None) is None
    True
    """
    if isinstance(value, dict):
        url = value.get("url")
        return url if isinstance(url, str) and url.strip() else None
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


class PackageJsonAdapter(Adapter):
    id = "package-json"
    format = "npm package metadata"
    role = "optional"
    filenames = ("package.json",)
    mapping_name = "package-json"

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
        if not isinstance(document, dict):
            raise SourceError(f"{relative} must contain a JSON object.")
        return ParsedSource(
            adapter_id=self.id,
            file=relative,
            format=self.format,
            document=document,
            source_map=json_source_map(text),
        )

    def map_to_codemeta(self, parsed: ParsedSource) -> ConceptMap:
        document: dict[str, Any] = parsed.document
        concepts: ConceptMap = {}

        name = document.get("name")
        if isinstance(name, str) and name.strip():
            # Scoped packages are named `@scope/tool`; the scope is an npm
            # namespace, not part of the software's name.
            add(concepts, "name", name.rsplit("/", 1)[-1], ("name",))

        add(concepts, "version", document.get("version"), ("version",))
        add(concepts, "description", document.get("description"), ("description",))
        add(concepts, "url", document.get("homepage"), ("homepage",))
        add_each(concepts, "keywords", document.get("keywords"), ("keywords",))
        add_each(concepts, "operatingSystem", document.get("os"), ("os",))

        self._add_license(concepts, document)

        repository = repository_url(document.get("repository"))
        if repository:
            add(concepts, "codeRepository", repository, ("repository",))

        bugs = document.get("bugs")
        bugs_url = bugs.get("url") if isinstance(bugs, dict) else bugs
        if isinstance(bugs_url, str) and bugs_url.strip():
            add(concepts, "issueTracker", bugs_url, ("bugs",))

        author = parse_person(document.get("author"))
        if author:
            add(concepts, "author", author, ("author",))
        # npm's `contributors` is a distinct role from `author`, which is
        # what CodeMeta's crosswalk says too. The mapping anchors it on both,
        # so someone credited here still satisfies a codemeta.json that lists
        # them as an author.
        for index, entry in enumerate(as_list(document.get("contributors"))):
            person = parse_person(entry)
            if person:
                add(concepts, "contributor", person, ("contributors", index))

        for field in ("dependencies", "peerDependencies"):
            self._add_dependencies(
                concepts, document.get(field), (field,), "softwareRequirements"
            )
        # Development and optional dependencies are not what the software
        # needs to run, which is the distinction softwareSuggestions draws.
        for field in ("devDependencies", "optionalDependencies"):
            self._add_dependencies(
                concepts, document.get(field), (field,), "softwareSuggestions"
            )

        cpu = document.get("cpu")
        if isinstance(cpu, list):
            add_each(concepts, "processorRequirements", cpu, ("cpu",))

        engines = document.get("engines")
        if isinstance(engines, dict):
            for platform, constraint in engines.items():
                add(
                    concepts,
                    "runtimePlatform",
                    f"{platform} {constraint}".strip(),
                    ("engines", platform),
                )
        return concepts

    def _add_license(self, concepts: ConceptMap, document: dict[str, Any]) -> None:
        value = document.get("license")
        if isinstance(value, str):
            add(concepts, "license", value, ("license",))
            return
        if isinstance(value, dict) and isinstance(value.get("type"), str):
            # The deprecated pre-npm-2 object form.
            add(concepts, "license", value["type"], ("license", "type"))
            return
        for index, entry in enumerate(as_list(document.get("licenses"))):
            if isinstance(entry, dict) and entry.get("type"):
                add(concepts, "license", entry["type"], ("licenses", index, "type"))

    def _add_dependencies(
        self,
        concepts: ConceptMap,
        dependencies: Any,
        base: DocPath,
        concept: str,
    ) -> None:
        if not isinstance(dependencies, dict):
            return
        for name, constraint in dependencies.items():
            add(
                concepts,
                concept,
                {"name": name, "version": constraint},
                (*base, name),
            )
