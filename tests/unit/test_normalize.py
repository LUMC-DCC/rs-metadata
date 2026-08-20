"""The equivalence logic, tested directly.

These are the decisions that determine whether the validator is trusted: a
strategy that is too strict produces false alarms, and one that is too lenient
misses real drift. Both directions are asserted for every strategy.
"""

from __future__ import annotations

import pytest

from rs_metadata.normalize import (
    extract_doi,
    extract_orcid,
    extract_ror,
    get_strategy,
    normalize_license,
    normalize_loose_name,
    normalize_text,
    normalize_uri,
    normalize_version,
    orcid_checksum_valid,
    parse_requirement,
    person_record,
    ror_checksum_valid,
    scalarize,
    split_full_name,
)

# ---------------------------------------------------------------------------
# Identifiers
# ---------------------------------------------------------------------------


def test_orcid_checksum_accepts_the_published_demonstration_record():
    # ORCID publishes 0000-0002-1825-0097 (Josiah Carberry) for documentation.
    assert orcid_checksum_valid("0000-0002-1825-0097")


@pytest.mark.parametrize(
    "orcid",
    [
        "0000-0002-1825-0098",  # last digit changed
        "0000-0000-0000-0000",  # the guide's placeholder
        "0000-0002-1825-009",  # too short
        "000A-0002-1825-0097",  # letter in the body
    ],
)
def test_orcid_checksum_rejects_bad_identifiers(orcid):
    assert not orcid_checksum_valid(orcid)


def test_ror_checksum_accepts_the_lumc_identifier():
    assert ror_checksum_valid("05xvt9f17")


@pytest.mark.parametrize("ror", ["05xvt9f18", "05xvt9f1", "05xvt9fxx"])
def test_ror_checksum_rejects_bad_identifiers(ror):
    assert not ror_checksum_valid(ror)


@pytest.mark.parametrize(
    "value",
    [
        "https://orcid.org/0000-0002-1825-0097",
        "http://orcid.org/0000-0002-1825-0097",
        "0000-0002-1825-0097",
    ],
)
def test_orcid_is_extracted_from_every_spelling(value):
    assert extract_orcid(value) == "0000-0002-1825-0097"


def test_ror_is_extracted_from_url_and_bare_form():
    assert extract_ror("https://ror.org/05xvt9f17") == "05xvt9f17"
    assert extract_ror("05xvt9f17") == "05xvt9f17"


@pytest.mark.parametrize(
    "value",
    [
        "10.5281/zenodo.1234567",
        "https://doi.org/10.5281/zenodo.1234567",
        "http://dx.doi.org/10.5281/zenodo.1234567",
        "doi:10.5281/zenodo.1234567",
        "10.5281/ZENODO.1234567",
    ],
)
def test_doi_is_extracted_from_every_spelling(value):
    assert extract_doi(value) == "10.5281/zenodo.1234567"


def test_doi_shaped_substring_in_an_unrelated_url_is_not_a_doi():
    """Anchored matching: a path that looks like a DOI is not one."""
    assert extract_doi("https://github.com/org/10.1234/repo") is None


def test_property_value_node_yields_its_doi():
    node = {"@type": "PropertyValue", "propertyID": "doi", "value": "10.5281/zenodo.1"}
    assert extract_doi(node) == "10.5281/zenodo.1"


# ---------------------------------------------------------------------------
# Versions
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("left", "right"),
    [
        ("1.2.0", "v1.2.0"),
        ("1.2.0", "1.2"),
        ("1.2.0", "1.2.0.0"),
        ("1.2-3", "1.2.3"),  # R uses a dash before the final component
        ("2.1.0", "  2.1.0  "),
    ],
)
def test_equivalent_versions_share_a_key(left, right):
    assert normalize_version(left) == normalize_version(right)


@pytest.mark.parametrize(
    ("left", "right"),
    [
        ("1.2.0", "1.2.1"),
        ("1.2.0", "1.20"),
        ("1.0.0", "1.0.0-rc1"),
        ("2.0.0", "1.0.0"),
    ],
)
def test_different_versions_do_not_share_a_key(left, right):
    assert normalize_version(left) != normalize_version(right)


def test_short_commit_hash_matches_the_full_one():
    full = "a3f8c2d1b4e7f0291a3f8c2d1b4e7f0291a3f8c2"
    assert normalize_version(full) == normalize_version(full[:7])


def test_calendar_version_is_not_mistaken_for_a_commit_hash():
    normalized = normalize_version("20240101")
    assert normalized == "20240101"
    assert normalized is not None and not normalized.startswith("sha:")


# ---------------------------------------------------------------------------
# URLs
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "value",
    [
        "https://github.com/org/tool",
        "http://github.com/org/tool",
        "https://github.com/org/tool/",
        "https://github.com/org/tool.git",
        "https://www.github.com/org/tool",
        "git+https://github.com/org/tool.git",
        "git@github.com:org/tool.git",
        "https://github.com:443/org/tool",
    ],
)
def test_repository_url_spellings_all_normalize_together(value):
    assert normalize_uri(value) == "github.com/org/tool"


