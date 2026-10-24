"""Golden and CLI contracts for canonical HTML artifact consumption."""
from __future__ import annotations

import base64
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest
from click.testing import CliRunner

import diffgraph.cli as cli
from diffgraph.contract import ValidatedArtifact
from diffgraph.formatters.html import HtmlFormatter


def git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True)


def changed_repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    git(root, "init")
    git(root, "config", "user.name", "HTML Tests")
    git(root, "config", "user.email", "html@example.test")
    (root / "app.py").write_text("def value():\n    return 1\n", encoding="utf-8")
    git(root, "add", "app.py")
    git(root, "commit", "-m", "base")
    (root / "app.py").write_text("def value():\n    return 2\n", encoding="utf-8")
    return root


def golden_artifact() -> dict:
    return json.loads(
        (Path(__file__).parents[1] / "diffgraph/schema/diffgraph-v2.structural.example.json")
        .read_text(encoding="utf-8")
    )


def embedded_artifact(report: str) -> dict:
    match = re.search(
        r'<script type="application/json" id="diffgraph-artifact">(.*?)</script>',
        report,
        re.DOTALL,
    )
    assert match is not None
    return json.loads(match.group(1))


def test_html_formatter_renders_complete_golden_artifact_without_inference():
    value = golden_artifact()
    artifact = ValidatedArtifact.from_value(value)

    report = HtmlFormatter(artifact).render()

    assert embedded_artifact(report) == value
    assert "src/greeting.py" in report
    assert "sym::src/greeting.py::greet" in report
    assert "privacy_tier" in report
    # Graph-first report: no textual dumps of the artifact.
    assert "Deterministic topology" not in report
    assert "<pre>" not in report.split('<script type="application/json"', 1)[0]
    assert "Local only" in report
    # The canonical example has no prose summary or inferred impact claim.
    assert "likely impact" not in report.lower()
    assert "AI analysis" not in report
    assert "https://" not in report
    assert "Content-Security-Policy\" content=\"default-src 'none';" in report
    assert "script-src 'sha256-" in report
    assert "style-src 'unsafe-inline'; img-src data:; base-uri 'none'; form-action 'none'" in report
    assert "https://" not in report


def test_html_formatter_is_self_contained_interactive_and_uses_safe_details_api():
    artifact = ValidatedArtifact.from_value(golden_artifact())

    report = HtmlFormatter(artifact).render()

    assert 'id="diffgraph-graph"' in report
    assert "Interactive graph" in report
    assert "module-container" in report
    assert "file-container" in report
    assert "symbol-node" in report
    assert "Scroll to zoom; drag empty space to pan." in report
    assert 'id="diffgraph-details"' in report
    assert "state.collapsed" in report
    assert "tooltip.textContent = text" in report
    assert "innerHTML" not in report
    assert "cdn" not in report.lower()
    assert "unsafe-inline" not in report.split("script-src", 1)[1].split("style-src", 1)[0]


def test_html_formatter_graph_colors_follow_light_and_dark_themes():
    artifact = ValidatedArtifact.from_value(golden_artifact())
    report = HtmlFormatter(artifact).render()

    script = re.search(r'<script>(.*?)</script>', report, re.DOTALL).group(1)
    style = re.search(r'<style>(.*?)</style>', report, re.DOTALL).group(1)

    # The script must not pin colors; fixed fills/strokes ignore the theme.
    assert re.search(r"#[0-9a-fA-F]{3,8}\b", script) is None
    assert re.search(r"\b(fill|stroke):\s*'", script) is None

    # Every themed variable is defined for light and overridden for dark.
    light_vars = set(re.findall(r"(--[\w-]+):", style.split("@media (prefers-color-scheme: dark)")[0]))
    dark_block = style.split("@media (prefers-color-scheme: dark)", 1)[1]
    dark_vars = set(re.findall(r"(--[\w-]+):", dark_block))
    assert {"--graph-bg", "--node-bg", "--symbol-bg", "--edge", "--text-strong"} <= light_vars
    assert light_vars == dark_vars
    for selector in (".file-box", ".symbol-box", ".edge-line", ".edge-arrow", ".module-outline", ".file-label"):
        rule = re.search(re.escape(selector) + r"\s*\{([^}]*)\}", style)
        assert rule is not None, selector
        assert "var(--" in rule.group(1), selector
        assert re.search(r"#[0-9a-fA-F]{3,8}\b", rule.group(1)) is None, selector


def test_html_formatter_csp_hash_allows_only_the_static_interactive_script():
    artifact = ValidatedArtifact.from_value(golden_artifact())
    report = HtmlFormatter(artifact).render()

    script_match = re.search(r'<script>(.*?)</script>', report, re.DOTALL)
    csp_match = re.search(r"script-src 'sha256-([^']+)'", report)
    assert script_match is not None
    assert csp_match is not None
    digest = base64.b64encode(hashlib.sha256(script_match.group(1).encode()).digest()).decode()
    assert csp_match.group(1) == digest


