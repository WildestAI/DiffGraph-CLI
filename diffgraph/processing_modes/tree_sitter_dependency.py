"""
Tree-sitter processor for static AST-based dependency extraction.

This processor uses tree-sitter to parse source files and extract dependencies
through static analysis of the AST, supporting multiple programming languages.
"""

from typing import List, Dict, Optional, Set, Tuple, Callable
import subprocess
import re
import time
from pathlib import Path
from dataclasses import dataclass

try:
    import tree_sitter_language_pack as tslp
    import tree_sitter as ts
    # Alias for convenience
    tslp.ts = ts
except ImportError:
    raise ImportError(
        "tree-sitter-language-pack is required for tree-sitter-dependency-graph mode. "
        "Install it with: pip install tree-sitter-language-pack"
    )

from ..graph_manager import GraphManager, ChangeType, ComponentNode
from .base import BaseProcessor, DiffAnalysis
from .schema_v2_adapter import (
    compute_symbol_diff,
    build_schema_v2_output,
    build_import_relationship,
)
from . import register_processor


@dataclass
class ExtractedComponent:
    """Represents a component extracted from the AST."""
    name: str
    component_type: str  # container, function, method
    parent: Optional[str] = None
    start_line: Optional[int] = None
    end_line: Optional[int] = None
    file_path: Optional[str] = None


@dataclass
class ExtractedDependency:
    """Represents a dependency relationship extracted from the AST."""
    source: str  # Component that has the dependency
    target: str  # Component being depended upon
    relationship_type: str  # imports, calls, inherits


# Language configurations with file extensions
LANGUAGE_CONFIGS = {
    'python': {
        'extensions': ['.py'],
        'ts_language': 'python'
    },
    'typescript': {
        'extensions': ['.ts'],
        'ts_language': 'typescript'
    },
    'tsx': {
        'extensions': ['.tsx'],
        'ts_language': 'tsx'
    },
    'javascript': {
        'extensions': ['.js', '.jsx', '.mjs'],
        'ts_language': 'javascript'
    },
    'go': {
        'extensions': ['.go'],
        'ts_language': 'go'
    },
    'rust': {
        'extensions': ['.rs'],
        'ts_language': 'rust'
    },
    'java': {
        'extensions': ['.java'],
        'ts_language': 'java'
    },
    'swift': {
        'extensions': ['.swift'],
        'ts_language': 'swift'
    }
}


def get_language_from_file(file_path: str) -> Optional[str]:
    """Determine the programming language from file extension."""
    ext = Path(file_path).suffix.lower()
    for lang, config in LANGUAGE_CONFIGS.items():
        if ext in config['extensions']:
            return lang
    return None


