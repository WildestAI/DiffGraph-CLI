"""
Local structural processor — placeholder for the tree-sitter-based processor.

When Phase 1 (PR #13, tree-sitter extraction) merges into main, this file is
replaced with a real import of TreeSitterDependencyProcessor.  Until then, this
placeholder:

  - registers the "local-structural" mode so the CLI's default mode works
  - reports privacy_tier = "local" (no data leaves the machine)
  - prints a human-readable message and exits cleanly rather than silently
    producing empty output

This lets Phase 2 (consent + privacy default) ship and be tested before
Phase 1 lands.
"""

import sys
from typing import Any, Callable, Dict, List, Optional

import click

from .base import BaseProcessor
from . import register_processor


# ---------------------------------------------------------------------------
# Attempt to import the real tree-sitter processor.
# It only exists on the phase1-tree-sitter-dependency-extraction branch;
# on main / this branch it will be absent.
# ---------------------------------------------------------------------------
try:
    from .tree_sitter_dependency import TreeSitterDependencyProcessor as _RealProcessor
    _TREE_SITTER_AVAILABLE = True
except ImportError:
    _RealProcessor = None  # type: ignore[assignment,misc]
    _TREE_SITTER_AVAILABLE = False


@register_processor("local-structural")
class LocalStructuralProcessor(BaseProcessor):
    """
    Local static analysis via tree-sitter — no data leaves the machine.

    Extracts Python symbols and import relationships from the diff using
    tree-sitter AST parsing.  Produces schema v2 output.
    """

    description: str = (
        "Local static analysis (tree-sitter).  No data leaves the machine.  "
        "Extracts symbols and import relationships from the diff.  "
        "Output: schema v2 DiffGraph dict."
    )

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if _TREE_SITTER_AVAILABLE:
            self._impl = _RealProcessor(**kwargs)
        else:
            self._impl = None

    @property
    def name(self) -> str:
        return "local-structural"

    @property
    def privacy_tier(self) -> str:
        return "local"

    def analyze_changes(
        self,
        files_with_content: List[Dict[str, str]],
        progress_callback: Optional[Callable] = None,
    ) -> Dict[str, Any]:
        """
        Delegate to TreeSitterDependencyProcessor if available, otherwise
        print an actionable message and exit.
        """
        if self._impl is not None:
            return self._impl.analyze_changes(files_with_content, progress_callback)

        # Phase 1 not yet merged — print an informative message.
        click.echo(
            "\n⚠  Local structural analysis (tree-sitter) is not yet available "
            "in this build.\n"
            "   It ships with Phase 1 of the v2 roadmap (PR #13).\n\n"
            "   In the meantime, use the OpenAI-powered mode:\n\n"
            "     wild diff --mode openai-agents-dependency-graph\n\n"
            "   Note: that mode sends your diff to OpenAI's API.\n",
            err=True,
        )
        sys.exit(1)
