"""
Base processor interface for different diffgraph generation modes.

This module defines the abstract base class that all processing modes must implement.
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Optional, Callable
from pydantic import BaseModel


class DiffAnalysis(BaseModel):
    """Model representing the analysis of code changes."""
    summary: str
    mermaid_diagram: str


class BaseProcessor(ABC):
    """
    Abstract base class for diffgraph processors.
    
    Each processing mode (e.g., OpenAI Agents, Tree-sitter, etc.) should inherit
    from this class and implement the analyze_changes method.
    """
    
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
        progress_callback: Optional[Callable] = None
    ) -> DiffAnalysis:
        """
        Analyze code changes and generate a diffgraph.
        
        Args:
            files_with_content: List of dictionaries containing:
                - path: File path
                - status: Change status (modified, untracked, etc.)
                - content: File content or diff
            progress_callback: Optional callback function to report progress.
                             Should accept (current_file, total_files, status)
        
        Returns:
            DiffAnalysis object containing summary and mermaid diagram
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