def test_different_repositories_stay_different():
    assert normalize_uri("https://github.com/a/tool") != normalize_uri(
        "https://github.com/b/tool"
    )


def test_npm_shorthand_expands_only_when_asked():
    assert normalize_uri("org/tool", expand_shorthand=True) == "github.com/org/tool"
    assert normalize_uri("org/tool") == "org/tool"


def test_non_http_scheme_is_preserved():
    normalized = normalize_uri("mailto:x@example.com")
    assert normalized is not None and normalized.startswith("mailto:")


# ---------------------------------------------------------------------------
# Licenses
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "value",
    [
        "Apache-2.0",
        "apache-2.0",
        "https://spdx.org/licenses/Apache-2.0",
        "http://spdx.org/licenses/Apache-2.0",
        "https://spdx.org/licenses/Apache-2.0.html",
        {"@type": "CreativeWork", "url": "https://spdx.org/licenses/Apache-2.0"},
    ],
)
def test_license_spellings_all_normalize_together(value):
    assert normalize_license(value) == "Apache-2.0"


def test_different_licenses_stay_different():
    assert normalize_license("MIT") != normalize_license("Apache-2.0")


def test_spdx_expression_is_canonicalised():
    assert normalize_license("mit OR apache-2.0") == "MIT OR Apache-2.0"


def test_unknown_license_falls_back_to_text():
    assert normalize_license("Our License") == normalize_license("  our license  ")


# ---------------------------------------------------------------------------
# Names and people
# ---------------------------------------------------------------------------


def test_display_name_and_package_name_compare_equal():
    assert normalize_loose_name("MyTool") == normalize_loose_name("my-tool")
    assert normalize_loose_name("Read_Aligner") == normalize_loose_name("read.aligner")


@pytest.mark.parametrize(
    ("full", "given", "family"),
    [
        ("Jane Doe", "Jane", "Doe"),
        ("Doe, Jane", "Jane", "Doe"),
        ("Jan van der Berg", "Jan", "van der Berg"),
        ("Maria de Vries", "Maria", "de Vries"),
        ("Ludwig von Mises", "Ludwig", "von Mises"),
        ("Cher", None, "Cher"),
    ],
)
def test_dutch_and_german_particles_stay_with_the_family_name(full, given, family):
    """Splitting on whitespace alone gets Dutch names wrong, and LUMC is Dutch."""
    assert split_full_name(full) == (given, family)


def test_people_strategy_matches_on_orcid_despite_different_names():
    strategy = get_strategy("people")
    anchor = [
        {
            "@type": "Person",
            "@id": "https://orcid.org/0000-0002-1825-0097",
            "givenName": "Josiah",
            "familyName": "Carberry",
        }
    ]
    source = [
        {
            "family-names": "Karberri",
            "given-names": "J.",
            "orcid": "0000-0002-1825-0097",
        }
    ]
    assert strategy.compare(anchor, source).identical


def test_people_strategy_treats_different_orcids_as_different_people():
    strategy = get_strategy("people")
    anchor = [
        {
            "familyName": "Doe",
            "givenName": "Jane",
            "@id": "https://orcid.org/0000-0002-1825-0097",
        }
    ]
    source = [
        {"family-names": "Doe", "given-names": "Jane", "orcid": "0000-0001-5109-3700"}
    ]
    assert not strategy.compare(anchor, source).identical


def test_people_strategy_accepts_initials():
    strategy = get_strategy("people")
    anchor = [{"givenName": "Josiah", "familyName": "Carberry"}]
    source = [{"given-names": "J.", "family-names": "Carberry"}]
    assert strategy.compare(anchor, source).identical


def test_people_strategy_rejects_different_given_names():
    strategy = get_strategy("people")
    anchor = [{"givenName": "Jane", "familyName": "Doe"}]
    source = [{"given-names": "John", "family-names": "Doe"}]
    assert not strategy.compare(anchor, source).identical


def test_people_matching_is_one_to_one():
    """Two anchor entries must not both match a single source entry."""
    strategy = get_strategy("people")
    anchor = [
        {"givenName": "Jane", "familyName": "Doe"},
        {"givenName": "Jane", "familyName": "Doe"},
    ]
    source = [{"given-names": "Jane", "family-names": "Doe"}]
    result = strategy.compare(anchor, source)
    assert result.shared == 1
    assert len(result.only_in_anchor) == 1


def test_organization_entry_matches_by_name():
    strategy = get_strategy("people")
    anchor = [{"@type": "Organization", "name": "Leiden University Medical Center"}]
    source = [{"name": "leiden university medical center"}]
    assert strategy.compare(anchor, source).identical


