# skill: wild-diff

Use this skill to analyse git diffs with WildestAI's `wild` CLI and get semantic understanding of code changes.

## What it does

`wild diff` deterministically analyses your current Git diff and prints a ranked
review path to stdout. Canonical HTML and JSON reports are available explicitly:
- A dependency graph of changed components and their relationships
- An offline self-contained HTML report (`--format html` or `-o report.html`)
- A schema-v2 JSON artifact for IDEs and CI (`--format json`)
- Optional deprecated AI HTML compatibility (`--format legacy-html`)

## Prerequisites

```bash
# Install
pip install wildest-ai
# or from source:
git clone https://github.com/WildestAI/wild && cd wild && pip install -e .

# Set your OpenAI API key
export OPENAI_API_KEY=sk-...
```

## Commands

```bash
# Analyse unstaged + untracked changes (most common)
wild diff

# Analyse only staged changes
wild diff --staged

# Diff between HEAD and a specific commit
wild diff <commit-hash>

# Diff between two commits
wild diff <commit1> <commit2>

# Diff for a specific file
wild diff path/to/file.py

# Generate an interactive HTML report, don't auto-open
wild diff --format html --output report.html --no-open
# `-o` alone also selects HTML
wild diff -o report.html --no-open

# All other git commands pass through transparently
wild log
wild blame path/to/file.py
wild status
```

## Output

By default, writes the terminal review path to stdout without creating files or
opening a browser. Use `--format html` for the interactive offline report; it
opens automatically unless `--no-open` is passed. `--output <path>` without an
explicit format is an HTML shorthand.

## MCP Server

If you need programmatic access (agent-to-agent), start the MCP server:

```bash
cd path/to/DiffGraph-CLI
python mcp_server.py
```

The MCP server exposes tools:
- `run_wild_diff(repo_path, args, output_file)` — run wild diff and return structured analysis; `output_file` is optional (defaults to `<repo_path>/diffgraph.html`)
- `get_docs(page)` — retrieve a documentation page
- `list_docs()` — list available documentation pages
- `search_docs(query)` — search across docs

## Configuration

Environment variables:
- `OPENAI_API_KEY` — required for AI analysis
- Copy `.env.example` to `.env` to set locally

## Notes

- Works with Python 3.7+
- Tested on macOS and Linux
- The CLI wraps `git` — it must be run inside a git repository
- Large diffs may be slow; consider scoping with file paths or commit ranges
- The `.env` file is git-ignored — never commit API keys
