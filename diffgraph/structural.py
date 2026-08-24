"""Deterministic, local DiffGraph v2 extraction from exact Git snapshots.

This first baseline intentionally supports Python only. Other languages remain in
``files`` and produce scoped ``UNSUPPORTED_LANGUAGE`` warnings; no capability is
inferred from a filename beyond that explicit boundary.
"""
from __future__ import annotations

import hashlib
import json
import threading
import time
from difflib import SequenceMatcher
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from diffgraph import __version__ as package_version
from diffgraph.contract import CURRENT_SCHEMA_VERSION
from diffgraph.git_snapshot import (
    GitSnapshotError,
    ResolutionWarning,
    SnapshotEntry,
    read_worktree_blob,
    repository_root,
    resolve_commit_range,
    resolve_staged,
    resolve_unstaged,
    run_git,
)

ANALYZER = "diffgraph-python-tree-sitter"
QUERY_VERSION = "python-structure-v2"
_PARSER_STATE = threading.local()


class StructuralDependencyError(ImportError):
    """A required local structural parser dependency is unavailable."""


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
    bindings: Tuple[str, ...]


@dataclass(frozen=True)
class _Call:
    caller: Optional[str]
    name: str
    line: int
    snippet: str


def _blob(repository: str, oid: Optional[str]) -> Optional[bytes]:
    if oid is None:
        return None
    return run_git(repository, "cat-file", "blob", oid)


def _worktree_bytes(repository: str, entry: SnapshotEntry) -> Optional[bytes]:
    if entry.new_path is None:
        return None
    return read_worktree_blob(
        repository, entry.new_path, entry.new_mode, expected_oid=entry.new_oid
    )


def _line_counts(
    old: Optional[bytes], new: Optional[bytes]
) -> Tuple[Optional[int], Optional[int]]:
    """Return deterministic added/removed line counts, or nulls for binaries."""
    old_bytes = old or b""
    new_bytes = new or b""
    if b"\0" in old_bytes or b"\0" in new_bytes:
        return None, None

    matcher = SequenceMatcher(
        None,
        old_bytes.splitlines(keepends=True),
        new_bytes.splitlines(keepends=True),
        autojunk=False,
    )
    added = removed = 0
    for tag, old_start, old_end, new_start, new_end in matcher.get_opcodes():
        if tag in ("replace", "delete"):
            removed += old_end - old_start
        if tag in ("replace", "insert"):
            added += new_end - new_start
    return added, removed


def _binary_sides(old: Optional[bytes], new: Optional[bytes]) -> Tuple[str, ...]:
    """Return snapshot sides matching the deterministic NUL-byte heuristic."""
    sides = []
    if old is not None and b"\0" in old:
        sides.append("pre-change")
    if new is not None and b"\0" in new:
        sides.append("post-change")
    return tuple(sides)


def _parser():
    parser = getattr(_PARSER_STATE, "python_parser", None)
    if parser is not None:
        return parser
    try:
        import tree_sitter
        import tree_sitter_language_pack
    except ImportError as error:
        raise StructuralDependencyError(
            "Python structural analysis requires tree-sitter and "
            "tree-sitter-language-pack"
        ) from error

    # Construct the official parser directly so byte offsets and byte input
    # remain exact across language-pack releases.
    parser = tree_sitter.Parser(tree_sitter_language_pack.get_language("python"))
    _PARSER_STATE.python_parser = parser
    return parser


def _node_text(source: bytes, node) -> str:
    return source[node.start_byte:node.end_byte].decode("utf-8")


def _name_child(node):
    child = node.child_by_field_name("name")
    if child is not None:
        return child
    return next((item for item in node.children if item.type == "identifier"), None)