def test_html_formatter_embeds_artifact_strings_inertly():
    value = golden_artifact()
    first = dict(value["relationships"][0])
    first.update({"id": "rel::a->target", "label": "</script><script>bad()</script>"})
    value["relationships"] = [first]
    value["diff_ref"]["pathspecs"] = ["<img src=x onerror=bad()>"]
    artifact = ValidatedArtifact.from_value(value)

    report = HtmlFormatter(artifact).render()

    assert "</script><script>bad()" not in report
    assert "<img src=x" not in report
    assert "&lt;img src=x onerror=bad()&gt;" in report  # top-bar snapshot label
    assert embedded_artifact(report) == value


def test_html_formatter_topbar_reports_snapshot_privacy_and_warnings():
    value = golden_artifact()
    value["metadata"]["warnings"] = [
        {"code": "UNSUPPORTED_LANGUAGE", "file": "README.md", "detail": "blob ids"},
        {"code": "PARSE_FAILURE", "file": "bad.py", "detail": "syntax error at line 3"},
    ]
    report = HtmlFormatter(ValidatedArtifact.from_value(value)).render()
    topbar = report.split('<header class="topbar">', 1)[1].split("</header>", 1)[0]

    assert '<span class="brand">wild diff</span>' in topbar
    assert "Local only" in topbar
    assert "⚠ 2 warnings" in topbar
    assert "Not analyzed (Python only, 1 file): README.md" in topbar
    assert "PARSE_FAILURE  bad.py: syntax error at line 3" in topbar
    assert "wild diff --format json" in topbar  # where to get the raw artifact
    assert "{'code'" not in topbar


def test_html_formatter_topbar_names_llm_model_and_calls():
    value = golden_artifact()
    value["metadata"].update(
        {"privacy_tier": "cloud_llm", "llm_model": "claude-opus-5-5", "llm_calls": 2, "cloud_providers_used": ["anthropic"]}
    )
    report = HtmlFormatter(ValidatedArtifact.from_value(value)).render()

    assert 'title="Code was sent to anthropic">AI: claude-opus-5-5 · 2 calls</span>' in report
    assert "Local only" not in report


def test_html_formatter_rejects_duplicate_object_ids_before_rendering_anchors():
    value = golden_artifact()
    duplicate_file = dict(value["files"][0])
    value["files"].append(duplicate_file)
    artifact = ValidatedArtifact.from_value(value)

    with pytest.raises(ValueError, match="requires unique file and symbol IDs"):
        HtmlFormatter(artifact).render()


def test_canonical_html_cli_is_atomic_honors_output_and_no_open(tmp_path, monkeypatch):
    root = changed_repo(tmp_path)
    destination = root / "report.html"
    monkeypatch.chdir(root)

    result = CliRunner().invoke(
        cli.main,
        ["diff", "--format", "html", "--output", str(destination), "--no-open"],
    )

    assert result.exit_code == 0, result.output
    assert destination.read_text(encoding="utf-8").startswith("<!doctype html>")
    assert not list(root.glob(".report.html.*.tmp"))
    assert "HTML report generated" in result.stdout
    assert result.stderr == ""


@pytest.mark.parametrize("failure", [OSError("missing opener"), 3])
def test_canonical_html_browser_launch_failure_is_a_warning(
    failure, tmp_path, monkeypatch
):
    root = changed_repo(tmp_path)
    monkeypatch.chdir(root)
    real_run = cli.subprocess.run

    def run(command, *args, **kwargs):
        if command[0] == "xdg-open":
            if isinstance(failure, OSError):
                raise failure
            return type("Result", (), {"returncode": failure})()
        return real_run(command, *args, **kwargs)

    monkeypatch.setattr(cli.sys, "platform", "linux")
    monkeypatch.setattr(cli.subprocess, "run", run)

    result = CliRunner().invoke(cli.main, ["diff", "--format", "html"])

    assert result.exit_code == 0, result.output
    assert "HTML report generated" in result.stdout
    assert "Could not open report in browser" in result.stderr
    assert (root / "diffgraph.html").exists()


def test_canonical_html_no_change_writes_a_complete_report(tmp_path, monkeypatch):
    root = changed_repo(tmp_path)
    git(root, "checkout", "--", "app.py")
    destination = root / "empty.html"
    monkeypatch.chdir(root)

    result = CliRunner().invoke(
        cli.main,
        ["diff", "--format", "html", "--output", str(destination), "--no-open"],
    )

    assert result.exit_code == 0, result.output
    report = destination.read_text(encoding="utf-8")
    assert embedded_artifact(report)["files"] == []
    assert "No changes in the selected snapshot." in report


