"""
Git utility functions for safe command execution and argument sanitization.
"""

import click
import os
from typing import List, Tuple


def sanitize_diff_args(diff_args: List[str]) -> Tuple[List[str], List[str]]:
    """
    Sanitize diff arguments to prevent command injection and ensure safe execution.

    Args:
        diff_args: List of diff arguments to sanitize

    Returns:
        List of sanitized, safe diff arguments
    """
    if not diff_args:
        return []

    # Dangerous flags that could cause issues or suppress patch content
    dangerous_flags = {
        '--name', '--name-only', '--name-status', '--pretty', '--numstat',
        '--format', '--exec', '--output-format', '--color',
        '--no-color', '--color=always', '--color=auto', '--color=never'
    }

    # Safe flags that are commonly needed
    safe_flags = {
        '-U', '--unified', '-R', '--reverse', '-B', '--break-rewrites',
        '-M', '--find-renames', '-C', '--find-copies', '--find-copies-harder',
        '-D', '--irreversible-delete', '-l', '--max-count', '-S', '--find-object',
        '-G', '--pickaxe-regex', '--pickaxe-all', '--pickaxe-regex',
        '--relative', '--no-relative', '--text', '--ignore-space-at-eol',
        '--ignore-space-change', '--ignore-all-space', '--ignore-blank-lines',
        '--indent-heuristic', '--patience', '--histogram', '--minimal',
        '--anchored', '--word-diff', '--word-diff-regex', '--color-words',
        '--no-renames', '--check', '--ws-error-highlight', '--full-index',
        '--binary', '--abbrev', '--src-prefix', '--dst-prefix', '--no-prefix'
    }

    sanitized_args = []
    pathspecs = []
    blocked_flags = []

    for arg in diff_args:
        # Block clearly dangerous flags with clear communication
        if arg in dangerous_flags:
            blocked_flags.append(arg)
            continue

        # Allow safe flags
        if arg in safe_flags:
            sanitized_args.append(arg)
            continue

        # Allow commit references (SHA, branch names, etc.)
        if not arg.startswith('-'):
            if is_pathspec(arg):
                pathspecs.append(arg)
            else:
                sanitized_args.append(arg)
            continue

        # Allow numeric values for context lines
        if arg.startswith('-') and arg[1:].isdigit():
            sanitized_args.append(arg)
            continue

        # For unknown flags, trust the user but warn them
        click.secho(f"⚠️  Warning: Unknown diff argument '{arg}' - allowing but use with caution", fg="yellow")
        sanitized_args.append(arg)

    # Always add --no-color for consistent, parseable output
    if '--no-color' not in sanitized_args:
        sanitized_args.append('--no-color')

    # Report any blocked dangerous flags
    if blocked_flags:
        click.secho(f"🚫 Blocked dangerous diff arguments: {', '.join(blocked_flags)}", fg="red")
        click.secho("   These flags could cause security issues or suppress patch content", fg="red")

    return sanitized_args, pathspecs

def is_pathspec(arg: str) -> bool:
    return os.path.sep in arg or arg.startswith('.') or os.path.exists(arg)