# Graph Export Feature

## Overview

The DiffGraph CLI now supports exporting the complete networkx graph data structure directly to a file, allowing other programs to programmatically access and analyze the code change data.

## What's New

### CLI Options

- `--format` / `-f`: Choose output format (`html` or `graph`)
- `--graph-format`: Choose serialization format for graph export (`json`, `pickle`, or `graphml`)
- `--output` / `-o`: Output file path (auto-detects extension based on format)

### Usage Examples

```bash
# Export as JSON (default for graph format)
wild diff --format graph --output analysis.json

# Export as pickle
wild diff --format graph --graph-format pickle --output analysis.pkl

# Export as GraphML
wild diff --format graph --graph-format graphml --output analysis.graphml

# HTML output still works as before (default)
wild diff --output report.html
```

## Exported Data Structure

The exported graph data includes:

1. **File Nodes**: All analyzed files with their metadata
   - Path
   - Status (pending/processing/processed/error)
   - Change type (added/deleted/modified/unchanged)
   - Summary
   - Components list

2. **Component Nodes**: All code components (classes, functions, methods)
   - Name
   - File path
   - Change type
   - Component type (container/function/method)
   - Parent component (for nested components)
   - Summary
   - Dependencies
   - Dependents

3. **Graph Structures**: NetworkX directed graphs
   - File dependency graph
   - Component dependency graph

4. **Metadata**
   - Version information
   - Processing status
   - List of processed files

## JSON Format Example

```json
{
  "version": "1.0",
  "file_nodes": {
    "app/main.py": {
      "path": "app/main.py",
      "status": "processed",
      "change_type": "modified",
      "summary": "Modified main application file",
      "error": null,
      "components": []
    }
  },
  "component_nodes": {
    "app/main.py::MyClass": {
      "name": "MyClass",
      "file_path": "app/main.py",
      "change_type": "modified",
      "component_type": "container",
      "parent": null,
      "summary": "Main application class",
      "dependencies": [],
      "dependents": []
    }
  },
  "file_graph": { ... },
  "component_graph": { ... },
  "processed_files": ["app/main.py"]
}
```

## Using Exported Data

### Loading Graph Data

```python
from diffgraph.graph_export import load_graph_from_json

# Load exported data
graph_manager = load_graph_from_json('analysis.json')

# Access file information
for file_path, file_node in graph_manager.file_nodes.items():
    print(f"{file_path}: {file_node.change_type.value}")

# Access component information
for component_id, component in graph_manager.component_nodes.items():
    print(f"{component.name}: {len(component.dependencies)} dependencies")
```

### Analyzing with NetworkX

```python
import networkx as nx

# Get the component dependency graph
graph = graph_manager.component_graph

# Find most connected components
degree_centrality = nx.degree_centrality(graph)
most_connected = max(degree_centrality.items(), key=lambda x: x[1])

# Find cycles
try:
    cycles = nx.find_cycle(graph)
    print(f"Found circular dependencies: {cycles}")
except nx.NetworkXNoCycle:
    print("No circular dependencies found")
```

## Implementation Details

### New Files

- `diffgraph/graph_export.py`: Core export/import functionality
  - `export_graph()`: Main export function
  - `export_graph_to_json()`: JSON serialization
  - `export_graph_to_pickle()`: Pickle serialization
  - `export_graph_to_graphml()`: GraphML serialization
  - `load_graph_from_json()`: Load from JSON
  - `load_graph_from_pickle()`: Load from pickle

### Modified Files

- `diffgraph/cli.py`: Added new CLI options and conditional output logic
- `diffgraph/graph_manager.py`: Added `export_to_dict()` method
- `README.md`: Updated documentation with new features

### Test Files

- `test_graph_export.py`: Comprehensive tests for export/import functionality
- `example_usage.py`: Example script showing how to use exported data

## Benefits

1. **Programmatic Access**: Other tools can now consume DiffGraph analysis results
2. **Data Persistence**: Save analysis for later review or comparison
3. **Integration**: Easy integration with CI/CD pipelines and automated workflows
4. **Flexibility**: Multiple format options for different use cases
5. **Compatibility**: Standard formats (JSON, GraphML) work with various tools

## Testing

Run the test suite:

```bash
python test_graph_export.py
```

Try the example:

```bash
# Export some changes
wild diff --format graph --output my-changes.json

# Analyze the exported data
python example_usage.py my-changes.json
```

## Backward Compatibility

All existing functionality is preserved. The default behavior remains unchanged:
- Default output format is still HTML
- Existing CLI options work as before
- No breaking changes to the API