def test_canonical_html_cancellation_does_not_create_output(tmp_path, monkeypatch):
    root = changed_repo(tmp_path)
    destination = root / "cancelled.html"
    monkeypatch.chdir(root)

    def interrupt(*args, **kwargs):
        raise KeyboardInterrupt

    monkeypatch.setattr(cli, "build_validated_artifact", interrupt)
    result = CliRunner().invoke(
        cli.main,
        ["diff", "--format", "html", "--output", str(destination), "--no-open"],
    )

    assert result.exit_code == 1
    assert result.stdout == ""
    assert "Aborted!" in result.stderr
    assert not destination.exists()


def test_canonical_html_is_offline_and_imports_no_ai_sdk(tmp_path, monkeypatch):
    root = changed_repo(tmp_path)
    monkeypatch.chdir(root)
    sys.modules.pop("diffgraph.ai_analysis", None)
    sys.modules.pop("agents", None)

    import socket

    monkeypatch.setattr(
        socket,
        "socket",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("network access")),
    )
    result = CliRunner().invoke(cli.main, ["diff", "--format", "html", "--no-open"])

    assert result.exit_code == 0, result.output
    assert "diffgraph.ai_analysis" not in sys.modules
    assert "agents" not in sys.modules


def test_html_write_failure_preserves_existing_report(tmp_path, monkeypatch):
    destination = tmp_path / "report.html"
    destination.write_text("previous complete report", encoding="utf-8")
    artifact = ValidatedArtifact.from_value(golden_artifact())

    def fail_replace(source, target):
        raise OSError("replace failed")

    monkeypatch.setattr("diffgraph.formatters.html.os.replace", fail_replace)

    try:
        HtmlFormatter(artifact).write(destination)
    except OSError as error:
        assert "replace failed" in str(error)
    else:
        raise AssertionError("expected write failure")

    assert destination.read_text(encoding="utf-8") == "previous complete report"
    assert not list(tmp_path.glob(".report.html.*.tmp"))


def _node_summary(text: str, model: str = "claude-haiku-4-5") -> dict:
    return {
        "text": text,
        "analysis_source": "inferred",
        "confidence": None,
        "evidence": [
            {"kind": "llm_inference", "model": model},
            {"kind": "structural_basis", "file_ids": [], "symbol_ids": []},
        ],
    }


def test_html_formatter_renders_node_summaries_as_labelled_escaped_text():
    value = golden_artifact()
    value["schema_version"] = "2.1"
    value["files"][0]["summary"] = _node_summary("Adds <b>token</b> & cache checks.")
    value["symbols"][0]["summary"] = _node_summary("Validates <script>alert(1)</script> input.")
    report = HtmlFormatter(ValidatedArtifact.from_value(value)).render()

    assert "<script>alert(1)" not in report
    assert "<b>token</b>" not in report
    # The graph and details panel read summaries from inert JSON and render
    # them only through textContent, labelled with the model.
    assert "summaryOf(file)" in report and "summaryOf(symbol)" in report
    assert "'summary-label'" in report and "'ai-badge', 'AI'" in report
    assert "innerHTML" not in report
    assert embedded_artifact(report)["symbols"][0]["summary"]["text"].startswith("Validates <script>")


def test_html_formatter_without_node_summaries_renders_no_summary_markup():
    report = HtmlFormatter(ValidatedArtifact.from_value(golden_artifact())).render()
    body = report.split("<style>", 1)[0] + report.split("</style>", 1)[1].split("<script", 1)[0]

    assert "ai-badge" not in body
    assert "overall-summary" not in body


def test_package_sources_compile_without_warnings():
    """Embedded JS lives in Python strings; invalid escapes (e.g. a bare \\s)
    are SyntaxWarnings today and errors in future Python versions."""
    import pathlib
    import warnings

    for path in pathlib.Path(__file__).resolve().parents[1].joinpath("diffgraph").rglob("*.py"):
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            compile(path.read_text(encoding="utf-8"), str(path), "exec")


def test_graph_defaults_to_changed_symbols_with_toggle_for_the_rest():
    from diffgraph.formatters.html import _INTERACTIVE_SCRIPT

    # Unchanged symbols are hidden behind a per-file ▾/▴ toggle; call
    # neighbours of changed code are counted in its label, not drawn.
    assert "changedSymbolIds" in _INTERACTIVE_SCRIPT
    assert "call or called by changed code" in _INTERACTIVE_SCRIPT
    assert "state.expanded" in _INTERACTIVE_SCRIPT
    assert "more-toggle" in _INTERACTIVE_SCRIPT
    assert "▾" in _INTERACTIVE_SCRIPT and "▴" in _INTERACTIVE_SCRIPT
