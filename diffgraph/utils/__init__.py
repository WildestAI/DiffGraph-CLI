"""
Utility functions for the DiffGraph package.
"""

from .git_utils import sanitize_diff_args, involves_working_tree

__all__ = ['sanitize_diff_args', 'involves_working_tree']
