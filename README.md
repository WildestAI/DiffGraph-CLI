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
diffgraph-ai
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
- `--version`: Show version information

Example:
```bash
diffgraph-ai --output my-report.html --no-open
```

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
