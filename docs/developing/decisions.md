# Design decisions

Why the validator behaves the way it does.

## Value types are derived and enforced

For every property, CodeMeta declares what kind of value it can hold.
However, JSON-LD does not reject a wrong type, it
silently coerces: a bare `"Apache-2.0"` where a `CreativeWork or URL` is
expected becomes a *relative* IRI, which resolves into something meaningless or
is dropped.

So, the rule is:

> A property with no `Text` type branch must be a node or an
> absolute URL. A bare string there is unresolvable and leads to an error.

The types themselves are automatically derived from CodeMeta's own property table, fetched by
`scripts/vendor_reference_data.py` and stored as `data/codemeta-3.1-types.json`.

Both CodeMeta and schema.org are used, in that order of authority. CodeMeta *narrows*
schema.org for its own profile. For example, schema.org allows `maintainer` to be a Person
or an Organization, whole CodeMeta only allows Person. However, CodeMeta misses some
properties required by the LUMC profile, which is why this profile writes
`schema:featureList` with a prefix. Those come from schema.org.

The two vocabularies are matched by IRI, not by name. Some CodeMeta terms
expand to CodeMeta's own IRIs rather than to schema.org ones. The vocabularies have
different properties that happen to share a name, so merging their ranges would
violate the CodeMeta's constraints.

The generated schema defines no classes at all. Its four `$defs` are
structural: non-empty text, an absolute IRI, an ISO 8601 date, and a generic
node. The class check happens against the vocabulary. A contract test asserts that no `$defs`
entry ever names a vocabulary class.

Two things stay hand-written, because no vocabulary states them:

- **Cardinality.** Whether a property takes one value or several is a profile
  decision. E.g., software has one name and can have several authors.
- **Remediation text**, optionally. Each field is described with its
  vocabulary's own definition, which suits a tooltip but often does not say how
  to fix a file.

## Crosswalks cover full CodeMeta

The profile includes 25 CodeMeta properties. CodeMeta has many more, and its published
crosswalks map many of them. Whether the profile *requires* a field and
whether two files *disagree* about it are separate questions. A `codemeta.json`
and a `DESCRIPTION` that list different optional dependencies are still noted.
So mappings cover every record-level property an upstream crosswalk names,
and a contract test enforces it against the vocabulary's own notion of which
properties belong to the record. However, the concepts beyond the profile
are kept as informational. The profile has no opinion about `dateModified`, so rs-metadata may show a difference but must never fail
a build over one.

## Value absence

The absense is not treated as disagreement. A dependency listed in `pyproject.toml` but not in `codemeta.json` is
incompleteness, not a contradiction, and is not reported as a conflict. Only
genuinely incompatible values are. Equivalent constraints are compared
semantically, so `>=1.24` and `>=1.24.0` do not disagree.

Missing recommended fields arrive as one aggregated warning rather than one
warning each.

### Best-effort comparison

The dedicated strategies each know something: that versions are ordered, that
SPDX identifiers have synonyms, that two spellings may be one person. That
knowledge is what makes them strict enough to throw an error over.
The properties outside the profile assume no such knowledge. They irreducible
values are declines for comparison and reported as seen and not judged.

## Subtypes

A subtype is an acceptable `@type`.
A `PropertyValue` slot accepts a `LocationFeatureSpecification`, because
schema.org says the latter is a kind of the former. In schema.org, a subclass
is substitutable for its parent, and CodeMeta inherits that.

The hierarchy is read from schema.org rather than enumerated, so the accepted
set stays correct as schema.org adds classes.

## Identifier ambiguity

An identifier may live in `@id` or in `identifier`. Both are correct JSON-LD, so both are
accepted. `@id` is the node's IRI, and `identifier` is a property whose value
may be a URL or a `PropertyValue`. A comparison against a companion file reads
`@id` first and falls back to `identifier`, so the same ORCID written two ways
across two files is not reported as a disagreement.

## Formats

Format rules are the one thing not derived from upstream, because nothing
publishes them in machine-readable form. schema.org defines `Date` as
"a date value in ISO 8601 date format", in prose only. We implement the
standard each datatype name denotes.
