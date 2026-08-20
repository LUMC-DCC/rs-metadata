"""Positive and negative tests for every LUMC profile rule.

Each rule gets both: a document that satisfies it and a document that breaks
exactly one thing. Asserting on the diagnostic *code* rather than on message
text means wording can be improved without rewriting the suite, while the
contract downstream tooling depends on stays pinned.
"""

from __future__ import annotations

import pytest

from rs_metadata.diagnostics import Severity
from rs_metadata.vocabulary import profile_field_policy
from tests.conftest import VALID_CFF, codes, codes_for, find, profile_errors

MANDATORY = profile_field_policy()["mandatory"]


def base(codemeta):
    return {"codemeta.json": codemeta, "CITATION.cff": VALID_CFF}


# ---------------------------------------------------------------------------
# Positive
# ---------------------------------------------------------------------------


def test_valid_record_has_no_errors(repo, codemeta):
    report = repo(base(codemeta))
    assert report.errors == [], "\n".join(d.message for d in report.errors)
    assert report.status in {"passed", "passed-with-warnings"}
    assert report.exit_code() == 0


def test_scalar_and_array_forms_are_equivalent(repo, codemeta):
    """CodeMeta lets a single value be written bare or as a one-element array."""
    codemeta["programmingLanguage"] = "Python"
    codemeta["schema:featureList"] = "http://edamontology.org/operation_0292"
    report = repo(base(codemeta))
    assert report.errors == []


def test_absolute_iri_spelling_of_feature_list_is_accepted(repo, codemeta):
    codemeta["https://schema.org/featureList"] = codemeta.pop("schema:featureList")
    report = repo(base(codemeta))
    assert report.errors == []
    assert "profile.non-canonical-value" in codes_for(report, "schema:featureList")


def test_software_application_type_is_accepted(repo, codemeta):
    codemeta["@type"] = "SoftwareApplication"
    assert repo(base(codemeta)).errors == []


def test_property_value_identifier_is_accepted(repo, codemeta):
    codemeta["identifier"] = {
        "@type": "PropertyValue",
        "propertyID": "doi",
        "value": "10.5281/zenodo.1234567",
    }
    assert repo(base(codemeta)).errors == []


def test_creative_work_license_is_accepted(repo, codemeta):
    codemeta["license"] = {
        "@type": "CreativeWork",
        "name": "Apache License 2.0",
        "url": "https://spdx.org/licenses/Apache-2.0",
    }
    assert repo(base(codemeta)).errors == []


# ---------------------------------------------------------------------------
# Mandatory fields
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("field", MANDATORY)
def test_each_mandatory_field_is_required(repo, codemeta, field):
    codemeta.pop(field)
    report = repo(base(codemeta))
    diagnostic = find(report, "profile.required-field", field)
    assert diagnostic.severity is Severity.ERROR
    assert field in diagnostic.message
    assert diagnostic.suggestion


def test_required_field_diagnostic_names_the_file(repo, codemeta):
    codemeta.pop("description")
    assert (
        "codemeta.json"
        in find(report_of(repo, codemeta), "profile.required-field").message
    )


def report_of(repo, codemeta):
    return repo(base(codemeta))


# ---------------------------------------------------------------------------
# Structure
# ---------------------------------------------------------------------------


def test_missing_context_is_reported_as_a_context_problem(repo, codemeta):
    codemeta.pop("@context")
    report = repo(base(codemeta))
    assert "profile.invalid-context" in codes(report)
    # Not also reported as a generic missing field.
    assert "profile.required-field" not in codes_for(report, "@context")


def test_unrecognized_context_is_an_error(repo, codemeta):
    codemeta["@context"] = "https://example.org/not-codemeta"
    assert "profile.invalid-context" in codes(repo(base(codemeta)))


def test_a_pre_3x_context_is_rejected(repo, codemeta):
    # This profile is defined against CodeMeta 3.x. Earlier versions renamed
    # properties, so the same record means something different under each.
    codemeta["@context"] = "https://doi.org/10.5063/schema/codemeta-2.0"
    diagnostic = find(repo(base(codemeta)), "profile.invalid-context", "@context")
    assert "3.x" in diagnostic.message


def test_an_unrecognized_context_stops_further_profile_checks(repo, codemeta):
    # Judging a record against the wrong vocabulary buries the one message
    # that matters under complaints about properties that are correct there.
    codemeta["@context"] = "https://doi.org/10.5063/schema/codemeta-2.0"
    codemeta["contIntegration"] = "https://ci.example.org/mytool"
    report = repo(base(codemeta))
    assert "profile.unknown-property" not in codes(report)
    assert len(profile_errors(report)) == 1


