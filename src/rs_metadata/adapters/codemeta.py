"""The anchor adapter: ``codemeta.json``.

codemeta.json is the canonical record. It is the only source validated against
the LUMC profile, and every other metadata file in the repository is compared
against it rather than against the others. That keeps the number of
comparators linear in the number of supported formats.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

from ..concepts import ConceptMap, ParsedSource, add_each
from ..locate import json_source_map
from ..vocabulary import codemeta_versions
from .base import Adapter, SourceError

#: Spellings of ``featureList`` rs-metadata treats as the LUMC-profile
#: property. CodeMeta 3.1 does not define ``featureList``, so it is written
#: with an explicit ``schema:`` prefix; the absolute IRI forms mean the same
#: thing after JSON-LD expansion and are accepted.
FEATURE_LIST = "schema:featureList"
FEATURE_LIST_ALIASES = (
    "http://schema.org/featureList",
    "https://schema.org/featureList",
)


def _context_versions() -> dict[str, str]:
    """Recognized ``@context`` values, from the vendored version table."""
    return cast(dict[str, str], codemeta_versions()["contexts"])


def context_entries(document: Any) -> list[Any]:
    """The ``@context`` value as a list, whatever shape it was written in."""
    context = document.get("@context") if isinstance(document, dict) else None
    if context is None:
        return []
    return context if isinstance(context, list) else [context]


def declared_codemeta_version(document: Any) -> str | None:
    """Which CodeMeta version the document's context declares, if recognizable.

    Parameters
    ----------
    document : Any
        A parsed CodeMeta record.

    Returns
    -------
    str or None
        The version, or ``None`` when no recognized CodeMeta context is
        referenced — which means the file is not a CodeMeta record at all.

    Examples
    --------
    >>> declared_codemeta_version({"@context": "https://w3id.org/codemeta/3.1"})
    '3.1'

    The context is usually an array, with an inline object alongside it:

    >>> declared_codemeta_version({"@context": [
    ...     "https://w3id.org/codemeta/3.1",
    ...     {"schema": "https://schema.org/"},
    ... ]})
    '3.1'

    Anything that is not a CodeMeta 3.x context is unrecognized, earlier
    CodeMeta included:

    >>> declared_codemeta_version(
    ...     {"@context": "https://doi.org/10.5063/schema/codemeta-2.0"}
    ... ) is None
    True

    >>> declared_codemeta_version({"@context": "https://example.org/x"}) is None
    True
    >>> declared_codemeta_version({}) is None
    True
    """
    versions = _context_versions()
    for entry in context_entries(document):
        if isinstance(entry, str):
            version = versions.get(entry.rstrip("/"))
            if version:
                return version
    return None


#: The spelling CodeMeta 3.1 does not define. Accepted nowhere, but recognized
#: so its contents can still be checked and one clear diagnostic issued.
BARE_FEATURE_LIST = "featureList"


def feature_list_key(document: dict[str, Any]) -> str | None:
    """Which *valid* spelling of ``featureList`` this document uses, if any.

    Parameters
    ----------
    document : dict
        A parsed CodeMeta record.

    Returns
    -------
    str or None
        The key in use, or ``None`` if the property is absent or spelled in a
        way JSON-LD would discard.

    Examples
    --------
    >>> feature_list_key({"schema:featureList": ["x"]})
    'schema:featureList'
    >>> feature_list_key({"https://schema.org/featureList": ["x"]})
    'https://schema.org/featureList'

    The bare spelling is deliberately not returned here: it is not a valid
    way to record operations, and treating it as one would hide the problem.

    >>> feature_list_key({"featureList": ["x"]}) is None
    True
    """
    for candidate in (FEATURE_LIST, *FEATURE_LIST_ALIASES):
        if candidate in document:
            return candidate
    return None


def any_feature_list_key(document: dict[str, Any]) -> str | None:
    """Which spelling this document uses, including the invalid bare one.

    Used by the value-level checks so that renaming the property does not
    reveal a second round of problems that could have been reported at the
    same time.

    Parameters
    ----------
    document : dict
        A parsed CodeMeta record.

    Returns
    -------
    str or None
        The key in use, or ``None`` if the property is absent entirely.

    Examples
    --------
    >>> any_feature_list_key({"schema:featureList": ["x"]})
    'schema:featureList'
    >>> any_feature_list_key({"featureList": ["x"]})
    'featureList'
    >>> any_feature_list_key({}) is None
    True
    """
    return feature_list_key(document) or (
        BARE_FEATURE_LIST if BARE_FEATURE_LIST in document else None
    )


class CodeMetaAdapter(Adapter):
    id = "codemeta"
    format = "CodeMeta"
    role = "anchor"
    filenames = ("codemeta.json",)
    mapping_name = None

    def parse(self, path: Path, relative: str) -> ParsedSource:
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as error:
            raise SourceError(f"{relative} could not be read: {error}") from error
        try:
            document = json.loads(text)
        except json.JSONDecodeError as error:
            raise SourceError(
                f"{relative} is not valid JSON: {error.msg} "
                f"(line {error.lineno}, column {error.colno}).",
                line=error.lineno,
            ) from error
        if not isinstance(document, dict):
            raise SourceError(
                f"{relative} must contain a JSON object describing one piece of "
                f"software, but its top level is a "
                f"{type(document).__name__.replace('NoneType', 'null')}."
            )
        return ParsedSource(
            adapter_id=self.id,
            file=relative,
            format=self.format,
            format_version=declared_codemeta_version(document),
            document=document,
            source_map=json_source_map(text),
        )

    def map_to_codemeta(self, parsed: ParsedSource) -> ConceptMap:
        """Identity mapping: the anchor is already expressed in CodeMeta.

        The only translation is folding the accepted ``featureList`` spellings
        onto one concept name so a document using an absolute IRI compares the
        same as one using the prefixed form.
        """
        document: dict[str, Any] = parsed.document
        concepts: ConceptMap = {}
        for key, value in document.items():
            if key.startswith("@"):
                continue
            concept = FEATURE_LIST if key in FEATURE_LIST_ALIASES else key
            add_each(concepts, concept, value, (key,))
        return concepts
