"""The catalog of stable diagnostic codes.

Every finding rs-metadata reports carries a code from this module. The codes
are a public interface: they appear in the JSON report, in CI annotations and
in documentation links, and downstream tooling is expected to filter on them.
Within a major version a code never changes meaning. Retiring a code is a
breaking change; adding one is not.

Codes are namespaced by the layer that produced them, which tells a reader
immediately where to look:

``profile.*``
    The anchor record does not satisfy the LUMC profile.
``recommendation.*``
    The record is valid but could be more useful to registries and archives.
``source.*``
    A metadata file could not be found, read, or validated against its own
    format's schema.
``consistency.*``
    Two metadata files describe the same concept differently.
``internal.*``
    rs-metadata itself failed. Always a bug report.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

DOCS_URL = "https://github.com/LUMC-DCC/rs-metadata/blob/main/docs/using/diagnostics.md"


class Severity(StrEnum):
    """How much a finding matters.

    Severity is a property of the finding, not a policy decision. Whether a
    warning fails a build is decided separately by ``--fail-on``, so the same
    report can drive a strict institutional gate and a lenient local check.
    """

    ERROR = "error"
    WARNING = "warning"
    INFO = "info"

    @property
    def meaning(self) -> str:
        """What this severity tells a reader, for documentation and help text.

        Examples
        --------
        >>> Severity.ERROR.meaning
        'The metadata is wrong. Fails the build by default.'
        """
        return {
            Severity.ERROR: "The metadata is wrong. Fails the build by default.",
            Severity.WARNING: (
                "The metadata works but should be improved. Non-fatal unless "
                "`--fail-on warning`."
            ),
            Severity.INFO: (
                "Context: something was noticed, or deliberately not checked. "
                "Never fatal."
            ),
        }[self]

    @property
    def rank(self) -> int:
        """Sort key placing the most severe findings first.

        Returns
        -------
        int
            ``0`` for errors, ``1`` for warnings, ``2`` for information.

        Examples
        --------
        >>> [s.value for s in sorted(Severity, key=lambda s: s.rank)]
        ['error', 'warning', 'info']
        """
        return {"error": 0, "warning": 1, "info": 2}[self.value]


class Namespace(StrEnum):
    """The layer a diagnostic code came from.

    Every code is ``<namespace>.<name>``, and the namespace tells a reader
    immediately where to look. Kept here rather than in the documentation
    generator so the prose and the codes cannot describe different sets.
    """

    PROFILE = "profile"
    RECOMMENDATION = "recommendation"
    SOURCE = "source"
    CONSISTENCY = "consistency"
    INTERNAL = "internal"

    @property
    def heading(self) -> str:
        """Heading for this namespace's section of the reference.

        Examples
        --------
        >>> Namespace.PROFILE.heading
        'Profile'
        """
        return {
            Namespace.PROFILE: "Profile",
            Namespace.RECOMMENDATION: "Recommendations",
            Namespace.SOURCE: "Sources",
            Namespace.CONSISTENCY: "Consistency",
            Namespace.INTERNAL: "Internal",
        }[self]

    @property
    def description(self) -> str:
        """What the codes in this namespace have in common.

        Examples
        --------
        >>> Namespace.CONSISTENCY.description
        'Two metadata files describe the same concept differently.'
        """
        return {
            Namespace.PROFILE: ("The anchor record does not satisfy the LUMC profile."),
            Namespace.RECOMMENDATION: (
                "The record is valid, but could be more useful to registries "
                "and archives. Recommendations never fail a build by default."
            ),
            Namespace.SOURCE: (
                "A metadata file could not be found, read, or validated "
                "against its own format's specification."
            ),
            Namespace.CONSISTENCY: (
                "Two metadata files describe the same concept differently."
            ),
            Namespace.INTERNAL: (
                "rs-metadata itself failed. Always worth a bug report."
            ),
        }[self]


@dataclass(frozen=True)
class DiagnosticCode:
    """Documentation for one diagnostic code, surfaced by ``explain``."""

    code: str
    title: str
    #: The most severe level this code is ever reported at. A few codes are
    #: reported less severely where the check is less certain of itself — a
    #: value that cannot be right is an error, one that merely looks wrong is a
    #: warning — so this is a ceiling rather than a promise. ``test_contracts``
    #: pins it to what the code actually emits.
    severity: Severity
    description: str
    remediation: str

    @property
    def docs(self) -> str:
        return f"{DOCS_URL}#{self.code.replace('.', '')}"

    @property
    def namespace(self) -> Namespace:
        """The layer this code comes from.

        Examples
        --------
        >>> CATALOG["consistency.mismatch"].namespace
        <Namespace.CONSISTENCY: 'consistency'>
        """
        return Namespace(self.code.split(".", 1)[0])


def _register(*codes: DiagnosticCode) -> dict[str, DiagnosticCode]:
    return {code.code: code for code in codes}


CATALOG: dict[str, DiagnosticCode] = _register(
    # ---------------------------------------------------------------- profile
    DiagnosticCode(
        code="profile.required-field",
        title="A mandatory profile field is missing",
        severity=Severity.ERROR,
        description=(
            "The LUMC profile requires this CodeMeta property in every "
            "research software record, so it is an error rather than a "
            "recommendation."
        ),
        remediation=(
            "Add the property to codemeta.json. See docs/using/profile.md for "
            "the accepted value shapes and worked examples."
        ),
    ),
    DiagnosticCode(
        code="profile.invalid-type",
        title="A property has the wrong shape",
        severity=Severity.ERROR,
        description=(
            "The value does not match the structure CodeMeta defines for this "
            "property, for example a bare string where a node object is "
            "required, or an object where a list of them is expected."
        ),
        remediation="Correct the value's shape to match the profile schema.",
    ),
    DiagnosticCode(
        code="profile.invalid-value",
        title="A property value is not valid",
        severity=Severity.ERROR,
        description=(
            "The value has the right shape but cannot be correct: a malformed "
            "identifier, an ORCID or ROR whose checksum does not verify, or a "
            "date that is not a calendar date. Severity follows how certain "
            "the check can be — a value that cannot be right is an error, "
            "while one that is merely outside a preferred vocabulary is a "
            "warning."
        ),
        remediation="Replace the value with a well-formed one.",
    ),
    DiagnosticCode(
        code="profile.invalid-context",
        title="The JSON-LD context is missing or does not declare CodeMeta",
        severity=Severity.ERROR,
        description=(
            "Without the CodeMeta context, property names in the file have no "
            "globally defined meaning and consumers cannot interpret the "
            "record. The context is what turns a JSON file into linked data."
        ),
        remediation=(
            'Set "@context" to ["https://w3id.org/codemeta/3.1", '
            '{"schema": "https://schema.org/"}].'
        ),
    ),
    DiagnosticCode(
        code="profile.unprefixed-term",
        title="A property outside the CodeMeta vocabulary is written unprefixed",
        severity=Severity.ERROR,
        description=(
            "CodeMeta 3.1 does not define this term, so written without a "
            "prefix it expands to nothing and JSON-LD processors drop it "
            "silently. The data looks present in the file but is invisible to "
            "every consumer."
        ),
        remediation=(
            "Write the property with an explicit prefix, and make sure the "
            "prefix is declared in @context."
        ),
    ),
    DiagnosticCode(
        code="profile.unknown-property",
        title="A property is not part of CodeMeta 3.1",
        severity=Severity.WARNING,
        description=(
            "The property is not defined by the CodeMeta 3.1 context and is "
            "not an absolute IRI or a prefixed term. Most often this is a "
            "typo. The LUMC profile does not forbid extra properties, so this "
            "is a warning: unknown terms are simply ignored by consumers."
        ),
        remediation=(
            "Correct the spelling, or write the property as a prefixed term "
            "whose prefix is declared in @context if the extension is "
            "intentional."
        ),
    ),
    DiagnosticCode(
        code="profile.placeholder-value",
        title="A value was copied from an example and never filled in",
        severity=Severity.ERROR,
        description=(
            "The value is one of the placeholders that circulate in metadata "
            "templates and in the rs-metadata examples, such as the all-zero "
            "ORCID, a 10.0000/ DOI, or an example.com repository URL. Left in "
            "place it is worse than an empty field: it asserts a specific "
            "identity or identifier that does not exist, and registries will "
            "harvest it."
        ),
        remediation="Replace the placeholder with the real value for this software.",
    ),
    DiagnosticCode(
        code="profile.non-canonical-value",
        title="A value is understood but not in the canonical form",
        severity=Severity.WARNING,
        description=(
            "The value is unambiguous, but CodeMeta and this profile both "
            "prescribe a different spelling of it. Non-canonical values still "
            "work with rs-metadata, which normalizes them, but they may not "
            "round-trip through other CodeMeta consumers."
        ),
        remediation="Rewrite the value in the canonical form shown in the message.",
    ),
    DiagnosticCode(
        code="profile.deprecated-value",
        title="A value comes from a deprecated vocabulary entry",
        severity=Severity.WARNING,
        description=(
            "The identifier is recognized but its issuing vocabulary has "
            "deprecated it in favor of a replacement."
        ),
        remediation="Replace it with the current identifier.",
    ),
    # --------------------------------------------------------- recommendation
    DiagnosticCode(
        code="recommendation.missing",
        title="A recommended field is absent",
        severity=Severity.WARNING,
        description=(
            "The field is not mandatory under the LUMC profile, but several "
            "registries require it and its absence limits how discoverable "
            "the software is. Recommendations never fail CI by default."
        ),
        remediation="Add the field to codemeta.json where it applies.",
    ),
    DiagnosticCode(
        code="recommendation.incomplete",
        title="A field is present but could carry more information",
        severity=Severity.INFO,
        description=(
            "The value is valid, but a richer form exists that downstream "
            "systems can use: an author without an ORCID, or an affiliation "
            "without a ROR, cannot be disambiguated automatically."
        ),
        remediation="Add the missing identifier or sub-field where you have it.",
    ),
    # ----------------------------------------------------------------- source
    DiagnosticCode(
        code="source.missing",
        title="A required metadata file was not found",
        severity=Severity.ERROR,
        description=(
            "This file is required alongside codemeta.json, because "
            "registries and archives read it directly and a record without it "
            "is not citable through them. Optional, auto-detected formats are "
            "never reported this way; their absence is not a finding."
        ),
        remediation="Create the file in the repository root.",
    ),
    DiagnosticCode(
        code="source.unreadable",
        title="A metadata file could not be parsed",
        severity=Severity.ERROR,
        description=(
            "The file exists but is not well-formed in its own syntax, so "
            "nothing in it can be validated or compared."
        ),
        remediation="Fix the syntax error reported in the message.",
    ),
    DiagnosticCode(
        code="source.invalid",
        title="A metadata file does not satisfy its own format's schema",
        severity=Severity.ERROR,
        description=(
            "The file parses, but violates the specification of the format it "
            "claims to be, so consumers of that format will reject it."
        ),
        remediation="Correct the file against its format specification.",
    ),
    DiagnosticCode(
        code="source.detected",
        title="An optional metadata source was detected",
        severity=Severity.INFO,
        description=(
            "Informational. rs-metadata found an additional metadata file and "
            "included it in the consistency comparison."
        ),
        remediation="",
    ),
    # ------------------------------------------------------------ consistency
    DiagnosticCode(
        code="consistency.mismatch",
        title="Two metadata files disagree about the same concept",
        severity=Severity.ERROR,
        description=(
            "Both files describe the same metadata concept but give values "
            "that are not equivalent after normalization. One of them is "
            "stale. Because codemeta.json is the anchor record, the "
            "discrepancy is reported against it."
        ),
        remediation=(
            "Update whichever file is out of date so both describe the same release."
        ),
    ),
    DiagnosticCode(
        code="consistency.incomplete",
        title="A source carries values the anchor record does not",
        severity=Severity.INFO,
        description=(
            "Not a contradiction. Another metadata file records something "
            "codemeta.json omits, which is usually fine but occasionally "
            "reveals metadata that was never copied across."
        ),
        remediation=(
            "Consider adding the missing values to codemeta.json if they "
            "belong in the canonical record."
        ),
    ),
    DiagnosticCode(
        code="consistency.uncomparable",
        title="A mapped field could not be meaningfully compared",
        severity=Severity.INFO,
        description=(
            "A mapping between the two formats exists, but this particular "
            "value cannot be compared: the source declares it dynamically, "
            "the mapping loses too much information, or one side is absent. "
            "Reported so the report is a complete account of what was and was "
            "not checked."
        ),
        remediation="",
    ),
    # --------------------------------------------------------------- internal
    DiagnosticCode(
        code="internal.error",
        title="rs-metadata failed unexpectedly",
        severity=Severity.ERROR,
        description=(
            "An unhandled condition inside rs-metadata. The metadata being "
            "validated is not necessarily at fault."
        ),
        remediation=(
            "Please report this at "
            "https://github.com/LUMC-DCC/rs-metadata/issues with the file that "
            "triggered it."
        ),
    ),
)


def get(code: str) -> DiagnosticCode:
    """Look up a diagnostic code in the catalog.

    Parameters
    ----------
    code : str
        A registered diagnostic code.

    Returns
    -------
    DiagnosticCode
        Its documentation: title, default severity, description, remediation.

    Raises
    ------
    KeyError
        If the code is not registered. A test asserts that every code emitted
        anywhere in the source is in the catalog, so this can only be
        reached by a typo in rs-metadata's own source.

    Examples
    --------
    >>> entry = get("consistency.mismatch")
    >>> entry.severity.value
    'error'
    >>> entry.title
    'Two metadata files disagree about the same concept'

    Every code carries a documentation link, which travels onto the finding:

    >>> entry.docs.endswith("docs/using/diagnostics.md#consistencymismatch")
    True

    An unregistered code fails loudly rather than producing a finding nobody
    can look up:

    >>> get("made.up")
    Traceback (most recent call last):
        ...
    KeyError: "Unknown diagnostic code 'made.up'. Codes must be...CATALOG."
    """
    try:
        return CATALOG[code]
    except KeyError:  # pragma: no cover - guards against internal typos
        raise KeyError(
            f"Unknown diagnostic code {code!r}. Codes must be registered in "
            f"rs_metadata.diagnostics.CATALOG."
        ) from None
