"""Per-adapter behavior: detection, parsing and mapping into CodeMeta."""

from __future__ import annotations

import json

import pytest

from rs_metadata.adapters.package_json import parse_person, repository_url
from rs_metadata.adapters.r_description import (
    parse_authors_r,
    parse_dcf,
    parse_requirements,
)
from rs_metadata.diagnostics import Severity
from tests.conftest import VALID_CFF, codes, codes_for, find


def base(codemeta, **files):
    return {"codemeta.json": codemeta, "CITATION.cff": VALID_CFF, **files}


def source(report, adapter_id):
    return next(item for item in report.sources if item.id == adapter_id)


# ---------------------------------------------------------------------------
# CITATION.cff
# ---------------------------------------------------------------------------


def test_missing_citation_cff_is_an_error(repo, codemeta):
    report = repo({"codemeta.json": codemeta})
    diagnostic = find(report, "source.missing")
    assert diagnostic.severity is Severity.ERROR
    assert "CITATION.cff" in diagnostic.message


def test_unquoted_yaml_version_keeps_its_written_form(repo, codemeta):
    """`version: 1.20` is the float 1.2 in YAML. The written text wins."""
    codemeta["version"] = "1.20"
    document = VALID_CFF.replace('version: "1.0.0"', "version: 1.20")
    report = repo(base(codemeta, **{"CITATION.cff": document}))
    assert "consistency.mismatch" not in codes_for(report, "version")


def test_iso_date_is_not_coerced_to_a_python_date(repo, codemeta):
    codemeta["datePublished"] = "2026-06-01"
    document = VALID_CFF + "date-released: 2026-06-01\n"
    report = repo(base(codemeta, **{"CITATION.cff": document}))
    assert "source.invalid" not in codes(report)
    assert "consistency.mismatch" not in codes_for(report, "datePublished")


def test_wrong_cff_version_is_reported_clearly(repo, codemeta):
    document = VALID_CFF.replace("cff-version: 1.2.0", "cff-version: 1.1.0")
    diagnostic = find(
        repo(base(codemeta, **{"CITATION.cff": document})), "source.invalid"
    )
    assert "1.1.0" in diagnostic.message


def test_cff_schema_violation_is_reported(repo, codemeta):
    document = "cff-version: 1.2.0\ntitle: TestTool\ntype: software\n"
    report = repo(base(codemeta, **{"CITATION.cff": document}))
    assert "source.invalid" in codes(report)


def test_invalid_cff_stops_before_comparison(repo, codemeta):
    """Comparing against a file that fails its own spec reports the wrong problem."""
    document = "cff-version: 1.2.0\ntitle: TestTool\ntype: software\n"
    report = repo(base(codemeta, **{"CITATION.cff": document}))
    assert not any(d.code.startswith("consistency.") for d in report.diagnostics)


def test_dataset_type_is_a_warning(repo, codemeta):
    document = VALID_CFF.replace("type: software", "type: dataset")
    report = repo(base(codemeta, **{"CITATION.cff": document}))
    assert find(report, "source.invalid").severity is Severity.WARNING


def test_malformed_yaml_reports_a_line(repo, codemeta):
    report = repo(base(codemeta, **{"CITATION.cff": "cff-version: 1.2.0\n  bad: [\n"}))
    diagnostic = find(report, "source.unreadable")
    assert diagnostic.location is not None
    assert diagnostic.location.line


# ---------------------------------------------------------------------------
# codemeta.json itself
# ---------------------------------------------------------------------------


def test_malformed_json_reports_a_line(repo, codemeta):
    report = repo({"codemeta.json": '{"name": "X",}', "CITATION.cff": VALID_CFF})
    diagnostic = find(report, "source.unreadable")
    assert diagnostic.location is not None and diagnostic.location.line == 1


def test_missing_codemeta_explains_what_it_is_for(repo):
    report = repo({"CITATION.cff": VALID_CFF})
    diagnostic = find(report, "source.missing")
    assert "anchor" in diagnostic.message
    assert "codemeta.github.io/create" in (diagnostic.suggestion or "")


