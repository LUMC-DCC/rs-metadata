"""The CLI and the renderers.

Both are meant to be thin. These tests assert that they carry the report
faithfully and choose the right exit status, not that they contain logic of
their own.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from rs_metadata.cli import EXIT_FINDINGS, EXIT_OK, EXIT_USAGE, main
from rs_metadata.core import Options, validate
from rs_metadata.diagnostics import Severity
from rs_metadata.renderers import github, text
from tests.conftest import EXAMPLES, VALID_CFF, write_repo


@pytest.fixture
def valid_repo(tmp_path, codemeta):
    write_repo(tmp_path, {"codemeta.json": codemeta, "CITATION.cff": VALID_CFF})
    return tmp_path


@pytest.fixture
def broken_repo(tmp_path, codemeta):
    codemeta["version"] = "9.9.9"
    write_repo(tmp_path, {"codemeta.json": codemeta, "CITATION.cff": VALID_CFF})
    return tmp_path


# ---------------------------------------------------------------------------
# Exit codes
# ---------------------------------------------------------------------------


def test_valid_repository_exits_zero(valid_repo, capsys):
    assert main(["validate", str(valid_repo)]) == EXIT_OK


def test_errors_exit_nonzero(broken_repo, capsys):
    assert main(["validate", str(broken_repo)]) == EXIT_FINDINGS


def test_strict_promotes_warnings_to_failures(valid_repo, capsys):
    assert main(["validate", str(valid_repo)]) == EXIT_OK
    assert main(["validate", str(valid_repo), "--strict"]) == EXIT_FINDINGS


def test_fail_on_never_always_succeeds(broken_repo, capsys):
    assert main(["validate", str(broken_repo), "--fail-on", "never"]) == EXIT_OK


def test_missing_directory_is_a_usage_error(tmp_path, capsys):
    assert main(["validate", str(tmp_path / "nope")]) == EXIT_USAGE


def test_no_subcommand_prints_help(capsys):
    assert main([]) == EXIT_USAGE
    assert "rs-metadata" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# Output formats
# ---------------------------------------------------------------------------


def test_json_output_is_parsable_and_complete(broken_repo, capsys):
    main(["validate", str(broken_repo), "--format", "json"])
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "failed"
    assert payload["tool"]["version"]
    assert payload["tool"]["name"] == "rs-metadata"
    assert payload["profile"]["codemetaVersion"] == "3.1"
    assert payload["summary"]["error"] >= 1
    assert any(d["code"] == "consistency.mismatch" for d in payload["diagnostics"])


def test_every_diagnostic_carries_a_documentation_link(broken_repo, capsys):
    main(["validate", str(broken_repo), "--format", "json"])
    payload = json.loads(capsys.readouterr().out)
    for diagnostic in payload["diagnostics"]:
        assert diagnostic["docs"].startswith("https://")


def test_report_file_is_written(broken_repo, tmp_path, capsys):
    target = tmp_path / "out" / "report.json"
    main(["validate", str(broken_repo), "--report", str(target)])
    assert json.loads(target.read_text(encoding="utf-8"))["status"] == "failed"


def test_text_output_names_file_property_and_fix(broken_repo, capsys):
    main(["validate", str(broken_repo), "--color", "never"])
    output = capsys.readouterr().out
    assert "consistency.mismatch" in output
    assert "codemeta.json" in output and "CITATION.cff" in output
    assert "Suggested fix:" in output
    assert "9.9.9" in output and "1.0.0" in output


def test_info_findings_are_hidden_unless_verbose(tmp_path, codemeta, capsys):
    # Drop the affiliation's ROR so the run produces an informational finding.
    del codemeta["author"][0]["affiliation"]["@id"]
    write_repo(tmp_path, {"codemeta.json": codemeta, "CITATION.cff": VALID_CFF})

    main(["validate", str(tmp_path), "--color", "never"])
    quiet = capsys.readouterr().out
    main(["validate", str(tmp_path), "--color", "never", "--verbose"])
    verbose = capsys.readouterr().out

    assert "hidden" in quiet
    assert "recommendation.incomplete" not in quiet
    assert "recommendation.incomplete" in verbose
    assert len(verbose) > len(quiet)


def test_color_can_be_forced_and_suppressed(broken_repo, capsys):
    main(["validate", str(broken_repo), "--color", "always"])
    assert "\033[" in capsys.readouterr().out
    main(["validate", str(broken_repo), "--color", "never"])
    assert "\033[" not in capsys.readouterr().out


def test_no_color_environment_variable_is_honored(broken_repo, monkeypatch, capsys):
    monkeypatch.setenv("NO_COLOR", "1")
    main(["validate", str(broken_repo)])
    assert "\033[" not in capsys.readouterr().out


# ---------------------------------------------------------------------------
# GitHub renderer
# ---------------------------------------------------------------------------


def test_github_annotations_point_at_the_offending_line(broken_repo, capsys):
    main(["validate", str(broken_repo), "--format", "github", "--color", "never"])
    output = capsys.readouterr().out
    assert "::error " in output
    assert "file=codemeta.json" in output
    assert "line=" in output


def test_annotation_escapes_newlines_and_percent_signs():
    from rs_metadata.report import Diagnostic, Location

    rendered = github.annotation(
        Diagnostic(
            code="internal.error",
            severity=Severity.ERROR,
            message="100% broken\nsecond line",
            location=Location(file="a,b.json", line=3),
        )
    )
    assert "%25" in rendered and "%0A" in rendered
    assert "file=a%2Cb.json" in rendered
    assert "\n" not in rendered


def test_github_outputs_and_summary_are_written(
    broken_repo, tmp_path, monkeypatch, capsys
):
    outputs = tmp_path / "outputs.txt"
    step_summary = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_OUTPUT", str(outputs))
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(step_summary))
    main(["validate", str(broken_repo), "--format", "github", "--color", "never"])

    written = dict(
        line.split("=", 1)
        for line in outputs.read_text(encoding="utf-8").strip().splitlines()
    )
    assert written["status"] == "failed"
    assert int(written["errors"]) >= 1

    summary = step_summary.read_text(encoding="utf-8")
    assert "## rs-metadata" in summary
    assert "codemeta.json" in summary


def test_summary_lists_absent_sources(valid_repo, tmp_path, monkeypatch, capsys):
    step_summary = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(step_summary))
    main(["validate", str(valid_repo), "--format", "github", "--color", "never"])
    assert "_not present_" in step_summary.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# explain
# ---------------------------------------------------------------------------


def test_explain_describes_a_code(capsys):
    assert main(["explain", "consistency.mismatch"]) == EXIT_OK
    output = capsys.readouterr().out
    assert "consistency.mismatch" in output
    assert "How to resolve it" in output
    assert "https://" in output


def test_explain_without_an_argument_lists_every_code(capsys):
    assert main(["explain"]) == EXIT_OK
    output = capsys.readouterr().out
    assert "profile.required-field" in output
    assert "consistency.uncomparable" in output


def test_explain_rejects_an_unknown_code(capsys):
    assert main(["explain", "made.up"]) == EXIT_USAGE
    assert "unknown diagnostic code" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# Reproducibility
# ---------------------------------------------------------------------------


def test_source_date_epoch_makes_reports_byte_identical(valid_repo, monkeypatch):
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "1780000000")
    first = validate(Options(root=valid_repo)).to_dict()
    second = validate(Options(root=valid_repo)).to_dict()
    assert json.dumps(first) == json.dumps(second)
    assert first["generatedAt"].endswith("Z")


# ---------------------------------------------------------------------------
# Examples
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", ["minimal", "complete"])
def test_shipped_examples_are_valid(name):
    """The examples are documentation; a broken one must break the build."""
    report = validate(Options(root=EXAMPLES / name))
    assert report.errors == [], "\n".join(d.message for d in report.errors)


def test_complete_example_exercises_three_sources():
    report = validate(Options(root=EXAMPLES / "complete"))
    parsed = {source.id for source in report.sources if source.status == "parsed"}
    assert parsed == {"codemeta", "cff", "pyproject"}
    assert report.checks > 20


def test_invalid_example_produces_the_documented_diagnostics():
    """Keeps examples/invalid/README.md honest."""
    report = validate(Options(root=EXAMPLES / "invalid"))
    assert report.status == "failed"
    found = {(d.code, d.property) for d in report.diagnostics}
    expected = {
        ("profile.required-field", "applicationCategory"),
        ("profile.required-field", "programmingLanguage"),
        ("profile.unknown-property", "programingLanguage"),
        ("profile.unprefixed-term", "schema:featureList"),
        ("profile.invalid-value", "schema:featureList"),
        ("profile.non-canonical-value", "schema:featureList"),
        ("profile.placeholder-value", "identifier"),
        ("profile.placeholder-value", "author"),
        ("profile.placeholder-value", "codeRepository"),
        ("profile.invalid-type", "license"),
        ("profile.invalid-value", "developmentStatus"),
        ("consistency.mismatch", "version"),
        ("consistency.mismatch", "author"),
        ("consistency.mismatch", "license"),
        ("consistency.mismatch", "codeRepository"),
    }
    assert expected <= found, expected - found


def test_text_renderer_handles_an_empty_report(tmp_path, capsys):
    from rs_metadata.report import Report

    text.render(Report(), color="never")
    assert "no findings" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# --source ID=PATH
# ---------------------------------------------------------------------------


def test_source_override_finds_a_nested_file(tmp_path):
    """A monorepo keeps packaging metadata away from the anchor record."""
    (tmp_path / "backend").mkdir()
    shutil.copy(EXAMPLES / "complete" / "codemeta.json", tmp_path / "codemeta.json")
    shutil.copy(EXAMPLES / "complete" / "CITATION.cff", tmp_path / "CITATION.cff")
    (tmp_path / "backend" / "pyproject.toml").write_text(
        '[project]\nname = "example-complete"\nversion = "9.9.9"\n'
        'description = "Deliberately disagrees."\n',
        encoding="utf-8",
    )

    without = main(["validate", str(tmp_path), "--color", "never"])
    assert without == 0, "the nested file should be invisible without --source"

    with_override = main(
        [
            "validate",
            str(tmp_path),
            "--source",
            "pyproject=backend/pyproject.toml",
            "--color",
            "never",
        ]
    )
    assert with_override == 1, "the nested file's version conflict should be found"


def test_source_override_rejects_an_unknown_id(tmp_path, capsys):
    assert main(["validate", str(tmp_path), "--source", "nope=x"]) == 2
    assert "unknown source id" in capsys.readouterr().err


def test_source_override_rejects_a_malformed_pair(tmp_path, capsys):
    assert main(["validate", str(tmp_path), "--source", "pyproject"]) == 2
    assert "expects ID=PATH" in capsys.readouterr().err


def test_a_named_source_that_is_absent_is_an_error(tmp_path):
    """An explicit path asserts the file is there; silence would hide a typo."""
    shutil.copy(EXAMPLES / "complete" / "codemeta.json", tmp_path / "codemeta.json")
    shutil.copy(EXAMPLES / "complete" / "CITATION.cff", tmp_path / "CITATION.cff")
    report = validate(
        Options(root=tmp_path, sources={"pyproject": Path("nowhere/pyproject.toml")})
    )
    assert "source.missing" in {d.code for d in report.errors}


def test_codemeta_flag_is_an_alias_for_the_general_form(tmp_path):
    by_alias = Options(root=tmp_path, codemeta=Path("meta/codemeta.json"))
    by_source = Options(root=tmp_path, sources={"codemeta": Path("meta/codemeta.json")})
    assert by_alias.path_for("codemeta") == by_source.path_for("codemeta")


def test_a_name_the_console_cannot_encode_does_not_kill_the_run(
    broken_repo, tmp_path, monkeypatch, capsys
):
    """Metadata is arbitrary Unicode; a console's encoding is not.

    A Windows code page and a Polish author name used to end the run with a
    UnicodeEncodeError and no report at all. Names outside Latin-1 are
    ordinary in research software, so this has to survive.
    """
    import io
    import sys

    codemeta = json.loads((broken_repo / "codemeta.json").read_text(encoding="utf-8"))
    codemeta["author"] = [
        {"@type": "Person", "givenName": "Łukasz", "familyName": "Wróblewski"}
    ]
    (broken_repo / "codemeta.json").write_text(
        json.dumps(codemeta, ensure_ascii=False), encoding="utf-8"
    )

    narrow = io.TextIOWrapper(io.BytesIO(), encoding="cp1252", errors="strict")
    monkeypatch.setattr(sys, "stdout", narrow)
    exit_code = main(
        ["validate", str(broken_repo), "--format", "github", "--color", "never"]
    )
    narrow.flush()

    assert exit_code != 0  # it still reported, rather than crashing
    written = narrow.buffer.getvalue().decode("cp1252")
    assert "Wr" in written  # the finding came through, however the name rendered


def test_the_reported_paths_are_posix_on_every_platform(tmp_path):
    """A report generated on Windows must read the same as one from Linux.

    File paths travel into CI annotations and into the JSON report, both of
    which are compared and linked across machines, so a backslash there is
    wrong everywhere.
    """
    from rs_metadata.scaffold import plan, write

    written = write(tmp_path, plan(tmp_path))
    assert all("\\" not in path for path in written), written
    assert ".github/workflows/metadata.yml" in written
