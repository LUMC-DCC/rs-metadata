"""Everything that carries a version must carry the same one.

``rs_metadata.__version__`` is read from the installed distribution and the
profile constants are read from the generated schema, so none of them can
drift from their source by being edited. What can still drift is the set of
files a human edits by hand — ``pyproject.toml``, ``CITATION.cff``,
``codemeta.json``, ``profile/lumc-codemeta.yaml`` — and that is what these
check.
"""

from __future__ import annotations

import json
import tomllib
from pathlib import Path
from typing import Any

import pytest
import yaml

from rs_metadata import (
    CODEMETA_VERSION,
    PROFILE_NAME,
    PROFILE_VERSION,
    __version__,
)
from rs_metadata.vocabulary import codemeta_versions, profile_schema

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def pyproject() -> dict[str, Any]:
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    return dict(tomllib.loads(text))


def test_tool_version_matches_pyproject(pyproject):
    """The installed distribution must be built from the current pyproject.

    ``__version__`` comes from the installed package metadata rather than a
    literal, so this fails when the working tree has been bumped but not
    reinstalled — which is exactly when a locally built report would claim the
    wrong version.
    """
    assert __version__ == pyproject["project"]["version"]


def test_profile_constants_come_from_the_profile_definition():
    """The schema carries the profile's identity; the YAML is what defines it."""
    profile = yaml.safe_load(
        (ROOT / "profile" / "lumc-codemeta.yaml").read_text(encoding="utf-8")
    )
    assert profile["name"] == PROFILE_NAME
    assert str(profile["version"]) == PROFILE_VERSION


def test_no_version_is_written_out_by_hand_in_the_package():
    """A literal version in the package would be a second place to bump.

    Every version the package exposes is read from an artifact that already
    declares it. This pins that, because re-adding a constant is easy and the
    resulting drift is silent.
    """
    import re

    source = (ROOT / "src" / "rs_metadata" / "__init__.py").read_text("utf-8")
    literals = re.findall(
        r'^\s*(?:__version__|[A-Z_]+)\s*(?::\s*str\s*)?=\s*"', source, re.MULTILINE
    )
    assert not literals, "a version constant is written out instead of derived"


def test_citation_file_version_matches(pyproject):
    """CITATION.cff is what Zenodo reads, so a stale version there is published."""
    cff = yaml.safe_load((ROOT / "CITATION.cff").read_text(encoding="utf-8"))
    assert cff["version"] == __version__


def test_codemeta_record_version_matches(pyproject):
    """The project's own codemeta.json is validated by its own CI."""
    record = json.loads((ROOT / "codemeta.json").read_text(encoding="utf-8"))
    assert record["version"] == __version__


def test_profile_schema_declares_the_profile_version():
    """The schema is publishable on its own, so it carries its own version."""
    schema = profile_schema()
    assert schema["title"] == PROFILE_NAME
    declared = schema["x-lumc-profile"]
    assert declared["profileVersion"] == PROFILE_VERSION
    assert declared["codemetaVersion"] == CODEMETA_VERSION


def test_codemeta_version_matches_the_vendored_data():
    """The constant and the vendored context must describe the same vocabulary."""
    assert codemeta_versions()["codemetaVersion"] == CODEMETA_VERSION
