"""Document paths and the source-map interface they are looked up in.

A *path* addresses a value inside a parsed document as a tuple mixing string
keys and integer indices. A *source map* turns such a path back into a
``(line, column)`` position in the original file text, which is what lets a
diagnostic point at the line that caused it.
"""

from __future__ import annotations

import bisect
from typing import Any

__all__ = ["LineIndex", "Path", "SourceMap", "format_path"]

#: A path into a document: object keys as strings, array indices as integers.
Path = tuple[Any, ...]


def format_path(path: Path) -> str:
    """Render a document path the way a format's own documentation would.

    Parameters
    ----------
    path : Path
        Tuple of object keys (:class:`str`) and array indices (:class:`int`).

    Returns
    -------
    str
        Dotted-and-bracketed rendering, or the empty string for the document
        root.

    Examples
    --------
    >>> format_path(("version",))
    'version'
    >>> format_path(("author", 1, "familyName"))
    'author[1].familyName'
    >>> format_path(("project", "urls", "Repository"))
    'project.urls.Repository'

    The document root renders as an empty string, which callers turn into
    ``None`` or a phrase like "the document root":

    >>> format_path(())
    ''

    A leading index is kept in bracket form rather than being promoted to a
    name:

    >>> format_path((0, "name"))
    '[0].name'
    """
    out = ""
    for part in path:
        if isinstance(part, int):
            out += f"[{part}]"
        elif out:
            out += f".{part}"
        else:
            out = str(part)
    return out


class SourceMap:
    """Maps document paths to 1-based ``(line, column)`` positions.

    Positions are strictly best-effort. A source map that could not be built
    is empty rather than absent, and every lookup simply returns ``None``:
    a diagnostic without a line number is still a correct diagnostic, so
    nothing in this package may raise.

    Parameters
    ----------
    positions : dict, optional
        Pre-computed mapping from path to ``(line, column)``.

    Examples
    --------
    >>> source_map = SourceMap({("version",): (4, 3)})
    >>> source_map.locate(("version",))
    (4, 3)

    An unknown path falls back to its nearest known ancestor, so a finding
    about a value the parser could not address precisely still lands near it:

    >>> source_map = SourceMap({("author",): (7, 3)})
    >>> source_map.locate(("author", 2, "familyName"))
    (7, 3)

    With nothing to fall back to, the answer is ``None``:

    >>> SourceMap().locate(("version",)) is None
    True
    """

    def __init__(self, positions: dict[Path, tuple[int, int]] | None = None) -> None:
        self._positions: dict[Path, tuple[int, int]] = positions or {}

    def locate(self, path: Path) -> tuple[int, int] | None:
        """Best known position for ``path``, or its nearest ancestor's.

        Parameters
        ----------
        path : Path
            Path to locate.

        Returns
        -------
        tuple of int, or None
            1-based ``(line, column)``, or ``None`` when neither the path nor
            any ancestor of it is known.
        """
        candidate: Path = tuple(path)
        while True:
            if candidate in self._positions:
                return self._positions[candidate]
            if not candidate:
                return None
            candidate = candidate[:-1]

    def __bool__(self) -> bool:
        """Whether any positions were recorded at all.

        Examples
        --------
        >>> bool(SourceMap())
        False
        >>> bool(SourceMap({(): (1, 1)}))
        True
        """
        return bool(self._positions)


class LineIndex:
    """Converts character offsets into 1-based line and column numbers.

    Built once per file and queried per position, so the conversion stays
    linear in the size of the file rather than quadratic.

    Parameters
    ----------
    text : str
        The full text the offsets refer to.

    Examples
    --------
    >>> index = LineIndex("abc\\ndefg\\n")
    >>> index.position(0)
    (1, 1)
    >>> index.position(2)
    (1, 3)

    The newline itself belongs to the line it terminates, and the character
    after it starts the next line:

    >>> index.position(4)
    (2, 1)
    >>> index.position(6)
    (2, 3)
    """

    def __init__(self, text: str) -> None:
        self._starts = [0]
        for index, char in enumerate(text):
            if char == "\n":
                self._starts.append(index + 1)

    def position(self, offset: int) -> tuple[int, int]:
        """Convert a character offset to a 1-based ``(line, column)`` pair.

        Parameters
        ----------
        offset : int
            Zero-based character offset into the text.

        Returns
        -------
        tuple of int
            The 1-based line and column.
        """
        line = bisect.bisect_right(self._starts, offset) - 1
        return line + 1, offset - self._starts[line] + 1
