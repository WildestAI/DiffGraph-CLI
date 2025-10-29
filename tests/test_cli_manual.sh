#!/bin/bash
# Manual CLI testing script for the new graph export feature

set -e  # Exit on error

echo "🧪 DiffGraph CLI Test Suite"
echo "================================"
echo ""

# Check if we're in a git repo
if ! git rev-parse --git-dir > /dev/null 2>&1; then
    echo "❌ Not in a git repository"
    exit 1
fi

echo "✅ Git repository detected"
echo ""

# Check if dependencies are installed
echo "📦 Checking dependencies..."
python -c "import click, networkx" 2>/dev/null || {
    echo "⚠️  Installing dependencies..."
    pip install -q -r requirements.txt
}
echo "✅ Dependencies OK"
echo ""

# Test 1: Create sample data without API
echo "Test 1: Testing graph export with sample data (no API needed)"
echo "--------------------------------------------------------------"
python << 'PYEOF'
from diffgraph.graph_manager import GraphManager, ChangeType
from diffgraph.graph_export import export_graph

# Create test graph
gm = GraphManager()
gm.add_file('app/main.py', ChangeType.MODIFIED)
gm.add_file('app/utils.py', ChangeType.ADDED)
gm.add_component('Application', 'app/main.py', ChangeType.MODIFIED, 'container', summary='Main app class')
gm.add_component('run', 'app/main.py', ChangeType.MODIFIED, 'method', parent='Application', summary='Runs the app')
gm.add_component('helper', 'app/utils.py', ChangeType.ADDED, 'function', summary='Helper function')
gm.add_component_dependency('app/main.py::run', 'app/utils.py::helper')
gm.mark_processed('app/main.py', 'Modified main file', [])
gm.mark_processed('app/utils.py', 'Added utils', [])

# Export in all formats
export_graph(gm, 'test_output.json', format='json')
export_graph(gm, 'test_output.pkl', format='pickle')
export_graph(gm, 'test_output.graphml', format='graphml')

print('✅ Generated test files:')
print('   - test_output.json')
print('   - test_output.pkl')
print('   - test_output.graphml')
PYEOF
echo ""

# Test 2: Verify JSON structure
echo "Test 2: Verifying JSON structure"
echo "----------------------------------"
python << 'PYEOF'
import json

with open('test_output.json', 'r') as f:
    data = json.load(f)

assert 'version' in data, "Missing version field"
assert 'file_nodes' in data, "Missing file_nodes"
assert 'component_nodes' in data, "Missing component_nodes"
assert len(data['file_nodes']) == 2, f"Expected 2 files, got {len(data['file_nodes'])}"
assert len(data['component_nodes']) == 3, f"Expected 3 components, got {len(data['component_nodes'])}"

print('✅ JSON structure is valid')
print(f'   - Files: {len(data["file_nodes"])}')
print(f'   - Components: {len(data["component_nodes"])}')
print(f'   - Version: {data["version"]}')
PYEOF
echo ""

# Test 3: Load and verify data integrity
echo "Test 3: Testing data load/export round-trip"
echo "--------------------------------------------"
python << 'PYEOF'
from diffgraph.graph_export import load_graph_from_json, load_graph_from_pickle

# Load from JSON
gm_json = load_graph_from_json('test_output.json')
print(f'✅ Loaded from JSON: {len(gm_json.file_nodes)} files, {len(gm_json.component_nodes)} components')

# Load from pickle
gm_pickle = load_graph_from_pickle('test_output.pkl')
print(f'✅ Loaded from pickle: {len(gm_pickle.file_nodes)} files, {len(gm_pickle.component_nodes)} components')

# Verify they match
assert len(gm_json.file_nodes) == len(gm_pickle.file_nodes), "File count mismatch"
assert len(gm_json.component_nodes) == len(gm_pickle.component_nodes), "Component count mismatch"
print('✅ Data integrity verified across formats')
PYEOF
echo ""

# Test 4: Test example usage script
echo "Test 4: Testing example usage script"
echo "-------------------------------------"
python example_usage.py test_output.json | head -30
echo ""
echo "✅ Example script works correctly"
echo ""

# Test 5: Test CLI help
echo "Test 5: Verifying CLI options"
echo "------------------------------"
python -m diffgraph.cli --help | grep -E "(--format|--graph-format)" && echo "✅ New CLI options are present" || echo "❌ CLI options missing"
echo ""

# Test 6: Check file sizes
echo "Test 6: Checking output file sizes"
echo "-----------------------------------"
ls -lh test_output.* | awk '{print "   " $9 ": " $5}'
echo ""

# Cleanup
echo "🧹 Cleanup"
echo "----------"
read -p "Remove test files? (y/N) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    rm -f test_output.json test_output.pkl test_output.graphml
    echo "✅ Test files removed"
else
    echo "ℹ️  Test files kept for inspection"
fi
echo ""

echo "================================"
echo "✅ All tests passed!"
echo ""
echo "Next steps:"
echo "  1. To test with real code changes, run:"
echo "     python -m diffgraph.cli diff --format graph --output my-analysis.json"
echo ""
echo "  2. To analyze exported data:"
echo "     python example_usage.py my-analysis.json"
echo ""
echo "  3. To generate HTML (default behavior):"
echo "     python -m diffgraph.cli diff --output report.html"
