"""JSON rendering of a report.

The JSON report is the stable machine interface. It is meant to be consumed
outside GitHub Actions too, so institutional tooling can inventory metadata
quality across repositories without scraping CI logs.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TextIO

from ..report import Report


def render(report: Report, stream: TextIO) -> None:
    json.dump(report.to_dict(), stream, indent=2, ensure_ascii=False)
    stream.write("\n")


def write(report: Report, path: Path) -> None:
    """Write the report to a file, creating parent directories as needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        render(report, handle)
