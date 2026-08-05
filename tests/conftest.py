import os

import pytest


@pytest.fixture(autouse=True)
def isolate_git_configuration(monkeypatch):
    """Keep repository fixtures independent of user and system Git config."""

    monkeypatch.setenv("GIT_CONFIG_GLOBAL", os.devnull)
    monkeypatch.setenv("GIT_CONFIG_SYSTEM", os.devnull)
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
