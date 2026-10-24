# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

`wild` (package `diffgraph`, entry point `diffgraph.cli:main`) is a Git wrapper CLI. `wild diff` gets custom handling. Every other `wild <cmd>` is passed straight through to `git`. Python >= 3.10.

## Commands

```bash
python -m pip install -r requirements.txt -e . pytest   # dev setup (matches CI)
python -m pytest                                         # full suite
python -m pytest tests/test_structural.py::test_name     # single test
python -m compileall -q diffgraph tests                  # CI also runs this
git diff --check                                         # CI fails on whitespace errors
python build.py --output-dir release --name wild         # PyInstaller one-file binary
```

CI (`.github/workflows/test.yml`) runs on Python 3.10, 3.11 and 3.12. `tests/conftest.py` points Git config at `/dev/null` so tests that build temporary repos don't pick up user or system Git config.

`build.py` refuses to run if there is a `.env` file anywhere in the workspace, so binaries can never bundle credentials. Delete or move `.env` before building.

## Architecture

The canonical pipeline runs one way and must stay **local and offline**:

```
cli.py ──► artifact.build_validated_artifact
             ├─ structural.analyze_local_diff   (tree-sitter Python analysis)
             │    └─ git_snapshot.resolve_*     (exact Git snapshot: staged / unstaged / A..B / A...B)
             └─ contract.ValidatedArtifact.from_value  (jsonschema check against diffgraph/schema/diffgraph-v2.schema.json)
         ──► one consumer: formatters/terminal.py (default) | formatters/html.py | canonical JSON (artifact.py)
```

Key invariants (tests enforce them):

- **Build once, validate once, dispatch once.** Each invocation resolves the snapshot once and builds one artifact. Consumers get only a `ValidatedArtifact`. They never re-read the repo or rebuild anything. `ValidatedArtifact` can only be created through `from_value`, and `.value` returns a deep copy.
- **No AI or network imports on canonical paths without `--llm`.** `test_artifact_dispatch.py` and `test_html_formatter.py` check that `diffgraph.ai_analysis` and `agents` (openai-agents) are never imported and that sockets are never opened. Keep new imports in canonical modules local-only. The legacy modules must only be imported lazily, inside the `legacy-html` branch of `cli.py`.
- **`contract.py` stays independent** of Git, tree-sitter and AI code, so outside consumers can validate artifacts without pulling those in. `enrich_with_prose` can attach AI prose to `summary` only. It must never change files, symbols or relationships.
- **No guessing.** Anything the analyzer can't prove gets a scoped warning (`UNSUPPORTED_LANGUAGE`, `PARSE_FAILURE`, `PARTIAL_ANALYSIS` for NUL/binary content, and the resolution warnings). It never invents symbols or edges. Only Python (`.py`/`.pyi`) gets structural extraction. A call edge is emitted only when it resolves to exactly one target, either in the same file or through a changed-file import. Attribute dispatch and shadowed names are left out on purpose.
- **Schema versioning.** `schema_version` is `MAJOR.MINOR`. Unknown majors are rejected. Minor bumps within v2 must be additive, and the whole artifact must still validate against the packaged schema. If the schema changes, also update `diffgraph-v2.structural.example.json` (both files are listed in `package_data` in `setup.py`).
- **Determinism.** JSON is written with `sort_keys=True`, written atomically, and missing parent directories are not created. Ordering everywhere must be stable.
- **CLI contract.** Exit code 0 means success (no changes still counts as success). 1 means a runtime, validation or output failure. 2 means a usage error. stdout carries only the artifact or terminal report. Diagnostics go to stderr. Option conflicts (`--structural-json` together with `--format`/`--output`, `--format terminal` together with `-o`, and so on) are `click.UsageError`s in `cli.main`. Pathspecs after `--` are relative to the directory where `wild` is invoked.

### Opt-in AI summaries (`--llm`)

`cli._enrich_with_llm` lazily imports `llm_summaries.py` (builds per-file prompts from the artifact's recorded blob ids, batches them, keeps only requested node ids) and `relay.py` (stdlib BYOK Relay client; the only network code on canonical paths). `contract.enrich_with_node_summaries` attaches `summary` to existing file/symbol entries, bumps `schema_version` to 2.1, and records privacy metadata. Formatters just render `summary` when present. Any backend implementing `llm_summaries.ChatClient` can replace the relay. Tests must never hit the network (`tests/test_llm_summaries.py` fakes the transport).

### Deprecated legacy path

`wild diff --format legacy-html` keeps the old OpenAI-agents flow (`ai_analysis.py`, `graph_manager.py`, `html_report.py`, `utils/git_utils.py`, `env_loader.py`) for one release. It loads assets from CDNs and needs `OPENAI_API_KEY`. Don't extend it. Canonical HTML (`formatters/html.py`) is self-contained and has an offline CSP.

## Versioning & releases

Bump the version in both `diffgraph/__init__.py` (`__version__`, which is embedded in artifacts and the binary) and `setup.py`, and add a `CHANGELOG.md` entry (Keep a Changelog format). A release happens only when a merged PR carries `release:publish` plus one `release:patch|minor|major` label and closes a roadmap issue that has the required labels. Tags look like `cli-v<semver>-<12-char-sha>`. See `docs/RELEASING.md` and `scripts/release_eligibility.py`.

## Other files

- `mcp_server.py`: FastMCP server that runs `wild diff` and serves the docs. It needs `pip install mcp`, which is not in `requirements.txt`.
- `skill.md` and `llms.txt` are user-facing docs for agents. Update them when CLI behavior changes. Parts of `llms.txt` still describe the old AI-first behavior.
