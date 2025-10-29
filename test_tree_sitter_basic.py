"""
Basic test for tree-sitter processor functionality.
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
    """Test tree-sitter processor with a Python file."""
    
    # Create temp file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
        f.write(python_code)
        temp_file = f.name
    
    try:
        # Create processor
        processor = get_processor("tree-sitter-dependency-graph")
        
        # Prepare file data
        files_with_content = [{
            'path': temp_file,
            'status': 'untracked',
            'content': python_code
        }]
        
        # Analyze
        print("🔍 Analyzing Python code with tree-sitter...")
        result = processor.analyze_changes(files_with_content)
        
        print("\n📊 Analysis Summary:")
        print(result.summary)
        
        print("\n📈 Mermaid Diagram:")
        print(result.mermaid_diagram[:500] + "..." if len(result.mermaid_diagram) > 500 else result.mermaid_diagram)
        
        # Verify components were extracted
        assert len(processor.graph_manager.component_nodes) > 0, "No components extracted"
        
        print("\n✅ Test passed! Found components:")
        for comp_id, comp in processor.graph_manager.component_nodes.items():
            print(f"  - {comp.name} ({comp.component_type})")
        
    finally:
        # Cleanup
        os.unlink(temp_file)

if __name__ == "__main__":
    test_tree_sitter_python()
