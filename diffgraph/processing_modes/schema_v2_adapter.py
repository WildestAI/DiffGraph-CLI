"""
Schema v2 output adapter for the tree-sitter processor.

Converts ExtractedComponent + ExtractedDependency objects into the DiffGraph
v2.0 JSON schema format defined in diffgraph/schema/diffgraph-v2.schema.json.

Key invariants:
- Every claim carries  analysis_source="structural"  — deterministic, no LLM.
- Every symbol carries  change_kind  computed by comparing pre/post AST snapshots.
- No network calls are made by this module.

Consumed by TreeSitterProcessor.analyze_changes_v2().
"""

from datetime import datetime, timezone
from typing import List, Dict, Optional, Any
from dataclasses import dataclass


# ---------------------------------------------------------------------------
# Internal data types
# ---------------------------------------------------------------------------

@dataclass
class SymbolChange:
    """A symbol (function, class, method) with its change_kind."""
    qualified_name: str      # e.g. "ClassName.method_name" or "standalone_func"
    file_path: str
    component_type: str      # "function" | "method" | "container"
    parent: Optional[str]    # Class name for methods; None for top-level symbols
    change_kind: str         # "added" | "modified" | "deleted" | "unchanged"
    start_line: int          # 0-indexed AST start (converted to 1-indexed in output)
    end_line: int            # 0-indexed AST end


# ---------------------------------------------------------------------------
# Symbol identity
# ---------------------------------------------------------------------------

def qualified_name_for(component: Any) -> str:
    """
    Stable qualified name for a component.

    Rules:
    - standalone function / top-level class  →  ``func_name``
    - method                                 →  ``ClassName.method_name``
    """
    if component.parent:
        return f"{component.parent}.{component.name}"
    return component.name


def symbol_id(file_path: str, qname: str) -> str:
    """
    Schema v2 stable symbol ID.

    Format: ``sym::<file_path>::<qualified_name>``

    The ``sym::`` prefix allows consumers to distinguish symbol IDs from
    file-scope synthetic IDs (``sym::file::<path>``).
    """
    return f"sym::{file_path}::{qname}"


def file_id(file_path: str) -> str:
    """Schema v2 file ID. Format: ``file::<path>``"""
    return f"file::{file_path}"


def relationship_id(source_id: str, target_id: str, index: int = 0) -> str:
    """
    Stable deterministic ID for a relationship entry.

    Schema v2 format: ``rel::<source_id>-><target_id>``.
    Append ``#N`` for multi-edges (same source/target, different kind).
    """
    base = f"rel::{source_id}->{target_id}"
    return base if index == 0 else f"{base}#{index}"


def _component_type_to_kind(component_type: str) -> str:
    """
    Map internal component_type strings to schema v2 ``SymbolEntry.kind`` enum.

    Schema enum: function | class | method | import | constant | type_alias | module
    """
    mapping = {
        "function": "function",
        "method": "method",
        "container": "class",
    }
    return mapping.get(component_type, "function")


def file_symbol_id(file_path: str) -> str:
    """Synthetic ID for a file-scope import source (schema v2 D1)."""
    return f"sym::file::{file_path}"


# ---------------------------------------------------------------------------
# Symbol diff computation
# ---------------------------------------------------------------------------

def _content_slice(content: Optional[str], start_line: int, end_line: int) -> str:
    """Extract lines [start_line, end_line] (0-indexed, inclusive) from content."""
    if not content:
        return ""
    lines = content.splitlines()
    # Guard against stale line numbers
    start = max(0, start_line)
    end = min(len(lines) - 1, end_line)
    return "\n".join(lines[start:end + 1])


