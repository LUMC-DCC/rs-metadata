"""Reading the vendored files that ship inside the package.

Everything the validator consults is a file in ``data/``, so CI gives
the same answer wherever it runs. Refreshing those files is a
deliberate act, performed by ``scripts/vendor_reference_data.py``.
"""

from __future__ import annotations

import json
from importlib import resources
from typing import Any, cast

DATA_PACKAGE = "rs_metadata.data"
SCHEMA_PACKAGE = "rs_metadata.schema"

__all__ = ["DATA_PACKAGE", "SCHEMA_PACKAGE", "load"]


def load(package: str, name: str) -> dict[str, Any]:
    """Read a packaged JSON document.

    Every vendored file is an object at the top level, so the cast is the type
    boundary between untyped JSON and the rest of the package.
    """
    text = resources.files(package).joinpath(name).read_text(encoding="utf-8")
    return cast(dict[str, Any], json.loads(text))
