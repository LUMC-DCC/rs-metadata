"""Adapter for ``Cargo.toml``.

Rust's manifest carries a richer metadata block than most packaging formats:
``[package]`` has description, license, repository, homepage, documentation,
keywords and categories, all of which crates.io displays and all of which have
CodeMeta equivalents.

Workspace inheritance is the one wrinkle. A field written
``version.workspace = true`` takes its value from the workspace root, so the
manifest in hand does not contain the value at all. Those are skipped rather
than guessed at, because comparing against a table saying ``{"workspace":
true}`` would report a difference on every correctly configured workspace
member.
"""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any

from ..concepts import ConceptMap, ParsedSource, add, add_each, location
from ..diagnostics import Severity
from ..locate import Path as DocPath
from ..locate import TomlSourceMap
from ..report import Diagnostic
from .base import Adapter, SourceError


def _inherited(value: Any) -> bool:
    """Whether a field defers to the workspace rather than stating a value.

    Examples
    --------
    >>> _inherited({"workspace": True})
    True
    >>> _inherited("1.2.0")
    False
    """
    return isinstance(value, dict) and value.get("workspace") is True


class CargoAdapter(Adapter):
    id = "cargo"
    format = "Rust package manifest"
    role = "optional"
    filenames = ("Cargo.toml",)
    mapping_name = "cargo"

    def parse(self, path: Path, relative: str) -> ParsedSource:
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as error:
            raise SourceError(f"{relative} could not be read: {error}") from error
        try:
            document = tomllib.loads(text)
        except tomllib.TOMLDecodeError as error:
            raise SourceError(f"{relative} is not valid TOML: {error}") from error

        package = document.get("package")
        edition = package.get("edition") if isinstance(package, dict) else None
        return ParsedSource(
            adapter_id=self.id,
            file=relative,
            format=self.format,
            format_version=f"edition {edition}" if isinstance(edition, str) else None,
            document=document,
            source_map=TomlSourceMap(text),
        )

    def validate_source(self, parsed: ParsedSource) -> list[Diagnostic]:
        """Check the manifest against Cargo's own requirements.

        Only what Cargo itself refuses is reported. A virtual manifest — a
        workspace root with no ``[package]`` — is valid Cargo and simply
        carries no metadata, so it is not a finding.
        """
        document: dict[str, Any] = parsed.document
        package = document.get("package")
        if not isinstance(package, dict):
            return []
        diagnostics: list[Diagnostic] = []
        for key in ("name", "version"):
            value = package.get(key)
            if value is None or _inherited(value):
                continue
            if not isinstance(value, str) or not value.strip():
                diagnostics.append(
                    Diagnostic(
                        code="source.invalid",
                        severity=Severity.ERROR,
                        message=(
                            f"Cargo requires `package.{key}` to be a string; "
                            f"found {type(value).__name__}."
                        ),
                        location=location(parsed, ("package", key), value),
                    )
                )
        return diagnostics

    def map_to_codemeta(self, parsed: ParsedSource) -> ConceptMap:
        document: dict[str, Any] = parsed.document
        package = document.get("package")
        if not isinstance(package, dict):
            # A virtual manifest: a workspace root with only `[workspace]`.
            return {}

        concepts: ConceptMap = {}
        base: DocPath = ("package",)

        def stated(key: str) -> Any:
            value = package.get(key)
            return None if _inherited(value) else value

        add(concepts, "name", stated("name"), (*base, "name"))
        add(concepts, "version", stated("version"), (*base, "version"))
        add(concepts, "description", stated("description"), (*base, "description"))
        add(concepts, "license", stated("license"), (*base, "license"))
        add(concepts, "codeRepository", stated("repository"), (*base, "repository"))
        add(concepts, "url", stated("homepage"), (*base, "homepage"))
        add(
            concepts,
            "softwareHelp",
            stated("documentation"),
            (*base, "documentation"),
        )
        add_each(concepts, "author", stated("authors"), (*base, "authors"))
        add_each(concepts, "keywords", stated("keywords"), (*base, "keywords"))
        # crates.io categories are a controlled vocabulary of application
        # areas, which is what applicationCategory is for.
        add_each(
            concepts, "applicationCategory", stated("categories"), (*base, "categories")
        )
        self._add_dependencies(concepts, document.get("dependencies"))
        # A Cargo.toml is prima facie evidence that the crate is Rust.
        add(concepts, "programmingLanguage", "Rust", base)
        return concepts

    def _add_dependencies(self, concepts: ConceptMap, dependencies: Any) -> None:
        if not isinstance(dependencies, dict):
            return
        for name, spec in dependencies.items():
            add(
                concepts,
                "softwareRequirements",
                {"name": name, "version": _constraint(spec)},
                ("dependencies", name),
            )


def _constraint(spec: Any) -> Any:
    """Reduce Cargo's dependency spellings to a version constraint.

    Examples
    --------
    The common form is a bare requirement string:

    >>> _constraint("1.0")
    '1.0'

    A table states the same thing under `version`, alongside features and
    other build options that say nothing about which version is required:

    >>> _constraint({"version": "1.0", "features": ["derive"]})
    '1.0'

    A git or path dependency pins a revision rather than a version, so there
    is no constraint to compare:

    >>> _constraint({"git": "https://example.org/x.git"}) is None
    True
    """
    if isinstance(spec, str):
        return spec
    if isinstance(spec, dict):
        version = spec.get("version")
        return version if isinstance(version, str) else None
    return None
