"""The ``rs-metadata`` command-line interface.

Thin by design: it parses arguments, calls :func:`rs_metadata.core.validate`,
renders the report and picks an exit status. The GitHub Action runs this same
command, so anything seen locally is exactly what CI will see.
"""

from __future__ import annotations

import argparse
import contextlib
import sys
from pathlib import Path

from . import CODEMETA_VERSION, PROFILE_VERSION, __version__
from .adapters import ADAPTERS
from .core import Options, validate
from .diagnostics import CATALOG, get
from .renderers import github, json_, text
from .scaffold import plan as plan_scaffold
from .scaffold import write as write_scaffold

EXIT_OK = 0
EXIT_FINDINGS = 1
EXIT_USAGE = 2

_EPILOG = """\
examples:
  rs-metadata init                        create any missing metadata files
  rs-metadata validate                    validate the current directory
  rs-metadata validate path/to/repo       validate another repository
  rs-metadata validate --format json      emit the machine-readable report
  rs-metadata validate --strict           treat warnings as failures
  rs-metadata explain consistency.mismatch
"""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="rs-metadata",
        description=(
            "Validate research software metadata against the LUMC CodeMeta "
            "profile, and check that codemeta.json agrees with the other "
            "metadata files in the repository."
        ),
        epilog=_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--version",
        action="version",
        version=(
            f"rs-metadata {__version__} (LUMC profile {PROFILE_VERSION}, "
            f"CodeMeta {CODEMETA_VERSION})"
        ),
    )
    subparsers = parser.add_subparsers(dest="command", metavar="command")

    check = subparsers.add_parser(
        "validate",
        help="validate a repository's metadata",
        description=(
            "Validate codemeta.json against the LUMC profile, then compare it "
            "with every other supported metadata file found in the repository. "
            "Optional formats that are not present are skipped silently."
        ),
    )
    check.add_argument(
        "path",
        nargs="?",
        default=".",
        type=Path,
        help="repository to validate (default: the current directory)",
    )
    check.add_argument(
        "--source",
        action="append",
        default=[],
        metavar="ID=PATH",
        help=(
            "path to one metadata file that is not in the repository root, "
            f"for example --source pyproject=backend/pyproject.toml. Repeatable. "
            f"Known ids: {', '.join(adapter.id for adapter in ADAPTERS)}"
        ),
    )
    check.add_argument(
        "--codemeta",
        type=Path,
        metavar="PATH",
        help="alias for --source codemeta=PATH",
    )
    check.add_argument(
        "--format",
        choices=("text", "json", "github"),
        default="text",
        help="output format (default: text)",
    )
    check.add_argument(
        "--report",
        type=Path,
        metavar="FILE",
        help="also write the machine-readable JSON report to FILE",
    )
    check.add_argument(
        "--fail-on",
        choices=("error", "warning", "never"),
        default="error",
        help="lowest severity that makes the command fail (default: error)",
    )
    check.add_argument(
        "--strict",
        action="store_true",
        help="shorthand for --fail-on warning",
    )
    check.add_argument(
        "--verbose",
        action="store_true",
        help="also show informational findings in text output",
    )
    check.add_argument(
        "--color",
        choices=("auto", "always", "never"),
        default="auto",
        help="colorize text output (default: auto)",
    )

    start = subparsers.add_parser(
        "init",
        help="create the metadata files this repository is missing",
        description=(
            "Create codemeta.json, CITATION.cff and a CI workflow, filling in "
            "whatever can be read from packaging metadata and the git remote. "
            "Existing files are never overwritten. Afterwards, run "
            "`rs-metadata validate` to see which values still need replacing."
        ),
    )
    start.add_argument(
        "path",
        nargs="?",
        default=".",
        type=Path,
        help="repository to set up (default: the current directory)",
    )
    start.add_argument(
        "--dry-run",
        action="store_true",
        help="show what would be created without writing anything",
    )

    explain = subparsers.add_parser(
        "explain",
        help="explain a diagnostic code",
        description=(
            "Print what a diagnostic code means, why it is reported and how to "
            "resolve it."
        ),
    )
    explain.add_argument(
        "code",
        nargs="?",
        help="diagnostic code, for example consistency.mismatch",
    )

    return parser