def _parse_python(
    content: bytes,
) -> Tuple[
    List[_Symbol],
    List[_Import],
    List[_Call],
    Dict[Optional[str], set],
    List[Tuple[str, int]],
]:
    # Do not silently replace undecodable source: the warning must identify the
    # exact side that could not be structurally analyzed.
    content.decode("utf-8")
    tree = _parser().parse(content)
    if tree.root_node.has_error:
        raise ValueError("Tree-sitter reported a syntax error")

    symbols: List[_Symbol] = []
    imports: List[_Import] = []
    calls: List[_Call] = []
    bindings: Dict[Optional[str], set] = {}
    module_rebindings: List[Tuple[str, int]] = []
    symbol_occurrences: Dict[str, int] = {}

    def identifiers(node) -> set:
        found = set()
        if node.type == "identifier":
            found.add(_node_text(content, node))
        for child in node.children:
            found.update(identifiers(child))
        return found

    def visit(node, parents: Tuple[Tuple[str, str], ...] = ()) -> None:
        next_parents = parents
        if node.type in ("class_definition", "function_definition"):
            name_node = _name_child(node)
            if name_node is not None:
                name = _node_text(content, name_node)
                parent = parents[-1][0] if parents else None
                is_method = bool(parents and parents[-1][1] == "class")
                kind = (
                    "class"
                    if node.type == "class_definition"
                    else "method"
                    if is_method
                    else "function"
                )
                base_qname = "{}.{}".format(parent, name) if parent else name
                occurrence = symbol_occurrences.get(base_qname, 0)
                symbol_occurrences[base_qname] = occurrence + 1
                qname = (
                    base_qname
                    if occurrence == 0
                    else "{}#{}".format(base_qname, occurrence)
                )
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
                next_parents = (*parents, (qname, kind))
        elif node.type in ("import_statement", "import_from_statement"):
            snippet = _node_text(content, node)
            if node.type == "import_statement":
                names = [c for c in node.children if c.type in ("dotted_name", "aliased_import")]
                for item in names:
                    if item.type == "aliased_import":
                        name_node = item.child_by_field_name("name")
                        if name_node is None:
                            raise ValueError("aliased import has no name")
                        raw = _node_text(content, name_node)
                    else:
                        raw = _node_text(content, item)
                    if item.type == "aliased_import":
                        binding = _node_text(content, item.children[-1])
                    else:
                        # ``import package.submodule`` binds ``package``.
                        binding = raw.split(".", 1)[0]
                    imports.append(_Import(
                        raw, node.start_point[0] + 1, snippet, (binding,)
                    ))
            else:
                module_node = node.child_by_field_name("module_name")
                if module_node is not None:
                    imported = []
                    after_import = False
                    for child in node.children:
                        if child.type == "import":
                            after_import = True
                            continue
                        if not after_import or child.type not in (
                            "dotted_name", "aliased_import"
                        ):
                            continue
                        if child.type == "aliased_import":
                            imported.append(_node_text(content, child.children[-1]))
                        else:
                            imported.append(_node_text(content, child).split(".", 1)[0])
                    imports.append(_Import(
                        _node_text(content, module_node),
                        node.start_point[0] + 1,
                        snippet,
                        tuple(imported),
                    ))
        elif node.type == "call":
            function = node.child_by_field_name("function")
            if function is not None and function.type == "identifier":
                caller = parents[-1][0] if parents else None
                ancestor = node.parent
                while ancestor is not None:
                    if ancestor.type in ("class_definition", "function_definition"):
                        body = ancestor.child_by_field_name("body")
                        if body is not None and not (
                            body.start_byte <= node.start_byte
                            and node.end_byte <= body.end_byte
                        ):
                            caller = parents[-2][0] if len(parents) > 1 else None
                        break
                    ancestor = ancestor.parent
                calls.append(
                    _Call(
                        caller,
                        _node_text(content, function),
                        node.start_point[0] + 1,
                        _node_text(content, node),
                    )
                )

        scope = parents[-1][0] if parents else None
        if node.type == "parameters" or node.type in (
            "import_statement", "import_from_statement"
        ):
            bindings.setdefault(scope, set()).update(identifiers(node))
        elif node.type in ("assignment", "annotated_assignment", "for_statement"):
            left = node.child_by_field_name("left")
            if left is not None:
                bound_names = identifiers(left)
                bindings.setdefault(scope, set()).update(bound_names)
                if scope is None:
                    module_rebindings.extend(
                        (name, node.start_point[0] + 1) for name in bound_names
                    )
        for child in node.children:
            visit(child, next_parents)

    visit(tree.root_node)
    return (
        sorted(symbols, key=lambda s: (s.qualified_name, s.start_line)),
        sorted(imports, key=lambda item: (item.line, item.module, item.snippet)),
        sorted(calls, key=lambda item: (item.line, item.caller or "", item.name, item.snippet)),
        bindings,
        module_rebindings,
    )


