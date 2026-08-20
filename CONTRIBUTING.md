# Contributing

Thanks for working on this. If you are here to fix your *own* repository's
metadata rather than the tool, [docs/using/](docs/using/) is the side you
want.

Read [docs/developing/architecture.md](docs/developing/architecture.md)
first. It explains the pipeline, layers, and invariants this page assumes.

## Setup

```bash
poetry install
poetry run pytest
```

Python 3.11 or newer. The runtime dependencies are few on purpose:
`jsonschema`, `PyYAML`, `packaging` and `nameparser`. The GitHub Action
installs them on every CI run of every repository that uses it.

## Checks

```bash
poetry run pytest --cov          # tests, including docstring examples
poetry run ruff check .          # lint
poetry run ruff format .         # format
poetry run mypy                  # types (strict)
```

`pytest` collects `tests/` and `src/`, so every docstring example runs as a
test.

To build the documentation:

```bash
poetry install --with docs
poetry run sphinx-build -b html docs docs/_build/html
```

Open `docs/_build/html/index.html`. CI builds the same thing with `-W`, so a
broken cross-reference or a missing autodoc target fails the build.

CI runs all of these on Linux, macOS and Windows across Python 3.11-3.14, and
additionally validates this repository's own metadata with the action from
this repository.

## Generated files

Three things are derived from data and must be rebuilt when that data changes.
Each has one job, and each is checked in CI, so a stale artifact fails the
build rather than shipping.

```bash
poetry run python scripts/vendor_reference_data.py   # src/rs_metadata/data/* from upstream
poetry run python scripts/build_schema.py            # derived parts of the profile schema
poetry run python scripts/generate_docs.py           # the generated docs pages and README block
```

`build_schema.py` generates the whole published JSON Schema from
`profile/lumc-codemeta.yaml`, which is where the profile is actually defined:
which fields are required, which are recommended, and how many values each
takes. Types, descriptions and node shapes come from the vendored
vocabularies. Edit the YAML, never the JSON.

`vendor_reference_data.py` is the command-line front door to the
`scripts/vendoring` package, which is the only part of the project that
touches the network. The validator never runs it. Refreshing the vendored vocabularies
changes what CI accepts in every repository using the action, so it should land
as its own commit with the provenance diff visible.

## Reporting something

Issue templates cover the kinds of report this project gets: a **false
alarm**, a **bug**, a request for a **metadata format** it does not read yet,
and a general **feature request** for everything else. The false-alarm form
asks for the metadata that triggered the finding and why it is correct,
because that is what decides the fix.

A false alarm is treated as a bug, not a request. A validator that fires on
correct metadata gets switched off, and then it catches nothing at all.

## Where things live

See the module map in
[docs/developing/architecture.md](docs/developing/architecture.md#module-map).

Two layout points that surprise people: schemas and mappings live *inside* the
package, not at the repository root, so they travel with the wheel and are
readable through `importlib.resources`; and `docs/` is split by audience into
`using/` and `developing/`.

## Conventions

**Validation semantics belong in the core.** The CLI and the Action are
renderers over one report model. If a behavior differs between them, that is a
bug: someone debugging locally must see exactly what CI saw.

**Every finding names the file, the property, the value and a fix.** A
diagnostic a maintainer cannot act on is worse than none, because it teaches
them to ignore the tool. When the validator knows what a correct value would
look like, it says so.

**One mistake, one diagnostic.** A misspelled `featureList` is also an unknown
property and also means a mandatory field is missing. Report the one that
explains the actual consequence and suppress the rest.

**Severities are conservative.** An `error` must be something genuinely wrong.
Before adding one, read the "what is deliberately not reported" list in
[docs/developing/consistency.md](docs/developing/consistency.md): a validator that fires on correct
metadata gets removed from CI, and then it catches nothing at all.

**No network access in the validator.** Not for DOI resolution, not for ORCID
lookup, not for EDAM. Shape and check digits are verifiable offline; existence
is not, and CI must be deterministic.

**Positions are best-effort.** Source maps must never raise. A diagnostic
without a line number is still correct.

**Docstrings are NumPy-style, and their examples run.** `pytest` executes every
`>>>` in `src/` via `--doctest-modules`, so an example that stops being true
fails the build. For rules that decide validity, show a passing and failing
value. Examples are often clearer than prose, and the test suite keeps them
current.

## Adding things

| What | How |
|---|---|
| A metadata format | [docs/developing/adapters.md](docs/developing/adapters.md) |
| A profile rule | Add it to the schema or the right `profile/` module, with positive **and** negative tests |
| A diagnostic code | Register it in `diagnostics.py`, then regenerate the docs |
| A comparison strategy | Subclass `Strategy` in `normalize/strategies.py` and register it |
| A change to the report | [docs/developing/report.md](docs/developing/report.md) |

Adding a user-visible rule usually also requires user-facing documentation:
the [field reference](docs/using/profile.md) for a new field, and the
[FAQ](docs/using/faq.md) when the decision needs explanation.

Every profile rule needs both a document that satisfies it and a document that
breaks exactly one thing. Assert on diagnostic *codes*, not message text, so
wording can be improved without rewriting the suite.

## Versioning

Three things are versioned separately:

```
CodeMeta       3.1     upstream vocabulary, never modified here
LUMC profile   1.0.0   which fields are mandatory, and their constraints
rs-metadata    1.0.0   the tool, and with it the JSON report format
```

Making previously valid metadata invalid breaks every consuming repository at
once, so it is a major profile bump and needs an announcement. The full policy
and the release steps are in
[docs/developing/releasing.md](docs/developing/releasing.md).

## Reporting problems

Open an issue at
[LUMC-DCC/rs-metadata/issues](https://github.com/LUMC-DCC/rs-metadata/issues).

A false alarm on correct metadata is a high-priority bug. Please include the
metadata that triggered it.
