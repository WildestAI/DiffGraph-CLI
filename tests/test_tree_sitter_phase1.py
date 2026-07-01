"""
Phase 1 acceptance tests for TreeSitterProcessor — schema v2 output.

Verifies the acceptance criteria from V2-IMPLEMENTATION-ROADMAP.md Phase 1:
  - analyze_changes() returns a schema v2 dict (not GraphManager / DiffAnalysis)
  - privacy_tier == "local"
  - Output validates against diffgraph-v2.schema.json
  - relationships[] includes import relationships for Python files
  - metadata.analysis_duration_ms is present
  - 21 existing schema v2 adapter tests still pass (run separately)
  - Zero network calls (covered by test_schema_v2_adapter.py::test_no_network_calls)
"""

import json
import os
import tempfile
import textwrap
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Optional jsonschema — skip validation test if not installed
# ---------------------------------------------------------------------------
try:
    import jsonschema
    HAS_JSONSCHEMA = True
except ImportError:
    HAS_JSONSCHEMA = False

# ---------------------------------------------------------------------------
# Optional tree-sitter — skip all tests if not installed
# ---------------------------------------------------------------------------
try:
    from diffgraph.processing_modes.tree_sitter_dependency import TreeSitterProcessor
    HAS_TREE_SITTER = True
except ImportError:
    HAS_TREE_SITTER = False

pytestmark = pytest.mark.skipif(
    not HAS_TREE_SITTER,
    reason="tree-sitter-language-pack not installed",
)

SCHEMA_PATH = Path(__file__).parent.parent / "diffgraph" / "schema" / "diffgraph-v2.schema.json"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SIMPLE_PYTHON_FILE = textwrap.dedent("""\
    import os
    import sys

    class Greeter:
        def greet(self, name: str) -> str:
            return f"Hello, {name}!"

    def main():
        g = Greeter()
        print(g.greet("world"))
""")

MODIFIED_PYTHON_FILE = textwrap.dedent("""\
    import os
    import sys
    import logging

    class Greeter:
        def greet(self, name: str) -> str:
            logging.info("greeting %s", name)
            return f"Hello, {name}!"

    def main():
        g = Greeter()
        print(g.greet("world"))

    def setup():
        logging.basicConfig(level=logging.INFO)
""")


def _make_file_data(path: str, content: str, status: str = "modified") -> dict:
    return {"path": path, "status": status, "content": content}


def _make_processor_with_tmp_git(tmp_path: Path) -> "TreeSitterProcessor":
    """
    Create a TreeSitterProcessor whose _get_pre/post helpers will
    fall back gracefully (we mock with a non-git cwd).
    """
    return TreeSitterProcessor()


# ---------------------------------------------------------------------------
# 1. analyze_changes() returns a dict, not DiffAnalysis
# ---------------------------------------------------------------------------

