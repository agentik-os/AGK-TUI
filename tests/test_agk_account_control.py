import importlib.util
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest


MODULE = Path(__file__).resolve().parents[1] / "hermes/plugins/platforms/discord/agk_account_control.py"


def load_account_control():
    assert MODULE.exists(), "canonical account-control module does not exist"
    spec = importlib.util.spec_from_file_location("agk_account_control", MODULE)
    assert spec and spec.loader
    loaded = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = loaded
    spec.loader.exec_module(loaded)
    return loaded


@pytest.fixture
def fake_pool():
    entry = type(
        "Entry",
        (),
        {
            "id": "ff5cab",
            "label": "owner@example.com",
            "access_token": "private-access-token",
            "runtime_api_key": None,
            "base_url": None,
            "last_status": "ok",
            "priority": 7,
        },
    )()

    def load(provider):
        entries = [entry] if provider == "openai-codex" else []
        return type("Pool", (), {"entries": lambda self: entries})()

    return load


def test_roster_joins_nickname_by_stable_id_and_redacts_private_fields(
    tmp_path, fake_pool, monkeypatch
):
    account_control = load_account_control()
    registry = account_control.AliasRegistry(tmp_path / "provider-account-aliases.json")
    registry.replace({"openai-codex": {"ff5cab": "Agentik"}})
    usage = type(
        "Usage",
        (),
        {
            "windows": (
                type(
                    "Window",
                    (),
                    {
                        "label": "Session",
                        "used_percent": 23.0,
                        "reset_at": datetime(2026, 8, 28, tzinfo=timezone.utc),
                    },
                )(),
            )
        },
    )()
    monkeypatch.setattr(account_control, "fetch_account_usage", lambda *args, **kwargs: usage)

    records = account_control.load_account_roster(tmp_path, pool_loader=fake_pool)

    assert records[0].owner_name == "Agentik"
    assert records[0].priority == 7
    rendered = account_control.render_account_roster(records)
    assert "Agentik" in rendered and "ff5cab" in rendered
    assert "Session" in rendered and "77% remaining" in rendered
    assert "2026-08-28T00:00:00+00:00" in rendered
    assert "@" not in rendered
    assert "access_token" not in rendered
    assert "private-access-token" not in rendered


def test_alias_registry_rebinds_nickname_atomically(tmp_path):
    account_control = load_account_control()
    registry = account_control.AliasRegistry(tmp_path / "provider-account-aliases.json")
    registry.bind("openai-codex", "Agentik", "old123")
    registry.bind("openai-codex", "Agentik", "new456")

    assert registry.credential_id("openai-codex", "Agentik") == "new456"
    assert registry.owner_name("openai-codex", "old123") is None
    assert registry.path.stat().st_mode & 0o777 == 0o600
    assert not registry.path.with_name(f".{registry.path.name}.new").exists()


def test_alias_registry_removes_credential_without_touching_other_owners(tmp_path):
    account_control = load_account_control()
    registry = account_control.AliasRegistry(tmp_path / "provider-account-aliases.json")
    registry.replace({"openai-codex": {"old123": "Agentik", "keep456": "Simono"}})

    registry.remove_credential("openai-codex", "old123")

    assert registry.snapshot() == {"openai-codex": {"keep456": "Simono"}}


def test_voice_binding_key_is_owner_keyed_and_case_insensitive():
    account_control = load_account_control()
    assert account_control.voice_binding_key("openai-codex", "Agentik") == (
        "voice-owner:openai-codex:agentik"
    )
