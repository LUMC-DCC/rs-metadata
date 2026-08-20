# Frequently asked questions

If a specific finding is confusing, `rs-metadata explain <code>` and the
[diagnostics reference](diagnostics.md) are the faster route. This page covers
the questions behind the findings.

---

## Getting set up

### Why do I need two files? Isn't one enough?

They are read by different things. `CITATION.cff` is what GitHub reads to show
a *"Cite this repository"* button and what Zenodo reads when archiving a
release; it is deliberately narrow and only describes how to cite the software.
`codemeta.json` is the rich record that the Research Software Directory,
Software Heritage and other archives harvest, and it has fields CFF does not.

Neither replaces the other, so both are required. rs-metadata exists largely
to stop them drifting apart.

### Do I really need a DOI?

For anything published or cited, yes — a DOI is what makes a *specific
release* citable, and most archives require one. Enable the
[Zenodo–GitHub integration](https://docs.github.com/en/repositories/archiving-a-github-repository/referencing-and-citing-content)
and publish a release; the DOI is minted for you.

For an internal script that will never be formally published, a Git tag URL is
accepted:

```json
"identifier": "https://github.com/your-org/your-tool/tree/v1.0.0"
```

Having no DOI is an **informational** note, not an error. It will not fail your
build.

### My software has no releases — it is a script, or a notebook.

Use the full 40-character Git commit hash as the version:

```json
"version": "a3f8c2d1b4e7f0291a3f8c2d1b4e7f0291a3f8c2"
```

and a Git tag or tree URL as the `identifier`. Both are explicitly accepted.

### There is no EDAM term for what my software does.

Free text is accepted:

```json
"schema:featureList": [
  "Dimensionality reduction of high-dimensional omics data"
]
```

You get an informational note suggesting EDAM terms, which doesn't fail a build.
Look in the [EDAM Browser](https://edamontology.github.io/edam-browser/) or at
what similar tools use in bio.tools; mixing EDAM terms and free text in the
same list is fine.

### Can I use fields the profile does not mention?

Yes. Any valid CodeMeta property is encouraged, the profile only sets a mandatory
minimum and highlights useful optional fields. It never rejects extra
properties.

A property CodeMeta does not define *at all* produces a warning with a spelling
suggestion, because it is nearly always a typo. If your extension is
deliberate, write it as a prefixed term and declare the prefix:

```json
"@context": [
  "https://w3id.org/codemeta/3.1",
  { "lumc": "https://lumc.nl/terms/" }
],
"lumc:internalProjectCode": "RSE-2026-001"
```

### I am not on GitHub.

Everything except the Action works anywhere. Install the package and run
`rs-metadata validate` from GitLab CI, Jenkins, a cron job or a pre-commit
hook, see [CI and CLI](ci-and-cli.md).

---

## Findings I disagree with

### It says my ORCID is invalid, but I copied it correctly.

ORCIDs carry a check digit, and rs-metadata verifies it arithmetically. A
failure means a digit is wrong somewhere — most often a transposition, or the
all-zero `0000-0000-0000-0000` left in from the documentation example.

Nothing is looked up online, so this is not a claim that the person does not
exist. It is a claim that the string cannot be a valid ORCID. Copy it from
[orcid.org](https://orcid.org/) again.

### It flagged my repository URL as a placeholder.

`https://github.com/example/...` is the URL used throughout metadata templates, so
seeing it in a real repository almost always means the template was copied and
not finished. It is only a **warning**, precisely because an account could in
principle really be called `example`.

`example.com`, `example.org` and `example.net` are reserved domains and are
reported as errors.

### My package is called `my-tool` on PyPI but `MyTool` in the citation.

That is fine and is not reported. Names are compared with separators and case
removed, so `MyTool`, `my-tool`, `my_tool` and `my.tool` are all the same
software.

### Do I have to list every dependency in `codemeta.json`?

No. A dependency in `pyproject.toml` that is absent from `codemeta.json` is
*incompleteness*, not a contradiction, and is reported at informational level
only.

What does get reported (as a warning) is the same package pinned to
genuinely different constraints in both files, because then one of them is
telling users something untrue.

### It rejects my license, but `Apache-2.0` is a real SPDX identifier.

It is but CodeMeta types `license` as **CreativeWork or URL**, and a bare
identifier is neither. JSON-LD expands it to a *relative* IRI, which resolves
against the document base into something meaningless or is dropped outright.
Nothing errors anywhere in the chain; the value simply stops naming a license
to anything that reads the file. Use the URL form:

```json
"license": "https://spdx.org/licenses/Apache-2.0"
```

The message names that URL for you whenever the text you wrote resolves to a
known SPDX identifier, so the fix is a copy and paste.

For dual licensing, list each license as its own SPDX URL.

For a license with no SPDX identifier at all — an institutional one, say — use
a node, which is what CodeMeta provides `CreativeWork` for:

```json
"license": {
  "@type": "CreativeWork",
  "name": "LUMC internal license",
  "url": "https://example.org/lumc-license"
}
```

### It says `featureList` is discarded, but I can see it in the file.

CodeMeta 3.1 does not define `featureList` in its
own vocabulary, so written without a prefix it expands to nothing and JSON-LD
processors drop it silently. The data is visible to you and invisible to every
consumer. Rename it to `schema:featureList`.

### The descriptions in my two files differ slightly and it warned me.

Prose gets reworded in one file and not the other. That is a documentation
lapse rather than contradictory metadata, so it is a warning.
Whitespace, case and trailing punctuation are ignored.

Note that `pyproject.toml`'s `description` is *not* compared with CodeMeta's:
PEP 621 defines it as a one-line summary, which is a different field from an
abstract. The report says so explicitly.

---

## Controlling the noise

### Can I suppress a specific warning?

No. There is no per-finding suppression mechanism (yet?).

What you can control is the threshold. Warnings are already non-fatal by
default, so a warning you disagree with will not block you.

If a finding is *wrong*, it fires on metadata that is actually correct,
please [open an issue](https://github.com/LUMC-DCC/rs-metadata/issues). False
alarms are treated as high-priority bugs, not as things to work around.

### I am rolling this out across many existing repositories and everything is red.

Start in report-only mode, fix over time, then tighten:

```yaml
- uses: LUMC-DCC/rs-metadata@v1
  with:
    fail-on: never
```

The JSON report is still produced and uploaded, so you can measure progress
across repositories before anything starts blocking.

---

## Trust and privacy

### Does this send my metadata anywhere?

No. The validator makes no network requests of any kind: not to resolve a DOI,
not to look up an ORCID, not to fetch an EDAM term. Every vocabulary it
consults (CodeMeta, the CFF schema, the SPDX license list, repostatus,
bio.tools tool types) is vendored inside the package.

That is also why it works offline and why a build that passes today will give
the same answer in five years.

### How does it know an SPDX identifier or an EDAM term is real?

The SPDX license list ships with the package, so identifiers are checked
against the real list, including deprecations. EDAM terms are checked for URI
*shape* and for branch — a `topic_` term in your operations list is an error —
but not for existence, because that would require a network lookup.

Refreshing the vendored vocabularies is an explicit, reviewed act; the source
URL, upstream version, retrieval date and checksum for each are recorded in
[`provenance.json`](../../src/rs_metadata/data/provenance.json).

### Which version of everything am I running?

```bash
rs-metadata --version
```

Three things are versioned separately: CodeMeta (the upstream vocabulary,
never modified), the LUMC profile, and the tool — which carries the JSON report
format with it. See [releasing](../developing/releasing.md).

---

## Still stuck?

- `rs-metadata explain <code>` for any finding
- [Diagnostics reference](diagnostics.md) — every code, what triggers it, how to fix it
- [`examples/invalid/`](https://github.com/LUMC-DCC/rs-metadata/tree/main/examples/invalid/) — one deliberate defect per diagnostic, with a table mapping each to its code
- [Open an issue](https://github.com/LUMC-DCC/rs-metadata/issues)
