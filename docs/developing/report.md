# The report contract

The JSON report is a stable, versioned interface. It exists so institutional
tooling can inventory metadata quality across many repositories without
scraping CI logs, and so the CLI and the GitHub Action can be thin renderers
over one model rather than two implementations that drift.

Machine-readable specification:
[`rs-metadata-report.schema.json`](https://lumc-dcc.github.io/rs-metadata/schema/1.0.0/rs-metadata-report.schema.json),
published at the URL its own `$id` names.
A test validates real reports against it, so the schema cannot fall out of step
with the code.

```bash
rs-metadata validate --format json
rs-metadata validate --report rs-metadata-report.json
```

---

## Shape

```text
{
  "status": "failed",
  "generatedAt": "2026-08-14T09:12:00Z",
  "tool": { "name": "rs-metadata", "version": "1.0.0", "url": "..." },
  "profile": {
    "name": "LUMC CodeMeta profile",
    "version": "1.0.0",
    "codemetaVersion": "3.1",
    "schema": "codemeta-lumc.schema.json"
  },
  "root": ".",
  "sources": [ ... ],
  "summary": { "error": 1, "warning": 2, "info": 3, "checks": 21 },
  "diagnostics": [ ... ]
}
```

### `status`

`passed`, `passed-with-warnings` or `failed`.

Note that `status` describes the *findings*, not the process outcome. Whether
warnings fail a build is policy, decided by `--fail-on`, so a run can exit `0`
with status `passed-with-warnings` and exit `1` with the same status under
`--fail-on warning`. Consumers wanting the process result should read the exit
code; consumers wanting the metadata quality should read `status`.

### `sources`

Every metadata file that was **considered**, including ones that were looked
for and not found.

```json
{
  "id": "pyproject",
  "file": "pyproject.toml",
  "format": "Python project metadata",
  "formatVersion": "PEP 621",
  "role": "optional",
  "status": "parsed",
  "mapping": { "id": "pyproject-pep621", "origin": "mixed", "source": "https://..." }
}
```

| Field | Notes |
|---|---|
| `id` | Stable adapter identifier — the key to filter on |
| `file` | Repository-relative path. For an absent source, the path that was looked for |
| `formatVersion` | As declared by the file itself, where the format declares one |
| `role` | `anchor` (codemeta.json), `required` (LUMC mandates it), `optional` (auto-detected) |
| `status` | `parsed`, `absent`, or `unparsable` |
| `mapping` | Which crosswalk related it to CodeMeta, and where that came from |

Recording absent sources is deliberate. It lets a reader distinguish "no
problems with `pyproject.toml`" from "there is no `pyproject.toml`", which
matters when you are auditing whether a check actually ran.

### `diagnostics`

```json
{
  "code": "consistency.mismatch",
  "severity": "error",
  "property": "version",
  "anchor": { "file": "codemeta.json", "path": "version", "line": 10, "value": "1.2.0" },
  "source": { "file": "pyproject.toml", "path": "project.version", "line": 4, "value": "1.1.0" },
  "strategy": "version",
  "rule": "equal",
  "mapping": { "id": "pyproject-pep621", "origin": "mixed" },
  "message": "version differs between codemeta.json and pyproject.toml.",
  "suggestion": "Update whichever file is stale so both describe the same release.",
  "docs": "https://github.com/LUMC-DCC/rs-metadata/blob/main/docs/using/diagnostics.md#consistencymismatch"
}
```

| Field | Present when |
|---|---|
| `code`, `severity`, `message`, `docs` | Always |
| `property` | The finding concerns a specific CodeMeta property |
| `location` | Profile and source findings — one place in one file |
| `anchor`, `source` | Consistency findings — the two sides being compared |
| `strategy`, `rule`, `mapping` | Consistency findings |
| `suggestion` | The validator knows what a correct value would look like |

Locations carry `line` and `column` resolved from the original file text, which
is what lets CI annotations land on the offending line. They are best-effort:
absent line numbers are normal and never indicate an error.

**Errors and warnings share one array.** They are not split into `errors` and
`warnings` lists. One array means one ordering and one shape; filter on
`severity`. Diagnostics are sorted most-severe-first, then by file, line,
property and code — a stable order, so two reports of the same repository diff
cleanly.

---

## Stability guarantees

Within a major tool version:

- A field that exists keeps its meaning and type.
- A diagnostic `code` keeps its meaning. Retiring one is a breaking change.
- The `severity` *values* (`error`, `warning`, `info`) and `status` values are
  closed sets.
- Fields may be **added**. Consumers must ignore unknown fields rather than
  fail — do not validate incoming reports with `additionalProperties: false`.

What is explicitly **not** guaranteed:

- `message` and `suggestion` wording. These are prose for humans and will be
  improved. Never match on them; match on `code`.
- The default severity of a given code. A rule may be promoted or relaxed as
  the profile matures; that is a profile version change, not a report format
  change.
- Ordering beyond the documented sort key.

## Versioning

The report format is versioned with the tool that produces it. A consumer
should pin on `tool.version`, whose major component is the compatibility
promise:

| Change | Bump |
|---|---|
| New optional field | minor |
| New diagnostic code | none — codes are data, not schema |
| Field removed, renamed, or retyped | major |
| A closed enum gains a value | major |

See [Design decisions](decisions.md) for why the report has no version of its
own, and [releasing.md](releasing.md) for the release process.

## Reproducible output

Set `SOURCE_DATE_EPOCH` and `generatedAt` is derived from it instead of the
clock, making two runs byte-for-byte identical:

```bash
SOURCE_DATE_EPOCH=1780000000 rs-metadata validate --format json
```

The golden-file tests rely on this. It is also the practical way to diff
reports across commits without the timestamp swamping the diff.

## Consuming it

Read `summary` for a dashboard number, `diagnostics[].code` for anything
programmatic, and `sources` to know what was actually checked.

```python
import json, pathlib

report = json.loads(pathlib.Path("rs-metadata-report.json").read_text())

if report["tool"]["version"].split(".")[0] != "1":
    raise SystemExit("Unsupported report version")

blocking = [d for d in report["diagnostics"] if d["severity"] == "error"]
skipped = [s["id"] for s in report["sources"] if s["status"] == "absent"]
```

Aggregating across repositories, `profile.version` tells you which ruleset
produced a given report — necessary when repositories upgrade the action at
different times and you are comparing their results.

## Changing the report

Both of these, in the same commit:

1. `report.py` — the model and its `to_dict()`.
2. `schema/rs-metadata-report.schema.json` — the contract, including a
   `description` for the new field.

Then decide whether the tool's own version needs to move, using the
table above. The test suite validates generated reports against the schema, so
a field added to one and not the other fails immediately — but nothing forces
the version bump, so that judgement is yours.
