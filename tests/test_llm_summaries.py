"""Tests for opt-in AI node summaries through BYOK Relay.

No test touches the network: the relay transport and chat calls are fakes.
"""
from __future__ import annotations

import json
import os
import stat
import subprocess
from pathlib import Path

import pytest
from click.testing import CliRunner

import diffgraph.cli as cli
from diffgraph.artifact import build_validated_artifact
from diffgraph.contract import ValidatedArtifact, enrich_with_node_summaries
from diffgraph.llm_summaries import parse_summaries, summarize_artifact
from diffgraph.relay import (
    MissingProviderKey,
    RelayClient,
    RelayError,
    RelayTimeout,
    load_token,
    provider_for_model,
    save_token,
)


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    """Fail loudly if any test reaches the real relay transport."""

    def refuse(*args, **kwargs):
        raise AssertionError("test attempted a real relay request")

    monkeypatch.setattr("diffgraph.relay._urllib_transport", refuse)


def git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path, monkeypatch):
    root = tmp_path / "repo"
    root.mkdir()
    git(root, "init")
    git(root, "config", "user.name", "LLM Tests")
    git(root, "config", "user.email", "llm@example.test")
    (root / "app.py").write_text(
        "import json\n\ndef keep():\n    return 0\n\ndef value():\n    return 1\n",
        encoding="utf-8",
    )
    git(root, "add", "app.py")
    git(root, "commit", "-m", "base")
    (root / "app.py").write_text(
        "import json\n\ndef keep():\n    return 0\n\ndef value():\n    return 2\n\n"
        "def added():\n    return json.dumps({})\n",
        encoding="utf-8",
    )
    (root / "NOTES.md").write_text("hello\n", encoding="utf-8")
    monkeypatch.chdir(root)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.delenv("BYOK_RELAY_TOKEN", raising=False)
    monkeypatch.delenv("BYOK_RELAY_URL", raising=False)
    return root


def artifact_for(root: Path) -> ValidatedArtifact:
    return build_validated_artifact(str(root), wild_version="test")


class FakeClient:
    """Answers every requested node id; records prompts."""

    def __init__(self, fail_with=None):
        self.prompts = []
        self.fail_with = fail_with

    def chat(self, model, messages, max_tokens=2048):
        prompt = messages[-1]["content"]
        self.prompts.append(prompt)
        if self.fail_with is not None:
            raise self.fail_with
        ids = [
            line[2:].split(": ", 1)[0]
            for line in prompt.splitlines()
            if line.startswith("- file::") or line.startswith("- sym::")
        ]
        reply = {node_id: f"Summary of {node_id}." for node_id in ids}
        reply["sym::invented.py::ghost"] = "must be ignored"
        return "```json\n" + json.dumps(reply) + "\n```"


# ---------------------------------------------------------------------------
# Relay client
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    ("model", "provider"),
    [
        ("claude-haiku-5-5", "anthropic"),
        ("gpt-5-mini", "openai"),
        ("o3", "openai"),
        ("gemini-2.5-flash", "google"),
        ("anthropic/some-model", "anthropic"),
    ],
)
def test_provider_for_model(model, provider):
    assert provider_for_model(model) == provider


def test_provider_for_unknown_model_is_rejected():
    with pytest.raises(ValueError, match="cannot tell which provider"):
        provider_for_model("llama-3")


def fake_transport(responses, calls):
    def transport(method, url, headers, body, timeout):
        calls.append((method, url, dict(headers), json.loads(body) if body else None))
        status, payload, response_headers = responses.pop(0)
        return status, response_headers, json.dumps(payload).encode()

    return transport


def test_chat_uses_openai_format_endpoint_with_relay_token_and_retries_429():
    calls, sleeps = [], []
    client = RelayClient(
        "https://relay.example/",
        "tok",
        transport=fake_transport(
            [
                (429, {"error": "slow down"}, {"Retry-After": "2"}),
                (200, {"choices": [{"message": {"content": "hi"}}]}, {}),
            ],
            calls,
        ),
        sleep=sleeps.append,
    )

    assert client.chat("gemini-2.5-flash", [{"role": "user", "content": "x"}]) == "hi"
    method, url, headers, body = calls[-1]
    assert (method, url) == ("POST", "https://relay.example/relay/v1/chat/completions")
    assert headers["x-relay-token"] == "tok"
    assert body["model"] == "google/gemini-2.5-flash" and body["stream"] is False
    assert sleeps == [2.0]


