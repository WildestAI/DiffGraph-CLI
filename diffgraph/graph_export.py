import json
import pickle
from pathlib import Path
from typing import Dict, Any, Optional
import networkx as nx
from networkx.readwrite import json_graph
from .graph_manager import GraphManager, FileNode, ComponentNode, ChangeType, FileStatus


def export_graph_to_json(graph_manager: GraphManager, output_path: str) -> str:
    """
    Export graph data to JSON format.
    
    Args:
        graph_manager: GraphManager instance containing the graphs
        output_path: Path where the JSON file should be saved
        
    Returns:
        Path to the generated JSON file
    """
    # Prepare the data structure
    data = _prepare_graph_data(graph_manager)
    
    # Write to JSON file
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    
    return str(Path(output_path).absolute())


def export_graph_to_pickle(graph_manager: GraphManager, output_path: str) -> str:
    """
    Export graph data to pickle format.
    
    Args:
        graph_manager: GraphManager instance containing the graphs
        output_path: Path where the pickle file should be saved
        
    Returns:
        Path to the generated pickle file
    """
    # Prepare the data structure
    data = _prepare_graph_data(graph_manager)
    
    # Write to pickle file
    with open(output_path, 'wb') as f:
        pickle.dump(data, f)
    
    return str(Path(output_path).absolute())


def export_graph_to_graphml(graph_manager: GraphManager, output_path: str) -> str:
    """
    Export graph data to GraphML format.
    
    Args:
        graph_manager: GraphManager instance containing the graphs
        output_path: Path where the GraphML file should be saved
        
    Returns:
        Path to the generated GraphML file
    """
    # GraphML doesn't support complex objects, so we'll create simplified versions
    # with serialized attributes
    
    # Create a combined graph for GraphML export
    combined_graph = nx.DiGraph()
    
    # Add file nodes
    for file_path, node in graph_manager.file_nodes.items():
        combined_graph.add_node(
            file_path,
            node_type='file',
            status=node.status.value,
            change_type=node.change_type.value,
            summary=node.summary or '',
            error=node.error or '',
            components=json.dumps([c.name if hasattr(c, 'name') else str(c) for c in (node.components or [])])
        )
    
    # Add component nodes
    for component_id, node in graph_manager.component_nodes.items():
        combined_graph.add_node(
            component_id,
            node_type='component',
            name=node.name,
            file_path=node.file_path,
            change_type=node.change_type.value,
            component_type=node.component_type,
            parent=node.parent or '',
            summary=node.summary or '',
            dependencies=json.dumps(node.dependencies),
            dependents=json.dumps(node.dependents)
        )
    
    # Add edges from both graphs
    for source, target in graph_manager.file_graph.edges():
        combined_graph.add_edge(source, target, graph_type='file')
    
    for source, target in graph_manager.component_graph.edges():
        combined_graph.add_edge(source, target, graph_type='component')
    
    # Write to GraphML file
    nx.write_graphml(combined_graph, output_path)
    
    return str(Path(output_path).absolute())


def _prepare_graph_data(graph_manager: GraphManager) -> Dict[str, Any]:
    """
    Prepare graph data for serialization.
    
    Args:
        graph_manager: GraphManager instance containing the graphs
        
    Returns:
        Dictionary containing all graph data and metadata
    """
    # Convert file nodes to serializable format
    file_nodes_data = {}
    for file_path, node in graph_manager.file_nodes.items():
        file_nodes_data[file_path] = {
            'path': node.path,
            'status': node.status.value,
            'change_type': node.change_type.value,
            'summary': node.summary,
            'error': node.error,
            'components': [
                {
                    'name': c.name if hasattr(c, 'name') else str(c),
                    'change_type': c.change_type if hasattr(c, 'change_type') else 'unknown',
                    'summary': c.summary if hasattr(c, 'summary') else None
                } if hasattr(c, '__dict__') else str(c)
                for c in (node.components or [])
            ]
        }
    
    # Convert component nodes to serializable format
    component_nodes_data = {}
    for component_id, node in graph_manager.component_nodes.items():
        component_nodes_data[component_id] = {
            'name': node.name,
            'file_path': node.file_path,
            'change_type': node.change_type.value,
            'component_type': node.component_type,
            'parent': node.parent,
            'summary': node.summary,
            'dependencies': node.dependencies,
            'dependents': node.dependents
        }
    
    # Convert graphs to node-link format
    file_graph_data = json_graph.node_link_data(graph_manager.file_graph, edges="links")
    component_graph_data = json_graph.node_link_data(graph_manager.component_graph, edges="links")
    
    # Combine all data
    data = {
        'version': '1.0',
        'file_nodes': file_nodes_data,
        'component_nodes': component_nodes_data,
        'file_graph': file_graph_data,
        'component_graph': component_graph_data,
        'processed_files': list(graph_manager.processed_files)
    }
    
    return data


