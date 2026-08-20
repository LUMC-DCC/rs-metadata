"""Adapter for a GitHub repository's own metadata.

GitHub keeps a description, a homepage, topics and a detected license on the
repository itself, and those are what a visitor reads first — long before they
open codemeta.json. They drift from the repository's metadata files the same
way any other copy does, and until now nothing checked them.

This is the one source that is not a file the project maintains, which raises
the obvious question of how it gets here without the validator reaching the
network. It never does. GitHub Actions writes the whole event payload to a
local file and points ``GITHUB_EVENT_PATH`` at it, and that payload's
``repository`` object is exactly the REST API's representation. Running inside
Actions, the data is already on disk. Running anywhere else, a maintainer can
dump it themselves::

    gh api repos/OWNER/REPO > github-repo.json
    rs-metadata validate . --source github=github-repo.json

Either shape is accepted: the bare repository object as the API returns it, or
an event payload with the object under ``repository``.

Nothing is read from a fork. A fork has its own URL, and a description and
topics copied at the moment it was made, while its codemeta.json still
describes the upstream software — so every field would disagree and every
fork's CI would fail on metadata that is not wrong.
"""

from __future__ import annotations

import datetime as dt
import json
import os
from pathlib import Path
from typing import Any

from ..concepts import ConceptMap, ParsedSource, add, add_each
from ..locate import json_source_map
from .base import Adapter, SourceError

#: What GitHub reports when its license detector recognized no license, or
#: recognized one it cannot name. Comparing it against anything would be a
#: false alarm about a repository that may well have a perfectly good license.
UNDETERMINED_LICENSE = frozenset({"NOASSERTION", "NONE", ""})


def _timestamp(value: Any) -> Any:
    """Normalize GitHub's two spellings of a timestamp to an ISO 8601 string.

    The REST API returns ISO strings, but a webhook payload — which is what
    the Actions event file contains — serializes `created_at` as seconds since
    the epoch while leaving `updated_at` a string. Reporting the raw number
    would show a reader `1786665985` and invite them to "fix" it.

    Examples
    --------
    >>> _timestamp("2026-08-14T00:06:33Z")
    '2026-08-14T00:06:33Z'
    >>> _timestamp(1786665985)
    '2026-08-14T00:06:25Z'
    >>> _timestamp(None) is None
    True
    """
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        moment = dt.datetime.fromtimestamp(value, tz=dt.UTC)
        return moment.strftime("%Y-%m-%dT%H:%M:%SZ")
    return value


class GitHubAdapter(Adapter):
    id = "github"
    format = "GitHub repository metadata"
    role = "optional"
    filenames = ("github-repo.json",)
    mapping_name = "github"

    def detect(self, root: Path) -> Path | None:
        """Find a dumped repository object, or the payload Actions provides.

        A file in the repository root wins, so a maintainer who commits or
        generates one keeps control. Otherwise, inside GitHub Actions, the
        event payload is already on disk and carries the same object.

        The payload is used **only when the directory being validated is the
        checked-out repository itself**. The runner sets ``GITHUB_EVENT_PATH``
        for every step regardless of what that step is looking at, so without
        this check, validating ``examples/complete`` would compare that
        example against the repository it happens to live in — and report a
        difference on every field, about metadata that is entirely correct.
        """
        path = super().detect(root)
        if path is not None:
            return path
        event = os.environ.get("GITHUB_EVENT_PATH")
        workspace = os.environ.get("GITHUB_WORKSPACE")
        if not event or not workspace:
            return None
        try:
            if root.resolve() != Path(workspace).resolve():
                return None
        except OSError:  # pragma: no cover - unresolvable path
            return None
        candidate = Path(event)
        return candidate if candidate.is_file() else None

    def parse(self, path: Path, relative: str) -> ParsedSource:
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as error:
            raise SourceError(f"{relative} could not be read: {error}") from error
        try:
            document = json.loads(text)
        except json.JSONDecodeError as error:
            raise SourceError(
                f"{relative} is not valid JSON: {error.msg}", line=error.lineno
            ) from error
        if not isinstance(document, dict):
            raise SourceError(f"{relative} must contain a JSON object.")

        repository = document.get("repository")
        if isinstance(repository, dict):
            # An Actions event payload wraps the object we want.
            document, relative = repository, "GitHub repository"
        elif "full_name" not in document:
            raise SourceError(
                f"{relative} does not look like a GitHub repository object. "
                f"Expected the output of `gh api repos/OWNER/REPO`, or an "
                f"Actions event payload with a `repository` key."
            )

        return ParsedSource(
            adapter_id=self.id,
            file=relative,
            format=self.format,
            document=document,
            source_map=json_source_map(text),
        )

    def map_to_codemeta(self, parsed: ParsedSource) -> ConceptMap:
        document: dict[str, Any] = parsed.document
        concepts: ConceptMap = {}

        if document.get("fork"):
            # A fork carries its own URL, and a description and topics copied
            # at fork time, while its codemeta.json still describes the
            # upstream software. Every field here would disagree, so a fork's
            # CI would fail on metadata that is not wrong. Nothing is read.
            return concepts

        # `name`, not `full_name`: upstream maps the latter, but that is
        # `owner/repo`, which never equals the software's name.
        add(concepts, "name", document.get("name"), ("name",))
        add(concepts, "description", document.get("description"), ("description",))
        add(concepts, "codeRepository", document.get("html_url"), ("html_url",))
        add(concepts, "url", document.get("homepage"), ("homepage",))
        add_each(concepts, "keywords", document.get("topics"), ("topics",))
        # `language` is the language GitHub detected. Upstream maps
        # `languages_url`, which is an endpoint rather than a value.
        add(concepts, "programmingLanguage", document.get("language"), ("language",))
        add(
            concepts,
            "dateCreated",
            _timestamp(document.get("created_at")),
            ("created_at",),
        )
        add(
            concepts,
            "dateModified",
            _timestamp(document.get("updated_at")),
            ("updated_at",),
        )
        self._add_license(concepts, document.get("license"))
        self._add_issue_tracker(concepts, document)
        return concepts

    def _add_license(self, concepts: ConceptMap, license_: Any) -> None:
        if not isinstance(license_, dict):
            return
        spdx = license_.get("spdx_id")
        if isinstance(spdx, str) and spdx.upper() not in UNDETERMINED_LICENSE:
            add(concepts, "license", spdx, ("license", "spdx_id"))

    def _add_issue_tracker(
        self, concepts: ConceptMap, document: dict[str, Any]
    ) -> None:
        """Derive the tracker URL, which the API gives only as a template.

        `issues_url` is `.../issues{/number}`, an API template rather than the
        page a maintainer would put in codemeta.json. The real tracker is the
        repository URL plus `/issues`, and only when issues are enabled.
        """
        html_url = document.get("html_url")
        if document.get("has_issues") and isinstance(html_url, str):
            add(concepts, "issueTracker", f"{html_url}/issues", ("has_issues",))