@pytest.mark.parametrize(
    "context",
    ["https://w3id.org/codemeta/3.0", "https://w3id.org/codemeta/3.1"],
)
def test_every_3x_context_is_current(repo, codemeta, context):
    # 3.0 and 3.1 resolve to byte-identical documents, and 3.0 is what the
    # common generators emit, so neither may produce a finding.
    codemeta["@context"] = [context, {"schema": "https://schema.org/"}]
    assert codes_for(repo(base(codemeta)), "@context") == set()


def test_wrong_type_for_a_property_is_reported(repo, codemeta):
    codemeta["name"] = 42
    assert "profile.invalid-type" in codes(repo(base(codemeta)))


def test_too_many_values_for_a_single_valued_field_is_reported(repo, codemeta):
    codemeta["name"] = ["not", "a", "single", "name"]
    diagnostic = find(repo(base(codemeta)), "profile.invalid-value", "name")
    assert "takes a single value" in diagnostic.message


def test_a_one_element_array_is_accepted_for_a_single_valued_field(repo, codemeta):
    """JSON-LD treats a bare value and a one-element array as the same."""
    codemeta["name"] = ["TestTool"]
    assert codes_for(repo(base(codemeta)), "name") == set()


def test_empty_string_is_rejected(repo, codemeta):
    codemeta["description"] = ""
    assert "profile.invalid-value" in codes(repo(base(codemeta)))


def test_empty_author_array_is_rejected(repo, codemeta):
    codemeta["author"] = []
    assert repo(base(codemeta)).errors


def test_relative_repository_url_is_rejected(repo, codemeta):
    codemeta["codeRepository"] = "github.com/lumc-test/testtool"
    assert repo(base(codemeta)).errors


# ---------------------------------------------------------------------------
# featureList
# ---------------------------------------------------------------------------


def test_unprefixed_feature_list_is_an_error(repo, codemeta):
    codemeta["featureList"] = codemeta.pop("schema:featureList")
    report = repo(base(codemeta))
    diagnostic = find(report, "profile.unprefixed-term")
    assert "silently discarded" in diagnostic.message
    assert "schema:featureList" in (diagnostic.suggestion or "")


def test_unprefixed_feature_list_is_reported_once(repo, codemeta):
    """One mistake, one diagnostic: not also 'missing' and 'unknown property'."""
    codemeta["featureList"] = codemeta.pop("schema:featureList")
    report = repo(base(codemeta))
    assert "profile.required-field" not in codes_for(report, "schema:featureList")
    assert "profile.unknown-property" not in codes(report)


def test_edam_topic_in_operations_is_rejected(repo, codemeta):
    codemeta["schema:featureList"] = ["http://edamontology.org/topic_0622"]
    diagnostic = find(
        repo(base(codemeta)), "profile.invalid-value", "schema:featureList"
    )
    assert "applicationSubCategory" in (diagnostic.suggestion or "")


def test_edam_operation_in_topics_is_rejected(repo, codemeta):
    codemeta["applicationSubCategory"] = ["http://edamontology.org/operation_0292"]
    diagnostic = find(
        repo(base(codemeta)), "profile.invalid-value", "applicationSubCategory"
    )
    assert "schema:featureList" in (diagnostic.suggestion or "")


def test_https_edam_uri_is_non_canonical(repo, codemeta):
    codemeta["schema:featureList"] = ["https://edamontology.org/operation_0292"]
    diagnostic = find(
        repo(base(codemeta)), "profile.non-canonical-value", "schema:featureList"
    )
    assert "http://edamontology.org/operation_0292" in (diagnostic.suggestion or "")


def test_malformed_edam_uri_is_an_error(repo, codemeta):
    codemeta["schema:featureList"] = ["http://edamontology.org/operation_92"]
    assert find(repo(base(codemeta)), "profile.invalid-value", "schema:featureList")


def test_free_text_operations_are_allowed_with_a_hint(repo, codemeta):
    codemeta["schema:featureList"] = ["Aligning reads to a reference"]
    report = repo(base(codemeta))
    assert report.errors == []
    assert "recommendation.incomplete" in codes_for(report, "schema:featureList")


# ---------------------------------------------------------------------------
# Identifiers
# ---------------------------------------------------------------------------


