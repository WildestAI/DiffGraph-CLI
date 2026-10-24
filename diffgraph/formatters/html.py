"""Deterministic, offline HTML adapter for canonical DiffGraph artifacts.

The interactive view is deliberately a small inline SVG renderer instead of a
runtime dependency.  It consumes the same embedded, validated artifact as the
textual report and performs no repository reads, structural analysis, AI calls,
or network access.
"""
from __future__ import annotations

import base64
import hashlib
import html
import json
import os
import tempfile
import textwrap
from pathlib import Path

from diffgraph.contract import ValidatedArtifact


def _text(value: object) -> str:
    """Escape one artifact value for HTML text content."""
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    return html.escape(str(value), quote=True)


def _json(value: object) -> str:
    """Render stable escaped JSON for human inspection."""
    return html.escape(json.dumps(value, indent=2, sort_keys=True), quote=True)


def _embedded_json(value: object) -> str:
    """Embed JSON without allowing artifact strings to terminate the script tag."""
    return (
        json.dumps(value, indent=2, sort_keys=True)
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
    )


# This code is static: artifact values remain inert JSON until it is parsed, and
# all details are assigned through textContent (never innerHTML).  Its CSP hash
# is calculated at render time so the report can permit exactly this script.
_INTERACTIVE_SCRIPT = textwrap.dedent(
    """\
    (() => {
      'use strict';
      const NS = 'http://www.w3.org/2000/svg';
      const source = document.getElementById('diffgraph-artifact');
      const host = document.getElementById('diffgraph-graph');
      if (!source || !host) return;
      let artifact;
      try { artifact = JSON.parse(source.textContent); } catch (_) { return; }

      const svg = document.createElementNS(NS, 'svg');
      svg.setAttribute('viewBox', '0 0 1200 720');
      svg.setAttribute('role', 'img');
      svg.setAttribute('aria-label', 'Interactive DiffGraph visualization');
      svg.setAttribute('tabindex', '0');
      const title = document.createElementNS(NS, 'title');
      title.textContent = 'Interactive DiffGraph visualization';
      svg.appendChild(title);
      const viewport = document.createElementNS(NS, 'g');
      svg.appendChild(viewport);
      host.appendChild(svg);

      const tooltip = document.createElement('pre');
      tooltip.className = 'graph-tooltip';
      tooltip.hidden = true;
      host.appendChild(tooltip);
      const state = { scale: 1, x: 0, y: 0, dragging: false, collapsed: new Set() };
      // Colors live in the stylesheet so both light and dark themes apply.
      const changeKinds = new Set(['added', 'deleted', 'modified', 'unchanged', 'untracked', 'renamed']);
      const changeClass = (kind) => `ck-${changeKinds.has(kind) ? kind : 'unchanged'}`;
      const svgEl = (name, attrs = {}) => {
        const node = document.createElementNS(NS, name);
        Object.entries(attrs).forEach(([key, value]) => node.setAttribute(key, String(value)));
        return node;
      };
      const addText = (parent, value, x, y, cls) => {
        const node = svgEl('text', { x, y, class: cls || '' });
        node.textContent = value == null ? '' : String(value);
        parent.appendChild(node);
        return node;
      };
      const details = (value, event) => {
        tooltip.textContent = JSON.stringify(value, null, 2);
        tooltip.hidden = false;
        const rect = host.getBoundingClientRect();
        tooltip.style.left = Math.max(8, event.clientX - rect.left + 12) + 'px';
        tooltip.style.top = Math.max(8, event.clientY - rect.top + 12) + 'px';
      };
      const hideDetails = () => { tooltip.hidden = true; };
      const attachDetails = (node, value) => {
        node.addEventListener('pointerenter', (event) => details(value, event));
        node.addEventListener('pointermove', (event) => details(value, event));
        node.addEventListener('pointerleave', hideDetails);
        node.addEventListener('focus', (event) => details(value, event));
        node.addEventListener('blur', hideDetails);
      };
      const setTransform = () => viewport.setAttribute('transform', `translate(${state.x} ${state.y}) scale(${state.scale})`);
      const draw = () => {
        viewport.replaceChildren();
        const files = [...(artifact.files || [])].sort((a, b) => a.id.localeCompare(b.id));
        const symbols = [...(artifact.symbols || [])].sort((a, b) => a.id.localeCompare(b.id));
        const modules = new Map();
        files.forEach((file) => {
          const bits = String(file.path || file.id).split('/');
          const module = bits.length > 1 ? bits.slice(0, -1).join('/') : '(root)';
          if (!modules.has(module)) modules.set(module, []);
          modules.get(module).push(file);
        });
        const positions = new Map();
        let y = 44;
        [...modules.entries()].sort(([a], [b]) => a.localeCompare(b)).forEach(([module, group]) => {
          const moduleY = y;
          const moduleGroup = svgEl('g', { class: 'module-container' });
          viewport.appendChild(moduleGroup);
          addText(moduleGroup, `module: ${module}`, 34, y + 22, 'module-label');
          y += 34;
          group.forEach((file) => {
            const fileSymbols = symbols.filter((symbol) => symbol.file_id === file.id);
            const collapsed = state.collapsed.has(file.id);
            const height = collapsed ? 56 : Math.max(72, 44 + fileSymbols.length * 38);
            const groupNode = svgEl('g', { class: 'file-container', tabindex: '0', role: 'button', 'aria-expanded': String(!collapsed), 'aria-label': `${collapsed ? 'Expand' : 'Collapse'} ${file.path || file.id}` });
            const rect = svgEl('rect', { x: 48, y, width: 1080, height, rx: 10, class: `file-box ${changeClass(file.change_kind)}` });
            groupNode.appendChild(rect);
            addText(groupNode, collapsed ? '▶' : '▼', 64, y + 29, 'toggle');
            addText(groupNode, file.path || file.id, 88, y + 29, 'file-label');
            addText(groupNode, file.change_kind || 'unknown', 1014, y + 29, 'change-label');
            attachDetails(groupNode, file);
            const toggle = () => { if (state.collapsed.has(file.id)) state.collapsed.delete(file.id); else state.collapsed.add(file.id); draw(); };
            groupNode.addEventListener('click', toggle);
            groupNode.addEventListener('keydown', (event) => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); toggle(); } });
            viewport.appendChild(groupNode);
            positions.set(file.id, { x: 92, y: y + 29, visible: true });
            if (!collapsed) fileSymbols.forEach((symbol, index) => {
              const sy = y + 48 + index * 38;
              const node = svgEl('g', { class: 'symbol-node', tabindex: '0', role: 'img', 'aria-label': `${symbol.kind || 'symbol'} ${symbol.qualified_name || symbol.name || symbol.id}` });
              node.appendChild(svgEl('rect', { x: 80, y: sy, width: 620, height: 28, rx: 7, class: `symbol-box ${changeClass(symbol.change_kind)}` }));
              addText(node, `${symbol.kind || 'symbol'}: ${symbol.qualified_name || symbol.name || symbol.id}`, 94, sy + 19, 'symbol-label');
              node.appendChild(svgEl('circle', { cx: 678, cy: sy + 14, r: 5, class: `change-dot ${changeClass(symbol.change_kind)}` }));
              attachDetails(node, symbol);
              viewport.appendChild(node);
              positions.set(symbol.id, { x: 390, y: sy + 14, visible: true });
            });
            if (collapsed) fileSymbols.forEach((symbol) => positions.set(symbol.id, { visible: false }));
            y += height + 14;
          });
          const moduleHeight = y - moduleY - 14;
          const outline = svgEl('rect', { x: 24, y: moduleY, width: 1128, height: moduleHeight, rx: 14, class: 'module-outline' });
          moduleGroup.insertBefore(outline, moduleGroup.firstChild);
          y += 18;
        });
        const edges = svgEl('g', { class: 'relationship-edges' });
        (artifact.relationships || []).slice().sort((a, b) => a.id.localeCompare(b.id)).forEach((relationship) => {
          const source = positions.get(relationship.source_id);
          const target = positions.get(relationship.target_id);
          if (!source || !target || !source.visible || !target.visible) return;
          const edge = svgEl('line', { x1: source.x, y1: source.y, x2: target.x, y2: target.y, class: 'edge-line', 'marker-end': 'url(#arrow)' });
          attachDetails(edge, relationship);
          edges.appendChild(edge);
        });
        const defs = svgEl('defs');
        const marker = svgEl('marker', { id: 'arrow', markerWidth: 8, markerHeight: 8, refX: 7, refY: 3, orient: 'auto' });
        marker.appendChild(svgEl('path', { d: 'M0,0 L0,6 L8,3 z', class: 'edge-arrow' }));
        defs.appendChild(marker);
        edges.insertBefore(defs, edges.firstChild);
        viewport.insertBefore(edges, viewport.firstChild);
        setTransform();
      };
      svg.addEventListener('wheel', (event) => { event.preventDefault(); const factor = event.deltaY < 0 ? 1.12 : 0.89; state.scale = Math.max(0.35, Math.min(3, state.scale * factor)); setTransform(); }, { passive: false });
      svg.addEventListener('pointerdown', (event) => { if (event.target === svg) { state.dragging = true; state.startX = event.clientX - state.x; state.startY = event.clientY - state.y; svg.setPointerCapture(event.pointerId); } });
      svg.addEventListener('pointermove', (event) => { if (state.dragging) { state.x = event.clientX - state.startX; state.y = event.clientY - state.startY; setTransform(); } });
      svg.addEventListener('pointerup', () => { state.dragging = false; });
      draw();
    })();
    """
).strip()


