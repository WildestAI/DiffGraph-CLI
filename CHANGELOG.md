# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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