from typing import Dict, List, Set, Optional
from dataclasses import dataclass
from enum import Enum
import networkx as nx
import re
import html

class ChangeType(Enum):
    """Type of change in the code."""
    ADDED = "added"      # New code/components
    DELETED = "deleted"  # Removed code/components
    MODIFIED = "modified"  # Changed code/components
    UNCHANGED = "unchanged"  # Context nodes

class FileStatus(Enum):
    """Status of a file in the analysis process."""
    PENDING = "pending"      # Not yet processed
    PROCESSING = "processing"  # Currently being analyzed
    PROCESSED = "processed"    # Analysis complete
    ERROR = "error"          # Error during analysis

@dataclass
class FileNode:
    """Represents a file node in the graph."""
    path: str
    status: FileStatus
    change_type: ChangeType
    summary: Optional[str] = None
    error: Optional[str] = None
    components: List[Dict] = None  # List of components (functions, classes, etc.) in the file

    def __post_init__(self):
        if self.components is None:
            self.components = []

@dataclass
class ComponentNode:
    """Represents a code component (function, class, etc.) in the graph."""
    name: str
    file_path: str
    change_type: ChangeType
    component_type: str  # container, function, method
    parent: Optional[str] = None  # name of the parent component if nested
    summary: Optional[str] = None
    dependencies: List[str] = None  # List of component names this depends on
    dependents: List[str] = None    # List of component names that depend on this

    def __post_init__(self):
        if self.dependencies is None:
            self.dependencies = []
        if self.dependents is None:
            self.dependents = []

