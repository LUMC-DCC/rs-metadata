# Adding support for a metadata format

An **adapter** is one supported metadata file or ecosystem: the logic needed to
find it, read it, check it against its own specification, and express what it
says in CodeMeta concepts.

Adapters know nothing about each other and nothing about comparison. Adding one
costs an adapter and a mapping file; nothing in the comparison engine changes,
and no existing adapter is touched.

## The contract

```python
detect(root)            -> Path | None      # is this format present?
parse(path, relative)   -> ParsedSource     # read it; raise SourceError if malformed
validate_source(parsed) -> list[Diagnostic] # check it against its own spec
map_to_codemeta(parsed) -> ConceptMap       # express it as CodeMeta concepts
```

`detect` and `validate_source` have working defaults. `parse` and
`map_to_codemeta` are the two you must write.

## Four steps

### 1. Write the mapping

`src/rs_metadata/mappings/<id>.yaml`. This is data, not code: which concepts
correspond, how strictly they must agree, and where the correspondence came
from.

```yaml
id: julia-project
format: Julia Project.toml
formatVersion: "1.0"

provenance:
  origin: codemeta-upstream
  source: https://github.com/codemeta/codemeta/blob/master/crosswalks/Julia%20Project.csv
  retrieved: "2026-08-14"
  notes: >
    Field correspondences follow the CodeMeta project's Julia crosswalk.

fields:
  - property: name
    source: name
    strategy: name
    rule: equal
    severity: warning

  - property: version
    source: version
    strategy: version
    rule: equal
    severity: error

  - property: author
    source: authors
    strategy: people
    rule: subset
    severity: warning
    anchorProperties: [author, maintainer]
    note: >
      Subset because packaging metadata commonly names only the current
      maintainer.

  - property: description
    source: description
    comparable: false
    reason: >
      Julia's description is a one-line summary, not a CodeMeta abstract.
```

Per-field keys:

| Key | Meaning |
|---|---|
| `property` | The CodeMeta concept |
| `source` | Where it lives in the source format (a label, shown in reports) |
| `strategy` | Comparison strategy — see [consistency.md](consistency.md) |
| `rule` | `equal`, `subset`, `overlap` or `informational` |
| `severity` | `error`, `warning` or `info` when the rule is violated |
| `anchorProperties` | Anchor concepts to compare against, if not just `property` |
| `comparable` | `false` to declare the field deliberately not compared |
| `reason` | **Required** when `comparable: false` — why not |
| `note` | Why the rule and severity are what they are |

**Reuse an upstream CodeMeta crosswalk wherever one exists.** Define your own
only where none is adequate, and set `origin` honestly: `codemeta-upstream`,
`mixed`, or `rs-metadata`. Provenance travels with every finding the mapping
produces.

**Choose severities conservatively.** An `error` should be something that is
genuinely wrong, not merely untidy. See the "what is deliberately not
reported" list in [consistency.md](consistency.md) — that list is the
difference between a validator people keep and one they delete.

### 2. Write the adapter

`src/rs_metadata/adapters/<name>.py`.

```python
class JuliaProjectAdapter(Adapter):
    id = "julia-project"
    format = "Julia project metadata"
    role = "optional"  # anchor | required | optional
    filenames = ("Project.toml",)
    mapping_name = "julia-project"

    def parse(self, path: Path, relative: str) -> ParsedSource:
        try:
            text = path.read_text(encoding="utf-8")
            document = tomllib.loads(text)
        except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as error:
            raise SourceError(f"{relative} could not be read: {error}") from error
        return ParsedSource(
            adapter_id=self.id,
            file=relative,
            format=self.format,
            document=document,
            source_map=TomlSourceMap(text),
        )

    def map_to_codemeta(self, parsed: ParsedSource) -> ConceptMap:
        document = parsed.document
        concepts: ConceptMap = {}
        add(concepts, "name", document.get("name"), ("name",))
        add(concepts, "version", document.get("version"), ("version",))
        add_each(concepts, "author", document.get("authors"), ("authors",))
        return concepts
```

