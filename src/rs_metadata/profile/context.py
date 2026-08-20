"""The state every profile check shares.

Each check family is a plain function taking a :class:`ProfileContext` and
returning diagnostics. That keeps the families independent of each other and
independently testable: a check can be exercised on a bare dictionary, with no
files on disk and no pipeline around it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..concepts import ParsedSource, location
from ..diagnostics import Severity
from ..locate import Path as DocPath
from ..report import Diagnostic
from ..vocabulary import profile_field_policy, profile_schema

__all__ = ["ProfileContext", "flatten"]


def flatten(name: str, raw: Any, prefix: DocPath) -> list[tuple[Any, DocPath]]:
    """Pair each value of a property with the path that locates it.

    Parameters
    ----------
    name : str
        Property name as written.
    raw : Any
        Its value: a scalar, a node, or an array of either.
    prefix : DocPath
        Path of the object the property belongs to. Empty at the document root.

    Returns
    -------
    list of tuple
        ``(value, path)`` pairs, one per item when ``raw`` is an array.

    Notes
    -----
    CodeMeta permits a single value to be written bare or as a one-element
    array, and every check has to cope with both. Doing that arithmetic once
    is what keeps a finding's reported line number right without each check
    re-deriving it.

    Examples
    --------
    >>> flatten("name", "MyTool", ())
    [('MyTool', ('name',))]
    >>> flatten("keywords", ["a", "b"], ())
    [('a', ('keywords', 0)), ('b', ('keywords', 1))]

    Inside a node, the path carries on from where the node sits:

    >>> flatten("familyName", "Doe", ("author", 0))
    [('Doe', ('author', 0, 'familyName'))]
    """
    if isinstance(raw, list):
        return [(item, (*prefix, name, index)) for index, item in enumerate(raw)]
    return [(raw, (*prefix, name))]


@dataclass
class ProfileContext:
    """One anchor record under validation, plus the profile it is judged by.

    Parameters
    ----------
    parsed : ParsedSource
        The parsed ``codemeta.json``, carrying its source map so diagnostics
        can report line numbers.

    Attributes
    ----------
    document : dict
        The parsed record.
    schema : dict
        The LUMC profile JSON Schema.
    policy : dict
        Mandatory, recommended and alias field lists, read from the schema so
        documentation, validator and schema cannot drift apart.

    Examples
    --------
    Build one from a bare document, without touching the filesystem:

    >>> ctx = ProfileContext.for_document({"name": "MyTool"})
    >>> ctx.document["name"]
    'MyTool'
    >>> "license" in ctx.policy["mandatory"]
    True

    :meth:`values` normalizes CodeMeta's scalar-or-array cardinality, pairing
    each value with the path it came from:

    >>> ctx = ProfileContext.for_document({"license": "MIT"})
    >>> ctx.values("license")
    [('MIT', ('license',))]
    >>> ctx = ProfileContext.for_document({"license": ["MIT", "Apache-2.0"]})
    >>> ctx.values("license")
    [('MIT', ('license', 0)), ('Apache-2.0', ('license', 1))]

    An absent property yields nothing, so checks iterate without guarding:

    >>> ProfileContext.for_document({}).values("license")
    []
    """

    parsed: ParsedSource
    schema: dict[str, Any] = field(default_factory=profile_schema)
    policy: dict[str, list[str]] = field(default_factory=profile_field_policy)

    @classmethod
    def for_document(
        cls, document: dict[str, Any], file: str = "codemeta.json"
    ) -> ProfileContext:
        """Build a context from a document alone, for tests and examples.

        Parameters
        ----------
        document : dict
            A CodeMeta record.
        file : str, optional
            Filename to attribute diagnostics to.

        Returns
        -------
        ProfileContext
            A context with an empty source map, so diagnostics carry no line
            numbers — which is exactly how they behave when a source map could
            not be built.
        """
        return cls(
            parsed=ParsedSource(
                adapter_id="codemeta",
                file=file,
                format="CodeMeta",
                document=document,
            )
        )

    @property
    def document(self) -> dict[str, Any]:
        """The parsed CodeMeta record."""
        return self.parsed.document  # type: ignore[no-any-return]

    @property
    def file(self) -> str:
        """The record's repository-relative path, used in every message."""
        return self.parsed.file

    def values(self, name: str) -> list[tuple[Any, DocPath]]:
        """Every value of a property, paired with its path.

        Parameters
        ----------
        name : str
            Property name as written in the document.

        Returns
        -------
        list of tuple
            ``(value, path)`` pairs. Empty when the property is absent.

        Notes
        -----
        CodeMeta permits a single value to be written bare or as a one-element
        array. Both are handled here so no check has to.
        """
        raw = self.document.get(name)
        if raw is None:
            return []
        return flatten(name, raw, ())

    def node_values(
        self, node: dict[str, Any], path: DocPath
    ) -> list[tuple[str, Any, DocPath]]:
        """Every real property of a nested node, flattened over arrays.

        Parameters
        ----------
        node : dict
            A nested node, such as a ``Person`` inside ``author``.
        path : DocPath
            Where that node sits in the document.

        Returns
        -------
        list of tuple
            ``(name, value, path)`` triples. JSON-LD keywords are skipped:
            ``@id`` and ``@type`` are not CodeMeta properties and are checked
            by the modules that understand them.

        Notes
        -----
        The nested counterpart of :meth:`values`, and the reason both
        :mod:`.types` and :mod:`.formats` can walk into nodes without each
        keeping its own copy of the array-versus-scalar path arithmetic.

        Examples
        --------
        >>> ctx = ProfileContext.for_document({})
        >>> ctx.node_values({"@type": "Person", "familyName": "Doe"}, ("author",))
        [('familyName', 'Doe', ('author', 'familyName'))]

        An array-valued property yields one entry per item, each with its own
        index in the path:

        >>> node = {"email": ["a@x.org", "b@x.org"]}
        >>> for entry in ctx.node_values(node, ("author",)):
        ...     print(entry)
        ('email', 'a@x.org', ('author', 'email', 0))
        ('email', 'b@x.org', ('author', 'email', 1))
        """
        entries: list[tuple[str, Any, DocPath]] = []
        for name, raw in node.items():
            if name.startswith("@"):
                continue
            entries.extend(
                (name, value, item_path)
                for value, item_path in flatten(name, raw, path)
            )
        return entries

    def title(self, name: str) -> str:
        """The schema's human-readable title for a property.

        Falls back to the property name, so a message is never blank.

        Examples
        --------
        >>> ProfileContext.for_document({}).title("codeRepository")
        'Code repository'
        >>> ProfileContext.for_document({}).title("notAProperty")
        'notAProperty'
        """
        entry = self.schema.get("properties", {}).get(name, {})
        return str(entry.get("title", name))

    def description(self, name: str) -> str | None:
        """The schema's description for a property, used as remediation text."""
        entry = self.schema.get("properties", {}).get(name)
        return entry.get("description") if isinstance(entry, dict) else None

    def diagnostic(
        self,
        code: str,
        severity: Severity,
        message: str,
        *,
        path: DocPath = (),
        value: Any = None,
        suggestion: str | None = None,
        prop: str | None = None,
    ) -> Diagnostic:
        """Build a diagnostic against this record.

        Resolves ``path`` to a line and column through the record's source
        map, and defaults the reported property to the path's first component.

        Parameters
        ----------
        code : str
            A registered diagnostic code.
        severity : Severity
            How much the finding matters.
        message : str
            A complete sentence naming the file and what is wrong.
        path : DocPath, optional
            Where in the document the finding applies.
        value : Any, optional
            The observed value, echoed back in the report.
        suggestion : str, optional
            Concrete remediation.
        prop : str, optional
            Override the reported property name.

        Returns
        -------
        Diagnostic
            The finding.

        Examples
        --------
        >>> ctx = ProfileContext.for_document({"version": "1.0"})
        >>> finding = ctx.diagnostic(
        ...     "profile.invalid-value",
        ...     Severity.ERROR,
        ...     "codemeta.json: version is wrong.",
        ...     path=("version",),
        ...     value="1.0",
        ... )
        >>> finding.property, finding.severity.value
        ('version', 'error')
        >>> finding.location.file, finding.location.path
        ('codemeta.json', 'version')
        """
        return Diagnostic(
            code=code,
            severity=severity,
            message=message,
            property=prop or (str(path[0]) if path else None),
            location=location(self.parsed, path, value),
            suggestion=suggestion,
        )