def test_codemeta_path_override(tmp_path, codemeta):
    from rs_metadata.core import Options, validate

    (tmp_path / "metadata").mkdir()
    (tmp_path / "metadata" / "codemeta.json").write_text(
        json.dumps(codemeta), encoding="utf-8"
    )
    (tmp_path / "CITATION.cff").write_text(VALID_CFF, encoding="utf-8")
    report = validate(
        Options(root=tmp_path, codemeta=tmp_path / "metadata" / "codemeta.json")
    )
    assert source(report, "codemeta").status == "parsed"
    assert report.errors == []


def test_bad_codemeta_override_says_so(tmp_path, codemeta):
    from pathlib import Path

    from rs_metadata.core import Options, validate

    report = validate(Options(root=tmp_path, codemeta=Path("nowhere/codemeta.json")))
    message = find(report, "source.missing").message
    # The path as it was given, not the absolute path it resolved to: shorter,
    # and identical on every platform.
    assert "nowhere/codemeta.json" in message
    assert str(tmp_path) not in message


# ---------------------------------------------------------------------------
# pyproject.toml
# ---------------------------------------------------------------------------

PYPROJECT = """\
[project]
name = "test-tool"
version = "1.0.0"
description = "A short summary that is not the CodeMeta abstract."
license = "Apache-2.0"
authors = [{ name = "Josiah Carberry" }]
dependencies = ["numpy>=1.24"]

[project.urls]
Repository = "https://github.com/lumc-test/testtool"
"""


def test_pyproject_is_auto_detected(repo, codemeta):
    report = repo(base(codemeta, **{"pyproject.toml": PYPROJECT}))
    assert source(report, "pyproject").status == "parsed"
    assert source(report, "pyproject").format_version == "PEP 621"


def test_package_name_matches_display_name(repo, codemeta):
    """`TestTool` in a citation and `test-tool` on PyPI are the same software."""
    report = repo(base(codemeta, **{"pyproject.toml": PYPROJECT}))
    assert "consistency.mismatch" not in codes_for(report, "name")


def test_pep621_summary_is_not_compared_with_the_abstract(repo, codemeta):
    report = repo(base(codemeta, **{"pyproject.toml": PYPROJECT}))
    diagnostic = find(report, "consistency.uncomparable", "description")
    assert "Summary" in diagnostic.message


def test_dynamic_version_is_not_compared(repo, codemeta):
    document = PYPROJECT.replace('version = "1.0.0"', 'dynamic = ["version"]')
    report = repo(base(codemeta, **{"pyproject.toml": document}))
    assert "consistency.mismatch" not in codes_for(report, "version")


def test_pyproject_version_mismatch_is_an_error(repo, codemeta):
    document = PYPROJECT.replace('version = "1.0.0"', 'version = "0.9.0"')
    report = repo(base(codemeta, **{"pyproject.toml": document}))
    assert find(report, "consistency.mismatch", "version").severity is Severity.ERROR


def test_license_file_table_is_not_mapped(repo, codemeta):
    """`{file = "LICENSE"}` names a file, not a license."""
    document = PYPROJECT.replace(
        'license = "Apache-2.0"', 'license = { file = "LICENSE" }'
    )
    report = repo(base(codemeta, **{"pyproject.toml": document}))
    assert "consistency.mismatch" not in codes_for(report, "license")


def test_license_text_table_is_mapped(repo, codemeta):
    document = PYPROJECT.replace('license = "Apache-2.0"', 'license = { text = "MIT" }')
    report = repo(base(codemeta, **{"pyproject.toml": document}))
    assert find(report, "consistency.mismatch", "license")


def test_dependency_presence_difference_is_informational(repo, codemeta):
    """codemeta.json is not obliged to enumerate every dependency."""
    report = repo(base(codemeta, **{"pyproject.toml": PYPROJECT}))
    assert report.errors == []
    assert "consistency.mismatch" not in codes_for(report, "softwareRequirements")


def test_conflicting_dependency_pins_are_a_warning(repo, codemeta):
    codemeta["softwareRequirements"] = [
        {"@type": "SoftwareSourceCode", "name": "numpy", "version": ">=2.0"}
    ]
    report = repo(base(codemeta, **{"pyproject.toml": PYPROJECT}))
    diagnostic = find(report, "consistency.mismatch", "softwareRequirements")
    assert diagnostic.severity is Severity.WARNING
    assert "numpy" in diagnostic.message


