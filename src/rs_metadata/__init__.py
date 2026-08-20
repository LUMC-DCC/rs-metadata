"""rs-metadata: validation of research software metadata for LUMC.

The package layers three concerns that are deliberately kept apart:

* **CodeMeta semantics** are inherited from CodeMeta 3.1 and never redefined
  here.
* **The LUMC profile** (:mod:`rs_metadata.profile`) says which CodeMeta
  properties are mandatory at LUMC and what shape their values must take.
* **Cross-format consistency** (:mod:`rs_metadata.consistency`) compares
  ``codemeta.json``, the anchor record, against every other metadata file in
  the repository through a common CodeMeta-oriented representation.

The command-line interface and the GitHub Action are thin renderers over one
shared report model (:mod:`rs_metadata.report`); neither implements validation
behavior of its own.

Nothing exported here is a hand-written constant. Each value below is read
from whichever artifact already defines it, because a version restated in a
second place is a version that can be wrong in a second place.
"""

from __future__ import annotations

from importlib.metadata import version as _distribution_version

from .vocabulary import profile_schema

__all__ = [
    "CODEMETA_CONTEXT",
    "CODEMETA_VERSION",
    "PROFILE_NAME",
    "PROFILE_VERSION",
    "__version__",
]

#: Version of the ``rs-metadata`` distribution, read from the installed
#: package metadata, which is built from ``pyproject.toml``. Declaring it here
#: as well would mean two places to bump and one of them eventually stale.
__version__ = _distribution_version("rs-metadata")

# The remaining four describe the *profile*, not the tool, and the profile is
# defined in `profile/lumc-codemeta.yaml`. That file is a development input
# and does not ship in the wheel; `scripts/build_schema.py` copies its
# identity into the generated schema, which does ship. So the schema is where
# these are read from at runtime, and the YAML remains the thing you edit.
_PROFILE = profile_schema()
_DECLARED = _PROFILE["x-lumc-profile"]

#: Human-readable name of the profile.
PROFILE_NAME: str = _PROFILE["title"]

#: Version of the LUMC profile. Versioned independently from CodeMeta: the
#: profile can tighten or relax its own rules without CodeMeta changing.
PROFILE_VERSION: str = _DECLARED["profileVersion"]

#: The upstream vocabulary version this profile is built on.
CODEMETA_VERSION: str = _DECLARED["codemetaVersion"]

#: The context IRI a conforming record must declare.
CODEMETA_CONTEXT: str = _DECLARED["codemetaContext"]