def test_invalid_orcid_checksum_is_an_error(repo, codemeta):
    codemeta["author"][0]["@id"] = "https://orcid.org/0000-0002-1825-0098"
    diagnostic = find(repo(base(codemeta)), "profile.invalid-value", "author")
    assert "check digit" in diagnostic.message


def test_placeholder_orcid_is_reported_as_a_placeholder(repo, codemeta):
    codemeta["author"][0]["@id"] = "https://orcid.org/0000-0000-0000-0000"
    report = repo(base(codemeta))
    assert "profile.placeholder-value" in codes_for(report, "author")
    # The check digit is wrong too, but that is not the useful message.
    assert "profile.invalid-value" not in codes_for(report, "author")


def test_duplicate_orcid_across_authors_is_flagged(repo, codemeta):
    codemeta["author"].append(
        {
            "@type": "Person",
            "@id": "https://orcid.org/0000-0002-1825-0097",
            "givenName": "Someone",
            "familyName": "Else",
        }
    )
    report = repo(base(codemeta))
    assert any("identifies one person" in d.message for d in report.diagnostics), [
        d.message for d in report.diagnostics
    ]


def test_invalid_ror_checksum_is_an_error(repo, codemeta):
    codemeta["author"][0]["affiliation"]["@id"] = "https://ror.org/05xvt9f18"
    diagnostic = find(repo(base(codemeta)), "profile.invalid-value", "author")
    assert "check digits" in diagnostic.message


def test_organization_maintainer_is_rejected(repo, codemeta):
    # CodeMeta types maintainer as Person, narrowing schema.org, which also
    # allows Organization. An institution belongs in copyrightHolder.
    codemeta["maintainer"] = [
        {
            "@type": "Organization",
            "@id": "https://ror.org/05xvt9f17",
            "name": "Leiden University Medical Center",
        }
    ]
    diagnostic = find(repo(base(codemeta)), "profile.invalid-type", "maintainer")
    assert "must be a Person node, but an Organization node was given" in (
        diagnostic.message
    )


def test_organization_is_accepted_where_the_range_allows_it(repo, codemeta):
    codemeta["copyrightHolder"] = [
        {
            "@type": "Organization",
            "@id": "https://ror.org/05xvt9f17",
            "name": "Leiden University Medical Center",
        }
    ]
    assert profile_errors(repo(base(codemeta))) == []


def test_node_without_a_type_is_accepted(repo, codemeta):
    # Common generators omit @type on authors; guessing the kind would risk
    # rejecting correct metadata, so a node where a node belongs is enough.
    codemeta["author"] = [{"givenName": "Jane", "familyName": "Doe"}]
    assert profile_errors(repo(base(codemeta))) == []


def test_invalid_ror_on_an_agents_own_id_is_an_error(repo, codemeta):
    # A ROR can appear as the agent's own @id, not only on an affiliation.
    # Only the affiliation case used to be checked.
    codemeta["author"] = [
        {
            "@type": "Organization",
            "name": "Leiden University Medical Center",
            "@id": "https://ror.org/05xvt9f18",
        }
    ]
    diagnostic = find(repo(base(codemeta)), "profile.invalid-value", "author")
    assert "check digits" in diagnostic.message


@pytest.mark.parametrize("prop", ["funder", "sponsor", "publisher", "editor"])
def test_agent_checks_cover_every_agent_valued_property(repo, codemeta, prop):
    # The agent properties come from CodeMeta's own type table, so all ten are
    # covered rather than the four that were once listed by hand.
    codemeta[prop] = [
        {
            "@type": "Person",
            "givenName": "Jane",
            "familyName": "Doe",
            "@id": "https://orcid.org/0000-0002-1825-0098",
        }
    ]
    diagnostic = find(repo(base(codemeta)), "profile.invalid-value", prop)
    assert "check digit" in diagnostic.message


def test_placeholder_doi_is_an_error(repo, codemeta):
    codemeta["identifier"] = "https://doi.org/10.0000/example.mytool.1"
    assert find(repo(base(codemeta)), "profile.placeholder-value", "identifier")


def test_example_com_url_is_an_error(repo, codemeta):
    codemeta["codeRepository"] = "https://example.com/mytool"
    assert find(repo(base(codemeta)), "profile.placeholder-value", "codeRepository")


def test_example_org_repository_is_only_a_warning(repo, codemeta):
    codemeta["codeRepository"] = "https://github.com/example/mytool"
    diagnostic = find(
        repo(base(codemeta)), "profile.placeholder-value", "codeRepository"
    )
    assert diagnostic.severity is Severity.WARNING


