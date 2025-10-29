# Testing Guide for Graph Export Feature

## Quick Start

### Option 1: Run the Automated Test Script (Recommended)

The easiest way to test all functionality:

```bash
./test_cli_manual.sh
```

This will:
- ✅ Test graph export in all formats (JSON, Pickle, GraphML)
- ✅ Verify data integrity
- ✅ Test loading exported data
- ✅ Verify CLI options
- ✅ No API key required!

### Option 2: Unit Tests

Run the comprehensive unit tests:

```bash
python test_graph_export.py
```

Expected output: `✅ All tests passed!`

### Option 3: Manual Testing with Real Changes

If you have an OpenAI API key and want to test with actual code changes:

```bash
# Set up your API key
export OPENAI_API_KEY="your-key-here"

# Option A: Export graph data (new feature)
python -m diffgraph.cli diff --format graph --output analysis.json

# Option B: Generate HTML (existing feature - should still work)
python -m diffgraph.cli diff --output report.html --no-open

# Analyze the exported graph data
python example_usage.py analysis.json
```

## Testing Scenarios

### Scenario 1: Test Without API Key

Create sample data and test export/import:

```bash
python << 'EOF'
from diffgraph.graph_manager import GraphManager, ChangeType
from diffgraph.graph_export import export_graph, load_graph_from_json

# Create test data
gm = GraphManager()
gm.add_file('example.py', ChangeType.MODIFIED)
gm.add_component('MyClass', 'example.py', ChangeType.MODIFIED, 'container')
gm.mark_processed('example.py', 'Test file', [])

# Export
export_graph(gm, 'test.json', format='json')
print("✅ Exported to test.json")

# Load back
loaded = load_graph_from_json('test.json')
print(f"✅ Loaded {len(loaded.file_nodes)} files, {len(loaded.component_nodes)} components")
EOF
```

### Scenario 2: Test All Export Formats

```bash
python << 'EOF'
from diffgraph.graph_manager import GraphManager, ChangeType
from diffgraph.graph_export import export_graph

gm = GraphManager()
gm.add_file('test.py', ChangeType.ADDED)
gm.mark_processed('test.py', 'New file', [])

# Export in all formats
export_graph(gm, 'output.json', format='json')
export_graph(gm, 'output.pkl', format='pickle')
export_graph(gm, 'output.graphml', format='graphml')

print("✅ Generated: output.json, output.pkl, output.graphml")
EOF

# Check the files
ls -lh output.*
```

### Scenario 3: Test CLI Options

```bash
# View help to see new options
python -m diffgraph.cli --help

# Test format option
python -m diffgraph.cli diff --format graph --help

# Test graph-format option  
python -m diffgraph.cli diff --format graph --graph-format json --help
```

### Scenario 4: Test with Current Git Changes

If you have uncommitted changes in your repo:

```bash
# Export current changes as graph data
python -m diffgraph.cli diff --format graph --output my-changes.json

# View the exported data
cat my-changes.json | python -m json.tool | less

# Analyze it
python example_usage.py my-changes.json
```

### Scenario 5: Test Data Integrity

```bash
python << 'EOF'
from diffgraph.graph_manager import GraphManager, ChangeType
from diffgraph.graph_export import export_graph, load_graph_from_json
import json

# Create and export
gm = GraphManager()
gm.add_file('test.py', ChangeType.MODIFIED)
gm.add_component('TestFunc', 'test.py', ChangeType.ADDED, 'function', 
                 summary='A test function', dependencies=['other_func'])
gm.mark_processed('test.py', 'Modified test file', [])

export_graph(gm, 'integrity_test.json', format='json')

# Load and verify
loaded = load_graph_from_json('integrity_test.json')
comp = loaded.component_nodes['test.py::TestFunc']

assert comp.name == 'TestFunc'
assert comp.summary == 'A test function'
assert comp.dependencies == ['other_func']
assert loaded.file_nodes['test.py'].summary == 'Modified test file'

print("✅ Data integrity verified!")
print(f"   Component: {comp.name}")
print(f"   Summary: {comp.summary}")
print(f"   Dependencies: {comp.dependencies}")
EOF
```

## Verifying the Feature Works

### Checklist

- [ ] CLI accepts `--format` option
- [ ] CLI accepts `--graph-format` option
- [ ] JSON export works
- [ ] Pickle export works
- [ ] GraphML export works
- [ ] Loading from JSON works
- [ ] Loading from pickle works
- [ ] Data integrity is preserved
- [ ] Example script works
- [ ] HTML output still works (backward compatibility)
- [ ] Help text shows new options

### Quick Verification Commands

```bash
# 1. Check CLI has new options
python -m diffgraph.cli --help | grep -E "format"

# 2. Run unit tests
python test_graph_export.py

# 3. Run full test suite
./test_cli_manual.sh

# 4. Test example usage
python example_usage.py test_output.json
```

## Troubleshooting

### Import Error: No module named 'networkx'

```bash
pip install -r requirements.txt
```

### Import Error: No module named 'diffgraph'

```bash
# Install in development mode
pip install -e .
```

### API Key Error

For testing without an API key, use the unit tests or create sample data manually:

```bash
# These don't require API keys:
python test_graph_export.py
./test_cli_manual.sh
```

For testing with real changes, you need an OpenAI API key:

```bash
export OPENAI_API_KEY="your-key-here"
# or add to .env file
```

## Expected Results

### JSON Output Structure

```json
{
  "version": "1.0",
  "file_nodes": {
    "file.py": {
      "path": "file.py",
      "status": "processed",
      "change_type": "modified",
      "summary": "...",
      "error": null,
      "components": [...]
    }
  },
  "component_nodes": {
    "file.py::ComponentName": {
      "name": "ComponentName",
      "file_path": "file.py",
      "change_type": "modified",
      "component_type": "container",
      "parent": null,
      "summary": "...",
      "dependencies": [...],
      "dependents": [...]
    }
  },
  "file_graph": {...},
  "component_graph": {...},
  "processed_files": [...]
}
```

### File Sizes

Typical sizes for test data:
- JSON: ~2KB (human-readable)
- Pickle: ~800B (binary, compact)
- GraphML: ~3KB (XML format)

## Performance Testing

To test with larger datasets:

```bash
python << 'EOF'
from diffgraph.graph_manager import GraphManager, ChangeType
from diffgraph.graph_export import export_graph
import time

# Create larger dataset
gm = GraphManager()
for i in range(100):
    gm.add_file(f'file_{i}.py', ChangeType.MODIFIED)
    gm.add_component(f'Class_{i}', f'file_{i}.py', ChangeType.MODIFIED, 'container')
    gm.mark_processed(f'file_{i}.py', f'File {i}', [])

# Time the export
start = time.time()
export_graph(gm, 'large_test.json', format='json')
elapsed = time.time() - start

print(f"✅ Exported 100 files in {elapsed:.2f} seconds")
EOF
```

## Next Steps After Testing

1. ✅ All tests pass → Feature is ready to use
2. ⚠️ Some tests fail → Check error messages and file issues
3. 🎉 Tests successful → Try with your real project changes!

```bash
# Use it in your project
cd /path/to/your/project
wild diff --format graph --output analysis.json
python /path/to/example_usage.py analysis.json
```
