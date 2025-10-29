# DiffGraph-CLI

DiffGraph-CLI is a powerful command-line tool that visualizes code changes using AI. It reads your current git diffs and untracked files, uses AI to understand the implications of your changes, and generates a beautiful, shareable HTML report with a dependency graph.

## 🌟 Features

- 📊 Visualizes code changes as a dependency graph
- 🤖 AI-powered analysis of code changes
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
- `--output` or `-o`: Specify the output HTML file path (default: diffgraph.html)
- `--no-open`: Don't automatically open the HTML report in browser
- `--mode` or `-m`: Select processing mode for diffgraph generation (default: openai-agents-dependency-graph)
- `--list-modes`: List all available processing modes
- `--version`: Show version information

Examples:
```bash
# Generate report with default mode
wild diff

# Generate report with custom output path
wild diff --output my-report.html --no-open

# List available processing modes
wild diff --list-modes

# Use a specific processing mode
wild diff --mode openai-agents-dependency-graph
```

## 🔧 Processing Modes

DiffGraph supports multiple processing modes for analyzing code changes. Each mode provides a different perspective on your code:

### Available Modes

#### `openai-agents-dependency-graph` (default)
Uses OpenAI Agents SDK to analyze code and generate component-level dependency graphs. This mode:
- Identifies classes, functions, and methods in your changes
- Analyzes dependencies between components
- Generates a visual dependency graph showing how components relate to each other
- Best for understanding architectural changes and component interactions

### Future Modes

The architecture is designed to support additional processing modes:
- **tree-sitter-dependency-graph**: AST-based analysis using Tree-sitter
- **data-flow-analysis**: Focus on data flow and transformations
- **user-context-analysis**: Analyze changes from a user interaction perspective
- **architecture-analysis**: System-level architectural insights

### Adding Custom Processing Modes

Developers can extend DiffGraph by creating custom processing modes. See the `diffgraph/processing_modes/` directory for examples. Each processor must:
1. Inherit from `BaseProcessor`
2. Implement the `analyze_changes()` method
3. Register itself using the `@register_processor` decorator

## 📊 Example Output

The generated HTML report includes:
- A summary of code changes
- A Mermaid.js dependency graph
- Syntax-highlighted code blocks
- Dark mode support
- Responsive design for all screen sizes

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## 📝 License

This project is licensed under the GNU General Public License v3.0 - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- [Mermaid.js](https://mermaid.js.org/) for graph visualization
- [Highlight.js](https://highlightjs.org/) for syntax highlighting
- [Tailwind CSS](https://tailwindcss.com/) for styling
- [OpenAI](https://openai.com/) for AI capabilities
