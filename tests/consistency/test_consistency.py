"""Cross-format consistency: what must agree, and what is allowed to differ.

The second half matters as much as the first. A validator that reports a
mismatch every time a package name is written `my-tool` on PyPI and `MyTool`
in a citation gets switched off, and then it catches nothing at all.
"""

from __future__ import annotations

import pytest

from rs_metadata.diagnostics import Severity
from tests.conftest import VALID_CFF, codes, codes_for, find


def cff(**overrides: str) -> str:
    """Build a CITATION.cff from the valid template with fields replaced."""
    lines = VALID_CFF.splitlines()
    for key, value in overrides.items():
        field = key.replace("_", "-")
        lines = [
            f"{field}: {value}" if line.startswith(f"{field}:") else line
            for line in lines
        ]
    return "\n".join(lines) + "\n"


def base(codemeta, **files):
    return {"codemeta.json": codemeta, "CITATION.cff": VALID_CFF, **files}


# ---------------------------------------------------------------------------
# Equivalent representations must not be reported
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("anchor", "companion"),
    [
        pytest.param(
            "https://spdx.org/licenses/Apache-2.0", "Apache-2.0", id="spdx-url-vs-id"
        ),
        pytest.param(
            "https://spdx.org/licenses/Apache-2.0",
            "apache-2.0",
            id="spdx-case-insensitive",
        ),
    ],
)
def test_equivalent_licenses_match(repo, codemeta, anchor, companion):
    codemeta["license"] = anchor
    report = repo(base(codemeta, **{"CITATION.cff": cff(license=companion)}))
    assert "consistency.mismatch" not in codes_for(report, "license")


@pytest.mark.parametrize(
    ("anchor", "companion"),
    [
        pytest.param("10.5281/zenodo.1234567", "10.5281/zenodo.1234567", id="bare"),
        pytest.param(
            "https://doi.org/10.5281/zenodo.1234567",
            "10.5281/zenodo.1234567",
            id="resolver-url-vs-bare",
        ),
        pytest.param(
            "https://dx.doi.org/10.5281/zenodo.1234567",
            "10.5281/ZENODO.1234567",
            id="dx-resolver-and-case",
        ),
        pytest.param(
            "doi:10.5281/zenodo.1234567", "10.5281/zenodo.1234567", id="doi-scheme"
        ),
    ],
)
def test_equivalent_dois_match(repo, codemeta, anchor, companion):
    codemeta["identifier"] = anchor
    report = repo(base(codemeta, **{"CITATION.cff": cff(doi=companion)}))
    assert "consistency.mismatch" not in codes_for(report, "identifier")


@pytest.mark.parametrize(
    ("anchor", "companion"),
    [
        pytest.param("1.0.0", '"1.0.0"', id="identical"),
        pytest.param("1.0.0", '"v1.0.0"', id="v-prefix"),
        pytest.param("1.0", '"1.0.0"', id="trailing-zero"),
    ],
)
def test_equivalent_versions_match(repo, codemeta, anchor, companion):
    codemeta["version"] = anchor
    report = repo(base(codemeta, **{"CITATION.cff": cff(version=companion)}))
    assert "consistency.mismatch" not in codes_for(report, "version")


@pytest.mark.parametrize(
    "companion",
    [
        "https://github.com/lumc-test/testtool",
        "http://github.com/lumc-test/testtool",
        "https://github.com/lumc-test/testtool/",
        "https://github.com/lumc-test/testtool.git",
        "https://www.github.com/lumc-test/testtool",
        "git+https://github.com/lumc-test/testtool.git",
    ],
)
def test_equivalent_repository_urls_match(repo, codemeta, companion):
    report = repo(base(codemeta, **{"CITATION.cff": cff(repository_code=companion)}))
    assert "consistency.mismatch" not in codes_for(report, "codeRepository")


