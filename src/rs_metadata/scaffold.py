"""Creating the metadata files a repository is missing.

``rs-metadata init`` writes ``codemeta.json``, ``CITATION.cff`` and a CI
workflow, filling in whatever can be read from packaging metadata and the git
remote. It never overwrites: a file that already exists is left alone and
reported as such.

Fields that cannot be inferred get the placeholder values the validator already
knows about, so ``rs-metadata validate`` immediately names each one that still
needs a real value.
"""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .adapters import ANCHOR, companion_adapters
from .concepts import ConceptMap
from .normalize import scalarize
from .vocabulary import placeholders

__all__ = ["Plan", "plan", "write"]

WORKFLOW_PATH = Path(".github/workflows/metadata.yml")

_WORKFLOW = """\
name: Validate software metadata

on: [push, pull_request]

jobs:
  metadata:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: LUMC-DCC/rs-metadata@v1
"""

_CITATION = """\
cff-version: 1.2.0
title: {name}
message: "If you use this software, please cite it using the metadata in this file."
type: software
abstract: >-
  {description}
authors:
  - family-names: {family}
    given-names: {given}
    orcid: https://orcid.org/{orcid}
version: {version}
repository-code: {repository}
license: {license_id}
"""


@dataclass
class Plan:
    """What :func:`write` would create, and what it would leave alone.

    Attributes
    ----------
    create : dict
        Repository-relative path mapped to the file contents to write.
    existing : list of str
        Paths that are already present and will not be touched.
    inferred : list of str
        Human-readable notes about what was filled in, and from where.
    """

    create: dict[str, str] = field(default_factory=dict)
    existing: list[str] = field(default_factory=list)
    inferred: list[str] = field(default_factory=list)


def _git_remote(root: Path) -> str | None:
    """The origin remote as an https URL, if this is a git repository."""
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "remote", "get-url", "origin"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):  # pragma: no cover - rare
        return None
    if result.returncode != 0:
        return None
    url = result.stdout.strip()
    if not url:
        return None
    match = re.match(r"^git@([^:]+):(.+?)(?:\.git)?$", url)
    if match:
        return f"https://{match.group(1)}/{match.group(2)}"
    return re.sub(r"\.git$", "", url)


def _existing_concepts(root: Path) -> tuple[ConceptMap, str | None]:
    """Concepts read from whichever packaging metadata is already present.

    Returns the concept map and the file it came from. The adapters already
    know how to read every supported format, so nothing here re-parses TOML or
    package manifests.
    """
    for adapter in companion_adapters():
        path = adapter.detect(root)
        if path is None:
            continue
        try:
            parsed = adapter.parse(path, path.name)
            return adapter.map_to_codemeta(parsed), path.name
        except Exception:  # pragma: no cover - a broken file is not init's job
            continue
    return {}, None


def _first(concepts: ConceptMap, name: str) -> Any:
    values = concepts.get(name) or []
    return values[0].raw if values else None


def plan(root: Path) -> Plan:
    """Work out which files are missing and what should go in them.

    Parameters
    ----------
    root : Path
        Repository to inspect.

    Returns
    -------
    Plan
        The files to create, those already present, and notes on what was
        inferred.

    Examples
    --------
    In an empty directory, all three files are proposed:

    >>> import tempfile
    >>> from pathlib import Path
    >>> with tempfile.TemporaryDirectory() as tmp:
    ...     proposed = plan(Path(tmp))
    >>> sorted(proposed.create)
    ['.github/workflows/metadata.yml', 'CITATION.cff', 'codemeta.json']

    A file that already exists is reported rather than replaced:

    >>> with tempfile.TemporaryDirectory() as tmp:
    ...     _ = (Path(tmp) / "codemeta.json").write_text("{}", encoding="utf-8")
    ...     proposed = plan(Path(tmp))
    >>> proposed.existing
    ['codemeta.json']
    >>> "codemeta.json" in proposed.create
    False
    """
    marks = placeholders()
    concepts, source = _existing_concepts(root)

    name = scalarize(_first(concepts, "name")) or root.resolve().name
    description = (
        scalarize(_first(concepts, "description"))
        or "One sentence describing what this software does."
    )
    version = scalarize(_first(concepts, "version")) or "0.1.0"
    license_id = scalarize(_first(concepts, "license")) or "Apache-2.0"
    if license_id.startswith("http"):
        license_id = license_id.rstrip("/").rsplit("/", 1)[-1]
    repository = (
        _git_remote(root)
        or scalarize(_first(concepts, "codeRepository"))
        or f"https://{marks['hosts'][0]}/your-org/{name}"
    )

    inferred: list[str] = []
    if source:
        inferred.append(f"name, description, version and license from {source}")
    if _git_remote(root):
        inferred.append("repository URL from the git origin remote")

    record = {
        "@context": [
            "https://w3id.org/codemeta/3.1",
            {"schema": "https://schema.org/"},
        ],
        "@type": "SoftwareSourceCode",
        "name": name,
        "description": description,
        "version": version,
        "identifier": f"https://doi.org/{marks['doiPrefix']}replace-me",
        "author": [
            {
                "@type": "Person",
                "@id": f"https://orcid.org/{marks['orcid']}",
                "givenName": "Given",
                "familyName": "Family",
            }
        ],
        "license": f"https://spdx.org/licenses/{license_id}",
        "codeRepository": repository,
        "programmingLanguage": ["Python"],
        "applicationCategory": "Command-line tool",
        "schema:featureList": ["http://edamontology.org/operation_0000"],
    }

    citation = _CITATION.format(
        name=name,
        description=description,
        family="Family",
        given="Given",
        orcid=marks["orcid"],
        version=version,
        repository=repository,
        license_id=license_id,
    )

    proposed = {
        ANCHOR.filenames[0]: json.dumps(record, indent=2, ensure_ascii=False) + "\n",
        "CITATION.cff": citation,
        # `as_posix`, not `str`: these are repository-relative paths that get
        # shown to a user and written into documentation, and a backslash
        # would make them wrong on every other platform.
        WORKFLOW_PATH.as_posix(): _WORKFLOW,
    }

    result = Plan(inferred=inferred)
    for relative, contents in proposed.items():
        if (root / relative).exists():
            result.existing.append(relative)
        else:
            result.create[relative] = contents
    return result


def write(root: Path, proposed: Plan) -> list[str]:
    """Create the planned files.

    Parameters
    ----------
    root : Path
        Repository to write into.
    proposed : Plan
        The plan from :func:`plan`.

    Returns
    -------
    list of str
        Paths actually written, in the order they were created.
    """
    written: list[str] = []
    for relative, contents in proposed.create.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(contents, encoding="utf-8")
        written.append(relative)
    return written
