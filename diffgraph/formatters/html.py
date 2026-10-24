"""Deterministic, offline HTML adapter for canonical DiffGraph artifacts.

The report is the interactive graph: a small inline SVG renderer (no runtime
dependency) fills the window, a top bar summarizes the snapshot, and a details
panel shows the selected node's evidence. The validated artifact is embedded
as inert JSON for the script; it is not rendered as text (use
``--format json`` for the raw artifact). The renderer performs no repository
reads, structural analysis, AI calls, or network access.
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
from diffgraph.formatters.common import warning_lines


def _text(value: object) -> str:
    """Escape one artifact value for HTML text content."""
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    return html.escape(str(value), quote=True)


def _embedded_json(value: object) -> str:
    """Embed compact JSON without allowing artifact strings to terminate the script tag."""
    return (
        json.dumps(value, sort_keys=True, separators=(",", ":"))
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
    )


def _plural(count: int, noun: str) -> str:
    return f"{count} {noun}{'' if count == 1 else 's'}"


def _short_ref(value: object) -> str:
    text = str(value or "")
    return text[:12] if len(text) in (40, 64) else text


def _diff_label(diff_ref: dict) -> str:
    """Human label for the analyzed snapshot (e.g. ``main...feature``)."""
    kind = diff_ref.get("kind")
    if kind == "commit_range":
        base = diff_ref.get("requested_base_ref") or _short_ref(diff_ref.get("base_ref"))
        head = diff_ref.get("requested_head_ref") or _short_ref(diff_ref.get("head_ref"))
        separator = "..." if diff_ref.get("comparison_mode") == "three_dot" else ".."
        label = f"{base}{separator}{head}"
    else:
        label = {"unstaged": "Unstaged changes", "staged": "Staged changes"}.get(kind, str(kind))
    pathspecs = diff_ref.get("pathspecs") or []
    if pathspecs:
        label += " — " + ", ".join(str(item) for item in pathspecs)
    return label


# This code is static: artifact values remain inert JSON until it is parsed, and
# all text is assigned through textContent (never innerHTML).  Its CSP hash is
# calculated at render time so the report can permit exactly this script.
_INTERACTIVE_SCRIPT = textwrap.dedent(
    """\
    (() => {
      'use strict';
      const NS = 'http://www.w3.org/2000/svg';
      const source = document.getElementById('diffgraph-artifact');
      const host = document.getElementById('diffgraph-graph');
      const layout = document.getElementById('diffgraph-layout');
      const panel = document.getElementById('diffgraph-details');
      if (!source || !host || !panel || !layout) return;
      let artifact;
      try { artifact = JSON.parse(source.textContent); } catch (_) { return; }
      const files = [...(artifact.files || [])].sort((a, b) => a.id.localeCompare(b.id));
      const symbols = [...(artifact.symbols || [])].sort((a, b) => a.id.localeCompare(b.id));
      const relationships = [...(artifact.relationships || [])].sort((a, b) => a.id.localeCompare(b.id));
      if (!files.length) return;

      const svg = document.createElementNS(NS, 'svg');
      svg.setAttribute('viewBox', '0 0 1200 720');
      svg.setAttribute('preserveAspectRatio', 'xMinYMin meet');
      svg.setAttribute('role', 'img');
      svg.setAttribute('aria-label', 'Interactive DiffGraph visualization');
      svg.setAttribute('tabindex', '0');
      const title = document.createElementNS(NS, 'title');
      title.textContent = 'Interactive DiffGraph visualization';
      svg.appendChild(title);
      const viewport = document.createElementNS(NS, 'g');
      svg.appendChild(viewport);
      host.appendChild(svg);

      const tooltip = document.createElement('div');
      tooltip.className = 'graph-tooltip';
      tooltip.hidden = true;
      host.appendChild(tooltip);
      const state = { scale: 1, x: 0, y: 0, dragging: false, collapsed: new Set(), expanded: new Set(), selected: null };
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
      const htmlEl = (tag, cls, text) => {
        const node = document.createElement(tag);
        if (cls) node.className = cls;
        if (text != null) node.textContent = String(text);
        return node;
      };
      // Optional inferred summary: untrusted model text, only ever set via textContent.
      const summaryOf = (item) => {
        const summary = item && item.summary;
        if (!summary || typeof summary.text !== 'string' || !summary.text.trim()) return null;
        const inference = (summary.evidence || []).find((entry) => entry && entry.kind === 'llm_inference');
        return { text: summary.text.trim().replace(/\\s+/g, ' '), model: inference && inference.model ? String(inference.model) : null };
      };
      const truncate = (value, max) => (value.length > max ? value.slice(0, max - 1) + '…' : value);
      const summaryLine = (summary, max) => truncate(`AI · ${summary.text}`, max);

      const fileIndex = new Map(files.map((file) => [file.id, file]));
      const symbolIndex = new Map(symbols.map((symbol) => [symbol.id, symbol]));
      const nameOf = (id) => {
        const file = fileIndex.get(id);
        if (file) return file.path || id;
        const symbol = symbolIndex.get(id);
        if (symbol) return symbol.qualified_name || symbol.name || id;
        return id;
      };

      // Default view: changed symbols plus their containing declarations.
      // Call neighbours are not shown by default: one hub function can call,
      // or be called by, dozens of unchanged symbols. They are counted in the
      // per-file toggle so the change's dependency graph stays one click away.
      const changedSymbolIds = new Set(symbols.filter((symbol) => symbol.change_kind && symbol.change_kind !== 'unchanged').map((symbol) => symbol.id));
      const relevantSymbolIds = new Set(changedSymbolIds);
      [...changedSymbolIds].forEach((id) => {
        let parent = symbolIndex.get(id).parent_id;
        while (parent && symbolIndex.has(parent) && !relevantSymbolIds.has(parent)) { relevantSymbolIds.add(parent); parent = symbolIndex.get(parent).parent_id; }
      });
      const callNeighbourIds = new Set();
      relationships.forEach((relationship) => {
        if (relationship.kind !== 'calls') return;
        if (changedSymbolIds.has(relationship.source_id)) callNeighbourIds.add(relationship.target_id);
        if (changedSymbolIds.has(relationship.target_id)) callNeighbourIds.add(relationship.source_id);
      });

      // ---- Hover: a short label; full details live in the panel. ----
      const showTooltip = (text, event) => {
        tooltip.textContent = text;
        tooltip.hidden = false;
        const rect = host.getBoundingClientRect();
        tooltip.style.left = Math.max(8, event.clientX - rect.left + 12) + 'px';
        tooltip.style.top = Math.max(8, event.clientY - rect.top + 12) + 'px';
      };
      const hideTooltip = () => { tooltip.hidden = true; };
      const hoverText = (item) => {
        if (item.source_id) return `${item.kind}: ${nameOf(item.source_id)} → ${nameOf(item.target_id)}`;
        const summary = summaryOf(item);
        const head = `${item.path ? 'file' : item.kind || 'symbol'} · ${nameOf(item.id)} · ${item.change_kind || 'unknown'}`;
        return summary ? `${head}\\n${truncate(summary.text, 240)}` : head;
      };

      // ---- Details panel ----
      const help = panel.querySelector('.details-help');
      const body = panel.querySelector('.details-body');
      const reveal = (id) => {
        const symbol = symbolIndex.get(id);
        const fileId = symbol ? symbol.file_id : id;
        state.collapsed.delete(fileId);
        if (symbol && !relevantSymbolIds.has(id)) state.expanded.add(fileId);
      };
      const linkTo = (id) => {
        if (!fileIndex.has(id) && !symbolIndex.has(id)) return htmlEl('code', null, id);
        const button = htmlEl('button', 'node-link', nameOf(id));
        button.type = 'button';
        button.title = nameOf(id);
        button.addEventListener('click', () => select(id));
        return button;
      };
      const section = (heading, ids) => {
        const unique = [...new Set(ids)];
        if (!unique.length) return null;
        const wrapper = htmlEl('section', 'details-section');
        wrapper.appendChild(htmlEl('h3', null, `${heading} (${unique.length})`));
        const list = htmlEl('ul');
        const fill = (ids) => list.replaceChildren(...ids.map((id) => { const item = htmlEl('li'); item.appendChild(linkTo(id)); return item; }));
        const limit = 12;
        fill(unique.slice(0, limit));
        wrapper.appendChild(list);
        if (unique.length > limit) {
          const more = htmlEl('button', 'show-all', `Show all ${unique.length}`);
          more.type = 'button';
          more.addEventListener('click', () => { fill(unique); more.remove(); });
          wrapper.appendChild(more);
        }
        return wrapper;
      };
      const evidenceSection = (evidence) => {
        const entries = (evidence || []).filter((entry) => entry && entry.kind !== 'structural_basis' && entry.kind !== 'llm_inference');
        if (!entries.length) return null;
        const wrapper = htmlEl('section', 'details-section');
        wrapper.appendChild(htmlEl('h3', null, 'Evidence'));
        entries.forEach((entry) => {
          const lines = entry.line_start ? `:${entry.line_start}${entry.line_end && entry.line_end !== entry.line_start ? `-${entry.line_end}` : ''}` : '';
          wrapper.appendChild(htmlEl('p', 'evidence-kind', `${entry.kind}${entry.file ? ` · ${entry.file}${lines}` : ''}`));
          if (entry.snippet) wrapper.appendChild(htmlEl('pre', 'evidence-snippet', entry.snippet));
        });
        return wrapper;
      };
      const summaryBlock = (item) => {
        const summary = summaryOf(item);
        if (!summary) return null;
        const block = htmlEl('div', 'ai-summary');
        block.appendChild(htmlEl('span', 'ai-badge', 'AI'));
        block.appendChild(htmlEl('span', 'ai-model', summary.model || 'summary'));
        block.appendChild(htmlEl('p', null, summary.text));
        return block;
      };
      const header = (kindLabel, name, changeKind) => {
        const wrapper = htmlEl('header', 'details-header');
        wrapper.appendChild(htmlEl('p', 'details-kind', kindLabel));
        wrapper.appendChild(htmlEl('h2', null, name));
        if (changeKind) wrapper.appendChild(htmlEl('span', `badge ${changeClass(changeKind)}`, changeKind));
        return wrapper;
      };
      const incoming = (id, kind) => relationships.filter((r) => r.target_id === id && r.kind === kind).map((r) => r.source_id);
      const outgoing = (id, kind) => relationships.filter((r) => r.source_id === id && r.kind === kind).map((r) => r.target_id);
      const renderDetails = () => {
        const selected = state.selected;
        if (!selected) { help.hidden = false; body.hidden = true; body.replaceChildren(); return; }
        const parts = [];
        if (selected.type === 'relationship') {
          const rel = selected.value;
          parts.push(header('relationship', rel.kind, null));
          const ends = htmlEl('p', 'details-edge');
          ends.append(linkTo(rel.source_id), htmlEl('span', 'edge-arrow-text', ' → '), linkTo(rel.target_id));
          parts.push(ends);
          if (rel.label) parts.push(htmlEl('p', 'details-meta', rel.label));
          if (rel.resolution_method) parts.push(htmlEl('p', 'details-meta', `resolution: ${rel.resolution_method}`));
          parts.push(evidenceSection(rel.evidence));
        } else if (fileIndex.has(selected.id)) {
          const file = fileIndex.get(selected.id);
          parts.push(header('file', file.path || file.id, file.change_kind));
          const stats = [];
          if (file.old_path && file.old_path !== file.path) stats.push(`renamed from ${file.old_path}`);
          if (file.language) stats.push(file.language);
          if (file.lines_added != null || file.lines_removed != null) stats.push(`+${file.lines_added || 0} / -${file.lines_removed || 0}`);
          const fileSymbols = symbols.filter((symbol) => symbol.file_id === file.id);
          stats.push(`${fileSymbols.filter((symbol) => changedSymbolIds.has(symbol.id)).length} of ${fileSymbols.length} symbols changed`);
          parts.push(htmlEl('p', 'details-meta', stats.join(' · ')));
          parts.push(summaryBlock(file));
          parts.push(section('Changed symbols', fileSymbols.filter((symbol) => changedSymbolIds.has(symbol.id)).map((symbol) => symbol.id)));
          parts.push(section('Imported by', incoming(file.id, 'imports').concat(...fileSymbols.map((symbol) => incoming(symbol.id, 'imports'))).filter((id) => id !== file.id)));
          parts.push(section('Imports', outgoing(file.id, 'imports').filter((id) => fileIndex.has(id) || (symbolIndex.has(id) && symbolIndex.get(id).file_id !== file.id))));
        } else {
          const symbol = symbolIndex.get(selected.id);
          parts.push(header(symbol.kind || 'symbol', symbol.qualified_name || symbol.name || symbol.id, symbol.change_kind));
          const location = symbol.location ? `${symbol.location.file}:${symbol.location.line_start}-${symbol.location.line_end}` : nameOf(symbol.file_id);
          parts.push(htmlEl('p', 'details-meta', location));
          parts.push(summaryBlock(symbol));
          if (symbol.parent_id) parts.push(section('Defined in', [symbol.parent_id]));
          parts.push(section('Calls', outgoing(symbol.id, 'calls')));
          parts.push(section('Called by', incoming(symbol.id, 'calls')));
          parts.push(section('Imported by', incoming(symbol.id, 'imports').filter((id) => id !== symbol.file_id)));
          parts.push(evidenceSection(symbol.evidence));
        }
        body.replaceChildren(...parts.filter(Boolean));
        help.hidden = true;
        body.hidden = false;
        layout.classList.remove('details-closed');
      };
      const select = (id) => {
        reveal(id);
        state.selected = { type: 'node', id };
        renderDetails();
        draw();
      };
      const selectRelationship = (relationship) => {
        state.selected = { type: 'relationship', id: relationship.id, value: relationship };
        renderDetails();
        draw();
      };
      const clearSelection = () => { state.selected = null; renderDetails(); draw(); };
      const closeButton = panel.querySelector('.details-close');
      if (closeButton) closeButton.addEventListener('click', () => { layout.classList.add('details-closed'); clearSelection(); });
      document.addEventListener('keydown', (event) => { if (event.key === 'Escape' && state.selected) clearSelection(); });

      const interactive = (node, item, onSelect) => {
        node.addEventListener('pointerenter', (event) => showTooltip(hoverText(item), event));
        node.addEventListener('pointermove', (event) => showTooltip(hoverText(item), event));
        node.addEventListener('pointerleave', hideTooltip);
        node.addEventListener('click', (event) => { event.stopPropagation(); onSelect(); });
        node.addEventListener('keydown', (event) => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); onSelect(); } });
      };
      const isSelected = (id) => Boolean(state.selected && state.selected.id === id);
      const setTransform = () => viewport.setAttribute('transform', `translate(${state.x} ${state.y}) scale(${state.scale})`);
      const draw = () => {
        viewport.replaceChildren();
        const modules = new Map();
        files.forEach((file) => {
          const bits = String(file.path || file.id).split('/');
          const module = bits.length > 1 ? bits.slice(0, -1).join('/') : '(root)';
          if (!modules.has(module)) modules.set(module, []);
          modules.get(module).push(file);
        });
        const positions = new Map();
        let y = 24;
        [...modules.entries()].sort(([a], [b]) => a.localeCompare(b)).forEach(([module, group]) => {
          const moduleY = y;
          const moduleGroup = svgEl('g', { class: 'module-container' });
          viewport.appendChild(moduleGroup);
          addText(moduleGroup, `module: ${module}`, 34, y + 22, 'module-label');
          y += 34;
          group.forEach((file) => {
            const fileSymbols = symbols.filter((symbol) => symbol.file_id === file.id);
            const collapsed = state.collapsed.has(file.id);
            const fileSummary = summaryOf(file);
            const headerHeight = fileSummary ? 66 : 44;
            const expanded = state.expanded.has(file.id);
            const hiddenSymbols = fileSymbols.filter((symbol) => !relevantSymbolIds.has(symbol.id));
            const hiddenCount = hiddenSymbols.length;
            const relatedCount = hiddenSymbols.filter((symbol) => callNeighbourIds.has(symbol.id)).length;
            const shownSymbols = expanded ? fileSymbols : fileSymbols.filter((symbol) => relevantSymbolIds.has(symbol.id));
            const symbolRows = shownSymbols.map((symbol) => ({ symbol, summary: summaryOf(symbol) }));
            const moreHeight = hiddenCount ? 34 : 0;
            const symbolsHeight = symbolRows.reduce((total, row) => total + (row.summary ? 54 : 38), 0) + moreHeight;
            const height = collapsed || !fileSymbols.length ? headerHeight + 12 : Math.max(headerHeight + 28, headerHeight + symbolsHeight);
            const groupNode = svgEl('g', { class: 'file-container', tabindex: '0', role: 'button', 'aria-label': `Details for ${file.path || file.id}` });
            groupNode.appendChild(svgEl('rect', { x: 48, y, width: 1080, height, rx: 10, class: `file-box ${changeClass(file.change_kind)}${isSelected(file.id) ? ' selected' : ''}` }));
            addText(groupNode, file.path || file.id, 88, y + 29, 'file-label');
            addText(groupNode, file.change_kind || 'unknown', 1014, y + 29, 'change-label');
            if (fileSummary) addText(groupNode, summaryLine(fileSummary, 150), 88, y + 52, 'summary-label');
            interactive(groupNode, file, () => select(file.id));
            viewport.appendChild(groupNode);
            if (fileSymbols.length) {
              const toggle = svgEl('g', { class: 'collapse-toggle', tabindex: '0', role: 'button', 'aria-expanded': String(!collapsed), 'aria-label': `${collapsed ? 'Expand' : 'Collapse'} ${file.path || file.id}` });
              toggle.appendChild(svgEl('rect', { x: 56, y: y + 12, width: 24, height: 24, rx: 5, class: 'toggle-hit' }));
              addText(toggle, collapsed ? '▶' : '▼', 63, y + 29, 'toggle');
              const flip = (event) => { event.stopPropagation(); if (state.collapsed.has(file.id)) state.collapsed.delete(file.id); else state.collapsed.add(file.id); draw(); };
              toggle.addEventListener('click', flip);
              toggle.addEventListener('keydown', (event) => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); flip(event); } });
              viewport.appendChild(toggle);
            }
            positions.set(file.id, { x: 92, y: y + 29, visible: true });
            let sy = y + headerHeight + 4;
            if (!collapsed) symbolRows.forEach(({ symbol, summary }) => {
              const boxHeight = summary ? 44 : 28;
              const node = svgEl('g', { class: 'symbol-node', tabindex: '0', role: 'button', 'aria-label': `Details for ${symbol.kind || 'symbol'} ${symbol.qualified_name || symbol.name || symbol.id}` });
              node.appendChild(svgEl('rect', { x: 80, y: sy, width: 620, height: boxHeight, rx: 7, class: `symbol-box ${changeClass(symbol.change_kind)}${isSelected(symbol.id) ? ' selected' : ''}` }));
              addText(node, `${symbol.kind || 'symbol'}: ${symbol.qualified_name || symbol.name || symbol.id}`, 94, sy + 19, 'symbol-label');
              if (summary) addText(node, summaryLine(summary, 84), 94, sy + 36, 'summary-label');
              node.appendChild(svgEl('circle', { cx: 678, cy: sy + 14, r: 5, class: `change-dot ${changeClass(symbol.change_kind)}` }));
              interactive(node, symbol, () => select(symbol.id));
              viewport.appendChild(node);
              positions.set(symbol.id, { x: 390, y: sy + 14, visible: true });
              sy += boxHeight + 10;
            });
            if (!collapsed && hiddenCount) {
              const more = svgEl('g', { class: 'more-toggle', tabindex: '0', role: 'button', 'aria-expanded': String(expanded) });
              const related = relatedCount ? ` · ${relatedCount} call or called by changed code` : '';
              const label = expanded ? `▴ Show fewer (hide ${hiddenCount} unchanged)` : `▾ ${hiddenCount} more unchanged symbol${hiddenCount === 1 ? '' : 's'}${related}`;
              more.setAttribute('aria-label', label);
              more.appendChild(svgEl('rect', { x: 80, y: sy, width: 620, height: 24, rx: 7, class: 'more-box' }));
              addText(more, label, 94, sy + 16, 'more-label');
              const toggleMore = (event) => {
                event.stopPropagation();
                if (state.expanded.has(file.id)) state.expanded.delete(file.id); else state.expanded.add(file.id);
                draw();
              };
              more.addEventListener('click', toggleMore);
              more.addEventListener('keydown', (event) => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); toggleMore(event); } });
              viewport.appendChild(more);
            }
            fileSymbols.forEach((symbol) => { if (collapsed || !positions.has(symbol.id)) positions.set(symbol.id, { visible: false }); });
            y += height + 14;
          });
          const moduleHeight = y - moduleY - 14;
          const outline = svgEl('rect', { x: 24, y: moduleY, width: 1128, height: moduleHeight, rx: 14, class: 'module-outline' });
          moduleGroup.insertBefore(outline, moduleGroup.firstChild);
          y += 18;
        });
        const edges = svgEl('g', { class: 'relationship-edges' });
        relationships.forEach((relationship) => {
          const sourcePos = positions.get(relationship.source_id);
          const targetPos = positions.get(relationship.target_id);
          if (!sourcePos || !targetPos || !sourcePos.visible || !targetPos.visible) return;
          const edge = svgEl('line', { x1: sourcePos.x, y1: sourcePos.y, x2: targetPos.x, y2: targetPos.y, class: `edge-line${isSelected(relationship.id) ? ' selected' : ''}`, 'marker-end': 'url(#arrow)' });
          interactive(edge, relationship, () => selectRelationship(relationship));
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
        """Return deterministic HTML: the graph plus a compact snapshot bar."""
        files = self.dg["files"]
        symbols = self.dg["symbols"]
        metadata = self.dg["metadata"]
        self._validate_unique_object_ids(files, symbols)
        script_hash = _script_csp_hash(_INTERACTIVE_SCRIPT)
        topbar = self._topbar(files, symbols, metadata)
        overall = self._overall_summary()
        empty = (
            '<p class="graph-empty">No changes in the selected snapshot.</p>'
            if not files
            else ""
        )

        return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src 'sha256-{script_hash}'; style-src 'unsafe-inline'; img-src data:; base-uri 'none'; form-action 'none'">
  <title>wild diff — {_text(_diff_label(self.dg["diff_ref"]))}</title>
  <style>
    :root {{
      color-scheme: light dark; font-family: system-ui, sans-serif;
      --page-bg: #ffffff; --graph-bg: #f8fafc; --node-bg: #ffffff; --symbol-bg: #f2f4f7;
      --text-strong: #101828; --text: #344054; --text-muted: #475467;
      --edge: #475467; --outline: #98a2b3; --focus: #101828; --selected: #7a5af8;
      --tooltip-bg: #101828; --tooltip-text: #f9fafb; --tooltip-border: #667085;
      --ck-added: #18794e; --ck-deleted: #b42318; --ck-modified: #175cd3;
      --ck-unchanged: #667085; --ck-untracked: #7a5af8; --ck-renamed: #b54708;
    }}
    @media (prefers-color-scheme: dark) {{
      :root {{
        --page-bg: #0c111d; --graph-bg: #0c111d; --node-bg: #161b26; --symbol-bg: #1f242f;
        --text-strong: #f5f5f6; --text: #cecfd2; --text-muted: #94969c;
        --edge: #94969c; --outline: #61646c; --focus: #f5f5f6; --selected: #bdb4fe;
        --tooltip-bg: #1f242f; --tooltip-text: #f5f5f6; --tooltip-border: #61646c;
        --ck-added: #47cd89; --ck-deleted: #f97066; --ck-modified: #84adff;
        --ck-unchanged: #94969c; --ck-untracked: #bdb4fe; --ck-renamed: #fdb022;
      }}
    }}
    html, body {{ height: 100%; margin: 0; }}
    body {{ display: flex; flex-direction: column; background: var(--page-bg); color: var(--text); line-height: 1.4; }}
    code, pre {{ font-family: ui-monospace, SFMono-Regular, Consolas, monospace; }}
    .topbar {{ display: flex; flex-wrap: wrap; gap: .5rem 1rem; align-items: center; padding: .55rem 1rem; border-bottom: 1px solid var(--outline); background: var(--node-bg); font-size: .875rem; }}
    .topbar .brand {{ font-weight: 700; color: var(--text-strong); }}
    .topbar .range {{ font-family: ui-monospace, SFMono-Regular, Consolas, monospace; color: var(--text-strong); }}
    .topbar .spacer {{ flex: 1; }}
    .badge {{ display: inline-block; padding: .05rem .55rem; border: 1px solid var(--outline); border-radius: 999px; font-size: .78rem; white-space: nowrap; }}
    .badge.ck-added {{ color: var(--ck-added); border-color: var(--ck-added); }}
    .badge.ck-deleted {{ color: var(--ck-deleted); border-color: var(--ck-deleted); }}
    .badge.ck-modified {{ color: var(--ck-modified); border-color: var(--ck-modified); }}
    .badge.ck-unchanged {{ color: var(--ck-unchanged); border-color: var(--ck-unchanged); }}
    .badge.ck-untracked {{ color: var(--ck-untracked); border-color: var(--ck-untracked); }}
    .badge.ck-renamed {{ color: var(--ck-renamed); border-color: var(--ck-renamed); }}
    .badge.ai {{ color: var(--selected); border-color: var(--selected); }}
    .popover {{ position: relative; }}
    .popover > summary {{ cursor: pointer; list-style: none; }}
    .popover > summary::-webkit-details-marker {{ display: none; }}
    .popover > .popover-body {{ position: absolute; right: 0; z-index: 3; width: min(32rem, 90vw); max-height: 60vh; overflow: auto; margin-top: .4rem; padding: .75rem 1rem; border: 1px solid var(--outline); border-radius: .5rem; background: var(--node-bg); box-shadow: 0 8px 24px #0003; }}
    .popover-body ul {{ margin: 0; padding-left: 1.1rem; }}
    .popover-body dl {{ display: grid; grid-template-columns: auto 1fr; gap: .2rem .8rem; margin: 0; }}
    .popover-body dt {{ color: var(--text-muted); }} .popover-body dd {{ margin: 0; overflow-wrap: anywhere; }}
    .overall-summary {{ margin: 0; padding: .45rem 1rem; border-bottom: 1px solid var(--outline); font-size: .875rem; }}
    .layout {{ flex: 1; display: grid; grid-template-columns: minmax(0, 1fr) 22rem; min-height: 0; }}
    .layout.details-closed {{ grid-template-columns: minmax(0, 1fr) 0; }}
    .layout.details-closed #diffgraph-details {{ display: none; }}
    #diffgraph-graph {{ position: relative; min-height: 0; overflow: hidden; background: var(--graph-bg); }}
    #diffgraph-graph svg {{ display: block; width: 100%; height: 100%; cursor: grab; }}
    #diffgraph-graph svg:active {{ cursor: grabbing; }}
    .graph-empty {{ margin: 3rem auto; text-align: center; color: var(--text-muted); }}
    #diffgraph-details {{ position: relative; overflow: auto; padding: 1rem 1.1rem; border-left: 1px solid var(--outline); background: var(--node-bg); font-size: .875rem; }}
    .details-close {{ position: absolute; top: .5rem; right: .6rem; border: 0; background: none; color: var(--text-muted); font-size: 1.1rem; cursor: pointer; }}
    .details-help h2 {{ margin: 0 0 .5rem; font-size: 1rem; color: var(--text-strong); }}
    .details-help ul {{ padding-left: 1.1rem; }}
    .legend {{ display: flex; flex-wrap: wrap; gap: .35rem; }}
    .details-header h2 {{ margin: .1rem 0 .4rem; font-size: 1rem; color: var(--text-strong); overflow-wrap: anywhere; }}
    .details-kind {{ margin: 0; color: var(--text-muted); text-transform: uppercase; font-size: .7rem; letter-spacing: .04em; }}
    .details-meta {{ margin: .45rem 0; color: var(--text-muted); overflow-wrap: anywhere; }}
    .details-section h3 {{ margin: 1rem 0 .3rem; font-size: .8rem; color: var(--text-strong); }}
    .details-section ul {{ margin: 0; padding-left: 1.1rem; }}
    .node-link {{ display: block; max-width: 100%; padding: 0; border: 0; background: none; color: var(--ck-modified); font: inherit; text-align: left; cursor: pointer; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
    .show-all {{ margin-top: .3rem; padding: .1rem .5rem; border: 1px solid var(--outline); border-radius: .3rem; background: none; color: var(--text-muted); font: inherit; font-size: .78rem; cursor: pointer; }}
    .details-edge .node-link {{ display: inline; white-space: normal; overflow-wrap: anywhere; }}
    .node-link:hover {{ text-decoration: underline; }}
    .ai-summary {{ margin: .6rem 0; padding: .55rem .7rem; border-left: 3px solid var(--selected); background: var(--symbol-bg); border-radius: .3rem; }}
    .ai-summary p {{ margin: .3rem 0 0; }}
    .ai-badge {{ display: inline-block; margin-right: .4rem; padding: 0 .35rem; border: 1px solid var(--selected); border-radius: .3rem; color: var(--selected); font-size: .7rem; font-weight: 700; }}
    .ai-model {{ color: var(--text-muted); font-size: .75rem; }}
    .evidence-kind {{ margin: .35rem 0 .15rem; color: var(--text-muted); font-size: .78rem; overflow-wrap: anywhere; }}
    .evidence-snippet {{ margin: 0 0 .4rem; padding: .4rem .5rem; overflow-x: auto; white-space: pre-wrap; background: var(--symbol-bg); border-radius: .3rem; font-size: .75rem; }}
    .module-label {{ font-size: 16px; font-weight: 700; fill: var(--text); }}
    .file-label {{ font-size: 16px; font-weight: 700; fill: var(--text-strong); }}
    .symbol-label {{ font-size: 14px; fill: var(--text); }}
    .change-label {{ font-size: 12px; fill: var(--text-muted); }}
    .summary-label {{ font-size: 12px; font-style: italic; fill: var(--text-muted); }}
    .toggle {{ font-size: 13px; fill: var(--text); pointer-events: none; }}
    .toggle-hit {{ fill: transparent; stroke: none; }}
    .collapse-toggle {{ cursor: pointer; outline: none; }}
    .collapse-toggle:hover .toggle-hit, .collapse-toggle:focus .toggle-hit {{ fill: var(--symbol-bg); }}
    .module-outline {{ fill: none; stroke: var(--outline); stroke-dasharray: 6 5; }}
    .file-box {{ fill: var(--node-bg); stroke: var(--ck-unchanged); stroke-width: 3; }}
    .symbol-box {{ fill: var(--symbol-bg); stroke: var(--ck-unchanged); stroke-width: 1; }}
    .change-dot {{ fill: var(--ck-unchanged); stroke: none; }}
    .ck-added {{ stroke: var(--ck-added); }} .change-dot.ck-added {{ fill: var(--ck-added); }}
    .ck-deleted {{ stroke: var(--ck-deleted); }} .change-dot.ck-deleted {{ fill: var(--ck-deleted); }}
    .ck-modified {{ stroke: var(--ck-modified); }} .change-dot.ck-modified {{ fill: var(--ck-modified); }}
    .ck-unchanged {{ stroke: var(--ck-unchanged); }} .change-dot.ck-unchanged {{ fill: var(--ck-unchanged); }}
    .ck-untracked {{ stroke: var(--ck-untracked); }} .change-dot.ck-untracked {{ fill: var(--ck-untracked); }}
    .ck-renamed {{ stroke: var(--ck-renamed); }} .change-dot.ck-renamed {{ fill: var(--ck-renamed); }}
    .file-box.selected, .symbol-box.selected {{ stroke: var(--selected); stroke-width: 3; }}
    .edge-line {{ stroke: var(--edge); stroke-width: 1.5; pointer-events: stroke; cursor: pointer; }}
    .edge-line:hover, .edge-line.selected {{ stroke: var(--selected); stroke-width: 3; }}
    .edge-arrow {{ fill: var(--edge); }}
    .file-container, .symbol-node {{ cursor: pointer; outline: none; }}
    .file-container:hover > rect, .symbol-node:hover > rect {{ stroke-width: 3; }}
    .file-container:focus > rect, .symbol-node:focus > rect {{ stroke: var(--focus); stroke-width: 3; }}
    .more-toggle {{ cursor: pointer; outline: none; }}
    .more-box {{ fill: none; stroke: var(--outline); stroke-dasharray: 4 4; }}
    .more-label {{ font-size: 13px; fill: var(--text-muted); }}
    .more-toggle:hover .more-label, .more-toggle:focus .more-label {{ fill: var(--text-strong); }}
    .more-toggle:focus > rect {{ stroke: var(--focus); stroke-dasharray: none; }}
    .graph-tooltip {{ position: absolute; z-index: 2; max-width: min(28rem, 80%); margin: 0; padding: .45rem .6rem; white-space: pre-line; border: 1px solid var(--tooltip-border); border-radius: .4rem; background: var(--tooltip-bg); color: var(--tooltip-text); font-size: .75rem; pointer-events: none; }}
  </style>
</head>
<body>
  {topbar}
  {overall}
  <div class="layout" id="diffgraph-layout">
    <main id="diffgraph-graph" aria-label="Interactive graph">{empty}</main>
    <aside id="diffgraph-details" aria-label="Details">
      <button type="button" class="details-close" aria-label="Close details">×</button>
      <div class="details-help">
        <h2>Explore the change</h2>
        <ul>
          <li>Select a file, symbol, or edge to see its details here.</li>
          <li>Scroll to zoom; drag empty space to pan.</li>
          <li>▶/▼ collapses a file; ▾/▴ shows or hides its unchanged symbols.</li>
        </ul>
        <div class="legend">
          <span class="badge ck-added">added</span><span class="badge ck-modified">modified</span><span class="badge ck-deleted">deleted</span><span class="badge ck-renamed">renamed</span><span class="badge ck-unchanged">unchanged</span>
        </div>
      </div>
      <div class="details-body" hidden></div>
    </aside>
  </div>
  <script type="application/json" id="diffgraph-artifact">{_embedded_json(self.dg)}</script>
  <script>{_INTERACTIVE_SCRIPT}</script>
</body>
</html>
"""

    def _topbar(self, files: list[dict], symbols: list[dict], metadata: dict) -> str:
        counts = {"added": 0, "modified": 0, "deleted": 0}
        for symbol in symbols:
            if symbol.get("change_kind") in counts and symbol.get("kind") != "import":
                counts[symbol["change_kind"]] += 1
        symbol_counts = " · ".join(
            f"{count} {kind}" for kind, count in counts.items() if count
        ) or "no symbol changes"
        if metadata.get("privacy_tier") == "local":
            privacy = '<span class="badge" title="No data left this machine">Local only</span>'
        else:
            calls = metadata.get("llm_calls") or 0
            model = metadata.get("llm_model")
            label = f"AI: {model} · {_plural(calls, 'call')}" if model else str(metadata.get("privacy_tier"))
            providers = ", ".join(metadata.get("cloud_providers_used") or [])
            title = f"Code was sent to {providers}" if providers else "Data left this machine"
            privacy = f'<span class="badge ai" title="{_text(title)}">{_text(label)}</span>'
        raw_warnings = metadata.get("warnings", [])
        lines = warning_lines(raw_warnings)
        warnings = (
            '<details class="popover"><summary><span class="badge">⚠ '
            f"{_text(_plural(len(raw_warnings), 'warning'))}</span></summary>"
            '<div class="popover-body"><ul>'
            + "".join(f"<li>{_text(line)}</li>" for line in lines)
            + "</ul></div></details>"
            if lines
            else ""
        )
        about = (
            '<details class="popover"><summary><span class="badge">About</span></summary>'
            '<div class="popover-body"><dl>'
            f"<dt>Snapshot</dt><dd>{_text(_diff_label(self.dg['diff_ref']))}</dd>"
            f"<dt>Generated</dt><dd>{_text(self.dg['generated_at'])}</dd>"
            f"<dt>wild</dt><dd>{_text(self.dg['wild_version'])}</dd>"
            f"<dt>Schema</dt><dd>{_text(self.dg['schema_version'])}</dd>"
            "<dt>Raw data</dt><dd><code>wild diff --format json</code></dd>"
            "</dl></div></details>"
        )
        return (
            '<header class="topbar">'
            '<span class="brand">wild diff</span>'
            f'<span class="range">{_text(_diff_label(self.dg["diff_ref"]))}</span>'
            f"<span>{_text(_plural(len(files), 'file'))} · {_text(symbol_counts)}</span>"
            '<span class="spacer"></span>'
            f"{privacy}{warnings}{about}"
            "</header>"
        )

    def _overall_summary(self) -> str:
        summary = self.dg.get("summary")
        if not isinstance(summary, dict) or not str(summary.get("text") or "").strip():
            return ""
        return (
            '<p class="overall-summary"><span class="ai-badge">AI</span>'
            f"{_text(summary['text'])}</p>"
        )

    @staticmethod
    def _validate_unique_object_ids(files: list[dict], symbols: list[dict]) -> None:
        """Reject duplicate object IDs; the graph keys positions and selection by ID."""
        object_ids = [item["id"] for item in (*files, *symbols)]
        duplicate_ids = sorted(item_id for item_id in set(object_ids) if object_ids.count(item_id) > 1)
        if duplicate_ids:
            raise ValueError("DiffGraph HTML rendering requires unique file and symbol IDs; duplicates: " + ", ".join(duplicate_ids))

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
