# A deliberately broken repository

Every defect below is intentional. rs-metadata's test suite asserts that this
directory produces exactly these diagnostics, so this file is both
documentation and a specification.

```bash
rs-metadata validate examples/invalid
```

## In `codemeta.json`

| Defect | Diagnostic | Severity |
|---|---|---|
| `applicationCategory` is absent | `profile.required-field` | error |
| `programmingLanguage` is misspelled as `programingLanguage`, so the mandatory field is absent | `profile.required-field` | error |
| …and the misspelling itself is flagged, with the correct spelling suggested | `profile.unknown-property` | warning |
| `featureList` is written without the `schema:` prefix, so JSON-LD processors discard it silently | `profile.unprefixed-term` | error |
| An EDAM *topic* appears in the operations list | `profile.invalid-value` | error |
| An EDAM URI uses `https`, which does not match the ontology's own identifiers | `profile.non-canonical-value` | warning |
| The DOI is the guide's `10.0000/` placeholder | `profile.placeholder-value` | error |
| The author's ORCID is the all-zero placeholder | `profile.placeholder-value` | error |
| The repository URL is the guide's `github.com/example/` placeholder | `profile.placeholder-value` | warning |
| The license is a bare SPDX identifier, which CodeMeta types as CreativeWork or URL | `profile.invalid-type` | error |
| `developmentStatus` is free text rather than a repostatus.org term | `profile.invalid-value` | warning |
| Fourteen recommended fields are absent | `recommendation.missing` | warning |
| The author has no valid ORCID to disambiguate them | `recommendation.incomplete` | info |

## Between `codemeta.json` and `CITATION.cff`

| Defect | Diagnostic | Severity |
|---|---|---|
| `version` is `1.4.0` in one file and `1.2.0` in the other | `consistency.mismatch` | error |
| The author is Jane Doe in one file and John Smith in the other | `consistency.mismatch` | error |
| The license is Apache-2.0 in one file and MIT in the other | `consistency.mismatch` | error |
| The two files name different repositories | `consistency.mismatch` | error |

## What is deliberately *not* reported

The ORCID's check digit is also wrong, and the bare `featureList` is also an
unknown property. Neither is reported separately: one mistake produces one
diagnostic, chosen to be the one that explains the actual consequence.
