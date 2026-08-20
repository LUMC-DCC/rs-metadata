"""``rs-metadata init`` creates what is missing and never touches what is not."""

from __future__ import annotations

import json

from rs_metadata.cli import EXIT_OK, main
from rs_metadata.scaffold import plan, write


def test_creates_all_three_files_in_an_empty_repository(tmp_path):
    written = write(tmp_path, plan(tmp_path))
    assert sorted(written) == [
        ".github/workflows/metadata.yml",
        "CITATION.cff",
        "codemeta.json",
    ]
    assert (tmp_path / ".github" / "workflows" / "metadata.yml").is_file()


def test_never_overwrites_an_existing_file(tmp_path):
    (tmp_path / "codemeta.json").write_text('{"name": "mine"}', encoding="utf-8")
    proposed = plan(tmp_path)
    assert "codemeta.json" in proposed.existing
    assert "codemeta.json" not in proposed.create
    write(tmp_path, proposed)
    assert (
        json.loads((tmp_path / "codemeta.json").read_text(encoding="utf-8"))["name"]
        == "mine"
    )


def test_prefills_from_existing_packaging_metadata(tmp_path):
    (tmp_path / "pyproject.toml").write_text(
        "[project]\n"
        'name = "coolthing"\n'
        'version = "2.4.1"\n'
        'description = "Aligns reads."\n'
        'license = "MIT"\n',
        encoding="utf-8",
    )
    write(tmp_path, plan(tmp_path))
    record = json.loads((tmp_path / "codemeta.json").read_text(encoding="utf-8"))
    assert record["name"] == "coolthing"
    assert record["version"] == "2.4.1"
    assert record["description"] == "Aligns reads."
    assert record["license"] == "https://spdx.org/licenses/MIT"


def test_the_generated_record_only_fails_on_placeholders(tmp_path):
    """init then validate should name exactly the fields a person must supply."""
    from rs_metadata.core import Options
    from rs_metadata.core import validate as run

    (tmp_path / "pyproject.toml").write_text(
        "[project]\n"
        'name = "coolthing"\n'
        'version = "2.4.1"\n'
        'description = "Aligns reads."\n'
        'license = "MIT"\n',
        encoding="utf-8",
    )
    write(tmp_path, plan(tmp_path))
    report = run(Options(root=tmp_path))
    codes = {d.code for d in report.errors}
    assert codes == {"profile.placeholder-value"}, (
        "a freshly scaffolded repository should fail only on the values a "
        f"person still has to provide, not on {sorted(codes)}"
    )


def test_dry_run_writes_nothing(tmp_path, capsys):
    assert main(["init", str(tmp_path), "--dry-run"]) == EXIT_OK
    assert "would create" in capsys.readouterr().out
    assert not (tmp_path / "codemeta.json").exists()


def test_rerunning_init_is_a_no_op(tmp_path, capsys):
    main(["init", str(tmp_path)])
    capsys.readouterr()
    assert main(["init", str(tmp_path)]) == EXIT_OK
    assert "already in place" in capsys.readouterr().out


def test_the_generated_workflow_is_valid_yaml(tmp_path):
    import yaml

    write(tmp_path, plan(tmp_path))
    workflow = yaml.safe_load(
        (tmp_path / ".github" / "workflows" / "metadata.yml").read_text("utf-8")
    )
    assert workflow["jobs"]["metadata"]["steps"][-1]["uses"].startswith("LUMC-DCC/")


def test_the_generated_citation_is_valid_cff(tmp_path):
    from rs_metadata.adapters import get_adapter

    write(tmp_path, plan(tmp_path))
    adapter = get_adapter("cff")
    parsed = adapter.parse(tmp_path / "CITATION.cff", "CITATION.cff")
    assert adapter.validate_source(parsed) == []
