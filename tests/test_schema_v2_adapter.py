"""
Tests for the schema v2 output adapter (schema_v2_adapter.py).

These tests cover:
- Symbol diff computation (added / modified / deleted / unchanged)
- Schema v2 output structure
- Zero network calls (all structural, local-only)

Design principle: every test assertion can be expressed as an exact equality
because all outputs are deterministic (no LLM, no network, no randomness).
"""

import pytest
from dataclasses import dataclass
from typing import Optional

from diffgraph.processing_modes.schema_v2_adapter import (
    compute_symbol_diff,
    build_schema_v2_output,
    build_import_relationship,
    build_symbol_entry,
    qualified_name_for,
    symbol_id,
    file_symbol_id,
)


# ---------------------------------------------------------------------------
# Minimal stub for ExtractedComponent (mirrors the real dataclass)
# ---------------------------------------------------------------------------

@dataclass
class StubComponent:
    name: str
    component_type: str = "function"
    parent: Optional[str] = None
    start_line: Optional[int] = 0
    end_line: Optional[int] = 5
    file_path: Optional[str] = "test.py"


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

FILE = "auth/validator.py"
CONTENT_V1 = """\
def validate_token(token):
    if not token:
        raise ValueError("empty token")
    return True

class RateLimiter:
    def check(self, key):
        return True
"""

CONTENT_V2 = """\
def validate_token(token):
    if not token:
        raise ValueError("empty token")
    # Added expiry check
    if is_expired(token):
        raise ValueError("expired token")
    return True

class RateLimiter:
    def check(self, key):
        return True

def helper():
    pass
"""


# ---------------------------------------------------------------------------
# qualified_name_for
# ---------------------------------------------------------------------------

class TestQualifiedName:
    def test_standalone_function(self):
        comp = StubComponent(name="validate_token")
        assert qualified_name_for(comp) == "validate_token"

    def test_method(self):
        comp = StubComponent(name="check", parent="RateLimiter", component_type="method")
        assert qualified_name_for(comp) == "RateLimiter.check"

    def test_class(self):
        comp = StubComponent(name="RateLimiter", component_type="container")
        assert qualified_name_for(comp) == "RateLimiter"


# ---------------------------------------------------------------------------
# symbol_id / file_symbol_id
# ---------------------------------------------------------------------------

class TestSymbolIds:
    def test_symbol_id_format(self):
        sid = symbol_id("auth/validator.py", "RateLimiter.check")
        assert sid == "sym::auth/validator.py::RateLimiter.check"

    def test_file_symbol_id_format(self):
        fid = file_symbol_id("auth/validator.py")
        assert fid == "sym::file::auth/validator.py"


# ---------------------------------------------------------------------------
# compute_symbol_diff
# ---------------------------------------------------------------------------

class TestComputeSymbolDiff:

    def _make_comps(self, specs):
        """Make StubComponents from (name, start, end, parent) tuples."""
        result = []
        for name, start, end, parent in specs:
            comp_type = "method" if parent else "function"
            result.append(StubComponent(
                name=name, component_type=comp_type,
                parent=parent, start_line=start, end_line=end, file_path=FILE,
            ))
        return result

    def test_added_symbol(self):
        pre = self._make_comps([("validate_token", 0, 3, None)])
        post = self._make_comps([
            ("validate_token", 0, 5, None),
            ("helper", 12, 13, None),  # new
        ])
        content_pre = CONTENT_V1
        content_post = CONTENT_V2

        changes = compute_symbol_diff(pre, post, content_pre, content_post)
        by_name = {c.qualified_name: c for c in changes}

        assert "helper" in by_name
        assert by_name["helper"].change_kind == "added"

    def test_deleted_symbol(self):
        pre = self._make_comps([
            ("validate_token", 0, 3, None),
            ("old_func", 5, 8, None),   # will be deleted
        ])
        post = self._make_comps([("validate_token", 0, 3, None)])
        changes = compute_symbol_diff(pre, post, CONTENT_V1, CONTENT_V1)
        by_name = {c.qualified_name: c for c in changes}

        assert by_name["old_func"].change_kind == "deleted"

    def test_modified_symbol(self):
        # Same name, different content
        pre = self._make_comps([("validate_token", 0, 3, None)])
        post = self._make_comps([("validate_token", 0, 6, None)])
        changes = compute_symbol_diff(pre, post, CONTENT_V1, CONTENT_V2)
        by_name = {c.qualified_name: c for c in changes}

        assert by_name["validate_token"].change_kind == "modified"

    def test_unchanged_symbol(self):
        # RateLimiter.check exists unchanged in both versions.
        # In CONTENT_V1 the method body is at lines 6–7 (0-indexed).
        # In CONTENT_V2 it has shifted to lines 9–10 due to inserted lines above.
        # Both slices resolve to the same text:
        #   "    def check(self, key):\n        return True"
        # → change_kind should be "unchanged".
        pre_comps = [StubComponent(name="check", component_type="method",
                                   parent="RateLimiter", start_line=6, end_line=7,
                                   file_path=FILE)]
        post_comps = [StubComponent(name="check", component_type="method",
                                    parent="RateLimiter", start_line=9, end_line=10,
                                    file_path=FILE)]
        changes = compute_symbol_diff(pre_comps, post_comps, CONTENT_V1, CONTENT_V2)
        by_name = {c.qualified_name: c for c in changes}

        assert by_name["RateLimiter.check"].change_kind == "unchanged"

    def test_new_file_all_added(self):
        """All symbols in a new file should be 'added'."""
        post = self._make_comps([("validate_token", 0, 3, None)])
        changes = compute_symbol_diff(None, post, None, CONTENT_V1)

        assert all(c.change_kind == "added" for c in changes)

    def test_deleted_file_all_deleted(self):
        """All symbols in a deleted file should be 'deleted'."""
        pre = self._make_comps([("validate_token", 0, 3, None)])
        changes = compute_symbol_diff(pre, None, CONTENT_V1, None)

        assert all(c.change_kind == "deleted" for c in changes)

    def test_no_changes(self):
        """Identical pre/post → all unchanged."""
        comps = self._make_comps([("validate_token", 0, 3, None)])
        changes = compute_symbol_diff(comps, comps, CONTENT_V1, CONTENT_V1)

        assert all(c.change_kind == "unchanged" for c in changes)


