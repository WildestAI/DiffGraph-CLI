"""
Unit tests for TerminalFormatter.

All tests operate on fixture DiffGraph v2 dicts — no git subprocess, no network,
no tree-sitter. The formatter is a pure consumer of the JSON schema.

Test cases from TERMINAL-FORMATTER.md:
  1. test_rank_symbols_empty_diff          — no symbols → all buckets empty
  2. test_rank_symbols_no_relationships    — all changed → REVIEW NEXT
  3. test_rank_symbols_with_importers      — symbol w/ importers → REVIEW FIRST
  4. test_rank_symbols_unchanged           — unchanged symbols → CONTEXT
  5. test_rank_symbols_deleted_file        — file deletion → REVIEW FIRST if imported
  6. test_rank_symbols_truncation          — >10 symbols → truncated w/ hint
  7. test_terminal_formatter_no_color      — NO_COLOR=1 → no ANSI codes
  8. test_terminal_formatter_piped         — stdout not TTY → no ANSI codes (via color=False)
  9. test_terminal_formatter_compact       — --compact → CONTEXT section absent
 10. test_rank_symbols_score_ordering      — higher score → earlier in REVIEW FIRST
 11. test_render_no_symbols_file_fallback  — no symbols but files → FILES CHANGED fallback
 12. test_render_footer_shows_duration     — analysis_duration_ms present → shows in footer
"""

import io
import os
import pytest

from diffgraph.formatters.terminal import TerminalFormatter, RankedSymbols


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

def _make_file(file_id: str, path: str, change_kind: str = "modified", language: str = "Python") -> dict:
    return {
        "id": file_id,
        "path": path,
        "change_kind": change_kind,
        "language": language,
        "stats": {"additions": 10, "deletions": 3},
    }


def _make_symbol(
    sym_id: str,
    name: str,
    file_id: str,
    change_kind: str = "modified",
    line_start: int = 1,
    line_end: int = 10,
) -> dict:
    return {
        "id": sym_id,
        "name": name,
        "file_id": file_id,
        "kind": "function",
        "change_kind": change_kind,
        "location": {"line_start": line_start, "line_end": line_end},
    }


def _make_import_rel(rel_id: str, source_id: str, target_id: str) -> dict:
    return {
        "id": rel_id,
        "source_id": source_id,
        "target_id": target_id,
        "kind": "imports",
        "analysis_source": "structural",
    }


def _make_diffgraph(
    files: list = None,
    symbols: list = None,
    relationships: list = None,
    metadata: dict = None,
    diff_ref: dict = None,
) -> dict:
    return {
        "schema_version": "2.0",
        "generated_at": "2026-07-10T16:30:00Z",
        "diff_ref": diff_ref or {"kind": "unstaged"},
        "files": files or [],
        "symbols": symbols or [],
        "relationships": relationships or [],
        "metadata": metadata or {
            "analysis_source": "structural",
            "privacy_tier": "local",
            "analysis_duration_ms": 840,
        },
    }


# ---------------------------------------------------------------------------
# 1. Empty diff — no symbols
# ---------------------------------------------------------------------------

def test_rank_symbols_empty_diff():
    dg = _make_diffgraph()
    fmt = TerminalFormatter(dg)
    ranked = fmt._rank_symbols()
    assert ranked.review_first == []
    assert ranked.review_next == []
    assert ranked.context == []


# ---------------------------------------------------------------------------
# 2. No relationships — all changed symbols → REVIEW NEXT
# ---------------------------------------------------------------------------

def test_rank_symbols_no_relationships():
    files = [_make_file("f1", "auth/validator.py", change_kind="modified")]
    symbols = [
        _make_symbol("s1", "validate_token", "f1", "modified", 1, 29),
        _make_symbol("s2", "TokenCache", "f1", "added", 31, 50),
    ]
    dg = _make_diffgraph(files=files, symbols=symbols)
    fmt = TerminalFormatter(dg)
    ranked = fmt._rank_symbols()
    assert ranked.review_first == []
    assert len(ranked.review_next) == 2
    assert ranked.context == []
    # Sorted by lines desc: validate_token (29 lines) before TokenCache (20 lines)
    assert ranked.review_next[0].symbol["name"] == "validate_token"


