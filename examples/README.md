# Examples

These are working repositories, not snippets. Each directory is validated by
rs-metadata's own CI on every commit, so an example that stops being correct
breaks the build rather than quietly misleading people.

| Example | What it is for |
|---|---|
| [`minimal/`](minimal/) | The smallest metadata that satisfies the LUMC profile. Start here. |
| [`complete/`](complete/) | Every recommended field filled in, plus `pyproject.toml`, showing cross-format consistency. |
| [`invalid/`](invalid/) | Deliberately broken, with one defect per diagnostic. Useful for seeing what a failure looks like before it happens to you. |

## Trying them

```bash
rs-metadata validate examples/minimal
```

Add `--verbose` to see informational findings as well as errors and warnings:

```bash
rs-metadata validate examples/complete --verbose
```

## Copying one

`minimal/` is the intended starting point, and
[getting started](../docs/using/getting-started.md) walks through it. Copy
both files into your repository root and replace every value:

```bash
cp examples/minimal/codemeta.json examples/minimal/CITATION.cff /path/to/your/repo/
```

The usual template placeholders — the all-zero ORCID, `10.0000/` DOIs,
`example.com` URLs — are reported as errors precisely so that a half-edited
copy cannot reach a registry. The values in `minimal/` are real but belong to
a fictional project, so replace them all.

The ORCID used throughout is `0000-0002-1825-0097`, the public demonstration
record ORCID maintains for documentation. Do not leave it in a real
`codemeta.json`.
