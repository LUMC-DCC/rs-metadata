"""Human-readable rendering of a report, for terminals.

Generated entirely from the report model. Nothing is computed here that is not
already in the JSON output, so what is read locally and what a
machine consumes from CI are the same findings in two presentations.
"""

from __future__ import annotations

import os
import sys
from typing import TextIO

from .. import CODEMETA_VERSION, PROFILE_NAME, PROFILE_VERSION, __version__
from ..diagnostics import Severity
from ..report import Diagnostic, Location, Report

_RESET = "\033[0m"
_STYLES = {
    "error": "\033[1;31m",
    "warning": "\033[1;33m",
    "info": "\033[1;36m",
    "dim": "\033[2m",
    "bold": "\033[1m",
    "green": "\033[1;32m",
}

_STATUS_LABEL = {
    "passed": ("green", "passed"),
    "passed-with-warnings": ("warning", "passed with warnings"),
    "failed": ("error", "failed"),
}

_ROLE_LABEL = {
    "anchor": "anchor record",
    "required": "required",
    "optional": "auto-detected",
}


class _Palette:
    def __init__(self, enabled: bool) -> None:
        self.enabled = enabled

    def __call__(self, style: str, text: str) -> str:
        if not self.enabled or style not in _STYLES:
            return text
        return f"{_STYLES[style]}{text}{_RESET}"


def use_color(mode: str, stream: TextIO) -> bool:
    """Decide whether to emit ANSI color.

    Honors ``NO_COLOR`` and ``FORCE_COLOR``, which is what a reader
    piping output into a file or a CI log expects.
    """
    if mode == "always":
        return True
    if mode == "never":
        return False
    if os.environ.get("NO_COLOR"):
        return False
    if os.environ.get("FORCE_COLOR"):
        return True
    return bool(getattr(stream, "isatty", lambda: False)())


def render(
    report: Report,
    stream: TextIO | None = None,
    *,
    color: str = "auto",
    verbose: bool = False,
) -> None:
    """Write the report to ``stream`` in human-readable form."""
    out = stream if stream is not None else sys.stdout
    paint = _Palette(use_color(color, out))

    def write(text: str = "") -> None:
        print(text, file=out)

    write(
        paint(
            "dim",
            f"rs-metadata {__version__} · {PROFILE_NAME} {PROFILE_VERSION} · "
            f"CodeMeta {CODEMETA_VERSION}",
        )
    )
    write()
    _render_sources(report, write, paint)

    diagnostics = report.sorted_diagnostics()
    shown = (
        diagnostics
        if verbose
        else [d for d in diagnostics if d.severity is not Severity.INFO]
    )

    if shown:
        write()
        for diagnostic in shown:
            _render_diagnostic(diagnostic, write, paint)

    _render_summary(report, write, paint, shown, len(diagnostics) - len(shown))


def _render_sources(report: Report, write, paint: _Palette) -> None:  # type: ignore[no-untyped-def]
    write(paint("bold", "Metadata sources"))
    width = max(
        (len(source.file or source.id) for source in report.sources), default=12
    )
    for source in report.sources:
        name = source.file or source.id
        detail = source.format
        if source.format_version:
            detail = f"{detail} {source.format_version}"
        if source.status == "absent":
            line = f"  {name:<{width}}  {paint('dim', 'not present')}"
        elif source.status == "unparsable":
            line = f"  {name:<{width}}  {paint('error', 'could not be parsed')}"
        else:
            line = (
                f"  {name:<{width}}  {detail} "
                f"{paint('dim', '(' + _ROLE_LABEL[source.role] + ')')}"
            )
        write(line)


def _render_diagnostic(diagnostic: Diagnostic, write, paint: _Palette) -> None:  # type: ignore[no-untyped-def]
    severity = diagnostic.severity.value
    label = paint(severity, severity.upper())
    write(f"{label} {paint('dim', '[' + diagnostic.code + ']')}")
    if diagnostic.property:
        write(f"Property: {paint('bold', diagnostic.property)}")
    write()

    if diagnostic.anchor or diagnostic.source:
        for side in (diagnostic.anchor, diagnostic.source):
            if side is not None:
                _render_side(side, write, paint)
    elif diagnostic.location is not None:
        _render_side(diagnostic.location, write, paint)

    write(f"  {diagnostic.message}")
    if diagnostic.suggestion:
        write()
        write(f"  {paint('bold', 'Suggested fix:')}")
        for line in _wrap(diagnostic.suggestion):
            write(f"    {line}")
    write()


def _render_side(location: Location, write, paint: _Palette) -> None:  # type: ignore[no-untyped-def]
    write(f"  {paint('bold', location.describe())}")
    if location.path and location.value is not None:
        write(f"    {location.path} = {location.value}")
    elif location.path:
        write(f"    {location.path}")
    write()


def _render_summary(  # type: ignore[no-untyped-def]
    report: Report,
    write,
    paint: _Palette,
    shown: list[Diagnostic],
    hidden: int,
) -> None:
    counts = [
        (report.count(Severity.ERROR), "error"),
        (report.count(Severity.WARNING), "warning"),
        (report.count(Severity.INFO), "note"),
    ]
    parts = [
        paint(
            name if name != "note" else "info",
            f"{count} {name}{'' if count == 1 else 's'}",
        )
        for count, name in counts
        if count
    ]
    if not parts:
        parts = [paint("green", "no findings")]
    summary = ", ".join(parts)
    write(f"{summary}  {paint('dim', f'({report.checks} consistency checks)')}")
    if hidden:
        write(
            paint(
                "dim",
                f"{hidden} informational finding{'' if hidden == 1 else 's'} "
                f"hidden; re-run with --verbose to see them.",
            )
        )
    style, text = _STATUS_LABEL[report.status]
    write(f"Result: {paint(style, text)}")
    if shown:
        # Name a finding the reader can actually see; suggesting `explain` for
        # a code that was filtered out is a dead end.
        write(
            paint(
                "dim",
                f"Explain any finding with: rs-metadata explain {shown[0].code}",
            )
        )


def _wrap(text: str, width: int = 76) -> list[str]:
    import textwrap

    return textwrap.wrap(" ".join(text.split()), width=width) or [""]
