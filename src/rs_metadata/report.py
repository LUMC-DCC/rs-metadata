"""The validation report: rs-metadata's single output contract.

Everything the validator learns ends up in a :class:`Report`. The CLI, the
GitHub Action and any institutional tooling render *this* model; none of them
re-derive validation behavior. That is what keeps ``rs-metadata validate`` on
a laptop and the Action in CI from ever disagreeing.

The serialized form is specified by ``schema/rs-metadata-report.schema.json``
and is validated against that schema in the test suite, so the schema cannot
drift away from the code.
"""

from __future__ import annotations

import datetime as dt
import os
from dataclasses import dataclass, field
from typing import Any

from . import (
    CODEMETA_VERSION,
    PROFILE_NAME,
    PROFILE_VERSION,
    __version__,
)
from .diagnostics import Severity, get

TOOL_URL = "https://github.com/LUMC-DCC/rs-metadata"

#: Values longer than this are truncated when echoed back in a report, so a
#: pasted-in abstract cannot make a diagnostic unreadable.
MAX_VALUE_CHARS = 300


def _truncate(value: Any) -> Any:
    if isinstance(value, str) and len(value) > MAX_VALUE_CHARS:
        return value[: MAX_VALUE_CHARS - 1] + "…"
    return value


@dataclass(frozen=True)
class MappingRef:
    """Which crosswalk related a source to CodeMeta, and where it came from.

    Carried on every consistency finding so a reader can tell a mapping taken
    from the upstream CodeMeta crosswalk tables apart from one rs-metadata
    introduced itself.
    """

    id: str
    origin: str
    version: str | None = None
    source: str | None = None
    retrieved: str | None = None

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {"id": self.id, "origin": self.origin}
        if self.version:
            data["version"] = self.version
        if self.source:
            data["source"] = self.source
        if self.retrieved:
            data["retrieved"] = self.retrieved
        return data


@dataclass(frozen=True)
class Location:
    """Where in a file a finding applies.

    ``line`` and ``column`` are resolved from the original file text rather
    than reconstructed from the parsed value, so CI annotations land on the
    offending line instead of at the top of the file.
    """

    file: str
    path: str | None = None
    line: int | None = None
    column: int | None = None
    value: Any = None

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {"file": self.file}
        if self.path is not None:
            data["path"] = self.path
        if self.line is not None:
            data["line"] = self.line
        if self.column is not None:
            data["column"] = self.column
        if self.value is not None:
            data["value"] = _truncate(self.value)
        return data

    def describe(self) -> str:
        """Render as ``file:line``, or just ``file`` when no line is known.

        Returns
        -------
        str
            A clickable-looking location for terminal output.

        Examples
        --------
        >>> Location(file="codemeta.json", line=12).describe()
        'codemeta.json:12'

        A missing line is normal because source positions are best-effort. In
        that case, return the filename rather than a misleading line 0:

        >>> Location(file="codemeta.json").describe()
        'codemeta.json'
        """
        return f"{self.file}:{self.line}" if self.line else self.file


@dataclass(frozen=True)
class Diagnostic:
    """One finding. Never generic: it names the metadata, the value and the fix."""

    code: str
    severity: Severity
    message: str
    property: str | None = None
    location: Location | None = None
    anchor: Location | None = None
    source: Location | None = None
    strategy: str | None = None
    rule: str | None = None
    mapping: MappingRef | None = None
    suggestion: str | None = None

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "code": self.code,
            "severity": self.severity.value,
            "message": self.message,
        }
        if self.property:
            data["property"] = self.property
        for name in ("location", "anchor", "source"):
            value = getattr(self, name)
            if value is not None:
                data[name] = value.to_dict()
        if self.strategy:
            data["strategy"] = self.strategy
        if self.rule:
            data["rule"] = self.rule
        if self.mapping is not None:
            data["mapping"] = self.mapping.to_dict()
        if self.suggestion:
            data["suggestion"] = self.suggestion
        data["docs"] = get(self.code).docs
        return data

    def primary_location(self) -> Location | None:
        """The location an editor or CI annotation should point at.

        Returns
        -------
        Location or None
            The single most relevant place, or ``None`` for a finding about
            the repository as a whole.

        Notes
        -----
        Consistency findings point to ``codemeta.json`` because it is the
        canonical record a maintainer is expected to correct.

        Examples
        --------
        A profile finding points at where it was found:

        >>> from rs_metadata.diagnostics import Severity
        >>> finding = Diagnostic(
        ...     code="profile.required-field", severity=Severity.ERROR,
        ...     message="x", location=Location(file="codemeta.json", line=3),
        ... )
        >>> finding.primary_location().describe()
        'codemeta.json:3'

        A consistency finding prefers the anchor over the source:

        >>> finding = Diagnostic(
        ...     code="consistency.mismatch", severity=Severity.ERROR,
        ...     message="x",
        ...     anchor=Location(file="codemeta.json", line=10),
        ...     source=Location(file="CITATION.cff", line=8),
        ... )
        >>> finding.primary_location().describe()
        'codemeta.json:10'
        """
        return self.location or self.anchor or self.source

    def sort_key(self) -> tuple[Any, ...]:
        location = self.primary_location()
        return (
            self.severity.rank,
            location.file if location else "",
            location.line or 0 if location else 0,
            self.property or "",
            self.code,
            self.message,
        )