def test_legacy_poetry_table_is_understood(repo, codemeta):
    document = """\
[tool.poetry]
name = "test-tool"
version = "9.9.9"
description = "Legacy layout."
authors = ["Josiah Carberry <j@example-lumc.nl>"]
repository = "https://github.com/lumc-test/testtool"

[tool.poetry.dependencies]
python = "^3.10"
numpy = ">=1.24"
"""
    report = repo(base(codemeta, **{"pyproject.toml": document}))
    assert source(report, "pyproject").format_version == "Poetry (legacy)"
    assert find(report, "consistency.mismatch", "version")


def test_pyproject_without_metadata_is_harmless(repo, codemeta):
    document = '[build-system]\nrequires = ["poetry-core"]\n'
    report = repo(base(codemeta, **{"pyproject.toml": document}))
    assert report.errors == []


def test_url_labels_are_matched_case_insensitively(repo, codemeta):
    document = PYPROJECT.replace("Repository =", "source code =")
    report = repo(base(codemeta, **{"pyproject.toml": document}))
    assert "consistency.mismatch" not in codes_for(report, "codeRepository")


def test_malformed_toml_is_reported(repo, codemeta):
    report = repo(base(codemeta, **{"pyproject.toml": "[project\nname = 1"}))
    assert "source.unreadable" in codes(report)
    assert source(report, "pyproject").status == "unparsable"


# ---------------------------------------------------------------------------
# package.json
# ---------------------------------------------------------------------------


def test_package_json_is_auto_detected(repo, codemeta):
    document = {
        "name": "testtool",
        "version": "1.0.0",
        "license": "Apache-2.0",
        "repository": "lumc-test/testtool",
    }
    report = repo(base(codemeta, **{"package.json": document}))
    assert source(report, "package-json").status == "parsed"
    assert "consistency.mismatch" not in codes_for(report, "codeRepository")


@pytest.mark.parametrize(
    "value",
    [
        "lumc-test/testtool",
        "github:lumc-test/testtool",
        "https://github.com/lumc-test/testtool",
        {"type": "git", "url": "git+https://github.com/lumc-test/testtool.git"},
    ],
)
def test_npm_repository_shorthands_all_resolve(repo, codemeta, value):
    document = {"name": "testtool", "version": "1.0.0", "repository": value}
    report = repo(base(codemeta, **{"package.json": document}))
    assert "consistency.mismatch" not in codes_for(report, "codeRepository")


def test_scoped_npm_name_ignores_the_scope(repo, codemeta):
    document = {"name": "@lumc/test-tool", "version": "1.0.0"}
    report = repo(base(codemeta, **{"package.json": document}))
    assert "consistency.mismatch" not in codes_for(report, "name")


def test_npm_author_string_is_parsed():
    person = parse_person("Josiah Carberry <j@example.com> (https://example.com)")
    assert person == {
        "name": "Josiah Carberry",
        "email": "j@example.com",
        "url": "https://example.com",
    }


def test_npm_repository_object_and_string():
    assert repository_url({"url": "https://x/y"}) == "https://x/y"
    assert repository_url("https://x/y") == "https://x/y"
    assert repository_url({}) is None


# ---------------------------------------------------------------------------
# R DESCRIPTION
# ---------------------------------------------------------------------------

DESCRIPTION = """\
Package: testtool
Title: TestTool
Version: 1.0-0
Description: A tool used by the rs-metadata test
    suite, wrapped over two lines.
Authors@R: c(
    person(given = "Josiah", family = "Carberry", role = c("aut", "cre"),
           email = "j@example-lumc.nl",
           comment = c(ORCID = "0000-0002-1825-0097")))
License: Apache License 2.0
URL: https://github.com/lumc-test/testtool
BugReports: https://github.com/lumc-test/testtool/issues
Imports: dplyr (>= 1.0), utils
Depends: R (>= 4.0)
"""


