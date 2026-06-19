# skill: wild-diff

Use this skill to analyse git diffs with WildestAI's `wild` CLI and get semantic understanding of code changes.

## What it does

`wild diff` analyses your current git diff using AI and produces:
- A dependency graph of changed components and their relationships
- An HTML report (`diffgraph.html`) with Mermaid.js visualisation
- Syntax-highlighted code blocks with AI-generated summaries
- Answers to: what changed, how components relate, what needs attention

## Prerequisites

```bash
# Install
pip install wildest-ai
# or from source:
git clone https://github.com/WildestAI/DiffGraph-CLI && cd DiffGraph-CLI && pip install -e .

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

# Write output to a custom file, don't auto-open
wild diff --output report.html --no-open

# All other git commands pass through transparently
wild log
wild blame path/to/file.py
wild status
```

## Output

By default, generates `diffgraph.html` in the current directory and opens it in your browser.

Use `--no-open` to suppress auto-open (useful in CI or headless environments).
Use `--output <path>` to write to a specific location.

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
