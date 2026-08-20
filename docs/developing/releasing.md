# Releasing

This project is consumed by copy-pasting a GitHub Action into repositories the
maintainers do not control. A release therefore changes what CI accepts in
every one of them, simultaneously, without anyone opting in.

## Three version streams

| Stream | Where | What it means |
|---|---|---|
| **CodeMeta 3.1** | `CODEMETA_VERSION` | The upstream vocabulary. Never modified here — this project profiles it, it does not fork it. |
| **LUMC profile** | `PROFILE_VERSION`, `x-lumc-profile.profileVersion` | Which fields are mandatory, and their constraints. |
| **rs-metadata** | `__version__`, `pyproject.toml` | The tool. |

They are separate on purpose. A consumer pinned to report format 1.x keeps
working across tool releases; a repository can reason about "which ruleset
judged me" independently of which tool build ran.

## What counts as breaking

For the **profile**, a change is major if metadata that was valid becomes
invalid:

- a new mandatory field;
- a tightened constraint on an existing field;
- a severity promoted from warning to error;
- a vocabulary narrowed.

These may break every consuming repository at once.

Minor profile changes: new recommendations, relaxed constraints, severities
demoted, better messages.

For the **tool**, a change is major if it removes a CLI flag, an Action input
or output, or retires a diagnostic code. Diagnostic codes are a public
interface: people filter on them and link to them.

Minor: new adapters, new diagnostic codes, new strategies, new flags with
defaults that preserve behavior.

> Fixing a **false alarm** — a finding that fires on correct metadata — is a
> patch release regardless of how much code it touches. It makes builds go from
> red to green, which never breaks anyone. Treat these as high priority; a
> validator that cries wolf gets deleted from CI, and then it catches nothing.

## Release steps

1. **Refresh vendored data if it is stale.** The `vendored-data` CI job reports
   this without blocking. As its own commit, so the provenance diff is visible
   in review:

   ```bash
   poetry run python scripts/vendor_reference_data.py
   ```

   An SPDX list refresh can change results — a license may become deprecated —
   so it is a profile-affecting change, not housekeeping.

2. **Bump versions.** There is exactly one place for each. The tool's version
   lives in `pyproject.toml`; `__version__` is read from the installed package
   metadata, so nothing else needs touching. The profile's version lives in
   `profile/lumc-codemeta.yaml`, and `scripts/build_schema.py` carries it into
   the generated schema, which is where `PROFILE_VERSION` is read from.

   Bump the profile only when the ruleset changed. It is versioned separately
   from the tool on purpose: a repository can reason about which ruleset
   judged it without tracking which build ran.

3. **Update the schema `$id`** if the version moved. It embeds the version so
   a repository can pin a schema URL that does not shift under it. A test
   asserts the `$id` matches the path `docs/conf.py` publishes it at, so the
   two cannot drift:

   ```
   https://lumc-dcc.github.io/rs-metadata/schema/1.0.0/codemeta-lumc.schema.json
   ```

   Publish the new path *alongside* the old one. Never repoint an existing
   version URL — editors and external tooling depend on it being stable.

4. **Regenerate the docs.**

   ```bash
   poetry run python scripts/generate_docs.py
   ```

5. **Run the full gate.**

   ```bash
   poetry run pytest --cov
   poetry run ruff check . && poetry run ruff format --check .
   poetry run mypy
   poetry run python scripts/generate_docs.py --check
   poetry run rs-metadata validate .
   ```

   The last one because this repository carries its own metadata and
   validates it with itself, so a profile change that breaks real repositories
   usually breaks this one first.

6. **Verify the wheel actually ships its data.** The schemas, mappings and
   vendored vocabularies are read at runtime; a packaging mistake here is
   invisible in the source tree and fatal on install.

   ```bash
   poetry build
   python -m venv /tmp/check && /tmp/check/bin/pip install dist/*.whl
   cd /tmp && /tmp/check/bin/rs-metadata validate <path-to>/examples/minimal
   ```

7. **Dry-run the upload against TestPyPI.** The Publish workflow can be run
   by hand, which builds, checks and uploads to TestPyPI without touching the
   real index. Do this at least once for a first release, and any time
   packaging changed:

   Actions → **Publish to PyPI** → Run workflow → repository: `testpypi`.

8. **Tag and release.** Publishing to PyPI is triggered by *publishing a
   GitHub release*, not by pushing the tag, so the tag can be corrected right
   up until the release is published.

   ```bash
   git tag -a v1.2.0 -m "rs-metadata 1.2.0"
   git push origin v1.2.0
   ```

   Then draft and publish the release on GitHub. The workflow refuses to
   upload if the tag and `pyproject.toml` disagree, because that mistake
   cannot be undone — see below.

9. **Move the major tag.** This is the one consumers actually reference.

   ```bash
   git tag -f v1 v1.2.0
   git push -f origin v1
   ```

   `v1` may only ever move **within** major version 1. When version 2 exists,
   `v1` freezes at the last 1.x release — repositories pinned to `@v1` must
   never be moved to a new major without opting in.

## PyPI, and what cannot be undone

Uploads use [Trusted Publishing](https://docs.pypi.org/trusted-publishers/):
PyPI verifies the workflow's OIDC identity, so there is no API token stored in
this repository to leak or rotate. It is configured once, per project, at
`https://pypi.org/manage/project/rs-metadata/settings/publishing/`, naming
this repository, the workflow file `publish.yml`, and the environment `pypi`.

**A version number is permanent.** This is the part worth internalizing before
the first release:

- A file, once uploaded, cannot be replaced. Uploading a different file under
  the same name and version is refused.
- Deleting a release removes it from the index, but **does not free the
  version number**. Nothing can ever be uploaded as `1.2.0` again.
- So a broken release is corrected by publishing `1.2.1`, never by fixing
  `1.2.0` in place.

What you *can* do is [yank](https://peps.python.org/pep-0592/) a release. A
yanked version stays installable for anyone who pinned it exactly, so lockfiles
keep resolving, but it is skipped by every ordinary install. That is the right
response to a release that is broken but not dangerous.

Reach for deletion only for something that must not remain downloadable at all
— a leaked credential, or content that cannot legally stay up. Yanking is
otherwise kinder to everyone downstream.

The `pypi` environment gives one more safeguard: adding a required reviewer to
it in repository settings turns publishing into an approval step, so an
accidental release has to get past a person.

## Announcing a breaking profile change

Before tagging:

- Say which repositories will start failing and why.
- Give the exact fix, as a diff someone can apply.
- Point at [`fail-on: never`](../using/ci-and-cli.md#common-variations) as the
  temporary escape hatch for whoever needs time.

## Publishing to PyPI

```bash
poetry publish --build
```

The Action installs from `$GITHUB_ACTION_PATH`, not from PyPI, so the two are
independent: an Action release does not require a PyPI release, and vice versa.
Keep them in step anyway — people who install the CLI locally expect it to
match what CI runs.

## See also

| | |
|---|---|
| [Architecture](architecture.md) | How the pieces fit |
| [Report contract](report.md) | Report format versioning in detail |
| [CONTRIBUTING.md](https://github.com/LUMC-DCC/rs-metadata/tree/main/CONTRIBUTING.md) | Development setup |
