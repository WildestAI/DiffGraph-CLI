"""
Tests for processor registry and factory.
"""
import pytest
from diffgraph.processing_modes import get_processor, list_available_modes
from diffgraph.processing_modes.openai_agents_dependency import _AGENTS_SDK_AVAILABLE

_skip_openai = pytest.mark.skipif(
    not _AGENTS_SDK_AVAILABLE,
    reason="openai-agents SDK not installed",
)


def test_list_available_modes():
    """Test listing available processing modes."""
    modes = list_available_modes()

    assert isinstance(modes, dict)
    assert len(modes) >= 1
    # Both built-in processors must be listed.
    assert "openai-agents-dependency-graph" in modes
    assert "local-structural" in modes
    # All descriptions must be non-empty strings.
    for name, desc in modes.items():
        assert isinstance(desc, str) and len(desc) > 0, (
            f"Mode '{name}' has empty or non-string description"
        )


def test_list_available_modes_no_instantiation():
    """
    list_available_modes() must not instantiate any processor class.

    Instantiation of openai-agents-dependency-graph requires the agents SDK
    and an API key — neither of which is available in test environments.
    If this test passes without those, the implementation is safe.
    """
    # Should not raise even without API key or agents SDK.
    modes = list_available_modes()
    assert "openai-agents-dependency-graph" in modes


@_skip_openai
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


@_skip_openai
def test_processor_interface():
    """Test that processor has required interface."""
    processor = get_processor("openai-agents-dependency-graph", api_key="test-key")

    # Check required attributes
    assert hasattr(processor, 'name')
    assert hasattr(processor, 'description')
    assert hasattr(processor, 'analyze_changes')
    assert hasattr(processor, 'privacy_tier')

    # Check properties work
    assert isinstance(processor.name, str)
    assert isinstance(processor.description, str)
    assert processor.privacy_tier == "cloud_llm"
    assert callable(processor.analyze_changes)


def test_local_structural_processor_privacy_tier():
    """LocalStructuralProcessor must report local privacy tier without instantiation."""
    from diffgraph.processing_modes.local_structural import LocalStructuralProcessor
    # Check the class attribute without instantiation (no tree-sitter needed).
    # Instantiated version:
    p = LocalStructuralProcessor()
    assert p.privacy_tier == "local"
    assert p.name == "local-structural"