def test_initials_match_full_given_names(repo, codemeta):
    """`J. Carberry` in one file and `Josiah Carberry` in the other is one person."""
    authors = "authors:\n  - family-names: Carberry\n    given-names: J.\n"
    document = VALID_CFF.replace(
        "authors:\n"
        "  - family-names: Carberry\n"
        "    given-names: Josiah\n"
        "    orcid: https://orcid.org/0000-0002-1825-0097\n",
        authors,
    )
    report = repo(base(codemeta, **{"CITATION.cff": document}))
    assert "consistency.mismatch" not in codes_for(report, "author")


def test_orcid_matches_across_differing_names(repo, codemeta):
    """A married or transliterated name still matches when the ORCID agrees."""
    document = VALID_CFF.replace("family-names: Carberry", "family-names: Karberri")
    report = repo(base(codemeta, **{"CITATION.cff": document}))
    assert "consistency.mismatch" not in codes_for(report, "author")


def test_unordered_collections_do_not_depend_on_order(repo, codemeta):
    codemeta["keywords"] = ["genomics", "alignment"]
    document = VALID_CFF + "keywords:\n  - alignment\n  - genomics\n"
    report = repo(base(codemeta, **{"CITATION.cff": document}))
    assert "consistency.mismatch" not in codes_for(report, "keywords")


# ---------------------------------------------------------------------------
# Genuine disagreements must be reported
# ---------------------------------------------------------------------------


def test_version_mismatch_is_an_error(repo, codemeta):
    codemeta["version"] = "2.0.0"
    report = repo(base(codemeta, **{"CITATION.cff": cff(version='"1.0.0"')}))
    diagnostic = find(report, "consistency.mismatch", "version")
    assert diagnostic.severity is Severity.ERROR
    assert diagnostic.anchor is not None and diagnostic.anchor.file == "codemeta.json"
    assert diagnostic.source is not None and diagnostic.source.file == "CITATION.cff"
    assert diagnostic.anchor.value == "2.0.0"
    assert diagnostic.source.value == "1.0.0"
    assert diagnostic.strategy == "version"
    assert diagnostic.rule == "equal"


def test_mismatch_carries_mapping_provenance(repo, codemeta):
    codemeta["version"] = "2.0.0"
    report = repo(base(codemeta, **{"CITATION.cff": cff(version='"1.0.0"')}))
    mapping = find(report, "consistency.mismatch", "version").mapping
    assert mapping is not None
    assert mapping.id == "cff-1.2.0"
    assert mapping.origin == "codemeta-upstream"
    assert "codemeta" in (mapping.source or "")


def test_license_mismatch_is_an_error(repo, codemeta):
    report = repo(base(codemeta, **{"CITATION.cff": cff(license="MIT")}))
    assert find(report, "consistency.mismatch", "license")


def test_different_repositories_are_an_error(repo, codemeta):
    report = repo(
        base(
            codemeta,
            **{"CITATION.cff": cff(repository_code="https://github.com/other/tool")},
        )
    )
    assert find(report, "consistency.mismatch", "codeRepository")


def test_different_authors_are_an_error(repo, codemeta):
    document = VALID_CFF.replace(
        "family-names: Carberry", "family-names: Smith"
    ).replace("    orcid: https://orcid.org/0000-0002-1825-0097\n", "")
    report = repo(base(codemeta, **{"CITATION.cff": document}))
    assert find(report, "consistency.mismatch", "author")


def test_differing_orcids_are_different_people(repo, codemeta):
    """Same name, different ORCID: the ORCID wins in both directions."""
    document = VALID_CFF.replace("0000-0002-1825-0097", "0000-0001-5109-3700")
    report = repo(base(codemeta, **{"CITATION.cff": document}))
    assert find(report, "consistency.mismatch", "author")


def test_prose_divergence_is_only_a_warning(repo, codemeta):
    document = VALID_CFF + "abstract: Something else entirely.\n"
    report = repo(base(codemeta, **{"CITATION.cff": document}))
    diagnostic = find(report, "consistency.mismatch", "description")
    assert diagnostic.severity is Severity.WARNING


def test_completely_disjoint_keywords_are_a_warning(repo, codemeta):
    codemeta["keywords"] = ["genomics", "alignment"]
    document = VALID_CFF + "keywords:\n  - astronomy\n  - telescopes\n"
    report = repo(base(codemeta, **{"CITATION.cff": document}))
    diagnostic = find(report, "consistency.mismatch", "keywords")
    assert diagnostic.severity is Severity.WARNING
    assert diagnostic.rule == "overlap"