# ---------------------------------------------------------------------------
# 3. Symbol with importers → REVIEW FIRST
# ---------------------------------------------------------------------------

def test_rank_symbols_with_importers():
    files = [
        _make_file("f_validator", "auth/validator.py", change_kind="modified"),
        _make_file("f_routes", "api/routes.py", change_kind="modified"),
    ]
    symbols = [
        _make_symbol("s_validate", "validate_token", "f_validator", "modified", 1, 29),
        _make_symbol("s_route", "list_users", "f_routes", "modified", 5, 15),
    ]
    relationships = [
        _make_import_rel("r1", "f_routes", "f_validator"),  # routes imports validator
    ]
    dg = _make_diffgraph(files=files, symbols=symbols, relationships=relationships)
    fmt = TerminalFormatter(dg)
    ranked = fmt._rank_symbols()

    # validate_token is imported by routes → REVIEW FIRST
    assert len(ranked.review_first) == 1
    assert ranked.review_first[0].symbol["name"] == "validate_token"
    assert "api/routes.py" in ranked.review_first[0].importer_paths

    # list_users has no importers → REVIEW NEXT
    assert len(ranked.review_next) == 1
    assert ranked.review_next[0].symbol["name"] == "list_users"


# ---------------------------------------------------------------------------
# 4. Unchanged symbols → CONTEXT
# ---------------------------------------------------------------------------

def test_rank_symbols_unchanged():
    files = [_make_file("f1", "auth/validator.py", change_kind="modified")]
    symbols = [
        _make_symbol("s1", "validate_token", "f1", "modified", 1, 5),
        _make_symbol("s2", "TokenCache", "f1", "unchanged", 10, 30),  # unchanged
    ]
    dg = _make_diffgraph(files=files, symbols=symbols)
    fmt = TerminalFormatter(dg)
    ranked = fmt._rank_symbols()
    assert len(ranked.context) == 1
    assert ranked.context[0].symbol["name"] == "TokenCache"
    assert len(ranked.review_next) == 1
    assert ranked.review_next[0].symbol["name"] == "validate_token"


# ---------------------------------------------------------------------------
# 5. Deleted file — if imported by modified file → REVIEW FIRST
# ---------------------------------------------------------------------------

def test_rank_symbols_deleted_file():
    files = [
        _make_file("f_legacy", "auth/legacy_auth.py", change_kind="deleted"),
        _make_file("f_routes", "api/routes.py", change_kind="modified"),
    ]
    symbols = [
        _make_symbol("s_old", "legacy_verify", "f_legacy", "deleted", 1, 20),
        _make_symbol("s_route", "get_user", "f_routes", "modified", 5, 10),
    ]
    relationships = [
        _make_import_rel("r1", "f_routes", "f_legacy"),  # routes imports legacy_auth
    ]
    dg = _make_diffgraph(files=files, symbols=symbols, relationships=relationships)
    fmt = TerminalFormatter(dg)
    ranked = fmt._rank_symbols()

    # legacy_verify is imported by modified routes → REVIEW FIRST
    assert len(ranked.review_first) == 1
    assert ranked.review_first[0].symbol["name"] == "legacy_verify"
    assert "api/routes.py" in ranked.review_first[0].importer_paths

    # get_user has no importers in the diff → REVIEW NEXT
    assert len(ranked.review_next) == 1
    assert ranked.review_next[0].symbol["name"] == "get_user"


# ---------------------------------------------------------------------------
# 6. Truncation — >10 symbols → show top 10, hint in header
# ---------------------------------------------------------------------------

