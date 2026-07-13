"""
Tests for base processor interface.
"""
import pytest
from diffgraph.processing_modes.base import BaseProcessor


def test_base_processor_is_abstract():
    """Test that BaseProcessor cannot be instantiated directly."""
    with pytest.raises(TypeError):
        BaseProcessor()  # type: ignore[abstract]


def test_base_processor_has_privacy_tier():
    """Test that BaseProcessor declares privacy_tier as an abstract property."""
    # Concrete subclass must implement privacy_tier; if omitted, instantiation fails.
    class _NoPrivacyTier(BaseProcessor):
        description = "test"

        @property
        def name(self) -> str:
            return "no-privacy-tier"

        def analyze_changes(self, files_with_content, progress_callback=None):
            return {}

    with pytest.raises(TypeError):
        _NoPrivacyTier()


def test_base_processor_description_class_attr():
    """list_available_modes() reads description as a class attr; verify it works."""
    class _ConcreteProcessor(BaseProcessor):
        description = "A test processor."

        @property
        def name(self) -> str:
            return "test"

        @property
        def privacy_tier(self) -> str:
            return "local"

        def analyze_changes(self, files_with_content, progress_callback=None):
            return {}

    assert _ConcreteProcessor.description == "A test processor."