def _change_kind(status: str, old_oid: Optional[str], new_oid: Optional[str]) -> str:
    if status == "A":
        return "added"
    if status == "D":
        return "deleted"
    if status == "R":
        return "renamed" if old_oid == new_oid else "renamed_modified"
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


@lru_cache(maxsize=1)
def _parser_version() -> str:
    try:
        return version("tree-sitter-language-pack")
    except PackageNotFoundError:
        return "unknown"


def _parser_provenance(oid: Optional[str]) -> str:
    return "analyzer={};parser=tree-sitter-language-pack@{};query={};blob={}".format(
        ANALYZER, _parser_version(), QUERY_VERSION, oid or "absent"
    )


def _warning(code: str, path: Optional[str], detail: str) -> Dict[str, str]:
    result = {"code": code, "detail": detail}
    if path is not None:
        result["file"] = path
    return result


def _resolution_warning(item: ResolutionWarning) -> Dict[str, str]:
    known_codes = {
        "not_a_git_repository",
        "git_diff_failed",
        "malformed_git_output",
        "missing_object_id",
        "unsupported_worktree_entry",
        "worktree_read_failed",
        "hash_object_failed",
        "malformed_hash_object_output",
        "unmerged_index_entry",
    }
    code = item.code if item.code in known_codes else "UNKNOWN"
    return _warning(code, item.path, "{}: {}".format(item.code, item.message))


def _symbol_id(path: str, qualified_name: str) -> str:
    return "sym::{}::{}".format(path, qualified_name)


def _evidence(path: str, symbol: _Symbol, oid: Optional[str]) -> List[Dict]:
    return [{
        "kind": "ast_parse", "file": path, "line_start": symbol.start_line,
        "line_end": symbol.end_line, "detail": _parser_provenance(oid),
    }]


def _keyed_imports(items: List[_Import]) -> Dict[Tuple[str, int], _Import]:
    occurrences: Dict[str, int] = {}
    result: Dict[Tuple[str, int], _Import] = {}
    for import_item in items:
        occurrence = occurrences.get(import_item.module, 0)
        occurrences[import_item.module] = occurrence + 1
        result[(import_item.module, occurrence)] = import_item
    return result


def _resolve_call_target(
    call: _Call,
    symbols: Dict[str, _Symbol],
    bindings: Dict[Optional[str], set],
    imported_targets: Dict[str, Optional[str]],
) -> Optional[str]:
    """Resolve only syntax-grounded, same-file Python calls.

    Bare identifiers shadowed by a parameter, assignment, loop target, or import
    are deliberately left unresolved. Attribute calls and ambiguous duplicate
    definitions are likewise omitted rather than guessed.
    """
    candidates: List[str] = []
    current_name = call.caller
    while current_name is not None:
        current = symbols.get(current_name)
        if current is None:
            break
        # Function and method scopes participate in lexical lookup. Class
        # namespaces do not: a bare name in a method never resolves through
        # sibling class attributes or methods.
        if current.kind in ("function", "method"):
            if call.name in bindings.get(current_name, set()):
                return None
            candidates.append("{}.{}".format(current_name, call.name))
        current_name = current.parent

    if call.name in bindings.get(None, set()):
        # An explicit import is a deterministic external target. Other global
        # bindings (for example an assignment) remain intentionally unresolved.
        return imported_targets.get(call.name)
    candidates.append(call.name)

    for candidate in candidates:
        matches = [
            qname
            for qname, symbol in symbols.items()
            if symbol.kind in ("function", "class")
            and (qname == candidate or qname.startswith(candidate + "#"))
        ]
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            return None
    return None