def compute_symbol_diff(
    pre_components: Optional[List[Any]],
    post_components: Optional[List[Any]],
    pre_content: Optional[str],
    post_content: Optional[str],
) -> List[SymbolChange]:
    """
    Compute per-symbol change_kind by comparing pre-change and post-change
    component lists extracted from the AST.

    Algorithm
    ---------
    1. Build lookup maps keyed by qualified_name for each snapshot.
    2. Union of keys → iterate.
    3. Present in post only        → ``"added"``
       Present in pre only         → ``"deleted"``
       Present in both:
         same content slice        → ``"unchanged"``
         different content slice   → ``"modified"``

    Why content slice comparison?
    AST line numbers shift when code is inserted above; comparing the
    *text* of the symbol body (not just the line range) correctly identifies
    symbols that moved without changing as ``"unchanged"``.

    Args:
        pre_components:  Components extracted from the pre-change version
                         (``git show HEAD:<path>``). None or [] for new files.
        post_components: Components extracted from the post-change version
                         (working tree / staged). None or [] for deleted files.
        pre_content:     Full file text of the pre-change version.
        post_content:    Full file text of the post-change version.

    Returns:
        List of SymbolChange, one per unique symbol across both snapshots.
    """
    pre_map: Dict[str, Any] = {
        qualified_name_for(c): c for c in (pre_components or [])
    }
    post_map: Dict[str, Any] = {
        qualified_name_for(c): c for c in (post_components or [])
    }

    all_keys = set(pre_map) | set(post_map)
    changes: List[SymbolChange] = []

    for key in sorted(all_keys):  # sorted for deterministic output order
        pre_comp = pre_map.get(key)
        post_comp = post_map.get(key)

        if post_comp and not pre_comp:
            change_kind = "added"
            comp = post_comp
        elif pre_comp and not post_comp:
            change_kind = "deleted"
            comp = pre_comp
        else:
            # Both snapshots have the symbol — compare content
            pre_text = _content_slice(pre_content, pre_comp.start_line or 0, pre_comp.end_line or 0)
            post_text = _content_slice(post_content, post_comp.start_line or 0, post_comp.end_line or 0)
            change_kind = "unchanged" if pre_text == post_text else "modified"
            comp = post_comp  # prefer post location for "where is it now"

        changes.append(SymbolChange(
            qualified_name=qualified_name_for(comp),
            file_path=comp.file_path or "",
            component_type=comp.component_type,
            parent=comp.parent,
            change_kind=change_kind,
            start_line=comp.start_line or 0,
            end_line=comp.end_line or 0,
        ))

    return changes


# ---------------------------------------------------------------------------
# Schema v2 output builder
# ---------------------------------------------------------------------------

def build_symbol_entry(sc: SymbolChange) -> Dict:
    """
    Convert a SymbolChange into a schema v2 ``symbols[]`` entry.

    Schema v2 required fields: id, name, file_id, kind, change_kind, analysis_source.
    Evidence is strongly recommended for structural symbols (ast_parse entry).
    """
    # ``name`` is the unqualified symbol name (e.g. ``check`` for ``RateLimiter.check``)
    unqualified_name = sc.qualified_name.split(".")[-1]
    # ``parent_id`` is the symbol ID of the containing class, or null for top-level symbols
    parent_id: Optional[str] = (
        symbol_id(sc.file_path, sc.parent)
        if sc.parent
        else None
    )
    # Evidence: flat fields directly on the entry (not nested under "location")
    evidence_entry: Dict = {
        "kind": "ast_parse",
        "file": sc.file_path,
        # Schema v2 line numbers are 1-indexed
        "line_start": sc.start_line + 1,
        "line_end": sc.end_line + 1,
    }
    # location: required fields are file, line_start, line_end
    location: Optional[Dict] = (
        {
            "file": sc.file_path,
            "line_start": sc.start_line + 1,
            "line_end": sc.end_line + 1,
        }
        if sc.change_kind != "deleted"
        else None
    )
    entry: Dict = {
        "id": symbol_id(sc.file_path, sc.qualified_name),
        "name": unqualified_name,
        "qualified_name": sc.qualified_name,
        "file_id": file_id(sc.file_path),
        "kind": _component_type_to_kind(sc.component_type),
        "parent_id": parent_id,
        "change_kind": sc.change_kind,
        "analysis_source": "structural",
        "location": location,
        "evidence": [evidence_entry],
    }
    return entry


def build_import_relationship(
    source_file: str,
    imported_module: str,
    source_line: Optional[int] = None,
) -> Dict:
    """
    Build a schema v2 ``relationships[]`` entry for an import statement.

    The ``source_id`` is a file-scope synthetic symbol ID (schema v2 D1) to
    represent the module-level import, not a specific function.
    The ``target_id`` is a synthetic module ID (``module::<name>``) — the
    target may not resolve to a known file within this analysis run.
    """
    src_id = file_symbol_id(source_file)
    # Synthetic target: module name may not resolve to a file in the diff;
    # use a stable namespaced ID so consumers can correlate across runs.
    tgt_id = f"module::{imported_module}"
    evidence_entry: Dict = {
        "kind": "import_statement",
        "file": source_file,
    }
    if source_line is not None:
        evidence_entry["line_start"] = source_line + 1
    return {
        "id": relationship_id(src_id, tgt_id),
        "kind": "imports",
        "source_id": src_id,
        "target_id": tgt_id,
        "analysis_source": "structural",
        "evidence": [evidence_entry],
    }


