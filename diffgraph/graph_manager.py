from typing import Dict, List, Set, Optional
from dataclasses import dataclass
from enum import Enum
import networkx as nx
import json, re

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

    def add_component(self, name: str, file_path: str, change_type: ChangeType, summary: str = None, dependencies: list = None, dependents: list = None) -> None:
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

        file_classes = []
        component_classes = []

        # Group components by their file paths
        file_components = {}
        for component_id, node in self.component_nodes.items():
            if node.file_path not in file_components:
                file_components[node.file_path] = []
            file_components[node.file_path].append((component_id, node))

        # Add file nodes as subgraphs with their components inside
        for file_path, node in self.file_nodes.items():
            file_id = file_path.replace("/", "_")
            file_label = file_path
            if node.error:
                file_label += f"<br/>(Error: {node.error})"
            mermaid.append(f'    subgraph {file_id}["{file_label}"]')
            mermaid.append(f'        direction TB')
            file_classes.append(f'class {file_id} file_{node.change_type.value}')
            # Add components within this file
            if file_path in file_components:
                for component_id, comp_node in file_components[file_path]:
                    comp_id = re.sub(r'[^a-zA-Z0-9_]', '_', component_id)
                    component_label = comp_node.name.replace('"', '\\"').replace('`', '\\`')
                    if comp_node.summary:
                        summary_txt = json.dumps(comp_node.summary)
                        mermaid.append(f'        {comp_id}["{component_label}"]:::component_{comp_node.change_type.value}')
                        mermaid.append(f'        click {comp_id} call callback("{summary_txt}") "{summary_txt}"')
                    else:
                        mermaid.append(f'        {comp_id}["{component_label}"]:::component_{comp_node.change_type.value}')
            mermaid.append('    end')

        # Add edges between components
        for source, target in self.component_graph.edges():
            src_id = re.sub(r'[^a-zA-Z0-9_]', '_', source)
            tgt_id = re.sub(r'[^a-zA-Z0-9_]', '_', target)
            mermaid.append(f'    {src_id} --> {tgt_id}')

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

        # Add explicit class statements for files and components
        mermaid.extend(file_classes)
        mermaid.extend(component_classes)

        return "\n".join(mermaid)