def test_r_description_is_auto_detected(repo, codemeta):
    report = repo(base(codemeta, **{"DESCRIPTION": DESCRIPTION}))
    assert source(report, "r-description").status == "parsed"


def test_r_dash_version_matches_dotted_version(repo, codemeta):
    """R writes 1.0-0 where other ecosystems write 1.0.0."""
    report = repo(base(codemeta, **{"DESCRIPTION": DESCRIPTION}))
    assert "consistency.mismatch" not in codes_for(report, "version")


def test_r_authors_at_r_is_parsed(repo, codemeta):
    report = repo(base(codemeta, **{"DESCRIPTION": DESCRIPTION}))
    assert "consistency.mismatch" not in codes_for(report, "author")


def test_r_license_alias_maps_to_spdx(repo, codemeta):
    report = repo(base(codemeta, **{"DESCRIPTION": DESCRIPTION}))
    assert "consistency.mismatch" not in codes_for(report, "license")


def test_non_r_description_file_is_not_detected(repo, codemeta):
    report = repo(base(codemeta, **{"DESCRIPTION": "Just some prose about a project."}))
    assert source(report, "r-description").status == "absent"


def test_dcf_continuation_lines_are_joined():
    fields = parse_dcf(DESCRIPTION)
    assert "wrapped over two lines" in fields["Description"]
    assert fields["Version"] == "1.0-0"


def test_authors_at_r_keyword_form():
    people = parse_authors_r(
        'person(given = "Jane", family = "Doe", role = "aut", '
        'comment = c(ORCID = "0000-0002-1825-0097"))'
    )
    assert people[0]["givenName"] == "Jane"
    assert people[0]["familyName"] == "Doe"
    assert people[0]["orcid"] == "0000-0002-1825-0097"
    assert people[0]["roles"] == ["aut"]


def test_authors_at_r_positional_form():
    people = parse_authors_r('person("Jane", "Doe", role = c("aut", "cre"))')
    assert people[0]["givenName"] == "Jane"
    assert people[0]["familyName"] == "Doe"
    assert set(people[0]["roles"]) == {"aut", "cre"}


def test_r_requirements_split_name_and_constraint():
    requirements = parse_requirements("dplyr (>= 1.0), utils, R (>= 4.0)")
    assert [r["name"] for r in requirements] == ["dplyr", "utils", "R"]
    assert requirements[0]["version"] == ">= 1.0"
    assert requirements[1]["version"] is None


# ---------------------------------------------------------------------------
# .zenodo.json
# ---------------------------------------------------------------------------


def test_zenodo_title_mismatch_is_an_error(repo, codemeta):
    report = repo(
        base(codemeta, **{".zenodo.json": json.dumps({"title": "Something Else"})})
    )
    assert "consistency.mismatch" in codes_for(report, "name")


def test_zenodo_orcid_is_read_from_the_bare_form(repo, codemeta):
    """Zenodo writes an ORCID bare, CodeMeta as a URI. They are the same person."""
    report = repo(
        base(
            codemeta,
            **{
                ".zenodo.json": json.dumps(
                    {
                        "creators": [
                            {
                                "name": "Carberry, Josiah",
                                "orcid": "0000-0002-1825-0097",
                            }
                        ]
                    }
                )
            },
        )
    )
    assert "consistency.mismatch" not in codes_for(report, "author")


def test_zenodo_non_software_upload_type_is_reported(repo, codemeta):
    report = repo(
        base(codemeta, **{".zenodo.json": json.dumps({"upload_type": "dataset"})})
    )
    diagnostic = find(report, "source.invalid")
    assert diagnostic.severity is Severity.WARNING
    assert "dataset" in diagnostic.message


def test_zenodo_version_does_not_trip_zenodos_own_stale_schema(repo, codemeta):
    """Zenodo's published legacy schema forbids `version`; its API documents it.

    Validating against that schema would report a correct file as invalid, so
    the adapter deliberately does not use it.
    """
    report = repo(
        base(
            codemeta,
            **{".zenodo.json": json.dumps({"version": codemeta["version"]})},
        )
    )
    assert "source.invalid" not in codes(report)


# ---------------------------------------------------------------------------
# biotools.json
# ---------------------------------------------------------------------------


