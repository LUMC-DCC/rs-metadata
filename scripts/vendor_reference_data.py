#!/usr/bin/env python3
"""Refresh the reference data vendored into ``src/rs_metadata/data``.

Usage::

    poetry run python scripts/vendor_reference_data.py          # refresh
    poetry run python scripts/vendor_reference_data.py --check  # verify only

``--check`` re-fetches the upstream sources and reports whether the vendored
copies are stale. It is intended for a scheduled CI job, never for the
validator itself.

The work lives in the :mod:`vendoring` package next to this file; this is only
the command-line front door.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from vendoring import refresh


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="report whether vendored data is stale instead of rewriting it",
    )
    args = parser.parse_args()
    return refresh(check=args.check)


if __name__ == "__main__":
    raise SystemExit(main())
