"""The validation pipeline.

This is the shared core the CLI and the GitHub Action both call. Neither adds
validation behavior of its own, so ``rs-metadata validate`` on a laptop and
the Action in CI can never disagree about whether a repository passes.

The pipeline runs in a fixed order::

    find codemeta.json
        -> validate it against the LUMC profile
        -> find and validate the required CITATION.cff
        -> auto-detect other supported metadata files
        -> parse each with its adapter and map it to CodeMeta concepts
        -> compare every meaningfully comparable concept with the anchor
        -> report errors, warnings and skipped checks
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .adapters import ADAPTERS, ANCHOR, Adapter, SourceError
from .concepts import ConceptMap, ParsedSource
from .consistency import compare
from .diagnostics import Severity
from .profile import validate as validate_profile
from .report import TOOL_URL, Diagnostic, Location, Report, Source


@dataclass
class Options:
    """Options that alter validation.

    Defaults cover a conventional repository. The path overrides support
    layouts such as monorepos, where metadata may live below the root.
    """

    root: Path = Path()
    #: Explicit paths for metadata files that do not sit at the repository
    #: root, keyed by adapter id. A monorepo keeps ``pyproject.toml`` in a
    #: subdirectory while ``codemeta.json`` describes the whole thing.
    sources: dict[str, Path] = field(default_factory=dict)
    #: Alias for ``sources["codemeta"]``, kept because it predates the general
    #: form and appears in published workflows.
    codemeta: Path | None = None
    #: Which severity makes the run fail: ``error``, ``warning`` or ``never``.
    fail_on: str = "error"

    def path_for(self, adapter_id: str) -> Path | None:
        """The explicit path given for one source, resolved against the root.

        Parameters
        ----------
        adapter_id : str
            The adapter's ``id``, for example ``pyproject``.

        Returns
        -------
        Path or None
            The path to use, or ``None`` when no override was given and the
            adapter should look in the root itself.

        Examples
        --------
        With no override, the adapter searches as usual:

        >>> Options(root=Path("/repo")).path_for("pyproject") is None
        True

        A relative override is resolved against the root:

        >>> options = Options(root=Path("/repo"),
        ...                   sources={"pyproject": Path("backend/pyproject.toml")})
        >>> options.path_for("pyproject").as_posix()
        '/repo/backend/pyproject.toml'

        An absolute one is taken as given. What counts as absolute is the
        platform's business — a leading slash is absolute on POSIX but not on
        Windows, which wants a drive — so this asks the platform rather than
        assuming:

        >>> elsewhere = Path("/elsewhere/CITATION.cff").resolve()
        >>> Options(sources={"cff": elsewhere}).path_for("cff") == elsewhere
        True

        ``codemeta`` accepts the older spelling too:

        >>> Options(root=Path("/repo"), codemeta=Path("meta/codemeta.json")
        ...         ).path_for("codemeta").as_posix()
        '/repo/meta/codemeta.json'
        """
        override = self.sources.get(adapter_id)
        if override is None and adapter_id == ANCHOR.id:
            override = self.codemeta
        if override is None:
            return None
        return override if override.is_absolute() else (self.root / override)


def validate(options: Options) -> Report:
    """Validate a repository's metadata.

    Parameters
    ----------
    options : Options
        What to validate, and where. The defaults describe a repository laid
        out at the repository root, which needs no configuration.

    Returns
    -------
    Report
        Every source considered and every finding. Use
        :meth:`~rs_metadata.report.Report.exit_code` to turn it into a process
        status, and the renderers to present it.

    Notes
    -----
    Validation stops when ``codemeta.json`` is missing or unreadable. A
    companion that fails its own schema is reported but not compared.

    Missing optional sources are not findings, but remain in ``sources`` to
    distinguish an absent file from a checked file with no problems.

    See Also
    --------
    rs_metadata.profile.validate : The profile checks alone.
    rs_metadata.consistency.compare : The cross-file comparison alone.

    Examples
    --------
    >>> import json, tempfile
    >>> from pathlib import Path

    A repository with nothing in it fails on the anchor, and says why:

    >>> with tempfile.TemporaryDirectory() as tmp:
    ...     report = validate(Options(root=Path(tmp)))
    >>> report.status
    'failed'
    >>> [d.code for d in report.diagnostics]
    ['source.missing']

    Every source is recorded, including the ones that were looked for and not
    found:

    >>> [(s.id, s.status) for s in report.sources]
    [('codemeta', 'absent')]

    With an anchor present, the profile runs and the required companion is
    reported as missing:

    >>> record = {"@context": "https://w3id.org/codemeta/3.1", "name": "MyTool"}
    >>> with tempfile.TemporaryDirectory() as tmp:
    ...     root = Path(tmp)
    ...     _ = (root / "codemeta.json").write_text(
    ...         json.dumps(record), encoding="utf-8")
    ...     report = validate(Options(root=root))
    >>> "source.missing" in {d.code for d in report.diagnostics}
    True
    >>> "profile.required-field" in {d.code for d in report.diagnostics}
    True

    Optional formats that are absent are listed, but produce no findings:

    >>> from rs_metadata.adapters import companion_adapters
    >>> absent = {s.id for s in report.sources if s.status == "absent"}
    >>> absent == {a.id for a in companion_adapters()}
    True
    """
    root = options.root.resolve()
    report = Report(root=str(options.root))

    anchor_path = _anchor_path(options, root)
    if anchor_path is None or not anchor_path.is_file():
        _report_missing_anchor(report, options, root)
        return report

    relative = _relative(anchor_path, root)
    try:
        anchor = ANCHOR.parse(anchor_path, relative)
    except SourceError as error:
        report.add_source(
            Source(
                id=ANCHOR.id,
                format=ANCHOR.format,
                role="anchor",
                status="unparsable",
                file=relative,
            )
        )
        report.add(_source_error(error, relative))
        return report

    report.add_source(
        Source(
            id=ANCHOR.id,
            format=ANCHOR.format,
            role="anchor",
            status="parsed",
            file=relative,
            format_version=anchor.format_version,
        )
    )

    for diagnostic in validate_profile(anchor):
        report.add(diagnostic)
    anchor_concepts: ConceptMap = ANCHOR.map_to_codemeta(anchor)

    for adapter in ADAPTERS:
        if adapter.role == "anchor":
            continue
        try:
            _run_adapter(report, adapter, root, anchor, anchor_concepts, options)
        except Exception as error:
            # One adapter failing is a bug in that adapter, not a reason to
            # lose the findings from every other source. `internal.error`
            # exists for exactly this, and says the metadata is not
            # necessarily at fault.
            report.add(_internal_error(adapter, error))

    return report


def _internal_error(adapter: Adapter, error: Exception) -> Diagnostic:
    """Report a crash inside one adapter without losing the rest of the run."""
    return Diagnostic(
        code="internal.error",
        severity=Severity.ERROR,
        message=(
            f"The {adapter.format} adapter failed unexpectedly: "
            f"{type(error).__name__}: {error}"
        ),
        location=Location(file=adapter.filenames[0]),
        suggestion=(
            f"This is a bug in rs-metadata, not necessarily in your metadata. "
            f"Please report it at {TOOL_URL}/issues, with the "
            f"{adapter.filenames[0]} that triggered it. Every other source in "
            f"this report was still checked."
        ),
    )


# ---------------------------------------------------------------------------
# Steps
# ---------------------------------------------------------------------------


def _anchor_path(options: Options, root: Path) -> Path | None:
    return options.path_for(ANCHOR.id) or ANCHOR.detect(root)


def _report_missing_anchor(report: Report, options: Options, root: Path) -> None:
    report.add_source(
        Source(
            id=ANCHOR.id,
            format=ANCHOR.format,
            role="anchor",
            status="absent",
            file=ANCHOR.filenames[0],
        )
    )
    override = options.path_for(ANCHOR.id)
    if override is not None:
        message = (
            f"No metadata record was found at {_as_given(options, ANCHOR.id)}, "
            f"the path given for codemeta.json."
        )
        suggestion = (
            "Check the path. Omit the override entirely if codemeta.json is "
            "in the repository root, which is where every consumer looks for it."
        )
    else:
        message = (
            f"No codemeta.json was found in {root}. It is the anchor metadata "
            f"record: the LUMC profile is defined against it, and every other "
            f"metadata file is checked for consistency with it."
        )
        suggestion = (
            "Create codemeta.json in the repository root. Generate one at "
            "https://codemeta.github.io/create/, or copy "
            "examples/minimal/codemeta.json from the rs-metadata repository "
            "and edit it."
        )
    report.add(
        Diagnostic(
            code="source.missing",
            severity=Severity.ERROR,
            message=message,
            location=Location(file="codemeta.json"),
            suggestion=suggestion,
        )
    )


def _run_adapter(
    report: Report,
    adapter: Adapter,
    root: Path,
    anchor: ParsedSource,
    anchor_concepts: ConceptMap,
    options: Options,
) -> None:
    mapping = adapter.mapping
    reference = mapping.reference if mapping else None
    override = options.path_for(adapter.id)
    # An explicit path is a statement that the file is there. If it is not, say
    # so even for an optional format, where silence would otherwise be correct:
    # the run did not do what it was asked to do.
    path = override if override is not None else adapter.detect(root)
    if override is not None and not override.is_file():
        report.add_source(
            Source(
                id=adapter.id,
                format=adapter.format,
                role=adapter.role,
                status="absent",
                file=str(override),
                mapping=reference,
            )
        )
        report.add(
            Diagnostic(
                code="source.missing",
                severity=Severity.ERROR,
                message=(
                    f"No {adapter.format} file was found at "
                    f"{_as_given(options, adapter.id)}, the path given for "
                    f"{adapter.id}."
                ),
                location=Location(file=str(override)),
                suggestion=(
                    f"Check the path. Omit --source {adapter.id}=... entirely "
                    f"if the file is in the repository root, which is where "
                    f"rs-metadata looks by default."
                ),
            )
        )
        return

    if path is None:
        report.add_source(
            Source(
                id=adapter.id,
                format=adapter.format,
                role=adapter.role,
                status="absent",
                file=adapter.filenames[0],
                mapping=reference,
            )
        )
        if adapter.role == "required":
            report.add(_missing_required(adapter))
        # A missing optional format is not a finding. It is recorded in
        # `sources` so the report still says what was looked for.
        return

    relative = _relative(path, root)
    try:
        parsed = adapter.parse(path, relative)
    except SourceError as error:
        report.add_source(
            Source(
                id=adapter.id,
                format=adapter.format,
                role=adapter.role,
                status="unparsable",
                file=relative,
                mapping=reference,
            )
        )
        report.add(_source_error(error, relative))
        return

    report.add_source(
        Source(
            id=adapter.id,
            format=adapter.format,
            role=adapter.role,
            status="parsed",
            # `parsed.file`, not the path on disk: an adapter may name its
            # source better than the filesystem does, and the GitHub one does
            # — its data arrives in a runner-provided temporary file.
            file=parsed.file,
            format_version=parsed.format_version,
            mapping=reference,
        )
    )

    source_diagnostics = adapter.validate_source(parsed)
    for diagnostic in source_diagnostics:
        report.add(diagnostic)

    # Comparing against a file that fails its own specification would produce
    # findings about the wrong problem, so stop here if it is invalid.
    if any(d.severity is Severity.ERROR for d in source_diagnostics):
        return

    if mapping is None:  # pragma: no cover - every companion has a mapping
        return

    parsed.concepts = adapter.map_to_codemeta(parsed)
    diagnostics, checks = compare(
        anchor, anchor_concepts, parsed, parsed.concepts, mapping
    )
    for diagnostic in diagnostics:
        report.add(diagnostic)
    report.checks += checks


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _missing_required(adapter: Adapter) -> Diagnostic:
    filename = adapter.filenames[0]
    return Diagnostic(
        code="source.missing",
        severity=Severity.ERROR,
        message=(
            f"{filename} was not found. It belongs alongside codemeta.json: "
            f'it is what makes GitHub show a "Cite this repository" button, '
            f"and what Zenodo reads when it archives a release. Without it the "
            f"software is not citable through the paths people actually use."
        ),
        location=Location(file=filename),
        suggestion=(
            "Create it interactively at "
            "https://citation-file-format.github.io/cff-initializer-javascript/, "
            "or copy examples/minimal/CITATION.cff from the rs-metadata "
            "repository and edit it."
        ),
    )


def _source_error(error: SourceError, relative: str) -> Diagnostic:
    return Diagnostic(
        code="source.unreadable",
        severity=Severity.ERROR,
        message=error.message,
        location=Location(file=relative, line=error.line),
        suggestion=(
            "Fix the syntax error. Nothing in this file can be validated or "
            "compared until it parses."
        ),
    )


def _as_given(options: Options, adapter_id: str) -> str:
    """The override path as the caller wrote it, in posix form.

    Echoing back what someone typed is more use than the absolute path it
    resolved to, and it keeps the message identical on every platform.
    """
    raw = options.sources.get(adapter_id)
    if raw is None and adapter_id == ANCHOR.id:
        raw = options.codemeta
    return raw.as_posix() if raw is not None else adapter_id


def _relative(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()
