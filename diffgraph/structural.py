"""Deterministic, local DiffGraph v2 extraction from exact Git snapshots.

This first baseline intentionally supports Python only. Other languages remain in
``files`` and produce scoped ``UNSUPPORTED_LANGUAGE`` warnings; no capability is
inferred from a filename beyond that explicit boundary.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from diffgraph import __version__ as package_version
from diffgraph.git_snapshot import (
    ResolutionWarning,
    SnapshotEntry,
    resolve_staged,
    resolve_unstaged,
)

ANALYZER = "diffgraph-python-tree-sitter"
QUERY_VERSION = "python-structure-v1"


@dataclass(frozen=True)
class _Symbol:
    name: str
    qualified_name: str
    kind: str
    parent: Optional[str]
    start_line: int
    end_line: int
    text_hash: str


@dataclass(frozen=True)
class _Import:
    module: str
    line: int
    snippet: str


def _run(repository: str, *args: str) -> bytes:
    return subprocess.run(
        ["git", *args], cwd=repository, check=True, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    ).stdout


def _root(repository: str) -> str:
    return os.fsdecode(_run(repository, "rev-parse", "--show-toplevel").rstrip(b"\n"))


def _blob(repository: str, oid: Optional[str]) -> Optional[bytes]:
    if oid is None:
        return None
    return _run(repository, "cat-file", "blob", oid)


def _worktree_bytes(repository: str, entry: SnapshotEntry) -> Optional[bytes]:
    if entry.new_path is None:
        return None
    path = os.path.join(repository, entry.new_path)
    before = os.stat(path, follow_symlinks=False)
    with open(path, "rb") as handle:
        content = handle.read()
        opened = os.fstat(handle.fileno())
    after = os.stat(path, follow_symlinks=False)
    identity = lambda value: (value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns)
    if identity(before) != identity(opened) or identity(before) != identity(after):
        raise OSError("working-tree file changed while it was read")
    computed = os.fsdecode(
        subprocess.run(
            ["git", "hash-object", "--stdin", "--path={}".format(entry.new_path)],
            cwd=repository, input=content, check=True, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        ).stdout
    ).strip()
    if computed != entry.new_oid:
        raise OSError("working-tree content no longer matches resolved Git identity")
    return content


def _parser():
    import tree_sitter
    import tree_sitter_language_pack

    # Construct the official parser directly so byte offsets and byte input
    # remain exact across language-pack releases.
    return tree_sitter.Parser(tree_sitter_language_pack.get_language("python"))


def _node_text(source: bytes, node) -> str:
    return source[node.start_byte:node.end_byte].decode("utf-8")


def _name_child(node):
    child = node.child_by_field_name("name")
    if child is not None:
        return child
    return next((item for item in node.children if item.type == "identifier"), None)


def _parse_python(content: bytes) -> Tuple[List[_Symbol], List[_Import]]:
    # Do not silently replace undecodable source: the warning must identify the
    # exact side that could not be structurally analyzed.
    content.decode("utf-8")
    tree = _parser().parse(content)
    if tree.root_node.has_error:
        raise ValueError("Tree-sitter reported a syntax error")

    symbols: List[_Symbol] = []
    imports: List[_Import] = []

    def visit(node, parents: Tuple[Tuple[str, str], ...] = ()) -> None:
        next_parents = parents
        if node.type in ("class_definition", "function_definition"):
            name_node = _name_child(node)
            if name_node is not None:
                name = _node_text(content, name_node)
                parent_names = tuple(item[0] for item in parents)
                parent = ".".join(parent_names) if parent_names else None
                is_method = bool(parents and parents[-1][1] == "class")
                kind = (
                    "class"
                    if node.type == "class_definition"
                    else "method"
                    if is_method
                    else "function"
                )
                qname = ".".join((*parent_names, name))
                body = content[node.start_byte:node.end_byte]
                symbols.append(
                    _Symbol(
                        name,
                        qname,
                        kind,
                        parent,
                        node.start_point[0] + 1,
                        node.end_point[0] + 1,
                        hashlib.sha256(body).hexdigest(),
                    )
                )
                next_parents = (*parents, (name, kind))
        elif node.type in ("import_statement", "import_from_statement"):
            snippet = _node_text(content, node)
            if node.type == "import_statement":
                names = [c for c in node.children if c.type in ("dotted_name", "aliased_import")]
                for item in names:
                    raw = _node_text(content, item).split(" as ", 1)[0]
                    imports.append(_Import(raw, node.start_point[0] + 1, snippet))
            else:
                module_node = node.child_by_field_name("module_name")
                if module_node is not None:
                    imports.append(_Import(_node_text(content, module_node), node.start_point[0] + 1, snippet))
        for child in node.children:
            visit(child, next_parents)

    visit(tree.root_node)
    return sorted(symbols, key=lambda s: (s.qualified_name, s.start_line)), sorted(
        imports, key=lambda item: (item.line, item.module, item.snippet)
    )


def _change_kind(status: str, old_oid: Optional[str], new_oid: Optional[str]) -> str:
    if status == "A": return "added"
    if status == "D": return "deleted"
    if status == "R": return "renamed" if old_oid == new_oid else "renamed_modified"
    return "modified"


def _provenance(entry: SnapshotEntry, old: Optional[bytes], new: Optional[bytes]) -> str:
    values = {
        "status": entry.status, "old_path": entry.old_path, "new_path": entry.new_path,
        "old_mode": entry.old_mode, "new_mode": entry.new_mode,
        "old_oid": entry.old_oid, "new_oid": entry.new_oid,
        "old_sha256": hashlib.sha256(old).hexdigest() if old is not None else None,
        "new_sha256": hashlib.sha256(new).hexdigest() if new is not None else None,
    }
    return json.dumps(values, sort_keys=True, separators=(",", ":"))


def _parser_provenance(oid: Optional[str]) -> str:
    try:
        parser_version = version("tree-sitter-language-pack")
    except PackageNotFoundError:
        parser_version = "unknown"
    return "analyzer={};parser=tree-sitter-language-pack@{};query={};blob={}".format(
        ANALYZER, parser_version, QUERY_VERSION, oid or "absent"
    )


def _warning(code: str, path: Optional[str], detail: str) -> Dict[str, str]:
    result = {"code": code, "detail": detail}
    if path is not None: result["file"] = path
    return result


def _resolution_warning(item: ResolutionWarning) -> Dict[str, str]:
    return _warning("UNKNOWN", item.path, "{}: {}".format(item.code, item.message))


def _symbol_id(path: str, qualified_name: str) -> str:
    return "sym::{}::{}".format(path, qualified_name)


def _evidence(path: str, symbol: _Symbol, oid: Optional[str]) -> List[Dict]:
    return [{
        "kind": "ast_parse", "file": path, "line_start": symbol.start_line,
        "line_end": symbol.end_line, "detail": _parser_provenance(oid),
    }]


def analyze_local_diff(
    repository: str = ".", *, staged: bool = False,
    pathspecs: Optional[Sequence[str]] = None, wild_version: str = package_version,
) -> Dict:
    """Build a schema-v2 structural artifact for HEAD→index or index→worktree."""
    started = time.monotonic()
    root = _root(repository)
    resolution = (resolve_staged if staged else resolve_unstaged)(root, pathspecs)
    warnings = [_resolution_warning(item) for item in resolution.warnings]
    files: List[Dict] = []
    symbols: List[Dict] = []
    relationships: List[Dict] = []
    analyzed = skipped = 0

    for entry in resolution.entries:
        path = entry.new_path or entry.old_path
        assert path is not None
        try:
            old = _blob(root, entry.old_oid)
            new = _blob(root, entry.new_oid) if staged else _worktree_bytes(root, entry)
        except (OSError, subprocess.CalledProcessError) as error:
            old = new = None
            warnings.append(_warning("PARTIAL_ANALYSIS", path, "snapshot read failed: {}".format(error)))

        file_entry = {
            "id": "file::" + path, "path": path,
            "old_path": entry.old_path if entry.status in ("R", "C") else None,
            "language": "python" if Path(path).suffix.lower() == ".py" else None,
            "change_kind": _change_kind(entry.status, entry.old_oid, entry.new_oid),
            "analysis_source": "structural",
            "evidence": [{"kind": "git_diff_name_status", "detail": _provenance(entry, old, new)}],
        }
        files.append(file_entry)
        if file_entry["language"] != "python":
            skipped += 1
            warnings.append(_warning("UNSUPPORTED_LANGUAGE", path, "Deterministic extraction currently supports Python (.py) only."))
            continue
        if old is None and entry.old_oid is not None or new is None and entry.new_oid is not None:
            skipped += 1
            continue

        parser_errors = (
            UnicodeDecodeError, ValueError, RuntimeError, ImportError, OSError, TypeError
        )
        try:
            old_symbols, old_imports = _parse_python(old) if old is not None else ([], [])
        except parser_errors as error:
            warnings.append(_warning("PARSE_FAILURE", entry.old_path or path, "pre-change: {}: {}".format(type(error).__name__, error)))
            skipped += 1
            continue
        try:
            new_symbols, new_imports = _parse_python(new) if new is not None else ([], [])
        except parser_errors as error:
            warnings.append(_warning("PARSE_FAILURE", path, "post-change: {}: {}".format(type(error).__name__, error)))
            skipped += 1
            continue
        analyzed += 1
        old_map = {item.qualified_name: item for item in old_symbols}
        new_map = {item.qualified_name: item for item in new_symbols}
        output_path = path
        for qname in sorted(set(old_map) | set(new_map)):
            before, after = old_map.get(qname), new_map.get(qname)
            current = after or before
            assert current is not None
            kind = "added" if before is None else "deleted" if after is None else (
                "unchanged" if before.text_hash == after.text_hash else "modified"
            )
            oid = entry.new_oid if after is not None else entry.old_oid
            location = None if after is None else {
                "file": output_path, "line_start": current.start_line, "line_end": current.end_line,
            }
            symbols.append({
                "id": _symbol_id(output_path, qname), "name": current.name,
                "qualified_name": qname, "file_id": "file::" + output_path,
                "kind": current.kind,
                "parent_id": _symbol_id(output_path, current.parent) if current.parent else None,
                "change_kind": kind, "analysis_source": "structural",
                "location": location, "evidence": _evidence(output_path, current, oid),
            })

        for qname, item in sorted(new_map.items()):
            source = _symbol_id(output_path, qname)
            if item.parent:
                target = _symbol_id(output_path, item.parent)
                relationships.append({
                    "id": "rel::{}->{}".format(target, source), "kind": "contains",
                    "source_id": target, "target_id": source, "analysis_source": "structural",
                    "evidence": _evidence(output_path, item, entry.new_oid),
                })
            elif item.kind in ("function", "class"):
                relationships.append({
                    "id": "rel::file::{}->{}".format(output_path, source), "kind": "defines",
                    "source_id": "file::" + output_path, "target_id": source,
                    "analysis_source": "structural", "evidence": _evidence(output_path, item, entry.new_oid),
                })

        def keyed_imports(items: List[_Import]) -> Dict[Tuple[str, int], _Import]:
            occurrences: Dict[str, int] = {}
            result: Dict[Tuple[str, int], _Import] = {}
            for import_item in items:
                occurrence = occurrences.get(import_item.module, 0)
                occurrences[import_item.module] = occurrence + 1
                result[(import_item.module, occurrence)] = import_item
            return result

        old_import_map = keyed_imports(old_imports)
        new_import_map = keyed_imports(new_imports)
        for import_key in sorted(set(old_import_map) | set(new_import_map)):
            before = old_import_map.get(import_key)
            after = new_import_map.get(import_key)
            item = after or before
            assert item is not None
            module, occurrence = import_key
            suffix = "" if occurrence == 0 else "#{}".format(occurrence)
            qualified_name = "import::{}{}".format(module, suffix)
            target = _symbol_id(output_path, qualified_name)
            oid = entry.new_oid if after is not None else entry.old_oid
            evidence = [
                {
                    "kind": "import_statement",
                    "file": output_path,
                    "line_start": item.line,
                    "line_end": item.line,
                    "snippet": item.snippet,
                    "detail": _parser_provenance(oid),
                }
            ]
            import_kind = (
                "added" if before is None else "deleted" if after is None else "unchanged"
            )
            location = (
                {
                    "file": output_path,
                    "line_start": item.line,
                    "line_end": item.line,
                }
                if after is not None
                else None
            )
            symbols.append(
                {
                    "id": target,
                    "name": module,
                    "qualified_name": qualified_name,
                    "file_id": "file::" + output_path,
                    "kind": "import",
                    "parent_id": None,
                    "change_kind": import_kind,
                    "analysis_source": "structural",
                    "location": location,
                    "evidence": evidence,
                }
            )
            if after is not None:
                relationships.append(
                    {
                        "id": "rel::file::{}->{}".format(output_path, target),
                        "kind": "imports",
                        "source_id": "file::" + output_path,
                        "target_id": target,
                        "analysis_source": "structural",
                        "evidence": evidence,
                        "label": "unresolved/external module: " + module,
                    }
                )

    files.sort(key=lambda item: item["path"])
    symbols.sort(key=lambda item: item["id"])
    relationships.sort(key=lambda item: (item["id"], item["kind"]))
    warnings.sort(key=lambda item: (item.get("file", ""), item["code"], item.get("detail", "")))
    return {
        "schema_version": "2.0",
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "wild_version": wild_version,
        "diff_ref": {
            "kind": "staged" if staged else "unstaged", "base_ref": "HEAD" if staged else None,
            "head_ref": None, "pathspecs": list(pathspecs or []), "repo_root": root,
        },
        "files": files, "symbols": symbols, "relationships": relationships,
        "summary": None,
        "metadata": {
            "privacy_tier": "local", "cloud_providers_used": [],
            "analysis_duration_ms": int((time.monotonic() - started) * 1000),
            "languages_detected": ["python"] if any(f["language"] == "python" for f in files) else [],
            "files_analyzed": analyzed, "files_skipped": skipped, "llm_calls": 0,
            "llm_model": None, "tiers_used": ["structural"], "warnings": warnings,
        },
    }
