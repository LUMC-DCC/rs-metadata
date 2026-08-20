# The LUMC CodeMeta profile

The fields your `codemeta.json` needs and their explanations.

**Profile version 1.0.0 | CodeMeta 3.1**

A *profile* is not a new vocabulary. Every field below is an ordinary CodeMeta
3.1 property with its ordinary CodeMeta meaning. What this profile adds is a
policy: which of those properties LUMC requires, which it recommends, and what
their values must look like.

Two consequences follow:

- **Extra CodeMeta properties are encouraged.** The profile names a floor,
  not a ceiling. CodeMeta includes many more [properties](https://codemeta.github.io/terms/)
  than this document mentions, and extra makes the record more useful to whoever finds it.
- **The profile is versioned separately from CodeMeta.** LUMC can tighten or
  relax its own rules without CodeMeta changing, and vice versa.

The machine-readable form is
[`codemeta-lumc.schema.json`](https://lumc-dcc.github.io/rs-metadata/schema/1.0.0/codemeta-lumc.schema.json),
published at the URL its own `$id` names.
Its `x-lumc-profile` block is the single source of truth for the field lists on
this page.

---

## Document structure

### `@context` — required

Without a context, the property names in the file have no globally defined
meaning and no consumer can interpret the record as CodeMeta.

```json
"@context": [
  "https://w3id.org/codemeta/3.1",
  { "schema": "https://schema.org/" }
]
```

> **On the inline `schema` prefix.** The CodeMeta 3.1 context already declares
> `schema` as `http://schema.org/`, so `schema:featureList` expands correctly
> even without the second entry. Including it explicitly
> re-binds the prefix to `https://schema.org/`, which is schema.org's own
> canonical form today. Both work and rs-metadata accepts either; the guide's
> spelling is used throughout the examples.

Any `3.x` context is accepted. `3.0` and `3.1` resolve to byte-identical
documents, and `3.0` is what several common generators emit, so it is not
worth a diagnostic.

Declaring CodeMeta 2.0 is an **error**, and validation stops there. Some
properties were renamed between 2.0 and 3.x, so the same file means
different things under the two vocabularies. Move the record to a 3.x
context.

### `@type` — required

`SoftwareSourceCode` for software distributed as source, which is the usual
case at LUMC, or `SoftwareApplication` for software distributed only as an
executable or a service.

---

## Mandatory fields

Absent, these are errors.

Several accept more than one value. A single value may be written either bare
or as a one-element array; the two are identical in meaning and rs-metadata
treats them as such.

### `name`

The name of the software exactly as it should appear in citations and search
results.

```json
"name": "ReadAligner"
```

### `description`

A few sentences, written for a reader outside your research group: what
problem does the software solve, at what level of abstraction?

### `version`

The version this record describes. A semantic version is preferred. For
scripts and notebooks without releases, a full 40-character Git commit hash is
accepted.

```json
"version": "2.1.0"
```

rs-metadata compares versions semantically: `1.2.0`, `v1.2.0` and `1.2` are
the same release, and a short commit hash matches the full one it abbreviates.

**Update this on every release**, in every metadata file. A stale version is
the single most common consistency error.

### `identifier`

A versioned, persistent identifier for this specific release — a URL or a
`PropertyValue`. This is what others cite.

```json
"identifier": "https://doi.org/10.5281/zenodo.0000000"
```

```json
"identifier": {
  "@type": "PropertyValue",
  "propertyID": "doi",
  "value": "10.5281/zenodo.0000000"
}
```

Multiple identifiers are encouraged; add your bio.tools entry here once you
register. For internal tools that will never be formally published, a Git tag
URL is acceptable. If no identifier is a DOI, rs-metadata says so
informationally — a DOI is what makes a release citable.

### `author`

The people or organizations responsible for creating the software, in citation
order. Give each person an ORCID in `@id`, and each affiliation a ROR in its
own `@id`.

```json
"author": [
  {
    "@type": "Person",
    "@id": "https://orcid.org/0000-0002-1825-0097",
    "givenName": "Josiah",
    "familyName": "Carberry",
    "affiliation": {
      "@type": "Organization",
      "@id": "https://ror.org/05xvt9f17",
      "name": "Leiden University Medical Center"
    }
  }
]
```

ORCID and ROR check digits are verified. A failure means the
identifier is mistyped or invented, so it is an error rather than a warning.
An author may be an `Organization` rather than a `Person`.

### `license`

An SPDX identifier **URL**, or a `CreativeWork` node.

```json
"license": "https://spdx.org/licenses/Apache-2.0"
```

CodeMeta types `license` as **CreativeWork or URL**, so a bare `Apache-2.0`
is not a conformant value: it expands to a *relative* IRI and no consumer can
tell which license it names. That is an error, and the message names the exact
SPDX URL to use when the text resolves to a known identifier.

Requiring an *SPDX* URL specifically is a profile rule, stricter than CodeMeta,
which permits any URL. A bare link says where to read the license but not which
one it is, so nothing can map it to terms.

| Value | Result |
|---|---|
| `https://spdx.org/licenses/Apache-2.0` | accepted |
| `Apache-2.0` | error — the SPDX URL is named for you |
| `MIT OR Apache-2.0` | error — list each license as its own SPDX URL |
| any non-SPDX URL | error — identifies no specific license |
| a `CreativeWork` with `name` and `url` | accepted — how a custom license is expressed |
| an SPDX identifier SPDX has deprecated | warning |

### `codeRepository`

The URL of the version-controlled source repository.

### `programmingLanguage`

Plain text, or a `ComputerLanguage` node so a version can be pinned.

```json
"programmingLanguage": [
  { "@type": "ComputerLanguage", "name": "Python", "version": "3.12" },
  "C++"
]
```

### `applicationCategory`

The *kind* of software. Values from the
[bio.tools toolType vocabulary](https://biotools.readthedocs.io/en/latest/curators_guide.html#tool-type)
maximize registry interoperability. CodeMeta permits free text here, so this
is a profile rule rather than a conformance one: a value outside the vocabulary
is a **warning**, not an error.

```json
"applicationCategory": "Command-line tool"
```

### `schema:featureList`

What the software *does*. EDAM operation URLs are preferred because they drive
semantic search in bio.tools and ELIXIR infrastructure; free text is accepted
alongside them.

```json
"schema:featureList": [
  "http://edamontology.org/operation_0292",
  "Per-region alignment quality summarization"
]
```

> **Why the prefix.** CodeMeta 3.1 does not define `featureList` in its own
> vocabulary. Written bare, it expands to nothing and JSON-LD processors
> discard it silently — the operations look present in the file and are
> invisible to every consumer. rs-metadata reports the unprefixed spelling as
> an error for exactly that reason. The absolute IRI forms
> (`http://schema.org/featureList`, `https://schema.org/featureList`) are
> accepted with a note recommending the prefixed spelling.

EDAM terms are checked for URI shape and for branch: a `topic_` term in the
operations list is an error, and belongs in `applicationSubCategory`. EDAM
IRIs use `http`, not `https`.

Find terms in the [EDAM Browser](https://edamontology.github.io/edam-browser/),
by looking at what similar tools use in bio.tools, or at
[EBI OLS](https://www.ebi.ac.uk/ols4/ontologies/edam).

---

## What values must look like

CodeMeta declares, for every property, what kind of value it may hold, and
rs-metadata enforces it. The rule in one line:

> A property whose declared type offers no text branch must be a node or an
> absolute URL.

That matters because JSON-LD does not reject a wrong type, it silently coerces.
A bare `"Apache-2.0"` where a node or URL belongs becomes a relative IRI that
resolves to nothing, and the value stops naming a license to anything reading
the file.

In practice, for the properties people most often write by hand:

| Property | Must be |
|---|---|
| `author`, `contributor`, `copyrightHolder`, `funder` | a `Person` or `Organization` node |
| `maintainer`, `editor` | a `Person` node |
| `affiliation` | an `Organization` node |
| `softwareRequirements` | a `SoftwareSourceCode` node |
| `referencePublication` | a `ScholarlyArticle` node |
| `license` | an SPDX URL or a `CreativeWork` node |
| `codeRepository`, `issueTracker`, `readme` | an absolute URL |
| `keywords`, `description`, `developmentStatus` | plain text |

Literal values are checked for form as well. Dates must be real ISO 8601 dates,
so `2026-02-30` is rejected. URLs must have a scheme and, where the scheme needs
one, a host; a scheme that looks like a typo of `http` or `https` is reported as
one. Email addresses are checked loosely, enough to catch a typo.

## Recommended fields

Absent, these produce one aggregated warning naming all of them, rather than one warning each.

None of them fails a build unless you run with `--fail-on warning`.

| Field | What it is for |
|---|---|
| `datePublished` | Release date, ISO 8601 (`2026-06-01`) |
| `keywords` | Free-text discovery terms: methods, organism, tissue, disease |
| `applicationSubCategory` | The subject *domain*; EDAM topic URLs preferred |
| `softwareHelp` | Documentation and training materials |
| `issueTracker` | Where to report problems |
| `maintainer` | Contact people; a project should normally name at least two |
| `funding` | Grant or project codes |
| `referencePublication` | The paper describing the software, by DOI |
| `developmentStatus` | A [repostatus.org](https://www.repostatus.org/) term |
| `operatingSystem` | Platforms the software runs on |
| `softwareRequirements` | Dependencies |
| `supportingData` | Reference datasets, or a model's training data |
| `runtimePlatform` | Container and environment, e.g. Docker, Conda |
| `releaseNotes` | Changelog link, or the notes themselves |
| `continuousIntegration` | Where the tests run |

`developmentStatus` is checked against the repostatus vocabulary
(`concept`, `wip`, `suspended`, `abandoned`, `active`, `inactive`,
`unsupported`, `moved`); anything else is a warning.

---

## Placeholders

Metadata templates and these examples use placeholder values — the all-zero ORCID,
`10.0000/` DOIs, `example.com` URLs, `operation_0000`. rs-metadata reports
them as errors.

A placeholder is worse than a missing field. A missing field is visibly
absent; a placeholder asserts a specific identifier that does not exist, and
registries harvest it as though it did. The `github.com/example/` repository
URL is reported only as a warning, because an account could in principle
really be called `example`.

---

## What is deliberately not enforced

- **Network-dependent checks.** No check resolves a DOI, dereferences an ORCID
  or fetches an EDAM term. CI must give the same answer on a build machine, on
  a laptop on a train, and in five years. Shape and check digits are verified;
  existence is not.
- **Prose quality.** Description length and wording are not policed.
- **Extra properties.** Anything valid in CodeMeta but outside this profile
  passes without comment. A property CodeMeta does not define at all produces a
  warning with a spelling suggestion, because it is nearly always a typo — but
  it is never fatal, since consumers simply ignore unknown terms.
- **`applicationCategory` outside the vocabulary.** CodeMeta types it as
  *Text or URL*, so free text such as `Command-line tool` is perfectly
  conformant. Preferring the bio.tools vocabulary is this profile's own rule,
  so a value outside it is a warning rather than an error.
- **`developmentStatus` is a closed vocabulary.** CodeMeta types it as *Text*
  and points at repostatus.org. This profile closes it to the eight terms
  `concept`, `wip`, `suspended`, `abandoned`, `active`, `inactive`,
  `unsupported` and `moved`. Because the type is *Text*, the bare term is the
  only valid form.

---

## See also

- [Diagnostics](diagnostics.md) — every code and how to resolve it
- [Consistency model](../developing/consistency.md) — what must agree across files, and why
- [`examples/`](https://github.com/LUMC-DCC/rs-metadata/tree/main/examples/) — working repositories to copy
