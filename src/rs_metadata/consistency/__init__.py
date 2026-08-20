"""The central comparison engine.

One engine compares every source against ``codemeta.json``. There are no
pairwise comparators: ``CITATION.cff`` is never compared with
``pyproject.toml``, only each with the anchor. That keeps the number of
comparisons linear in the number of supported formats and means a
disagreement is always reported against the file that is supposed to be
canonical.

What counts as agreement is decided in three places, each with one job:

* the **mapping** says which concepts correspond and how strictly they are
  expected to agree (:mod:`rs_metadata.mapping`);
* the **strategy** says when two representations are equivalent
  (:mod:`rs_metadata.normalize`);
* this package turns the outcome into diagnostics —
  :mod:`.engine` decides *whether* a rule was violated, :mod:`.messages`
  decides *how to say so*.

See ``docs/developing/consistency.md`` for the model, and
``docs/developing/crosswalk.md`` for the per-format rules.
"""

from __future__ import annotations

from .engine import apply_rule, compare, rule_violated
from .messages import MAX_LISTED

__all__ = ["MAX_LISTED", "apply_rule", "compare", "rule_violated"]