class TestAnalyzeChangesReturnType:
    def test_returns_dict(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        processor = TreeSitterProcessor()
        result = processor.analyze_changes(
            [_make_file_data("auth/validator.py", SIMPLE_PYTHON_FILE, "added")]
        )
        assert isinstance(result, dict), (
            f"analyze_changes() must return dict, got {type(result)}"
        )

    def test_has_schema_version_key(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        processor = TreeSitterProcessor()
        result = processor.analyze_changes(
            [_make_file_data("auth/validator.py", SIMPLE_PYTHON_FILE, "added")]
        )
        assert result.get("schema_version") == "2.0", (
            "schema_version must be '2.0'"
        )

    def test_has_required_top_level_keys(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        processor = TreeSitterProcessor()
        result = processor.analyze_changes(
            [_make_file_data("auth/validator.py", SIMPLE_PYTHON_FILE, "added")]
        )
        required = {"schema_version", "generated_at", "wild_version", "diff_ref",
                    "files", "symbols", "relationships", "metadata"}
        missing = required - set(result.keys())
        assert not missing, f"Missing top-level keys: {missing}"


# ---------------------------------------------------------------------------
# 2. privacy_tier == "local"
# ---------------------------------------------------------------------------

class TestPrivacyTier:
    def test_privacy_tier_property(self):
        processor = TreeSitterProcessor()
        assert processor.privacy_tier == "local"

    def test_metadata_privacy_tier_in_output(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        processor = TreeSitterProcessor()
        result = processor.analyze_changes(
            [_make_file_data("auth/validator.py", SIMPLE_PYTHON_FILE, "added")]
        )
        assert result["metadata"]["privacy_tier"] == "local"

    def test_cloud_providers_empty(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        processor = TreeSitterProcessor()
        result = processor.analyze_changes(
            [_make_file_data("auth/validator.py", SIMPLE_PYTHON_FILE, "added")]
        )
        assert result["metadata"]["cloud_providers_used"] == []


# ---------------------------------------------------------------------------
# 3. analysis_duration_ms is present
# ---------------------------------------------------------------------------

class TestAnalysisDuration:
    def test_duration_present_and_non_negative(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        processor = TreeSitterProcessor()
        result = processor.analyze_changes(
            [_make_file_data("auth/validator.py", SIMPLE_PYTHON_FILE, "added")]
        )
        duration = result["metadata"].get("analysis_duration_ms")
        assert duration is not None, "analysis_duration_ms must be present"
        assert isinstance(duration, int), "analysis_duration_ms must be int"
        assert duration >= 0, "analysis_duration_ms must be non-negative"


# ---------------------------------------------------------------------------
# 4. relationships[] includes import relationships for Python files
# ---------------------------------------------------------------------------

class TestImportRelationships:
    def test_import_relationships_present_for_python(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        processor = TreeSitterProcessor()
        # MODIFIED_PYTHON_FILE imports os, sys, logging
        result = processor.analyze_changes(
            [_make_file_data("api/routes.py", MODIFIED_PYTHON_FILE, "added")]
        )
        relationships = result.get("relationships", [])
        import_rels = [r for r in relationships if r.get("kind") == "imports"]
        assert len(import_rels) >= 1, (
            f"Expected import relationships for Python imports (os/sys/logging), "
            f"got 0 from {len(relationships)} total relationships"
        )

    def test_import_relationships_have_structural_source(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        processor = TreeSitterProcessor()
        result = processor.analyze_changes(
            [_make_file_data("api/routes.py", MODIFIED_PYTHON_FILE, "added")]
        )
        for rel in result.get("relationships", []):
            if rel.get("kind") == "imports":
                assert rel.get("analysis_source") == "structural", (
                    f"Import relationship must have analysis_source='structural': {rel}"
                )

    def test_no_relationships_for_non_python_file(self, tmp_path, monkeypatch):
        """Non-Python files (unsupported extension) should not crash."""
        monkeypatch.chdir(tmp_path)
        processor = TreeSitterProcessor()
        result = processor.analyze_changes(
            [_make_file_data("README.md", "# Hello", "added")]
        )
        assert isinstance(result.get("relationships"), list)


# ---------------------------------------------------------------------------
# 5. symbols[] are populated for Python files
# ---------------------------------------------------------------------------

class TestSymbols:
    def test_symbols_present_for_added_python_file(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        processor = TreeSitterProcessor()
        result = processor.analyze_changes(
            [_make_file_data("auth/validator.py", SIMPLE_PYTHON_FILE, "added")]
        )
        symbols = result.get("symbols", [])
        assert len(symbols) >= 1, "Expected at least one symbol for Python file"

    def test_added_file_symbols_have_change_kind_added(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        processor = TreeSitterProcessor()
        result = processor.analyze_changes(
            [_make_file_data("auth/validator.py", SIMPLE_PYTHON_FILE, "added")]
        )
        for sym in result.get("symbols", []):
            assert sym.get("change_kind") == "added", (
                f"New-file symbol should be 'added', got '{sym.get('change_kind')}': {sym}"
            )

    def test_symbols_have_analysis_source_structural(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        processor = TreeSitterProcessor()
        result = processor.analyze_changes(
            [_make_file_data("auth/validator.py", SIMPLE_PYTHON_FILE, "added")]
        )
        for sym in result.get("symbols", []):
            assert sym.get("analysis_source") == "structural", (
                f"Tree-sitter symbols must be structural: {sym}"
            )

    def test_empty_files_list_returns_valid_output(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        processor = TreeSitterProcessor()
        result = processor.analyze_changes([])
        assert result.get("symbols") == []
        assert result.get("relationships") == []
        assert result.get("files") == []


# ---------------------------------------------------------------------------
# 6. Output validates against diffgraph-v2.schema.json
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not HAS_JSONSCHEMA, reason="jsonschema not installed")
@pytest.mark.skipif(not SCHEMA_PATH.exists(), reason="schema file not found on branch")
class TestSchemaValidation:
    @pytest.fixture(scope="class")
    def schema(self):
        return json.loads(SCHEMA_PATH.read_text())

    def test_added_file_validates_against_schema(self, schema, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        processor = TreeSitterProcessor()
        result = processor.analyze_changes(
            [_make_file_data("auth/validator.py", SIMPLE_PYTHON_FILE, "added")]
        )
        jsonschema.validate(result, schema)   # raises jsonschema.ValidationError if invalid

    def test_empty_diff_validates_against_schema(self, schema, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        processor = TreeSitterProcessor()
        result = processor.analyze_changes([])
        jsonschema.validate(result, schema)

    def test_multi_file_diff_validates_against_schema(self, schema, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        processor = TreeSitterProcessor()
        result = processor.analyze_changes([
            _make_file_data("auth/validator.py", SIMPLE_PYTHON_FILE, "added"),
            _make_file_data("api/routes.py", MODIFIED_PYTHON_FILE, "modified"),
        ])
        jsonschema.validate(result, schema)
