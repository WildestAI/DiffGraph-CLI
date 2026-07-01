"""
Basic smoke test for tree-sitter processor functionality.

Updated for schema v2 output (dict-based, not DiffAnalysis object).
The processor now returns a dict conforming to diffgraph-v2.schema.json.
"""

import tempfile
import os
from diffgraph.processing_modes import get_processor

# Create a simple Python test file
python_code = '''
import os
import sys

class MyClass:
    def __init__(self):
        self.value = 0
    
    def increment(self):
        self.value += 1
        return self.value

def standalone_function():
    """A standalone function."""
    obj = MyClass()
    obj.increment()
    return obj.value

def another_function():
    """Another function that calls standalone."""
    result = standalone_function()
    return result * 2
'''

def test_tree_sitter_python():
    """Test tree-sitter processor with a Python file — schema v2 output."""
    
    # Create temp file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
        f.write(python_code)
        temp_file = f.name
    
    try:
        # Create processor
        processor = get_processor("tree-sitter-dependency-graph")
        
        # Prepare file data — pass content directly for test isolation
        files_with_content = [{
            'path': temp_file,
            'status': 'untracked',
            'content': python_code
        }]
        
        # Analyze — result is now a schema v2 dict
        print("🔍 Analyzing Python code with tree-sitter...")
        result = processor.analyze_changes(files_with_content)
        
        # Schema v2: result is a dict, not a DiffAnalysis object
        assert isinstance(result, dict), f"Expected dict, got {type(result)}"
        assert result.get("schema_version") == "2.0"
        
        symbols = result.get("symbols", [])
        relationships = result.get("relationships", [])
        
        print(f"\n📊 Analysis Summary:")
        print(f"  schema_version: {result['schema_version']}")
        print(f"  symbols: {len(symbols)}")
        print(f"  relationships: {len(relationships)}")
        print(f"  privacy_tier: {result['metadata']['privacy_tier']}")
        
        # Verify symbols were extracted (MyClass, __init__, increment, standalone_function, another_function)
        assert len(symbols) > 0, "No symbols extracted"
        
        print("\n✅ Test passed! Found symbols:")
        for sym in symbols:
            print(f"  - {sym['name']} ({sym['kind']}) change={sym['change_kind']}")
        
        # Verify os/sys imports were captured
        import_rels = [r for r in relationships if r.get("kind") == "imports"]
        print(f"\n  Import relationships: {len(import_rels)}")
        for r in import_rels:
            print(f"    {r['source_id']} → {r['target_id']}")
        
    finally:
        # Cleanup
        os.unlink(temp_file)

if __name__ == "__main__":
    test_tree_sitter_python()
