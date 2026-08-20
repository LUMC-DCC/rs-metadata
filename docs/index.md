# rs-metadata

Generates and defines the [**LUMC CodeMeta profile**](https://lumc-dcc.github.io/rs-metadata/schema/1.0.0/codemeta-lumc.schema.json) with CodeMeta 3.1 vocabulary.
It also checks consistency across the metadata in a repository.
The project supports [LUMC Research Software guidelines on metadata](https://lumc-dcc.github.io/rs-guidelines/go/metadata).

## Quick start

```bash
pip install rs-metadata
rs-metadata init
```

`init` creates missing `codemeta.json`, `CITATION.cff`, and CI workflow files.
It uses metadata files and the git remote where possible, and it never
overwrites existing files.

```bash
rs-metadata validate
```

tells you if you still missing real values.


```{toctree}
:caption: Background
:maxdepth: 1

background
```

```{toctree}
:caption: Using rs-metadata
:maxdepth: 1

using/getting-started
using/profile
using/diagnostics
using/ci-and-cli
using/faq
using/release-checklist
```

```{toctree}
:caption: Developing rs-metadata
:maxdepth: 1

developing/architecture
developing/decisions
developing/recipes
developing/adapters
developing/consistency
developing/crosswalk
developing/report
developing/releasing
```

```{toctree}
:caption: Reference
:maxdepth: 1

api/index
```
