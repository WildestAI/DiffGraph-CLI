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


def test_golden_contains_only_local_structural_claims(golden_artifact):
    assert golden_artifact["summary"] is None
    assert golden_artifact["metadata"]["privacy_tier"] == "local"
    assert golden_artifact["metadata"]["llm_calls"] == 0
    assert all(
        item["analysis_source"] == "structural"
        for collection in ("files", "symbols", "relationships")
        for item in golden_artifact[collection]
    )


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