BIOTOOLS = [
    {
        "name": "TestTool",
        "description": "A tool used by the rs-metadata test suite.",
        "homepage": "https://example-lumc.nl/testtool",
        "version": ["1.0.0"],
        "language": ["Python"],
        "license": "Apache-2.0",
        "toolType": ["Command-line tool"],
        "function": [
            {
                "operation": [
                    {
                        "term": "Sequence alignment",
                        "uri": "http://edamontology.org/operation_0292",
                    }
                ]
            }
        ],
        "link": [
            {
                "url": "https://github.com/lumc-test/testtool",
                "type": ["Repository"],
            }
        ],
    }
]


def test_biotools_is_auto_detected_and_schema_validated(repo, codemeta):
    report = repo(base(codemeta, **{"biotools.json": BIOTOOLS}))
    assert source(report, "biotools").status == "parsed"
    assert source(report, "biotools").format_version == "3.3.0"
    assert "source.invalid" not in codes(report)


def test_biotools_schema_violation_stops_comparison(repo, codemeta):
    invalid = [{"name": "TestTool", "description": "Long enough to be valid."}]
    report = repo(base(codemeta, **{"biotools.json": invalid}))
    diagnostic = find(report, "source.invalid")
    assert "homepage" in diagnostic.message
    assert not [
        item
        for item in report.diagnostics
        if item.code.startswith("consistency.")
        and item.source is not None
        and item.source.file == "biotools.json"
    ]


def test_biotools_uses_flattened_language_and_license_fields(repo, codemeta):
    report = repo(base(codemeta, **{"biotools.json": BIOTOOLS}))
    assert "consistency.mismatch" not in codes_for(report, "programmingLanguage")
    assert "consistency.mismatch" not in codes_for(report, "license")


def test_biotools_edam_operations_map_to_feature_list(repo, codemeta):
    report = repo(base(codemeta, **{"biotools.json": BIOTOOLS}))
    assert "consistency.mismatch" not in codes_for(report, "schema:featureList")


def test_biotools_version_list_only_needs_to_contain_current_release(repo, codemeta):
    document = json.loads(json.dumps(BIOTOOLS))
    document[0]["version"] = ["0.9.0", "1.0.0"]
    report = repo(base(codemeta, **{"biotools.json": document}))
    assert "consistency.mismatch" not in codes_for(report, "version")


def test_biotools_requires_the_schema_array_shape(repo, codemeta):
    report = repo(base(codemeta, **{"biotools.json": BIOTOOLS[0]}))
    diagnostic = find(report, "source.unreadable")
    assert "array" in diagnostic.message


# ---------------------------------------------------------------------------
# Cargo.toml
# ---------------------------------------------------------------------------


CARGO = """\
[package]
name = "readaligner"
version = "{version}"
license = "Apache-2.0"
"""


def test_cargo_version_mismatch_is_an_error(repo, codemeta):
    report = repo(base(codemeta, **{"Cargo.toml": CARGO.format(version="9.9.9")}))
    assert "consistency.mismatch" in codes_for(report, "version")


def test_cargo_workspace_inherited_fields_are_not_compared(repo, codemeta):
    """`version.workspace = true` states no value, so there is nothing to compare."""
    manifest = '[package]\nname = "readaligner"\nversion.workspace = true\n'
    report = repo(base(codemeta, **{"Cargo.toml": manifest}))
    assert "consistency.mismatch" not in codes_for(report, "version")


def test_cargo_virtual_manifest_carries_no_metadata(repo, codemeta):
    report = repo(base(codemeta, **{"Cargo.toml": '[workspace]\nmembers = ["a"]\n'}))
    assert not [d for d in report.diagnostics if d.code.startswith("consistency.")]


# ---------------------------------------------------------------------------
# Dockerfile
# ---------------------------------------------------------------------------


def test_dockerfile_oci_label_mismatch_is_reported(repo, codemeta):
    dockerfile = 'FROM python:3.11\nLABEL org.opencontainers.image.version="9.9.9"\n'
    report = repo(base(codemeta, **{"Dockerfile": dockerfile}))
    assert "consistency.mismatch" in codes_for(report, "version")


