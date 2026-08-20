"""Sphinx configuration.

The prose is Markdown so it stays readable on GitHub; MyST renders it here
without a second source format. The API reference comes from the docstrings,
which already carry runnable examples, so nothing is written twice.

Build it with::

    poetry install --with docs
    poetry run sphinx-build -b html docs docs/_build/html
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from rs_metadata import __version__

project = "rs-metadata"
author = "Leiden University Medical Center"
copyright = f"{date.today().year}, {author}"
release = __version__
version = __version__

extensions = [
    "myst_parser",
    "sphinx.ext.autodoc",
    "sphinx.ext.napoleon",
    "sphinx.ext.viewcode",
    "sphinx.ext.intersphinx",
    "sphinx_copybutton",
    "sphinxcontrib.mermaid",
]

source_suffix = {".md": "markdown", ".rst": "restructuredtext"}
exclude_patterns = ["_build", "README.md"]

myst_enable_extensions = ["colon_fence", "deflist"]
myst_heading_anchors = 3
# Mermaid diagrams are written as ```mermaid fences in the Markdown, which
# GitHub renders natively. This makes Sphinx render the same source.
myst_fence_as_directive = ["mermaid"]

html_theme = "sphinx_book_theme"
html_title = f"rs-metadata {release}"
html_static_path: list[str] = []

# The schemas are published at the URL their own `$id` names, so a `$ref` to
# one resolves. They are copied here at build time rather than committed under
# docs/, which would be a second copy of a file that already ships in the
# package. `_extra` is gitignored for the same reason `_build` is.
_SCHEMA_SOURCE = Path(__file__).resolve().parents[1] / "src" / "rs_metadata" / "schema"
_EXTRA = Path(__file__).parent / "_extra"
_SCHEMA_PUBLISHED = _EXTRA / "schema" / release
_SCHEMA_PUBLISHED.mkdir(parents=True, exist_ok=True)
_published = []
for _schema in sorted(_SCHEMA_SOURCE.glob("*.json")):
    (_SCHEMA_PUBLISHED / _schema.name).write_bytes(_schema.read_bytes())
    _published.append(_schema.name)

# Sphinx writes into `_static` and `_sources`. GitHub Pages does not run
# Jekyll for artifact-based deployments, but a leading underscore is exactly
# what Jekyll strips, so this costs nothing and removes the failure mode.
(_EXTRA / ".nojekyll").write_text("", encoding="utf-8")

# A landing page so `/schema/` and `/schema/<version>/` resolve to something
# a person can read, rather than a 404 that looks like the schema is missing.
_rows = "\n".join(
    f'      <li><a href="{name}"><code>{name}</code></a></li>' for name in _published
)
(_SCHEMA_PUBLISHED / "index.html").write_text(
    f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>rs-metadata schemas {release}</title></head>
<body>
  <h1>rs-metadata schemas, version {release}</h1>
  <p>Each file is served at the URL its own <code>$id</code> declares, so a
  <code>$ref</code> written against it resolves. The path carries the release
  version and its contents never change; a later release publishes a new
  path rather than replacing this one.</p>
  <ul>
{_rows}
  </ul>
  <p><a href="../../">Documentation</a></p>
</body></html>
""",
    encoding="utf-8",
)
(_EXTRA / "schema" / "index.html").write_text(
    f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>rs-metadata schemas</title>
<meta http-equiv="refresh" content="0; url={release}/"></head>
<body><p>Published schema versions:
<a href="{release}/">{release}</a>.</p></body></html>
""",
    encoding="utf-8",
)

html_extra_path = ["_extra"]
html_theme_options = {
    "repository_url": "https://github.com/LUMC-DCC/rs-metadata",
    "repository_branch": "main",
    "path_to_docs": "docs",
    "use_repository_button": True,
    "use_issues_button": True,
    "use_edit_page_button": True,
    "use_source_button": True,
    "home_page_in_toc": True,
    "show_toc_level": 2,
    "navigation_with_keys": False,
}

napoleon_google_docstring = False
napoleon_numpy_docstring = True
napoleon_use_rtype = False
napoleon_use_ivar = True

autodoc_member_order = "bysource"
autodoc_typehints = "description"
autodoc_default_options = {
    "members": True,
    "undoc-members": False,
    "show-inheritance": True,
}

intersphinx_mapping = {"python": ("https://docs.python.org/3", None)}
