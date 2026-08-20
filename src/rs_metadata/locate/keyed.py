"""Source positions found by searching the raw text for a key.

TOML and Debian-control parsers do not expose positions, and writing
position-preserving parsers for either would be a poor trade for what a line
number is worth. Searching the text finds the right line for the overwhelming
majority of real files, and a wrong-but-close line is no worse than no line at
all — which is what the alternative would be.
"""

from __future__ import annotations

import re

from .base import Path, SourceMap

__all__ = ["DcfSourceMap", "KeySearchSourceMap", "TomlSourceMap"]


class KeySearchSourceMap(SourceMap):
    """Base for source maps that locate a key by scanning lines.

    Parameters
    ----------
    lines : list of str
        The file's lines, without terminators.
    """

    def __init__(self, lines: list[str]) -> None:
        super().__init__()
        self._lines = lines

    def _find(
        self, pattern: re.Pattern[str], start: int = 0, end: int | None = None
    ) -> int | None:
        """First 1-based line index in ``[start, end)`` matching ``pattern``."""
        for number in range(start, end if end is not None else len(self._lines)):
            if pattern.match(self._lines[number]):
                return number + 1
        return None

    def __bool__(self) -> bool:
        return bool(self._lines)


class TomlSourceMap(KeySearchSourceMap):
    """Approximate positions in a TOML file by locating tables, then keys.

    Resolution matches the longest table prefix of the requested path, then
    searches for the remaining key within that table's extent, so a key name
    that appears in several tables resolves to the right one.

    Parameters
    ----------
    text : str
        The TOML document as it appears on disk.

    Examples
    --------
    >>> document = (
    ...     '[project]\\n'
    ...     'name = "my-tool"\\n'
    ...     'version = "1.0.0"\\n'
    ...     '\\n'
    ...     '[tool.poetry]\\n'
    ...     'version = "9.9.9"\\n'
    ... )
    >>> source_map = TomlSourceMap(document)
    >>> source_map.locate(("project", "version"))
    (3, 1)

    The same key name in a different table resolves separately, which is why
    the table prefix is matched first:

    >>> source_map.locate(("tool", "poetry", "version"))
    (6, 1)

    A path naming only a table resolves to the table header:

    >>> source_map.locate(("project",))
    (1, 1)

    Array indices are ignored, since TOML arrays have no addressable lines;
    the enclosing key is returned instead:

    >>> source_map.locate(("project", "name", 0))
    (2, 1)

    An unknown key yields ``None``:

    >>> source_map.locate(("project", "nonexistent")) is None
    False
    """

    def __init__(self, text: str) -> None:
        super().__init__(text.splitlines())
        self._tables: dict[str, int] = {}
        for number, line in enumerate(self._lines):
            match = re.match(r"\s*\[\[?([^\]]+)\]\]?", line)
            if match:
                self._tables.setdefault(match.group(1).strip(), number)

    def locate(self, path: Path) -> tuple[int, int] | None:
        """Best-effort position for a dotted TOML path.

        Parameters
        ----------
        path : Path
            Path whose string components name tables and keys. Integer
            components are ignored.

        Returns
        -------
        tuple of int, or None
            1-based ``(line, column)``. The column is always 1: only the line
            is resolved.
        """
        parts = [str(part) for part in path if not isinstance(part, int)]
        if not parts:
            return None
        for split in range(len(parts) - 1, 0, -1):
            table = ".".join(parts[:split])
            if table not in self._tables:
                continue
            start = self._tables[table]
            end = min(
                (line for line in self._tables.values() if line > start),
                default=len(self._lines),
            )
            key = re.compile(rf"\s*{re.escape(parts[split])}\s*=")
            found = self._find(key, start + 1, end)
            if found:
                return found, 1
            # The table exists but the key does not; the header is still the
            # most useful thing to point at.
            return start + 1, 1
        joined = ".".join(parts)
        if joined in self._tables:
            return self._tables[joined] + 1, 1
        found = self._find(re.compile(rf"\s*{re.escape(parts[0])}\s*="))
        return (found, 1) if found else None


class DcfSourceMap(KeySearchSourceMap):
    """Approximate positions in a Debian-control file such as R's DESCRIPTION.

    Debian-control files are flat, so only the first path component is
    meaningful. Field names are matched case-insensitively.

    Parameters
    ----------
    lines : list of str
        The file's lines, without terminators.

    Examples
    --------
    >>> source_map = DcfSourceMap(
    ...     ["Package: tool", "Version: 1.0-0", "License: MIT"]
    ... )
    >>> source_map.locate(("Version",))
    (2, 1)

    Matching ignores case, because R's own tooling does:

    >>> source_map.locate(("license",))
    (3, 1)

    An unknown field yields ``None``:

    >>> source_map.locate(("Nonexistent",)) is None
    True
    """

    def locate(self, path: Path) -> tuple[int, int] | None:
        """Best-effort position for a Debian-control field.

        Parameters
        ----------
        path : Path
            Path whose first string component names the field.

        Returns
        -------
        tuple of int, or None
            1-based ``(line, column)``, or ``None`` if the field is absent.
        """
        parts = [str(part) for part in path if not isinstance(part, int)]
        if not parts:
            return None
        found = self._find(re.compile(rf"{re.escape(parts[0])}\s*:", re.IGNORECASE))
        return (found, 1) if found else None
