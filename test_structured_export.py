#!/usr/bin/env python
"""
Test suite for structured export functionality.
Tests Phase 1 implementation of integration-friendly JSON output.
"""

import json
import os
from diffgraph.graph_manager import GraphManager, ChangeType
from diffgraph.structured_export import (
    classify_file,
    export_structured_json,
    transform_component_node,
    transform_file_node,
    transform_to_structured_format
)


def test_file_classification():
    """Test file classification into categories."""
    print("Testing file classification...")
    
    # Auto-generated files
    assert classify_file('package-lock.json') == 'auto_generated'
    assert classify_file('yarn.lock') == 'auto_generated'
    assert classify_file('dist/bundle.min.js') == 'auto_generated'
    assert classify_file('build/output.js') == 'auto_generated'
    assert classify_file('__pycache__/module.pyc') == 'auto_generated'
    
    # Documentation files
    assert classify_file('README.md') == 'documentation'
    assert classify_file('docs/guide.rst') == 'documentation'
    assert classify_file('CHANGELOG.md') == 'documentation'
    
    # Configuration files
    assert classify_file('setup.py') == 'configuration'
    assert classify_file('pyproject.toml') == 'configuration'
    assert classify_file('package.json') == 'configuration'
    assert classify_file('.eslintrc') == 'configuration'
    assert classify_file('requirements.txt') == 'configuration'
    
    # Source code files
    assert classify_file('main.py') == 'source_code'
    assert classify_file('src/app.js') == 'source_code'
    assert classify_file('lib/utils.go') == 'source_code'
    
    print("✅ File classification tests passed")


def test_component_transformation():
    """Test component node transformation."""
    print("\nTesting component transformation...")
    
    gm = GraphManager()
    gm.add_file('test.py', ChangeType.MODIFIED)
    gm.add_component('TestClass', 'test.py', ChangeType.MODIFIED, 'class',
                     summary='A test class', dependencies=['OtherClass'],
                     dependents=['UsageClass'])
    
    component_id = 'test.py::TestClass'
    component = gm.component_nodes[component_id]
    
    result = transform_component_node(component_id, component, gm)
    
    assert result['id'] == component_id
    assert result['name'] == 'TestClass'
    assert result['component_type'] == 'class'
    assert result['change_type'] == 'modified'
    assert result['summary'] == 'A test class'
    assert result['impact_radius'] == 2  # 1 dependency + 1 dependent
    assert result['complexity'] is None  # Phase 2
    assert result['parameters'] is None  # Phase 2
    
    print("✅ Component transformation tests passed")


def test_structured_export():
    """Test full structured export."""
    print("\nTesting structured export...")
    
    # Create test graph
    gm = GraphManager()
    
    # Add source files
    gm.add_file('src/main.py', ChangeType.MODIFIED)
    gm.add_file('src/utils.py', ChangeType.ADDED)
    gm.add_file('tests/test_main.py', ChangeType.ADDED)
    
    # Add documentation
    gm.add_file('README.md', ChangeType.MODIFIED)
    
    # Add configuration
    gm.add_file('setup.py', ChangeType.MODIFIED)
    
    # Add auto-generated
    gm.add_file('package-lock.json', ChangeType.MODIFIED)
    
    # Add components
    gm.add_component('MainClass', 'src/main.py', ChangeType.MODIFIED, 'class',
                     summary='Main application class')
    gm.add_component('run', 'src/main.py', ChangeType.MODIFIED, 'method',
                     parent='MainClass', summary='Run method')
    gm.add_component('helper', 'src/utils.py', ChangeType.ADDED, 'function',
                     summary='Helper function')
    
    # Add dependency
    gm.add_component_dependency('src/main.py::run', 'src/utils.py::helper')
    
    # Mark as processed
    gm.mark_processed('src/main.py', 'Modified main file', [])
    gm.mark_processed('src/utils.py', 'Added utils', [])
    gm.mark_processed('tests/test_main.py', 'Added tests', [])
    gm.mark_processed('README.md', 'Updated docs', [])
    gm.mark_processed('setup.py', 'Version bump', [])
    gm.mark_processed('package-lock.json', 'Dependency update', [])
    
    # Export
    output_path = 'test_structured_output.json'
    result_path = export_structured_json(gm, output_path, diff_args=[])
    
    assert os.path.exists(output_path)
    print(f"  Generated: {result_path}")
    
    # Load and validate
    with open(output_path, 'r') as f:
        data = json.load(f)
    
    # Validate top-level structure
    assert 'version' in data
    assert data['version'] == '2.0'
    assert 'metadata' in data
    assert 'auto_generated' in data
    assert 'documentation' in data
    assert 'configuration' in data
    assert 'source_code' in data
    
    print(f"  Version: {data['version']}")
    
    # Validate metadata
    metadata = data['metadata']
    assert 'analyzed_at' in metadata
    assert 'total_files_changed' in metadata
    assert metadata['total_files_changed'] == 6
    
    print(f"  Files changed: {metadata['total_files_changed']}")
    
    # Validate categorization
    assert len(data['auto_generated']) == 1
    assert data['auto_generated'][0]['path'] == 'package-lock.json'
    
    assert 'README.md' in data['documentation']
    
    assert 'setup.py' in data['configuration']
    
    print(f"  Auto-generated: {len(data['auto_generated'])}")
    print(f"  Documentation: {len(data['documentation'])}")
    print(f"  Configuration: {len(data['configuration'])}")
    
    # Validate source code structure
    source = data['source_code']
    assert 'files' in source
    assert 'components' in source
    
    files = source['files']
    assert 'nodes' in files
    assert 'edges' in files
    
    # Should have 3 source files (main.py, utils.py, test_main.py)
    assert len(files['nodes']) == 3
    
    print(f"  Source files: {len(files['nodes'])}")
    
    components = source['components']
    assert 'nodes' in components
    assert 'edges' in components
    
    # Should have 3 components
    assert len(components['nodes']) == 3
    
    print(f"  Components: {len(components['nodes'])}")
    
    # Should have 1 edge (run -> helper)
    assert len(components['edges']) == 1
    
    print(f"  Component edges: {len(components['edges'])}")
    
    # Validate component structure
    component_node = components['nodes'][0]
    assert 'id' in component_node
    assert 'name' in component_node
    assert 'component_type' in component_node
    assert 'change_type' in component_node
    assert 'summary' in component_node
    assert 'impact_radius' in component_node
    
    # Check Phase 1 null fields
    assert component_node['complexity'] is None
    assert component_node['old_line_number'] is None
    assert component_node['new_line_number'] is None
    assert component_node['parameters'] is None
    
    print("  ✓ Component structure validated")
    
    # Validate edge structure
    edge = components['edges'][0]
    assert 'source' in edge
    assert 'target' in edge
    assert 'relationship' in edge
    assert 'change_type' in edge
    assert edge['source'] == 'src/main.py::run'
    assert edge['target'] == 'src/utils.py::helper'
    
    print("  ✓ Edge structure validated")
    
    # Cleanup
    os.remove(output_path)
    print("  ✓ Cleaned up test file")
    
    print("✅ Structured export tests passed")