def test_rank_symbols_truncation():
    # 15 changed symbols, no relationships → all go to REVIEW NEXT
    files = [_make_file("f1", "big_module.py", change_kind="modified")]
    symbols = [
        _make_symbol(f"s{i}", f"func_{i}", "f1", "added", i * 3, i * 3 + 2)
        for i in range(15)
    ]
    dg = _make_diffgraph(files=files, symbols=symbols)
    fmt = TerminalFormatter(dg, max_items=10)
    ranked = fmt._rank_symbols()
    # All 15 are ranked (ranking is pure — truncation happens at render time)
    assert len(ranked.review_next) == 15

    # Render and check for truncation hint
    out = io.StringIO()
    fmt.render(out)
    output = out.getvalue()
    assert "showing top 10 of 15" in output
    assert "wild diff --all" in output


# ---------------------------------------------------------------------------
# 7. NO_COLOR=1 → no ANSI codes in output
# ---------------------------------------------------------------------------

def test_terminal_formatter_no_color(monkeypatch):
    monkeypatch.setenv("NO_COLOR", "1")
    files = [_make_file("f1", "auth/validator.py", change_kind="modified")]
    symbols = [_make_symbol("s1", "validate_token", "f1", "modified", 1, 10)]
    dg = _make_diffgraph(files=files, symbols=symbols)
    fmt = TerminalFormatter(dg)
    out = io.StringIO()
    fmt.render(out)
    output = out.getvalue()
    assert "\033[" not in output


# ---------------------------------------------------------------------------
# 8. color=False (piped stdout) → no ANSI codes
# ---------------------------------------------------------------------------

def test_terminal_formatter_piped():
    files = [_make_file("f1", "auth/validator.py", change_kind="modified")]
    symbols = [_make_symbol("s1", "validate_token", "f1", "modified", 1, 10)]
    dg = _make_diffgraph(files=files, symbols=symbols)
    fmt = TerminalFormatter(dg, color=False)
    out = io.StringIO()
    fmt.render(out)
    output = out.getvalue()
    assert "\033[" not in output


# ---------------------------------------------------------------------------
# 9. --compact → CONTEXT section absent
# ---------------------------------------------------------------------------

def test_terminal_formatter_compact():
    files = [_make_file("f1", "auth/validator.py", change_kind="modified")]
    symbols = [
        _make_symbol("s1", "validate_token", "f1", "modified", 1, 10),
        _make_symbol("s2", "TokenCache", "f1", "unchanged", 20, 40),
    ]
    dg = _make_diffgraph(files=files, symbols=symbols)

    # Without compact — CONTEXT section should be present
    fmt = TerminalFormatter(dg, color=False)
    out = io.StringIO()
    fmt.render(out)
    assert "CONTEXT" in out.getvalue()
    assert "TokenCache" in out.getvalue()

    # With compact — CONTEXT section should be absent
    fmt_compact = TerminalFormatter(dg, compact=True, color=False)
    out_compact = io.StringIO()
    fmt_compact.render(out_compact)
    assert "CONTEXT" not in out_compact.getvalue()
    assert "TokenCache" not in out_compact.getvalue()


# ---------------------------------------------------------------------------
# 10. Score ordering — higher score symbol appears first in REVIEW FIRST
# ---------------------------------------------------------------------------

def test_rank_symbols_score_ordering():
    """
    Symbol A: 2 importers, 5 lines → score = 2*3 + 5 = 11
    Symbol B: 1 importer, 20 lines → score = 1*3 + 20 = 23
    B should appear first in REVIEW FIRST despite A having more importers.
    """
    files = [
        _make_file("f_a", "module_a.py", change_kind="modified"),
        _make_file("f_b", "module_b.py", change_kind="modified"),
        _make_file("f_importer1", "consumer1.py", change_kind="modified"),
        _make_file("f_importer2", "consumer2.py", change_kind="modified"),
    ]
    symbols = [
        _make_symbol("s_a", "small_func", "f_a", "modified", 1, 5),   # 5 lines
        _make_symbol("s_b", "big_func", "f_b", "modified", 1, 20),    # 20 lines
    ]
    relationships = [
        _make_import_rel("r1", "f_importer1", "f_a"),   # importer1 → A
        _make_import_rel("r2", "f_importer2", "f_a"),   # importer2 → A (A has 2 importers)
        _make_import_rel("r3", "f_importer1", "f_b"),   # importer1 → B (B has 1 importer)
    ]
    dg = _make_diffgraph(files=files, symbols=symbols, relationships=relationships)
    fmt = TerminalFormatter(dg)
    ranked = fmt._rank_symbols()

    assert len(ranked.review_first) == 2
    # small_func score: 2*3 + 5 = 11; big_func score: 1*3 + 20 = 23
    # big_func should come first
    assert ranked.review_first[0].symbol["name"] == "big_func"
    assert ranked.review_first[1].symbol["name"] == "small_func"


