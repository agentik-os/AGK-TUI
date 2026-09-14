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


@pytest.mark.parametrize("status", ["ok", "exhausted", "dead", "reconnect required"])
def test_roster_renderer_preserves_every_safe_account_state(status):
    account_control = load_account_control()
    record = account_control.AccountRecord(
        "openai-codex", "ff5cab", "Agentik", status, 0, ()
    )

    rendered = account_control.render_account_roster([record])

    assert f"`{status}`" in rendered


def test_roster_renderer_uses_provider_labels_and_complete_usage_output():
    account_control = load_account_control()
    records = [
        account_control.AccountRecord(
            "openai-codex",
            "ff5cab",
            "Agentik",
            "ok",
            1,
            (account_control.UsageWindow("Session", 77, "2026-08-28T00:00:00+00:00"),),
        ),
        account_control.AccountRecord(
            "anthropic",
            "420097",
            "Loumna",
            "reconnect required",
            2,
            (account_control.UsageWindow("Current week", 96, None),),
        ),
    ]

    rendered = account_control.render_account_roster(records)

    assert rendered == (
        "# Station · Account roster\n"
        "\n"
        "**Agentik** · `OpenAI` · `ff5cab` · `ok` · priority 1\n"
        "- Session · 23% used · 77% remaining · resets 2026-08-28T00:00:00+00:00\n"
        "\n"
        "**Loumna** · `Claude` · `420097` · `reconnect required` · priority 2\n"
        "- Current week · 4% used · 96% remaining\n"
    )


def test_roster_renderer_normalizes_untrusted_public_fields():
    account_control = load_account_control()
    record = account_control.AccountRecord(
        provider="<@provider>",
        credential_id="eyJhbGciOiJIUzI1NiJ9.payload.signature",
        owner_name="owner@example.com",
        status="**ok**",
        priority="sk-proj-abcdefghijklmnopqrstuvwxyz123456",
        windows=(
            account_control.UsageWindow(
                "**<@unsafe>**",
                50,
                "sk-proj-abcdefghijklmnopqrstuvwxyz123456",
            ),
        ),
    )

    rendered = account_control.render_account_roster([record])

    assert "Unassigned" in rendered
    assert "Unknown provider" in rendered
    assert "`unknown`" in rendered
    assert "- Limit" in rendered
    assert "@" not in rendered
    assert "eyJ" not in rendered
    assert "sk-proj" not in rendered
    assert "**ok**" not in rendered


@pytest.mark.parametrize("unsafe_label", ["sk-proj-allowedchars123", "__hidden__"])
def test_roster_renderer_rejects_secret_and_underscore_markdown_usage_labels(
    unsafe_label,
):
    account_control = load_account_control()
    record = account_control.AccountRecord(
        "openai-codex",
        "ff5cab",
        "Agentik",
        "ok",
        0,
        (account_control.UsageWindow(unsafe_label, 50, None),),
    )

    rendered = account_control.render_account_roster([record])

    assert unsafe_label not in rendered
    assert "- Limit · 50% used · 50% remaining" in rendered


def test_owner_nickname_rejects_underscore_markdown_at_registry_and_render_boundaries(
    tmp_path,
):
    account_control = load_account_control()
    registry = account_control.AliasRegistry(tmp_path / "provider-account-aliases.json")

    with pytest.raises(ValueError, match="owner_name"):
        registry.bind("openai-codex", "admin_user", "ff5cab")

    rendered = account_control.render_account_roster(
        [account_control.AccountRecord("openai-codex", "ff5cab", "admin_user", "ok", 0, ())]
    )
    assert "admin_user" not in rendered
    assert "**Unassigned**" in rendered


def test_alias_registry_rebinds_nickname_atomically(tmp_path):
    account_control = load_account_control()
    registry = account_control.AliasRegistry(tmp_path / "provider-account-aliases.json")
    registry.bind("openai-codex", "Agentik", "old123")
    registry.bind("openai-codex", "Agentik", "new456")

    assert registry.credential_id("openai-codex", "Agentik") == "new456"
    assert registry.owner_name("openai-codex", "old123") is None
    assert registry.path.stat().st_mode & 0o777 == 0o600
    assert not registry.path.with_name(f".{registry.path.name}.new").exists()


def test_alias_registry_repairs_existing_permissive_mode_before_read(tmp_path):
    account_control = load_account_control()
    path = tmp_path / "provider-account-aliases.json"
    path.write_text(
        '{"providers":{"openai-codex":[{"credential_id":"ff5cab","owner_nickname":"Agentik"}]}}',
        encoding="utf-8",
    )
    path.chmod(0o644)

    snapshot = account_control.AliasRegistry(path).snapshot()

    assert snapshot == {"openai-codex": {"ff5cab": "Agentik"}}
    assert path.stat().st_mode & 0o777 == 0o600


def test_alias_registry_rejects_unsafe_owner_nicknames(tmp_path):
    account_control = load_account_control()
    registry = account_control.AliasRegistry(tmp_path / "provider-account-aliases.json")
    unsafe_names = [
        "owner@example.com",
        "<@123456789>",
        "**admin**",
        "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0In0.signature",
        "sk-proj-abcdefghijklmnopqrstuvwxyz123456",
        "line\nbreak",
    ]

    for owner_name in unsafe_names:
        with pytest.raises(ValueError, match="owner_name"):
            registry.bind("openai-codex", owner_name, "ff5cab")


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


def test_prefer_eligible_credential_reorders_atomically_and_reads_back():
    module = load_account_control()
    written = []

    class Entry:
        def __init__(self, credential_id, priority, status="ok"):
            self.id = credential_id
            self.priority = priority
            self.last_status = status

        def to_dict(self):
            return {"id": self.id, "priority": self.priority, "last_status": self.last_status}

    current = [Entry("first", 0), Entry("second", 1)]

    def load(_provider):
        rows = current if not written else [
            Entry(row["id"], row["priority"], row.get("last_status")) for row in written[-1]
        ]
        return type("Pool", (), {"entries": lambda self: rows})()

    def write(_provider, rows):
        written.append(rows)

    status = module.prefer_eligible_credential(
        "openai-codex", "second", pool_loader=load, pool_writer=write
    )

    assert status == "saved"
    assert [(row["id"], row["priority"]) for row in written[-1]] == [
        ("second", 0), ("first", 1),
    ]


def test_prefer_eligible_credential_rejects_missing_or_unavailable():
    module = load_account_control()

    class Entry:
        id = "exhausted"
        priority = 0
        last_status = "exhausted"

        def to_dict(self):
            return {"id": self.id, "priority": self.priority, "last_status": self.last_status}

    load = lambda _provider: type("Pool", (), {"entries": lambda self: [Entry()]})()
    writer = lambda *_args: (_ for _ in ()).throw(AssertionError("must not write"))

    assert module.prefer_eligible_credential(
        "openai-codex", "missing", pool_loader=load, pool_writer=writer
    ) == "missing"
    assert module.prefer_eligible_credential(
        "openai-codex", "exhausted", pool_loader=load, pool_writer=writer
    ) == "unavailable"
