# Recipes

What to do, in order, for the changes you want to make. Each ends with the
same check:

```bash
poetry run pytest && poetry run ruff check . && poetry run mypy
```

CI additionally runs every generator in `--check` mode, so a derived file left
stale fails the build.

## Add a field to the profile

1. Add it to `profile/lumc-codemeta.yaml` under `required:` or `recommended:`,
   with `one` or `many`. Use the bare name if CodeMeta defines it, otherwise
   prefix it (`schema:featureList`).
2. If the vocabulary's own definition would not tell someone how to fill the
   field in, add a line under `help:`.
3. If it can hold a class not already listed under `types:`, add that class
   with the properties worth describing. The generator fails with the class
   name if you forget.
4. `poetry run python scripts/build_schema.py`

Nothing else. Types, descriptions and node shapes come from the vocabularies.

## Move to a newer CodeMeta

1. Change `version` and the URLs under the `codemeta` entry in
   `profile/lumc-codemeta.yaml`.
2. Update the two `codemeta` entries in `scripts/vendoring/sources.py`, and
   `CONTEXT_VERSIONS` in `scripts/vendoring/codemeta.py`, to match.
3. `poetry run python scripts/vendor_reference_data.py`
4. `poetry run python scripts/build_schema.py`
5. Run the suite. Failures are the real report: a property whose type changed
   upstream shows up as a test that no longer holds.

Renamed properties are not migrated. A record on an older context is reported
as unrecognized, which is deliberate: the same file means different things
under two vocabularies, and guessing which was meant is worse than saying so.

## Add a vocabulary

For a namespace beyond CodeMeta and schema.org.

1. Add an entry under `vocabularies:` in the profile, with its `prefix` and
   the URLs its properties and classes come from.
2. Add a `Source` to `scripts/vendoring/sources.py` and a parser module beside
   it, producing the same shape as the others: property name mapped to `range`
   and `description`.
3. Merge it in `merge_types`. Order is precedence, so put it after the
   vocabularies it should not override.
4. Prefix its fields in the profile and regenerate.

## Support a new metadata file

0. **Check whether CodeMeta already publishes a crosswalk for it**, under
   [`crosswalks/`](https://github.com/codemeta/codemeta/tree/master/crosswalks).
   If one exists, add it to `CROSSWALK_SOURCES` in
   `scripts/vendoring/crosswalks.py`, register the `Source`, and re-run the
   vendoring script; the mapping's `origin` is then `mixed`, not
   `rs-metadata`. A test enforces both that claim and the coverage below.
1. Write an adapter in `adapters/`, subclassing `Adapter`. See
   [Adapters](adapters.md) for what each method owes.
2. Write the crosswalk in `mappings/<id>.yaml`. Every concept the upstream
   table maps must either get a rule or be declared under `upstream.omitted`
   with the reason it is not compared.
3. Register it in `adapters/registry.py`. Registration order is reporting
   order.
4. Add a test in `tests/adapters/` that builds a repository and runs the real
   pipeline.
5. `poetry run python scripts/generate_docs.py`

## Change the anchor format

This is a substantial change. `codemeta.json` is the record
the profile is defined against, so replacing it means:

- a new anchor adapter, and `ANCHOR` pointing at it;
- a context model, if the new format is not JSON-LD — `profile/jsonld.py`
  assumes it is;
- new crosswalks, since every mapping translates *to* CodeMeta concepts;
- a profile definition written against the new vocabulary.

The vocabulary layer, the type and format checks, the consistency engine and
the reporting all carry over unchanged. Budget for the four above.

## Add or change a rule

| Change | Where |
|---|---|
| A structural rule | `profile/lumc-codemeta.yaml`, then regenerate the schema |
| A rule about meaning | the matching `profile/` module |
| What must agree across files | the relevant `mappings/*.yaml` |
| A comparison strategy | `normalize/strategies.py`, subclass `Strategy` and register |
| A diagnostic code | `diagnostics.py`, then regenerate docs |
| The report shape | `report.py` **and** `schema/rs-metadata-report.schema.json` |

A new rule needs a test on both sides: a record that satisfies it, and one that
breaks exactly that rule.

## Refresh the vendored vocabularies

```bash
poetry run python scripts/vendor_reference_data.py
poetry run python scripts/build_schema.py
poetry run pytest
```