def test_missing_provider_key_and_timeouts_are_typed():
    missing = RelayClient("https://r", "t", transport=fake_transport(
        [(400, {"error": 'No API key stored for provider "google". POST /keys/google first.'}, {})], []
    ))
    with pytest.raises(MissingProviderKey) as error:
        missing.chat("gemini-x", [])
    assert error.value.provider == "google"

    timeout = RelayClient("https://r", "t", transport=fake_transport([(504, {"error": "gateway"}, {})], []))
    with pytest.raises(RelayTimeout):
        timeout.chat("gpt-x", [])


def test_register_and_store_key_never_persist_the_provider_key(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.delenv("BYOK_RELAY_TOKEN", raising=False)
    calls = []
    client = RelayClient("https://r", transport=fake_transport(
        [(200, {"token": "relay-tok"}, {}), (200, {"ok": True}, {})], calls
    ))

    client.register()
    client.store_key("anthropic", "sk-ant-secret-value")
    path = save_token("https://r", client.token)

    assert calls[0][1:4:2] == ("https://r/users", {"app_id": "wild-cli"})
    assert calls[1][1] == "https://r/keys/anthropic"
    assert calls[1][2]["x-relay-token"] == "relay-tok"
    assert stat.S_IMODE(os.stat(path).st_mode) == 0o600
    assert "sk-ant-secret-value" not in path.read_text()
    assert load_token("https://r/") == "relay-tok"
    monkeypatch.setenv("BYOK_RELAY_TOKEN", "env-tok")
    assert load_token("https://r") == "env-tok"


# ---------------------------------------------------------------------------
# Summaries and contract enrichment
# ---------------------------------------------------------------------------

def test_parse_summaries_keeps_only_requested_ids():
    reply = 'Sure! {"file::a.py": "  Changed\\n a. ", "sym::x::y": "nope", "file::b.py": 3}'
    assert parse_summaries(reply, ["file::a.py", "file::b.py"]) == {"file::a.py": "Changed a."}
    assert parse_summaries("no json here", ["file::a.py"]) == {}


def test_summaries_cover_changed_nodes_and_never_change_topology(repo):
    artifact = artifact_for(repo)
    client = FakeClient()

    result = summarize_artifact(artifact, client, "claude-haiku-5-5")
    enriched = enrich_with_node_summaries(
        artifact, result.summaries, provider="anthropic", model="claude-haiku-5-5",
        llm_calls=result.llm_calls, prompt_ref="test", warnings=result.warnings,
    ).value

    assert set(result.summaries) == {
        "file::app.py", "file::NOTES.md", "sym::app.py::value", "sym::app.py::added",
    }  # unchanged symbols and import stubs are not requested
    assert result.llm_calls == 1 and result.warnings == []
    assert "+    return 2" in client.prompts[0]  # exact snapshot diff was sent
    before = artifact.value
    assert enriched["schema_version"] == "2.1"
    assert enriched["relationships"] == before["relationships"]
    assert [s["id"] for s in enriched["symbols"]] == [s["id"] for s in before["symbols"]]
    value = next(s for s in enriched["symbols"] if s["id"] == "sym::app.py::value")
    assert value["summary"]["text"] == "Summary of sym::app.py::value."
    assert value["summary"]["evidence"][1] == {
        "kind": "structural_basis", "symbol_ids": ["sym::app.py::value"],
    }
    metadata = enriched["metadata"]
    assert metadata["privacy_tier"] == "cloud_llm"
    assert metadata["cloud_providers_used"] == ["anthropic"]
    assert metadata["llm_calls"] == 1 and metadata["llm_model"] == "claude-haiku-5-5"


def test_relay_failures_become_scoped_warnings_but_missing_key_propagates(repo):
    artifact = artifact_for(repo)

    result = summarize_artifact(artifact, FakeClient(RelayTimeout("slow")), "gpt-5-mini")
    assert result.summaries == {} and result.llm_calls == 1
    assert {(w["code"], w["file"]) for w in result.warnings} == {
        ("LLM_TIMEOUT", "app.py"), ("LLM_TIMEOUT", "NOTES.md"),
    }
    enriched = enrich_with_node_summaries(
        artifact, {}, provider="openai", model="gpt-5-mini",
        llm_calls=result.llm_calls, warnings=result.warnings,
    ).value
    # Code left the machine even though no summary came back.
    assert enriched["metadata"]["privacy_tier"] == "cloud_llm"
    assert enriched["schema_version"] == "2.0"

    with pytest.raises(MissingProviderKey):
        summarize_artifact(artifact, FakeClient(MissingProviderKey("openai")), "gpt-5-mini")


def test_enrichment_rejects_unknown_ids_and_non_llm_warnings(repo):
    artifact = artifact_for(repo)
    with pytest.raises(ValueError, match="unknown node ids"):
        enrich_with_node_summaries(
            artifact, {"sym::ghost.py::x": "made up"}, provider="p", model="m", llm_calls=1
        )
    with pytest.raises(ValueError, match="only LLM_ERROR"):
        enrich_with_node_summaries(
            artifact, {}, provider="p", model="m", llm_calls=1,
            warnings=[{"code": "PARSE_FAILURE", "detail": "x"}],
        )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def test_cli_llm_json_keeps_stdout_pure_and_adds_summaries(repo, monkeypatch):
    monkeypatch.setenv("BYOK_RELAY_TOKEN", "tok")
    monkeypatch.setattr(RelayClient, "chat", lambda self, *a, **k: FakeClient().chat(*a, **k))

    result = CliRunner().invoke(
        cli.main, ["diff", "--format", "json", "--llm", "claude-haiku-5-5"]
    )

    assert result.exit_code == 0, result.output
    artifact = json.loads(result.stdout)
    assert artifact["schema_version"] == "2.1"
    assert "Summarizing with claude-haiku-5-5" in result.stderr


def test_cli_llm_html_report_embeds_summaries(repo, monkeypatch):
    monkeypatch.setenv("BYOK_RELAY_TOKEN", "tok")
    monkeypatch.setattr(RelayClient, "chat", lambda self, *a, **k: FakeClient().chat(*a, **k))
    destination = repo.parent / "report.html"

    result = CliRunner().invoke(
        cli.main, ["diff", "--llm", "gemini-2.5-flash", "-o", str(destination), "--no-open"]
    )

    assert result.exit_code == 0, result.output
    report = destination.read_text(encoding="utf-8")
    assert "Summary of sym::app.py::value." in report
    assert '"schema_version": "2.1"' in report or '"schema_version":"2.1"' in report


def test_cli_llm_terminal_shows_summaries_and_provenance(repo, monkeypatch):
    monkeypatch.setenv("BYOK_RELAY_TOKEN", "tok")
    monkeypatch.setattr(RelayClient, "chat", lambda self, *a, **k: FakeClient().chat(*a, **k))

    result = CliRunner().invoke(cli.main, ["diff", "--llm", "claude-haiku-5-5"])

    assert result.exit_code == 0, result.output
    assert "AI: Summary of sym::app.py::value." in result.stdout
    assert "AI: Summary of file::NOTES.md." in result.stdout
    assert "AI summaries: claude-haiku-5-5 via BYOK Relay (anthropic) · 1 call" in result.stdout
    assert "Optional: wild diff --llm" not in result.stdout


def test_cli_llm_without_token_fails_cleanly_when_not_interactive(repo):
    result = CliRunner().invoke(cli.main, ["diff", "--llm", "gemini-2.5-flash"])

    assert result.exit_code == 1
    assert "set BYOK_RELAY_TOKEN" in result.stderr


def test_cli_llm_first_run_registers_and_prompts_for_key(repo, monkeypatch):
    calls = []
    monkeypatch.setattr(cli, "_stdin_is_interactive", lambda: True)
    monkeypatch.setattr(RelayClient, "register", lambda self, app_id="wild-cli": setattr(self, "token", "new-tok") or "new-tok")
    monkeypatch.setattr(RelayClient, "store_key", lambda self, provider, key: calls.append((provider, key)))
    monkeypatch.setattr(RelayClient, "chat", lambda self, *a, **k: FakeClient().chat(*a, **k))

    result = CliRunner().invoke(cli.main, ["diff", "--llm", "gpt-5-mini"], input="sk-test-key-123\n")

    assert result.exit_code == 0, result.output
    assert calls == [("openai", "sk-test-key-123")]
    assert load_token("https://relay.byokrelay.com") == "new-tok"
    assert "sk-test-key-123" not in result.output


@pytest.mark.parametrize(
    "args",
    [["status", "--llm", "gpt-5-mini"], ["diff", "--format", "legacy-html", "--llm", "gpt-5-mini"]],
)
def test_cli_llm_usage_errors(args, repo):
    assert CliRunner().invoke(cli.main, args).exit_code == 2