@dataclass
class Source:
    """A metadata file that was considered, whether or not it was found.

    Absent sources are recorded too. A report that lists ``pyproject.toml`` as
    ``absent`` tells the reader something a silent report does not: that
    rs-metadata looked, and there was nothing there.
    """

    id: str
    format: str
    role: str
    status: str
    file: str | None = None
    format_version: str | None = None
    mapping: MappingRef | None = None

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "id": self.id,
            "format": self.format,
            "role": self.role,
            "status": self.status,
        }
        if self.file is not None:
            data["file"] = self.file
        if self.format_version is not None:
            data["formatVersion"] = self.format_version
        if self.mapping is not None:
            data["mapping"] = self.mapping.to_dict()
        return data


@dataclass
class Report:
    """The complete outcome of one validation run."""

    root: str = "."
    sources: list[Source] = field(default_factory=list)
    diagnostics: list[Diagnostic] = field(default_factory=list)
    checks: int = 0

    # -- building ---------------------------------------------------------

    def add(self, diagnostic: Diagnostic) -> None:
        self.diagnostics.append(diagnostic)

    def add_source(self, source: Source) -> None:
        self.sources.append(source)

    def count(self, severity: Severity) -> int:
        return sum(1 for d in self.diagnostics if d.severity is severity)

    # -- outcome ----------------------------------------------------------

    @property
    def errors(self) -> list[Diagnostic]:
        return [d for d in self.diagnostics if d.severity is Severity.ERROR]

    @property
    def warnings(self) -> list[Diagnostic]:
        return [d for d in self.diagnostics if d.severity is Severity.WARNING]

    @property
    def status(self) -> str:
        """Overall outcome, describing the findings rather than the build.

        Returns
        -------
        {"passed", "passed-with-warnings", "failed"}
            ``failed`` if any error was found, ``passed-with-warnings`` if
            only warnings were, ``passed`` otherwise.

        Notes
        -----
        Independent of :meth:`exit_code`. A run can report
        ``passed-with-warnings`` and still exit non-zero under
        ``--fail-on warning``, because the status describes the *metadata* and
        the exit code describes the *policy*.

        Examples
        --------
        >>> from rs_metadata.diagnostics import Severity
        >>> def finding(severity):
        ...     return Diagnostic(code="internal.error", severity=severity,
        ...                       message="x")
        >>> Report().status
        'passed'
        >>> Report(diagnostics=[finding(Severity.INFO)]).status
        'passed'
        >>> Report(diagnostics=[finding(Severity.WARNING)]).status
        'passed-with-warnings'
        >>> Report(diagnostics=[finding(Severity.ERROR),
        ...                     finding(Severity.WARNING)]).status
        'failed'
        """
        if self.count(Severity.ERROR):
            return "failed"
        if self.count(Severity.WARNING):
            return "passed-with-warnings"
        return "passed"

    def exit_code(self, fail_on: str = "error") -> int:
        """Map the report onto a process exit status.

        Parameters
        ----------
        fail_on : {"error", "warning", "never"}, optional
            Lowest severity that should fail the run.

        Returns
        -------
        int
            ``1`` if the run should fail, ``0`` otherwise.

        Notes
        -----
        Severity is a property of a finding; turning severity into a build
        failure is *policy*, and lives here rather than in the checks. That
        separation is what lets one report drive a strict institutional gate
        and a lenient local check without re-running anything.

        Examples
        --------
        >>> from rs_metadata.diagnostics import Severity
        >>> def finding(severity):
        ...     return Diagnostic(code="internal.error", severity=severity,
        ...                       message="x")

        Warnings are non-fatal by default, which is what makes recommendations
        safe to ship:

        >>> warned = Report(diagnostics=[finding(Severity.WARNING)])
        >>> warned.exit_code()
        0
        >>> warned.exit_code("warning")
        1

        Errors fail unless failures are switched off, which is useful when
        adopting the standard across existing repositories:

        >>> failed = Report(diagnostics=[finding(Severity.ERROR)])
        >>> failed.exit_code(), failed.exit_code("never")
        (1, 0)

        Informational findings never fail a run:

        >>> Report(diagnostics=[finding(Severity.INFO)]).exit_code("warning")
        0
        """
        if fail_on == "never":
            return 0
        if self.count(Severity.ERROR):
            return 1
        if fail_on == "warning" and self.count(Severity.WARNING):
            return 1
        return 0

    def sorted_diagnostics(self) -> list[Diagnostic]:
        return sorted(self.diagnostics, key=lambda d: d.sort_key())

    # -- serialization ----------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "status": self.status,
            "tool": {"name": "rs-metadata", "version": __version__, "url": TOOL_URL},
            "profile": {
                "name": PROFILE_NAME,
                "version": PROFILE_VERSION,
                "codemetaVersion": CODEMETA_VERSION,
                "schema": "codemeta-lumc.schema.json",
            },
            "root": self.root,
            "sources": [source.to_dict() for source in self.sources],
            "summary": {
                "error": self.count(Severity.ERROR),
                "warning": self.count(Severity.WARNING),
                "info": self.count(Severity.INFO),
                "checks": self.checks,
            },
            "diagnostics": [d.to_dict() for d in self.sorted_diagnostics()],
        }
        generated = _generated_at()
        if generated is not None:
            data["generatedAt"] = generated
        return data


def _generated_at() -> str | None:
    """Timestamp the run, honoring ``SOURCE_DATE_EPOCH`` for reproducibility.

    Set ``SOURCE_DATE_EPOCH`` to compare two reports byte for byte, which the
    golden-file tests rely on.
    """
    epoch = os.environ.get("SOURCE_DATE_EPOCH")
    if epoch:
        try:
            moment = dt.datetime.fromtimestamp(int(epoch), tz=dt.UTC)
        except (ValueError, OverflowError, OSError):
            return None
        return moment.isoformat().replace("+00:00", "Z")
    return (
        dt.datetime.now(tz=dt.UTC)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )
