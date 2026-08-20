"""Structural invariants of the schemas, mappings and adapter registry.

These tests guard the seams between the declarative parts of the project. They
are the ones that catch a mapping rule nobody wired up, a diagnostic code
emitted but never documented, or a schema that drifted from the field policy
the documentation quotes.
"""

from __future__ import annotations

import json
import re

import jsonschema
import pytest

from rs_metadata import PROFILE_VERSION, __version__
from rs_metadata.adapters import companion_adapters
from rs_metadata.diagnostics import CATALOG, Severity
from rs_metadata.mapping import Rule, available, load
from rs_metadata.normalize import STRATEGIES
from rs_metadata.vocabulary import profile_schema, report_schema, vocabularies
from tests.conftest import REPO_ROOT, VALID_CFF, write_repo

SOURCE_FILES = sorted((REPO_ROOT / "src" / "rs_metadata").rglob("*.py"))
MAPPINGS = REPO_ROOT / "src" / "rs_metadata" / "mappings"


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


def test_profile_schema_is_itself_valid():
    jsonschema.Draft202012Validator.check_schema(profile_schema())


def test_report_schema_is_itself_valid():
    jsonschema.Draft202012Validator.check_schema(report_schema())


def test_field_policy_matches_the_schema_required_keyword():
    """Docs, validator and schema must not be able to disagree here."""
    schema = profile_schema()
    declared = set(schema["x-lumc-profile"]["mandatory"])
    required = set(schema["required"]) - {"@context", "@type"}
    assert declared == required


def test_recommended_fields_are_all_described_in_the_schema():
    schema = profile_schema()
    properties = schema["properties"]
    for field in schema["x-lumc-profile"]["recommended"]:
        assert field in properties, f"{field} is recommended but has no schema entry"


def test_profile_does_not_forbid_extra_codemeta_properties():
    """Any valid CodeMeta property outside the LUMC minimum must remain allowed."""
    schema = profile_schema()
    assert "additionalProperties" not in schema
    assert schema["x-lumc-profile"]["profileVersion"] == PROFILE_VERSION


def test_report_validates_against_its_own_schema(repo, codemeta):
    report = repo({"codemeta.json": codemeta, "CITATION.cff": VALID_CFF})
    jsonschema.Draft202012Validator(report_schema()).validate(report.to_dict())


def test_failing_report_validates_against_its_own_schema(tmp_path):
    from rs_metadata.core import Options, validate

    write_repo(tmp_path, {"codemeta.json": {"name": "x"}, "CITATION.cff": "not: cff\n"})
    report = validate(Options(root=tmp_path))
    assert report.status == "failed"
    jsonschema.Draft202012Validator(report_schema()).validate(report.to_dict())


# ---------------------------------------------------------------------------
# Mappings
# ---------------------------------------------------------------------------


def test_every_adapter_except_the_anchor_has_a_mapping():
    for adapter in companion_adapters():
        assert adapter.mapping is not None, adapter.id


@pytest.mark.parametrize("name", available())
def test_mapping_files_are_well_formed(name):
    mapping = load(name)
    assert mapping.id
    assert mapping.fields
    assert mapping.reference.origin in {"codemeta-upstream", "rs-metadata", "mixed"}
    for rule in mapping.fields.values():
        # Rule() rejects an unknown value at load time, so this pins that
        # the mapping went through that parsing rather than a raw string.
        assert isinstance(rule.rule, Rule)
        if rule.comparable:
            assert rule.strategy in STRATEGIES, rule.strategy
        else:
            assert rule.reason, f"{name}:{rule.property} must explain itself"


@pytest.mark.parametrize("name", available())
def test_upstream_mappings_cite_their_source(name):
    """Provenance is machine-readable so reports can distinguish crosswalks."""
    mapping = load(name)
    if mapping.reference.origin in {"codemeta-upstream", "mixed"}:
        assert mapping.reference.source, name
        assert mapping.reference.retrieved, name


@pytest.mark.parametrize("adapter", companion_adapters(), ids=lambda a: a.id)
def test_adapters_only_emit_concepts_their_mapping_declares(adapter, tmp_path):
    """An extracted concept with no rule would be silently dropped."""
    mapping = adapter.mapping
    assert mapping is not None
    fixture = RICH_FIXTURES[adapter.id]
    path = tmp_path / adapter.filenames[0]
    path.write_text(fixture, encoding="utf-8")
    parsed = adapter.parse(path, adapter.filenames[0])
    concepts = adapter.map_to_codemeta(parsed)
    undeclared = set(concepts) - set(mapping.fields)
    assert not undeclared, f"{adapter.id} emits unmapped concepts: {undeclared}"


@pytest.mark.parametrize("adapter", companion_adapters(), ids=lambda a: a.id)
def test_uncomparable_rules_are_actually_reachable(adapter, tmp_path):
    """A `comparable: false` rule is only honest if the adapter extracts the field.

    Without this, a mapping can claim to have considered a field that the code
    never looks at, and the report silently omits it.
    """
    mapping = adapter.mapping
    assert mapping is not None
    declared = {
        rule.property for rule in mapping.fields.values() if not rule.comparable
    }
    if not declared:
        pytest.skip(f"{adapter.id} declares no uncomparable fields")
    path = tmp_path / adapter.filenames[0]
    path.write_text(RICH_FIXTURES[adapter.id], encoding="utf-8")
    parsed = adapter.parse(path, adapter.filenames[0])
    concepts = adapter.map_to_codemeta(parsed)
    missing = declared - set(concepts)
    assert not missing, (
        f"{adapter.id} declares {missing} not comparable but never extracts them, "
        f"so the report cannot say they were considered"
    )


# ---------------------------------------------------------------------------
# Diagnostics
# ---------------------------------------------------------------------------


def test_every_code_emitted_in_the_source_is_in_the_catalog():
    """A code that is not in the catalog has no documentation and no `explain`."""
    pattern = re.compile(
        r'"((?:profile|recommendation|source|consistency|internal)\.[a-z-]+)"'
    )
    used = set()
    for path in SOURCE_FILES:
        used.update(pattern.findall(path.read_text(encoding="utf-8")))
    unknown = used - set(CATALOG)
    assert not unknown, f"undocumented diagnostic codes: {sorted(unknown)}"


def test_catalog_entries_are_complete():
    for code, entry in CATALOG.items():
        assert entry.code == code
        assert entry.title and entry.description
        assert isinstance(entry.severity, Severity)
        assert entry.docs.startswith("https://")
        if entry.severity is not Severity.INFO:
            # Anything that can fail a build must say how to make it stop.
            assert entry.remediation, code


def test_code_names_follow_the_documented_pattern():
    pattern = re.compile(r"^[a-z][a-z0-9-]*\.[a-z][a-z0-9-]*$")
    for code in CATALOG:
        assert pattern.match(code), code


# ---------------------------------------------------------------------------
# Vendored data
# ---------------------------------------------------------------------------


def test_vendored_data_records_its_provenance():
    from rs_metadata.vocabulary import provenance

    sources = provenance()["sources"]
    assert {"codemeta", "citation-file-format", "spdx-license-list"} <= set(sources)
    for name, entry in sources.items():
        assert entry.get("url"), name
        assert entry.get("retrieved"), name
        assert entry.get("files"), name


def test_vocabularies_declare_whether_they_are_closed():
    catalog = vocabularies()
    assert catalog["developmentStatus"]["closed"] is True
    # bio.tools tool types are preferred but free text is permitted.
    assert catalog["applicationCategory"]["closed"] is False


# ---------------------------------------------------------------------------
# Versions
# ---------------------------------------------------------------------------


def test_package_version_matches_pyproject():
    text = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    match = re.search(r'^version = "([^"]+)"', text, re.MULTILINE)
    assert match and match.group(1) == __version__


def test_action_is_well_formed_and_drives_the_shared_core():
    """The Action must render the same report the CLI does, not reimplement it."""
    import yaml

    action = yaml.safe_load((REPO_ROOT / "action.yml").read_text(encoding="utf-8"))
    assert action["runs"]["using"] == "composite"

    steps = action["runs"]["steps"]
    script = "\n".join(step.get("run", "") for step in steps)
    assert "rs-metadata" in script
    assert "--format github" in script
    assert "--fail-on" in script
    assert "--report" in script

    # Every documented output must actually be produced by the CLI.
    assert set(action["outputs"]) == {
        "status",
        "errors",
        "warnings",
        "notes",
        "report-path",
    }
    assert {"codemeta", "fail-on", "report", "working-directory"} <= set(
        action["inputs"]
    )


def test_action_inputs_are_all_documented():
    """The Action reference has one home; an undocumented input fails here."""
    import yaml

    action = yaml.safe_load((REPO_ROOT / "action.yml").read_text(encoding="utf-8"))
    reference = (REPO_ROOT / "docs" / "using" / "ci-and-cli.md").read_text(
        encoding="utf-8"
    )
    for name in action["inputs"]:
        assert f"`{name}`" in reference, (
            f"input {name} is undocumented in docs/using/ci-and-cli.md"
        )
    for name in action["outputs"]:
        assert f"`{name}`" in reference, (
            f"output {name} is undocumented in docs/using/ci-and-cli.md"
        )


# ---------------------------------------------------------------------------
# Fixtures used above
# ---------------------------------------------------------------------------

RICH_FIXTURES = {
    "cff": VALID_CFF
    + (
        "abstract: An abstract.\n"
        "url: https://example-lumc.nl/tool\n"
        "repository-artifact: https://example-lumc.nl/tool.tar.gz\n"
        "date-released: '2026-06-01'\n"
        "keywords:\n  - genomics\n"
        "identifiers:\n  - type: url\n    value: https://bio.tools/testtool\n"
        "contact:\n  - family-names: Carberry\n    given-names: Josiah\n"
        "references:\n"
        "  - type: article\n    title: Paper\n"
        "    authors:\n      - family-names: Carberry\n        given-names: Josiah\n"
        "preferred-citation:\n"
        "  type: article\n  title: Paper\n  doi: 10.1000/x\n"
        "  authors:\n    - family-names: Carberry\n      given-names: Josiah\n"
    ),
    "pyproject": """\
[project]
name = "test-tool"
version = "1.0.0"
description = "Summary."
requires-python = ">=3.11"
license = "Apache-2.0"
keywords = ["genomics"]
authors = [{ name = "Josiah Carberry" }]
maintainers = [{ name = "Josiah Carberry" }]
dependencies = ["numpy>=1.24"]
classifiers = [
    "Development Status :: 5 - Production/Stable",
    "Operating System :: POSIX :: Linux",
    "Programming Language :: Python :: 3",
]

[project.urls]
Homepage = "https://example-lumc.nl"
Repository = "https://github.com/lumc-test/testtool"
Issues = "https://github.com/lumc-test/testtool/issues"
Documentation = "https://example-lumc.nl/docs"
Download = "https://example-lumc.nl/testtool-1.0.0.tar.gz"
""",
    "package-json": json.dumps(
        {
            "name": "testtool",
            "version": "1.0.0",
            "description": "Summary.",
            "license": "Apache-2.0",
            "homepage": "https://example-lumc.nl",
            "repository": "lumc-test/testtool",
            "bugs": {"url": "https://github.com/lumc-test/testtool/issues"},
            "author": "Josiah Carberry <j@example-lumc.nl>",
            "contributors": [{"name": "Someone Else"}],
            "keywords": ["genomics"],
            "dependencies": {"lodash": "^4"},
            "peerDependencies": {"react": "^18"},
            "devDependencies": {"jest": "^29"},
            "optionalDependencies": {"fsevents": "^2"},
            "cpu": ["x64", "arm64"],
            "engines": {"node": ">=18"},
            "os": ["linux", "darwin"],
        },
        indent=2,
    ),
    "r-description": """\
Package: testtool
Title: TestTool
Version: 1.0-0
Date: 2026-06-01
Description: A description.
Authors@R: c(person(given = "Josiah", family = "Carberry", role = c("aut", "cre")),
             person(given = "Someone", family = "Else", role = "ctb"))
Maintainer: Josiah Carberry <j@example-lumc.nl>
License: Apache License 2.0
URL: https://github.com/lumc-test/testtool
BugReports: https://github.com/lumc-test/testtool/issues
Imports: dplyr (>= 1.0)
Depends: R (>= 4.0)
Suggests: testthat (>= 3.0)
""",
    "github": json.dumps(
        {
            "name": "testtool",
            "full_name": "lumc-test/testtool",
            "description": "Summary.",
            "html_url": "https://github.com/lumc-test/testtool",
            "homepage": "https://example-lumc.nl",
            "topics": ["genomics"],
            "language": "Python",
            "has_issues": True,
            "created_at": "2026-01-15T10:00:00Z",
            "updated_at": "2026-06-01T12:30:00Z",
            "license": {"spdx_id": "Apache-2.0", "name": "Apache License 2.0"},
        },
        indent=2,
    ),
    "zenodo": json.dumps(
        {
            "title": "TestTool",
            "description": "A description.",
            "version": "1.0.0",
            "license": "Apache-2.0",
            "upload_type": "software",
            "publication_date": "2026-06-01",
            "doi": "10.5281/zenodo.0000000",
            "keywords": ["genomics"],
            "related_identifiers": [
                {
                    "identifier": "https://github.com/lumc-test/testtool",
                    "relation": "isSupplementTo",
                },
                {
                    "identifier": "https://example-lumc.nl/testtool-1.0.0.tar.gz",
                    "relation": "isIdenticalTo",
                },
            ],
            "grants": [{"id": "10.13039/501100000780::283595"}],
            "creators": [
                {
                    "name": "Carberry, Josiah",
                    "orcid": "0000-0002-1825-0097",
                    "affiliation": "Example Institute",
                }
            ],
            "contributors": [
                {"name": "Roe, John", "type": "ContactPerson"},
                {"name": "Doe, Jane", "type": "Editor"},
                {"name": "Acme Ltd", "type": "Producer"},
                {"name": "Example Institute", "type": "RightsHolder"},
                {"name": "Funder Trust", "type": "Sponsor"},
                {"name": "Someone Else", "type": "Researcher"},
            ],
        },
        indent=2,
    ),
    "julia-project": """\
name = "ReadAligner"
uuid = "7876af07-990d-54b4-ab0e-23690620f79a"
version = "1.0.0"
authors = ["Josiah Carberry <j@example-lumc.nl>"]

[deps]
JSON = "682c06a0-de6a-54ab-a142-c8b1cf79cde6"

[compat]
julia = "1.10"
JSON = "0.21"
""",
    "cargo": """\
[package]
name = "testtool"
version = "1.0.0"
edition = "2021"
description = "Summary."
license = "Apache-2.0"
repository = "https://github.com/lumc-test/testtool"
homepage = "https://example-lumc.nl"
documentation = "https://docs.rs/testtool"
authors = ["Josiah Carberry <j@example-lumc.nl>"]
keywords = ["genomics"]
categories = ["science"]

[dependencies]
serde = "1.0"
""",
    "dockerfile": """\
FROM python:3.11-slim
LABEL org.opencontainers.image.title="TestTool" \\
      org.opencontainers.image.description="Summary." \\
      org.opencontainers.image.version="1.0.0" \\
      org.opencontainers.image.licenses="Apache-2.0" \\
      org.opencontainers.image.source="https://github.com/lumc-test/testtool" \\
      org.opencontainers.image.url="https://example-lumc.nl" \\
      org.opencontainers.image.documentation="https://example-lumc.nl/docs" \\
      org.opencontainers.image.authors="Josiah Carberry <j@example-lumc.nl>" \\
      org.opencontainers.image.vendor="Example Institute"
""",
}


@pytest.mark.parametrize("adapter", companion_adapters(), ids=lambda a: a.id)
def test_every_mapping_rule_is_reachable_from_its_adapter(adapter, tmp_path):
    """A rule for a field the adapter never reads is documentation of a lie.

    The crosswalk page is generated from these files, so an unreachable rule
    tells a reader that a field is compared when nothing ever reads it. This
    is the reverse of the check above: that one catches an adapter emitting
    more than its mapping declares, this one catches a mapping declaring more
    than its adapter can produce.
    """
    mapping = adapter.mapping
    assert mapping is not None
    path = tmp_path / adapter.filenames[0]
    path.write_text(RICH_FIXTURES[adapter.id], encoding="utf-8")
    emitted = set(adapter.map_to_codemeta(adapter.parse(path, adapter.filenames[0])))
    unreachable = set(mapping.fields) - emitted
    assert not unreachable, (
        f"{adapter.id} declares rules for {sorted(unreachable)} that its "
        f"rich fixture never produces. Either the adapter does not read the "
        f"field, or the fixture does not exercise it."
    )


def test_no_doctest_asserts_a_platform_specific_path():
    """`PosixPath(...)` in expected output is a doctest that only runs on POSIX.

    It passes everywhere the developers work and fails on Windows, and since
    doctest stops a docstring at its first failure, one such line hides every
    later one in the same docstring. That is exactly how this got through
    twice. Compare paths, or render them with `as_posix()`, which reads the
    same on every platform.
    """
    offenders = []
    for path in SOURCE_FILES:
        for number, line in enumerate(
            path.read_text(encoding="utf-8").splitlines(), start=1
        ):
            if "PosixPath(" in line or "WindowsPath(" in line:
                offenders.append(f"{path.relative_to(REPO_ROOT)}:{number}")
    assert not offenders, (
        f"platform-specific path repr in a doctest: {offenders}. Use "
        f"`.as_posix()`, or compare against a Path built the same way."
    )


def test_schema_ids_match_where_the_docs_build_publishes_them():
    """A `$id` is a promise that the schema is retrievable there.

    Both schemas are served by the documentation site, at a path built from
    the release version. If the two ever disagree, every `$ref` written
    against the published schema breaks — silently, because a JSON Schema
    validator reports an unresolvable reference, not a wrong one.
    """
    from rs_metadata import __version__

    base = "https://lumc-dcc.github.io/rs-metadata/schema"
    schemas = sorted((REPO_ROOT / "src" / "rs_metadata" / "schema").glob("*.json"))
    assert schemas, "no schemas found to check"
    for path in schemas:
        document = json.loads(path.read_text(encoding="utf-8"))
        assert document["$id"] == f"{base}/{__version__}/{path.name}", (
            f"{path.name} declares $id {document['$id']!r}, which is not where "
            f"docs/conf.py publishes it."
        )


@pytest.mark.parametrize("adapter", companion_adapters(), ids=lambda a: a.id)
def test_adapters_never_record_the_same_value_twice(adapter, tmp_path):
    """One fact, recorded once.

    Two code paths reaching the same conclusion — a Python classifier and the
    mere existence of a pyproject.toml both meaning "Python" — record it
    twice. The comparison deduplicates, so nothing is visibly wrong, which is
    why it survived: the only symptom is that the finding's line number points
    at whichever path happened to run first.
    """
    path = tmp_path / adapter.filenames[0]
    path.write_text(RICH_FIXTURES[adapter.id], encoding="utf-8")
    concepts = adapter.map_to_codemeta(adapter.parse(path, adapter.filenames[0]))
    for concept, values in concepts.items():
        seen = [repr(value.raw) for value in values]
        duplicates = {item for item in seen if seen.count(item) > 1}
        assert not duplicates, (
            f"{adapter.id} records {sorted(duplicates)} more than once for {concept}"
        )


def test_every_upstream_correspondence_is_mapped_or_declared_omitted():
    """A crosswalk CodeMeta publishes may not be silently ignored.

    CodeMeta maintains a crosswalk table per ecosystem. Where one exists,
    every record-level property in it must either have a rule in the mapping,
    or be listed under `upstream.omitted` with a reason.

    "Record-level" means a property CodeMeta places on the software itself
    rather than inside an agent: `citation` belongs to the record, `givenName`
    belongs to a Person nested in it. The vocabulary already says which is
    which, so the line is read from there rather than drawn by hand.

    This deliberately does *not* stop at the twenty-five properties the
    profile speaks to. A crosswalk upstream has already worked out is worth
    honoring whether or not this profile happens to require the field —
    `softwareSuggestions`, `citation` and `processorRequirements` are all real
    correspondences that were being silently dropped for that reason.
    """
    import yaml

    from rs_metadata.vocabulary import codemeta_crosswalks, codemeta_types

    tracked = {name for name, entry in codemeta_types().items() if entry.get("parent")}
    for mapping_id, table in codemeta_crosswalks().items():
        path = MAPPINGS / f"{mapping_id}.yaml"
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
        mapped = {field["property"] for field in document.get("fields", [])}
        omitted = set(document.get("upstream", {}).get("omitted", {}))
        unaccounted = (set(table["properties"]) & tracked) - mapped - omitted
        assert not unaccounted, (
            f"{mapping_id} ignores {sorted(unaccounted)}, which CodeMeta's own "
            f"crosswalk maps. Add a rule, or declare it under "
            f"`upstream.omitted` with the reason."
        )


def test_declared_omissions_are_actually_in_the_upstream_crosswalk():
    """An `upstream.omitted` entry for something upstream never mapped is noise."""
    import yaml

    from rs_metadata.vocabulary import codemeta_crosswalks

    crosswalks = codemeta_crosswalks()
    for path in sorted(MAPPINGS.glob("*.yaml")):
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
        omitted = set(document.get("upstream", {}).get("omitted", {}))
        if not omitted:
            continue
        upstream = set(crosswalks.get(document["id"], {}).get("properties", {}))
        assert omitted <= upstream, (
            f"{document['id']} declares {sorted(omitted - upstream)} omitted "
            f"from the upstream crosswalk, but upstream does not map it."
        )


def test_a_mapping_claiming_no_upstream_really_has_none():
    """`origin: rs-metadata` asserts CodeMeta publishes no crosswalk for it."""
    import yaml

    from rs_metadata.mapping import Origin
    from rs_metadata.vocabulary import codemeta_crosswalks

    crosswalks = codemeta_crosswalks()
    for path in sorted(MAPPINGS.glob("*.yaml")):
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
        origin = Origin(document["provenance"]["origin"])
        if origin is not Origin.RS_METADATA:
            continue
        assert document["id"] not in crosswalks, (
            f"{document['id']} claims origin `rs-metadata`, but CodeMeta "
            f"publishes a crosswalk for it. Set `origin: mixed` and follow it."
        )


def test_catalog_severity_is_the_ceiling_actually_emitted():
    """The severity `explain` prints must be the worst a code is reported at.

    A few codes vary with how certain the check can be. Documenting a severity
    lower than one actually emitted would understate a real failure; higher
    would overstate every other case.
    """
    import re
    from pathlib import Path

    from rs_metadata.diagnostics import CATALOG, Severity

    rank = {Severity.INFO: 0, Severity.WARNING: 1, Severity.ERROR: 2}
    emitted: dict[str, set[Severity]] = {}
    pattern = re.compile(
        r'"((?:profile|consistency|recommendation|source)\.[a-z-]+)",\s*\n?\s*'
        r"Severity\.(\w+)"
    )
    root = Path(__file__).resolve().parents[2] / "src"
    for path in root.rglob("*.py"):
        for code, level in pattern.findall(path.read_text(encoding="utf-8")):
            emitted.setdefault(code, set()).add(Severity[level])

    for code, levels in sorted(emitted.items()):
        declared = CATALOG[code].severity
        worst = max(levels, key=lambda level: rank[level])
        assert declared == worst, (
            f"{code} is emitted at {sorted(x.value for x in levels)} but the "
            f"catalog declares {declared.value}"
        )


def test_vendored_and_project_owned_data_are_disjoint():
    """The vendoring script must never overwrite a hand-maintained file.

    Both kinds live in ``data/`` because both are read the same way, but only
    one has an upstream. If a project-owned name ever appeared in the script's
    output list, a hand-written rule would be silently replaced on the next
    refresh.
    """
    import ast
    from pathlib import Path

    from rs_metadata.vocabulary import PROJECT_OWNED_DATA

    package = Path(__file__).resolve().parents[2] / "scripts" / "vendoring"
    written = {
        node.value
        for module in package.glob("*.py")
        for node in ast.walk(ast.parse(module.read_text(encoding="utf-8")))
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and node.value.endswith((".json", ".jsonld"))
    }
    collisions = written & set(PROJECT_OWNED_DATA)
    assert not collisions, f"vendoring script would overwrite {sorted(collisions)}"


def test_every_project_owned_data_file_exists_and_loads():
    from importlib import resources

    from rs_metadata.vocabulary import PROJECT_OWNED_DATA

    for name in PROJECT_OWNED_DATA:
        text = resources.files("rs_metadata.data").joinpath(name).read_text("utf-8")
        payload = json.loads(text)
        assert payload.get("$comment"), f"{name} must say it is maintained by hand"


