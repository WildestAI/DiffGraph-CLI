"""
Tests for processor registry and factory.
"""
import pytest
from diffgraph.processing_modes import get_processor, list_available_modes


def test_list_available_modes():
    """Test listing available processing modes."""
    modes = list_available_modes()
    
    assert isinstance(modes, dict)
    assert len(modes) >= 1
    assert "openai-agents-dependency-graph" in modes
    assert isinstance(modes["openai-agents-dependency-graph"], str)
    assert len(modes["openai-agents-dependency-graph"]) > 0


def test_get_processor_success():
    """Test getting a processor instance."""
    processor = get_processor("openai-agents-dependency-graph", api_key="test-key")
    
    assert processor is not None
    assert processor.name == "openai-agents-dependency-graph"
    assert hasattr(processor, 'analyze_changes')
    assert callable(processor.analyze_changes)


def test_get_processor_invalid_mode():
    """Test that getting an invalid processor raises ValueError."""
    with pytest.raises(ValueError) as exc_info:
        get_processor("non-existent-mode")
    
    assert "Unknown processing mode" in str(exc_info.value)
    assert "non-existent-mode" in str(exc_info.value)


def test_processor_interface():
    """Test that processor has required interface."""
    processor = get_processor("openai-agents-dependency-graph", api_key="test-key")
    
    # Check required attributes
    assert hasattr(processor, 'name')
    assert hasattr(processor, 'description')
    assert hasattr(processor, 'analyze_changes')
    
    # Check properties work
    assert isinstance(processor.name, str)
    assert isinstance(processor.description, str)
    assert callable(processor.analyze_changes)