def _script_csp_hash(script: str) -> str:
    digest = hashlib.sha256(script.encode("utf-8")).digest()
    return base64.b64encode(digest).decode("ascii")


class HtmlFormatter:
    """Render one already-validated DiffGraph artifact as self-contained HTML."""

    def __init__(self, artifact: ValidatedArtifact):
        if not isinstance(artifact, ValidatedArtifact):
            raise TypeError("HtmlFormatter requires a ValidatedArtifact")
        self.artifact = artifact
        self.dg = artifact.value

    def render(self) -> str:
        """Return deterministic HTML containing only canonical artifact data."""
        files = sorted(self.dg["files"], key=lambda item: item["id"])
        symbols = sorted(self.dg["symbols"], key=lambda item: item["id"])
        relationships = sorted(self.dg["relationships"], key=lambda item: item["id"])
        metadata = self.dg["metadata"]
        warnings = metadata.get("warnings", [])

        self._validate_unique_object_ids(files, symbols)
        anchors = {item["id"]: self._object_anchor(item["id"]) for item in (*files, *symbols)}
        file_items = self._object_items(files, "No files in the selected snapshot.", anchors)
        symbol_items = self._object_items(symbols, "No symbols in the artifact.", anchors)
        relationship_items = self._relationship_items(relationships, anchors)
        warning_items = "".join(f"<li><pre>{_json(warning)}</pre></li>" for warning in warnings) or "<li>None</li>"
        summary = f"<h3>Summary</h3><pre>{_json(self.dg['summary'])}</pre>" if "summary" in self.dg else ""
        script_hash = _script_csp_hash(_INTERACTIVE_SCRIPT)

        return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src 'sha256-{script_hash}'; style-src 'unsafe-inline'; img-src data:; base-uri 'none'; form-action 'none'">
  <title>DiffGraph Report</title>
  <style>
    :root {{ color-scheme: light dark; font-family: system-ui, sans-serif; }}
    body {{ max-width: 1100px; margin: auto; padding: 2rem; line-height: 1.45; }}
    section {{ margin: 2rem 0; }}
    article, .panel {{ border: 1px solid #8886; border-radius: .6rem; padding: 1rem; margin: .75rem 0; }}
    code, pre {{ font-family: ui-monospace, SFMono-Regular, Consolas, monospace; }}
    pre {{ overflow-x: auto; white-space: pre-wrap; overflow-wrap: anywhere; }}
    .edge {{ display: grid; grid-template-columns: minmax(0,1fr) auto minmax(0,1fr); gap: .75rem; align-items: center; }}
    .edge code {{ overflow-wrap: anywhere; }}
    .kind {{ border: 1px solid #8888; border-radius: 1rem; padding: .15rem .55rem; }}
    dt {{ font-weight: 700; }} dd {{ margin-bottom: .5rem; }}
    :root {{
      --graph-bg: #f8fafc; --node-bg: #ffffff; --symbol-bg: #f2f4f7;
      --text-strong: #101828; --text: #344054; --text-muted: #475467;
      --edge: #475467; --outline: #98a2b3; --focus: #101828;
      --tooltip-bg: #101828; --tooltip-text: #f9fafb; --tooltip-border: #667085;
      --ck-added: #18794e; --ck-deleted: #b42318; --ck-modified: #175cd3;
      --ck-unchanged: #667085; --ck-untracked: #7a5af8; --ck-renamed: #b54708;
    }}
    @media (prefers-color-scheme: dark) {{
      :root {{
        --graph-bg: #0c111d; --node-bg: #161b26; --symbol-bg: #1f242f;
        --text-strong: #f5f5f6; --text: #cecfd2; --text-muted: #94969c;
        --edge: #94969c; --outline: #61646c; --focus: #f5f5f6;
        --tooltip-bg: #1f242f; --tooltip-text: #f5f5f6; --tooltip-border: #61646c;
        --ck-added: #47cd89; --ck-deleted: #f97066; --ck-modified: #84adff;
        --ck-unchanged: #94969c; --ck-untracked: #bdb4fe; --ck-renamed: #fdb022;
      }}
    }}
    #diffgraph-graph {{ position: relative; height: 46rem; min-height: 28rem; overflow: hidden; border: 1px solid #8886; border-radius: .6rem; background: var(--graph-bg); }}
    #diffgraph-graph svg {{ display: block; width: 100%; height: 100%; cursor: grab; }}
    #diffgraph-graph svg:active {{ cursor: grabbing; }}
    .module-label {{ font-size: 16px; font-weight: 700; fill: var(--text); }}
    .file-label {{ font-size: 16px; font-weight: 700; fill: var(--text-strong); }}
    .symbol-label {{ font-size: 14px; fill: var(--text); }}
    .change-label {{ font-size: 12px; fill: var(--text-muted); }}
    .toggle {{ font-size: 15px; fill: var(--text); }}
    .module-outline {{ fill: none; stroke: var(--outline); stroke-dasharray: 6 5; }}
    .file-box {{ fill: var(--node-bg); stroke: var(--ck-unchanged); stroke-width: 3; }}
    .symbol-box {{ fill: var(--symbol-bg); stroke: var(--ck-unchanged); stroke-width: 1; }}
    .change-dot {{ fill: var(--ck-unchanged); }}
    .ck-added {{ stroke: var(--ck-added); }} .change-dot.ck-added {{ fill: var(--ck-added); }}
    .ck-deleted {{ stroke: var(--ck-deleted); }} .change-dot.ck-deleted {{ fill: var(--ck-deleted); }}
    .ck-modified {{ stroke: var(--ck-modified); }} .change-dot.ck-modified {{ fill: var(--ck-modified); }}
    .ck-unchanged {{ stroke: var(--ck-unchanged); }} .change-dot.ck-unchanged {{ fill: var(--ck-unchanged); }}
    .ck-untracked {{ stroke: var(--ck-untracked); }} .change-dot.ck-untracked {{ fill: var(--ck-untracked); }}
    .ck-renamed {{ stroke: var(--ck-renamed); }} .change-dot.ck-renamed {{ fill: var(--ck-renamed); }}
    .change-dot {{ stroke: none; }}
    .edge-line {{ stroke: var(--edge); stroke-width: 1.5; pointer-events: stroke; }}
    .edge-line:hover {{ stroke: var(--focus); stroke-width: 2.5; }}
    .edge-arrow {{ fill: var(--edge); }}
    .file-container, .symbol-node {{ cursor: pointer; outline: none; }}
    .file-container:hover > rect, .symbol-node:hover > rect {{ stroke-width: 3; }}
    .file-container:focus > rect, .symbol-node:focus > rect {{ stroke: var(--focus); stroke-width: 3; }}
    .graph-tooltip {{ position: absolute; z-index: 2; max-width: min(34rem, 80%); max-height: 18rem; margin: 0; padding: .65rem; overflow: auto; border: 1px solid var(--tooltip-border); border-radius: .4rem; background: var(--tooltip-bg); color: var(--tooltip-text); font-size: .75rem; pointer-events: none; }}
  </style>
</head>
<body>
  <h1>DiffGraph Report</h1>
  <section aria-labelledby="graph-heading">
    <h2 id="graph-heading">Interactive graph</h2>
    <p class="panel">Scroll to zoom, drag blank space to pan, and select a file container to expand or collapse its canonical symbols. Hover or focus an item for its canonical details.</p>
    <div id="diffgraph-graph"></div>
  </section>
  <section aria-labelledby="artifact-heading">
    <h2 id="artifact-heading">Artifact</h2>
    <dl class="panel">
      <dt>Schema version</dt><dd><code>{_text(self.dg['schema_version'])}</code></dd>
      <dt>Generated at</dt><dd><code>{_text(self.dg['generated_at'])}</code></dd>
      <dt>wild version</dt><dd><code>{_text(self.dg['wild_version'])}</code></dd>
    </dl>
    <h3>Diff reference</h3><pre>{_json(self.dg['diff_ref'])}</pre>
    {summary}
  </section>
  <section aria-labelledby="files-heading"><h2 id="files-heading">Files</h2>{file_items}</section>
  <section aria-labelledby="symbols-heading"><h2 id="symbols-heading">Symbols</h2>{symbol_items}</section>
  <section aria-labelledby="topology-heading">
    <h2 id="topology-heading">Deterministic topology</h2>
    {relationship_items}
  </section>
  <section aria-labelledby="warnings-heading"><h2 id="warnings-heading">Warnings</h2><ul>{warning_items}</ul></section>
  <section aria-labelledby="metadata-heading"><h2 id="metadata-heading">Metadata</h2><pre>{_json(metadata)}</pre></section>
  <script type="application/json" id="diffgraph-artifact">{_embedded_json(self.dg)}</script>
  <script>{_INTERACTIVE_SCRIPT}</script>
</body>
</html>
"""

    @staticmethod
    def _object_anchor(item_id: str) -> str:
        """Return a stable, safe fragment target for a canonical object ID."""
        return "object-{}".format(hashlib.sha256(item_id.encode("utf-8")).hexdigest())

    @staticmethod
    def _validate_unique_object_ids(files: list[dict], symbols: list[dict]) -> None:
        """Reject duplicate object IDs before rendering ambiguous anchor targets."""
        object_ids = [item["id"] for item in (*files, *symbols)]
        duplicate_ids = sorted(item_id for item_id in set(object_ids) if object_ids.count(item_id) > 1)
        if duplicate_ids:
            raise ValueError("DiffGraph HTML rendering requires unique file and symbol IDs; duplicates: " + ", ".join(duplicate_ids))

    @staticmethod
    def _object_items(items: list[dict], empty_message: str, anchors: dict[str, str]) -> str:
        if not items:
            return f'<p class="panel">{html.escape(empty_message)}</p>'
        return "".join(
            f'<article id="{anchors[item["id"]]}"><h3><code>{_text(item["id"])}</code></h3><pre>{_json(item)}</pre></article>'
            for item in items
        )

    @staticmethod
    def _relationship_items(relationships: list[dict], anchors: dict[str, str]) -> str:
        if not relationships:
            return '<p class="panel">No relationships in the artifact.</p>'

        def endpoint(item_id: str) -> str:
            anchor = anchors.get(item_id)
            text = _text(item_id)
            if anchor is None:
                return f"<code>{text}</code>"
            return f'<a href="#{anchor}" aria-label="Jump to {text}"><code>{text}</code></a>'

        return "".join(
            "<article>"
            f'<div class="edge">{endpoint(item["source_id"])}<span class="kind">{_text(item["kind"])}</span>{endpoint(item["target_id"])}</div>'
            f"<pre>{_json(item)}</pre>"
            "</article>"
            for item in relationships
        )

    def write(self, destination: Path) -> Path:
        """Atomically write a complete report and return its absolute path."""
        rendered = self.render()
        temporary_path = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=destination.parent, prefix=f".{destination.name}.", suffix=".tmp", delete=False) as temporary:
                temporary_path = Path(temporary.name)
                temporary.write(rendered)
            os.replace(temporary_path, destination)
        except BaseException:
            if temporary_path is not None:
                try:
                    temporary_path.unlink()
                except FileNotFoundError:
                    pass
            raise
        return destination.absolute()
