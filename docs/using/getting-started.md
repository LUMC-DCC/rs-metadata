# Getting started

You will add two metadata files, check them, and turn on validation.

## 1. Create the files

```bash
pip install rs-metadata
rs-metadata init
```

This creates missing `codemeta.json`, `CITATION.cff`, and
`.github/workflows/metadata.yml` files. It can use `pyproject.toml`,
`package.json`, `DESCRIPTION`, `Cargo.toml`, `Project.toml` (if you already have them),
and the git remote as inputs.

Prefer to write them by hand? Use the
[CodeMeta generator](https://autocodemeta.linkeddata.es) and
[cffinit](https://citation-file-format.github.io/cff-initializer-javascript/),
or copy examples, e.g., [`examples/minimal/`][https://github.com/LUMC-DCC/rs-metadata/tree/main/examples/minimal/].

**Why two files.** `codemeta.json` is the rich record registries and archives
harvest. `CITATION.cff` is what GitHub reads to show a *"Cite this repository"*
button and what Zenodo reads when it archives a release. Both are required.

## 2. Replace the placeholders

`init` leaves placeholder values wherever it could not infer anything, and
rs-metadata reports those as errors. A leftover placeholder is worse than a
missing field: it asserts an identifier that does not exist, and registries
ingest it anyway.

```bash
rs-metadata validate
```

Ten fields are mandatory:

| Field | What to put |
|---|---|
| `name` | The name as it should appear in citations |
| `description` | A few sentences for a reader outside your group |
| `version` | This release, e.g. `1.0.0` |
| `identifier` | A DOI, or a Git tag URL |
| `author` | Everyone who should be credited, with ORCIDs |
| `license` | An SPDX URL, e.g. `https://spdx.org/licenses/MIT` |
| `codeRepository` | Your repository URL |
| `programmingLanguage` | e.g. `Python` |
| `applicationCategory` | e.g. `Command-line tool` |
| `schema:featureList` | What the software does, EDAM terms preferred |

The [field reference](profile.md) covers each one and the value shapes accepted.

## 3. Keep the two files agreeing

`name`, `version`, `author`, `license`, `identifier` and the repository URL
must match between the two files. You do not have to write them identically,
since comparison is semantic:

| In `codemeta.json` | In `CITATION.cff` | Verdict |
|---|---|---|
| `https://spdx.org/licenses/MIT` | `MIT` | same license |
| `https://doi.org/10.5281/zenodo.1` | `10.5281/zenodo.1` | same DOI |
| `1.2.0` | `v1.2.0` | same release |
| `Josiah Carberry` | `J. Carberry` | same person |

## 4. Read the result

`rs-metadata validate` gives you one of three outcomes:

- **passed:** nothing to do.
- **passed with warnings:** worth fixing, nothing blocking. Add `--verbose`
  for the informational notes.
- **failed:** errors, with the file, line, value, and a suggested fix.

Every finding carries a code:

```bash
rs-metadata explain consistency.mismatch
```

The [diagnostics reference](diagnostics.md) lists them all, also please refer to [FAQ](faq.md).

## 5. Turn on validation in CI

`init` already wrote `.github/workflows/metadata.yml`:

```yaml
name: Validate software metadata
on: [push, pull_request]

jobs:
  metadata:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: LUMC-DCC/rs-metadata@v1
```

Findings appear inline on the pull request diff, on the line that caused them.
For other CI systems, pre-commit or editor setup, see [CI and CLI](ci-and-cli.md).

## Next

Metadata usually rots at release time, when the version is bumped in one file
and not the other. Check the [release checklist](release-checklist.md).

Worth doing once the mandatory fields are in place:

- **Fill in the recommended fields.** rs-metadata lists the missing ones in a
  single warning. Several are required by registries.
- **Add anything else that describes your software.** CodeMeta has far more
  [properties](https://codemeta.github.io/terms/) than this profile mentions, and extra ones are welcome.
