"""
Base processor interface for different diffgraph generation modes.

This module defines the abstract base class that all processing modes must implement.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Callable


class BaseProcessor(ABC):
    """
    Abstract base class for diffgraph processors.

    Each processing mode (e.g., Tree-sitter, OpenAI Agents, etc.) must inherit
    from this class and implement analyze_changes() and privacy_tier.

    Return type contract
    --------------------
    analyze_changes() returns a schema v2 DiffGraph dict.  The JSON Schema
    contract lives at diffgraph/schema/diffgraph-v2.schema.json.  No Pydantic
    model is imposed here — the schema file IS the contract.
    """

    # Class-level description; subclasses should override this string.
    description: str = "No description provided."

    def __init__(self, **kwargs):
        """
        Initialize the processor with configuration options.

        Args:
            **kwargs: Configuration parameters specific to the processor
        """
        self.config = kwargs

    @abstractmethod
    def analyze_changes(
        self,
        files_with_content: List[Dict[str, str]],
        progress_callback: Optional[Callable] = None,
    ) -> Dict[str, Any]:
        """
        Analyze code changes and return a schema v2 DiffGraph dict.

        Args:
            files_with_content: List of dicts with keys:
                - path: File path
                - status: Change status (modified, untracked, etc.)
                - content: File content or diff
            progress_callback: Optional (current_file, total_files, status) callback.

        Returns:
            dict — a schema v2 DiffGraph dict validated against
            diffgraph/schema/diffgraph-v2.schema.json.
        """
        pass

    @property
    @abstractmethod
    def privacy_tier(self) -> str:
        """
        Privacy tier for this processor.  One of:

        "local"          — No data leaves the machine.
        "cloud_llm"      — Diff sent to a third-party LLM API.
                           Requires user consent before first use.
        "cloud_backend"  — Diff sent to the WildestAI backend.
                           Requires user consent before first use.
        """
        pass

    @property
    @abstractmethod
    def name(self) -> str:
        """Return the name/identifier of this processing mode."""
        pass
    
    @property
    @abstractmethod
    def description(self) -> str:
        """Return a human-readable description of this processing mode."""
        pass
    
    @classmethod
    def get_required_config(cls) -> List[str]:
        """
        Return list of required configuration parameters for this processor.
        
        Returns:
            List of configuration parameter names
        """
        return []
