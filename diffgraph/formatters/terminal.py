"""
Terminal formatter for DiffGraph v2 output.

Renders a schema v2 DiffGraph dict as a ranked review path in the terminal.
Pure consumer — knows nothing about git, tree-sitter, or LLMs.

Usage:
    formatter = TerminalFormatter(diffgraph_v2_dict)
    formatter.render(sys.stdout)

Flags (set via constructor):
    compact      Omit the CONTEXT section (unchanged symbols)
    max_items    Cap on REVIEW FIRST + REVIEW NEXT (None = --all, no limit)
    color        Override auto-detection (True/False); default: detect from TTY + NO_COLOR
"""

from __future__ import annotations

import os
import re
import shutil
import sys
from dataclasses import dataclass, field
from typing import Optional


# ---------------------------------------------------------------------------
# Color / terminal helpers
# ---------------------------------------------------------------------------

def use_color(out=None) -> bool:
    """Return True if ANSI color codes should be emitted."""
    if "NO_COLOR" in os.environ:
        return False
    stream = out if out is not None else sys.stdout
    if not hasattr(stream, "isatty"):
        return False
    return stream.isatty()


def _is_dumb_terminal() -> bool:
    return os.environ.get("TERM", "") == "dumb"


# ANSI escape helpers
def _ansi(code: str, text: str, color: bool) -> str:
    if not color:
        return text
    return f"\033[{code}m{text}\033[0m"


def bold(text: str, color: bool) -> str:
    return _ansi("1", text, color)


def dim(text: str, color: bool) -> str:
    return _ansi("2", text, color)


def yellow(text: str, color: bool) -> str:
    return _ansi("33", text, color)


def green(text: str, color: bool) -> str:
    return _ansi("32", text, color)


def red(text: str, color: bool) -> str:
    return _ansi("31", text, color)


def bold_yellow(text: str, color: bool) -> str:
    return _ansi("1;33", text, color)


def dim_red(text: str, color: bool) -> str:
    return _ansi("2;31", text, color)


def _change_label(change_kind: str, color: bool) -> str:
    """Return colored [label] for a change_kind value."""
    labels = {
        "modified": ("[modified]", yellow),
        "added": ("[added]", green),
        "deleted": ("[deleted]", red),
        "unchanged": ("[unchanged]", dim),
    }
    label, colorize = labels.get(change_kind, ("[unknown]", lambda t, c: t))
    return colorize(label, color)


# ---------------------------------------------------------------------------
# Ranking data structures
# ---------------------------------------------------------------------------

@dataclass
class _RankedSymbol:
    """Enriched symbol entry ready for rendering."""
    symbol: dict
    importer_paths: list[str] = field(default_factory=list)
    lines_changed: int = 0
    score: int = 0


@dataclass
class RankedSymbols:
    """Three-bucket output from _rank_symbols()."""
    review_first: list[_RankedSymbol] = field(default_factory=list)
    review_next: list[_RankedSymbol] = field(default_factory=list)
    context: list[_RankedSymbol] = field(default_factory=list)


# ---------------------------------------------------------------------------
# TerminalFormatter
# ---------------------------------------------------------------------------