def _imported_call_targets(
    imports: Dict[Tuple[str, int], _Import],
    module_rebindings: List[Tuple[str, int]],
) -> Dict[str, Optional[str]]:
    """Map unambiguous, unrebound import bindings to external import symbols."""

    targets: Dict[str, Optional[str]] = {}
    import_lines: Dict[str, int] = {}
    for (module, occurrence), item in imports.items():
        suffix = "" if occurrence == 0 else "#{}".format(occurrence)
        target = "import::{}{}".format(module, suffix)
        for binding in item.bindings:
            if binding in targets:
                # Re-importing the same local name makes the final binding
                # order-dependent. Do not claim a particular external target.
                targets[binding] = None
            else:
                targets[binding] = target
            import_lines[binding] = item.line
    for binding, line in module_rebindings:
        if line > import_lines.get(binding, line):
            # A later module-level assignment replaces the imported binding.
            targets[binding] = None
    return targets


def analyze_local_diff(
    repository: str = ".", *, staged: bool = False,
    pathspecs: Optional[Sequence[str]] = None,
    base_ref: Optional[str] = None,
    head_ref: Optional[str] = None,
    three_dot: bool = False,
    wild_version: str = package_version,
) -> Dict:
    """Build a schema-v2 artifact for a local snapshot or immutable commit range."""
    started = time.monotonic()
    root = repository_root(repository)
    if (base_ref is None) != (head_ref is None):
        raise ValueError("base_ref and head_ref must be supplied together")
    is_commit_range = base_ref is not None
    if is_commit_range and staged:
        raise ValueError("staged and commit-range comparisons are mutually exclusive")
    resolution = (
        resolve_commit_range(
            repository,
            base_ref,
            head_ref,
            three_dot=three_dot,
            pathspecs=pathspecs,
        )
        if is_commit_range
        else (resolve_staged if staged else resolve_unstaged)(repository, pathspecs)
    )
    warnings = [_resolution_warning(item) for item in resolution.warnings]
    files: List[Dict] = []
    symbols: List[Dict] = []
    relationships: List[Dict] = []
    analyzed = skipped = 0

    for entry in resolution.entries:
        path = entry.new_path or entry.old_path
        if path is None:
            raise RuntimeError("snapshot entry has neither an old nor a new path")
        try:
            old = _blob(root, entry.old_oid)
            new = (
                _blob(root, entry.new_oid)
                if staged or is_commit_range
                else _worktree_bytes(root, entry)
            )
        except (OSError, GitSnapshotError) as error:
            old = new = None
            warnings.append(_warning("PARTIAL_ANALYSIS", path, "snapshot read failed: {}".format(error)))

        snapshot_missing = (
            old is None and entry.old_oid is not None
        ) or (
            new is None and entry.new_oid is not None
        )
        binary_sides = () if snapshot_missing else _binary_sides(old, new)
        lines_added, lines_removed = (
            (None, None) if snapshot_missing or binary_sides else _line_counts(old, new)
        )
        file_entry = {
            "id": "file::" + path, "path": path,
            "old_path": entry.old_path if entry.status in ("R", "C") else None,
            "language": (
                "python"
                if not binary_sides and Path(path).suffix.lower() == ".py"
                else None
            ),
            "change_kind": _change_kind(entry.status, entry.old_oid, entry.new_oid),
            "lines_added": lines_added,
            "lines_removed": lines_removed,
            "analysis_source": "structural",
            "evidence": [{"kind": "git_diff_name_status", "detail": _provenance(entry, old, new)}],
        }
        files.append(file_entry)
        if binary_sides:
            skipped += 1
            warnings.append(_warning(
                "PARTIAL_ANALYSIS",
                path,
                "Binary content detected in {} snapshot; structural parsing and line counts were skipped.".format(
                    " and ".join(binary_sides)
                ),
            ))
            continue
        if file_entry["language"] != "python":
            skipped += 1
            warnings.append(_warning("UNSUPPORTED_LANGUAGE", path, "Deterministic extraction currently supports Python (.py) only."))
            continue
        if (old is None and entry.old_oid is not None) or (
            new is None and entry.new_oid is not None
        ):
            skipped += 1
            continue

        parser_errors = (
            UnicodeDecodeError, ValueError, RuntimeError, OSError, TypeError
        )
        try:
            old_symbols, old_imports, _old_calls, _old_bindings, _old_rebindings = (
                _parse_python(old) if old is not None else ([], [], [], {}, [])
            )
        except parser_errors as error:
            warnings.append(_warning("PARSE_FAILURE", entry.old_path or path, "pre-change: {}: {}".format(type(error).__name__, error)))
            skipped += 1
            continue
        try:
            new_symbols, new_imports, new_calls, new_bindings, new_rebindings = (
                _parse_python(new) if new is not None else ([], [], [], {}, [])
            )
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
            if current is None:
                raise RuntimeError("symbol comparison produced no symbol")
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

        old_import_map = _keyed_imports(old_imports)
        new_import_map = _keyed_imports(new_imports)
        imported_call_targets = _imported_call_targets(
            new_import_map, new_rebindings
        )
        for import_key in sorted(set(old_import_map) | set(new_import_map)):
            before = old_import_map.get(import_key)
            after = new_import_map.get(import_key)
            item = after or before
            if item is None:
                raise RuntimeError("import comparison produced no import")
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
                "added"
                if before is None
                else "deleted"
                if after is None
                else "unchanged"
                if before.snippet == after.snippet
                else "modified"
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

        call_occurrences: Dict[Tuple[str, str], int] = {}
        for call in new_calls:
            target_qname = _resolve_call_target(
                call, new_map, new_bindings, imported_call_targets
            )
            if target_qname is None:
                continue
            source = (
                _symbol_id(output_path, call.caller)
                if call.caller is not None
                else "file::" + output_path
            )
            target = _symbol_id(output_path, target_qname)
            edge = (source, target)
            occurrence = call_occurrences.get(edge, 0)
            call_occurrences[edge] = occurrence + 1
            suffix = "" if occurrence == 0 else "#{}".format(occurrence)
            relationships.append(
                {
                    "id": "rel::{}->{}{}".format(source, target, suffix),
                    "kind": "calls",
                    "source_id": source,
                    "target_id": target,
                    "analysis_source": "structural",
                    "resolution_method": (
                        "import_grounded"
                        if target_qname.startswith("import::")
                        else "resolved"
                    ),
                    "confidence": None,
                    "evidence": [
                        {
                            "kind": "call_site",
                            "file": output_path,
                            "line_start": call.line,
                            "line_end": call.line,
                            "snippet": call.snippet,
                            "detail": _parser_provenance(entry.new_oid),
                        }
                    ],
                }
            )

    files.sort(key=lambda item: item["path"])
    symbols.sort(key=lambda item: item["id"])
    relationships.sort(key=lambda item: (item["id"], item["kind"]))
    warnings.sort(key=lambda item: (item.get("file", ""), item["code"], item.get("detail", "")))
    return {
        "schema_version": CURRENT_SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "wild_version": wild_version,
        "diff_ref": {
            "kind": "commit_range" if is_commit_range else "staged" if staged else "unstaged",
            "base_ref": (
                resolution.comparison_base_oid if is_commit_range else "HEAD" if staged else None
            ),
            "head_ref": resolution.head_oid if is_commit_range else None,
            "pathspecs": list(pathspecs or []), "repo_root": root,
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
