# DiffGraph-CLI

DiffGraph-CLI is a powerful command-line tool that visualizes code changes using AI. It reads your current git diffs and untracked files, uses AI to understand the implications of your changes, and generates a beautiful, shareable HTML report with a dependency graph.

## 🌟 Features

- 📊 Visualizes code changes as a dependency graph
- 🤖 AI-powered analysis of code changes
- 💾 Export graph data in multiple formats (JSON, Pickle, GraphML)
- 🌙 Dark mode support
- 📝 Markdown-formatted summaries
- 🔍 Syntax highlighting for code blocks
- 📱 Responsive design
- 🔄 Works with both tracked and untracked files

## 🚀 Installation

1. Clone the repository:
```bash
git clone https://github.com/yourusername/DiffGraph-CLI.git
cd DiffGraph-CLI
```

2. Create a virtual environment and activate it:
```bash
python -m venv venv
source venv/bin/activate  # On Windows, use: venv\Scripts\activate
```

3. Install the package:
```bash
pip install -e .
```

4. Set up your OpenAI API key:
```bash
# Create a .env file in the project root
cp .env.example .env  # On Windows, use: type nul > .env
```
Add your OpenAI API key to the .env file

> Note: The `.env` file is git-ignored for security reasons. Make sure to keep your API key secure and never commit it to version control.

## 💻 Usage

Basic usage:
```bash
wild
```

This will:
1. Read your current git changes
2. Analyze them using AI
3. Generate an HTML report (`diffgraph.html`)
4. Open the report in your default browser

### Command-line Options

- `--api-key`: Specify your OpenAI API key (defaults to OPENAI_API_KEY environment variable)
- `--output` or `-o`: Specify the output file path (default: diffgraph.html for HTML, diffgraph.json for graph)
- `--format` or `-f`: Output format: `html` (default) or `graph`
- `--graph-format`: Graph serialization format when using `--format graph`: `json` (default), `pickle`, or `graphml`
- `--no-open`: Don't automatically open the HTML report in browser
- `--version`: Show version information

Examples:
```bash
# Generate HTML report (default)
wild --output my-report.html --no-open

# Export graph data as JSON
wild --format graph --output graph-data.json

# Export graph data as pickle
wild --format graph --graph-format pickle --output graph-data.pkl

# Export graph data as GraphML
wild --format graph --graph-format graphml --output graph-data.graphml
```

## 📊 Output Formats

### HTML Report (default)
The generated HTML report includes:
- A summary of code changes
- A Mermaid.js dependency graph
- Syntax-highlighted code blocks
- Dark mode support
- Responsive design for all screen sizes

### Graph Data Export
When using `--format graph`, the tool exports the complete networkx graph data structure, allowing other programs to programmatically analyze the code changes:

**Supported formats:**
- **JSON** (default): Human-readable, widely compatible format
- **Pickle**: Python-specific format that preserves exact data structures
- **GraphML**: Standard graph format compatible with many graph analysis tools

**Exported data includes:**
- File-level dependency graph with metadata (status, change type, summary)
- Component-level dependency graph (functions, classes, methods)
- Complete analysis results for each file and component
- Relationships between components (dependencies and dependents)

**Example: Loading and using exported graph data**
```python
from diffgraph.graph_export import load_graph_from_json
import networkx as nx

# Load the exported graph data
graph_manager = load_graph_from_json('diffgraph.json')

# Access file nodes
for file_path, file_node in graph_manager.file_nodes.items():
    print(f"File: {file_path}")
    print(f"  Status: {file_node.status.value}")
    print(f"  Change Type: {file_node.change_type.value}")
    print(f"  Summary: {file_node.summary}")

# Access component nodes
for component_id, component_node in graph_manager.component_nodes.items():
    print(f"Component: {component_node.name}")
    print(f"  Type: {component_node.component_type}")
    print(f"  Dependencies: {component_node.dependencies}")

# Use networkx to analyze the graphs
print(f"Total files: {graph_manager.file_graph.number_of_nodes()}")
print(f"Total components: {graph_manager.component_graph.number_of_nodes()}")
print(f"Component dependencies: {graph_manager.component_graph.number_of_edges()}")
```

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## 📝 License

This project is licensed under the GNU General Public License v3.0 - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- [Mermaid.js](https://mermaid.js.org/) for graph visualization
- [Highlight.js](https://highlightjs.org/) for syntax highlighting
- [Tailwind CSS](https://tailwindcss.com/) for styling
- [OpenAI](https://openai.com/) for AI capabilities
