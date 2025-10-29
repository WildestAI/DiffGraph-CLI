# Structured Output Design Document

**Version**: 2.0  
**Status**: Design Phase → Initial Implementation  
**Created**: 2025-10-24  
**Last Updated**: 2025-10-24  

## Overview

This document outlines the design for a new structured JSON output format optimized for integration consumption (VSCode extensions, web UIs, CI/CD tools). Unlike the current NetworkX graph serialization, this format is specifically designed to be:

1. **Integration-friendly**: Easy to consume without understanding NetworkX internals
2. **Semantically rich**: Clear categorization of file types and relationships
3. **Complete**: All referenced entities exist as nodes in the graph
4. **Self-documenting**: Includes metadata and context for all elements

## Design Philosophy

### Problems with Current Format

1. **Internal representation exposed**: NetworkX node-link format is optimized for our processing, not consumption
2. **Processing artifacts included**: Fields like `processed_files` are internal state
3. **Requires transformation**: Consumers need to understand NetworkX and transform data
4. **Missing context**: No distinction between source code, docs, config, auto-generated files

### New Approach

- **Categorize files** by purpose (source code, docs, config, auto-generated)
- **Explicit graph structure** with nodes and edges arrays
- **Rich metadata** including line numbers, additions/deletions, complexity
- **Complete graph** with external dependencies as first-class nodes
- **Clear semantics** with typed relationships and change types

## Full Schema Specification

### Top-Level Structure

```json
{
  "version": "2.0",
  "metadata": { ... },
  "auto_generated": [ ... ],
  "documentation": { ... },
  "configuration": { ... },
  "source_code": {
    "files": { "nodes": [...], "edges": [...] },
    "components": { "nodes": [...], "edges": [...] }
  }
}
```

### Metadata Section

```json
{
  "version": "2.0",
  "metadata": {
    "analyzed_at": "2025-10-24T22:54:00Z",
    "diff_base": "main",           // git ref for base
    "diff_target": "HEAD",          // git ref for target
    "total_files_changed": 12,
    "total_additions": 1296,
    "total_deletions": 28,
    "analyzer_version": "1.1.0",    // CLI version
    "ai_model": "gpt-4o"            // AI model used for analysis
  }
}
```

### Auto-Generated Files

Files that should not be reviewed (lock files, build artifacts, etc.)

```json
{
  "auto_generated": [
    {
      "path": "package-lock.json",
      "classification_method": "pattern",  // "pattern" or "ai"
      "reason": "npm lock file",
      "additions": 100,
      "deletions": 50
    }
  ]
}
```

**Classification Strategy**:
- **Pattern-based** (high confidence): Lock files, minified files, common build artifacts
- **AI-based** (edge cases): Framework-specific generated files, unusual patterns

**Common Patterns** (to be hardcoded):
```
*-lock.json, *.lock, yarn.lock, Gemfile.lock, Cargo.lock
*.min.js, *.min.css, *.bundle.js
dist/*, build/*, target/*, out/*, .next/*, __pycache__/*
*.pyc, *.class, *.o, *.so
package-lock.json, composer.lock, poetry.lock
.DS_Store, Thumbs.db
```

### Documentation Files

Documentation that may reference code but isn't part of the dependency graph.

```json
{
  "documentation": {
    "README.md": {
      "additions": 61,
      "deletions": 5,
      "summary": "Added graph export feature documentation with usage examples",
      "sections_modified": ["Usage", "Output Formats", "Features"],
      "cross_references": [
        {
          "component_id": "diffgraph/cli.py::main",
          "line_numbers": [47, 65, 71],
          "context": "CLI usage examples"
        }
      ]
    }
  }
}
```