# ---------------------------------------------------------------------------
# 11. No symbols, files present → FILES CHANGED fallback section
# ---------------------------------------------------------------------------

def test_render_no_symbols_file_fallback():
    files = [
        _make_file("f1", "legacy/mystery.py", change_kind="modified"),
        _make_file("f2", "legacy/helper.py", change_kind="modified"),
    ]
    dg = _make_diffgraph(files=files, symbols=[])
    fmt = TerminalFormatter(dg, color=False)
    out = io.StringIO()
    fmt.render(out)
    output = out.getvalue()
    assert "FILES CHANGED" in output
    assert "legacy/mystery.py" in output
    assert "legacy/helper.py" in output
    assert "symbol extraction unavailable" in output


# ---------------------------------------------------------------------------
# 12. analysis_duration_ms present → shows in footer
# ---------------------------------------------------------------------------

def test_render_footer_shows_duration():
    files = [_make_file("f1", "auth/validator.py", change_kind="modified")]
    symbols = [_make_symbol("s1", "fn", "f1", "modified", 1, 5)]
    metadata = {
        "analysis_source": "structural",
        "privacy_tier": "local",
        "analysis_duration_ms": 1234,
    }
    dg = _make_diffgraph(files=files, symbols=symbols, metadata=metadata)
    fmt = TerminalFormatter(dg, color=False)
    out = io.StringIO()
    fmt.render(out)
    assert "1234ms" in out.getvalue()


# ---------------------------------------------------------------------------
# 13. Importer display — max 3 inline, collapse rest with (+N more)
# ---------------------------------------------------------------------------

def test_importer_display_collapse():
    """5 importers → show 3 inline + (+2 more)."""
    importer_files = [
        _make_file(f"f_consumer_{i}", f"consumers/c{i}.py", change_kind="modified")
        for i in range(5)
    ]
    target_file = _make_file("f_target", "core/engine.py", change_kind="modified")
    files = importer_files + [target_file]
    symbols = [_make_symbol("s1", "process", "f_target", "modified", 1, 10)]
    symbols += [
        _make_symbol(f"s_c{i}", f"use_engine_{i}", f"f_consumer_{i}", "modified", 1, 5)
        for i in range(5)
    ]
    relationships = [
        _make_import_rel(f"r{i}", f"f_consumer_{i}", "f_target")
        for i in range(5)
    ]
    dg = _make_diffgraph(files=files, symbols=symbols, relationships=relationships)
    fmt = TerminalFormatter(dg, color=False)
    out = io.StringIO()
    fmt.render(out)
    output = out.getvalue()
    # Should show "(+2 more)" since we show max 3 importers inline
    assert "(+2 more)" in output


# ---------------------------------------------------------------------------
# 14. --all flag disables truncation
# ---------------------------------------------------------------------------

def test_rank_symbols_all_flag():
    files = [_make_file("f1", "big_module.py", change_kind="modified")]
    symbols = [
        _make_symbol(f"s{i}", f"func_{i}", "f1", "added", i * 3, i * 3 + 2)
        for i in range(15)
    ]
    dg = _make_diffgraph(files=files, symbols=symbols)
    fmt = TerminalFormatter(dg, max_items=None, color=False)  # max_items=None = --all
    out = io.StringIO()
    fmt.render(out)
    output = out.getvalue()
    # All 15 functions should be listed; no truncation hint
    for i in range(15):
        assert f"func_{i}" in output
    assert "showing top" not in output