@register_processor("tree-sitter-dependency-graph")
class TreeSitterProcessor(BaseProcessor):
    """
    Processor using tree-sitter for static AST-based dependency extraction.
    
    This processor parses source files using tree-sitter and extracts:
    - Imports and module dependencies
    - Function and method calls (including deep call chains)
    - Class inheritance relationships
    
    Supports: Python, TypeScript, JavaScript, Go, Rust, Java, Swift
    """

    def __init__(self, **kwargs):
        """Initialize the tree-sitter processor."""
        super().__init__(**kwargs)
        self.graph_manager = GraphManager()
        self.parsers = {}
        self.current_file_components = {}  # Track components per file
        
    @property
    def name(self) -> str:
        """Return the name of this processing mode."""
        return "tree-sitter-dependency-graph"
    
    @property
    def description(self) -> str:
        """Return a description of this processing mode."""
        return ("Static AST-based dependency extraction using tree-sitter. "
                "Supports Python, TypeScript, JavaScript, Go, Rust, Java, Swift. "
                "Extracts imports, function calls, and inheritance relationships.")
    
    def _get_parser(self, language: str):
        """Get or create a parser for the given language."""
        if language not in self.parsers:
            try:
                ts_lang = LANGUAGE_CONFIGS[language]['ts_language']
                parser = tslp.get_parser(ts_lang)
                self.parsers[language] = parser
            except Exception as e:
                raise ValueError(f"Failed to initialize parser for {language}: {e}")
        return self.parsers[language]
    
    def _get_full_file_content(self, file_path: str) -> Optional[str]:
        """Get the full content of a file using git show."""
        try:
            result = subprocess.run(
                ["git", "show", f"HEAD:{file_path}"],
                capture_output=True,
                text=True,
                check=True
            )
            return result.stdout
        except subprocess.CalledProcessError:
            # File might be new/untracked, try reading from filesystem
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    return f.read()
            except Exception:
                return None
    
    def _extract_components_python(self, tree, source_bytes: bytes, file_path: str) -> List[ExtractedComponent]:
        """Extract components (classes, functions, methods) from Python AST."""
        components = []
        root = tree.root_node
        
        # Query for classes
        class_query = """
        (class_definition
          name: (identifier) @class_name) @class_def
        """
        
        # Query for functions
        function_query = """
        (function_definition
          name: (identifier) @func_name) @func_def
        """
        
        language = tslp.get_language(LANGUAGE_CONFIGS['python']['ts_language'])
        
        # Extract classes
        try:
            query = tslp.ts.Query(language, class_query)
            cursor = tslp.ts.QueryCursor(query)
            captures_dict = cursor.captures(root)
            
            class_nodes = captures_dict.get("class_def", [])
            class_name_nodes = captures_dict.get("class_name", [])
            
            for class_node, class_name_node in zip(class_nodes, class_name_nodes):
                class_name = source_bytes[class_name_node.start_byte:class_name_node.end_byte].decode('utf-8')
                components.append(ExtractedComponent(
                    name=class_name,
                    component_type="container",
                    start_line=class_node.start_point[0],
                    end_line=class_node.end_point[0],
                    file_path=file_path
                ))
                
                # Extract methods within this class
                for child in class_node.children:
                    if child.type == "block":
                        for stmt in child.children:
                            if stmt.type == "function_definition":
                                method_name_node = None
                                for method_child in stmt.children:
                                    if method_child.type == "identifier":
                                        method_name_node = method_child
                                        break
                                
                                if method_name_node:
                                    method_name = source_bytes[method_name_node.start_byte:method_name_node.end_byte].decode('utf-8')
                                    components.append(ExtractedComponent(
                                        name=method_name,
                                        component_type="method",
                                        parent=class_name,
                                        start_line=stmt.start_point[0],
                                        end_line=stmt.end_point[0],
                                        file_path=file_path
                                    ))
        except Exception as e:
            print(f"Warning: Error extracting classes: {e}")
        
        # Extract standalone functions
        try:
            query = tslp.ts.Query(language, function_query)
            cursor = tslp.ts.QueryCursor(query)
            captures_dict = cursor.captures(root)
            
            func_nodes = captures_dict.get("func_def", [])
            
            for func_node in func_nodes:
                # Check if this function is not inside a class
                parent = func_node.parent
                is_method = False
                while parent:
                    if parent.type == "class_definition":
                        is_method = True
                        break
                    parent = parent.parent
                
                if not is_method:
                    func_name_node = None
                    for child in func_node.children:
                        if child.type == "identifier":
                            func_name_node = child
                            break
                    
                    if func_name_node:
                        func_name = source_bytes[func_name_node.start_byte:func_name_node.end_byte].decode('utf-8')
                        components.append(ExtractedComponent(
                            name=func_name,
                            component_type="function",
                            start_line=func_node.start_point[0],
                            end_line=func_node.end_point[0],
                            file_path=file_path
                        ))
        except Exception as e:
            print(f"Warning: Error extracting functions: {e}")
        
        return components
    
    def _extract_components_typescript(self, tree, source_bytes: bytes, file_path: str) -> List[ExtractedComponent]:
        """Extract components from TypeScript/JavaScript AST."""
        components = []
        root = tree.root_node
        
        language = tslp.get_language(LANGUAGE_CONFIGS['typescript']['ts_language'])
        
        # Query for classes
        class_query = """
        (class_declaration
          name: (type_identifier) @class_name) @class_def
        """
        
        # Query for functions
        function_query = """
        [
          (function_declaration
            name: (identifier) @func_name) @func_def
          (arrow_function) @arrow_func
        ]
        """
        
        # Extract classes
        try:
            query = language.query(class_query)
            captures = query.captures(root)
            
            for node, capture_name in captures:
                if capture_name == "class_name":
                    class_name = source_bytes[node.start_byte:node.end_byte].decode('utf-8')
                    class_node = node.parent
                    
                    components.append(ExtractedComponent(
                        name=class_name,
                        component_type="container",
                        start_line=class_node.start_point[0],
                        end_line=class_node.end_point[0],
                        file_path=file_path
                    ))
                    
                    # Extract methods
                    for child in class_node.children:
                        if child.type == "class_body":
                            for member in child.children:
                                if member.type in ["method_definition", "public_field_definition"]:
                                    name_node = None
                                    for m_child in member.children:
                                        if m_child.type == "property_identifier":
                                            name_node = m_child
                                            break
                                    
                                    if name_node:
                                        method_name = source_bytes[name_node.start_byte:name_node.end_byte].decode('utf-8')
                                        components.append(ExtractedComponent(
                                            name=method_name,
                                            component_type="method",
                                            parent=class_name,
                                            start_line=member.start_point[0],
                                            end_line=member.end_point[0],
                                            file_path=file_path
                                        ))
        except Exception as e:
            print(f"Warning: Error extracting TypeScript classes: {e}")
        
        # Extract functions
        try:
            query = language.query(function_query)
            captures = query.captures(root)
            
            for node, capture_name in captures:
                if capture_name == "func_name":
                    func_name = source_bytes[node.start_byte:node.end_byte].decode('utf-8')
                    func_node = node.parent
                    
                    # Check if inside a class
                    parent = func_node.parent
                    is_method = False
                    while parent:
                        if parent.type == "class_declaration":
                            is_method = True
                            break
                        parent = parent.parent
                    
                    if not is_method:
                        components.append(ExtractedComponent(
                            name=func_name,
                            component_type="function",
                            start_line=func_node.start_point[0],
                            end_line=func_node.end_point[0],
                            file_path=file_path
                        ))
        except Exception as e:
            print(f"Warning: Error extracting TypeScript functions: {e}")
        
        return components
    
    def _extract_components_go(self, tree, source_bytes: bytes, file_path: str) -> List[ExtractedComponent]:
        """Extract components from Go AST."""
        components = []
        root = tree.root_node
        
        language = tslp.get_language(LANGUAGE_CONFIGS['go']['ts_language'])
        
        # Query for type declarations (structs/interfaces)
        type_query = """
        (type_declaration
          (type_spec
            name: (type_identifier) @type_name)) @type_def
        """
        
        # Query for functions
        function_query = """
        (function_declaration
          name: (identifier) @func_name) @func_def
        """
        
        # Query for methods
        method_query = """
        (method_declaration
          receiver: (parameter_list
            (parameter_declaration
              type: [(type_identifier) (pointer_type)] @receiver_type))
          name: (field_identifier) @method_name) @method_def
        """
        
        # Extract types (structs/interfaces)
        try:
            query = language.query(type_query)
            captures = query.captures(root)
            
            for node, capture_name in captures:
                if capture_name == "type_name":
                    type_name = source_bytes[node.start_byte:node.end_byte].decode('utf-8')
                    type_node = node.parent.parent
                    
                    components.append(ExtractedComponent(
                        name=type_name,
                        component_type="container",
                        start_line=type_node.start_point[0],
                        end_line=type_node.end_point[0],
                        file_path=file_path
                    ))
        except Exception as e:
            print(f"Warning: Error extracting Go types: {e}")
        
        # Extract functions
        try:
            query = language.query(function_query)
            captures = query.captures(root)
            
            for node, capture_name in captures:
                if capture_name == "func_name":
                    func_name = source_bytes[node.start_byte:node.end_byte].decode('utf-8')
                    func_node = node.parent
                    
                    components.append(ExtractedComponent(
                        name=func_name,
                        component_type="function",
                        start_line=func_node.start_point[0],
                        end_line=func_node.end_point[0],
                        file_path=file_path
                    ))
        except Exception as e:
            print(f"Warning: Error extracting Go functions: {e}")
        
        # Extract methods
        try:
            query = language.query(method_query)
            captures = query.captures(root)
            
            receiver_map = {}
            method_names = {}
            
            for node, capture_name in captures:
                if capture_name == "receiver_type":
                    method_node = node.parent.parent.parent
                    receiver_type = source_bytes[node.start_byte:node.end_byte].decode('utf-8')
                    # Remove pointer prefix if present
                    receiver_type = receiver_type.lstrip('*')
                    receiver_map[id(method_node)] = receiver_type
                elif capture_name == "method_name":
                    method_node = node.parent
                    method_names[id(method_node)] = source_bytes[node.start_byte:node.end_byte].decode('utf-8')
            
            for method_id, method_name in method_names.items():
                if method_id in receiver_map:
                    receiver_type = receiver_map[method_id]
                    # Find the method node
                    for node, capture_name in captures:
                        if capture_name == "method_def" and id(node) == method_id:
                            components.append(ExtractedComponent(
                                name=method_name,
                                component_type="method",
                                parent=receiver_type,
                                start_line=node.start_point[0],
                                end_line=node.end_point[0],
                                file_path=file_path
                            ))
                            break
        except Exception as e:
            print(f"Warning: Error extracting Go methods: {e}")
        
        return components
    
    def _extract_components_rust(self, tree, source_bytes: bytes, file_path: str) -> List[ExtractedComponent]:
        """Extract components from Rust AST."""
        components = []
        root = tree.root_node
        
        language = tslp.get_language(LANGUAGE_CONFIGS['rust']['ts_language'])
        
        # Query for structs/enums/traits
        type_query = """
        [
          (struct_item
            name: (type_identifier) @type_name) @struct_def
          (enum_item
            name: (type_identifier) @type_name) @enum_def
          (trait_item
            name: (type_identifier) @type_name) @trait_def
        ]
        """
        
        # Query for functions
        function_query = """
        (function_item
          name: (identifier) @func_name) @func_def
        """
        
        # Query for impl blocks
        impl_query = """
        (impl_item
          type: (type_identifier) @impl_type) @impl_block
        """
        
        # Extract types
        try:
            query = language.query(type_query)
            captures = query.captures(root)
            
            for node, capture_name in captures:
                if capture_name == "type_name":
                    type_name = source_bytes[node.start_byte:node.end_byte].decode('utf-8')
                    type_node = node.parent
                    
                    components.append(ExtractedComponent(
                        name=type_name,
                        component_type="container",
                        start_line=type_node.start_point[0],
                        end_line=type_node.end_point[0],
                        file_path=file_path
                    ))
        except Exception as e:
            print(f"Warning: Error extracting Rust types: {e}")
        
        # Extract standalone functions
        try:
            query = language.query(function_query)
            captures = query.captures(root)
            
            for node, capture_name in captures:
                if capture_name == "func_name":
                    func_name = source_bytes[node.start_byte:node.end_byte].decode('utf-8')
                    func_node = node.parent
                    
                    # Check if inside impl block
                    parent = func_node.parent
                    is_method = False
                    impl_type = None
                    while parent:
                        if parent.type == "impl_item":
                            is_method = True
                            # Find the type this impl is for
                            for child in parent.children:
                                if child.type == "type_identifier":
                                    impl_type = source_bytes[child.start_byte:child.end_byte].decode('utf-8')
                                    break
                            break
                        parent = parent.parent
                    
                    if is_method and impl_type:
                        components.append(ExtractedComponent(
                            name=func_name,
                            component_type="method",
                            parent=impl_type,
                            start_line=func_node.start_point[0],
                            end_line=func_node.end_point[0],
                            file_path=file_path
                        ))
                    elif not is_method:
                        components.append(ExtractedComponent(
                            name=func_name,
                            component_type="function",
                            start_line=func_node.start_point[0],
                            end_line=func_node.end_point[0],
                            file_path=file_path
                        ))
        except Exception as e:
            print(f"Warning: Error extracting Rust functions: {e}")
        
        return components
    
    def _extract_components_java(self, tree, source_bytes: bytes, file_path: str) -> List[ExtractedComponent]:
        """Extract components from Java AST."""
        components = []
        root = tree.root_node
        
        language = tslp.get_language(LANGUAGE_CONFIGS['java']['ts_language'])
        
        # Query for classes/interfaces
        class_query = """
        [
          (class_declaration
            name: (identifier) @class_name) @class_def
          (interface_declaration
            name: (identifier) @interface_name) @interface_def
        ]
        """
        
        # Query for methods
        method_query = """
        (method_declaration
          name: (identifier) @method_name) @method_def
        """
        
        # Extract classes/interfaces
        try:
            query = language.query(class_query)
            captures = query.captures(root)
            
            for node, capture_name in captures:
                if capture_name in ["class_name", "interface_name"]:
                    class_name = source_bytes[node.start_byte:node.end_byte].decode('utf-8')
                    class_node = node.parent
                    
                    components.append(ExtractedComponent(
                        name=class_name,
                        component_type="container",
                        start_line=class_node.start_point[0],
                        end_line=class_node.end_point[0],
                        file_path=file_path
                    ))
                    
                    # Extract methods within this class
                    for child in class_node.children:
                        if child.type == "class_body":
                            for member in child.children:
                                if member.type == "method_declaration":
                                    method_name_node = None
                                    for m_child in member.children:
                                        if m_child.type == "identifier":
                                            method_name_node = m_child
                                            break
                                    
                                    if method_name_node:
                                        method_name = source_bytes[method_name_node.start_byte:method_name_node.end_byte].decode('utf-8')
                                        components.append(ExtractedComponent(
                                            name=method_name,
                                            component_type="method",
                                            parent=class_name,
                                            start_line=member.start_point[0],
                                            end_line=member.end_point[0],
                                            file_path=file_path
                                        ))
        except Exception as e:
            print(f"Warning: Error extracting Java classes: {e}")
        
        return components
    
    def _extract_components_swift(self, tree, source_bytes: bytes, file_path: str) -> List[ExtractedComponent]:
        """Extract components from Swift AST."""
        components = []
        root = tree.root_node
        
        language = tslp.get_language(LANGUAGE_CONFIGS['swift']['ts_language'])
        
        # Query for classes/structs/protocols
        type_query = """
        [
          (class_declaration
            name: (type_identifier) @class_name) @class_def
          (struct_declaration
            name: (type_identifier) @struct_name) @struct_def
          (protocol_declaration
            name: (type_identifier) @protocol_name) @protocol_def
        ]
        """
        
        # Query for functions
        function_query = """
        (function_declaration
          name: (simple_identifier) @func_name) @func_def
        """
        
        # Extract types
        try:
            query = language.query(type_query)
            captures = query.captures(root)
            
            for node, capture_name in captures:
                if capture_name in ["class_name", "struct_name", "protocol_name"]:
                    type_name = source_bytes[node.start_byte:node.end_byte].decode('utf-8')
                    type_node = node.parent
                    
                    components.append(ExtractedComponent(
                        name=type_name,
                        component_type="container",
                        start_line=type_node.start_point[0],
                        end_line=type_node.end_point[0],
                        file_path=file_path
                    ))
                    
                    # Extract methods
                    for child in type_node.children:
                        if child.type == "class_body":
                            for member in child.children:
                                if member.type == "function_declaration":
                                    method_name_node = None
                                    for m_child in member.children:
                                        if m_child.type == "simple_identifier":
                                            method_name_node = m_child
                                            break
                                    
                                    if method_name_node:
                                        method_name = source_bytes[method_name_node.start_byte:method_name_node.end_byte].decode('utf-8')
                                        components.append(ExtractedComponent(
                                            name=method_name,
                                            component_type="method",
                                            parent=type_name,
                                            start_line=member.start_point[0],
                                            end_line=member.end_point[0],
                                            file_path=file_path
                                        ))
        except Exception as e:
            print(f"Warning: Error extracting Swift types: {e}")
        
        # Extract standalone functions
        try:
            query = language.query(function_query)
            captures = query.captures(root)
            
            for node, capture_name in captures:
                if capture_name == "func_name":
                    func_name = source_bytes[node.start_byte:node.end_byte].decode('utf-8')
                    func_node = node.parent
                    
                    # Check if inside a type
                    parent = func_node.parent
                    is_method = False
                    while parent:
                        if parent.type in ["class_declaration", "struct_declaration", "protocol_declaration"]:
                            is_method = True
                            break
                        parent = parent.parent
                    
                    if not is_method:
                        components.append(ExtractedComponent(
                            name=func_name,
                            component_type="function",
                            start_line=func_node.start_point[0],
                            end_line=func_node.end_point[0],
                            file_path=file_path
                        ))
        except Exception as e:
            print(f"Warning: Error extracting Swift functions: {e}")
        
        return components
    
    def _extract_components(self, language: str, tree, source_bytes: bytes, file_path: str) -> List[ExtractedComponent]:
        """Extract components based on language."""
        if language == 'python':
            return self._extract_components_python(tree, source_bytes, file_path)
        elif language in ['typescript', 'javascript']:
            return self._extract_components_typescript(tree, source_bytes, file_path)
        elif language == 'go':
            return self._extract_components_go(tree, source_bytes, file_path)
        elif language == 'rust':
            return self._extract_components_rust(tree, source_bytes, file_path)
        elif language == 'java':
            return self._extract_components_java(tree, source_bytes, file_path)
        elif language == 'swift':
            return self._extract_components_swift(tree, source_bytes, file_path)
        else:
            return []
    
    def _extract_imports_python(self, tree, source_bytes: bytes) -> List[str]:
        """Extract import statements from Python."""
        imports = []
        root = tree.root_node
        
        language = tslp.get_language(LANGUAGE_CONFIGS['python']['ts_language'])
        
        import_query = """
        [
          (import_statement
            name: (dotted_name) @import_name)
          (import_from_statement
            module_name: (dotted_name) @import_name)
        ]
        """
        
        try:
            query = tslp.ts.Query(language, import_query)
            cursor = tslp.ts.QueryCursor(query)
            captures_dict = cursor.captures(root)
            
            import_nodes = captures_dict.get("import_name", [])
            for node in import_nodes:
                import_name = source_bytes[node.start_byte:node.end_byte].decode('utf-8')
                imports.append(import_name)
        except Exception as e:
            print(f"Warning: Error extracting Python imports: {e}")
        
        return imports
    
    def _extract_function_calls(self, tree, source_bytes: bytes) -> List[str]:
        """Extract function calls from the AST (language-agnostic)."""
        calls = []
        
        def traverse(node):
            if node.type == "call_expression" or node.type == "call":
                # Try to get the function name
                for child in node.children:
                    if child.type in ["identifier", "attribute", "field_expression", "selector_expression"]:
                        call_name = source_bytes[child.start_byte:child.end_byte].decode('utf-8')
                        calls.append(call_name)
                        break
            
            for child in node.children:
                traverse(child)
        
        traverse(tree.root_node)
        return calls
    
    # ------------------------------------------------------------------
    # Pre/post content helpers (Gap 7 from PR-13-REVIEW.md)
    # ------------------------------------------------------------------

    def _get_pre_change_content(self, file_path: str, staged: bool = False) -> Optional[str]:
        """
        Fetch the pre-change version of a file.

        - For unstaged diffs:    ``git show HEAD:<file>``
        - For staged diffs:      ``git show HEAD:<file>``  (same — HEAD is the base)
        - New / untracked files: returns None (no pre-change version exists)
        """
        try:
            result = subprocess.run(
                ["git", "show", f"HEAD:{file_path}"],
                capture_output=True, text=True, check=True,
            )
            return result.stdout
        except subprocess.CalledProcessError:
            return None  # File is new — no pre-change version

    def _get_post_change_content(self, file_path: str, staged: bool = False) -> Optional[str]:
        """
        Fetch the post-change version of a file.

        - For unstaged diffs:    read from the working tree filesystem
        - For staged diffs:      ``git show :0:<file>`` (index / staging area)
        - Deleted files:         returns None
        """
        if staged:
            try:
                result = subprocess.run(
                    ["git", "show", f":0:{file_path}"],
                    capture_output=True, text=True, check=True,
                )
                return result.stdout
            except subprocess.CalledProcessError:
                return None  # Deleted in staging area
        else:
            try:
                with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                    return f.read()
            except OSError:
                return None  # File deleted or unreadable

    # ------------------------------------------------------------------
    # Schema v2 entry point (Gap 1–7 from PR-13-REVIEW.md)
    # ------------------------------------------------------------------

    def analyze_changes_v2(
        self,
        files_with_content: List[Dict[str, str]],
        diff_ref: Optional[Dict] = None,
        wild_version: str = "2.0.0-dev",
        staged: bool = False,
        progress_callback: Optional[Callable] = None,
    ) -> Dict:
        """
        Analyse code changes and return a DiffGraph v2.0-compliant dict.

        Differences from analyze_changes():
        - Compares pre/post AST snapshots to compute ``change_kind`` per symbol.
        - Emits ``symbols[]`` + ``relationships[]`` with ``analysis_source``.
        - No GraphManager, no Mermaid, no LLM — purely structural.
        - ``metadata.privacy_tier`` is always ``"local"``.

        Args:
            files_with_content: Same format as analyze_changes().
            diff_ref:  Optional diff provenance dict. Defaults to
                       {"from": "HEAD", "to": "working_tree", "kind": "unstaged"}.
            wild_version: Semver string for the schema ``wild_version`` field.
            staged:    True when analysing staged changes (``wild diff --staged``).
            progress_callback: Optional (file, total, status) callback.

        Returns:
            A dict that validates against diffgraph-v2.schema.json.
        """
        if diff_ref is None:
            diff_ref = {
                "from": "HEAD",
                "to": "index" if staged else "working_tree",
                "kind": "staged" if staged else "unstaged",
            }

        start_time = time.time()
        total_files = len(files_with_content)

        all_symbol_changes = []
        all_import_relationships = []
        file_change_list = []
        languages_seen: set = set()

        for idx, file_data in enumerate(files_with_content):
            file_path = file_data["path"]
            status = file_data.get("status", "modified")

            if progress_callback:
                progress_callback(file_path, total_files, "processing")

            # Map status → schema v2 change_kind for the file entry
            file_change_kind_map = {
                "untracked": "added",
                "added": "added",
                "deleted": "deleted",
                "renamed": "renamed",
                "modified": "modified",
            }
            file_change_kind = file_change_kind_map.get(status, "modified")
            file_change_list.append({"path": file_path, "change_kind": file_change_kind})

            # Determine language — skip unsupported files
            language = get_language_from_file(file_path)
            if not language:
                if progress_callback:
                    progress_callback(file_path, total_files, "skipped")
                continue
            languages_seen.add(language)

            # Fetch pre/post content
            is_new = status in ("untracked", "added")
            is_deleted = status == "deleted"

            pre_content: Optional[str] = None if is_new else self._get_pre_change_content(file_path, staged)
            post_content: Optional[str] = None if is_deleted else self._get_post_change_content(file_path, staged)

            # Parse pre snapshot
            pre_components = []
            if pre_content:
                try:
                    parser = self._get_parser(language)
                    pre_tree = parser.parse(pre_content.encode("utf-8"))
                    pre_components = self._extract_components(
                        language, pre_tree, pre_content.encode("utf-8"), file_path
                    )
                except Exception as e:
                    pass  # Treat parse failure as empty pre-snapshot

            # Parse post snapshot
            post_components = []
            post_imports: List[str] = []
            if post_content:
                try:
                    parser = self._get_parser(language)
                    post_tree = parser.parse(post_content.encode("utf-8"))
                    post_source_bytes = post_content.encode("utf-8")
                    post_components = self._extract_components(
                        language, post_tree, post_source_bytes, file_path
                    )
                    # Extract imports from post-change version only
                    if language == "python":
                        post_imports = self._extract_imports_python(
                            post_tree, post_source_bytes
                        )
                except Exception as e:
                    pass  # Treat parse failure as empty post-snapshot

            # Compute symbol-level diff
            symbol_changes = compute_symbol_diff(
                pre_components=pre_components,
                post_components=post_components,
                pre_content=pre_content,
                post_content=post_content,
            )
            all_symbol_changes.extend(symbol_changes)

            # Build import relationships (structural, from post-change)
            for imported_module in post_imports:
                all_import_relationships.append(
                    build_import_relationship(
                        source_file=file_path,
                        imported_module=imported_module,
                    )
                )

            if progress_callback:
                progress_callback(file_path, total_files, "completed")

        duration_ms = int((time.time() - start_time) * 1000)

        return build_schema_v2_output(
            symbol_changes=all_symbol_changes,
            import_relationships=all_import_relationships,
            file_changes=file_change_list,
            diff_ref=diff_ref,
            wild_version=wild_version,
            analysis_duration_ms=duration_ms,
            languages_detected=sorted(languages_seen),
        )

    def analyze_changes(
        self, 
        files_with_content: List[Dict[str, str]], 
        progress_callback: Optional[Callable] = None
    ) -> DiffAnalysis:
        """
        Analyze code changes using tree-sitter AST parsing.
        
        Args:
            files_with_content: List of files with their content/diffs
            progress_callback: Optional callback for progress updates
        
        Returns:
            DiffAnalysis with summary and mermaid diagram
        """
        total_files = len(files_with_content)
        
        # Process each file
        for idx, file_data in enumerate(files_with_content):
            file_path = file_data['path']
            status = file_data['status']
            
            if progress_callback:
                progress_callback(file_path, total_files, "processing")
            
            # Determine language
            language = get_language_from_file(file_path)
            if not language:
                if progress_callback:
                    progress_callback(file_path, total_files, "completed")
                continue
            
            # Determine change type
            if status == 'untracked':
                change_type = ChangeType.ADDED
            elif status == 'deleted':
                change_type = ChangeType.DELETED
            else:
                change_type = ChangeType.MODIFIED
            
            # Add file to graph
            self.graph_manager.add_file(file_path, change_type)
            self.graph_manager.mark_processing(file_path)
            
            # Get full file content
            full_content = self._get_full_file_content(file_path)
            if not full_content:
                self.graph_manager.mark_error(file_path, "Could not read file content")
                if progress_callback:
                    progress_callback(file_path, total_files, "error")
                continue
            
            try:
                # Parse the file
                parser = self._get_parser(language)
                tree = parser.parse(bytes(full_content, 'utf-8'))
                source_bytes = bytes(full_content, 'utf-8')
                
                # Extract components
                components = self._extract_components(language, tree, source_bytes, file_path)
                
                # Add components to graph
                self.current_file_components[file_path] = {}
                for comp in components:
                    comp_id = f"{file_path}::{comp.name}"
                    self.current_file_components[file_path][comp.name] = comp_id
                    
                    self.graph_manager.add_component(
                        name=comp.name,
                        file_path=file_path,
                        change_type=change_type,
                        component_type=comp.component_type,
                        parent=comp.parent,
                        summary=f"{comp.component_type.capitalize()} in {file_path}"
                    )
                
                # Extract imports and create file-level dependencies
                if language == 'python':
                    imports = self._extract_imports_python(tree, source_bytes)
                    # TODO: Link imports to actual files (requires module resolution)
                
                # Extract function calls for component dependencies
                function_calls = self._extract_function_calls(tree, source_bytes)
                
                # Link function calls to components
                for call in function_calls:
                    # Simple name matching - look for components with this name
                    call_parts = call.split('.')
                    call_name = call_parts[-1] if call_parts else call
                    
                    for comp in components:
                        if comp.name == call_name:
                            # Found a match - this could be a dependency
                            target_id = f"{file_path}::{comp.name}"
                            # Add as dependency for all components in this file
                            for source_comp in components:
                                if source_comp.name != comp.name:
                                    source_id = f"{file_path}::{source_comp.name}"
                                    self.graph_manager.add_component_dependency(source_id, target_id)
                
                # Mark file as processed
                component_summaries = [
                    {"name": c.name, "type": c.component_type, "parent": c.parent}
                    for c in components
                ]
                self.graph_manager.mark_processed(file_path, f"Analyzed {len(components)} components", component_summaries)
                
                if progress_callback:
                    progress_callback(file_path, total_files, "completed")
                    
            except Exception as e:
                error_msg = f"Error parsing {file_path}: {str(e)}"
                self.graph_manager.mark_error(file_path, error_msg)
                if progress_callback:
                    progress_callback(file_path, total_files, "error")
        
        # Generate final diagram
        if progress_callback:
            progress_callback(None, total_files, "generating_diagram")
        
        mermaid_diagram = self.graph_manager.get_mermaid_diagram()
        
        # Generate summary
        total_components = len(self.graph_manager.component_nodes)
        total_files_analyzed = len(self.graph_manager.processed_files)
        
        summary = f"""# Code Analysis Summary (Tree-sitter)

## Overview
- **Files Analyzed**: {total_files_analyzed}
- **Components Extracted**: {total_components}
- **Analysis Method**: Static AST parsing with tree-sitter

## Components by Type
"""
        
        # Count components by type
        component_counts = {}
        for comp in self.graph_manager.component_nodes.values():
            comp_type = comp.component_type
            component_counts[comp_type] = component_counts.get(comp_type, 0) + 1
        
        for comp_type, count in component_counts.items():
            summary += f"- **{comp_type.capitalize()}s**: {count}\n"
        
        summary += f"\n## Dependency Graph\n\nThe diagram below shows the relationships between components:\n"
        
        return DiffAnalysis(
            summary=summary,
            mermaid_diagram=mermaid_diagram
        )
