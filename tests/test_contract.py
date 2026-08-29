"""Tests for the reusable, packaged DiffGraph artifact contract."""
from __future__ import annotations

import copy
import json
import subprocess
import sys
from importlib import resources

import pytest

import diffgraph.contract as contract
from diffgraph.contract import (
    CURRENT_SCHEMA_VERSION,
    SUPPORTED_SCHEMA_MAJOR,
    DiffGraphContractError,
    ValidatedArtifact,
    enrich_with_prose,
    load_schema,
    schema_version,
    validate_artifact,
)


@pytest.fixture
def golden_artifact():
    path = resources.files("diffgraph").joinpath(
        "schema/diffgraph-v2.structural.example.json"
    )
    return json.loads(path.read_text(encoding="utf-8"))


def test_packaged_schema_and_complete_golden_validate(golden_artifact):
    schema = load_schema()

    assert schema["$id"].endswith("/v2.0/schema.json")
    assert CURRENT_SCHEMA_VERSION == "2.0"
    assert SUPPORTED_SCHEMA_MAJOR == 2
    validate_artifact(golden_artifact)


def test_validated_artifact_cannot_bypass_validation():
    with pytest.raises(TypeError):
        ValidatedArtifact({})


def test_validated_artifact_isolated_from_mutation(golden_artifact):
    artifact = ValidatedArtifact.from_value(golden_artifact)
    original_path = artifact.value["files"][0]["path"]

    golden_artifact["files"][0]["path"] = "mutated-source.py"
    exposed_value = artifact.value
    exposed_value["files"][0]["path"] = "mutated-copy.py"

    assert artifact.value["files"][0]["path"] == original_path


def test_golden_contains_only_local_structural_claims(golden_artifact):
    assert golden_artifact["summary"] is None
    assert golden_artifact["metadata"]["privacy_tier"] == "local"
    assert golden_artifact["metadata"]["llm_calls"] == 0
    assert all(
        item["analysis_source"] == "structural"
        for collection in ("files", "symbols", "relationships")
        for item in golden_artifact[collection]
    )


def test_optional_prose_enrichment_cannot_mutate_frozen_topology(golden_artifact):
    frozen = ValidatedArtifact.from_value(golden_artifact)
    topology_before = {
        field: frozen.value[field]
        for field in ("files", "symbols", "relationships")
    }

    enriched = enrich_with_prose(
        frozen,
        "The deterministic graph shows one modified Python symbol.",
        provider="byok-openai",
        model="gpt-test",
        confidence=0.75,
        prompt_ref="summary-v1",
    )

    validate_artifact(enriched.value)
    assert frozen.value["summary"] is None
    assert {
        field: frozen.value[field]
        for field in ("files", "symbols", "relationships")
    } == topology_before
    assert {
        field: enriched.value[field]
        for field in ("files", "symbols", "relationships")
    } == topology_before
    assert enriched.value["summary"] == {
        "text": "The deterministic graph shows one modified Python symbol.",
        "analysis_source": "inferred",
        "confidence": 0.75,
        "evidence": [
            {"kind": "llm_inference", "model": "gpt-test", "prompt_ref": "summary-v1"},
            {
                "kind": "structural_basis",
                "file_ids": [item["id"] for item in topology_before["files"]],
                "symbol_ids": [item["id"] for item in topology_before["symbols"]],
            },
        ],
    }
    assert enriched.value["metadata"]["privacy_tier"] == "cloud_llm"
    assert enriched.value["metadata"]["cloud_providers_used"] == ["byok-openai"]
    assert enriched.value["metadata"]["llm_calls"] == 1
    assert enriched.value["metadata"]["llm_model"] == "gpt-test"
    assert enriched.value["metadata"]["tiers_used"] == ["inferred", "structural"]


def test_optional_prose_enrichment_preserves_cloud_backend_privacy(golden_artifact):
    golden_artifact["metadata"]["privacy_tier"] = "cloud_backend"
    frozen = ValidatedArtifact.from_value(golden_artifact)

    enriched = enrich_with_prose(
        frozen,
        "The deterministic graph has backend provenance.",
        provider="byok-openai",
        model="gpt-test",
    )

    assert enriched.value["metadata"]["privacy_tier"] == "cloud_backend"
    assert enriched.value["metadata"]["cloud_providers_used"] == ["byok-openai"]


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"text": "", "provider": "provider", "model": "model"}, "summary text"),
        ({"text": "summary", "provider": "", "model": "model"}, "provider"),
        ({"text": "summary", "provider": "provider", "model": ""}, "model"),
        ({"text": "summary", "provider": "provider", "model": "model", "confidence": 2}, "confidence"),
    ],
)
def test_optional_prose_enrichment_rejects_ambiguous_provenance(golden_artifact, kwargs, message):
    frozen = ValidatedArtifact.from_value(golden_artifact)

    with pytest.raises(ValueError, match=message):
        enrich_with_prose(frozen, **kwargs)


@pytest.mark.parametrize("value", [None, 2, "2", "v2", "2.0.0", "02.0", "2.-1"])
def test_schema_version_rejects_malformed_values(value):
    with pytest.raises(DiffGraphContractError, match=r"MAJOR\.MINOR"):
        schema_version(value)


def test_schema_version_rejects_unknown_major(golden_artifact):
    golden_artifact["schema_version"] = "3.0"

    with pytest.raises(DiffGraphContractError, match="Unsupported DiffGraph schema major 3"):
        validate_artifact(golden_artifact)


def test_supported_additive_minor_is_accepted_when_schema_valid(golden_artifact):
    golden_artifact["schema_version"] = "2.17"

    validate_artifact(golden_artifact)


def test_supported_minor_still_rejects_schema_invalid_artifact(golden_artifact):
    artifact = copy.deepcopy(golden_artifact)
    artifact["schema_version"] = "2.17"
    del artifact["metadata"]["privacy_tier"]

    with pytest.raises(DiffGraphContractError, match="artifact validation failed"):
        validate_artifact(artifact)


def test_invalid_packaged_schema_fails_closed(golden_artifact, monkeypatch):
    monkeypatch.setattr(
        contract,
        "load_schema",
        lambda: {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "type": 123,
        },
    )

    with pytest.raises(DiffGraphContractError, match="canonical DiffGraph schema is invalid"):
        validate_artifact(golden_artifact)


def test_formatter_import_and_validation_do_not_load_ai_modules():
    script = """
import json
import sys
from importlib import resources
from diffgraph.formatters.terminal import TerminalFormatter
artifact = json.loads(resources.files('diffgraph').joinpath(
    'schema/diffgraph-v2.structural.example.json'
).read_text(encoding='utf-8'))
TerminalFormatter(artifact)
assert 'diffgraph.ai_analysis' not in sys.modules
assert 'agents' not in sys.modules
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
