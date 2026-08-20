"""Adapter for Julia's ``Project.toml``.

Julia's manifest is deliberately minimal: name, UUID, version, authors,
dependencies and compatibility bounds. It carries no license, description or
repository, because Julia keeps those in a ``LICENSE`` file and in the registry
rather than in the project file. So this is a narrow adapter by the format's
design, not by choice.

Its ``authors`` field is worth noting: entries are either ``"Name <email>"``
strings or tables following the Citation File Format's person and entity
schemas, which is the same shape CITATION.cff uses and the same normalization
already handles.
"""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any

from ..concepts import ConceptMap, ParsedSource, add, add_each
from ..locate import Path as DocPath
from ..locate import TomlSourceMap
from .base import Adapter, SourceError


class JuliaProjectAdapter(Adapter):
    id = "julia-project"
    format = "Julia project metadata"
    role = "optional"
    filenames = ("Project.toml", "JuliaProject.toml")
    mapping_name = "julia-project"

    def detect(self, root: Path) -> Path | None:
        """Find a Julia ``Project.toml``, but never a Rust or Python one.

        ``Project.toml`` is a generic enough name that a case-insensitive match
        would also catch files from other ecosystems on a case-insensitive
        filesystem. A Julia project always has a ``name`` and a ``uuid``, so
        that pair is what identifies the format.
        """
        path = super().detect(root)
        if path is None:
            return None
        try:
            document = tomllib.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError):
            # Malformed: let `parse` report it rather than silently skipping.
            return path
        return path if "uuid" in document and "name" in document else None

    def parse(self, path: Path, relative: str) -> ParsedSource:
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as error:
            raise SourceError(f"{relative} could not be read: {error}") from error
        try:
            document = tomllib.loads(text)
        except tomllib.TOMLDecodeError as error:
            raise SourceError(f"{relative} is not valid TOML: {error}") from error
        return ParsedSource(
            adapter_id=self.id,
            file=relative,
            format=self.format,
            document=document,
            source_map=TomlSourceMap(text),
        )

    def map_to_codemeta(self, parsed: ParsedSource) -> ConceptMap:
        document: dict[str, Any] = parsed.document
        concepts: ConceptMap = {}

        add(concepts, "name", document.get("name"), ("name",))
        add(concepts, "version", document.get("version"), ("version",))
        # Extracted only so the report can say it was seen and deliberately
        # not compared. See the mapping's `comparable: false`.
        add(concepts, "identifier", document.get("uuid"), ("uuid",))
        add_each(concepts, "author", document.get("authors"), ("authors",))
        self._add_compat(concepts, document.get("compat"))
        # A Project.toml with a uuid is prima facie evidence of the language.
        # Anchored on `uuid`, which is the field that identifies the format.
        add(concepts, "programmingLanguage", "Julia", ("uuid",))
        return concepts

    def _add_compat(self, concepts: ConceptMap, compat: Any) -> None:
        """Read `[compat]`, where the `julia` entry is the runtime, not a dep."""
        if not isinstance(compat, dict):
            return
        for name, constraint in compat.items():
            path: DocPath = ("compat", name)
            if str(name).casefold() == "julia":
                add(concepts, "runtimePlatform", f"Julia {constraint}", path)
                continue
            add(
                concepts,
                "softwareRequirements",
                {"name": name, "version": constraint}
                if isinstance(constraint, str)
                else {"name": name},
                path,
            )
