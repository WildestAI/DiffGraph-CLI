# Phase 1 Implementation Notes

**Goal**: Ship a working version with restructured output using only existing data.

## Implementation Questions - Answered

### 1. Impact Radius Calculation

**Question**: Should this be calculated from:
- Just the diff graph? (only changed components)
- The full codebase graph? (would require analyzing unchanged files too)

**Answer for Phase 1**: Calculate from the diff graph only.

**Implementation**:
```python
# Simple calculation from existing data
impact_radius = len(component.dependencies) + len(component.dependents)
```

**For Phase 2**: Analyze full codebase to get true impact radius including transitive dependencies.

### 2. Relationship Detection

**Question**: For detecting REST/RPC/pub-sub patterns, should we:
- Use AI to identify them from code context?
- Use pattern matching (e.g., `requests.post()`, `grpc.call()`)?
- Hybrid approach?

**Answer for Phase 1**: Keep it simple - use generic relationship types from existing graph.

**Implementation**:
- Map existing edges to basic relationships: `imports`, `calls`, `extends`, `implements`
- Don't detect REST/RPC/pub-sub yet
- Use `calls` as the generic relationship for most function calls

**For Phase 2**: Add pattern matching and AI detection for specialized relationships.

### 3. Auto-Generated Patterns

**Question**: Should I create a configurable patterns file?

**Answer**: Yes, but keep it minimal for Phase 1.

**Implementation**:
```python
# Hardcode in the module for now
AUTO_GENERATED_PATTERNS = [
    '*-lock.json', '*.lock', 
    '*.min.js', '*.min.css',
    'dist/*', 'build/*', 'target/*',
    '__pycache__/*', '*.pyc'
]

DOC_PATTERNS = [
    '*.md', '*.rst', '*.adoc', 
    'docs/*', 'documentation/*'
]

CONFIG_PATTERNS = [
    '*.toml', '*.yaml', '*.yml', 
    'setup.py', 'setup.cfg', 'pyproject.toml',
    '.*rc', '.*ignore', 'Makefile', 'Dockerfile',
    'package.json', 'tsconfig.json'
]
```

**For Phase 2**: Move to external config file, add more patterns, use AI for edge cases.

### 4. AI Prompts

**Question**: Should I keep backward compatibility or completely replace?

**Answer**: Completely replace for JSON format. Keep NetworkX format for pickle/graphml.

