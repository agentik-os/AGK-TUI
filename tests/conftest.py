"""Shared test isolation.

A developer machine exports AGK settings from its shell profile (for example
`AGK_ENVIRONMENT=agentik`). Tests describe product behavior from explicit
inputs, so ambient AGK configuration must never decide their outcome.
"""

from __future__ import annotations

import os

import pytest

_AMBIENT = (
    "AGK_ENVIRONMENT",
    "AGK_ENV_CONFIG",
    "AGK_TERMINAL_ROOT",
    "AGK_RULES_CONFIG",
    "AGK_AGENT_CATALOG",
    "AGK_OS_REGISTRY",
    "AGK_TOPOLOGY_STATUS",
    "AGK_OPENROUTER_MODEL",
    "HERMES_HOME",
)


@pytest.fixture(autouse=True)
def _no_ambient_agk_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in _AMBIENT:
        monkeypatch.delenv(name, raising=False)


# The subprocess-based tests inherit os.environ directly at import time in a
# few modules, so the process environment is cleaned as well.
for _name in _AMBIENT:
    os.environ.pop(_name, None)
