"""
Structured export module for generating integration-friendly JSON output.

This module transforms the internal NetworkX graph representation into a
structured format optimized for consumption by VSCode extensions, web UIs,
and other integrations.

Phase 1: Uses existing analysis data, leaves advanced fields as null.
Phase 2+: Will add full codebase analysis, external dependencies, etc.
"""

import json
import subprocess
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime, timezone
from .graph_manager import GraphManager, FileNode, ComponentNode, ChangeType


# File classification patterns
AUTO_GENERATED_PATTERNS = [
    '*-lock.json', '*.lock', 'yarn.lock', 'Gemfile.lock', 'Cargo.lock',
    '*.min.js', '*.min.css', '*.bundle.js',
    'dist/*', 'build/*', 'target/*', 'out/*', '.next/*',
    '__pycache__/*', '*.pyc', '*.class', '*.o', '*.so',
    'package-lock.json', 'composer.lock', 'poetry.lock',
    '.DS_Store', 'Thumbs.db'
]

DOC_PATTERNS = [
    '*.md', '*.rst', '*.adoc',
    'docs/*', 'documentation/*', 'doc/*',
    'CHANGELOG.*', 'HISTORY.*', 'AUTHORS.*', 'CONTRIBUTORS.*'
]

CONFIG_PATTERNS = [
    '*.toml', '*.yaml', '*.yml', 'setup.py', 'setup.cfg', 'pyproject.toml',
    '.*rc', '.*ignore', 'Makefile', 'Dockerfile', 'docker-compose.yml',
    'package.json', 'tsconfig.json', 'webpack.config.js',
    'requirements.txt', 'Pipfile', 'Gemfile'
]


def matches_pattern(file_path: str, patterns: List[str]) -> bool:
    """Check if file path matches any of the given patterns."""
    from fnmatch import fnmatch
    for pattern in patterns:
        if fnmatch(file_path, pattern):
            return True
    return False


def classify_file(file_path: str) -> str:
    """
    Classify a file into one of four categories.

    Priority order:
    1. Auto-generated (highest priority)
    2. Configuration (before docs to catch requirements.txt)
    3. Documentation
    4. Source code (default)

    Args:
        file_path: Path to the file

    Returns:
        One of: 'auto_generated', 'documentation', 'configuration', 'source_code'
    """
    if matches_pattern(file_path, AUTO_GENERATED_PATTERNS):
        return 'auto_generated'
    if matches_pattern(file_path, CONFIG_PATTERNS):
        return 'configuration'
    if matches_pattern(file_path, DOC_PATTERNS):
        return 'documentation'
    return 'source_code'


def get_file_stats(file_path: str, diff_args: List[str]) -> Dict[str, int]:
    """
    Get git diff stats (additions/deletions) for a file.

    Args:
        file_path: Path to the file
        diff_args: Git diff arguments (e.g., ['HEAD~1', 'HEAD'])

    Returns:
        Dictionary with 'additions' and 'deletions' counts
    """
    try:
        cmd = ['git', 'diff', '--numstat'] + diff_args + ['--', file_path]
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)

        if result.returncode == 0 and result.stdout.strip():
            # Output format: "additions\tdeletions\tfilename"
            parts = result.stdout.strip().split('\t')
            if len(parts) >= 2:
                additions = int(parts[0]) if parts[0] != '-' else 0
                deletions = int(parts[1]) if parts[1] != '-' else 0
                return {'additions': additions, 'deletions': deletions}
    except Exception as e:
        print(f"Warning: Could not get stats for {file_path}: {e}")

    return {'additions': 0, 'deletions': 0}


def get_language_from_extension(file_path: str) -> Optional[str]:
    """Determine programming language from file extension."""
    ext_map = {
        '.py': 'python',
        '.js': 'javascript',
        '.ts': 'typescript',
        '.jsx': 'javascript',
        '.tsx': 'typescript',
        '.java': 'java',
        '.go': 'go',
        '.rs': 'rust',
        '.rb': 'ruby',
        '.php': 'php',
        '.c': 'c',
        '.cpp': 'cpp',
        '.h': 'c',
        '.hpp': 'cpp',
        '.cs': 'csharp',
        '.swift': 'swift',
        '.kt': 'kotlin',
        '.sh': 'shell',
        '.bash': 'shell',
    }

    ext = Path(file_path).suffix
    return ext_map.get(ext)


