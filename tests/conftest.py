"""Shared test fixtures.

Most tests build a throwaway repository from a dictionary of files and run the
real pipeline over it. Going through :func:`rs_metadata.core.validate` rather
than calling internals keeps the tests honest about what a user would actually
see, and means a refactor that breaks the wiring fails the suite.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from rs_metadata.core import Options, validate
from rs_metadata.report import Report

REPO_ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = REPO_ROOT / "examples"

#: A codemeta.json that satisfies the profile with nothing to spare. Tests
#: start from this and break exactly one thing, so a failure names its cause.
VALID_CODEMETA: dict[str, Any] = {
    "@context": ["https://w3id.org/codemeta/3.1", {"schema": "https://schema.org/"}],
    "@type": "SoftwareSourceCode",
    "name": "TestTool",
    "description": "A tool used by the rs-metadata test suite.",
    "version": "1.0.0",
    "identifier": "https://doi.org/10.5281/zenodo.1234567",
    "author": [
        {
            "@type": "Person",
            "@id": "https://orcid.org/0000-0002-1825-0097",
            "givenName": "Josiah",
            "familyName": "Carberry",
            "affiliation": {
                "@type": "Organization",
                "@id": "https://ror.org/05xvt9f17",
                "name": "Leiden University Medical Center",
            },
        }
    ],
    "license": "https://spdx.org/licenses/Apache-2.0",
    "codeRepository": "https://github.com/lumc-test/testtool",
    "programmingLanguage": ["Python"],
    "applicationCategory": "Command-line tool",
    "schema:featureList": ["http://edamontology.org/operation_0292"],
}

VALID_CFF = """\
cff-version: 1.2.0
title: TestTool
message: "If you use this software, please cite it."
type: software
authors:
  - family-names: Carberry
    given-names: Josiah
    orcid: https://orcid.org/0000-0002-1825-0097
version: "1.0.0"
doi: 10.5281/zenodo.1234567
repository-code: https://github.com/lumc-test/testtool
license: Apache-2.0
"""


def write_repo(root: Path, files: dict[str, Any]) -> Path:
    """Materialise a repository. Mappings are written as JSON, strings as text."""
    for name, content in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, (dict, list)):
            path.write_text(json.dumps(content, indent=2), encoding="utf-8")
        else:
            path.write_text(str(content), encoding="utf-8")
    return root


@pytest.fixture
def repo(tmp_path: Path):
    """Build a repository and validate it in one step."""

    def build(files: dict[str, Any], **options: Any) -> Report:
        write_repo(tmp_path, files)
        return validate(Options(root=tmp_path, **options))

    return build


@pytest.fixture
def codemeta() -> dict[str, Any]:
    """A fresh, valid anchor record that a test may mutate freely."""
    copied: dict[str, Any] = json.loads(json.dumps(VALID_CODEMETA))
    return copied


def codes(report: Report) -> set[str]:
    return {diagnostic.code for diagnostic in report.diagnostics}


def codes_for(report: Report, prop: str) -> set[str]:
    return {
        diagnostic.code
        for diagnostic in report.diagnostics
        if diagnostic.property == prop
    }


def profile_errors(report: Report) -> list[str]:
    """Errors raised by the profile alone, ignoring cross-file consistency.

    Lets a test change one value in codemeta.json without also having to keep
    every companion file in step just to isolate a profile rule.
    """
    return [
        diagnostic.message
        for diagnostic in report.errors
        if not diagnostic.code.startswith("consistency.")
    ]


def messages(report: Report) -> str:
    return "\n".join(diagnostic.message for diagnostic in report.diagnostics)


def find(report: Report, code: str, prop: str | None = None):
    """The first diagnostic with a code, optionally narrowed to one property."""
    for diagnostic in report.diagnostics:
        if diagnostic.code == code and (prop is None or diagnostic.property == prop):
            return diagnostic
    raise AssertionError(
        f"No {code} diagnostic"
        f"{f' for {prop}' if prop else ''} in report. Found:\n"
        + "\n".join(
            f"  {d.severity.value:<8} {d.code} ({d.property}): {d.message}"
            for d in report.diagnostics
        )
    )


@pytest.fixture(autouse=True)
def _hermetic_environment(monkeypatch):
    """Keep the runner's own environment out of every test.

    GitHub Actions sets `GITHUB_EVENT_PATH` and `GITHUB_WORKSPACE` for every
    step, and the GitHub adapter reads them. Without this the suite passes
    locally and fails in CI, which is exactly what happened: thirty-nine tests
    started comparing their fixtures against whatever repository the workflow
    was running in. A test that wants those variables sets them itself.
    """
    for name in ("GITHUB_EVENT_PATH", "GITHUB_WORKSPACE"):
        monkeypatch.delenv(name, raising=False)
