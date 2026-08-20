"""Source positions for JSON text.

:func:`json.loads` returns correct values but no positions, so this module
runs a second, position-only pass over the same text. Values always come from
:func:`json.loads`; the scanner here contributes line numbers and nothing
else, which means a disagreement between the two can degrade an annotation but
can never corrupt the data being validated.
"""

from __future__ import annotations

from typing import ClassVar

from .base import LineIndex, Path, SourceMap

__all__ = ["json_source_map"]

#: A byte-order mark, which is legal at the start of a JSON file and would
#: otherwise be scanned as an unexpected character.
_BOM = "﻿"


class _JsonScanner:
    """A position-recording pass over JSON text.

    Records the offset of every value, and for object members the offset of
    the *key* rather than the value: an annotation reading ``"version":`` is
    easier to place than one pointing into the middle of a line.

    Parameters
    ----------
    text : str
        JSON document text.
    """

    _LITERAL_END: ClassVar[frozenset[str]] = frozenset(",]}\t\n\r ")

    def __init__(self, text: str) -> None:
        self.text = text
        self.length = len(text)
        self.index = 0
        self.offsets: dict[Path, int] = {}

    def scan(self) -> dict[Path, int]:
        """Scan the document and return every path's character offset.

        Returns
        -------
        dict
            Mapping from document path to zero-based character offset.

        Raises
        ------
        ValueError
            If the text is not well-formed JSON. Callers treat this as
            "no positions available" rather than as a validation failure,
            because :func:`json.loads` reports malformed JSON far better.
        """
        self._skip_whitespace()
        self.offsets[()] = self.index
        self._value(())
        return self.offsets

    # -- helpers ----------------------------------------------------------

    def _skip_whitespace(self) -> None:
        while self.index < self.length and self.text[self.index] in " \t\n\r":
            self.index += 1

    def _peek(self) -> str:
        if self.index >= self.length:
            raise ValueError("unexpected end of JSON input")
        return self.text[self.index]

    def _expect(self, char: str) -> None:
        if self._peek() != char:
            raise ValueError(f"expected {char!r} at offset {self.index}")
        self.index += 1

    # -- grammar ----------------------------------------------------------

    def _value(self, path: Path) -> None:
        self._skip_whitespace()
        char = self._peek()
        if char == "{":
            self._object(path)
        elif char == "[":
            self._array(path)
        elif char == '"':
            self._string()
        else:
            self._literal()

    def _object(self, path: Path) -> None:
        self._expect("{")
        self._skip_whitespace()
        if self._peek() == "}":
            self.index += 1
            return
        while True:
            self._skip_whitespace()
            key_offset = self.index
            key = self._string()
            child = (*path, key)
            self.offsets[child] = key_offset
            self._skip_whitespace()
            self._expect(":")
            self._value(child)
            self._skip_whitespace()
            char = self._peek()
            self.index += 1
            if char == ",":
                continue
            if char == "}":
                return
            raise ValueError(f"expected ',' or '}}' at offset {self.index - 1}")

    def _array(self, path: Path) -> None:
        self._expect("[")
        self._skip_whitespace()
        if self._peek() == "]":
            self.index += 1
            return
        position = 0
        while True:
            self._skip_whitespace()
            child = (*path, position)
            self.offsets[child] = self.index
            self._value(child)
            self._skip_whitespace()
            char = self._peek()
            self.index += 1
            if char == ",":
                position += 1
                continue
            if char == "]":
                return
            raise ValueError(f"expected ',' or ']' at offset {self.index - 1}")

    def _string(self) -> str:
        self._expect('"')
        chunks: list[str] = []
        while True:
            if self.index >= self.length:
                raise ValueError("unterminated string")
            char = self.text[self.index]
            if char == '"':
                self.index += 1
                return "".join(chunks)
            if char == "\\":
                self.index += 1
                if self.index >= self.length:
                    raise ValueError("unterminated escape")
                escape = self.text[self.index]
                if escape == "u":
                    chunks.append(
                        chr(int(self.text[self.index + 1 : self.index + 5], 16))
                    )
                    self.index += 5
                else:
                    chunks.append(
                        {
                            '"': '"',
                            "\\": "\\",
                            "/": "/",
                            "b": "\b",
                            "f": "\f",
                            "n": "\n",
                            "r": "\r",
                            "t": "\t",
                        }.get(escape, escape)
                    )
                    self.index += 1
                continue
            chunks.append(char)
            self.index += 1

    def _literal(self) -> None:
        start = self.index
        while (
            self.index < self.length and self.text[self.index] not in self._LITERAL_END
        ):
            self.index += 1
        if self.index == start:
            # An empty literal means a missing value, as in `{"name": }`.
            # Accepting it would let the scanner claim positions for a
            # document json.loads is about to reject.
            raise ValueError(f"expected a value at offset {start}")


def json_source_map(text: str) -> SourceMap:
    """Build a source map for JSON text.

    Parameters
    ----------
    text : str
        The JSON document as it appears on disk.

    Returns
    -------
    SourceMap
        Positions for every value in the document. Empty if the text could
        not be scanned; this function never raises.

    Examples
    --------
    >>> document = '{\\n  "name": "MyTool",\\n  "version": "1.0.0"\\n}'
    >>> source_map = json_source_map(document)
    >>> source_map.locate(("version",))
    (3, 3)

    Positions point at the *key*, so an annotation reads naturally against the
    line it lands on. Array elements are addressed by index:

    >>> source_map = json_source_map('{"author": [{"familyName": "Doe"}]}')
    >>> source_map.locate(("author", 0, "familyName"))
    (1, 14)

    Malformed JSON yields an empty map rather than an exception, because the
    parser reports the syntax error with a far better message:

    >>> bool(json_source_map('{"name": }'))
    False
    """
    try:
        scanner = _JsonScanner(text.lstrip(_BOM))
        offsets = scanner.scan()
    except (ValueError, IndexError, KeyError):
        return SourceMap()
    index = LineIndex(text)
    return SourceMap({path: index.position(offset) for path, offset in offsets.items()})
