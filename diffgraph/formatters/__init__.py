"""
DiffGraph formatters — render a schema v2 DiffGraph dict to various output formats.

Formatters are pure consumers of the schema v2 dict produced by processors.
They know nothing about git, tree-sitter, or LLMs.
"""

from .terminal import TerminalFormatter

__all__ = ["TerminalFormatter"]
