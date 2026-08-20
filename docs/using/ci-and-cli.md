# Running rs-metadata

How to run the validator
in CI, locally, from a pre-commit hook, from a CI system other than GitHub
Actions, and inside your editor.

The GitHub Action and the command-line tool share one engine, so a result you
get locally is exactly the result CI will get.

---

## GitHub Actions

The common case needs no configuration:

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

You get inline annotations on the pull request diff, a job summary, and a
`rs-metadata-report.json` build artifact.

### Inputs

Every input is an escape hatch. An ordinary repository needs none of them.

| Input | Default | Purpose |
|---|---|---|
| `codemeta` | `""` | Path to the anchor record, if it is not in the repository root. Shorthand for `sources: codemeta=PATH` |
| `sources` | `""` | Paths to metadata files kept outside the root, one `ID=PATH` per line |
| `working-directory` | `.` | Directory to validate |
| `fail-on` | `error` | Lowest severity that fails the job: `error`, `warning`, `never` |
| `report` | `rs-metadata-report.json` | Where the JSON report is written |
| `upload-report` | `true` | Upload the report as a build artifact |
| `artifact-name` | `rs-metadata-report` | Name of that artifact |
| `python-version` | `3.12` | Python used to run the validator |

### Outputs

| Output | Value |
|---|---|
| `status` | `passed`, `passed-with-warnings` or `failed` |
| `errors`, `warnings`, `notes` | Finding counts |
| `report-path` | Path to the JSON report |

### Common variations

**Treat recommendations as blocking.** Reasonable once your repositories are
already clean; not a good first move.

```yaml
- uses: LUMC-DCC/rs-metadata@v1
  with:
    fail-on: warning
```

**Metadata kept outside the root.**

```yaml
- uses: LUMC-DCC/rs-metadata@v1
  with:
    codemeta: metadata/codemeta.json
```

**One record, packaging metadata elsewhere.** When `codemeta.json` describes
the repository as a whole but the packaging metadata sits in a subdirectory,
name the files rather than moving them:

```yaml
- uses: LUMC-DCC/rs-metadata@v1
  with:
    sources: |
      pyproject=backend/pyproject.toml
      package-json=frontend/package.json
```

Ids are the ones the report lists under **Metadata sources** — `codemeta`,
`cff`, `github`, `zenodo`, `pyproject`, `package-json`, `r-description`,
`cargo`, `julia-project` and `dockerfile`. A
path given here is asserted to exist: if the file is not there, that is an
error rather than a silent skip, so a typo cannot quietly validate nothing.

**A monorepo with several packages,** each with its own `codemeta.json`. Run
the action once per package with a distinct artifact name:

```yaml
jobs:
  metadata:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        package: [tool-a, tool-b]
    steps:
      - uses: actions/checkout@v4
      - uses: LUMC-DCC/rs-metadata@v1
        with:
          working-directory: packages/${{ matrix.package }}
          artifact-name: rs-metadata-report-${{ matrix.package }}
```

> Artifact names must be unique within a workflow run. In a matrix, either give
> each job a distinct `artifact-name` as above, or set `upload-report: false`.

**Report only, never fail.** Useful while rolling the standard out across
existing repositories.

```yaml
- uses: LUMC-DCC/rs-metadata@v1
  with:
    fail-on: never
```

**Act on the outcome in a later step.**

```yaml
- uses: LUMC-DCC/rs-metadata@v1
  id: metadata
  with:
    fail-on: never

- if: steps.metadata.outputs.status != 'passed'
  run: echo "::notice::Metadata needs attention before the next release."
```

---

## Command line

```bash
pip install rs-metadata
```

| Command | What it does |
|---|---|
| `rs-metadata init` | Create any missing metadata files and CI workflow |
| `rs-metadata validate` | Validate the current directory |
| `rs-metadata validate path/to/repo` | Validate another repository |
| `rs-metadata validate --verbose` | Also show informational findings |
| `rs-metadata validate --strict` | Treat warnings as failures |
| `rs-metadata validate --format json` | Print the machine-readable report |
| `rs-metadata validate --report FILE` | Also write the report to a file |
| `rs-metadata explain <code>` | Explain one diagnostic code |
| `rs-metadata explain` | List every diagnostic code |
| `rs-metadata --version` | Tool, profile and CodeMeta versions |

Other flags: `--source ID=PATH` (repeatable) to name a metadata file kept
outside the repository root, `--codemeta PATH` as shorthand for
`--source codemeta=PATH`, `--fail-on {error,warning,never}`, and
`--color {auto,always,never}`. Color also honors the `NO_COLOR` and
`FORCE_COLOR` environment variables.