def test_graph_completeness():
    """Test that all edge targets exist as nodes."""
    print("\nTesting graph completeness...")
    
    gm = GraphManager()
    gm.add_file('file1.py', ChangeType.MODIFIED)
    gm.add_file('file2.py', ChangeType.ADDED)
    
    gm.add_component('Func1', 'file1.py', ChangeType.MODIFIED, 'function')
    gm.add_component('Func2', 'file2.py', ChangeType.ADDED, 'function')
    
    gm.add_component_dependency('file1.py::Func1', 'file2.py::Func2')
    
    gm.mark_processed('file1.py', 'File 1', [])
    gm.mark_processed('file2.py', 'File 2', [])
    
    # Export and validate
    output_path = 'test_completeness.json'
    export_structured_json(gm, output_path, diff_args=[])
    
    with open(output_path, 'r') as f:
        data = json.load(f)
    
    # Get all component node IDs
    component_ids = set(node['id'] for node in data['source_code']['components']['nodes'])
    
    # Verify all edge sources and targets exist in nodes
    for edge in data['source_code']['components']['edges']:
        assert edge['source'] in component_ids, f"Source {edge['source']} not in nodes"
        assert edge['target'] in component_ids, f"Target {edge['target']} not in nodes"
    
    print("  ✓ All edge sources exist as nodes")
    print("  ✓ All edge targets exist as nodes")
    
    os.remove(output_path)
    
    print("✅ Graph completeness tests passed")


def test_empty_graph():
    """Test handling of empty graph."""
    print("\nTesting empty graph...")
    
    gm = GraphManager()
    
    output_path = 'test_empty.json'
    export_structured_json(gm, output_path, diff_args=[])
    
    with open(output_path, 'r') as f:
        data = json.load(f)
    
    assert data['version'] == '2.0'
    assert data['metadata']['total_files_changed'] == 0
    assert len(data['auto_generated']) == 0
    assert len(data['documentation']) == 0
    assert len(data['configuration']) == 0
    assert len(data['source_code']['files']['nodes']) == 0
    assert len(data['source_code']['components']['nodes']) == 0
    
    os.remove(output_path)
    
    print("✅ Empty graph tests passed")


def main():
    """Run all tests."""
    print("=" * 60)
    print("Testing Structured Export (Phase 1)")
    print("=" * 60)
    
    test_file_classification()
    test_component_transformation()
    test_structured_export()
    test_graph_completeness()
    test_empty_graph()
    
    print("\n" + "=" * 60)
    print("✅ All tests passed!")
    print("=" * 60)


if __name__ == "__main__":
    main()
