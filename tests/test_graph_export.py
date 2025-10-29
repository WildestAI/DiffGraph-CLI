#!/usr/bin/env python
"""
Simple test script to verify graph export functionality.
This creates a minimal graph and tests export/import in all formats.
"""

from diffgraph.graph_manager import GraphManager, ChangeType, FileStatus
from diffgraph.graph_export import export_graph, load_graph_from_json, load_graph_from_pickle
import os
import json


def test_graph_export():
    """Test graph export functionality."""
    print("Creating test graph...")
    
    # Create a test graph manager
    gm = GraphManager()
    
    # Add some test data
    gm.add_file("test_file1.py", ChangeType.MODIFIED)
    gm.add_file("test_file2.py", ChangeType.ADDED)
    
    gm.add_component("TestClass", "test_file1.py", ChangeType.MODIFIED, "container")
    gm.add_component("test_function", "test_file1.py", ChangeType.ADDED, "function")
    gm.add_component("test_method", "test_file1.py", ChangeType.MODIFIED, "method", 
                     parent="TestClass", summary="A test method")
    
    gm.add_component("NewClass", "test_file2.py", ChangeType.ADDED, "container",
                     summary="A new class")
    
    # Add a dependency
    gm.add_component_dependency("test_file1.py::test_function", "test_file1.py::TestClass")
    
    # Mark files as processed
    gm.mark_processed("test_file1.py", "Modified test file", [])
    gm.mark_processed("test_file2.py", "New test file", [])
    
    print(f"  Files in graph: {len(gm.file_nodes)}")
    print(f"  Components in graph: {len(gm.component_nodes)}")
    print(f"  File edges: {gm.file_graph.number_of_edges()}")
    print(f"  Component edges: {gm.component_graph.number_of_edges()}")
    
    # Test JSON export
    print("\nTesting JSON export...")
    json_path = "test_output.json"
    result_path = export_graph(gm, json_path, format='json')
    print(f"  Exported to: {result_path}")
    
    # Verify JSON file exists and is valid
    assert os.path.exists(json_path), "JSON file was not created"
    with open(json_path, 'r') as f:
        data = json.load(f)
        assert 'version' in data, "JSON missing version"
        assert 'file_nodes' in data, "JSON missing file_nodes"
        assert 'component_nodes' in data, "JSON missing component_nodes"
        print(f"  JSON contains {len(data['file_nodes'])} files and {len(data['component_nodes'])} components")
    
    # Test loading from JSON
    print("\nTesting JSON import...")
    loaded_gm = load_graph_from_json(json_path)
    print(f"  Loaded {len(loaded_gm.file_nodes)} files")
    print(f"  Loaded {len(loaded_gm.component_nodes)} components")
    assert len(loaded_gm.file_nodes) == len(gm.file_nodes), "File count mismatch"
    assert len(loaded_gm.component_nodes) == len(gm.component_nodes), "Component count mismatch"
    
    # Test pickle export
    print("\nTesting pickle export...")
    pickle_path = "test_output.pkl"
    result_path = export_graph(gm, pickle_path, format='pickle')
    print(f"  Exported to: {result_path}")
    assert os.path.exists(pickle_path), "Pickle file was not created"
    
    # Test loading from pickle
    print("\nTesting pickle import...")
    loaded_gm_pickle = load_graph_from_pickle(pickle_path)
    print(f"  Loaded {len(loaded_gm_pickle.file_nodes)} files")
    print(f"  Loaded {len(loaded_gm_pickle.component_nodes)} components")
    assert len(loaded_gm_pickle.file_nodes) == len(gm.file_nodes), "File count mismatch"
    assert len(loaded_gm_pickle.component_nodes) == len(gm.component_nodes), "Component count mismatch"
    
    # Test GraphML export
    print("\nTesting GraphML export...")
    graphml_path = "test_output.graphml"
    result_path = export_graph(gm, graphml_path, format='graphml')
    print(f"  Exported to: {result_path}")
    assert os.path.exists(graphml_path), "GraphML file was not created"
    
    # Verify GraphML is valid XML
    with open(graphml_path, 'r') as f:
        content = f.read()
        assert '<?xml' in content, "GraphML missing XML header"
        assert '<graphml' in content, "GraphML missing graphml tag"
        print(f"  GraphML file is valid XML ({len(content)} bytes)")
    
    # Test export_to_dict method
    print("\nTesting export_to_dict method...")
    data_dict = gm.export_to_dict()
    assert 'version' in data_dict, "export_to_dict missing version"
    assert 'file_nodes' in data_dict, "export_to_dict missing file_nodes"
    assert 'component_nodes' in data_dict, "export_to_dict missing component_nodes"
    print(f"  export_to_dict returned {len(data_dict['file_nodes'])} files")
    
    # Cleanup
    print("\nCleaning up test files...")
    for path in [json_path, pickle_path, graphml_path]:
        if os.path.exists(path):
            os.remove(path)
            print(f"  Removed {path}")
    
    print("\n✅ All tests passed!")


if __name__ == "__main__":
    test_graph_export()
