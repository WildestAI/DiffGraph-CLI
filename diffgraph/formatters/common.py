"""Rendering helpers shared by the artifact formatters (pure, no I/O)."""

from __future__ import annotations


def collapsed(items: list[str], max_inline: int = 3) -> str:
    """Join items, collapsing any beyond max_inline into '(+N more)'."""
    text = ", ".join(items[:max_inline])
    extra = len(items) - max_inline
    if extra > 0:
        text += f"  (+{extra} more)"
    return text


def warning_lines(warnings: list[dict]) -> list[str]:
    """Return one readable line per warning.

    File-scoped UNSUPPORTED_LANGUAGE warnings collapse into a single line:
    their detail is a fixed message plus blob ids, which the JSON artifact
    already carries. Other warnings keep their detail, since it is specific
    (e.g. the location of a syntax error).
    """
    lines: list[str] = []
    unsupported: list[str] = []
    unsupported_index = 0
    for w in warnings:
        code = w.get("code", "UNKNOWN")
        path = w.get("file")
        if code == "UNSUPPORTED_LANGUAGE" and path:
            if not unsupported:
                # Placeholder keeps the summary at the first occurrence's position.
                unsupported_index = len(lines)
                lines.append("")
            unsupported.append(path)
            continue
        detail = w.get("detail", "")
        # Git resolution details already start with their own code.
        if detail.startswith(f"{code}: "):
            detail = detail[len(code) + 2:]
        line = code
        if path:
            line += f"  {path}"
        if detail:
            line += f": {detail}" if path else f"  {detail}"
        lines.append(line)
    if unsupported:
        lines[unsupported_index] = (
            f"Not analyzed (Python only, {len(unsupported)} "
            f"file{'s' if len(unsupported) != 1 else ''}): {collapsed(unsupported)}"
        )
    return lines