Then register it in `src/rs_metadata/adapters/__init__.py`. Registration order
is reporting order.

Points that matter:

- **Always pass a path.** The third argument to `add` is where the value came
  from. It becomes the line number in a CI annotation, which is the difference
  between a finding a maintainer can act on and one they have to hunt for.
- **Build a source map.** `json_source_map`, `yaml_source_map`, `TomlSourceMap`
  and `DcfSourceMap` cover the common cases. Positions are best-effort and must
  never raise.
- **Raise `SourceError`, never let a parser exception escape.** Include a line
  number when the parser gives you one.
- **Never read the same fact twice.** Two code paths reaching the same
  conclusion — a Python classifier and the mere existence of a
  `pyproject.toml` both meaning "Python" — record it twice. Comparison
  deduplicates, so the only symptom is a finding pointing at whichever path
  ran first. A test enforces this.
- **Tolerate wrongly typed values.** A field holding a number where a list
  belongs must not raise; use `as_list`, which never does. A file being wrong
  is what the tool is for, so it may not be a reason to crash. A fuzz-style
  test covers every mapped field.
- **Extract fields you have declared `comparable: false`.** A mapping that
  claims to have considered a field the code never reads is dishonest, and the
  report cannot say it was skipped. A test enforces this, as does its
  converse: every rule must be reachable from the adapter.
- **`role = "required"`** means the file's absence is an error. Reserve it for
  a file something downstream actually depends on; anything else should be
  `optional` and skipped silently when missing.
- **Do not reach the network.**

### 3. Handle the format's real-world spellings

This is where most of the work is, and where most false alarms come from.
Existing adapters deal with:

- npm's `user/repo`, `github:user/repo` and `git+https://…​.git` repository
  forms, and its `Name <email> (url)` author strings;
- PEP 621's `dynamic` fields, the PEP 639 license expression, the older
  `{text = …}` and `{file = …}` tables, and the free-form `project.urls`
  labels;
- Poetry's pre-PEP-621 `[tool.poetry]` layout;
- R's `Authors@R`, which holds R code rather than data, and its own license
  spellings;
- YAML resolving `version: 1.20` to the float `1.2` and `date-released:
  2026-06-01` to a `datetime.date` — the CFF adapter recovers the text as
  written.

If a value cannot be interpreted, map nothing. A missing value is skipped
silently; a wrong one produces a false alarm.

### 4. Test it

Add cases to `tests/adapters/test_adapters.py`, and a fixture to
`RICH_FIXTURES` in `tests/unit/test_contracts.py` — a file exercising every
field your mapping declares. Two contract tests then run automatically against
it:

- every concept your adapter emits is declared in your mapping;
- every field you declared `comparable: false` is actually extracted.

Cover both directions for each rule: equivalent representations that must
**not** be reported, and genuine disagreements that must be.

Then regenerate the crosswalk documentation:

```bash
poetry run python scripts/generate_docs.py
```

## Adding a comparison strategy

Only if no existing strategy fits. Subclass `Strategy` in
`normalize/strategies.py`:

```python
class ChecksumStrategy(Strategy):
    name = "checksum"

    def key(self, value):
        # None means "carries nothing comparable"
        return normalize_text(value)
```

Register it in `STRATEGIES` and re-export it from `normalize/__init__.py`.
Override `compare` only when the concept has real
structure that key equality cannot express — `people` and `dependency-set` do;
most do not.

## Adding a diagnostic code

Register it in `diagnostics.py`. A test asserts that every code emitted
anywhere in the source is in the catalog, so an unregistered one fails CI
rather than shipping without documentation or an `explain` entry.

Codes are a public interface. Within a major version, a code never changes
meaning: adding one is a minor release, retiring one is a major release.