def test_dockerfile_build_argument_label_is_not_compared(repo, codemeta):
    """`${TAG}` is decided at build time, so this file states no version."""
    dockerfile = 'FROM python:3.11\nLABEL org.opencontainers.image.version="${TAG}"\n'
    report = repo(base(codemeta, **{"Dockerfile": dockerfile}))
    assert "consistency.mismatch" not in codes_for(report, "version")


def test_dockerfile_only_the_final_stage_ships(repo, codemeta):
    dockerfile = (
        "FROM python:3.11 AS build\n"
        'LABEL org.opencontainers.image.version="9.9.9"\n'
        "FROM python:3.11\n"
        'LABEL org.opencontainers.image.version="{version}"\n'
    ).format(version=codemeta["version"])
    report = repo(base(codemeta, **{"Dockerfile": dockerfile}))
    assert "consistency.mismatch" not in codes_for(report, "version")


# ---------------------------------------------------------------------------
# Project.toml (Julia)
# ---------------------------------------------------------------------------


JULIA = """\
name = "ReadAligner"
uuid = "7876af07-990d-54b4-ab0e-23690620f79a"
version = "{version}"
"""


def test_julia_version_mismatch_is_an_error(repo, codemeta):
    report = repo(base(codemeta, **{"Project.toml": JULIA.format(version="9.9.9")}))
    assert "consistency.mismatch" in codes_for(report, "version")


def test_julia_uuid_is_never_compared_against_the_doi(repo, codemeta):
    """Both are `identifier` upstream, but a UUID is not a DOI."""
    report = repo(base(codemeta, **{"Project.toml": JULIA.format(version="1.0.0")}))
    assert "consistency.mismatch" not in codes_for(report, "identifier")


def test_a_non_julia_project_toml_is_not_detected(repo, codemeta):
    """`Project.toml` is a generic name; the uuid/name pair identifies Julia."""
    report = repo(base(codemeta, **{"Project.toml": '[tool.other]\nkey = "value"\n'}))
    assert source(report, "julia-project").status == "absent"


def test_julia_compat_supplies_requirements_and_the_runtime(tmp_path):
    from rs_metadata.adapters.julia_project import JuliaProjectAdapter

    path = tmp_path / "Project.toml"
    path.write_text(
        'name = "X"\nuuid = "u"\n[compat]\njulia = "1.10"\nJSON = "0.21"\n',
        encoding="utf-8",
    )
    adapter = JuliaProjectAdapter()
    concepts = adapter.map_to_codemeta(adapter.parse(path, "Project.toml"))
    assert [value.raw for value in concepts["runtimePlatform"]] == ["Julia 1.10"]
    assert [value.raw for value in concepts["softwareRequirements"]] == [
        {"name": "JSON", "version": "0.21"}
    ]


# ---------------------------------------------------------------------------
# GitHub repository metadata
# ---------------------------------------------------------------------------


def repository(**overrides):
    document = {
        "name": "testtool",
        "full_name": "lumc-test/testtool",
        "html_url": "https://github.com/lumc-test/testtool",
        "fork": False,
    }
    return json.dumps({**document, **overrides})


def test_github_repository_url_mismatch_is_an_error(repo, codemeta):
    payload = repository(html_url="https://github.com/somewhere/else")
    report = repo(base(codemeta, **{"github-repo.json": payload}))
    assert "consistency.mismatch" in codes_for(report, "codeRepository")


def test_github_topics_are_compared_against_keywords(repo, codemeta):
    codemeta["keywords"] = ["genomics"]
    report = repo(
        base(codemeta, **{"github-repo.json": repository(topics=["proteomics"])})
    )
    assert "consistency.mismatch" in codes_for(report, "keywords")


def test_github_undetermined_license_is_not_compared(repo, codemeta):
    """`NOASSERTION` means GitHub's detector recognized nothing, not a conflict."""
    payload = repository(license={"spdx_id": "NOASSERTION", "name": "Other"})
    report = repo(base(codemeta, **{"github-repo.json": payload}))
    assert "consistency.mismatch" not in codes_for(report, "license")