# ---------------------------------------------------------------------------
# build_symbol_entry
# ---------------------------------------------------------------------------

class TestBuildSymbolEntry:

    def test_required_fields_present(self):
        from diffgraph.processing_modes.schema_v2_adapter import SymbolChange
        sc = SymbolChange(
            qualified_name="validate_token",
            file_path=FILE,
            component_type="function",
            parent=None,
            change_kind="modified",
            start_line=0,
            end_line=3,
        )
        entry = build_symbol_entry(sc)

        assert entry["id"] == f"sym::{FILE}::validate_token"
        assert entry["qualified_name"] == "validate_token"
        assert entry["file"] == FILE
        assert entry["change_kind"] == "modified"
        assert entry["analysis_source"] == "structural"
        assert len(entry["evidence"]) >= 1
        ev = entry["evidence"][0]
        assert ev["kind"] == "ast_parse"
        assert ev["location"]["line_start"] == 1   # 0-indexed → 1-indexed
        assert ev["location"]["line_end"] == 4     # 3 → 4

    def test_structural_source_always_set(self):
        from diffgraph.processing_modes.schema_v2_adapter import SymbolChange
        sc = SymbolChange("f", FILE, "function", None, "added", 0, 2)
        assert build_symbol_entry(sc)["analysis_source"] == "structural"


# ---------------------------------------------------------------------------
# build_import_relationship
# ---------------------------------------------------------------------------

class TestBuildImportRelationship:

    def test_basic_import(self):
        rel = build_import_relationship("api/routes.py", "auth.validator")
        assert rel["from"] == "sym::file::api/routes.py"
        assert rel["to"] == "auth.validator"
        assert rel["kind"] == "imports"
        assert rel["analysis_source"] == "structural"
        assert rel["evidence"][0]["kind"] == "import_statement"


# ---------------------------------------------------------------------------
# build_schema_v2_output
# ---------------------------------------------------------------------------

class TestBuildSchemaV2Output:

    def _minimal_output(self):
        from diffgraph.processing_modes.schema_v2_adapter import SymbolChange
        sc = SymbolChange("validate_token", FILE, "function", None, "modified", 0, 3)
        return build_schema_v2_output(
            symbol_changes=[sc],
            import_relationships=[],
            file_changes=[{"path": FILE, "change_kind": "modified"}],
            diff_ref={"from": "HEAD", "to": "working_tree", "kind": "unstaged"},
            wild_version="2.0.0-dev",
            analysis_duration_ms=123,
            languages_detected=["python"],
        )

    def test_schema_version(self):
        out = self._minimal_output()
        assert out["schema_version"] == "2.0"

    def test_privacy_tier_local(self):
        out = self._minimal_output()
        assert out["metadata"]["privacy_tier"] == "local"
        assert out["metadata"]["cloud_providers_used"] == []

    def test_summary_null_no_llm(self):
        """schema v2 D2: summary must be null (not absent) when no LLM."""
        out = self._minimal_output()
        assert "summary" in out
        assert out["summary"] is None

    def test_warnings_always_present(self):
        """schema v2 D4: warnings must always be present."""
        out = self._minimal_output()
        assert "warnings" in out
        assert out["warnings"] == []

    def test_no_network_calls(self):
        """
        Structural invariant: building schema v2 output makes zero network calls.

        We verify this by monkeypatching socket.connect and asserting it is
        never called during build_schema_v2_output().
        """
        import socket
        original_connect = socket.socket.connect

        calls = []

        def mock_connect(self, *args, **kwargs):
            calls.append(args)
            return original_connect(self, *args, **kwargs)

        socket.socket.connect = mock_connect
        try:
            self._minimal_output()
        finally:
            socket.socket.connect = original_connect

        assert calls == [], (
            f"build_schema_v2_output() made {len(calls)} network connection(s): {calls}"
        )

    def test_required_top_level_keys(self):
        required = {
            "schema_version", "generated_at", "wild_version", "diff_ref",
            "files", "symbols", "relationships", "metadata",
        }
        out = self._minimal_output()
        missing = required - set(out.keys())
        assert not missing, f"Missing required keys: {missing}"
