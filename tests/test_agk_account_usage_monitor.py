import asyncio
import importlib.util
import json
import sys
from pathlib import Path


MODULE = Path(__file__).resolve().parents[1] / "hermes/plugins/platforms/discord/agk_account_usage_monitor.py"
spec = importlib.util.spec_from_file_location("agk_account_usage_monitor", MODULE)
assert spec and spec.loader
monitor = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = monitor
spec.loader.exec_module(monitor)


def test_remaining_bar_is_bounded_and_represents_remaining_credit():
    assert monitor.remaining_bar(93) == "█████████░"
    assert monitor.remaining_bar(6) == "█░░░░░░░░░"
    assert monitor.remaining_bar(150) == "██████████"


def test_provider_panel_uses_only_account_number_id_status_and_usage():
    accounts = [monitor.AccountSnapshot(
        index=1,
        credential_id="7dac56",
        status="ok",
        windows=(monitor.UsageWindow("Session", 93.0, "2026-09-02T09:15:13+00:00"),),
    )]
    text = monitor.render_provider_panel("OpenAI Codex", accounts)
    assert "Account 1 [`7dac56`]" in text
    assert "93% remaining" in text
    assert "email" not in text.lower()
    assert "token" not in text.lower()


def test_monitor_config_uses_requested_channels_and_light_interval():
    cfg = monitor.MonitorConfig.from_extra({
        "usage_monitor_channel_id": 1542505218569150585,
        "usage_monitor_openai_channel_id": 1542505478679171164,
        "usage_monitor_interval_seconds": 300,
    })
    assert cfg.summary_or_category_id == 1542505218569150585
    assert cfg.openai_channel_id == 1542505478679171164
    assert cfg.interval_seconds == 300
    assert cfg.interval_seconds >= 180


def test_summary_panel_reports_all_pool_health_without_secrets():
    openai = [monitor.AccountSnapshot(1, "7dac56", "ok", (monitor.UsageWindow("Session", 93, None),))]
    claude = [monitor.AccountSnapshot(1, "420097", "ok", (monitor.UsageWindow("Current week", 96, None),))]
    text = monitor.render_summary(openai, claude)
    assert "OpenAI" in text and "Claude Code" in text
    assert "1/1 healthy" in text
    assert "93%" in text and "96%" in text


def test_unknown_account_without_usage_is_not_counted_healthy():
    text = monitor.render_summary([monitor.AccountSnapshot(1, "unknown1", "unknown", ())], [])
    assert "OpenAI** · 0/1 healthy" in text


def test_state_file_contract_is_profile_local_and_contains_only_message_ids(tmp_path):
    store = monitor.MessageStateStore(tmp_path)
    store.save({
        "summary": 1,
        "openai": 2,
        "claude": 3,
        "voice-owner:openai-codex:agentik": 4,
    })
    assert store.load() == {
        "summary": 1,
        "openai": 2,
        "claude": 3,
        "voice-owner:openai-codex:agentik": 4,
    }
    assert (tmp_path / "discord_usage_monitor.json").stat().st_mode & 0o777 == 0o600


def test_discord_adapter_starts_and_stops_usage_monitor():
    adapter = (Path(__file__).resolve().parents[1] / "hermes/plugins/platforms/discord/adapter.py").read_text(encoding="utf-8")
    assert "DiscordAccountUsageMonitor" in adapter
    assert "_account_usage_monitor.start()" in adapter
    assert "await self._account_usage_monitor.stop()" in adapter


def test_future_install_configures_requested_monitor_channels():
    root = Path(__file__).resolve().parents[1]
    source = "\n".join((root / path).read_text(encoding="utf-8") for path in ("scripts/sync-hermes.sh", "install.sh"))
    assert "1542505218569150585" in source
    assert "1542505478679171164" in source
    assert "usage_monitor_interval_seconds" in source


def test_alias_registry_joins_owner_names_by_stable_credential_id(tmp_path):
    (tmp_path / "provider-account-aliases.json").write_text(json.dumps({
        "providers": {
            "openai-codex": [
                {"credential_id": "ff5cab", "owner_nickname": "Agentik"},
                {"credential_id": "6aedd9", "owner_nickname": "Simono"},
            ],
            "anthropic": [
                {"credential_id": "420097", "owner_nickname": "Loumna"},
            ],
        }
    }))

    aliases = monitor.load_owner_aliases(tmp_path)

    assert aliases["openai-codex"]["ff5cab"] == "Agentik"
    assert aliases["openai-codex"]["6aedd9"] == "Simono"
    assert aliases["anthropic"]["420097"] == "Loumna"


def test_voice_channel_name_uses_owner_session_name_and_primary_used_percent():
    account = monitor.AccountSnapshot(
        index=1,
        credential_id="ff5cab",
        status="ok",
        windows=(monitor.UsageWindow("Session", 77.0, None),),
        owner_name="Agentik",
    )
    assert monitor.voice_channel_name("OpenAI", account) == "Agentik-OpenAI : 23%"
    assert monitor.voice_channel_name(
        "Claude",
        monitor.AccountSnapshot(2, "420097", "unknown", (), owner_name="Loumna"),
    ) == "Loumna-Claude : ?%"