**Implementation**:
- When `--graph-format json`: Use new structured format
- When `--graph-format pickle` or `graphml`: Use current NetworkX format
- No backward compatibility needed (hasn't shipped yet)

## What to Implement in Phase 1

### Module Structure

Create new module: `diffgraph/structured_export.py`

```python
# diffgraph/structured_export.py

def export_structured_json(graph_manager: GraphManager, 
                          output_path: str, 
                          diff_args: List[str]) -> str:
    """
    Export graph in structured JSON format.
    
    Phase 1: Uses existing data, leaves some fields null.
    """
    pass

def classify_file(file_path: str) -> str:
    """Classify file as: auto_generated, documentation, configuration, or source_code"""
    pass

def get_file_stats(file_path: str, diff_args: List[str]) -> Dict:
    """Get git diff stats (additions/deletions) for a file"""
    pass

def transform_to_structured_format(graph_manager: GraphManager, 
                                   diff_args: List[str]) -> dict:
    """Transform NetworkX graph data to structured format"""
    pass
```

### CLI Changes

Update `diffgraph/cli.py`:

```python
# When format is 'graph' and graph_format is 'json'
if format == 'graph':
    if graph_format == 'json':
        # Use new structured format
        from diffgraph.structured_export import export_structured_json
        graph_path = export_structured_json(agent.graph_manager, output, diff_args)
    else:
        # Use existing NetworkX format for pickle/graphml
        graph_path = export_graph(agent.graph_manager, output, graph_format)
```

### Data Extraction

#### From Existing GraphManager

Available data:
- `graph_manager.file_nodes` → File information
- `graph_manager.component_nodes` → Component information
- `graph_manager.file_graph` → File dependencies
- `graph_manager.component_graph` → Component dependencies
- `graph_manager.processed_files` → Which files completed analysis

Already have:
- Component names, types, summaries
- Parent relationships (for nested components)
- Change types (added, deleted, modified)
- Dependencies and dependents lists

#### From Git

Need to extract:
```bash
# File-level stats
git diff --numstat [diff_args] -- <file>
# Output: additions\tdeletions\tfilename

# Component-level line numbers (harder - skip for Phase 1)
# Leave as null for now
```

### Fields to Leave Null/Empty in Phase 1

**Component Nodes**:
- `complexity`: null (needs cyclomatic complexity analysis)
- `old_line_number`: null (needs git diff parsing)
- `new_line_number`: null (needs git diff parsing)
- `parameters`: null (needs signature parsing)
- `return_type`: null (needs signature parsing)

**Per-component Stats**:
- `additions`: null (needs per-function diff analysis)
- `deletions`: null (needs per-function diff analysis)

**Documentation**:
- `sections_modified`: empty array (needs doc parsing)
- `cross_references`: empty array (needs NLP)

**Configuration**:
- `config_changes`: empty array (needs structured parsing)
- `cross_references`: empty array (needs analysis)

**External Nodes**:
- Don't create for Phase 1 (or create with minimal info if edge targets them)

**Advanced Relationships**:
- Only use: `imports`, `calls`, `extends`, `implements`
- No REST/RPC/pub-sub/database for Phase 1

### Simple Transformation Logic

```python
def transform_component_to_structured(component_id: str, 
                                     component: ComponentNode,
                                     graph_manager: GraphManager) -> dict:
    # Simple impact radius from existing dependency lists
    impact_radius = len(component.dependencies) + len(component.dependents)
    
    return {
        'id': component_id,
        'parent_id': component.parent,
        'component_type': component.component_type,
        'name': component.name,
        'file_path': component.file_path,
        'old_line_number': None,  # Phase 2
        'new_line_number': None,  # Phase 2
        'change_type': component.change_type.value,
        'additions': None,  # Phase 2
        'deletions': None,  # Phase 2
        'summary': component.summary,
        'complexity': None,  # Phase 2
        'impact_radius': impact_radius,
        'parameters': None,  # Phase 2
        'return_type': None  # Phase 2
    }

def transform_edge_to_structured(source: str, 
                               target: str,
                               graph_manager: GraphManager) -> dict:
    # Determine relationship type from context
    # For Phase 1: just use 'calls' for most things
    relationship = 'calls'  # Default
    
    # Could check if both are in same file → might be 'extends' or 'implements'
    # But keep simple for Phase 1
    
    return {
        'source': source,
        'target': target,
        'relationship': relationship,
        'change_type': 'added',  # Simplified for Phase 1
        'summary': ''  # Empty for Phase 1, or copy from node summaries
    }
```

## Testing for Phase 1

### Test Cases

1. **Basic transformation**: Simple diff with 2-3 files
2. **File classification**: Mix of .py, .md, .json, package-lock.json
3. **Component hierarchy**: Nested components (class → methods)
4. **Edge transformation**: Various relationship types
5. **Deletions**: Removed files and components
6. **Git stats**: Verify additions/deletions extracted correctly

### Validation

- JSON schema validation
- All edge targets exist in nodes
- No duplicate node IDs
- Consistent change_types
- Null fields are actually null (not missing)

## Success Criteria for Phase 1

- ✅ Restructured JSON output generated
- ✅ File classification works (basic patterns)
- ✅ All existing data preserved
- ✅ Graph completeness (edges → nodes)
- ✅ Git stats extracted for files
- ✅ Tests pass
- ✅ Documentation updated

**Not Required**:
- ❌ Complete metadata (complexity, line numbers, etc.)
- ❌ External dependency nodes
- ❌ Advanced relationship types
- ❌ Cross-references
- ❌ Full codebase impact analysis

## Timeline

**Phase 1**: ~2-3 hours implementation + testing
- Create structured_export.py
- Update CLI
- Add tests
- Update docs

**Phase 2**: Future (1-2 weeks)
- Full analysis implementation
- External dependency detection
- Advanced relationships
- Complete metadata

## Next Conversation Pickup

**To resume Phase 1 implementation**:
1. Read `STRUCTURED_OUTPUT_DESIGN.md` - Full schema
2. Read this file - Implementation decisions
3. Start with: "Let's implement Phase 1 structured export"
4. Create `diffgraph/structured_export.py`
5. Update `diffgraph/cli.py` to use it for JSON format

**Key files to modify**:
- New: `diffgraph/structured_export.py`
- Update: `diffgraph/cli.py`
- Update: `diffgraph/graph_export.py` (minor)
- New: `test_structured_export.py`
- Update: `README.md`, `CHANGELOG.md`

**Commit message template**:
```
feat: Add structured JSON output format (Phase 1)

Implement integration-friendly structured output format with file
classification and rich metadata. Phase 1 uses existing analysis data.

- Add diffgraph/structured_export.py for transformation
- Update CLI to use structured format for JSON export
- Add file classification (source/docs/config/auto-generated)
- Extract git diff stats for additions/deletions
- Leave advanced fields (complexity, line numbers) for Phase 2

Breaking: JSON format now outputs structured format instead of NetworkX
Legacy: Use --graph-format pickle for NetworkX format
```