def test_author_without_orcid_gets_an_informational_hint(repo, codemeta):
    del codemeta["author"][0]["@id"]
    report = repo(base(codemeta))
    assert report.errors == []
    assert "recommendation.incomplete" in codes_for(report, "author")


def test_organization_author_is_not_asked_for_an_orcid(repo, codemeta):
    codemeta["author"] = [
        {
            "@type": "Organization",
            "@id": "https://ror.org/05xvt9f17",
            "name": "Leiden University Medical Center",
        }
    ]
    report = repo(base(codemeta))
    assert "recommendation.incomplete" not in codes_for(report, "author")


# ---------------------------------------------------------------------------
# Licenses
# ---------------------------------------------------------------------------


def test_bare_spdx_identifier_is_an_error(repo, codemeta):
    # CodeMeta types license as CreativeWork or URL, so a bare identifier
    # expands to a relative IRI and names nothing. The exact URL is suggested.
    codemeta["license"] = "Apache-2.0"
    diagnostic = find(repo(base(codemeta)), "profile.invalid-type", "license")
    assert "https://spdx.org/licenses/Apache-2.0" in (diagnostic.suggestion or "")


def test_unknown_spdx_url_is_an_error(repo, codemeta):
    codemeta["license"] = "https://spdx.org/licenses/Apache-2.0-only"
    diagnostic = find(repo(base(codemeta)), "profile.invalid-value", "license")
    assert "Did you mean" in (diagnostic.suggestion or "")


def test_unrecognized_license_text_is_an_error(repo, codemeta):
    codemeta["license"] = "Our institutional license"
    diagnostic = find(repo(base(codemeta)), "profile.invalid-type", "license")
    # An institutional license is still expressible, just not as bare text.
    assert "CreativeWork" in (diagnostic.suggestion or "")


def test_license_creative_work_is_accepted(repo, codemeta):
    codemeta["license"] = {
        "@type": "CreativeWork",
        "name": "LUMC internal license",
        "url": "https://example.org/lumc-license",
    }
    assert profile_errors(repo(base(codemeta))) == []


def test_non_spdx_license_url_is_an_error(repo, codemeta):
    # A plain URL is conformant CodeMeta but says nothing about which license
    # it is, so registries cannot map it to terms. That is a profile rule.
    codemeta["license"] = "https://opensource.org/licenses/MIT"
    assert find(repo(base(codemeta)), "profile.invalid-value", "license")


def test_deprecated_spdx_identifier_is_flagged(repo, codemeta):
    codemeta["license"] = "https://spdx.org/licenses/GPL-3.0"
    assert "profile.deprecated-value" in codes_for(repo(base(codemeta)), "license")


def test_known_spdx_url_raises_no_profile_finding(repo, codemeta):
    codemeta["license"] = "https://spdx.org/licenses/MIT"
    report = repo(base(codemeta))
    assert profile_errors(report) == []
    assert codes_for(report, "license") == {"consistency.mismatch"}


def test_spdx_expression_is_rejected_with_the_array_form(repo, codemeta):
    # CodeMeta has nowhere to put an SPDX operator, so dual licensing is
    # expressed as an array of SPDX URLs instead.
    codemeta["license"] = "MIT OR Apache-2.0"
    diagnostic = find(repo(base(codemeta)), "profile.invalid-type", "license")
    assert "List each license as its own SPDX URL" in (diagnostic.suggestion or "")


def test_license_array_of_spdx_urls_is_accepted(repo, codemeta):
    codemeta["license"] = [
        "https://spdx.org/licenses/MIT",
        "https://spdx.org/licenses/Apache-2.0",
    ]
    assert profile_errors(repo(base(codemeta))) == []


# ---------------------------------------------------------------------------
# Vocabularies and typos
# ---------------------------------------------------------------------------


def test_unknown_property_suggests_the_closest_term(repo, codemeta):
    codemeta["programingLanguage"] = ["Python"]
    diagnostic = find(repo(base(codemeta)), "profile.unknown-property")
    assert "programmingLanguage" in (diagnostic.suggestion or "")


def test_undeclared_prefix_is_an_error(repo, codemeta):
    codemeta["custom:field"] = "value"
    diagnostic = find(repo(base(codemeta)), "profile.invalid-context")
    assert "custom:" in diagnostic.message


def test_declared_prefix_is_accepted(repo, codemeta):
    codemeta["@context"].append({"lumc": "https://lumc.nl/terms/"})
    codemeta["lumc:internalId"] = "RSE-2026-001"
    assert repo(base(codemeta)).errors == []


def test_absolute_iri_property_is_accepted(repo, codemeta):
    codemeta["https://example.org/terms/custom"] = "value"
    report = repo(base(codemeta))
    assert "profile.unknown-property" not in codes(report)


def test_non_repostatus_development_status_is_an_error(repo, codemeta):
    # The vocabulary is closed, so anything outside it fails the build.
    codemeta["developmentStatus"] = "actively maintained"
    assert find(repo(base(codemeta)), "profile.invalid-value", "developmentStatus")


def test_repostatus_url_is_rejected(repo, codemeta):
    # developmentStatus is typed Text, so the bare term is the only member of
    # the vocabulary; the repostatus.org URL is not one of them.
    codemeta["developmentStatus"] = "https://www.repostatus.org/#active"
    diagnostic = find(
        repo(base(codemeta)), "profile.invalid-value", "developmentStatus"
    )
    assert "bare term" in (diagnostic.suggestion or "")


def test_repostatus_term_is_accepted(repo, codemeta):
    codemeta["developmentStatus"] = "active"
    assert "profile.invalid-value" not in codes_for(
        repo(base(codemeta)), "developmentStatus"
    )


def test_non_biotools_category_is_a_warning(repo, codemeta):
    # CodeMeta permits free text here, so this is a profile rule and stays a
    # warning rather than failing the build.
    codemeta["applicationCategory"] = "Notebook"
    report = repo(base(codemeta))
    assert profile_errors(report) == []
    assert "profile.invalid-value" in codes_for(report, "applicationCategory")


# ---------------------------------------------------------------------------
# Recommendations
# ---------------------------------------------------------------------------


def test_missing_recommendations_are_aggregated_into_one_finding(repo, codemeta):
    report = repo(base(codemeta))
    recommendations = [
        d for d in report.diagnostics if d.code == "recommendation.missing"
    ]
    assert len(recommendations) == 1
    assert "datePublished" in recommendations[0].message


def test_recommendations_never_fail_the_build(repo, codemeta):
    report = repo(base(codemeta))
    assert report.exit_code("error") == 0
    assert report.exit_code("warning") == 1
    assert report.exit_code("never") == 0


# ---------------------------------------------------------------------------
# Literal formats
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "value",
    [
        "2026-02-30",  # February has no 30th
        "2025-02-29",  # 2025 is not a leap year
        "2026-13-01",  # no 13th month
        "01/06/2026",  # ambiguous: 1 June or 6 January?
        "June 1, 2026",  # not ISO 8601 at all
        "2026-6-1",  # ISO 8601 requires zero padding
    ],
)
def test_malformed_dates_are_rejected(repo, codemeta, value):
    # A pattern over digits cannot know February has 28 days, so these are
    # decided by constructing the date rather than by matching a regex.
    codemeta["datePublished"] = value
    assert find(repo(base(codemeta)), "profile.invalid-value", "datePublished")


@pytest.mark.parametrize("value", ["2026-06-01", "2026-06", "2026"])
def test_valid_iso_dates_are_accepted(repo, codemeta, value):
    # Reduced precision is valid ISO 8601. Rejecting it would be a false alarm.
    codemeta["datePublished"] = value
    assert codes_for(repo(base(codemeta)), "datePublished") == set()


def test_a_bad_date_produces_exactly_one_finding(repo, codemeta):
    # The schema pattern rejects it too; only the message that explains ISO
    # 8601 should survive.
    codemeta["datePublished"] = "01/06/2026"
    assert (
        len(
            [
                d
                for d in repo(base(codemeta)).diagnostics
                if d.property == "datePublished"
            ]
        )
        == 1
    )


@pytest.mark.parametrize("value", [2026, "2026"])
def test_a_year_is_accepted_quoted_or_bare(repo, codemeta, value):
    # JSON-LD treats both alike and generators differ on which they emit.
    codemeta["copyrightYear"] = value
    assert codes_for(repo(base(codemeta)), "copyrightYear") == set()


def test_version_is_not_format_checked(repo, codemeta):
    # version is Number or Text, and the Text branch makes 1.0.0 correct.
    codemeta["version"] = "1.0.0-rc1"
    assert "profile.invalid-value" not in codes_for(repo(base(codemeta)), "version")


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("htp://github.com/lumc/tool", "did you mean 'http'"),
        ("hpts://github.com/lumc/tool", "did you mean 'https'"),
        ("https://", "no host"),
        ("https://github.com/a b", "whitespace"),
        ("github.com/lumc/tool", "no scheme"),
    ],
)
def test_malformed_urls_name_the_actual_defect(repo, codemeta, value, expected):
    # A scheme regex accepted all of these. The message says what is wrong
    # rather than repeating that a URL was expected.
    codemeta["codeRepository"] = value
    diagnostic = find(repo(base(codemeta)), "profile.invalid-type", "codeRepository")
    assert expected in diagnostic.message


