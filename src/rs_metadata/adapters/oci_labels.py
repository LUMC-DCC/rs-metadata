"""Adapter for the OCI image labels in a ``Dockerfile`` or ``Containerfile``.

A Dockerfile is a build script, not a metadata file, and most of it says
nothing about the software. The exception is the ``org.opencontainers.image.*``
label set, which the OCI image specification defines precisely and which ends
up baked into every published image. When those labels disagree with
codemeta.json, the image on a registry is describing the software differently
from the repository.

The module is named for the labels rather than for the file because it reads
one specific vocabulary out of a build script, handles ``Containerfile`` just
as well, and because a Python module called ``dockerfile.py`` invites editors
to treat it as a Dockerfile.

Two things are deliberately not read. A label whose value still contains a
``$`` is left alone, because it interpolates a build argument that this file
does not determine — reporting ``${VERSION}`` as a version mismatch would be a
false alarm about a correct Dockerfile. And in a multi-stage build only the
final stage's labels are kept, since those are the ones on the image that
actually ships.
"""

from __future__ import annotations

import re
import shlex
from pathlib import Path
from typing import Any

from ..concepts import ConceptMap, ParsedSource, add, add_each
from ..locate import SourceMap
from .base import Adapter, SourceError

#: The OCI annotation keys with a CodeMeta equivalent, from the image
#: specification's ``annotations.md``. Keys the spec defines that describe the
#: image build rather than the software — ``created``, ``revision``,
#: ``ref.name``, ``base.name``, ``base.digest`` — are not mapped.
OCI_CONCEPTS = {
    "org.opencontainers.image.title": "name",
    "org.opencontainers.image.description": "description",
    "org.opencontainers.image.version": "version",
    "org.opencontainers.image.licenses": "license",
    "org.opencontainers.image.source": "codeRepository",
    "org.opencontainers.image.url": "url",
    "org.opencontainers.image.documentation": "softwareHelp",
    "org.opencontainers.image.authors": "author",
    "org.opencontainers.image.vendor": "copyrightHolder",
}

_CONTINUED = re.compile(r"\\\s*$")


class DockerfileAdapter(Adapter):
    id = "dockerfile"
    format = "Dockerfile (OCI image labels)"
    role = "optional"
    filenames = ("Dockerfile", "Containerfile")
    mapping_name = "dockerfile-oci"

    def parse(self, path: Path, relative: str) -> ParsedSource:
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as error:
            raise SourceError(f"{relative} could not be read: {error}") from error
        labels = parse_labels(text)
        return ParsedSource(
            adapter_id=self.id,
            file=relative,
            format=self.format,
            document=labels,
            source_map=SourceMap(_label_positions(text, labels)),
        )

    def map_to_codemeta(self, parsed: ParsedSource) -> ConceptMap:
        labels: dict[str, str] = parsed.document
        concepts: ConceptMap = {}
        for key, value in labels.items():
            concept = OCI_CONCEPTS.get(key)
            if concept is None:
                continue
            if concept == "author":
                # The spec writes authors as "contact details", commonly a
                # comma-separated list of `Name <email>`.
                add_each(concepts, concept, _split_authors(value), (key,))
            else:
                add(concepts, concept, value, (key,))
        return concepts


def _split_authors(value: str) -> list[str]:
    """Split an `image.authors` value into individual contacts.

    Examples
    --------
    >>> _split_authors("Jane Doe <jane@example.org>, John Roe <john@example.org>")
    ['Jane Doe <jane@example.org>', 'John Roe <john@example.org>']
    """
    return [part.strip() for part in value.split(",") if part.strip()]


def parse_labels(text: str) -> dict[str, str]:
    """Extract the final stage's literal ``LABEL`` values from a Dockerfile.

    Examples
    --------
    >>> parse_labels('FROM x\\nLABEL org.opencontainers.image.title="Tool"')
    {'org.opencontainers.image.title': 'Tool'}

    One instruction may set several labels, and values may be quoted:

    >>> sorted(parse_labels('LABEL a="one" b="two words"').items())
    [('a', 'one'), ('b', 'two words')]

    A value that interpolates a build argument is not a value this file
    states, so it is skipped:

    >>> parse_labels('LABEL org.opencontainers.image.version="${VERSION}"')
    {}

    Only the last build stage ships, so an earlier stage's labels are dropped:

    >>> parse_labels('FROM x AS build\\nLABEL a="1"\\nFROM y\\nLABEL b="2"')
    {'b': '2'}
    """
    labels: dict[str, str] = {}
    for instruction, argument in _instructions(text):
        if instruction == "FROM":
            # A new stage starts; only the final one ends up in the image.
            labels.clear()
        elif instruction == "LABEL":
            labels.update(_parse_label_argument(argument))
    return labels


def _instructions(text: str) -> list[tuple[str, str]]:
    """Dockerfile instructions, with line continuations joined."""
    out: list[tuple[str, str]] = []
    buffer = ""
    for raw in text.splitlines():
        line = raw.strip()
        if not buffer and (not line or line.startswith("#")):
            continue
        if _CONTINUED.search(line):
            buffer += _CONTINUED.sub(" ", line)
            continue
        joined = (buffer + line).strip()
        buffer = ""
        head, _, rest = joined.partition(" ")
        if head:
            out.append((head.upper(), rest.strip()))
    if buffer.strip():
        head, _, rest = buffer.strip().partition(" ")
        out.append((head.upper(), rest.strip()))
    return out


def _parse_label_argument(argument: str) -> dict[str, str]:
    """Parse one LABEL instruction's ``key=value`` pairs."""
    try:
        tokens = shlex.split(argument)
    except ValueError:
        return {}
    labels: dict[str, str] = {}
    for token in tokens:
        key, sep, value = token.partition("=")
        if not sep or not key.strip():
            continue
        # `$` means a build argument decides this value, not the file.
        if "$" in value:
            continue
        stripped = value.strip()
        if stripped:
            labels[key.strip()] = stripped
    return labels


def _label_positions(
    text: str, labels: dict[str, str]
) -> dict[tuple[Any, ...], tuple[int, int]]:
    """Locate each label by the line its LABEL instruction appears on."""
    positions: dict[tuple[Any, ...], tuple[int, int]] = {}
    for number, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line.upper().startswith("LABEL"):
            continue
        for key in labels:
            if key in line:
                positions[(key,)] = (number, raw.index(key.split("=")[0]) + 1)
    return positions
