"""The adapter contract.

An *adapter* is one supported metadata file or ecosystem: the logic needed to
find it, read it, check it against its own specification, and express what it
says in CodeMeta concepts. Adapters know nothing about each other and nothing
about comparison; they only ever translate into the common representation.

Adding support for a new ecosystem means writing one adapter and one mapping
file. Nothing in the comparison engine changes, and no existing adapter is
touched. See ``docs/developing/adapters.md``.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from ..concepts import ConceptMap, ParsedSource
from ..mapping import Mapping
from ..mapping import load as load_mapping
from ..report import Diagnostic


class SourceError(Exception):
    """A metadata file exists but cannot be read.

    Carries a line number where the underlying parser reports one, so even a
    syntax error gets an inline CI annotation.
    """

    def __init__(self, message: str, line: int | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.line = line


class Adapter(ABC):
    """One supported metadata format."""

    #: Stable identifier, used as a filter key in the report.
    id: str
    #: Human-readable format name.
    format: str
    #: ``anchor`` for codemeta.json, ``required`` for a file whose absence
    #: is itself a finding, ``optional`` for formats that are auto-detected
    #: when a repository happens to contain them.
    role: str = "optional"
    #: Canonical filenames, in preference order.
    filenames: tuple[str, ...] = ()
    #: Mapping file stem, or ``None`` for the anchor, which needs no crosswalk.
    mapping_name: str | None = None

    # -- contract ---------------------------------------------------------

    def detect(self, root: Path) -> Path | None:
        """Find this format's file in a repository, or return ``None``.

        Matching is case-insensitive because ``citation.cff`` and
        ``CITATION.cff`` are the same file on macOS and Windows. Whether the
        casing is the one GitHub actually requires is a separate question,
        answered by :meth:`validate_source`.
        """
        try:
            entries = {entry.name.casefold(): entry for entry in root.iterdir()}
        except OSError:
            return None
        for name in self.filenames:
            entry = entries.get(name.casefold())
            if entry is not None and entry.is_file():
                return entry
        return None

    @abstractmethod
    def parse(self, path: Path, relative: str) -> ParsedSource:
        """Read the file. Raises :class:`SourceError` if it is malformed."""

    def validate_source(self, parsed: ParsedSource) -> list[Diagnostic]:
        """Check the file against its own format's specification."""
        return []

    @abstractmethod
    def map_to_codemeta(self, parsed: ParsedSource) -> ConceptMap:
        """Express what the file says as CodeMeta concepts."""

    # -- helpers ----------------------------------------------------------

    @property
    def mapping(self) -> Mapping | None:
        return load_mapping(self.mapping_name) if self.mapping_name else None

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<{type(self).__name__} id={self.id!r}>"
