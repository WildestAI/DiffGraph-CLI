"""
Processing modes module for different diffgraph generation strategies.

This module provides a registry of available processing modes and factory
functions to create processor instances.
"""

from typing import Dict, Type, Optional
from .base import BaseProcessor

# Registry of available processing modes
_PROCESSOR_REGISTRY: Dict[str, Type[BaseProcessor]] = {}


def register_processor(mode_name: str):
    """
    Decorator to register a processor class.
    
    Args:
        mode_name: The name identifier for this processing mode
        
    Example:
        @register_processor("openai-agents-dependency-graph")
        class OpenAIAgentsProcessor(BaseProcessor):
            ...
    """
    def decorator(cls: Type[BaseProcessor]):
        _PROCESSOR_REGISTRY[mode_name] = cls
        return cls
    return decorator


def get_processor(mode_name: str, **kwargs) -> BaseProcessor:
    """
    Factory function to create a processor instance.
    
    Args:
        mode_name: The name of the processing mode
        **kwargs: Configuration parameters for the processor
        
    Returns:
        An instance of the requested processor
        
    Raises:
        ValueError: If the mode_name is not registered
    """
    if mode_name not in _PROCESSOR_REGISTRY:
        available_modes = ", ".join(_PROCESSOR_REGISTRY.keys())
        raise ValueError(
            f"Unknown processing mode: '{mode_name}'. "
            f"Available modes: {available_modes}"
        )
    
    processor_class = _PROCESSOR_REGISTRY[mode_name]
    return processor_class(**kwargs)


def list_available_modes() -> Dict[str, str]:
    """
    Return a dict of {mode_name: description} for all registered processors.

    Uses the class-level ``description`` attribute so no instantiation is
    required (avoids unsafe ``__new__`` and missing-arg errors).
    """
    return {
        name: cls.description
        for name, cls in _PROCESSOR_REGISTRY.items()
    }


# Import processors to trigger registration
from . import openai_agents_dependency  # noqa: F401, E402
from . import local_structural           # noqa: F401, E402


__all__ = [
    "BaseProcessor",
    "register_processor",
    "get_processor",
    "list_available_modes",
]
