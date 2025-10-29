# Adding New Processing Modes

This guide explains how to add new processing modes to DiffGraph.

## Overview

Processing modes allow DiffGraph to analyze code changes from different perspectives. Each mode can focus on different aspects like:
- User context
- System architecture
- Module & component level interactions
- Data flow
- Abstract syntax tree analysis
- Dependency graphs

## Architecture

The processing mode system is built on:
1. **BaseProcessor**: Abstract base class that defines the interface
2. **Processor Registry**: Automatic registration of processing modes
3. **Factory Pattern**: `get_processor()` creates instances based on mode name

## Creating a New Processing Mode

### Step 1: Create Your Processor Class

Create a new file in `diffgraph/processing_modes/` (e.g., `tree_sitter_dependency.py`):

```python
from typing import List, Dict, Optional, Callable
from .base import BaseProcessor, DiffAnalysis
from . import register_processor

@register_processor("tree-sitter-dependency-graph")
class TreeSitterProcessor(BaseProcessor):
    """
    Processor using Tree-sitter for AST-based dependency analysis.
    """
    
    def __init__(self, **kwargs):
        """Initialize the processor with any required configuration."""
        super().__init__(**kwargs)
        # Initialize your tools/libraries here
        # self.parser = ...
    
    @property
    def name(self) -> str:
        """Return the mode identifier."""
        return "tree-sitter-dependency-graph"
    
    @property
    def description(self) -> str:
        """Return a human-readable description."""
        return "Uses Tree-sitter for AST-based dependency analysis"
    
    @classmethod
    def get_required_config(cls) -> List[str]:
        """List any required configuration parameters."""
        return []  # e.g., ["api_key", "model_name"]
    
    def analyze_changes(
        self,
        files_with_content: List[Dict[str, str]],
        progress_callback: Optional[Callable] = None
    ) -> DiffAnalysis:
        """
        Analyze code changes and generate diffgraph.
        
        Args:
            files_with_content: List of dicts with 'path', 'status', 'content'
            progress_callback: Optional callback(current_file, total_files, status)
        
        Returns:
            DiffAnalysis with 'summary' and 'mermaid_diagram'
        """
        # Your analysis logic here
        summary = "Analysis summary..."
        mermaid_diagram = "graph LR\\n    A --> B"
        
        return DiffAnalysis(
            summary=summary,
            mermaid_diagram=mermaid_diagram
        )
```

### Step 2: Register the Processor

Import your processor in `diffgraph/processing_modes/__init__.py`:

```python
# Add to the imports section at the bottom
from . import tree_sitter_dependency  # noqa: F401, E402
```

The `@register_processor` decorator automatically registers your mode.

### Step 3: Test Your Processor

```python
# Test your processor
from diffgraph.processing_modes import get_processor, list_available_modes

# Check it's registered
modes = list_available_modes()
assert "tree-sitter-dependency-graph" in modes

# Create an instance
processor = get_processor("tree-sitter-dependency-graph")

# Test analysis
files = [
    {
        "path": "test.py",
        "status": "modified",
        "content": "def hello(): pass"
    }
]
result = processor.analyze_changes(files)
print(result.summary)
print(result.mermaid_diagram)
```

### Step 4: Use via CLI

```bash
# List all modes
wild diff --list-modes

# Use your new mode
wild diff --mode tree-sitter-dependency-graph
```

## Best Practices

### 1. Progress Reporting
Use the `progress_callback` to report progress:

```python
if progress_callback:
    progress_callback(current_file, total_files, "processing")
```

Status values: `"processing"`, `"analyzing"`, `"processing_components"`, `"completed"`, `"error"`

### 2. Error Handling
Handle errors gracefully and provide useful error messages:

```python
try:
    # Your analysis code
    pass
except Exception as e:
    if progress_callback:
        progress_callback(current_file, total_files, "error")
    # Log or handle the error appropriately
```

### 3. Configuration
Define required configuration in `get_required_config()`:

```python
@classmethod
def get_required_config(cls) -> List[str]:
    return ["api_key", "model_name"]
```

The CLI will pass configuration via `**kwargs` to your `__init__` method.

### 4. Mermaid Diagram Generation
Generate valid Mermaid syntax for visualization:

```python
mermaid = ["graph LR"]
mermaid.append("    A[Component A] --> B[Component B]")
mermaid.append("    B --> C[Component C]")
return "\\n".join(mermaid)
```

### 5. Reusability
Consider using the existing `GraphManager` class for managing component graphs:

```python
from ..graph_manager import GraphManager, ChangeType

self.graph_manager = GraphManager()
self.graph_manager.add_file(file_path, ChangeType.MODIFIED)
self.graph_manager.add_component(name, file_path, change_type, ...)
mermaid_diagram = self.graph_manager.get_mermaid_diagram()
```

## Example Modes to Implement

### 1. Tree-sitter Dependency Graph
Focus: AST-based static analysis
- Use Tree-sitter for language-agnostic parsing
- Extract imports, function calls, class inheritance
- Build dependency graph from AST structure

### 2. Data Flow Analysis
Focus: How data flows through the code
- Track variable assignments and transformations
- Identify data sources and sinks
- Visualize data pipelines

### 3. User Context Analysis
Focus: User-facing changes
- Identify UI components and API endpoints
- Analyze user interaction flows
- Show impact on user experience

### 4. Architecture Analysis
Focus: System-level structure
- Identify modules and layers
- Analyze architectural patterns
- Show system component relationships

## Testing

Create tests in `tests/processing_modes/`:

```python
import pytest
from diffgraph.processing_modes import get_processor

def test_tree_sitter_processor():
    processor = get_processor("tree-sitter-dependency-graph")
    
    files = [{
        "path": "example.py",
        "status": "modified",
        "content": "def foo(): return 42"
    }]
    
    result = processor.analyze_changes(files)
    
    assert result.summary
    assert result.mermaid_diagram
    assert "graph" in result.mermaid_diagram
```

## Documentation

Update the README.md with your new mode:

```markdown
### Available Modes

#### `tree-sitter-dependency-graph`
Uses Tree-sitter for AST-based dependency analysis. This mode:
- Parses code using language-specific grammars
- Extracts structural dependencies from the AST
- Generates dependency graphs without AI
- Best for quick, deterministic analysis
```

## Questions?

If you have questions or need help implementing a new processing mode, please open an issue on GitHub.
