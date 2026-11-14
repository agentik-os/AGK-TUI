"""The Agentik OS Hermes plugin against the Hermes command contract."""

import importlib
import inspect
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def plugin(tmp_path, monkeypatch):
    """Import the plugin package with the two Hermes modules it needs."""
    config = types.ModuleType("hermes_cli.config")
    config.read_raw_config = lambda: {}
    hermes_cli = types.ModuleType("hermes_cli")
    hermes_cli.config = config
    registry = types.ModuleType("tools.registry")
    registry.tool_error = lambda message, **_: {"error": message}
    registry.tool_result = lambda payload=None, **_: payload
    tools = types.ModuleType("tools")
    tools.registry = registry
    for name, module in (("hermes_cli", hermes_cli), ("hermes_cli.config", config),
                         ("tools", tools), ("tools.registry", registry)):
        monkeypatch.setitem(sys.modules, name, module)
    monkeypatch.syspath_prepend(str(ROOT / "hermes" / "plugins"))
    for name in [name for name in sys.modules if name.split(".")[0] == "agentik_os"]:
        monkeypatch.delitem(sys.modules, name)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("AGK_ENV_CONFIG", str(tmp_path / "environment.yaml"))
    for name in ("AGK_ENVIRONMENT", "AGENTIK_ENVIRONMENT", "AGK_TERMINAL_ROOT", "AGK_RULES_CONFIG"):
        monkeypatch.delenv(name, raising=False)
    return importlib.import_module("agentik_os")


def invoke(handler, raw_args, **context):
    """Hermes' own call rule: pass the context keywords a handler accepts."""
    parameters = list(inspect.signature(handler).parameters.values())[1:]
    if any(item.kind is inspect.Parameter.VAR_KEYWORD for item in parameters):
        return handler(raw_args, **context)
    accepted = {item.name for item in parameters}
    return handler(raw_args, **{key: value for key, value in context.items() if key in accepted})


def test_commands_use_the_context_hermes_passes_to_handlers(plugin, tmp_path):
    (tmp_path / "environment.yaml").write_text(
        "environment: agentik\nprojects_root: ~/code\n", encoding="utf-8")
    commands = importlib.import_module("agentik_os.commands")
    service = commands.AgentikCommandService.from_runtime()
    # A single-user install declares its environment in AGK's own config.
    assert service.environment == "agentik"
    assert "project" in service.command_names

    cli = dict(source=None, session_id="S-1", session_key="S-1", platform="cli")
    active = invoke(service.handler("active"), "", **cli)
    assert "failed safely" not in active
    assert "Surface: local" in active and "Session: S-1" in active

    # Projects are created where this install keeps its projects.
    created = invoke(service.handler("project"), "new Demo", **cli)
    assert "failed safely" not in created and not created.startswith("Error")
    assert (tmp_path / "code/demo").is_dir()
    assert "Demo" in invoke(service.handler("active"), "", **cli)
    # The local terminal keeps one context across its sessions…
    assert "Demo" in invoke(
        service.handler("active"), "", **{**cli, "session_id": "S-2", "session_key": "S-2"})
    # …while every chat on a messaging platform has its own.
    chat = dict(source=object(), session_id="D-1", session_key="discord:42", platform="discord")
    elsewhere = invoke(service.handler("active"), "", **chat)
    assert "Surface: discord" in elsewhere and "Demo" not in elsewhere
    assert service.invocation() == {}


def test_environment_and_launcher_resolve_without_a_login_shell(plugin, tmp_path, monkeypatch):
    commands = importlib.import_module("agentik_os.commands")
    paths = importlib.import_module("agentik_os.paths")
    assert commands.configured_environment({}, tmp_path) == "unknown"
    assert commands.configured_environment(
        {"runtime_identity": {"environment_id": "mission"}}, tmp_path) == "mission"
    monkeypatch.setenv("AGK_ENVIRONMENT", "private")
    assert commands.configured_environment({}, tmp_path) == "private"
    monkeypatch.setenv("AGK_ENVIRONMENT", "root")
    assert commands.configured_environment({}, tmp_path) == "unknown"

    # launchd and systemd start the gateway without the user's PATH.
    monkeypatch.setenv("PATH", "/nonexistent")
    assert paths.agk_executable() == "/usr/local/bin/agk"
    launcher = tmp_path / ".local/bin/agk"
    launcher.parent.mkdir(parents=True)
    launcher.write_text("#!/bin/sh\n", encoding="utf-8")
    assert paths.agk_executable() == str(launcher)

    rules = importlib.import_module("agentik_os.rules")
    installed = tmp_path / ".local/lib/agk-terminal/config/rules.yaml"
    installed.parent.mkdir(parents=True)
    installed.write_text(
        "rules:\n  - id: a\n    title: A\n    enabled: true\n    providers: ['*']\n    content: keep\n",
        encoding="utf-8")
    assert [rule["id"] for rule in rules.active_rules()] == ["a"]