def test_partially_overlapping_keywords_pass(repo, codemeta):
    codemeta["keywords"] = ["genomics", "alignment", "clinical"]
    document = VALID_CFF + "keywords:\n  - genomics\n  - sequencing\n"
    report = repo(base(codemeta, **{"CITATION.cff": document}))
    assert "consistency.mismatch" not in codes_for(report, "keywords")


def test_cff_identifier_absent_from_anchor_is_an_error(repo, codemeta):
    """CFF may claim fewer identifiers than the anchor, but never different ones."""
    document = VALID_CFF + (
        "identifiers:\n  - type: url\n    value: https://bio.tools/testtool\n"
    )
    report = repo(base(codemeta, **{"CITATION.cff": document}))
    diagnostic = find(report, "consistency.mismatch", "identifier")
    assert diagnostic.rule == "subset"


def test_anchor_may_hold_more_identifiers_than_cff(repo, codemeta):
    codemeta["identifier"] = [
        "https://doi.org/10.5281/zenodo.1234567",
        "https://bio.tools/testtool",
    ]
    report = repo(base(codemeta))
    assert "consistency.mismatch" not in codes_for(report, "identifier")


# ---------------------------------------------------------------------------
# Not comparable
# ---------------------------------------------------------------------------


def test_cff_references_are_declared_not_comparable(repo, codemeta):
    document = VALID_CFF + (
        "references:\n"
        "  - type: article\n"
        "    title: Some paper\n"
        "    authors:\n"
        "      - family-names: Carberry\n"
        "        given-names: Josiah\n"
    )
    report = repo(base(codemeta, **{"CITATION.cff": document}))
    diagnostic = find(report, "consistency.uncomparable", "softwareRequirements")
    assert "bibliography" in diagnostic.message


def test_missing_optional_sources_are_not_findings(repo, codemeta):
    report = repo(base(codemeta))
    absent = {source.id for source in report.sources if source.status == "absent"}
    assert {"pyproject", "package-json", "r-description"} <= absent
    assert "source.missing" not in codes(report)


def test_absent_sources_are_still_recorded(repo, codemeta):
    """The report says what was looked for, not only what was found."""
    from rs_metadata.adapters import ADAPTERS

    report = repo(base(codemeta))
    identifiers = {source.id for source in report.sources}
    # Derived from the registry rather than listed: a newly registered adapter
    # that forgot to report itself should fail here, not require an edit here.
    assert identifiers == {adapter.id for adapter in ADAPTERS}


def test_equivalent_version_constraints_are_not_a_conflict(repo, codemeta):
    # >=1.24 and >=1.24.0 admit exactly the same releases. Reporting them as a
    # conflict is a false alarm, and a validator that cries wolf gets ignored.
    codemeta["softwareRequirements"] = [
        {"@type": "SoftwareSourceCode", "name": "numpy", "version": ">=1.24"}
    ]
    report = repo(
        {
            **base(codemeta),
            "pyproject.toml": (
                "[project]\n"
                'name = "testtool"\n'
                'version = "1.0.0"\n'
                'description = "A tool used by the rs-metadata test suite."\n'
                'dependencies = ["numpy >= 1.24.0"]\n'
            ),
        }
    )
    assert "consistency.mismatch" not in codes_for(report, "softwareRequirements")


def test_genuinely_incompatible_constraints_are_still_reported(repo, codemeta):
    codemeta["softwareRequirements"] = [
        {"@type": "SoftwareSourceCode", "name": "numpy", "version": ">=1.24"}
    ]
    report = repo(
        {
            **base(codemeta),
            "pyproject.toml": (
                "[project]\n"
                'name = "testtool"\n'
                'version = "1.0.0"\n'
                'description = "A tool used by the rs-metadata test suite."\n'
                'dependencies = ["numpy >= 1.26"]\n'
            ),
        }
    )
    assert "consistency.mismatch" in codes_for(report, "softwareRequirements")