@pytest.mark.parametrize(
    "value",
    [
        "https://github.com/lumc/tool",
        "git+https://github.com/lumc/tool",
        "ssh://git@github.com/lumc/tool",
        "ftps://files.example.org/tool",  # resembles https but is real
    ],
)
def test_legitimate_url_schemes_are_left_alone(repo, codemeta, value):
    # Rejecting an unfamiliar-but-real scheme would be a false alarm, so only
    # a near-miss of a web scheme that matches nothing real is flagged.
    codemeta["codeRepository"] = value
    assert "profile.invalid-type" not in codes_for(
        repo(base(codemeta)), "codeRepository"
    )


@pytest.mark.parametrize(
    "value", ["not an email", "jane@@example.org", "jane@localhost", "jane.doe.lumc.nl"]
)
def test_malformed_email_is_rejected(repo, codemeta, value):
    # CodeMeta types email as Text, so this is a profile rule: a malformed
    # address helps nobody and is nearly always a typo.
    codemeta["author"][0]["email"] = value
    assert find(repo(base(codemeta)), "profile.invalid-value", "email")


@pytest.mark.parametrize(
    "value", ["jane.doe@lumc.nl", "j+tag@sub.example.org", "mailto:jane@lumc.nl"]
)
def test_wellformed_email_is_accepted(repo, codemeta, value):
    codemeta["author"][0]["email"] = value
    assert "profile.invalid-value" not in codes_for(repo(base(codemeta)), "email")


@pytest.mark.parametrize(
    "identifier",
    [
        "urn:swh:1:dir:abc123",  # Software Heritage
        "doi:10.5281/zenodo.1234567",
        "https://example.org/people/jane",  # institutional person URI
    ],
)
def test_any_absolute_iri_identifies_an_agent(repo, codemeta, identifier):
    # Omitting an ORCID is only a nudge, so providing a different valid
    # identifier must not be a hard error. The schema used to demand ORCID.
    codemeta["author"][0]["@id"] = identifier
    assert profile_errors(repo(base(codemeta))) == []


@pytest.mark.parametrize("identifier", ["https://", "htp://orcid.org/x", "not-an-iri"])
def test_unresolvable_agent_id_is_an_error(repo, codemeta, identifier):
    codemeta["author"][0]["@id"] = identifier
    assert find(repo(base(codemeta)), "profile.invalid-value", "author")


def test_license_node_naming_a_known_spdx_license_is_nudged(repo, codemeta):
    # A node is conformant, but where SPDX already has an identifier the URL
    # says the same thing in a form registries resolve.
    codemeta["license"] = {"@type": "CreativeWork", "name": "Apache-2.0"}
    report = repo(base(codemeta))
    assert profile_errors(report) == []
    diagnostic = find(report, "profile.non-canonical-value", "license")
    assert diagnostic.suggestion == 'Use "https://spdx.org/licenses/Apache-2.0".'


# ---------------------------------------------------------------------------
# Subtyping, from schema.org's class hierarchy
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "declared", ["ScholarlyArticle", "SoftwareSourceCode", "Dataset", "Report"]
)
def test_a_subclass_satisfies_the_class_a_range_names(repo, codemeta, declared):
    """CodeMeta types citation as CreativeWork; all of these are CreativeWorks."""
    codemeta["citation"] = [{"@type": declared, "name": "Something"}]
    assert profile_errors(repo(base(codemeta))) == []


def test_subtyping_runs_one_way_only(repo, codemeta):
    # referencePublication is a ScholarlyArticle. A plain CreativeWork is the
    # parent, not the child, so it does not satisfy the narrower type.
    codemeta["referencePublication"] = [{"@type": "CreativeWork", "name": "P"}]
    assert find(repo(base(codemeta)), "profile.invalid-type", "referencePublication")


def test_an_unrelated_class_is_still_rejected(repo, codemeta):
    codemeta["referencePublication"] = [{"@type": "Person", "familyName": "Doe"}]
    assert find(repo(base(codemeta)), "profile.invalid-type", "referencePublication")
