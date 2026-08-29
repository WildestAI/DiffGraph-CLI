"""Canonical DiffGraph artifact contract and compatibility checks.

This module is intentionally independent of Git, tree-sitter, and AI/network
code so artifact consumers can validate DiffGraph data without importing any of
those subsystems.
"""
from __future__ import annotations

import json
import re
from copy import deepcopy
from dataclasses import dataclass
from importlib import resources
from typing import Any, Mapping, Tuple

SUPPORTED_SCHEMA_MAJOR = 2
CURRENT_SCHEMA_VERSION = "2.0"
_SCHEMA_RESOURCE = "schema/diffgraph-v2.schema.json"
_VERSION_PATTERN = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)$")


class DiffGraphContractError(ValueError):
    """Raised when an artifact cannot be proven to satisfy the contract."""


@dataclass(frozen=True, init=False)
class ValidatedArtifact:
    """An artifact that has passed the packaged canonical contract.

    Construction is intentionally restricted to :meth:`from_value` so callers
    cannot brand an unvalidated dictionary and bypass consumer checks.
    """

    _value: dict

    @classmethod
    def from_value(cls, artifact: dict) -> "ValidatedArtifact":
        """Validate an existing value once and brand it for trusted consumers."""
        artifact_copy = deepcopy(artifact)
        validate_artifact(artifact_copy)
        validated = object.__new__(cls)
        object.__setattr__(validated, "_value", artifact_copy)
        return validated

    @property
    def value(self) -> dict:
        """Return a defensive copy without exposing the validated state."""
        return deepcopy(self._value)


def enrich_with_prose(
    artifact: ValidatedArtifact,
    text: str,
    *,
    provider: str,
    model: str,
    confidence: float | None = None,
    prompt_ref: str | None = None,
) -> ValidatedArtifact:
    """Return a separately validated artifact with optional AI prose only.

    The supplied prose is deliberately limited to ``summary`` and its own
    provenance.  Files, symbols, and relationships are copied from the frozen
    deterministic artifact, so a provider cannot add, remove, or edit graph
    topology.  This helper performs no provider call and never receives a
    prompt or API credential.
    """
    if not isinstance(artifact, ValidatedArtifact):
        raise TypeError("enrich_with_prose requires a ValidatedArtifact")
    if not isinstance(text, str) or not text.strip():
        raise ValueError("summary text must be a non-empty string")
    if not isinstance(provider, str) or not provider.strip():
        raise ValueError("provider must be a non-empty string")
    if not isinstance(model, str) or not model.strip():
        raise ValueError("model must be a non-empty string")
    if confidence is not None and (
        isinstance(confidence, bool)
        or not isinstance(confidence, (int, float))
        or not 0 <= confidence <= 1
    ):
        raise ValueError("confidence must be a number from 0 through 1")
    if prompt_ref is not None and (not isinstance(prompt_ref, str) or not prompt_ref.strip()):
        raise ValueError("prompt_ref must be a non-empty string when provided")

    enriched = artifact.value
    llm_evidence = {"kind": "llm_inference", "model": model}
    if prompt_ref is not None:
        llm_evidence["prompt_ref"] = prompt_ref
    enriched["summary"] = {
        "text": text,
        "analysis_source": "inferred",
        "confidence": confidence,
        "evidence": [
            llm_evidence,
            {
                "kind": "structural_basis",
                "file_ids": [item["id"] for item in enriched["files"]],
                "symbol_ids": [item["id"] for item in enriched["symbols"]],
            },
        ],
    }
    metadata = enriched["metadata"]
    # The v2 contract has no combined tier. Retain a pre-existing backend
    # classification so enrichment never hides that the artifact's data also
    # left the machine through WildestAI's backend.
    if metadata.get("privacy_tier") != "cloud_backend":
        metadata["privacy_tier"] = "cloud_llm"
    metadata["cloud_providers_used"] = sorted(
        set(metadata.get("cloud_providers_used", [])) | {provider}
    )
    metadata["llm_calls"] = (metadata.get("llm_calls") or 0) + 1
    metadata["llm_model"] = model
    metadata["tiers_used"] = sorted(set(metadata.get("tiers_used", [])) | {"inferred"})
    return ValidatedArtifact.from_value(enriched)


def schema_version(value: object) -> Tuple[int, int]:
    """Parse and compatibility-check a DiffGraph ``MAJOR.MINOR`` version."""
    if not isinstance(value, str):
        raise DiffGraphContractError(
            "DiffGraph schema_version must use MAJOR.MINOR format; "
            f"received {value!r}"
        )
    match = _VERSION_PATTERN.fullmatch(value)
    if match is None:
        raise DiffGraphContractError(
            "DiffGraph schema_version must use MAJOR.MINOR format; "
            f"received {value!r}"
        )

    major, minor = (int(part) for part in match.groups())
    if major != SUPPORTED_SCHEMA_MAJOR:
        raise DiffGraphContractError(
            f"Unsupported DiffGraph schema major {major}; "
            f"this consumer supports major {SUPPORTED_SCHEMA_MAJOR}"
        )
    return major, minor


def load_schema() -> Mapping[str, Any]:
    """Load the packaged canonical schema, failing closed on missing/bad data."""
    try:
        schema_text = (
            resources.files("diffgraph").joinpath(_SCHEMA_RESOURCE).read_text(
                encoding="utf-8"
            )
        )
        schema = json.loads(schema_text)
    except (OSError, TypeError, json.JSONDecodeError) as error:
        raise DiffGraphContractError(
            f"could not load canonical DiffGraph schema: {error}"
        ) from error
    if not isinstance(schema, dict):
        raise DiffGraphContractError("canonical DiffGraph schema is not a JSON object")
    return schema


def validate_artifact(artifact: object) -> None:
    """Validate version compatibility and every canonical schema constraint.

    Minor versions within the supported major are accepted when they remain
    valid against this consumer's schema. Unknown majors, malformed versions,
    missing validator support, invalid packaged schemas, and invalid artifacts
    are all rejected.
    """
    if not isinstance(artifact, dict):
        raise DiffGraphContractError(
            f"DiffGraph artifact must be a JSON object; received {type(artifact).__name__}"
        )
    schema_version(artifact.get("schema_version"))

    try:
        import jsonschema
    except ImportError as error:
        raise DiffGraphContractError(
            "jsonschema is required to validate DiffGraph artifacts"
        ) from error

    schema = load_schema()
    try:
        validator_class = jsonschema.validators.validator_for(schema)
        validator_class.check_schema(schema)
        validator = validator_class(schema, format_checker=jsonschema.FormatChecker())
        error = next(iter(validator.iter_errors(artifact)), None)
    except jsonschema.SchemaError as error:
        raise DiffGraphContractError(
            f"canonical DiffGraph schema is invalid: {error.message}"
        ) from error

    if error is not None:
        location = ".".join(str(part) for part in error.absolute_path) or "<root>"
        raise DiffGraphContractError(
            f"DiffGraph artifact validation failed at {location}: {error.message}"
        ) from error
