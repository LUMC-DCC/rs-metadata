"""Refreshing the reference data vendored into ``src/rs_metadata/data``.

rs-metadata validates offline: no check performed during ``rs-metadata
validate`` may depend on network access, so every external vocabulary the
validator consults is vendored into the package. This package is the only code
in the project that touches the network, and ``scripts/vendor_reference_data.py``
is the only supported way to run it.

The modules divide by upstream rather than by processing stage, so refreshing
one vocabulary means reading one file:

``sources``
    Every upstream document, declared as data, and the downloading.
``codemeta``, ``schemaorg``, ``vocabularies``, ``hints``, ``licenses``
    Pure parsers, one per upstream. No network access, no file access.
``build``
    Which vendored file is derived from which sources, and the provenance
    that follows from that.
"""

from .build import ARTIFACTS, DATA_DIR, refresh
from .sources import SOURCES

__all__ = ["ARTIFACTS", "DATA_DIR", "SOURCES", "refresh"]
