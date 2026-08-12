"""Golden and CLI contracts for canonical HTML artifact consumption."""
from __future__ import annotations

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
    assert "rel::file::src/greeting.py-&gt;sym::src/greeting.py::greet" in report
    assert "privacy_tier" in report
    assert "Deterministic topology" in report
    # The canonical example has no prose summary or inferred impact claim.
    assert "likely impact" not in report.lower()
    assert "AI analysis" not in report
    assert "https://" not in report


def test_html_formatter_sorts_topology_and_escapes_artifact_text():
    value = golden_artifact()
    first = dict(value["relationships"][0])
    first["id"] = "rel::z->target"
    second = dict(first)
    second.update(
        {"id": "rel::a->target", "label": "</script><script>bad()</script>"}
    )
    value["relationships"] = [first, second]
    artifact = ValidatedArtifact.from_value(value)

    report = HtmlFormatter(artifact).render()

    assert report.index("rel::a-&gt;target") < report.index("rel::z-&gt;target")
    assert "</script><script>bad()" not in report
    assert embedded_artifact(report) == value


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
    assert "No files in the selected snapshot." in report


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
