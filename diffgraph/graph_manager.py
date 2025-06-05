from typing import Dict, List, Set, Optional
from dataclasses import dataclass
from enum import Enum
import networkx as nx

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

    def add_component(self, name: str, file_path: str, change_type: ChangeType) -> None:
        """Add a new component to the graph."""
        component_id = f"{file_path}::{name}"
        if component_id not in self.component_nodes:
            self.component_nodes[component_id] = ComponentNode(
                name=name,
                file_path=file_path,
                change_type=change_type
            )
            self.component_graph.add_node(component_id)

    def add_component_dependency(self, source: str, target: str) -> None:
        """Add a dependency relationship between components."""
        if source in self.component_nodes and target in self.component_nodes:
            self.component_graph.add_edge(source, target)
            self.component_nodes[source].dependencies.append(target)
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
        mermaid = ["graph TD"]

        # Add file nodes with their change type colors
        for file_path, node in self.file_nodes.items():
            color = {
                ChangeType.ADDED: "green",
                ChangeType.DELETED: "red",
                ChangeType.MODIFIED: "orange",
                ChangeType.UNCHANGED: "gray"
            }[node.change_type]

            label = f"{file_path}"
            if node.summary:
                label += f"<br/>{node.summary[:50]}..."
            if node.error:
                label += f"<br/>(Error: {node.error})"

            mermaid.append(f'    {file_path.replace("/", "_")}["{label}"]:::change_{node.change_type.value}')

        # Add component nodes
        for component_id, node in self.component_nodes.items():
            color = {
                ChangeType.ADDED: "green",
                ChangeType.DELETED: "red",
                ChangeType.MODIFIED: "orange",
                ChangeType.UNCHANGED: "gray"
            }[node.change_type]

            label = f"{node.name}"
            if node.summary:
                label += f"<br/>{node.summary[:50]}..."

            mermaid.append(f'    {component_id.replace("/", "_").replace("::", "_")}["{label}"]:::change_{node.change_type.value}')

        # Add edges between components
        for source, target in self.component_graph.edges():
            mermaid.append(f'    {source.replace("/", "_").replace("::", "_")} --> {target.replace("/", "_").replace("::", "_")}')

        # Add style definitions
        mermaid.append("    classDef change_added fill:green,stroke:#333,stroke-width:2px")
        mermaid.append("    classDef change_deleted fill:red,stroke:#333,stroke-width:2px")
        mermaid.append("    classDef change_modified fill:orange,stroke:#333,stroke-width:2px")
        mermaid.append("    classDef change_unchanged fill:gray,stroke:#333,stroke-width:2px")

        return "\n".join(mermaid)