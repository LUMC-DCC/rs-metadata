"""Renderers turn a report into an output format.

Every renderer is a pure function of the report. None of them decide anything
about validity, which is what lets the CLI and the GitHub Action stay thin.
"""

from __future__ import annotations

from . import github, json_, text

__all__ = ["github", "json_", "text"]
