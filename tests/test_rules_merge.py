import importlib.util
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]


def load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_system_rules_are_merged_with_profile_overrides(tmp_path, monkeypatch):
    system = tmp_path / "system.yaml"
    user = tmp_path / "home" / ".agentik" / "rules.yaml"
    user.parent.mkdir(parents=True)
    system.write_text(yaml.safe_dump({"rules": [
        {"id": "global", "enabled": True, "content": "global rule"},
        {"id": "shared", "enabled": True, "content": "system value"},
    ]}))
    user.write_text(yaml.safe_dump({"rules": [
        {"id": "shared", "enabled": True, "content": "profile value"},
        {"id": "local", "enabled": True, "content": "local rule"},
    ]}))
    monkeypatch.setenv("HOME", str(tmp_path / "home"))

    sync = load(ROOT / "scripts" / "sync-rules.py", "sync_rules_test")
    merged = sync.load_effective_rules(system_path=system, user_path=user)
    by_id = {rule["id"]: rule for rule in merged}
    assert by_id["global"]["content"] == "global rule"
    assert by_id["shared"]["content"] == "profile value"
    assert by_id["local"]["content"] == "local rule"

    plugin_source = (ROOT / "hermes" / "plugins" / "agentik_os" / "rules.py").read_text()
    assert "_merge_rules" in plugin_source
    assert "/etc/agk-terminal/rules.yaml" in plugin_source


def test_global_rules_require_gateway_reconnect_continuation():
    document = yaml.safe_load((ROOT / "config" / "rules.yaml").read_text(encoding="utf-8"))
    rules = {rule["id"]: rule for rule in document["rules"]}
    rule = rules["resume-interrupted-work-after-gateway-reconnect"]
    content = rule["content"].lower()
    assert rule["enabled"] is True
    assert "automatically resume" in content
    assert "durable" in content
    assert "restart/shutdown" in content
    assert "explicitly stops" in content
    assert "first unfinished step" in content