def test_person_record_reads_both_naming_conventions():
    codemeta = person_record({"givenName": "Jane", "familyName": "Doe"})
    cff = person_record({"given-names": "Jane", "family-names": "Doe"})
    assert (codemeta.given, codemeta.family) == (cff.given, cff.family)


# ---------------------------------------------------------------------------
# Dependencies
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "name", "constraint"),
    [
        ("numpy>=1.24", "numpy", ">=1.24"),
        ("numpy >= 1.24", "numpy", ">=1.24"),
        ("numpy[extra]>=1.24", "numpy", ">=1.24"),
        ('numpy>=1.24; python_version < "3.11"', "numpy", ">=1.24"),
        ({"name": "numpy", "version": ">=1.24"}, "numpy", ">=1.24"),
        ("dplyr (>= 1.0)", "dplyr", ">=1.0"),
        ("matplotlib", "matplotlib", ""),
    ],
)
def test_requirements_parse_across_ecosystems(value, name, constraint):
    requirement = parse_requirement(value)
    assert requirement is not None
    assert requirement.name == name
    assert requirement.constraint == constraint


def test_dependency_sets_report_presence_separately_from_conflicts():
    strategy = get_strategy("dependency-set")
    result = strategy.compare(
        [{"name": "numpy", "version": ">=2.0"}, {"name": "scipy"}],
        ["numpy>=1.24", "pandas"],
    )
    assert [c.subject for c in result.conflicts] == ["numpy"]
    assert result.only_in_anchor == ["scipy"]
    assert result.only_in_source == ["pandas"]


def test_missing_constraint_on_one_side_is_not_a_conflict():
    strategy = get_strategy("dependency-set")
    result = strategy.compare([{"name": "numpy"}], ["numpy>=1.24"])
    assert result.conflicts == []


# ---------------------------------------------------------------------------
# Miscellaneous
# ---------------------------------------------------------------------------


def test_language_strategy_ignores_a_pinned_version():
    strategy = get_strategy("language")
    assert strategy.key(
        {"@type": "ComputerLanguage", "name": "Python", "version": "3.12"}
    ) == (strategy.key("Python"))


def test_scalarize_prefers_identity_or_label_as_requested():
    node = {"name": "Python", "url": "https://python.org"}
    assert scalarize(node) == "https://python.org"
    assert scalarize(node, ("name", "url")) == "Python"


def test_text_normalisation_ignores_case_whitespace_and_trailing_stops():
    assert normalize_text("  A  Tool.  ") == normalize_text("a tool")


def test_empty_values_normalize_to_none():
    assert normalize_text("   ") is None
    assert normalize_version("") is None
    assert normalize_uri("") is None


@pytest.mark.parametrize(
    ("written", "expected"),
    [
        ("Jane Doe", ("Jane", "Doe")),
        # Particles belong with the family name, across locales. The hand-written
        # prefix list this replaced handled the Dutch and German cases only.
        ("Jan van der Berg", ("Jan", "van der Berg")),
        ("Ludwig von Mises", ("Ludwig", "von Mises")),
        ("Maria de la Cruz", ("Maria", "de la Cruz")),
        ("Jean-Luc de La Fontaine", ("Jean-Luc", "de La Fontaine")),
        ("Doe, Jane", ("Jane", "Doe")),
        ("Mariia Steeghs-Turchina", ("Mariia", "Steeghs-Turchina")),
        # A mononym is a family name, which is what citation styles do with it.
        ("Cher", (None, "Cher")),
    ],
)
def test_full_names_split_with_particles_intact(written, expected):
    from rs_metadata.normalize.people import split_full_name

    assert split_full_name(written) == expected


# ---------------------------------------------------------------------------
# Best-effort comparison
# ---------------------------------------------------------------------------


def test_best_effort_folds_a_timestamp_onto_its_calendar_day():
    """GitHub stamps to the second; a metadata file records a day."""
    strategy = get_strategy("best-effort")
    assert strategy.compare(["2026-06-01"], ["2026-06-01T09:31:07Z"]).identical


def test_best_effort_reduces_a_node_the_way_json_ld_intends():
    strategy = get_strategy("best-effort")
    result = strategy.compare(
        ["https://example.org/x"], [{"@id": "https://example.org/x", "name": "X"}]
    )
    assert result.identical


def test_best_effort_declines_rather_than_guessing():
    """A shape it was never taught is reported as considered, not as a difference.

    This is the whole point of the strategy: it backs concepts the profile has
    no opinion about, so inventing a disagreement would be worse than silence.
    """
    strategy = get_strategy("best-effort")
    result = strategy.compare([{"unexpected": ["shape"]}], [{"other": 1}])
    assert not result.comparable
    assert not result.conflicts


def test_best_effort_still_reports_a_real_difference():
    strategy = get_strategy("best-effort")
    result = strategy.compare(["one"], ["two"])
    assert result.comparable
    assert not result.identical
