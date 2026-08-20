"""GitHub Actions rendering: inline annotations and a job summary.

Annotations put each finding on the line of the file that caused it, so a
reviewer sees the problem in the pull request diff rather than in a log. The
job summary gives the same information in one readable place, because GitHub
caps annotations at ten per severity per step.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import TextIO

from .. import CODEMETA_VERSION, PROFILE_NAME, PROFILE_VERSION, __version__
from ..diagnostics import Severity
from ..report import Diagnostic, Report

_COMMAND = {
    Severity.ERROR: "error",
    Severity.WARNING: "warning",
    Severity.INFO: "notice",
}

_STATUS_TEXT = {
    "passed": "✅ Passed",
    "passed-with-warnings": "⚠️ Passed with warnings",
    "failed": "❌ Failed",
}

_STATUS_ICON = {"parsed": "✓", "absent": "–", "unparsable": "✗"}


def _escape_data(text: str) -> str:
    return text.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def _escape_property(text: str) -> str:
    return _escape_data(text).replace(":", "%3A").replace(",", "%2C")


def annotation(diagnostic: Diagnostic) -> str:
    """Render one diagnostic as a GitHub workflow command."""
    properties = [f"title=rs-metadata: {diagnostic.code}"]
    location = diagnostic.primary_location()
    if location is not None:
        properties.append(f"file={location.file}")
        if location.line:
            properties.append(f"line={location.line}")
            if location.column:
                properties.append(f"col={location.column}")

    body = diagnostic.message
    if diagnostic.suggestion:
        body = f"{body}\n\nSuggested fix: {diagnostic.suggestion}"

    rendered = ",".join(_escape_property(item) for item in properties)
    return f"::{_COMMAND[diagnostic.severity]} {rendered}::{_escape_data(body)}"


def render(report: Report, stream: TextIO) -> None:
    """Emit workflow commands for every finding."""
    for diagnostic in report.sorted_diagnostics():
        print(annotation(diagnostic), file=stream)


def summary(report: Report) -> str:
    """Build the Markdown job summary."""
    lines = [
        "## rs-metadata",
        "",
        f"**{_STATUS_TEXT[report.status]}**: "
        f"{report.count(Severity.ERROR)} errors, "
        f"{report.count(Severity.WARNING)} warnings, "
        f"{report.count(Severity.INFO)} notes "
        f"across {report.checks} consistency checks.",
        "",
        f"<sub>rs-metadata {__version__} · {PROFILE_NAME} {PROFILE_VERSION} · "
        f"CodeMeta {CODEMETA_VERSION}</sub>",
        "",
        "### Metadata sources",
        "",
        "| | File | Format | Role |",
        "|---|---|---|---|",
    ]
    for source in report.sources:
        detail = source.format
        if source.format_version:
            detail = f"{detail} {source.format_version}"
        if source.status == "absent":
            detail = "_not present_"
        lines.append(
            f"| {_STATUS_ICON[source.status]} | `{source.file or source.id}` | "
            f"{detail} | {source.role} |"
        )

    findings = [
        d for d in report.sorted_diagnostics() if d.severity is not Severity.INFO
    ]
    if findings:
        lines += ["", "### Findings", ""]
        for diagnostic in findings:
            icon = "❌" if diagnostic.severity is Severity.ERROR else "⚠️"
            location = diagnostic.primary_location()
            where = f" at `{location.describe()}`" if location else ""
            lines.append(f"{icon} **`{diagnostic.code}`**{where}")
            lines.append("")
            lines.append(f"> {diagnostic.message}")
            if diagnostic.suggestion:
                lines.append(">")
                lines.append(f"> **Fix:** {diagnostic.suggestion}")
            lines.append("")
    else:
        lines += ["", "No errors or warnings. 🎉", ""]

    return "\n".join(lines) + "\n"


def write_summary(report: Report) -> None:
    """Append the job summary to ``$GITHUB_STEP_SUMMARY`` when running in CI."""
    target = os.environ.get("GITHUB_STEP_SUMMARY")
    if not target:
        return
    with Path(target).open("a", encoding="utf-8") as handle:
        handle.write(summary(report))


def write_outputs(report: Report, report_path: Path | None) -> None:
    """Expose the outcome as step outputs for downstream workflow steps."""
    target = os.environ.get("GITHUB_OUTPUT")
    if not target:
        return
    values = {
        "status": report.status,
        "errors": str(report.count(Severity.ERROR)),
        "warnings": str(report.count(Severity.WARNING)),
        "notes": str(report.count(Severity.INFO)),
        "report-path": str(report_path) if report_path else "",
    }
    with Path(target).open("a", encoding="utf-8") as handle:
        for key, value in values.items():
            handle.write(f"{key}={value}\n")
