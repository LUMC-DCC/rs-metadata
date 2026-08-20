"""Resolve a path inside a parsed document back to a line in the file.

A diagnostic that says *"version is wrong"* costs a maintainer a search; one
that CI renders inline against line 12 costs them nothing. Every adapter
therefore builds a source map alongside the parsed value.

Positions are strictly best-effort. A source map that fails to build returns
no positions at all and validation continues unchanged, so **nothing in this
package raises**: a diagnostic without a line number is still correct.

One module per source syntax, because the four have nothing in common beyond
the interface:

=================== =====================================================
Module              Strategy
=================== =====================================================
:mod:`.base`        Paths, the :class:`SourceMap` interface, offset maths
:mod:`.json_map`    A second, position-only scan over the JSON text
:mod:`.yaml_map`    PyYAML node marks, which already carry positions
:mod:`.keyed`       Line search, for TOML and Debian-control files
=================== =====================================================

Examples
--------
>>> source_map = json_source_map('{"name": "MyTool", "version": "1.0.0"}')
>>> source_map.locate(("version",))
(1, 20)
>>> format_path(("author", 0, "familyName"))
'author[0].familyName'
"""

from __future__ import annotations

from .base import LineIndex, Path, SourceMap, format_path
from .json_map import json_source_map
from .keyed import DcfSourceMap, KeySearchSourceMap, TomlSourceMap
from .yaml_map import yaml_source_map

__all__ = [
    "DcfSourceMap",
    "KeySearchSourceMap",
    "LineIndex",
    "Path",
    "SourceMap",
    "TomlSourceMap",
    "format_path",
    "json_source_map",
    "yaml_source_map",
]