class TerminalFormatter:
    """
    Render a schema v2 DiffGraph dict as a ranked terminal review path.

    Args:
        diffgraph:  Schema v2 dict (from TreeSitterProcessor.analyze_changes() or any v2 source)
        compact:    Omit the CONTEXT section when True
        max_items:  Cap per section (REVIEW FIRST, REVIEW NEXT); None = no cap
        color:      Force color on/off; None = auto-detect from TTY + NO_COLOR
    """

    DEFAULT_MAX_ITEMS = 10
    SUPPORTED_SCHEMA_MAJOR = 2

    def __init__(
        self,
        diffgraph: dict,
        *,
        compact: bool = False,
        max_items: Optional[int] = DEFAULT_MAX_ITEMS,
        color: Optional[bool] = None,
    ):
        self._validate_schema_version(diffgraph.get("schema_version"))
        self.dg = diffgraph
        self.compact = compact
        self.max_items = max_items
        self._color_override = color

    @classmethod
    def _validate_schema_version(cls, schema_version: object) -> None:
        """Reject malformed or unsupported DiffGraph schema versions."""
        if not isinstance(schema_version, str) or not re.fullmatch(r"\d+\.\d+", schema_version):
            raise ValueError(
                "DiffGraph schema_version must use MAJOR.MINOR format; "
                f"received {schema_version!r}"
            )

        major = int(schema_version.split(".", 1)[0])
        if major != cls.SUPPORTED_SCHEMA_MAJOR:
            raise ValueError(
                f"Unsupported DiffGraph schema major {major}; "
                f"TerminalFormatter supports major {cls.SUPPORTED_SCHEMA_MAJOR}"
            )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def render(self, out=None) -> None:
        """Write the full ranked review path to `out` (default: sys.stdout)."""
        if out is None:
            out = sys.stdout
        color = self._color_override if self._color_override is not None else use_color(out)

        ranked = self._rank_symbols()
        self._write_header(out, color)
        self._write_warnings(out, color)
        self._write_section("REVIEW FIRST", ranked.review_first, out, color, section_style="bold_yellow")
        self._write_section("REVIEW NEXT", ranked.review_next, out, color, section_style="bold")
        if not self.compact:
            self._write_section("CONTEXT", ranked.context, out, color, section_style="dim")
        self._write_footer(out, color)

    # ------------------------------------------------------------------
    # Ranking (pure function — no I/O)
    # ------------------------------------------------------------------

    def _rank_symbols(self) -> RankedSymbols:
        """
        Pure function: DiffGraph v2 dict → RankedSymbols.
        No I/O, no side effects. Directly testable.
        """
        symbols = self.dg.get("symbols", [])
        relationships = self.dg.get("relationships", [])
        files = self.dg.get("files", [])

        # Build lookup: file_id → file path
        file_id_to_path: dict[str, str] = {
            f["id"]: f.get("path", f["id"]) for f in files
        }

        # Changed file ids (for filtering importers to only those in the diff)
        changed_file_ids = {
            f["id"] for f in files if f.get("change_kind", "unchanged") != "unchanged"
        }

        # Build import relationship index: target_file_id → set of source_file_ids
        # (only structural/derived relationships, source must be in the diff)
        import_index: dict[str, set[str]] = {}
        for rel in relationships:
            if (
                rel.get("kind") == "imports"
                and rel.get("analysis_source") in ("structural", "derived")
                and rel.get("source_id") in changed_file_ids
            ):
                target = rel.get("target_id", "")
                if target:
                    import_index.setdefault(target, set()).add(rel["source_id"])

        ranked = RankedSymbols()

        for sym in symbols:
            change_kind = sym.get("change_kind", "unchanged")

            if change_kind == "unchanged":
                ranked.context.append(_RankedSymbol(symbol=sym))
                continue

            # Compute importer paths (files in the diff that import this symbol's file)
            sym_file_id = sym.get("file_id", "")
            importer_file_ids = import_index.get(sym_file_id, set())
            importer_paths = [
                file_id_to_path.get(fid, fid)
                for fid in sorted(importer_file_ids)
            ]

            # Lines changed (only meaningful for "modified")
            lines_changed = 0
            if change_kind == "modified" and sym.get("location"):
                loc = sym["location"]
                lines_changed = max(0, loc.get("line_end", 0) - loc.get("line_start", 0) + 1)

            score = len(importer_paths) * 3 + lines_changed

            rs = _RankedSymbol(
                symbol=sym,
                importer_paths=importer_paths,
                lines_changed=lines_changed,
                score=score,
            )

            if importer_paths:
                ranked.review_first.append(rs)
            else:
                ranked.review_next.append(rs)

        # Sort each bucket
        ranked.review_first.sort(key=lambda r: r.score, reverse=True)
        ranked.review_next.sort(
            key=lambda r: (-r.lines_changed, r.symbol.get("name", ""))
        )
        ranked.context.sort(
            key=lambda r: (
                file_id_to_path.get(r.symbol.get("file_id", ""), ""),
                r.symbol.get("location", {}).get("line_start", 0),
            )
        )

        return ranked

    # ------------------------------------------------------------------
    # Rendering helpers
    # ------------------------------------------------------------------

    def _write_header(self, out, color: bool) -> None:
        files = self.dg.get("files", [])
        symbols = self.dg.get("symbols", [])

        changed_files = sum(1 for f in files if f.get("change_kind", "unchanged") != "unchanged")
        modified = sum(1 for s in symbols if s.get("change_kind") == "modified")
        added = sum(1 for s in symbols if s.get("change_kind") == "added")
        deleted = sum(1 for s in symbols if s.get("change_kind") == "deleted")

        # Detect fallback (no symbols extracted)
        if not symbols and files:
            parts = [f"{changed_files} file{'s' if changed_files != 1 else ''} changed"]
            parts.append("symbol extraction unavailable")
            line = bold("wild diff", color) + " — " + "  ·  ".join(parts)
        else:
            sym_parts = []
            if modified:
                sym_parts.append(f"{modified} symbol{'s' if modified != 1 else ''} modified")
            if added:
                sym_parts.append(f"{added} added")
            if deleted:
                sym_parts.append(f"{deleted} deleted")

            counts = f"{changed_files} file{'s' if changed_files != 1 else ''} changed"
            if sym_parts:
                counts += "  ·  " + "  ·  ".join(sym_parts)

            line = bold("wild diff", color) + " — " + counts

        out.write(line + "\n\n")

    def _write_warnings(self, out, color: bool) -> None:
        """Write any per-file warnings (e.g. unsupported language fallbacks)."""
        metadata = self.dg.get("metadata", {})
        warnings = metadata.get("warnings", [])
        for w in warnings:
            out.write(dim_red("⚠", color) + f"  {w}\n")
        if warnings:
            out.write("\n")

        # File-level fallback section when no symbols
        files = self.dg.get("files", [])
        symbols = self.dg.get("symbols", [])
        if not symbols and files:
            changed_files = [f for f in files if f.get("change_kind", "unchanged") != "unchanged"]
            if changed_files:
                out.write(bold("▶ FILES CHANGED", color) + "\n")
                for f in changed_files:
                    path = f.get("path", f.get("id", "?"))
                    stats = f.get("stats", {})
                    additions = stats.get("additions", 0)
                    deletions = stats.get("deletions", 0)
                    out.write(f"  {path}  +{additions} / -{deletions}\n")
                out.write("\n")

    def _write_section(
        self,
        title: str,
        items: list[_RankedSymbol],
        out,
        color: bool,
        section_style: str = "bold",
    ) -> None:
        if not items:
            return  # Never show empty sections

        # Apply cap
        total = len(items)
        capped = items if self.max_items is None else items[: self.max_items]
        hidden = total - len(capped)

        # Section header
        prefix = "▶ " if not _is_dumb_terminal() else "> "
        header_text = f"{prefix}{title}"
        if title == "REVIEW FIRST":
            header = bold_yellow(header_text, color)
        elif title == "CONTEXT":
            header = dim(header_text, color)
        else:
            header = bold(header_text, color)

        if hidden > 0:
            hint = f"  (showing top {len(capped)} of {total} · run: wild diff --all to see all)"
            out.write(header + dim(hint, color) + "\n")
        else:
            out.write(header + "\n")

        for rs in capped:
            self._write_symbol_entry(rs, out, color, title)

        out.write("\n")

    def _write_symbol_entry(
        self, rs: _RankedSymbol, out, color: bool, section_title: str
    ) -> None:
        sym = rs.symbol
        name = sym.get("name", "<unknown>")
        change_kind = sym.get("change_kind", "unknown")
        file_id = sym.get("file_id", "")

        # Resolve file path from files[]
        files = self.dg.get("files", [])
        file_path = next(
            (f.get("path", f.get("id", file_id)) for f in files if f["id"] == file_id),
            file_id,
        )

        change_label = _change_label(change_kind, color)

        # Main line: "  file/path.py  SymbolName [modified]  · 29 lines"
        line = f"  {file_path}  {bold(name, color)} {change_label}"
        if rs.lines_changed:
            line += f"  · {rs.lines_changed} lines"
        elif change_kind in ("added", "deleted") and rs.symbol.get("location"):
            loc = rs.symbol["location"]
            loc_lines = max(0, loc.get("line_end", 0) - loc.get("line_start", 0) + 1)
            if loc_lines:
                line += f"  · {loc_lines} lines"
        out.write(line + "\n")

        # Importer line (REVIEW FIRST only)
        if rs.importer_paths and section_title == "REVIEW FIRST":
            importers = rs.importer_paths
            max_inline = 3
            shown = importers[:max_inline]
            extra = len(importers) - len(shown)
            importer_str = ", ".join(shown)
            if extra:
                importer_str += f"  (+{extra} more)"
            arrow = "↳" if not _is_dumb_terminal() else "+->"
            out.write(
                "    " + dim(f"{arrow} imported by: {importer_str}", color) + "\n"
            )

    def _write_footer(self, out, color: bool) -> None:
        metadata = self.dg.get("metadata", {})
        analysis_source = metadata.get("analysis_source", "structural")
        duration_ms = metadata.get("analysis_duration_ms")
        diff_ref = self.dg.get("diff_ref", {})
        diff_kind = diff_ref.get("kind", "unstaged")

        # Detect languages from files[]
        files = self.dg.get("files", [])
        langs = sorted({f.get("language") for f in files if f.get("language")})
        lang_str = " · ".join(langs) if langs else ""

        # Diff context
        diff_context_map = {
            "unstaged": "unstaged changes",
            "staged": "staged changes",
        }
        if diff_kind in diff_context_map:
            diff_context = diff_context_map[diff_kind]
        elif diff_kind == "commit_range":
            base = diff_ref.get("base_ref", "")
            head = diff_ref.get("head_ref", "")
            diff_context = f"{base}..{head}" if base and head else "commit range"
        elif diff_kind == "file_scope":
            pathspec = diff_ref.get("pathspec", "")
            diff_context = pathspec or "file scope"
        else:
            diff_context = diff_kind

        parts = [analysis_source]
        if lang_str:
            parts.append(lang_str)
        if duration_ms is not None:
            parts.append(f"{duration_ms}ms")
        parts.append(diff_context)

        sep = "─" * 64 if not _is_dumb_terminal() else "-" * 64
        out.write(dim(sep, color) + "\n")
        out.write(dim("Analysis: " + " · ".join(parts), color) + "\n")

        # Optional LLM upgrade hint (shown only for local-structural analysis)
        privacy_tier = metadata.get("privacy_tier", "local")
        if privacy_tier == "local":
            hint = "Optional: wild diff --llm openai  (adds LLM summary · diff sent to OpenAI)"
            out.write(dim(hint, color) + "\n")