def test_collect_snapshots_applies_aliases_by_id_not_pool_order(monkeypatch):
    entries = [
        type("Entry", (), {"id": "7dac56", "last_status": "ok", "access_token": None, "base_url": None})(),
        type("Entry", (), {"id": "ff5cab", "last_status": "ok", "access_token": None, "base_url": None})(),
    ]
    monkeypatch.setattr("agent.credential_pool.load_pool", lambda _provider: type("Pool", (), {"entries": lambda self: entries})())

    rows = monitor.collect_provider_snapshots(
        "openai-codex",
        aliases={"ff5cab": "Agentik", "7dac56": "MoonBaseCapital"},
    )

    assert [(row.credential_id, row.owner_name) for row in rows] == [
        ("7dac56", "MoonBaseCapital"),
        ("ff5cab", "Agentik"),
    ]


def test_collect_snapshots_refreshes_expired_claude_pool_entries_before_usage(monkeypatch):
    stale = type("Entry", (), {
        "id": "420097", "last_status": None, "access_token": "stale", "base_url": None,
    })()
    fresh = type("Entry", (), {
        "id": "420097", "last_status": None, "access_token": "fresh", "base_url": None,
    })()

    class Pool:
        def entries(self):
            return [stale]

        def _entry_needs_refresh(self, entry):
            return entry is stale

        def _refresh_entry(self, entry, *, force):
            assert entry is stale and force is False
            return fresh

    monkeypatch.setattr("agent.credential_pool.load_pool", lambda _provider: Pool())
    calls = []

    def fake_fetch(provider, *, base_url=None, api_key=None):
        calls.append((provider, api_key))
        return type("Usage", (), {
            "windows": (type("Window", (), {
                "used_percent": 4.0, "label": "Current session", "reset_at": None,
            })(),),
        })()

    monkeypatch.setattr("agent.account_usage.fetch_account_usage", fake_fetch)

    rows = monitor.collect_provider_snapshots("anthropic", aliases={"420097": "Loumna"})

    assert calls == [("anthropic", "fresh")]
    assert rows[0].owner_name == "Loumna"
    assert rows[0].windows[0].remaining_percent == 96.0


class _FakeVoiceChannel:
    def __init__(self, channel_id, name, category=None):
        self.id = channel_id
        self.name = name
        self.category = category
        self.edits = []

    async def edit(self, *, name, reason):
        self.name = name
        self.edits.append((name, reason))
        return self


class _FakeGuild:
    def __init__(self):
        self.created = []
        self.next_id = 9000

    async def create_voice_channel(self, name, *, category, reason):
        channel = _FakeVoiceChannel(self.next_id, name, category)
        self.next_id += 1
        category.channels.append(channel)
        self.created.append((channel, reason))
        return channel


class _FakeCategory:
    def __init__(self, channels):
        self.channels = channels
        self.guild = _FakeGuild()
        for channel in channels:
            channel.category = self


class _FakeClient:
    def __init__(self, channels):
        self.channels = {channel.id: channel for channel in channels}

    def get_channel(self, channel_id):
        return self.channels.get(channel_id)

    async def fetch_channel(self, channel_id):
        return self.channels.get(channel_id)


def test_voice_channel_sync_reuses_seed_creates_per_account_and_skips_unchanged_names(tmp_path):
    seed = _FakeVoiceChannel(1542505478679171164, "Agentik-OpenAI : 94%")
    category = _FakeCategory([seed])
    client = _FakeClient([seed])
    usage_monitor = monitor.DiscordAccountUsageMonitor(
        client,
        monitor.MonitorConfig(1542505218569150585, seed.id),
        monitor.MessageStateStore(tmp_path),
    )
    rows = [
        monitor.AccountSnapshot(1, "ff5cab", "ok", (monitor.UsageWindow("Session", 77, None),), owner_name="Agentik"),
        monitor.AccountSnapshot(2, "6aedd9", "ok", (monitor.UsageWindow("Session", 52, None),), owner_name="Simono"),
    ]
    state = {}

    asyncio.run(usage_monitor._sync_voice_channels(
        category, "openai-codex", "OpenAI", rows, state, seed_channel=seed
    ))
    asyncio.run(usage_monitor._sync_voice_channels(
        category, "openai-codex", "OpenAI", rows, state, seed_channel=seed
    ))

    assert seed.name == "Agentik-OpenAI : 23%"
    assert len(seed.edits) == 1
    assert [item[0].name for item in category.guild.created] == ["Simono-OpenAI : 48%"]
    assert state["voice-owner:openai-codex:agentik"] == seed.id
    assert state["voice-owner:openai-codex:simono"] == 9000


def test_voice_channel_sync_migrates_legacy_credential_binding_to_owner_key(tmp_path):
    existing = _FakeVoiceChannel(321, "Old quota name")
    category = _FakeCategory([existing])
    usage_monitor = monitor.DiscordAccountUsageMonitor(
        _FakeClient([existing]),
        monitor.MonitorConfig(123, 456),
        monitor.MessageStateStore(tmp_path),
    )
    account = monitor.AccountSnapshot(
        1,
        "ff5cab",
        "ok",
        (monitor.UsageWindow("Session", 77, None),),
        owner_name="Agentik",
    )
    state = {"voice:openai-codex:ff5cab": existing.id}

    asyncio.run(usage_monitor._sync_voice_channels(
        category, "openai-codex", "OpenAI", [account], state
    ))

    assert state == {"voice-owner:openai-codex:agentik": existing.id}
    assert existing.name == "Agentik-OpenAI : 23%"