```bash
rs-metadata validate --source pyproject=backend/pyproject.toml
```

### Exit status

| Code | Meaning |
|---|---|
| `0` | Passed, possibly with warnings |
| `1` | Findings at or above the `--fail-on` threshold |
| `2` | Usage error — bad arguments, or the path is not a directory |

---

## Other CI systems

Only the annotation renderer is GitHub-specific. Elsewhere, install the
package and run the CLI.

**GitLab CI**

```yaml
validate-metadata:
  image: python:3.12
  script:
    - pip install rs-metadata
    - rs-metadata validate --report rs-metadata-report.json
  artifacts:
    when: always
    paths:
      - rs-metadata-report.json
```

**Jenkins, Azure Pipelines, a cron job, anything else**

```bash
pip install rs-metadata
rs-metadata validate --format json --report rs-metadata-report.json
```

The [JSON report](../developing/report.md) is a stable interface meant to be
read outside CI.

---

## Pre-commit

To catch problems before they reach CI:

```yaml
# .pre-commit-config.yaml
repos:
  - repo: local
    hooks:
      - id: rs-metadata
        name: Validate software metadata
        entry: rs-metadata validate
        language: python
        additional_dependencies: ["rs-metadata"]
        pass_filenames: false
        files: '^(codemeta\.json|CITATION\.cff|\.zenodo\.json|pyproject\.toml|package\.json|DESCRIPTION|Cargo\.toml|Project\.toml|Dockerfile)$'
```

`pass_filenames: false` matters: the validator takes a repository, not a list
of files. The `files` pattern only decides *when* the hook runs.

---

## Editor setup

Both schemas are published by this documentation site, at the URL each one's
own `$id` names:

| Schema | URL |
|---|---|
| Profile | `https://lumc-dcc.github.io/rs-metadata/schema/1.0.0/codemeta-lumc.schema.json` |
| Report | `https://lumc-dcc.github.io/rs-metadata/schema/1.0.0/rs-metadata-report.schema.json` |

The path carries the release version, so a `$ref` written against one keeps
resolving to the schema it was written against. There is no floating "latest"
URL, deliberately: a schema that changes under a stable URL breaks consumers
silently. A test asserts each `$id` matches where the site actually serves it.

Point your editor at the profile schema for completion, inline errors and
hover documentation while writing `codemeta.json`.

**VS Code** — `.vscode/settings.json`:

```json
{
  "json.schemas": [
    {
      "fileMatch": ["codemeta.json"],
      "url": "https://lumc-dcc.github.io/rs-metadata/schema/1.0.0/codemeta-lumc.schema.json"
    }
  ]
}
```

**Any editor with a JSON language server** — add `$schema` to the file itself:

```json
{
  "$schema": "https://lumc-dcc.github.io/rs-metadata/schema/1.0.0/codemeta-lumc.schema.json",
  "@context": ["https://w3id.org/codemeta/3.1"]
}
```

`$schema` is not a CodeMeta property, but it describes the file rather than
the software, so rs-metadata accepts it without complaint and JSON-LD ignores
it.

The schema gives structure and completion. Run the validator for check digits,
SPDX identifiers and cross-file consistency.

---

## Reproducible output

Set `SOURCE_DATE_EPOCH` to freeze the report timestamp, making two runs
byte-for-byte identical:

```bash
SOURCE_DATE_EPOCH=1780000000 rs-metadata validate --format json
```

Useful for diffing reports across commits.


## Comparing against GitHub's own metadata

A repository's description, topics, homepage and detected license live on
GitHub rather than in any file, and they drift like any other copy — more
easily, in fact, because they are edited in a web form rather than committed
alongside the code.

Inside GitHub Actions this needs no configuration. The runner already writes
the event payload to disk and points `GITHUB_EVENT_PATH` at it, and that
payload carries the repository object, so rs-metadata reads it from there. No
network call, no token, no permissions to grant.

Anywhere else, fetch it once and hand it over:

```bash
gh api repos/OWNER/REPO > github-repo.json
```

rs-metadata picks up a `github-repo.json` in the repository root
automatically, or take it from elsewhere:

```bash
rs-metadata validate . --source github=/tmp/github-repo.json
```

The validator still makes no network call of its own — you made it, which
keeps the run reproducible and lets it work offline.

Nothing is read from a fork. A fork has its own URL, and a description and
topics copied at the moment it was made, while its `codemeta.json` still
describes the upstream software; comparing them would fail every fork's CI on
metadata that is not wrong.