def test_the_schema_matches_the_profile_definition():
    """The published schema is generated; a hand edit to it would be lost.

    Regenerating has to be a no-op, or the JSON in the repository says
    something the profile does not.
    """
    import importlib.util
    import json
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    spec = importlib.util.spec_from_file_location(
        "build_schema", root / "scripts" / "build_schema.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    generated = module.build(module.load_profile())
    published = json.loads(module.SCHEMA_PATH.read_text(encoding="utf-8"))
    assert generated == published, (
        "codemeta-lumc.schema.json does not match profile/lumc-codemeta.yaml. "
        "Run: poetry run python scripts/build_schema.py"
    )


def test_every_profile_field_exists_in_a_vocabulary():
    """A typo in the profile definition must fail loudly, not silently drop."""
    import importlib.util
    from pathlib import Path

    from rs_metadata.vocabulary import type_entry

    root = Path(__file__).resolve().parents[2]
    spec = importlib.util.spec_from_file_location(
        "build_schema", root / "scripts" / "build_schema.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    profile = module.load_profile()
    for name in {**profile["required"], **profile["recommended"]}:
        assert type_entry(name) is not None, (
            f"{name} is named in the profile but defined by neither CodeMeta "
            f"nor schema.org"
        )


def test_schema_org_supplies_the_class_hierarchy():
    """Subtype checking depends on the vendored hierarchy being present."""
    from rs_metadata.vocabulary import satisfies, schema_org_classes

    classes = schema_org_classes()
    assert classes["ScholarlyArticle"]["ancestors"][:3] == [
        "Article",
        "CreativeWork",
        "Thing",
    ]
    assert satisfies("ScholarlyArticle", "CreativeWork")
    assert not satisfies("CreativeWork", "ScholarlyArticle")


def test_codemeta_own_terms_are_never_typed_from_schema_org():
    """A shared name is not a shared property.

    Twelve CodeMeta terms expand to CodeMeta's own IRIs, and schema.org
    defines properties called ``maintainer`` and ``funding`` too. Matching on
    name would merge two unrelated properties and widen a range CodeMeta
    deliberately narrowed, so the vendoring script matches on the IRI the
    context expands a term to. This pins that.
    """
    from rs_metadata.vocabulary.properties import codemeta_terms, codemeta_types

    terms = codemeta_terms()["terms"]
    borrowed_from_schema_org = {
        name
        for name, entry in terms.items()
        if str(entry.get("id", "")).startswith("schema:")
    }
    leaked = {
        name
        for name, entry in codemeta_types().items()
        if name in terms
        and name not in borrowed_from_schema_org
        and entry.get("source") != "codemeta"
    }
    assert not leaked, f"schema.org typed CodeMeta's own {sorted(leaked)}"


def test_every_codemeta_term_records_the_iri_it_expands_to():
    """Types carry the IRI, so the name-to-name assumption stays checkable."""
    from rs_metadata.vocabulary.properties import codemeta_terms, codemeta_types

    properties = codemeta_types()
    for name, entry in codemeta_terms()["terms"].items():
        assert properties[name].get("id") == entry["id"], name


def test_class_definitions_are_generated_not_written():
    """A $defs entry naming a class must come from the vocabulary.

    The whole point is that no class shape is maintained by hand, so each one
    has to carry the generator's marker and accept its subclasses.
    """
    from rs_metadata.vocabulary import profile_schema, schema_org_classes, subclasses

    classes = set(schema_org_classes())
    for name, definition in profile_schema()["$defs"].items():
        accepted = definition.get("properties", {}).get("@type", {}).get("enum")
        if accepted is None:
            # A structural definition: non-empty text, an IRI, a date, a
            # number. Some share a name with a schema.org datatype, which is
            # not the same as describing a node class.
            assert name not in classes or not definition.get("properties"), (
                f"$defs/{name} looks like a class definition but declares no @type"
            )
            continue
        assert "Generated by" in definition.get("$comment", ""), (
            f"$defs/{name} describes a class but is not generated"
        )
        assert accepted == [name, *subclasses(name)], (
            f"$defs/{name} does not accept exactly its own subclasses"
        )


def test_every_reachable_class_has_a_definition():
    """A class a profile field can hold must be described, not fall through."""
    from rs_metadata.vocabulary import (
        LITERAL_TYPES,
        profile_schema,
        schema_org_classes,
        type_entry,
    )

    schema = profile_schema()
    policy = schema["x-lumc-profile"]
    classes = set(schema_org_classes())
    scalars = LITERAL_TYPES | {"URL"}
    defined = set(schema["$defs"])
    for name in [*policy["mandatory"], *policy["recommended"]]:
        entry = type_entry(name)
        assert entry is not None
        for target in entry["range"]:
            if target in classes and target not in scalars:
                assert target in defined, f"{name} can hold a {target} with no $defs"
