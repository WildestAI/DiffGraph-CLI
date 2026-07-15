"""
Tests for schema-v2 DiffGraph export.

Phase 3 acceptance criteria:
  - Output conforms to JSON schema v2 (symbols[]/relationships[])
  - analysis_source: "inferred" on every symbol and relationship
  - change_kind (not change_type) with v2 values
  - metadata.privacy_tier present
  - schema_version: "2.0" at top level
  - File classification preserved as FileEntry.category
  - Per-file additions/deletions preserved under FileEntry.stats
  - Language detection preserved under metadata.languages_detected
  - Output validates against diffgraph-v2.schema.json when jsonschema is installed

Zero network calls.  All tests use a hand-built GraphManager.
"""

import json
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest

from diffgraph.graph_manager import GraphManager, ChangeType
from diffgraph.structured_export import (
    transform_to_diffgraph_v2,
    export_diffgraph_v2,
    _diff_ref_from_args,
    _file_id,
    _sym_id,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SCHEMA_PATH = Path(__file__).parent.parent / 'diffgraph' / 'schema' / 'diffgraph-v2.schema.json'


def _make_graph_manager(
    files: dict | None = None,
    components: dict | None = None,
    file_edges: list | None = None,
    comp_edges: list | None = None,
) -> GraphManager:
    """Build a minimal GraphManager for testing without running git or AI."""
    gm = GraphManager()

    for path, change_type in (files or {}).items():
        node = MagicMock()
        node.change_type = change_type
        node.summary = f'Summary of {path}'
        gm.file_nodes[path] = node
        gm.file_graph.add_node(path)

    for comp_id, spec in (components or {}).items():
        node = MagicMock()
        node.name = spec['name']
        node.component_type = spec.get('type', 'function')
        node.change_type = spec.get('change_type', ChangeType.MODIFIED)
        node.file_path = spec['file']
        node.parent = spec.get('parent')
        node.summary = spec.get('summary', '')
        node.dependencies = []
        node.dependents = []
        gm.component_nodes[comp_id] = node
        gm.component_graph.add_node(comp_id)

    for src, tgt in (file_edges or []):
        gm.file_graph.add_edge(src, tgt)

    for src, tgt in (comp_edges or []):
        gm.component_graph.add_edge(src, tgt)

    return gm


# ---------------------------------------------------------------------------
# diff_ref helpers
# ---------------------------------------------------------------------------

class TestDiffRefFromArgs:
    def test_no_args_is_unstaged(self):
        ref = _diff_ref_from_args([])
        assert ref['kind'] == 'unstaged'
        assert ref['base_ref'] is None
        assert ref['head_ref'] is None

    def test_staged_flag(self):
        ref = _diff_ref_from_args(['--staged'])
        assert ref['kind'] == 'staged'
        assert ref['base_ref'] == 'HEAD'

    def test_cached_flag(self):
        ref = _diff_ref_from_args(['--cached'])
        assert ref['kind'] == 'staged'

    def test_commit_range_two_args(self):
        ref = _diff_ref_from_args(['main', 'HEAD'])
        assert ref['kind'] == 'commit_range'
        assert ref['base_ref'] == 'main'
        assert ref['head_ref'] == 'HEAD'

    def test_commit_range_dotdot(self):
        ref = _diff_ref_from_args(['abc123..def456'])
        assert ref['kind'] == 'commit_range'
        assert ref['base_ref'] == 'abc123'
        assert ref['head_ref'] == 'def456'

    def test_commit_range_dotdotdot(self):
        ref = _diff_ref_from_args(['main...feature'])
        assert ref['kind'] == 'commit_range'
        assert ref['base_ref'] == 'main'
        assert ref['head_ref'] == 'feature'


# ---------------------------------------------------------------------------
# transform_to_diffgraph_v2
# ---------------------------------------------------------------------------

class TestTransformToDiffgraphV2:
    """Tests for the core transform function."""

    def _make_simple_gm(self) -> GraphManager:
        return _make_graph_manager(
            files={
                'auth/validator.py': ChangeType.MODIFIED,
                'tests/test_validator.py': ChangeType.ADDED,
            },
            components={
                'validate_token': {
                    'name': 'validate_token',
                    'type': 'function',
                    'change_type': ChangeType.MODIFIED,
                    'file': 'auth/validator.py',
                    'summary': 'Validates JWT token',
                },
                'RateLimiter': {
                    'name': 'RateLimiter',
                    'type': 'class',
                    'change_type': ChangeType.ADDED,
                    'file': 'auth/validator.py',
                    'summary': 'New rate limiter class',
                },
            },
            comp_edges=[('validate_token', 'RateLimiter')],
        )

    def test_top_level_schema_version(self):
        gm = self._make_simple_gm()
        out = transform_to_diffgraph_v2(gm, [])
        assert out['schema_version'] == '2.0'

    def test_generated_at_present(self):
        gm = self._make_simple_gm()
        out = transform_to_diffgraph_v2(gm, [])
        assert 'generated_at' in out
        assert out['generated_at'].endswith('+00:00') or 'Z' in out['generated_at'] or 'T' in out['generated_at']

    def test_required_top_level_keys(self):
        gm = self._make_simple_gm()
        out = transform_to_diffgraph_v2(gm, [])
        for key in ('schema_version', 'generated_at', 'wild_version', 'diff_ref',
                    'files', 'symbols', 'relationships', 'metadata'):
            assert key in out, f'Missing top-level key: {key}'

    def test_warnings_in_metadata_not_top_level(self):
        """schema v2 puts warnings inside metadata, not at the document root."""
        gm = self._make_simple_gm()
        out = transform_to_diffgraph_v2(gm, [])
        assert 'warnings' not in out, 'warnings should be inside metadata, not top-level'
        assert 'warnings' in out['metadata']

    def test_files_count(self):
        gm = self._make_simple_gm()
        out = transform_to_diffgraph_v2(gm, [])
        assert len(out['files']) == 2

    def test_file_entry_required_fields(self):
        gm = self._make_simple_gm()
        out = transform_to_diffgraph_v2(gm, [])
        for f in out['files']:
            assert 'id' in f
            assert f['id'].startswith('file::')
            assert 'path' in f
            assert 'change_kind' in f
            assert f['change_kind'] in ('added', 'modified', 'deleted', 'unchanged')
            # File analysis_source is always 'structural' (schema const)
            assert f['analysis_source'] == 'structural'

    def test_file_entry_has_classification(self):
        gm = self._make_simple_gm()
        out = transform_to_diffgraph_v2(gm, [])
        for f in out['files']:
            assert 'classification' in f
            assert 'is_test' in f['classification']
            assert isinstance(f['classification']['is_test'], bool)

    def test_test_file_classified_as_test(self):
        gm = self._make_simple_gm()  # includes tests/test_validator.py
        out = transform_to_diffgraph_v2(gm, [])
        test_files = [f for f in out['files'] if 'test' in f['path']]
        assert test_files, 'Expected at least one test file'
        for f in test_files:
            assert f['classification']['is_test'] is True

    def test_file_entry_has_lines_added_removed(self):
        gm = self._make_simple_gm()
        with patch('diffgraph.structured_export.get_file_stats', return_value={'additions': 10, 'deletions': 3}):
            out = transform_to_diffgraph_v2(gm, [])
        for f in out['files']:
            assert 'lines_added' in f
            assert 'lines_removed' in f
            assert f['lines_added'] == 10
            assert f['lines_removed'] == 3

    def test_symbols_count(self):
        gm = self._make_simple_gm()
        out = transform_to_diffgraph_v2(gm, [])
        assert len(out['symbols']) == 2

    def test_symbol_required_fields(self):
        gm = self._make_simple_gm()
        out = transform_to_diffgraph_v2(gm, [])
        for sym in out['symbols']:
            assert sym['id'].startswith('sym::')
            assert 'name' in sym
            assert 'file_id' in sym
            assert sym['file_id'].startswith('file::')
            assert 'kind' in sym
            assert 'change_kind' in sym
            assert sym['change_kind'] in ('added', 'modified', 'deleted', 'unchanged')
            assert sym['analysis_source'] == 'inferred'

    def test_symbol_analysis_source_always_inferred(self):
        gm = self._make_simple_gm()
        out = transform_to_diffgraph_v2(gm, [])
        for sym in out['symbols']:
            assert sym['analysis_source'] == 'inferred'

    def test_symbol_evidence_present(self):
        gm = self._make_simple_gm()
        out = transform_to_diffgraph_v2(gm, [])
        for sym in out['symbols']:
            assert 'evidence' in sym
            assert isinstance(sym['evidence'], list)
            assert len(sym['evidence']) >= 1
            assert sym['evidence'][0]['kind'] == 'llm_inference'

    def test_change_kind_not_change_type(self):
        """Schema v2 uses 'change_kind', not 'change_type'."""
        gm = self._make_simple_gm()
        out = transform_to_diffgraph_v2(gm, [])
        for sym in out['symbols']:
            assert 'change_kind' in sym
            assert 'change_type' not in sym
        for f in out['files']:
            assert 'change_kind' in f
            assert 'change_type' not in f

    def test_relationships_from_component_edges(self):
        gm = self._make_simple_gm()
        out = transform_to_diffgraph_v2(gm, [])
        assert len(out['relationships']) >= 1

    def test_relationship_required_fields(self):
        gm = self._make_simple_gm()
        out = transform_to_diffgraph_v2(gm, [])
        for rel in out['relationships']:
            assert rel['id'].startswith('rel::')
            assert 'kind' in rel
            assert 'source_id' in rel
            assert 'target_id' in rel
            assert rel['analysis_source'] == 'inferred'

    def test_relationship_analysis_source_always_inferred(self):
        gm = self._make_simple_gm()
        out = transform_to_diffgraph_v2(gm, [])
        for rel in out['relationships']:
            assert rel['analysis_source'] == 'inferred'

    def test_metadata_privacy_tier_present(self):
        gm = self._make_simple_gm()
        out = transform_to_diffgraph_v2(gm, [], privacy_tier='cloud_llm')
        assert out['metadata']['privacy_tier'] == 'cloud_llm'

    def test_metadata_privacy_tier_local(self):
        gm = self._make_simple_gm()
        out = transform_to_diffgraph_v2(gm, [], privacy_tier='local')
        assert out['metadata']['privacy_tier'] == 'local'
        assert out['metadata']['cloud_providers_used'] == []

    def test_metadata_languages_detected(self):
        gm = self._make_simple_gm()
        out = transform_to_diffgraph_v2(gm, [])
        assert 'languages_detected' in out['metadata']
        assert 'python' in out['metadata']['languages_detected']

    def test_metadata_analysis_duration_ms(self):
        gm = self._make_simple_gm()
        out = transform_to_diffgraph_v2(gm, [], analysis_duration_ms=840)
        assert out['metadata']['analysis_duration_ms'] == 840

    def test_empty_graph_manager(self):
        """Empty GraphManager produces valid (empty) output."""
        gm = GraphManager()
        out = transform_to_diffgraph_v2(gm, [])
        assert out['schema_version'] == '2.0'
        assert out['files'] == []
        assert out['symbols'] == []
        assert out['relationships'] == []

    def test_file_id_format(self):
        assert _file_id('auth/validator.py') == 'file::auth/validator.py'

    def test_sym_id_format(self):
        assert _sym_id('auth/validator.py', 'validate_token') == 'sym::auth/validator.py::validate_token'


# ---------------------------------------------------------------------------
# Schema validation (requires jsonschema)
# ---------------------------------------------------------------------------

class TestSchemaValidation:
    """Validate output against the bundled diffgraph-v2.schema.json."""

    @pytest.mark.skipif(not SCHEMA_PATH.exists(), reason='Schema file not present')
    def test_output_validates_against_schema(self):
        jsonschema = pytest.importorskip('jsonschema')
        with open(SCHEMA_PATH) as f:
            schema = json.load(f)

        gm = _make_graph_manager(
            files={
                'auth/validator.py': ChangeType.MODIFIED,
            },
            components={
                'validate_token': {
                    'name': 'validate_token',
                    'type': 'function',
                    'change_type': ChangeType.MODIFIED,
                    'file': 'auth/validator.py',
                },
            },
        )

        with patch('diffgraph.structured_export.get_file_stats',
                   return_value={'additions': 5, 'deletions': 2}):
            with patch('subprocess.run') as mock_run:
                mock_run.return_value = MagicMock(returncode=0, stdout='/repo')
                out = transform_to_diffgraph_v2(gm, [])

        jsonschema.validate(out, schema)

    @pytest.mark.skipif(not SCHEMA_PATH.exists(), reason='Schema file not present')
    def test_empty_output_validates_against_schema(self):
        jsonschema = pytest.importorskip('jsonschema')
        with open(SCHEMA_PATH) as f:
            schema = json.load(f)

        gm = GraphManager()
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout='/repo')
            out = transform_to_diffgraph_v2(gm, [])

        jsonschema.validate(out, schema)


