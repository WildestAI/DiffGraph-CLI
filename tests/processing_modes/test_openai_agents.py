"""
Tests for OpenAI Agents processor.

Tests that require the OpenAI Agents SDK are skipped automatically when the
'agents' package is not installed (e.g. in CI or local-only environments).
"""
import pytest
from diffgraph.processing_modes import get_processor
from diffgraph.processing_modes.openai_agents_dependency import _AGENTS_SDK_AVAILABLE

pytestmark = pytest.mark.skipif(
    not _AGENTS_SDK_AVAILABLE,
    reason="openai-agents SDK not installed",
)


def test_openai_processor_initialization():
    """Test OpenAI processor can be initialized."""
    processor = get_processor("openai-agents-dependency-graph", api_key="test-key")
    
    assert processor.name == "openai-agents-dependency-graph"
    assert "OpenAI" in processor.description
    assert hasattr(processor, 'graph_manager')


def test_openai_processor_requires_api_key():
    """Test that OpenAI processor requires API key."""
    with pytest.raises(ValueError) as exc_info:
        get_processor("openai-agents-dependency-graph")
    
    assert "API key" in str(exc_info.value)


def test_openai_processor_metadata():
    """Test OpenAI processor metadata."""
    processor = get_processor("openai-agents-dependency-graph", api_key="test-key")
    
    assert processor.name == "openai-agents-dependency-graph"
    assert len(processor.description) > 0
    assert "dependency" in processor.description.lower()
    assert "component" in processor.description.lower()
