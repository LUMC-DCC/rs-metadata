"""One module per supported metadata format, plus the registry that lists them.

An adapter answers everything format-specific: where the file lives, how to
read it, whether it satisfies its *own* specification, and how to express its
contents as CodeMeta concepts. Nothing downstream knows that TOML or Debian
control files exist.

See ``docs/developing/adapters.md`` for how to add one.
"""

from __future__ import annotations

from .base import Adapter, SourceError
from .registry import ADAPTERS, ANCHOR, companion_adapters, get_adapter

__all__ = [
    "ADAPTERS",
    "ANCHOR",
    "Adapter",
    "SourceError",
    "companion_adapters",
    "get_adapter",
]