# ---------------------------------------------------------------------------
# export_diffgraph_v2 (file I/O)
# ---------------------------------------------------------------------------

class TestExportDiffgraphV2:
    def test_writes_json_file(self, tmp_path):
        gm = _make_graph_manager(
            files={'main.py': ChangeType.ADDED},
        )
        out_file = str(tmp_path / 'out.json')
        with patch('diffgraph.structured_export.get_file_stats',
                   return_value={'additions': 1, 'deletions': 0}):
            with patch('subprocess.run') as mock_run:
                mock_run.return_value = MagicMock(returncode=0, stdout=str(tmp_path))
                path = export_diffgraph_v2(gm, out_file)

        assert Path(path).exists()
        with open(path) as f:
            data = json.load(f)
        assert data['schema_version'] == '2.0'

    def test_creates_parent_directories(self, tmp_path):
        gm = GraphManager()
        out_file = str(tmp_path / 'nested' / 'dir' / 'out.json')
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout=str(tmp_path))
            path = export_diffgraph_v2(gm, out_file)
        assert Path(path).exists()

    def test_returns_absolute_path(self, tmp_path):
        gm = GraphManager()
        out_file = str(tmp_path / 'out.json')
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout=str(tmp_path))
            path = export_diffgraph_v2(gm, out_file)
        assert Path(path).is_absolute()
