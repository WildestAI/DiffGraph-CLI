

# `wild` CLI Refactor: Git Wrapper + Custom DiffGraph

## 📌 Goal

Transform the `wild` CLI into a **complete `git` wrapper**, with special behavior for `wild diff`. All other `git` commands (e.g. `commit`, `log`, `blame`, etc.) should behave identically to `git`, except that `wild diff` runs custom logic to generate a DiffGraph.

---

## 🏗️ CLI Architecture

- Use `click.group()` to define `wild` as a command group.
- Implement a subcommand for `diff` manually.
- For all other commands, **pass them through to `git` via `subprocess.run()`** with all received arguments.

```python
@click.group(context_settings={"ignore_unknown_options": True, "allow_extra_args": True})
@click.pass_context
def main(ctx):
    ...
```

---

## 🧠 Custom Logic: `wild diff`

### ✅ Supported Inputs

The following `git diff` variants should work:

| Command | Behavior |
|--------|----------|
| `wild diff` | Diff for unstaged + untracked files (default) |
| `wild diff --staged` | Diff for staged files |
| `wild diff <commit-id>` | Diff between HEAD and `<commit-id>` |
| `wild diff <commit-id1> <commit-id2>` | Diff between two commits |
| `wild diff <file>` | Diff for a specific file (unstaged) |

### 🧩 Parsing Strategy

Use `subprocess.run(["git", "diff", *args], capture_output=True)` to get raw diff. Then:
- Pipe this into the DiffGraph generation engine.
- Save HTML/JSON as needed.
- Display/log output or errors.

### 🔥 Error Handling

- Fail loudly (e.g., `sys.exit(1)` with `click.secho(error, fg="red")`)
- Provide actionable errors (e.g., "Large diff detected, please limit your scope.")

---

## 🔄 Passthrough Logic for Other Commands

```python
@main.command(context_settings={"ignore_unknown_options": True})
@click.argument('args', nargs=-1, type=click.UNPROCESSED)
def passthrough(args):
    subprocess.run(["git", *args])
```

Fallback command can be invoked when the subcommand isn’t `diff`.

You can either:
- Use `@main.command()` dynamically
- Or manually detect in `main()` via `ctx.args`

---

## 🧪 Future-Proofing (Optional Flags)

Stub the following optional flags:

- `--no-graph` → skip DiffGraph generation, just pass through
- `--show-diff` → print `git diff` output to stdout as well
- `--output <file>` → write DiffGraph to custom file path

These can be parsed as `click.option()` on the `diff` subcommand.

---

## 🧱 File Structure

```
diffgraph/
  ├── cli.py          # Entry point (wild=diffgraph.cli:main)
  ├── git_passthrough.py
  ├── diff_handler.py # logic to parse, analyze, and visualize diff
  └── utils/
        └── parse_git_diff.py
```

---

## ⚙️ Optional Enhancements (after MVP)

- Support `--cached` alias for `--staged`
- Enable `--name-only`, `--stat`, etc. (if useful for DiffGraph context)
- Fallback to raw `git` output if AI fails (later)

---

## ✅ Completion Criteria

- `wild diff` works with all standard `git diff` options
- All other commands work identically to `git`
- DiffGraph generated and saved correctly
- CLI exits with proper codes
- VSCode extension remains compatible (no regressions)

---

## ⏭️ Next Steps

1. Refactor `cli.py` to define `@click.group()`
2. Create custom handler for `diff`
3. Create passthrough logic for other commands
4. Validate `diff` parsing logic with multiple input formats
5. Validate integration with VSCode extension
6. Test for edge cases and large diffs