def _survive_a_narrow_console() -> None:
    """Stop an unencodable character in someone's metadata from killing the run.

    A console whose encoding cannot represent a value being reported — a
    Windows code page and a Polish author name, say — raises
    ``UnicodeEncodeError`` from ``print``, and the tool dies with a traceback
    instead of a report. Names outside Latin-1 are ordinary in research
    software, so this is a real failure and not an edge case.

    ``backslashreplace`` keeps the run alive and, unlike ``replace``, leaves
    the character identifiable rather than turning it into a question mark.
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:  # pragma: no cover - not a text stream
            continue
        with contextlib.suppress(ValueError, OSError):
            reconfigure(errors="backslashreplace")


def main(argv: list[str] | None = None) -> int:
    _survive_a_narrow_console()
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command is None:
        parser.print_help()
        return EXIT_USAGE
    if args.command == "explain":
        return _explain(args.code)
    if args.command == "init":
        return _init(args)
    return _validate(args)


def _validate(args: argparse.Namespace) -> int:
    root: Path = args.path
    if not root.is_dir():
        print(
            f"rs-metadata: {root} is not a directory.",
            file=sys.stderr,
        )
        return EXIT_USAGE

    try:
        sources = _parse_sources(args.source)
    except ValueError as error:
        print(f"rs-metadata: {error}", file=sys.stderr)
        return EXIT_USAGE

    fail_on = "warning" if args.strict else args.fail_on
    report = validate(
        Options(root=root, sources=sources, codemeta=args.codemeta, fail_on=fail_on)
    )

    if args.format == "json":
        json_.render(report, sys.stdout)
    elif args.format == "github":
        github.render(report, sys.stdout)
        github.write_summary(report)
        github.write_outputs(report, args.report)
        text.render(report, sys.stdout, color=args.color, verbose=args.verbose)
    else:
        text.render(report, sys.stdout, color=args.color, verbose=args.verbose)

    if args.report is not None:
        json_.write(report, args.report)

    return report.exit_code(fail_on)


def _init(args: argparse.Namespace) -> int:
    root: Path = args.path
    if not root.is_dir():
        print(f"rs-metadata: {root} is not a directory.", file=sys.stderr)
        return EXIT_USAGE

    proposed = plan_scaffold(root)

    for note in proposed.inferred:
        print(f"  read {note}")
    for relative in proposed.existing:
        print(f"  kept {relative} (already present)")

    if not proposed.create:
        print("\nEverything is already in place. Run `rs-metadata validate`.")
        return EXIT_OK

    if args.dry_run:
        for relative in proposed.create:
            print(f"  would create {relative}")
        return EXIT_OK

    for relative in write_scaffold(root, proposed):
        print(f"  wrote {relative}")

    print(
        "\nThe new files carry placeholder values where nothing could be "
        "inferred.\nRun `rs-metadata validate` to see which ones still need a "
        "real value."
    )
    return EXIT_OK


def _explain(code: str | None) -> int:
    if not code:
        print("Diagnostic codes:\n")
        width = max(len(item) for item in CATALOG)
        for name in sorted(CATALOG):
            entry = CATALOG[name]
            print(f"  {name:<{width}}  {entry.severity.value:<7}  {entry.title}")
        print("\nRun `rs-metadata explain <code>` for details on one of them.")
        return EXIT_OK

    try:
        entry = get(code)
    except KeyError:
        print(f"rs-metadata: unknown diagnostic code {code!r}.", file=sys.stderr)
        print(
            "Run `rs-metadata explain` with no argument to list every code.",
            file=sys.stderr,
        )
        return EXIT_USAGE

    print(f"{entry.code}  ({entry.severity.value})")
    print(f"{entry.title}\n")
    print(_wrap(entry.description))
    if entry.remediation:
        print(f"\nHow to resolve it:\n{_wrap(entry.remediation)}")
    print(f"\nDocumentation: {entry.docs}")
    return EXIT_OK


def _parse_sources(pairs: list[str]) -> dict[str, Path]:
    """Turn ``--source ID=PATH`` arguments into a path map.

    Parameters
    ----------
    pairs : list of str
        Raw ``ID=PATH`` strings, in the order given.

    Returns
    -------
    dict
        Adapter id mapped to the path given for it.

    Raises
    ------
    ValueError
        If a pair has no ``=``, names an unknown adapter, or repeats one. An
        unknown id is almost always a typo, and silently ignoring it would
        validate the root file while the caller believed otherwise.

    Examples
    --------
    >>> {k: v.as_posix() for k, v in
    ...  _parse_sources(["pyproject=backend/pyproject.toml"]).items()}
    {'pyproject': 'backend/pyproject.toml'}

    >>> _parse_sources(["nope=x"])
    Traceback (most recent call last):
        ...
    ValueError: unknown source id 'nope'. Known ids: codemeta, cff, ...

    >>> _parse_sources(["pyproject"])
    Traceback (most recent call last):
        ...
    ValueError: --source expects ID=PATH, but got 'pyproject'.
    """
    known = [adapter.id for adapter in ADAPTERS]
    sources: dict[str, Path] = {}
    for pair in pairs:
        name, separator, raw = pair.partition("=")
        if not separator or not raw.strip():
            raise ValueError(f"--source expects ID=PATH, but got {pair!r}.")
        name = name.strip()
        if name not in known:
            raise ValueError(
                f"unknown source id {name!r}. Known ids: {', '.join(known)}"
            )
        if name in sources:
            raise ValueError(f"--source {name}=... was given more than once.")
        sources[name] = Path(raw.strip())
    return sources


def _wrap(text_value: str, width: int = 78) -> str:
    import textwrap

    return textwrap.fill(" ".join(text_value.split()), width=width)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
