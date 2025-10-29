# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.1.0] - 2025-10-28

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
- **Documentation**:
  - Added comprehensive developer guide: `docs/ADDING_PROCESSING_MODES.md`
  - Updated README.md with processing modes information
  - Documented how to create custom processing modes

### Changed
- Refactored `CodeAnalysisAgent` into modular `OpenAIAgentsProcessor`
- Removed direct dependency on `ai_analysis.py` in CLI (now uses processor factory)
- Improved extensibility for adding new analysis approaches (Tree-sitter, data flow, etc.)

### Removed
- `diffgraph/ai_analysis.py` - Functionality moved to `diffgraph/processing_modes/openai_agents_dependency.py`


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