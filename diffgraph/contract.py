"""Canonical DiffGraph artifact contract and compatibility checks.

This module is intentionally independent of Git, tree-sitter, and AI/network
code so artifact consumers can validate DiffGraph data without importing any of
those subsystems.
"""
from __future__ import annotations

import json
import re
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

    value: dict

    @classmethod
    def from_value(cls, artifact: dict) -> "ValidatedArtifact":
        """Validate an existing value once and brand it for trusted consumers."""
        validate_artifact(artifact)
        validated = object.__new__(cls)
        object.__setattr__(validated, "value", artifact)
        return validated


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
