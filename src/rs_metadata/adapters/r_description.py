"""Adapter for an R package ``DESCRIPTION``.

DESCRIPTION is a Debian-control file, and its ``Authors@R`` field holds R
source code rather than data. Evaluating that code is out of the question, so
the ``person()`` calls are parsed structurally: enough to recover names,
roles and ORCIDs, which is all the comparison needs.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from ..concepts import ConceptMap, ParsedSource, add
from ..locate import DcfSourceMap
from ..normalize import as_list
from ..vocabulary import format_hints
from .base import Adapter, SourceError

_FIELD_RE = re.compile(r"^([A-Za-z][A-Za-z0-9@._-]*)\s*:\s*(.*)$")
_QUOTED_RE = re.compile(r"""["']([^"']*)["']""")

#: R license strings predate SPDX and use their own spellings. Only the
#: unambiguous ones are translated; anything else is passed through and
#: compared as text.
#: Read from ``data/format-hints.json``: CRAN's spellings, not ours.
R_LICENSE_ALIASES: dict[str, str] = format_hints()["rLicenseAliases"]["aliases"]


def parse_dcf(text: str) -> dict[str, str]:
    """Parse a single-record Debian-control file, as R's DESCRIPTION is.

    Parameters
    ----------
    text : str
        The file contents.

    Returns
    -------
    dict
        Field names mapped to their values.

    Notes
    -----
    Continuation lines are indented; they are joined with newlines so that
    multi-line fields such as ``Description`` and ``Authors@R`` survive
    intact — the latter matters because it holds R source code whose
    structure must be preserved for parsing.

    Examples
    --------
    >>> fields = parse_dcf("Package: tool\\nVersion: 1.0-0\\n")
    >>> fields["Package"], fields["Version"]
    ('tool', '1.0-0')

    Indented continuation lines belong to the field above them:

    >>> fields = parse_dcf(
    ...     "Description: A tool that does\\n"
    ...     "    several things at once.\\n"
    ...     "License: MIT\\n"
    ... )
    >>> fields["Description"]
    'A tool that does\\nseveral things at once.'
    >>> fields["License"]
    'MIT'

    Field names may contain ``@``, which R relies on:

    >>> sorted(parse_dcf('Authors@R: person("Jane", "Doe")\\n'))
    ['Authors@R']
    """
    fields: dict[str, str] = {}
    current: str | None = None
    for line in text.splitlines():
        if not line.strip():
            continue
        if line[0] in " \t" and current is not None:
            fields[current] = f"{fields[current]}\n{line.strip()}"
            continue
        match = _FIELD_RE.match(line)
        if match:
            # Bound to its own name so the key is a `str` at the point of use.
            # `current` has to stay optional for the continuation branch above,
            # and a strict checker will not narrow it here on its own.
            name = match.group(1)
            current = name
            fields[name] = match.group(2).strip()
        else:
            current = None
    return fields


def _balanced(text: str, start: int) -> str:
    """Return the contents of the parenthesised group opening at ``start``."""
    depth = 0
    for index in range(start, len(text)):
        char = text[index]
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                return text[start + 1 : index]
    return text[start + 1 :]


def _argument(body: str, name: str) -> str | None:
    match = re.search(rf"\b{name}\s*=\s*(c\([^)]*\)|\"[^\"]*\"|'[^']*')", body)
    if not match:
        return None
    raw = match.group(1)
    values = _QUOTED_RE.findall(raw)
    return " ".join(values).strip() or None


def parse_authors_r(code: str) -> list[dict[str, Any]]:
    """Extract people from an ``Authors@R`` field.

    Parameters
    ----------
    code : str
        The field's contents, which are R source code rather than data.

    Returns
    -------
    list of dict
        One mapping per ``person()`` call, using CodeMeta's key names so the
        result drops straight into the comparison engine.

    Notes
    -----
    The code is parsed *structurally*, never evaluated: running arbitrary R
    from a repository being validated is out of the question. Enough is
    recovered — names, roles, ORCIDs, emails — for author comparison, which is
    all the engine needs.

    Both call styles are handled: keyword, ``person(given = "Jane", family =
    "Doe")``, and positional, ``person("Jane", "Doe", role = "aut")``.

    Examples
    --------
    Keyword form, including an ORCID in the ``comment`` argument:

    >>> people = parse_authors_r(
    ...     'person(given = "Jane", family = "Doe", role = c("aut", "cre"),'
    ...     ' comment = c(ORCID = "0000-0002-1825-0097"))'
    ... )
    >>> people[0]["givenName"], people[0]["familyName"]
    ('Jane', 'Doe')
    >>> people[0]["orcid"]
    '0000-0002-1825-0097'
    >>> people[0]["roles"]
    ['aut', 'cre']

    Positional form:

    >>> people = parse_authors_r('person("Jane", "Doe", role = "aut")')
    >>> people[0]["givenName"], people[0]["familyName"]
    ('Jane', 'Doe')

    Several people in one ``c(...)`` call:

    >>> people = parse_authors_r(
    ...     'c(person(given = "Jane", family = "Doe"),'
    ...     ' person(given = "John", family = "Smith"))'
    ... )
    >>> [person["familyName"] for person in people]
    ['Doe', 'Smith']

    An entry with no name at all is skipped rather than yielding a blank
    author:

    >>> parse_authors_r('person(role = "cph")')
    []
    """
    people: list[dict[str, Any]] = []
    for match in re.finditer(r"\bperson\s*\(", code):
        body = _balanced(code, match.end() - 1)
        given = _argument(body, "given")
        family = _argument(body, "family")
        if given is None and family is None:
            # Positional: the first two string arguments are given and family.
            head = body.split("=")[0] if "=" in body else body
            positional = _QUOTED_RE.findall(head)
            if len(positional) >= 2:
                given, family = positional[0], positional[1]
            elif positional:
                family = positional[0]
        roles_raw = _argument(body, "role") or ""
        person: dict[str, Any] = {"roles": roles_raw.split()}
        if given:
            person["givenName"] = given
        if family:
            person["familyName"] = family
        email = _argument(body, "email")
        if email:
            person["email"] = email
        orcid = re.search(r"ORCID\s*=\s*[\"']([^\"']+)[\"']", body)
        if orcid:
            person["orcid"] = orcid.group(1)
        if given or family:
            people.append(person)
    return people


def parse_requirements(field: str) -> list[dict[str, Any]]:
    """Split an R ``Depends``/``Imports`` field into package requirements.

    Parameters
    ----------
    field : str
        A comma-separated requirement list, possibly wrapped over lines.

    Returns
    -------
    list of dict
        Mappings with ``name`` and ``version``, ready for
        :func:`~rs_metadata.normalize.parse_requirement`.

    Examples
    --------
    Constraints are parenthesised in R, and optional:

    >>> requirements = parse_requirements("dplyr (>= 1.0), utils")
    >>> [(r["name"], r["version"]) for r in requirements]
    [('dplyr', '>= 1.0'), ('utils', None)]

    Line-wrapped fields are handled, since DESCRIPTION wraps freely:

    >>> [r["name"] for r in parse_requirements("dplyr,\\nutils,\\nstats")]
    ['dplyr', 'utils', 'stats']

    ``R`` itself is returned here and filtered out by the adapter, which maps
    it to the programming language rather than to a dependency:

    >>> [r["name"] for r in parse_requirements("R (>= 4.0), dplyr")]
    ['R', 'dplyr']

    An empty field yields nothing:

    >>> parse_requirements("")
    []
    """
    requirements = []
    for entry in field.replace("\n", " ").split(","):
        text = entry.strip()
        if not text:
            continue
        match = re.match(r"^([A-Za-z][A-Za-z0-9._]*)\s*(?:\(([^)]*)\))?", text)
        if not match:
            continue
        requirements.append(
            {"name": match.group(1), "version": (match.group(2) or "").strip() or None}
        )
    return requirements


class RDescriptionAdapter(Adapter):
    id = "r-description"
    format = "R package DESCRIPTION"
    role = "optional"
    filenames = ("DESCRIPTION",)
    mapping_name = "r-description"

    def detect(self, root: Path) -> Path | None:
        """Only treat DESCRIPTION as R metadata when it really is R metadata.

        ``DESCRIPTION`` is a generic filename. Requiring the mandatory R
        fields avoids misreading an unrelated text file as a package
        description.
        """
        candidate = super().detect(root)
        if candidate is None:
            return None
        try:
            head = candidate.read_text(encoding="utf-8", errors="replace")[:4096]
        except OSError:  # pragma: no cover - unreadable file
            return None
        fields = parse_dcf(head)
        return candidate if "Package" in fields and "Version" in fields else None

    def parse(self, path: Path, relative: str) -> ParsedSource:
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as error:
            raise SourceError(f"{relative} could not be read: {error}") from error
        fields = parse_dcf(text)
        if not fields:
            raise SourceError(f"{relative} does not contain any Debian-control fields.")
        return ParsedSource(
            adapter_id=self.id,
            file=relative,
            format=self.format,
            document=fields,
            source_map=DcfSourceMap(text.splitlines()),
        )

    def map_to_codemeta(self, parsed: ParsedSource) -> ConceptMap:
        fields: dict[str, str] = parsed.document
        concepts: ConceptMap = {}

        # Both spellings are offered because the upstream crosswalk and the
        # codemetar tool disagree about which one CodeMeta `name` corresponds
        # to; the mapping accepts a match against either.
        add(concepts, "name", fields.get("Package"), ("Package",))
        add(concepts, "name", fields.get("Title"), ("Title",))
        add(concepts, "version", fields.get("Version"), ("Version",))
        add(
            concepts,
            "description",
            _unwrap(fields.get("Description")),
            ("Description",),
        )
        add(concepts, "datePublished", fields.get("Date"), ("Date",))
        add(concepts, "issueTracker", fields.get("BugReports"), ("BugReports",))
        add(concepts, "programmingLanguage", "R", ("Package",))

        license_value = fields.get("License")
        if license_value:
            add(concepts, "license", _map_license(license_value), ("License",))

        # R's URL field is a list, and CRAN packages routinely put the source
        # repository and the documentation site in it without distinguishing
        # them. Both concepts are recorded, and both compare as subsets.
        for url in re.split(r"[,\s]+", fields.get("URL", "")):
            if url.strip():
                add(concepts, "codeRepository", url.strip(), ("URL",))
                add(concepts, "url", url.strip(), ("URL",))

        self._add_people(concepts, fields)

        for field in ("Depends", "Imports"):
            for requirement in parse_requirements(fields.get(field, "")):
                if requirement["name"] == "R":
                    continue  # an interpreter requirement, not a dependency
                add(concepts, "softwareRequirements", requirement, (field,))
        # `Suggests` is what a package can use but does not need, which is the
        # distinction CodeMeta draws with softwareSuggestions.
        for requirement in parse_requirements(fields.get("Suggests", "")):
            add(concepts, "softwareSuggestions", requirement, ("Suggests",))
        return concepts

    def _add_people(self, concepts: ConceptMap, fields: dict[str, str]) -> None:
        people = parse_authors_r(fields.get("Authors@R", ""))
        for person in people:
            roles = as_list(person.get("roles"))
            if "cre" in roles:
                add(concepts, "maintainer", person, ("Authors@R",))
            if "aut" in roles or not roles:
                add(concepts, "author", person, ("Authors@R",))
            if "ctb" in roles:
                add(concepts, "contributor", person, ("Authors@R",))
        if not people and fields.get("Author"):
            # The legacy free-text Author field.
            for name in fields["Author"].split(","):
                cleaned = re.sub(r"\[[^\]]*\]", "", name).strip()
                if cleaned:
                    add(concepts, "author", cleaned, ("Author",))
        if fields.get("Maintainer"):
            add(
                concepts,
                "maintainer",
                re.sub(r"<[^>]*>", "", fields["Maintainer"]).strip(),
                ("Maintainer",),
            )


def _unwrap(text: str | None) -> str | None:
    return re.sub(r"\s+", " ", text).strip() if text else None


#: CRAN's own expression grammar, which is parsing rather than vocabulary and
#: therefore lives here rather than in the fetched alias table. ``GPL (>= 2)``
#: means version 2 or later; ``|`` separates alternatives.
_R_OR_LATER = re.compile(r"^(?P<name>.+?)\s*\(\s*>=\s*(?P<version>[\d.]+)\s*\)$")


def _map_license(value: str) -> str:
    """Reduce a CRAN license string to an SPDX identifier where one exists.

    The vocabulary comes from R's own license database. The grammar around it
    does not: CRAN writes ``GPL (>= 2)`` for "version 2 or later" and separates
    alternatives with ``|``, neither of which any table can enumerate.
    """
    cleaned = re.sub(r"\+\s*file\s+LICEN[CS]E", "", value, flags=re.IGNORECASE).strip()

    # Alternatives: take the first, which is the one CRAN treats as primary.
    if "|" in cleaned:
        cleaned = cleaned.split("|", 1)[0].strip()

    direct = R_LICENSE_ALIASES.get(cleaned.casefold())
    if direct is not None:
        return direct

    match = _R_OR_LATER.match(cleaned)
    if match:
        base = f"{match.group('name')}-{match.group('version')}".casefold()
        mapped = R_LICENSE_ALIASES.get(base)
        if mapped:
            # "or later" is SPDX's -or-later suffix where the identifier has one.
            return mapped.replace("-only", "-or-later")
    return cleaned
