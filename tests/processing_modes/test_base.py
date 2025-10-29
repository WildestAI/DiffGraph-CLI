"""
Tests for base processor interface.
"""
import pytest
from diffgraph.processing_modes import BaseProcessor, DiffAnalysis


def test_base_processor_is_abstract():
    """Test that BaseProcessor cannot be instantiated directly."""
    with pytest.raises(TypeError):
        BaseProcessor()


def test_diff_analysis_model():
    """Test DiffAnalysis model creation."""
    analysis = DiffAnalysis(
        summary="Test summary",
        mermaid_diagram="graph LR\n    A --> B"
    )
    assert analysis.summary == "Test summary"
    assert "graph LR" in analysis.mermaid_diagram
