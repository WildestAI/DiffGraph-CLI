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
    """Convert a SymbolChange into a schema v2 ``symbols[]`` entry."""
    return {
        "id": symbol_id(sc.file_path, sc.qualified_name),
        "qualified_name": sc.qualified_name,
        "file": sc.file_path,
        "change_kind": sc.change_kind,
        "analysis_source": "structural",
        "evidence": [
            {
                "kind": "ast_parse",
                "location": {
                    "file": sc.file_path,
                    # Schema v2 line numbers are 1-indexed
                    "line_start": sc.start_line + 1,
                    "line_end": sc.end_line + 1,
                },
            }
        ],
    }


def build_import_relationship(
    source_file: str,
    imported_module: str,
    source_line: Optional[int] = None,
) -> Dict:
    """
    Build a schema v2 ``relationships[]`` entry for an import statement.

    The ``from`` side uses a file-scope synthetic symbol ID (schema v2 D1) to
    represent the module-level import, not a specific function.
    """
    entry: Dict = {
        "from": file_symbol_id(source_file),
        "to": imported_module,
        "kind": "imports",
        "analysis_source": "structural",
        "evidence": [
            {
                "kind": "import_statement",
                "location": {"file": source_file},
            }
        ],
    }
    if source_line is not None:
        entry["evidence"][0]["location"]["line_start"] = source_line + 1
    return entry


def build_schema_v2_output(
    *,
    symbol_changes: List[SymbolChange],
    import_relationships: List[Dict],          # already-built relationship dicts
    file_changes: List[Dict],                  # [{"path": str, "change_kind": str}]
    diff_ref: Dict,                            # {from, to, kind}
    wild_version: str,
    analysis_duration_ms: int,
    languages_detected: List[str],
) -> Dict:
    """
    Assemble a complete schema v2 JSON dict from structural analysis data.

    Invariants enforced here:
    - ``summary: null``  (no LLM → D2 from JSON-SCHEMA.md)
    - ``warnings: []``   (always present → D4)
    - ``metadata.privacy_tier: "local"``  (no network calls)
    - ``metadata.cloud_providers_used: []``

    Args:
        symbol_changes:        Output of compute_symbol_diff().
        import_relationships:  Output of build_import_relationship() calls.
        file_changes:          List of dicts with "path" and "change_kind".
        diff_ref:              {"from": str, "to": str, "kind": str}
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
        "diff_ref": diff_ref,
        "files": file_changes,
        "symbols": [build_symbol_entry(sc) for sc in symbol_changes],
        "relationships": import_relationships,
        "summary": None,           # D2: null when no LLM
        "warnings": [],            # D4: always present
        "metadata": {
            "privacy_tier": "local",
            "cloud_providers_used": [],
            "analysis_duration_ms": analysis_duration_ms,
            "languages_detected": sorted(languages_detected),
        },
    }