class GraphManager:
    """Manages the graph of file dependencies and analysis state."""

    def __init__(self):
        """Initialize an empty graph."""
        self.file_graph = nx.DiGraph()  # Graph for file-level dependencies
        self.component_graph = nx.DiGraph()  # Graph for component-level dependencies
        self.file_nodes: Dict[str, FileNode] = {}
        self.component_nodes: Dict[str, ComponentNode] = {}
        self.processing_queue: List[str] = []  # BFS queue
        self.processed_files: Set[str] = set()

    def _sanitize_tooltip(self, text: str) -> str:
        """
        Sanitize text for Mermaid tooltips.
        Handles escape sequences, preserves intentional spacing, escapes HTML, and removes Mermaid-breaking characters.
        """
        if not text:
            return ""

        # Replace escape sequences with spaces while preserving intentional spacing
        text = text.replace('\n', ' ').replace('\r', ' ').replace('\t', ' ')

        # Then escape HTML special characters
        text = html.escape(text)

        # Remove backticks and backslashes as they can break Mermaid syntax
        text = text.replace('`', '').replace('\\', '')

        return text

    def add_file(self, file_path: str, change_type: ChangeType) -> None:
        """Add a new file to the graph if it doesn't exist."""
        if file_path not in self.file_nodes:
            self.file_nodes[file_path] = FileNode(
                path=file_path,
                status=FileStatus.PENDING,
                change_type=change_type
            )
            self.file_graph.add_node(file_path)
            self.processing_queue.append(file_path)

    def add_component(self, name: str, file_path: str, change_type: ChangeType, component_type: str, parent: Optional[str] = None, summary: str = None, dependencies: list = None, dependents: list = None) -> None:
        """Add a new component to the graph."""
        component_id = f"{file_path}::{name}"
        # Clean up dependencies and dependents lists
        dependencies = [d for d in (dependencies or []) if d]
        dependents = [d for d in (dependents or []) if d]

        if component_id not in self.component_nodes:
            self.component_nodes[component_id] = ComponentNode(
                name=name,
                file_path=file_path,
                change_type=change_type,
                component_type=component_type,
                parent=parent,
                summary=summary,
                dependencies=dependencies,
                dependents=dependents
            )
            self.component_graph.add_node(component_id)
        else:
            # Update existing component
            existing = self.component_nodes[component_id]
            existing.summary = summary or existing.summary
            existing.dependencies = dependencies or existing.dependencies
            existing.dependents = dependents or existing.dependents
            existing.component_type = component_type
            existing.parent = parent

    def add_component_dependency(self, source: str, target: str) -> None:
        """Add a dependency relationship between components."""
        if not source or not target or source == target:
            return

        if source in self.component_nodes and target in self.component_nodes:
            if not self.component_graph.has_edge(source, target):
                self.component_graph.add_edge(source, target)
                if target not in self.component_nodes[source].dependencies:
                    self.component_nodes[source].dependencies.append(target)
                if source not in self.component_nodes[target].dependents:
                    self.component_nodes[target].dependents.append(source)

    def get_next_file(self) -> Optional[str]:
        """Get the next file to process from the queue."""
        while self.processing_queue:
            file_path = self.processing_queue.pop(0)
            if file_path not in self.processed_files:
                return file_path
        return None

    def mark_processing(self, file_path: str) -> None:
        """Mark a file as being processed."""
        if file_path in self.file_nodes:
            self.file_nodes[file_path].status = FileStatus.PROCESSING

    def mark_processed(self, file_path: str, summary: str, components: List[Dict]) -> None:
        """Mark a file as processed with its analysis summary and components."""
        if file_path in self.file_nodes:
            self.file_nodes[file_path].status = FileStatus.PROCESSED
            self.file_nodes[file_path].summary = summary
            self.file_nodes[file_path].components = components
            self.processed_files.add(file_path)

    def mark_error(self, file_path: str, error: str) -> None:
        """Mark a file as having an error during processing."""
        if file_path in self.file_nodes:
            self.file_nodes[file_path].status = FileStatus.ERROR
            self.file_nodes[file_path].error = error
            self.processed_files.add(file_path)

    def get_connected_components(self, start_component: str, max_depth: int = 3) -> Set[str]:
        """Get all components connected to the start component within max_depth."""
        connected = set()
        queue = [(start_component, 0)]  # (component_id, depth)

        while queue:
            current, depth = queue.pop(0)
            if depth > max_depth:
                continue

            connected.add(current)

            # Add dependencies
            for dep in self.component_nodes[current].dependencies:
                if dep not in connected:
                    queue.append((dep, depth + 1))

            # Add dependents
            for dep in self.component_nodes[current].dependents:
                if dep not in connected:
                    queue.append((dep, depth + 1))

        return connected

    def get_mermaid_diagram(self) -> str:
        """Generate a Mermaid diagram representation of the graph."""
        mermaid = ["graph LR"]

        # Group components by their file paths and create a hierarchy
        file_components = {}
        component_hierarchy = {}  # parent -> children mapping

        for component_id, node in self.component_nodes.items():
            if node.file_path not in file_components:
                file_components[node.file_path] = []
            file_components[node.file_path].append((component_id, node))

            # If this component has a parent, add it to the hierarchy
            if hasattr(node, 'parent') and node.parent:
                parent_id = f"{node.file_path}::{node.parent}"
                if parent_id not in component_hierarchy:
                    component_hierarchy[parent_id] = []
                component_hierarchy[parent_id].append(component_id)

        # Add file nodes as subgraphs with their components inside
        for file_path, node in self.file_nodes.items():
            # Create a valid ID for the file node
            file_id = re.sub(r'[^a-zA-Z0-9_]', '_', file_path)

            # Create a properly escaped label
            file_label = file_path.replace('"', '\\"').replace('`', '\\`')
            if node.error:
                file_label += f"<br/>(Error: {node.error})"

            mermaid.append(f'    subgraph {file_id}["{file_label}"]')
            mermaid.append(f'        direction TB')
            mermaid.append(f'        class {file_id} file_{node.change_type.value}')

            # Add components within this file
            if file_path in file_components:
                # First add container components
                for component_id, comp_node in file_components[file_path]:
                    if hasattr(comp_node, 'component_type') and comp_node.component_type == 'container':
                        comp_id = re.sub(r'[^a-zA-Z0-9_]', '_', component_id)
                        component_label = comp_node.name.replace('"', '\\"').replace('`', '\\`')

                        # Create a subgraph for the container
                        mermaid.append(f'        subgraph {comp_id}["{component_label}"]')
                        mermaid.append(f'            direction TB')
                        mermaid.append(f'            class {comp_id} component_{comp_node.change_type.value}')

                        # Add nested components if any
                        if component_id in component_hierarchy:
                            for nested_id in component_hierarchy[component_id]:
                                nested_node = self.component_nodes[nested_id]
                                nested_comp_id = re.sub(r'[^a-zA-Z0-9_]', '_', nested_id)
                                nested_label = nested_node.name.replace('"', '\\"').replace('`', '\\`')
                                if nested_node.summary:
                                    mermaid.append(f'            {nested_comp_id}["{nested_label}"]:::component_{nested_node.change_type.value}')
                                    sanitized_summary = self._sanitize_tooltip(nested_node.summary)
                                    mermaid.append(f'            click {nested_comp_id} call callback("{sanitized_summary}") "{sanitized_summary}"')
                                else:
                                    mermaid.append(f'            {nested_comp_id}["{nested_label}"]:::component_{nested_node.change_type.value}')
                                mermaid.append(f'            class {nested_comp_id} component_{nested_node.change_type.value}')

                        mermaid.append('        end')
                        mermaid.append(f'        {comp_id}:::component_{comp_node.change_type.value}')

                # Then add standalone components (functions, methods without containers)
                for component_id, comp_node in file_components[file_path]:
                    if not hasattr(comp_node, 'component_type') or comp_node.component_type != 'container':
                        if not hasattr(comp_node, 'parent') or not comp_node.parent:  # Only add if not nested
                            comp_id = re.sub(r'[^a-zA-Z0-9_]', '_', component_id)
                            component_label = comp_node.name.replace('"', '\\"').replace('`', '\\`')
                            if comp_node.summary:
                                summary_txt = json.dumps(comp_node.summary)
                                mermaid.append(f'        {comp_id}["{component_label}"]:::component_{comp_node.change_type.value}')
                                sanitized_summary = self._sanitize_tooltip(comp_node.summary)
                                mermaid.append(f'        click {comp_id} call callback("{sanitized_summary}") "{sanitized_summary}"')
                            else:
                                mermaid.append(f'        {comp_id}["{component_label}"]:::component_{comp_node.change_type.value}')
                            mermaid.append(f'        class {comp_id} component_{comp_node.change_type.value}')

            mermaid.append('    end')

        # Add edges between components
        for source, target in self.component_graph.edges():
            source_id = re.sub(r'[^a-zA-Z0-9_]', '_', source)
            target_id = re.sub(r'[^a-zA-Z0-9_]', '_', target)
            mermaid.append(f'    {source_id} --> {target_id}')

        # Add style definitions for files (lighter shades)
        mermaid.append("    classDef file_added fill:#90EE90,stroke:#333,stroke-width:2px")  # Light green
        mermaid.append("    classDef file_deleted fill:#FFB6C1,stroke:#333,stroke-width:2px")  # Light red
        mermaid.append("    classDef file_modified fill:#FFD580,stroke:#333,stroke-width:2px")  # Light orange
        mermaid.append("    classDef file_unchanged fill:#D3D3D3,stroke:#333,stroke-width:2px")  # Light gray

        # Add style definitions for components (darker shades)
        mermaid.append("    classDef component_added fill:#32CD32,stroke:#333,stroke-width:2px")  # Lime green
        mermaid.append("    classDef component_deleted fill:#DC143C,stroke:#333,stroke-width:2px")  # Crimson
        mermaid.append("    classDef component_modified fill:#FF8C00,stroke:#333,stroke-width:2px")  # Dark orange
        mermaid.append("    classDef component_unchanged fill:#808080,stroke:#333,stroke-width:2px")  # Gray
        mermaid.append("    classDef hidden fill:none,stroke:none")

        return "\n".join(mermaid)