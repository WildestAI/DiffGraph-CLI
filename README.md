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
- `--structural-json`: Write a local Python structural DiffGraph v2 artifact to the given path (`-` for stdout). Applies to `wild diff` only.
- `--version`: Show version information

Example:
```bash
wild --output my-report.html --no-open
```

### Local structural JSON (experimental)

A deterministic, network-free Python baseline can be written as a validated
DiffGraph v2 artifact without changing the existing AI/HTML default:

```bash
wild --structural-json diffgraph.json diff
wild --structural-json staged.json diff --staged -- src/
wild --structural-json - diff -- path/to/file.py
```

This increment intentionally supports only local unstaged (`index` → working
tree) and staged (`HEAD` → index) snapshots. Put pathspecs after `--`.
Pathspecs are interpreted relative to the directory where `wild` is invoked,
matching Git's command-line behavior. Commit ranges are rejected rather than
analyzed with guessed semantics.

Python (`.py`) is the only language with structural symbol/import extraction in
this baseline. Other changed files remain in `files[]` and receive a scoped
`UNSUPPORTED_LANGUAGE` warning. Syntax/decoding failures receive a scoped
`PARSE_FAILURE` warning and do not produce invented symbol changes. Import
targets are explicitly labeled unresolved/external; no project-wide resolution
is claimed. Every file records old/new paths, modes, Git object IDs, and content
SHA-256 values in structural evidence, while symbol/relationship evidence names
the parser package, query revision, and source blob identity.

### Artifact compatibility

DiffGraph artifacts use a `MAJOR.MINOR` `schema_version`. Consumers reject
malformed versions and unknown major versions. Minor releases within major 2
are additive: a consumer accepts them only when the complete artifact still
validates against its packaged v2 schema. This fail-closed rule lets producers
add optional data without weakening validation for existing consumers. The
canonical schema and a complete local-only example are packaged under
`diffgraph/schema/`; neither contains AI-derived symbols or relationships.

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