def load_graph_from_json(json_path: str) -> GraphManager:
    """
    Load graph data from a JSON file.
    
    Args:
        json_path: Path to the JSON file
        
    Returns:
        GraphManager instance with loaded data
    """
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    return _reconstruct_graph_manager(data)


def load_graph_from_pickle(pickle_path: str) -> GraphManager:
    """
    Load graph data from a pickle file.
    
    Args:
        pickle_path: Path to the pickle file
        
    Returns:
        GraphManager instance with loaded data
    """
    with open(pickle_path, 'rb') as f:
        data = pickle.load(f)
    
    return _reconstruct_graph_manager(data)


def _reconstruct_graph_manager(data: Dict[str, Any]) -> GraphManager:
    """
    Reconstruct a GraphManager instance from serialized data.
    
    Args:
        data: Dictionary containing serialized graph data
        
    Returns:
        GraphManager instance with reconstructed data
    """
    graph_manager = GraphManager()
    
    # Reconstruct file nodes
    for file_path, node_data in data['file_nodes'].items():
        file_node = FileNode(
            path=node_data['path'],
            status=FileStatus(node_data['status']),
            change_type=ChangeType(node_data['change_type']),
            summary=node_data.get('summary'),
            error=node_data.get('error'),
            components=node_data.get('components', [])
        )
        graph_manager.file_nodes[file_path] = file_node
    
    # Reconstruct component nodes
    for component_id, node_data in data['component_nodes'].items():
        component_node = ComponentNode(
            name=node_data['name'],
            file_path=node_data['file_path'],
            change_type=ChangeType(node_data['change_type']),
            component_type=node_data['component_type'],
            parent=node_data.get('parent'),
            summary=node_data.get('summary'),
            dependencies=node_data.get('dependencies', []),
            dependents=node_data.get('dependents', [])
        )
        graph_manager.component_nodes[component_id] = component_node
    
    # Reconstruct graphs
    graph_manager.file_graph = json_graph.node_link_graph(data['file_graph'], directed=True, edges="links")
    graph_manager.component_graph = json_graph.node_link_graph(data['component_graph'], directed=True, edges="links")
    
    # Reconstruct processed files set
    graph_manager.processed_files = set(data.get('processed_files', []))
    
    return graph_manager


def export_graph(graph_manager: GraphManager, output_path: str, format: str = 'json') -> str:
    """
    Export graph data in the specified format.
    
    Args:
        graph_manager: GraphManager instance containing the graphs
        output_path: Path where the file should be saved
        format: Export format ('json', 'pickle', or 'graphml')
        
    Returns:
        Path to the generated file
        
    Raises:
        ValueError: If format is not supported
    """
    format = format.lower()
    
    if format == 'json':
        return export_graph_to_json(graph_manager, output_path)
    elif format == 'pickle':
        return export_graph_to_pickle(graph_manager, output_path)
    elif format == 'graphml':
        return export_graph_to_graphml(graph_manager, output_path)
    else:
        raise ValueError(f"Unsupported format: {format}. Supported formats: json, pickle, graphml")
