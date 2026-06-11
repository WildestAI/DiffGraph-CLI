#!/usr/bin/env python3
"""
WildestAI MCP Server

Exposes DiffGraph-CLI functionality and documentation to AI agents via the
Model Context Protocol (MCP). Agents can run `wild diff` on a repo and retrieve
docs programmatically.

Usage:
    python mcp_server.py

Requirements:
    pip install mcp
"""

import json
import os
import subprocess
import sys
from pathlib import Path

from mcp.server.fastmcp import FastMCP

# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).parent
DOCS_DIR = REPO_ROOT / "docs"

mcp = FastMCP(
    name="wildestai",
    instructions=(
        "WildestAI helps developers understand code changes. "
        "Use run_wild_diff to analyse a git repository's current diff and get a "
        "semantic understanding of what changed. Use list_docs / get_docs / search_docs "
        "to explore the project's documentation."
    ),
)

# ---------------------------------------------------------------------------
# Tool: run_wild_diff
# ---------------------------------------------------------------------------

@mcp.tool()
def run_wild_diff(
    repo_path: str,
    args: str = "",
    output_file: str = "",
) -> dict:
    """
    Run `wild diff` on a git repository and return the result.

    Args:
        repo_path: Absolute path to the git repository root.
        args: Optional extra arguments, e.g. "--staged", "<commit>", "<file>".
              Pass as a space-separated string.
        output_file: Optional path for the HTML output file. Defaults to
                     <repo_path>/diffgraph.html.

    Returns:
        A dict with keys:
            success (bool): Whether the command succeeded.
            stdout (str): Standard output from wild diff.
            stderr (str): Standard error output.
            output_file (str): Path to the generated HTML report (if any).
            returncode (int): Process exit code.
    """
    repo = Path(repo_path).expanduser().resolve()
    if not repo.is_dir():
        return {"success": False, "error": f"Directory not found: {repo_path}"}

    if not (repo / ".git").exists():
        return {"success": False, "error": f"Not a git repository: {repo_path}"}

    cmd = ["wild", "diff", "--no-open"]
    if output_file:
        cmd += ["--output", output_file]
    if args:
        cmd += args.split()

    try:
        result = subprocess.run(
            cmd,
            cwd=str(repo),
            capture_output=True,
            text=True,
            timeout=120,
        )
        out_path = output_file or str(repo / "diffgraph.html")
        return {
            "success": result.returncode == 0,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "output_file": out_path if Path(out_path).exists() else "",
            "returncode": result.returncode,
        }
    except subprocess.TimeoutExpired:
        return {"success": False, "error": "wild diff timed out after 120 seconds"}
    except FileNotFoundError:
        return {
            "success": False,
            "error": (
                "`wild` command not found. Install with: pip install wildest-ai "
                "or `pip install -e .` from the DiffGraph-CLI repo."
            ),
        }

# ---------------------------------------------------------------------------
# Tool: list_docs
# ---------------------------------------------------------------------------

@mcp.tool()
def list_docs() -> list[dict]:
    """
    List available documentation pages for DiffGraph-CLI / WildestAI.

    Returns:
        A list of dicts, each with keys:
            name (str): Short name / slug of the document.
            title (str): Human-readable title.
            path (str): Relative path from the repo root.
    """
    pages = []

    # Core docs
    built_in = [
        ("readme", "README — Overview & Quick Start", "README.md"),
        ("changelog", "Changelog", "CHANGELOG.md"),
        ("skill", "Agent Skill — how to use wild from an AI agent", "skill.md"),
        ("context", "Project Context — deep reference", "../../wildestai/docs/DiffGraph-CLI/CONTEXT.md"),
        ("vision", "WildestAI Vision — 22-section strategic context", "../../wildestai/docs/DiffGraph-CLI/WildestAI-vision.md"),
    ]
    for name, title, rel_path in built_in:
        full = (REPO_ROOT / rel_path).resolve()
        if full.exists():
            pages.append({"name": name, "title": title, "path": str(full.relative_to(REPO_ROOT.parent.parent) if full.is_relative_to(REPO_ROOT.parent.parent) else full)})

    # docs/ subdirectory
    if DOCS_DIR.exists():
        for f in sorted(DOCS_DIR.glob("**/*.md")):
            slug = f.stem.lower().replace(" ", "-")
            pages.append({
                "name": slug,
                "title": f.stem.replace("-", " ").replace("_", " ").title(),
                "path": str(f.relative_to(REPO_ROOT)),
            })

    return pages


