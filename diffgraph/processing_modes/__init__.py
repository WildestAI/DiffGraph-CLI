"""
Processing modes module for different diffgraph generation strategies.

This module provides a registry of available processing modes and factory
functions to create processor instances.
"""

from typing import Dict, Type, Optional
from .base import BaseProcessor, DiffAnalysis

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
    Get a dictionary of available processing modes and their descriptions.
    
    Returns:
        Dictionary mapping mode names to descriptions
    """
    modes = {}
    for mode_name, processor_class in _PROCESSOR_REGISTRY.items():
        # Get description by creating a minimal instance
        try:
            # Try to create instance without required parameters to get description
            # Most processors should allow getting description without full initialization
            temp_instance = processor_class.__new__(processor_class)
            if hasattr(temp_instance, 'description'):
                desc = temp_instance.description
                if isinstance(desc, property):
                    # For property descriptors, we need to access via class
                    description = processor_class.description.fget(temp_instance)
                else:
                    description = desc
            else:
                description = "No description available"
        except Exception as e:
            # Fallback: try to get from docstring or use default
            description = processor_class.__doc__.split('\n')[0] if processor_class.__doc__ else "No description available"
        modes[mode_name] = description
    return modes


# Import processors to trigger registration
# This will be populated as we add more processors
from . import openai_agents_dependency  # noqa: F401, E402


__all__ = [
    "BaseProcessor",
    "DiffAnalysis",
    "register_processor",
    "get_processor",
    "list_available_modes",
]
