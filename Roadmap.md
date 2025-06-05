# 📜 Project Roadmap: diffgraph-ai (Hackathon Version)

This roadmap outlines the step-by-step implementation of `diffgraph-ai`, a CLI tool that reads current git diffs and untracked files, uses AI to understand code changes and their implications, and renders a shareable HTML diffgraph.

Each step is:

* ✅ Independently testable
* 🔁 A minimal vertical slice of functionality
* 📦 Scoped for fast iteration

---

## ✅ Step 1: Initialize the CLI

### 🌟 Goal:

Create a command-line tool `diffgraph-ai` that accepts input flags and runs `git diff` internally.

### 🧹 Constraints:

* Output should be raw `git diff` (text format)
* It must print this to stdout
* CLI should fail gracefully if not inside a git repo

### 💼 Resources:

* Python: [`click`](https://click.palletsprojects.com/) or `argparse`
* Git diff subprocess: [`subprocess.run`](https://docs.python.org/3/library/subprocess.html)

### ✅ Test Plan:

```bash
$ diffgraph-ai
# should print raw git diff, or a friendly error message if repo not found
```

### 📌 Status: `Not Started`

---

## ✅ Step 2: Identify Changed and Untracked Files

### 🌟 Goal:

Detect both:

* Modified/staged files (`git diff --name-only`)
* **Untracked new files** (via `git status`)

### 🧹 Constraints:

* Must include files not yet staged or committed
* Use `git status --porcelain` to detect untracked (`??`)
* Exclude deleted or renamed files for now
* Ignore non-text/binary files

### 💼 Resources:

* [Git porcelain format](https://git-scm.com/docs/git-status#_short_format)
* `subprocess.run`

### ✅ Test Plan:

```bash
# Scenario: added a new file but haven't git-added it
$ diffgraph-ai
# Should list modified AND untracked files
```

### 📌 Status: `Not Started`

---

## ✅ Step 3: Load File Contents (Tracked and Untracked)

### 🌟 Goal:

Load the full content of all changed files:

* For modified/tracked files: use `git diff` to find modified lines
* For **untracked files**: read the entire file, treat as new

### 🧹 Constraints:

* Untracked files must be treated as fully added
* Preserve filename and content in memory
* Structure output as a list of file objects: `{ path, status, content }`

### 💼 Resources:

* `os.path.exists`
* Python file I/O (`open(path).read()`)

### ✅ Test Plan:

```bash
# After creating a new file:
$ diffgraph-ai
# Output should include full content of the new file
```

### 📌 Status: `Not Started`

---

## ✅ Step 4: Call OpenAI Agent with Diff + Files

### 🌟 Goal:

Send the raw git diff and the changed file contents to an OpenAI agent for analysis.

### 🧹 Constraints:

* Use `openai` Python SDK
* Use GPT-4o or GPT-4.1
* Keep prompts under token limits (8K to 32K)

### 💼 Resources:

* [OpenAI Python SDK](https://github.com/openai/openai-python)
* Provided system prompt from earlier steps

### ✅ Test Plan:

```bash
$ diffgraph-ai
# Output: Structured response from GPT (summary + mermaid code)
```

### 📌 Status: `Not Started`

---

## ✅ Step 5: Generate and Save HTML Report

### 🌟 Goal:

Create an HTML file (`diffgraph.html`) that contains:

* Behavior summary (markdown rendered as HTML)
* Mermaid diagram (rendered using Mermaid.js)

### 🧹 Constraints:

* Fully self-contained HTML (no server)
* Should open in browser (`open diffgraph.html`)
* Use a simple HTML + JS template

### 💼 Resources:

* [Mermaid.js CDN](https://cdn.jsdelivr.net/npm/mermaid)
* Python templating with `jinja2` (optional)

### ✅ Test Plan:

```bash
$ diffgraph-ai > diffgraph.html && open diffgraph.html
# Should show graph + explanation
```

### 📌 Status: `Not Started`

---

## ✅ Step 6: Handle No Diff or Clean State

### 🌟 Goal:

Make sure `diffgraph-ai` exits cleanly when there is no diff (i.e., working directory is clean).

### 🧹 Constraints:

* CLI should show: “No changes to analyze”
* Should not call OpenAI if no diff or untracked file is present

### 💼 Resources:

* `git diff --quiet` exit code

### ✅ Test Plan:

```bash
# With clean repo:
$ diffgraph-ai
# Should print "No changes to analyze"
```

### 📌 Status: `Not Started`

---

## ✅ Step 7: Polish Output (Titles, Colors, CSS)

### 🌟 Goal:

Add CSS to the HTML output for a more polished look:

* Title bar: “Diffgraph Report”
* Syntax highlighting for code blocks
* Optional dark mode toggle

### 🧹 Constraints:

* Must work offline (use embedded CSS)

### 💼 Resources:

* [Tailwind CDN](https://tailwindcss.com/docs/installation/play-cdn)
* [Highlight.js CDN](https://highlightjs.org/)

### ✅ Test Plan:

```bash
# Open HTML and inspect: layout, styles, formatting
```

### 📌 Status: `Not Started`

---

## ✅ Step 8: Create Demo Script + Sample Diff

### 🌟 Goal:

Prepare a simple Git repo with a few staged or unstaged changes that can reliably demo the tool.

### 🧹 Constraints:

* Must run with one command
* All code + diff should be deterministic

### 💼 Resources:

* `examples/` folder with sample code
* Git alias or shell script

### ✅ Test Plan:

```bash
$ cd examples/demo1
$ diffgraph-ai && open diffgraph.html
```

### 📌 Status: `Not Started`

---

## 🏁 Final Deliverables Checklist

* [ ] CLI (`diffgraph-ai`)
* [ ] HTML diffgraph report (Mermaid + Summary)
* [ ] Example repo with demo-ready diff
* [ ] Optional: OpenAI Agent configuration JSON (for Cursor / Claude etc.)
* [ ] README with install + run instructions