# ---------------------------------------------------------------------------
# Tool: get_docs
# ---------------------------------------------------------------------------

@mcp.tool()
def get_docs(name: str) -> dict:
    """
    Retrieve the content of a documentation page by name or path.

    Args:
        name: The short name from list_docs (e.g. "readme", "context") or a
              relative path from the repo root (e.g. "docs/Roadmap-v1-git-wrapper.md").

    Returns:
        A dict with keys:
            found (bool): Whether the document was located.
            name (str): The name used to look up.
            content (str): Full text of the document (if found).
            error (str): Error message (if not found).
    """
    # Map known slugs to paths
    slug_map = {
        "readme": REPO_ROOT / "README.md",
        "changelog": REPO_ROOT / "CHANGELOG.md",
        "skill": REPO_ROOT / "skill.md",
        "context": REPO_ROOT.parent / "docs" / "DiffGraph-CLI" / "CONTEXT.md",
        "vision": REPO_ROOT.parent / "docs" / "DiffGraph-CLI" / "WildestAI-vision.md",
    }

    target: Path | None = None

    if name in slug_map:
        target = slug_map[name]
    else:
        # Try as relative path from repo root
        candidate = (REPO_ROOT / name).resolve()
        if candidate.exists():
            target = candidate
        else:
            # Try docs subdir
            candidate2 = (DOCS_DIR / name).resolve()
            if candidate2.exists():
                target = candidate2

    if target is None or not target.exists():
        return {
            "found": False,
            "name": name,
            "content": "",
            "error": f"Document '{name}' not found. Call list_docs() to see available pages.",
        }

    try:
        content = target.read_text(encoding="utf-8")
        return {"found": True, "name": name, "content": content, "error": ""}
    except Exception as e:
        return {"found": False, "name": name, "content": "", "error": str(e)}


# ---------------------------------------------------------------------------
# Tool: search_docs
# ---------------------------------------------------------------------------

@mcp.tool()
def search_docs(query: str, max_results: int = 5) -> list[dict]:
    """
    Search across all documentation for a query string (case-insensitive).

    Args:
        query: The search term or phrase.
        max_results: Maximum number of matching excerpts to return (default 5).

    Returns:
        A list of dicts, each with:
            document (str): Document name.
            path (str): Relative path.
            excerpt (str): The matching line + a few lines of context.
            line (int): Line number of the match.
    """
    results = []
    query_lower = query.lower()

    search_paths = [
        (REPO_ROOT / "README.md", "readme"),
        (REPO_ROOT / "CHANGELOG.md", "changelog"),
        (REPO_ROOT / "skill.md", "skill"),
        (REPO_ROOT.parent / "docs" / "DiffGraph-CLI" / "CONTEXT.md", "context"),
    ]

    if DOCS_DIR.exists():
        for f in DOCS_DIR.glob("**/*.md"):
            search_paths.append((f, f.stem.lower()))

    for path, name in search_paths:
        if not path.exists():
            continue
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except Exception:
            continue

        for i, line in enumerate(lines):
            if query_lower in line.lower():
                start = max(0, i - 2)
                end = min(len(lines), i + 3)
                excerpt = "\n".join(lines[start:end])
                results.append({
                    "document": name,
                    "path": str(path.relative_to(REPO_ROOT) if path.is_relative_to(REPO_ROOT) else path),
                    "excerpt": excerpt,
                    "line": i + 1,
                })
                if len(results) >= max_results:
                    return results

    return results


# ---------------------------------------------------------------------------
# Resource: llms.txt
# ---------------------------------------------------------------------------

@mcp.resource("wildestai://llms.txt")
def llms_txt() -> str:
    """The llms.txt for WildestAI — compact AI discoverability summary."""
    llms_path = REPO_ROOT.parent / "wildest-ai-website" / "public" / "llms.txt"
    if llms_path.exists():
        return llms_path.read_text(encoding="utf-8")
    return (
        "# WildestAI\n\n"
        "WildestAI turns code changes from raw diffs into understandable, "
        "evidence-linked software evolution.\n\n"
        "CLI: wild diff — analyses git diffs with AI, generates dependency graph HTML report.\n"
        "Website: https://wildest.ai\n"
        "GitHub: https://github.com/WildestAI/DiffGraph-CLI\n"
    )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    mcp.run()