def _build_diff_ref(raw_diff_ref: Dict) -> Dict:
    """
    Convert the internal diff_ref format to the schema v2 format.

    Internal format (from analyze_changes_v2)::
        {"from": "HEAD", "to": "working_tree", "kind": "unstaged"}

    Schema v2 format (additionalProperties: false)::
        {"kind": "unstaged", "base_ref": "HEAD", "head_ref": null}

    Only ``kind`` is required. ``base_ref`` and ``head_ref`` are optional.
    """
    kind = raw_diff_ref.get("kind", "unstaged")
    result: Dict = {"kind": kind}

    # Map internal "from" → "base_ref", "to" → "head_ref"
    # For working-tree / staged diffs the head side is not a commit SHA.
    base = raw_diff_ref.get("from") or raw_diff_ref.get("base_ref")
    head = raw_diff_ref.get("to") or raw_diff_ref.get("head_ref")

    # Only include if it looks like a real ref (not "working_tree" / "index")
    _working_sentinels = {"working_tree", "index", "staged", None}
    if base and base not in _working_sentinels:
        result["base_ref"] = base
    if head and head not in _working_sentinels:
        result["head_ref"] = head

    if "pathspecs" in raw_diff_ref:
        result["pathspecs"] = raw_diff_ref["pathspecs"]
    if "repo_root" in raw_diff_ref:
        result["repo_root"] = raw_diff_ref["repo_root"]

    return result


def _build_file_entry(fc: Dict) -> Dict:
    """
    Build a schema v2 ``FileEntry`` dict from an internal file-change dict.

    Internal format::
        {"path": str, "change_kind": str}

    Schema v2 required fields: id, path, change_kind, analysis_source.
    """
    path = fc["path"]
    return {
        "id": file_id(path),
        "path": path,
        "change_kind": fc["change_kind"],
        "analysis_source": "structural",
    }


def build_schema_v2_output(
    *,
    symbol_changes: List[SymbolChange],
    import_relationships: List[Dict],          # already-built relationship dicts
    file_changes: List[Dict],                  # [{"path": str, "change_kind": str}]
    diff_ref: Dict,                            # {from|base_ref, to|head_ref, kind}
    wild_version: str,
    analysis_duration_ms: int,
    languages_detected: List[str],
) -> Dict:
    """
    Assemble a complete schema v2 JSON dict from structural analysis data.

    Invariants enforced here:
    - ``summary: null``  (no LLM → D2 from JSON-SCHEMA.md)
    - ``metadata.warnings: []``  (always present → D4; lives in metadata not top-level)
    - ``metadata.privacy_tier: "local"``  (no network calls)
    - ``metadata.cloud_providers_used: []``

    Args:
        symbol_changes:        Output of compute_symbol_diff().
        import_relationships:  Output of build_import_relationship() calls.
        file_changes:          List of dicts with "path" and "change_kind".
        diff_ref:              Internal diff ref dict; converted to schema v2 by this function.
        wild_version:          Semver string, e.g. "2.0.0".
        analysis_duration_ms:  Wall-clock ms for the full analysis run.
        languages_detected:    List of language slugs, e.g. ["python"].

    Returns:
        A dict that validates against diffgraph-v2.schema.json.
    """
    return {
        "schema_version": "2.0",
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "wild_version": wild_version,
        "diff_ref": _build_diff_ref(diff_ref),
        "files": [_build_file_entry(fc) for fc in file_changes],
        "symbols": [build_symbol_entry(sc) for sc in symbol_changes],
        "relationships": import_relationships,
        "summary": None,           # D2: null when no LLM
        "metadata": {
            "privacy_tier": "local",
            "cloud_providers_used": [],
            "analysis_duration_ms": analysis_duration_ms,
            "languages_detected": sorted(languages_detected),
            "warnings": [],        # D4: always present; in metadata not top-level
        },
    }