def test_nothing_is_read_from_a_fork(repo, codemeta):
    """A fork's URL and topics are its own; its codemeta.json describes upstream."""
    payload = repository(
        fork=True,
        html_url="https://github.com/forker/testtool",
        topics=["unrelated"],
    )
    report = repo(base(codemeta, **{"github-repo.json": payload}))
    assert not [d for d in report.diagnostics if d.code.startswith("consistency.")]


def test_github_reads_an_actions_event_payload(tmp_path, monkeypatch):
    """Inside Actions the data is already on disk, so no network call is needed."""
    from rs_metadata.adapters.github import GitHubAdapter

    event = tmp_path / "event.json"
    event.write_text(
        json.dumps(
            {
                "action": "opened",
                "repository": {
                    "name": "testtool",
                    "full_name": "lumc-test/testtool",
                    "html_url": "https://github.com/lumc-test/testtool",
                    "topics": ["genomics"],
                    "has_issues": True,
                },
            }
        ),
        encoding="utf-8",
    )
    # Both are set by the runner. The workspace is what says the directory
    # being validated is the repository the payload describes.
    monkeypatch.setenv("GITHUB_EVENT_PATH", str(event))
    monkeypatch.setenv("GITHUB_WORKSPACE", str(tmp_path))
    adapter = GitHubAdapter()
    found = adapter.detect(tmp_path)
    assert found is not None and found == event

    parsed = adapter.parse(found, str(found))
    assert parsed.file == "GitHub repository"
    concepts = adapter.map_to_codemeta(parsed)
    assert [value.raw for value in concepts["issueTracker"]] == [
        "https://github.com/lumc-test/testtool/issues"
    ]


def test_github_is_absent_when_nothing_provides_it(repo, codemeta):
    report = repo(base(codemeta))
    assert source(report, "github").status == "absent"


def test_the_actions_payload_is_ignored_outside_the_workspace(tmp_path, monkeypatch):
    """A subdirectory is not the repository, so the repository's metadata is not its.

    The runner sets GITHUB_EVENT_PATH for every step whatever it looks at. The
    action's own `working-directory: examples/complete` used to compare that
    example against this repository, reporting a difference on every field of
    metadata that was entirely correct.
    """
    from rs_metadata.adapters.github import GitHubAdapter

    event = tmp_path / "event.json"
    event.write_text(
        json.dumps({"repository": {"full_name": "o/r", "name": "r"}}), encoding="utf-8"
    )
    workspace = tmp_path / "workspace"
    subdirectory = workspace / "examples" / "complete"
    subdirectory.mkdir(parents=True)

    monkeypatch.setenv("GITHUB_EVENT_PATH", str(event))
    monkeypatch.setenv("GITHUB_WORKSPACE", str(workspace))
    adapter = GitHubAdapter()

    assert adapter.detect(subdirectory) is None
    assert adapter.detect(workspace) == event


def test_a_unix_timestamp_is_reported_as_a_date(tmp_path):
    """A webhook payload writes `created_at` as an integer, unlike the API.

    Reported raw it showed a reader `1786665985`, which looks like corrupt
    metadata rather than a date.
    """
    from rs_metadata.adapters.github import GitHubAdapter

    path = tmp_path / "github-repo.json"
    path.write_text(
        json.dumps(
            {
                "full_name": "o/r",
                "name": "r",
                "created_at": 1786665985,
                "updated_at": "2026-08-14T00:06:33Z",
            }
        ),
        encoding="utf-8",
    )
    adapter = GitHubAdapter()
    concepts = adapter.map_to_codemeta(adapter.parse(path, "github-repo.json"))
    assert [v.raw for v in concepts["dateCreated"]] == ["2026-08-14T00:06:25Z"]
    assert [v.raw for v in concepts["dateModified"]] == ["2026-08-14T00:06:33Z"]


# ---------------------------------------------------------------------------
# Robustness
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "field,value",
    [("contributors", 42), ("licenses", 42), ("keywords", True)],
)
def test_a_wrongly_typed_package_json_field_does_not_crash(
    repo, codemeta, field, value
):
    """A number where a list belongs used to raise straight through the CLI."""
    payload = json.dumps({"name": "x", "version": "1.0.0", field: value})
    report = repo(base(codemeta, **{"package.json": payload}))
    assert "internal.error" not in codes(report)


