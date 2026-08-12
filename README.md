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
- `--format`: Select `html` (default), `terminal`, or canonical `json` output.
- `--output` or `-o`: Specify the HTML or JSON output path. HTML defaults to
  `diffgraph.html`; JSON defaults to stdout. Terminal output is always stdout.
- `--no-open`: Don't automatically open the HTML report in browser
- `--structural-json`: Write a local Python structural DiffGraph v2 artifact to the given path (`-` for stdout). Applies to `wild diff` only.
- `--version`: Show version information

Example:
```bash
wild --output my-report.html --no-open
```

### Canonical local output (experimental)

A deterministic, network-free Python baseline can be written as a validated
DiffGraph v2 artifact without changing the existing AI/HTML default:

```bash
wild diff --format json
wild diff --format json --output diffgraph.json
wild diff --format terminal
# Compatibility spelling retained for existing scripts:
wild --structural-json diffgraph.json diff
wild --structural-json staged.json diff --staged -- src/
wild --structural-json - diff -- path/to/file.py
```

`--structural-json PATH` remains a compatibility alias for canonical JSON with
that destination. Do not combine it with `--format` or `--output`; ambiguous
combinations are usage errors. Likewise, `--format terminal` cannot use
`--output`. Terminal-only `--compact` and `--all` flags follow `diff`.

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

#### CLI and offline contract

- Each canonical invocation resolves the requested Git snapshot once, builds
  one artifact, validates it against the packaged schema, and passes that same
  validated object to the JSON or terminal consumer. Consumers never re-read
  repository files or rebuild the artifact.
- JSON sent to stdout contains only the artifact. Terminal output also uses
  stdout. A successful JSON file write reports its path on stderr; diagnostics,
  usage help, and errors use stderr. Explicit JSON paths are replaced atomically
  and parent directories are not created implicitly.
- Exit code `0` means success, including a snapshot with no changes. Empty JSON
  has empty `files`, `symbols`, and `relationships` arrays; terminal output says
  that the selected snapshot has no changes. Runtime, validation, output, and
  cancellation failures return `1`; option/command usage errors return `2`.
  Ctrl-C prints Click's `Aborted!` diagnostic and does not dispatch an artifact
  or print a success message.
- Canonical JSON and terminal modes are local/offline. They import or invoke no
  AI or network module, make no network calls, report `privacy_tier: local` and
  `llm_calls: 0`, and use only local Git/object/worktree data plus packaged
  parser/schema resources.

The default `html` mode is intentionally outside this canonical dispatch in
this increment. Its existing AI analysis, progress output, report destination
(`diffgraph.html` by default), and browser-opening behavior remain unchanged;
HTML migration will happen separately rather than mixing legacy and canonical
artifact construction here.

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
