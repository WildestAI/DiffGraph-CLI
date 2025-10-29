# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- **Tree-sitter Dependency Extraction (Phase 1)**: Static AST-based analysis mode
  - New `tree-sitter-dependency-graph` processing mode
  - Multi-language support framework for Python, TypeScript, JavaScript, Go, Rust, Java, Swift
  - Python extraction fully implemented: classes, functions, methods, imports
  - Component relationship extraction from static analysis
  - Uses tree-sitter-language-pack for fast, accurate parsing
  - No AI/API calls required - pure static analysis

### Changed
- Added `tree-sitter-language-pack>=0.10.0` dependency to setup.py
- Made tree-sitter processor optional (graceful fallback if not installed)

## [1.3.0] - 2025-10-28

### Added
- **Processing Modes System**: Introduced modular architecture for different diffgraph generation strategies
  - Created `BaseProcessor` abstract class for implementing custom processing modes
  - Added processor registry and factory pattern for mode instantiation
  - Implemented `@register_processor` decorator for automatic mode registration
- **OpenAI Agents Dependency Graph Mode**: Refactored existing AI analysis into `openai-agents-dependency-graph` mode
  - Maintains all existing functionality as the default processing mode
  - Analyzes code at component level (classes, functions, methods)
  - Generates dependency graphs showing component relationships
- **CLI Enhancements**:
  - Added `--mode` / `-m` option to select processing mode
  - Added `--list-modes` flag to display available processing modes
  - Default mode: `openai-agents-dependency-graph` (backward compatible)
- **Graph Export Integration**: Merged graph export features from v1.2.0
  - `--format` option to export graph data (JSON, pickle, GraphML)
  - Structured JSON output format optimized for integrations
- **Documentation**:
  - Added comprehensive developer guide: `docs/ADDING_PROCESSING_MODES.md`
  - Updated README.md with processing modes information
  - Documented how to create custom processing modes
- **Comprehensive Test Suite**:
  - Created tests/ directory with proper pytest structure
  - Added tests for BaseProcessor, registry, OpenAI processor, and CLI options

### Changed
- Refactored `CodeAnalysisAgent` into modular `OpenAIAgentsProcessor`
- Removed direct dependency on `ai_analysis.py` in CLI (now uses processor factory)
- Improved extensibility for adding new analysis approaches (Tree-sitter, data flow, etc.)

### Removed
- `diffgraph/ai_analysis.py` - Functionality moved to `diffgraph/processing_modes/openai_agents_dependency.py`

## [1.2.0] - 2025-10-24

### Added
- **Structured JSON Output Format (Phase 1)**: Integration-friendly JSON format optimized for VSCode extensions and UIs
  - New `diffgraph/structured_export.py` module for structured data transformation
  - Automatic file categorization: `auto_generated`, `documentation`, `configuration`, `source_code`
  - Rich metadata including git diff stats (additions/deletions per file)
  - Impact radius calculation from dependency graphs
  - Clean separation of files and components with explicit graph structure
  - Complete graph validation (all edge targets exist as nodes)
  - Pattern-based classification with 40+ common patterns
- Comprehensive test suite (`test_structured_export.py`) for structured export
- Design documentation in `docs/planning/` for future enhancements

### Changed
- **JSON format now uses structured output by default** (breaking change for JSON, but backwards compatible overall)
  - `--format graph --graph-format json`: Now outputs structured format
  - `--format graph --graph-format pickle`: Still uses NetworkX format
  - `--format graph --graph-format graphml`: Still uses NetworkX format
- Updated README with structured JSON examples and usage patterns
- Enhanced documentation to explain categorization and structure

### Technical Details
- Phase 1 implementation uses existing analysis data
- Advanced fields (complexity, line numbers, parameters) reserved for Phase 2
- External dependency nodes reserved for Phase 2
- Advanced relationship detection (REST/RPC/pub-sub) reserved for Phase 2
- Structure designed for iterative enhancement without breaking changes

## [1.1.0] - 2025-10-24

### Added
- **Graph Data Export Feature**: Export complete networkx graph data structure to file
  - New `--format` option to choose between HTML and graph output formats
  - New `--graph-format` option to select serialization format (json, pickle, graphml)
  - Support for JSON export (human-readable, widely compatible)
  - Support for Pickle export (Python-native, preserves exact data structures)
  - Support for GraphML export (standard graph format for analysis tools)
  - New `diffgraph/graph_export.py` module with export/import functions
  - `export_to_dict()` method added to GraphManager for serialization
  - `load_graph_from_json()` and `load_graph_from_pickle()` functions for loading exported data
- Comprehensive test suite (`test_graph_export.py`) for graph export functionality
- Example usage script (`example_usage.py`) demonstrating how to use exported data
- Automated test script (`test_cli_manual.sh`) for easy feature validation
- Documentation: `GRAPH_EXPORT_FEATURE.md` and `TESTING_GUIDE.md`

### Changed
- Updated `--output` option description to reflect format-aware default paths
- Enhanced README with graph export documentation and usage examples
- Updated feature list to include graph data export capabilities

### Technical Details
- Exported data includes file nodes, component nodes, dependency graphs, and metadata
- All graph data can be loaded back into GraphManager for programmatic analysis
- NetworkX graphs are serialized using node-link format for compatibility
- Backward compatible: existing HTML output functionality unchanged

## [1.0.0] - 2025-08-06

### Changed
- **BREAKING CHANGE**: Renamed CLI command from `diffgraph-ai` to `wild`
  - Updated all documentation to reflect the new command name
  - Updated setup.py entry point to use `wild` command
  - All usage examples now use `wild` instead of `diffgraph-ai`
  - This is a breaking change - users will need to update their scripts and documentation

### Fixed
- Fixed `--version` command not working after CLI rename by explicitly specifying `package_name='wild'` in `@click.version_option()`
- Improved path handling in environment loader by wrapping paths with `os.path.normpath()` for better cross-platform compatibility
- Removed redundant `hasattr(sys, 'executable')` check as `sys.executable` is always available in Python

## [0.1.0] - 2025-06-06

### Added
- Initial release of DiffGraph CLI tool
- AI-powered code change analysis
- HTML report generation with Mermaid.js dependency graphs
- Support for both tracked and untracked files
- Dark mode support in HTML reports
- Syntax highlighting for code blocks
- Responsive design for all screen sizes