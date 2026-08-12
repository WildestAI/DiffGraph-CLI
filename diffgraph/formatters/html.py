"""Deterministic HTML adapter for a validated canonical DiffGraph artifact.

This consumer performs no repository reads, structural analysis, AI calls, or
network access.  It renders only values already present in the artifact.  The
report is self-contained; the deprecated legacy HTML renderer remains the only
HTML path with external CDN assets.
"""
from __future__ import annotations

import html
import json
import os
import tempfile
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

        file_items = self._object_items(files, "No files in the selected snapshot.")
        symbol_items = self._object_items(symbols, "No symbols in the artifact.")
        relationship_items = self._relationship_items(relationships)
        warning_items = (
            "".join(f"<li><pre>{_json(warning)}</pre></li>" for warning in warnings)
            or "<li>None</li>"
        )
        summary = (
            f"<h3>Summary</h3><pre>{_json(self.dg['summary'])}</pre>"
            if "summary" in self.dg
            else ""
        )

        return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
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
  </style>
</head>
<body>
  <h1>DiffGraph Report</h1>
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
</body>
</html>
"""

    @staticmethod
    def _object_items(items: list[dict], empty_message: str) -> str:
        if not items:
            return f'<p class="panel">{html.escape(empty_message)}</p>'
        return "".join(
            f'<article><h3><code>{_text(item["id"])}</code></h3><pre>{_json(item)}</pre></article>'
            for item in items
        )

    @staticmethod
    def _relationship_items(relationships: list[dict]) -> str:
        if not relationships:
            return '<p class="panel">No relationships in the artifact.</p>'
        return "".join(
            "<article>"
            f'<div class="edge"><code>{_text(item["source_id"])}</code>'
            f'<span class="kind">{_text(item["kind"])}</span>'
            f'<code>{_text(item["target_id"])}</code></div>'
            f'<pre>{_json(item)}</pre>'
            "</article>"
            for item in relationships
        )

    def write(self, destination: Path) -> Path:
        """Atomically write a complete report and return its absolute path."""
        rendered = self.render()
        temporary_path = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=destination.parent,
                prefix=f".{destination.name}.",
                suffix=".tmp",
                delete=False,
            ) as temporary:
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
