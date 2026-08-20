# Release checklist

## Every release

- [ ] **`version`** — update in `codemeta.json`, `CITATION.cff`, and your
      packaging file (`pyproject.toml`, `package.json`, `DESCRIPTION`).
- [ ] **`identifier` / `doi`** — a DOI identifies *one release*. Update it
      after the new DOI is minted, in both `codemeta.json` and `CITATION.cff`.
- [ ] **`datePublished` / `date-released`** — the new release date, `YYYY-MM-DD`.
- [ ] **`releaseNotes`** — if it points at a specific release rather than a
      changelog file.
- [ ] **Run the validator** before tagging: `rs-metadata validate`.

> **Ordering with Zenodo.** Zenodo mints the DOI when you publish the release,
> so the DOI for release *N* does not exist until after you tag. Either use the
> DOI from the previous release until you can amend, or use Zenodo's
> concept DOI, which resolves to the latest version and does not change (recommended).
> State whichever convention you pick in your contributing guide so it is applied
> consistently.

## When authorship changes

- [ ] **`author`** — update in `codemeta.json` **and** `CITATION.cff`. They are
      compared, and a mismatch is an error.
- [ ] Add ORCIDs for new authors, and a ROR for their affiliation.
- [ ] Consider whether the new contributor is an `author` (credited in the
      citation) or also a `maintainer` (a contact point). Authors appear in every
      generated citation.

## When something structural changes

| What changed | Update |
|---|---|
| The license | `license` in every metadata file, and the `LICENSE` file |
| The repository moved | `codeRepository`, `issueTracker`, `url`, `continuousIntegration` |
| The software's primary function | `schema:featureList`, `applicationCategory`, `description`, `keywords` |
| A new dependency you had listed | `softwareRequirements` |
| Support status | `developmentStatus` — a [repostatus.org](https://www.repostatus.org/) term |
| You registered in bio.tools | Add the bio.tools ID as an extra `identifier` **and** under `identifiers` in `CITATION.cff` |

## Once, at the start

- [ ] Add the validation workflow so all of the above is checked automatically
      on every push, see [getting started](getting-started.md#5-turn-on-validation-in-ci).

---

## Automating the version bump

If you use a release tool, teach it about the metadata files so this checklist
mostly runs itself.

**bump-my-version** — add the metadata files to the ones it rewrites:

```toml
# .bumpversion.toml
[[tool.bumpversion.files]]
filename = "codemeta.json"
search = '"version": "{current_version}"'
replace = '"version": "{new_version}"'

[[tool.bumpversion.files]]
filename = "CITATION.cff"
search = 'version: "{current_version}"'
replace = 'version: "{new_version}"'
```

**Anything else** — whatever rewrites your packaging version should rewrite
these two as well. The validator will catch it if it does not, which is the
point: you do not have to remember, you only have to not ignore a red build.
