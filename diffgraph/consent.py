"""
Consent management for cloud-tier processors.

When a user runs `wild diff` with a processor that sends data to a cloud API,
they must explicitly consent once.  The decision is persisted to:

    ~/.config/wild/config.json

Local-tier processors (privacy_tier == "local") bypass this check entirely.

Usage
-----
    from diffgraph.consent import ensure_consent

    # Call before processor.analyze_changes().
    # Exits cleanly if the user declines.
    ensure_consent(processor.privacy_tier, processor.name)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Optional

import click

# ---------------------------------------------------------------------------
# Config storage
# ---------------------------------------------------------------------------

CONFIG_PATH = Path.home() / ".config" / "wild" / "config.json"

_CONSENT_KEY_MAP = {
    "cloud_llm":     "cloud_llm_consent_given",
    "cloud_backend": "cloud_backend_consent_given",
}


def _load_config() -> dict:
    if CONFIG_PATH.exists():
        try:
            return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def _save_config(updates: dict) -> None:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    config = _load_config()
    config.update(updates)
    CONFIG_PATH.write_text(json.dumps(config, indent=2), encoding="utf-8")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def has_consent(privacy_tier: str) -> bool:
    """
    Return True if the user has already consented (or if no consent is needed).

    Local-tier processors never require consent.
    """
    if privacy_tier == "local":
        return True
    consent_key = _CONSENT_KEY_MAP.get(privacy_tier)
    if consent_key is None:
        # Unknown tier — conservatively require consent.
        return False
    return bool(_load_config().get(consent_key))


def request_consent(privacy_tier: str, processor_name: str) -> bool:
    """
    Prompt the user for one-time consent.

    Prints a privacy notice, asks for confirmation, persists the decision, and
    returns True if the user consented.  Returns False (without raising) if the
    user declines.
    """
    tier_label = {
        "cloud_llm":     "a third-party LLM API (e.g. OpenAI)",
        "cloud_backend": "the WildestAI cloud backend",
    }.get(privacy_tier, "an external cloud service")

    click.echo(
        f"\n⚠  Privacy notice — '{processor_name}' mode\n"
        f"\n"
        f"   This processor sends your diff to {tier_label}.\n"
        f"   Your code will leave this machine.\n"
        f"\n"
        f"   You only need to answer this once.  Your choice is saved to:\n"
        f"   {CONFIG_PATH}\n"
    )

    if not click.confirm("   Continue?", default=False):
        click.echo(
            "\n   Consent declined.  No data was sent.\n"
            "\n"
            "   To analyze locally (no data leaves your machine):\n"
            "\n"
            "     wild diff\n"
            "\n"
            "   (Local structural analysis is the default — no flag needed.)\n"
        )
        return False

    consent_key = _CONSENT_KEY_MAP.get(privacy_tier)
    if consent_key:
        _save_config({consent_key: True})
    click.echo("   ✓ Consent recorded.  This prompt won't appear again.\n")
    return True


def ensure_consent(privacy_tier: str, processor_name: str) -> None:
    """
    Ensure the user has consented before running a cloud-tier processor.

    Exits cleanly (sys.exit(0)) if the user declines.  No-op for local-tier.
    """
    if has_consent(privacy_tier):
        return
    if not request_consent(privacy_tier, processor_name):
        sys.exit(0)
