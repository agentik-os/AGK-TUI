from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
HERMES = ROOT / "hermes"


def test_discord_exposes_nutrition_as_primary_command_and_food_alias():
    plugin = (HERMES / "plugins/agentik_os/__init__.py").read_text(encoding="utf-8")
    assert '"nutrition"' in plugin
    assert '"food"' in plugin
    assert "Nutrition OS" in plugin


def test_specialist_uses_nutrition_os_profile_identity():
    manifest = yaml.safe_load(
        (HERMES / "agents/nutrition-specialist/agent.yaml").read_text(encoding="utf-8")
    )
    assert manifest["id"] == "nutrition-specialist"
    assert manifest["profile"] == "nutrition-os"
    assert manifest["os"] == ["nutrition-os@1.0.1"]
    assert manifest["launcher"].endswith("/nutrition-os-hermes")


def test_nutrition_command_uses_the_dedicated_nutrition_os_profile():
    command = (HERMES / "plugins/agentik_os/nutrition_command.py").read_text(encoding="utf-8")
    assert 'profiles/nutrition-os/data/nutrition-os' in command
    assert 'profiles/nutrition-os").resolve()' in command
    assert 'profiles/nutrition/data/nutrition-os' not in command


def test_agentik_commands_fall_back_when_invocation_context_api_is_unavailable():
    commands = (HERMES / "plugins/agentik_os/commands.py").read_text(encoding="utf-8")
    assert "def _plugin_command_invocation()" in commands
    assert commands.count("get_plugin_command_invocation_context") == 2
    assert "except (ImportError, AttributeError):" in commands
    assert "return _plugin_command_invocation()" in commands


def test_global_rule_defines_everywhere_as_hermes_agk_discord():
    rules = yaml.safe_load(Path("/etc/agk-terminal/rules.yaml").read_text(encoding="utf-8"))["rules"]
    scope_rule = next(rule for rule in rules if rule["id"] == "agk-everywhere-scope")
    content = scope_rule["content"].lower()
    assert all(layer in content for layer in ("hermes", "agk", "discord"))
    assert "station" in content


def test_global_rule_publishes_actionable_links_to_contextual_discord_channel():
    for rules_path in (
        Path("/etc/agk-terminal/rules.yaml"),
        Path(__file__).resolve().parents[1] / "config" / "rules.yaml",
    ):
        rules = yaml.safe_load(rules_path.read_text(encoding="utf-8"))["rules"]
        link_rule = next(rule for rule in rules if rule["id"] == "discord-actionable-links")
        content = link_rule["content"].lower()
        assert link_rule["enabled"] is True
        assert all(term in content for term in ("clickable", "dedicated", "#general", "client", "secret"))