**Detection**: Pattern-based (*.md, docs/*, *.rst, *.adoc, etc.) + AI for edge cases

**Cross-references**: AI can detect when docs mention specific components

### Configuration Files

Configuration files that affect system behavior but aren't source code.

```json
{
  "configuration": {
    "setup.py": {
      "additions": 1,
      "deletions": 1,
      "summary": "Version bump from 1.0.0 to 1.1.0",
      "config_changes": [
        {
          "key": "version",
          "old_value": "1.0.0",
          "new_value": "1.1.0",
          "line_number": 5
        }
      ],
      "cross_references": []
    }
  }
}
```

**Detection**: Pattern-based (*.toml, *.yaml, *.json config files, .*rc files) + AI

**Structured Changes**: AI can extract specific config key changes for important files

### Source Code - Files Graph

File-level dependency graph (import relationships).

```json
{
  "source_code": {
    "files": {
      "nodes": [
        {
          "path": "diffgraph/graph_export.py",
          "name": "graph_export.py",
          "type": "src",              // "src" or "test"
          "change_type": "added",     // "added", "deleted", "modified", "unchanged"
          "additions": 273,
          "deletions": 0,
          "summary": "New module for graph data export in multiple formats",
          "language": "python",
          "old_path": null            // for renamed files
        }
      ],
      "edges": [
        {
          "source": "diffgraph/cli.py",
          "target": "diffgraph/graph_export.py",
          "relationship": "imports",
          "change_type": "added",     // "added", "deleted", "modified", "unchanged"
          "summary": "CLI now imports graph_export module for data export"
        }
      ]
    }
  }
}
```

### Source Code - Components Graph

Component-level dependency graph (functions, classes, methods).

#### Component Nodes

```json
{
  "components": {
    "nodes": [
      // Regular component
      {
        "id": "diffgraph/graph_export.py::export_graph",
        "parent_id": null,
        "component_type": "function",
        "name": "export_graph",
        "file_path": "diffgraph/graph_export.py",
        "old_line_number": null,
        "new_line_number": 254,
        "change_type": "added",
        "additions": 15,
        "deletions": 0,
        "summary": "Main export function supporting JSON, pickle, and GraphML formats",
        "complexity": "medium",       // "low", "medium", "high"
        "impact_radius": 3,           // number of connected components
        "parameters": ["graph_manager", "output_path", "format"],
        "return_type": "str"
      },
      
      // Nested component (method inside class)
      {
        "id": "diffgraph/graph_manager.py::GraphManager::export_to_dict",
        "parent_id": "diffgraph/graph_manager.py::GraphManager",
        "component_type": "method",
        "name": "export_to_dict",
        "file_path": "diffgraph/graph_manager.py",
        "old_line_number": null,
        "new_line_number": 305,
        "change_type": "added",
        "additions": 59,
        "deletions": 0,
        "summary": "Exports graph manager state to dictionary for serialization",
        "complexity": "medium",
        "impact_radius": 2,
        "parameters": [],
        "return_type": "dict"
      },
      
      // Deleted component
      {
        "id": "diffgraph/old_module.py::OldClass",
        "parent_id": null,
        "component_type": "class",
        "name": "OldClass",
        "file_path": "diffgraph/old_module.py",
        "old_line_number": 42,
        "new_line_number": null,
        "change_type": "deleted",
        "additions": 0,
        "deletions": 50,
        "summary": "Removed deprecated class that was replaced by NewClass",
        "complexity": "low",
        "impact_radius": 1,
        "parameters": null,
        "return_type": null
      },
      
      // External service node
      {
        "id": "external::openai_api",
        "parent_id": null,
        "component_type": "external_service",
        "name": "OpenAI API",
        "file_path": null,
        "old_line_number": null,
        "new_line_number": null,
        "change_type": "unchanged",
        "additions": 0,
        "deletions": 0,
        "summary": "External OpenAI API service for code analysis",
        "complexity": null,
        "impact_radius": 5,           // how many internal components use it
        "parameters": null,
        "return_type": null
      },
      
      // External API endpoint (nested under service)
      {
        "id": "external::openai_api::chat_completions",
        "parent_id": "external::openai_api",
        "component_type": "external_endpoint",
        "name": "chat.completions",
        "file_path": null,
        "old_line_number": null,
        "new_line_number": null,
        "change_type": "unchanged",
        "additions": 0,
        "deletions": 0,
        "summary": "OpenAI chat completions endpoint",
        "complexity": null,
        "impact_radius": 3,
        "parameters": null,
        "return_type": null
      },
      
      // Database node
      {
        "id": "external::postgres_db",
        "parent_id": null,
        "component_type": "external_database",
        "name": "PostgreSQL Database",
        "file_path": null,
        "old_line_number": null,
        "new_line_number": null,
        "change_type": "unchanged",
        "additions": 0,
        "deletions": 0,
        "summary": "Main application database",
        "complexity": null,
        "impact_radius": 10,
        "parameters": null,
        "return_type": null
      },
      
      // Database table (nested under database)
      {
        "id": "external::postgres_db::jobs_table",
        "parent_id": "external::postgres_db",
        "component_type": "database_table",
        "name": "jobs_table",
        "file_path": null,
        "old_line_number": null,
        "new_line_number": null,
        "change_type": "modified",    // schema change detected
        "additions": 2,               // columns added
        "deletions": 0,
        "summary": "Job queue table with status tracking",
        "complexity": null,
        "impact_radius": 5,
        "parameters": null,
        "return_type": null
      }
    ]
  }
}
```

**Component Types**:
- **Source Code**: `class`, `function`, `method`, `interface`, `trait`, `module`, `enum`, `struct`
- **Test Code**: `test_class`, `test_function`, `test_method`
- **External**: `external_service`, `external_endpoint`, `external_database`, `database_table`, `database_collection`, `message_queue`, `cache_store`

#### Component Edges

```json
{
  "edges": [
    // Function call
    {
      "source": "diffgraph/cli.py::main",
      "target": "diffgraph/graph_export.py::export_graph",
      "relationship": "calls",
      "change_type": "added",
      "summary": "CLI conditionally calls export_graph when --format graph is specified"
    },
    
    // REST API call
    {
      "source": "api/handlers.py::process_request",
      "target": "external::openai_api::chat_completions",
      "relationship": "rest_api_call",
      "change_type": "modified",
      "summary": "Updated to use streaming API responses"
    },
    
    // gRPC call
    {
      "source": "client/grpc_client.py::call_service",
      "target": "external::grpc_service::ProcessBatch",
      "relationship": "rpc_call",
      "change_type": "added",
      "summary": "New gRPC call for batch processing"
    },
    
    // Database access
    {
      "source": "worker/processor.py::process_job",
      "target": "external::postgres_db::jobs_table",
      "relationship": "shared_storage",
      "change_type": "modified",
      "summary": "Modified job status update logic"
    },
    
    // Pub/Sub
    {
      "source": "publisher/events.py::emit_event",
      "target": "subscriber/listener.py::handle_event",
      "relationship": "pub_sub",
      "change_type": "added",
      "summary": "New event subscription for job completion notifications"
    },
    
    // Import
    {
      "source": "module_a.py::ComponentA",
      "target": "module_b.py::ComponentB",
      "relationship": "imports",
      "change_type": "deleted",
      "summary": "Removed unused import after refactoring"
    },
    
    // Class inheritance
    {
      "source": "models/user.py::AdminUser",
      "target": "models/user.py::BaseUser",
      "relationship": "extends",
      "change_type": "unchanged",
      "summary": "AdminUser inherits from BaseUser"
    },
    
    // Interface implementation
    {
      "source": "handlers/file_handler.py::S3FileHandler",
      "target": "interfaces/storage.py::StorageInterface",
      "relationship": "implements",
      "change_type": "unchanged",
      "summary": "S3FileHandler implements StorageInterface"
    }
  ]
}
```

**Relationship Types**:
- **Code**: `imports`, `calls`, `extends`, `implements`, `uses`
- **External**: `rest_api_call`, `rpc_call`, `graphql_query`, `websocket_connection`
- **Data**: `shared_storage`, `database_query`, `cache_access`, `file_io`
- **Events**: `pub_sub`, `event_emit`, `event_listen`, `webhook`

**Change Types**: `added`, `deleted`, `modified`, `unchanged`

## Implementation Strategy

### Phase 1: Basic Restructuring (Current Implementation)

**Goal**: Ship a working version that restructures existing data without new analysis.

**What to Implement**:
1. ✅ File classification (basic patterns only, AI for edge cases)
2. ✅ Restructure existing graph data into new schema
3. ✅ Extract additions/deletions from git diff stats
4. ✅ Use existing summaries from AI analysis
5. ✅ Copy component metadata that already exists

**What to Leave Blank** (for Phase 2):
- `complexity`: Set to `null`
- `impact_radius`: Set to `0` or calculate from diff graph only
- `parameters`, `return_type`: Set to `null`
- `cross_references` in docs/config: Empty arrays
- `config_changes` details: Basic summary only
- External nodes: Don't add yet (or add with minimal info if referenced)
- Advanced relationships (REST/RPC/pub-sub): Use generic `calls` for now

**Data Sources for Phase 1**:
- NetworkX graphs: `graph_manager.file_graph`, `graph_manager.component_graph`
- Existing nodes: `graph_manager.file_nodes`, `graph_manager.component_nodes`
- Git diff: Use `git diff --numstat` for additions/deletions
- Existing AI summaries: Already in component/file nodes

### Phase 2: Enhanced Analysis (Future)

**New Analysis Required**:
1. **Complexity Calculation**:
   - Cyclomatic complexity for functions/methods
   - Class complexity (weighted by methods)
   - AI-based complexity assessment

2. **Impact Radius**:
   - Analyze full codebase (not just diff)
   - Build complete dependency graph
   - Calculate transitive dependencies
   - Count upstream + downstream connections

3. **External Dependencies**:
   - Detect external service calls (API, RPC, GraphQL)
   - Identify database/cache/queue access
   - Create external nodes in graph
   - Infer parent relationships (endpoint → service, table → database)

4. **Relationship Detection**:
   - Pattern matching: `requests.post()` → REST, `grpc.call()` → RPC
   - AI analysis: Identify pub/sub, event patterns
   - Database query detection: ORM patterns, raw SQL

5. **Cross-References**:
   - NLP on docs to find component mentions
   - Extract line numbers where components are referenced
   - Link config changes to affected components

6. **Parameter & Return Types**:
   - Parse function signatures
   - Use type hints when available
   - AI inference for dynamic languages

### Phase 3: Advanced Features (Future)

- **Security Analysis**: Identify vulnerable patterns
- **Performance Impact**: Flag performance-critical changes
- **Breaking Changes**: Detect API/signature changes
- **Test Coverage**: Map tests to source components
- **Migration Paths**: Suggest refactoring strategies

## Technical Implementation Notes

### File Classification

```python
# Minimal patterns for Phase 1
AUTO_GENERATED_PATTERNS = [
    '*-lock.json', '*.lock', '*.min.js', '*.min.css',
    'dist/*', 'build/*', '__pycache__/*', '*.pyc'
]

DOC_PATTERNS = [
    '*.md', '*.rst', '*.adoc', 'docs/*', 'documentation/*'
]

CONFIG_PATTERNS = [
    '*.toml', '*.yaml', '*.yml', 'setup.py', 'setup.cfg',
    '.*rc', '.*ignore', 'Makefile', 'Dockerfile'
]

def classify_file(path: str) -> str:
    """Returns: 'auto_generated', 'documentation', 'configuration', or 'source_code'"""
    # Check patterns first
    if matches_patterns(path, AUTO_GENERATED_PATTERNS):
        return 'auto_generated'
    if matches_patterns(path, DOC_PATTERNS):
        return 'documentation'
    if matches_patterns(path, CONFIG_PATTERNS):
        return 'configuration'
    
    # Default to source code
    return 'source_code'
```

### Extracting Git Stats

```python
def get_diff_stats(file_path: str, diff_args: List[str]) -> Dict[str, int]:
    """Get additions/deletions for a file using git diff --numstat"""
    cmd = ['git', 'diff', '--numstat'] + diff_args + ['--', file_path]
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    # Output format: "additions\tdeletions\tfilename"
    if result.stdout:
        parts = result.stdout.strip().split('\t')
        return {
            'additions': int(parts[0]) if parts[0] != '-' else 0,
            'deletions': int(parts[1]) if parts[1] != '-' else 0
        }
    return {'additions': 0, 'deletions': 0}
```

### Mapping Current Data to New Schema

```python
def transform_component_node(component_id: str, component: ComponentNode) -> dict:
    """Transform existing ComponentNode to new schema"""
    return {
        'id': component_id,
        'parent_id': component.parent,
        'component_type': component.component_type,  # already have this
        'name': component.name,
        'file_path': component.file_path,
        'old_line_number': None,  # TODO: extract from git diff
        'new_line_number': None,  # TODO: extract from git diff
        'change_type': component.change_type.value,
        'additions': None,  # TODO: calculate per-component
        'deletions': None,  # TODO: calculate per-component
        'summary': component.summary,
        'complexity': None,  # Phase 2
        'impact_radius': len(component.dependencies) + len(component.dependents),  # Simple calculation
        'parameters': None,  # Phase 2
        'return_type': None  # Phase 2
    }
```

## Testing Strategy

### Unit Tests

- Test file classification for all patterns
- Test transformation of each node/edge type
- Test git stat extraction
- Test handling of missing data (nulls)

### Integration Tests

- Transform a real diff and validate schema
- Compare with current format (should have same info)
- Test with various programming languages
- Test with renames, moves, deletions

### Validation

- JSON schema validation
- Graph completeness (all edge targets exist as nodes)
- No orphaned nodes
- Consistent change_types

## Future Considerations

### Scalability

- Large diffs (100+ files): Streaming output?
- Deep dependency graphs: Limit impact_radius calculation?
- External services: Cache discovered endpoints?

### Extensibility

- Plugin system for custom relationship types
- Custom component types per language/framework
- User-defined classification patterns

### Integration Examples

- VSCode extension consuming this format
- GitHub PR bot showing visual diff
- CI/CD pipeline blocking risky changes
- Documentation auto-update from cross-references

## Migration Path

1. **v1.1.0** (Current): NetworkX format
2. **v1.2.0**: Add structured format, make it default for JSON
3. **v1.3.0**: Enhanced analysis (Phase 2)
4. **v2.0.0**: Deprecate NetworkX format, structured only

## References

- Current implementation: `diffgraph/graph_export.py`
- Graph management: `diffgraph/graph_manager.py`
- AI analysis: `diffgraph/ai_analysis.py`
- Related: [GRAPH_EXPORT_FEATURE.md](./GRAPH_EXPORT_FEATURE.md)

---

**Status**: Ready for Phase 1 implementation
**Next Steps**: Implement basic restructuring without new analysis
**Review Date**: After Phase 1 ships