def determine_relationship_type(source_id: str, target_id: str,
                               graph_manager: GraphManager) -> str:
    """
    Determine the relationship type between two components.

    Phase 1: Simple heuristics based on names and types.
    Phase 2: Will use AI and pattern matching for advanced detection.

    Args:
        source_id: Source component ID
        target_id: Target component ID
        graph_manager: GraphManager instance

    Returns:
        Relationship type string
    """
    # Default to 'calls'
    relationship = 'calls'

    # Get component types if available
    source = graph_manager.component_nodes.get(source_id)
    target = graph_manager.component_nodes.get(target_id)

    if source and target:
        # Check for inheritance patterns
        if source.component_type == 'class' and target.component_type == 'class':
            if 'extends' in (source.summary or '').lower() or 'inherit' in (source.summary or '').lower():
                relationship = 'extends'

        # Check for interface implementation
        if source.component_type == 'class' and target.component_type == 'interface':
            relationship = 'implements'

        # If both are in same file, might be internal reference
        if source.file_path == target.file_path:
            if source.parent == target_id:
                relationship = 'member_of'

    return relationship


def transform_component_node(component_id: str,
                            component: ComponentNode,
                            graph_manager: GraphManager) -> Dict[str, Any]:
    """
    Transform a ComponentNode to structured format.

    Phase 1: Uses existing data, leaves some fields as null.
    """
    # Simple impact radius calculation from existing dependencies
    impact_radius = len(component.dependencies) + len(component.dependents)

    return {
        'id': component_id,
        'parent_id': component.parent,
        'component_type': component.component_type,
        'name': component.name,
        'file_path': component.file_path,
        'old_line_number': None,  # Phase 2: extract from git diff
        'new_line_number': None,  # Phase 2: extract from git diff
        'change_type': component.change_type.value,
        'additions': None,  # Phase 2: per-component diff analysis
        'deletions': None,  # Phase 2: per-component diff analysis
        'summary': component.summary,
        'complexity': None,  # Phase 2: cyclomatic complexity
        'impact_radius': impact_radius,
        'parameters': None,  # Phase 2: signature parsing
        'return_type': None  # Phase 2: signature parsing
    }


def transform_file_node(file_path: str,
                       file_node: FileNode,
                       diff_args: List[str]) -> Dict[str, Any]:
    """
    Transform a FileNode to structured format.
    """
    stats = get_file_stats(file_path, diff_args)
    language = get_language_from_extension(file_path)

    return {
        'path': file_path,
        'name': Path(file_path).name,
        'type': 'test' if 'test' in file_path.lower() else 'src',
        'change_type': file_node.change_type.value,
        'additions': stats['additions'],
        'deletions': stats['deletions'],
        'summary': file_node.summary or '',
        'language': language,
        'old_path': None  # Phase 2: detect file renames
    }


def transform_component_edge(source: str,
                            target: str,
                            graph_manager: GraphManager) -> Dict[str, Any]:
    """
    Transform a component edge to structured format.
    """
    relationship = determine_relationship_type(source, target, graph_manager)

    # For Phase 1, we'll mark all edges as 'added' if they exist in the graph
    # Phase 2 will properly detect added/deleted/modified/unchanged
    return {
        'source': source,
        'target': target,
        'relationship': relationship,
        'change_type': 'added',  # Simplified for Phase 1
        'summary': ''  # Phase 2: generate edge-specific summaries
    }


def transform_file_edge(source: str,
                       target: str,
                       graph_manager: GraphManager) -> Dict[str, Any]:
    """
    Transform a file edge to structured format.
    """
    return {
        'source': source,
        'target': target,
        'relationship': 'imports',
        'change_type': 'added',  # Simplified for Phase 1
        'summary': f'{Path(source).name} imports {Path(target).name}'
    }


