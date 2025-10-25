#!/usr/bin/env python
"""
Example script showing how to load and use exported graph data.

This demonstrates how another program can read the exported graph data
and access all the analysis information.
"""

from diffgraph.graph_export import load_graph_from_json
import sys


def analyze_exported_graph(json_path: str):
    """
    Load and analyze an exported graph file.
    
    Args:
        json_path: Path to the exported JSON file
    """
    print(f"Loading graph data from: {json_path}")
    print("-" * 60)
    
    # Load the graph
    graph_manager = load_graph_from_json(json_path)
    
    # Summary statistics
    print("\n📊 Graph Statistics:")
    print(f"  Total files: {len(graph_manager.file_nodes)}")
    print(f"  Total components: {len(graph_manager.component_nodes)}")
    print(f"  File dependencies: {graph_manager.file_graph.number_of_edges()}")
    print(f"  Component dependencies: {graph_manager.component_graph.number_of_edges()}")
    print(f"  Processed files: {len(graph_manager.processed_files)}")
    
    # Analyze files
    print("\n📁 File Analysis:")
    for file_path, file_node in graph_manager.file_nodes.items():
        print(f"\n  {file_path}")
        print(f"    Status: {file_node.status.value}")
        print(f"    Change Type: {file_node.change_type.value}")
        if file_node.summary:
            print(f"    Summary: {file_node.summary[:80]}...")
        if file_node.error:
            print(f"    Error: {file_node.error}")
    
    # Analyze components
    print("\n🔧 Component Analysis:")
    for component_id, component_node in graph_manager.component_nodes.items():
        print(f"\n  {component_node.name} ({component_node.component_type})")
        print(f"    File: {component_node.file_path}")
        print(f"    Change Type: {component_node.change_type.value}")
        if component_node.parent:
            print(f"    Parent: {component_node.parent}")
        if component_node.dependencies:
            print(f"    Dependencies: {', '.join(component_node.dependencies[:3])}{'...' if len(component_node.dependencies) > 3 else ''}")
        if component_node.dependents:
            print(f"    Dependents: {', '.join(component_node.dependents[:3])}{'...' if len(component_node.dependents) > 3 else ''}")
        if component_node.summary:
            print(f"    Summary: {component_node.summary[:80]}...")
    
    # Find most connected components
    if graph_manager.component_nodes:
        print("\n🌟 Most Connected Components:")
        component_connections = []
        for component_id, component_node in graph_manager.component_nodes.items():
            total_connections = len(component_node.dependencies) + len(component_node.dependents)
            if total_connections > 0:
                component_connections.append((component_node.name, total_connections))
        
        component_connections.sort(key=lambda x: x[1], reverse=True)
        for name, count in component_connections[:5]:
            print(f"  {name}: {count} connections")
    
    print("\n" + "=" * 60)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python example_usage.py <path_to_exported_json>")
        print("\nExample:")
        print("  # First, export graph data from your changes")
        print("  wild diff --format graph --output my-changes.json")
        print()
        print("  # Then analyze the exported data")
        print("  python example_usage.py my-changes.json")
        sys.exit(1)
    
    json_path = sys.argv[1]
    analyze_exported_graph(json_path)