def test_an_adapter_crash_does_not_lose_the_rest_of_the_run(
    repo, codemeta, monkeypatch
):
    """One adapter's bug is reported, not raised. Every other source still runs."""
    from rs_metadata.adapters.cargo import CargoAdapter

    def explode(self, parsed):
        raise RuntimeError("simulated adapter bug")

    monkeypatch.setattr(CargoAdapter, "map_to_codemeta", explode)
    report = repo(base(codemeta, **{"Cargo.toml": '[package]\nname = "x"\n'}))

    internal = find(report, "internal.error")
    assert "simulated adapter bug" in internal.message
    assert internal.severity is Severity.ERROR
    # The anchor was still validated and CITATION.cff was still compared.
    assert {source.id for source in report.sources} >= {"codemeta", "cff", "cargo"}
    assert report.checks > 0


# ---------------------------------------------------------------------------
# Concepts beyond the profile
# ---------------------------------------------------------------------------


def test_npm_dev_dependencies_are_suggestions_not_requirements(tmp_path):
    """`devDependencies` is what a package can use, not what it needs to run."""
    from rs_metadata.adapters.package_json import PackageJsonAdapter

    path = tmp_path / "package.json"
    path.write_text(
        json.dumps(
            {
                "name": "x",
                "dependencies": {"lodash": "^4"},
                "devDependencies": {"jest": "^29"},
                "cpu": ["x64"],
            }
        ),
        encoding="utf-8",
    )
    adapter = PackageJsonAdapter()
    concepts = adapter.map_to_codemeta(adapter.parse(path, "package.json"))
    assert [v.raw["name"] for v in concepts["softwareRequirements"]] == ["lodash"]
    assert [v.raw["name"] for v in concepts["softwareSuggestions"]] == ["jest"]
    assert [v.raw for v in concepts["processorRequirements"]] == ["x64"]


def test_r_suggests_and_contributors_are_read(tmp_path):
    from rs_metadata.adapters.r_description import RDescriptionAdapter

    path = tmp_path / "DESCRIPTION"
    path.write_text(
        "Package: x\n"
        "Version: 1.0\n"
        'Authors@R: c(person(given = "A", family = "B", role = "aut"),\n'
        '             person(given = "C", family = "D", role = "ctb"))\n'
        "Suggests: testthat (>= 3.0)\n"
    )
    adapter = RDescriptionAdapter()
    concepts = adapter.map_to_codemeta(adapter.parse(path, "DESCRIPTION"))
    assert [v.raw["name"] for v in concepts["softwareSuggestions"]] == ["testthat"]
    assert len(concepts["contributor"]) == 1
    assert len(concepts["author"]) == 1


def test_github_timestamps_compare_on_the_calendar_day(repo, codemeta):
    """A stamped-to-the-second `created_at` must not differ from a plain date."""
    codemeta["dateCreated"] = "2026-01-15"
    payload = json.dumps(
        {
            "name": "testtool",
            "full_name": "lumc-test/testtool",
            "html_url": "https://github.com/lumc-test/testtool",
            "fork": False,
            "created_at": "2026-01-15T10:00:00Z",
        }
    )
    report = repo(base(codemeta, **{"github-repo.json": payload}))
    assert "consistency.mismatch" not in codes_for(report, "dateCreated")


def test_a_concept_beyond_the_profile_never_fails_a_build(repo, codemeta):
    """The profile has no opinion on these, so a difference is never an error."""
    codemeta["dateCreated"] = "2020-01-01"
    payload = json.dumps(
        {
            "name": "testtool",
            "full_name": "lumc-test/testtool",
            "html_url": "https://github.com/lumc-test/testtool",
            "fork": False,
            "created_at": "2026-01-15T10:00:00Z",
        }
    )
    report = repo(base(codemeta, **{"github-repo.json": payload}))
    beyond = [d for d in report.diagnostics if d.property == "dateCreated"]
    assert beyond and all(d.severity is Severity.INFO for d in beyond)