def categorize_files(graph_manager: GraphManager,
                    diff_args: List[str]) -> Tuple[List[Dict], Dict[str, Dict],
                                                   Dict[str, Dict], Dict[str, Any]]:
    """
    Categorize files into auto_generated, documentation, configuration, and source_code.

    Returns:
        Tuple of (auto_generated, documentation, configuration, source_code)
    """
    auto_generated = []
    documentation = {}
    configuration = {}
    source_files = []

    for file_path, file_node in graph_manager.file_nodes.items():
        category = classify_file(file_path)
        stats = get_file_stats(file_path, diff_args)

        if category == 'auto_generated':
            auto_generated.append({
                'path': file_path,
                'classification_method': 'pattern',
                'reason': 'Matches auto-generated file pattern',
                'additions': stats['additions'],
                'deletions': stats['deletions']
            })

        elif category == 'documentation':
            documentation[file_path] = {
                'additions': stats['additions'],
                'deletions': stats['deletions'],
                'summary': file_node.summary or '',
                'sections_modified': [],  # Phase 2
                'cross_references': []  # Phase 2
            }

        elif category == 'configuration':
            configuration[file_path] = {
                'additions': stats['additions'],
                'deletions': stats['deletions'],
                'summary': file_node.summary or '',
                'config_changes': [],  # Phase 2
                'cross_references': []  # Phase 2
            }

        else:  # source_code
            source_files.append(file_path)

    return auto_generated, documentation, configuration, source_files


def transform_to_structured_format(graph_manager: GraphManager,
                                  diff_args: List[str],
                                  diff_base: str = 'main',
                                  diff_target: str = 'HEAD') -> Dict[str, Any]:
    """
    Transform NetworkX graph data to structured format.

    Args:
        graph_manager: GraphManager instance with analyzed data
        diff_args: Git diff arguments used for analysis
        diff_base: Base git ref for the diff
        diff_target: Target git ref for the diff

    Returns:
        Structured format dictionary
    """
    # Categorize files
    auto_gen, docs, config, source_files = categorize_files(graph_manager, diff_args)

    # Calculate total stats
    total_files = len(graph_manager.file_nodes)
    total_additions = sum(get_file_stats(f, diff_args)['additions']
                         for f in graph_manager.file_nodes.keys())
    total_deletions = sum(get_file_stats(f, diff_args)['deletions']
                         for f in graph_manager.file_nodes.keys())

    # Build source code section
    source_code = {
        'files': {
            'nodes': [],
            'edges': []
        },
        'components': {
            'nodes': [],
            'edges': []
        }
    }

    # Add file nodes for source code files
    for file_path in source_files:
        file_node = graph_manager.file_nodes[file_path]
        source_code['files']['nodes'].append(
            transform_file_node(file_path, file_node, diff_args)
        )

    # Add file edges
    for source, target in graph_manager.file_graph.edges():
        if source in source_files and target in source_files:
            source_code['files']['edges'].append(
                transform_file_edge(source, target, graph_manager)
            )

    # Add component nodes
    for component_id, component in graph_manager.component_nodes.items():
        # Only include components from source code files
        if component.file_path in source_files:
            source_code['components']['nodes'].append(
                transform_component_node(component_id, component, graph_manager)
            )

    # Add component edges
    for source, target in graph_manager.component_graph.edges():
        # Only include edges where both nodes are in source code
        source_comp = graph_manager.component_nodes.get(source)
        target_comp = graph_manager.component_nodes.get(target)
        if (source_comp and target_comp and
            source_comp.file_path in source_files and
            target_comp.file_path in source_files):
            source_code['components']['edges'].append(
                transform_component_edge(source, target, graph_manager)
            )

    # Build final structure
    return {
        'version': '2.0',
        'metadata': {
            'analyzed_at': datetime.now(timezone.utc).isoformat(),
            'diff_base': diff_base,
            'diff_target': diff_target,
            'total_files_changed': total_files,
            'total_additions': total_additions,
            'total_deletions': total_deletions,
            'analyzer_version': '1.2.0'  # TODO: Get from package
        },
        'auto_generated': auto_gen,
        'documentation': docs,
        'configuration': config,
        'source_code': source_code
    }


def export_structured_json(graph_manager: GraphManager,
                          output_path: str,
                          diff_args: List[str] = None,
                          diff_base: str = 'main',
                          diff_target: str = 'HEAD') -> str:
    """
    Export graph data in structured JSON format.

    Args:
        graph_manager: GraphManager instance with analyzed data
        output_path: Path where JSON file should be saved
        diff_args: Git diff arguments (default: empty list)
        diff_base: Base git ref for the diff
        diff_target: Target git ref for the diff

    Returns:
        Absolute path to the generated JSON file
    """
    if diff_args is None:
        diff_args = []

    # Transform to structured format
    structured_data = transform_to_structured_format(
        graph_manager, diff_args, diff_base, diff_target
    )

    # Write to JSON file
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(structured_data, f, indent=2, ensure_ascii=False)

    return str(Path(output_path).absolute())
