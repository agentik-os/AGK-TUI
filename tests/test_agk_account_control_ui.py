from __future__ import annotations

import importlib.util
import json
import stat
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
UI_MODULE = ROOT / "hermes/plugins/platforms/discord/agk_account_control_ui.py"
DISCORD_DIR = UI_MODULE.parent
sys.path.insert(0, str(DISCORD_DIR))

assert UI_MODULE.exists(), "agk_account_control_ui.py does not exist"
spec = importlib.util.spec_from_file_location("agk_account_control_ui", UI_MODULE)
assert spec and spec.loader
ui = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = ui
spec.loader.exec_module(ui)

ACCOUNT_CONTROL_CHANNEL_ID = ui.ACCOUNT_CONTROL_CHANNEL_ID
ACCOUNT_CONTROL_GUILD_ID = ui.ACCOUNT_CONTROL_GUILD_ID
ACCOUNT_CONTROL_MESSAGE_ID = ui.ACCOUNT_CONTROL_MESSAGE_ID
ACCOUNT_CONTROL_OWNER_ID = ui.ACCOUNT_CONTROL_OWNER_ID
reconcile_account_control_channel = ui.reconcile_account_control_channel


class FakeMessage:
    def __init__(self, message_id: int):
        self.id = message_id
        self.edits = []
        self.pinned = False

    async def edit(self, **kwargs):
        self.edits.append(kwargs)
        return self

    async def pin(self, **_kwargs):
        self.pinned = True


class FakeChannel:
    def __init__(self, channel_id: int, name: str, guild, overwrites=None):
        self.id = channel_id
        self.name = name
        self.guild = guild
        self.overwrites = overwrites or {}
        self.messages = {}
        self.sent = []
        self.permission_updates = []

    async def set_permissions(self, target, **kwargs):
        self.permission_updates.append((target.id, kwargs))

    def can_view(self, role_id: int) -> bool:
        target = next(target for target in self.overwrites if target.id == role_id)
        return bool(self.overwrites[target].view_channel)

    async def fetch_message(self, message_id: int):
        if message_id not in self.messages:
            raise LookupError(message_id)
        return self.messages[message_id]

    async def send(self, **kwargs):
        message = FakeMessage(7000 + len(self.sent))
        message.edits.append(kwargs)
        self.messages[message.id] = message
        self.sent.append(message)
        return message


class FakeSnowflake:
    def __init__(self, snowflake_id: int):
        self.id = snowflake_id


class FakeGuild:
    def __init__(self, *, existing=False):
        self.id = ACCOUNT_CONTROL_GUILD_ID
        self.default_role = FakeSnowflake(1)
        self.owner = FakeSnowflake(ACCOUNT_CONTROL_OWNER_ID)
        self.me = FakeSnowflake(2)
        self.created_channels = []
        self._channels = {}
        if existing:
            channel = FakeChannel(ACCOUNT_CONTROL_CHANNEL_ID, "account-control", self)
            channel.messages[ACCOUNT_CONTROL_MESSAGE_ID] = FakeMessage(ACCOUNT_CONTROL_MESSAGE_ID)
            self._channels[channel.id] = channel

    def get_member(self, member_id):
        return self.owner if member_id == self.owner.id else None

    def get_channel(self, channel_id):
        return self._channels.get(channel_id)

    async def create_text_channel(self, name, **kwargs):
        channel = FakeChannel(9000, name, self, kwargs["overwrites"])
        self.created_channels.append(channel)
        self._channels[channel.id] = channel
        return channel


class FakeAdapter:
    def __init__(self, hermes_home):
        self.hermes_home = hermes_home
        self.roster_calls = 0

    def load_account_roster(self):
        self.roster_calls += 1
        return ()


@pytest.mark.asyncio
async def test_reconcile_creates_private_channel_and_one_persistent_post(tmp_path):
    guild = FakeGuild()
    adapter = FakeAdapter(tmp_path)

    state = await reconcile_account_control_channel(guild, adapter)
    state2 = await reconcile_account_control_channel(guild, adapter)

    assert state == state2
    assert len(guild.created_channels) == 1
    channel = guild.created_channels[0]
    assert channel.name == "account-control"
    assert channel.can_view(ACCOUNT_CONTROL_OWNER_ID)
    assert not channel.can_view(guild.default_role.id)
    assert len(channel.sent) == 1


class FakeResponse:
    def __init__(self):
        self.messages = []
        self.modals = []

    def is_done(self):
        return bool(self.messages or self.modals)

    async def send_message(self, content=None, **kwargs):
        self.messages.append((content, kwargs))

    async def edit_message(self, **kwargs):
        self.messages.append(("edit", kwargs))

    async def send_modal(self, modal):
        self.modals.append(modal)

    async def defer(self, **kwargs):
        self.messages.append(("defer", kwargs))


class FakeInteraction:
    def __init__(
        self,
        custom_id,
        *,
        user_id=ACCOUNT_CONTROL_OWNER_ID,
        guild_id=ACCOUNT_CONTROL_GUILD_ID,
        channel_id=ACCOUNT_CONTROL_CHANNEL_ID,
        values=None,
    ):
        self.user = SimpleNamespace(id=user_id)
        self.guild_id = guild_id
        self.channel_id = channel_id
        self.data = {"custom_id": custom_id, "values": values or []}
        self.response = FakeResponse()
        self.followup = SimpleNamespace(send=self._followup)
        self.followups = []

    async def _followup(self, content=None, **kwargs):
        self.followups.append((content, kwargs))


class SpyRunner:
    def __init__(self):
        self.calls = []

    def create(self, *args, **kwargs):
        self.calls.append(("create", args, kwargs))
        return SimpleNamespace(
            attempt_id="a" * 32,
            provider=args[0],
            owner_name=args[2],
            expires_at=2000.0,
        )

    def start(self, attempt_id):
        self.calls.append(("start", attempt_id))
        return SimpleNamespace(attempt_id=attempt_id)

    def cancel(self, attempt_id):
        self.calls.append(("cancel", attempt_id))
        return True

    def submit_claude_code(self, *args, **kwargs):
        self.calls.append(("submit", args, kwargs))
        return True

    def oauth_result(self, _attempt):
        return {
            "authorization_url": "https://auth.example/device",
            "device_code": "ABCD-EFGH",
            "access_token": "must-not-leak",
        }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "custom_id",
    [
        "agkacct:provider",
        "agkacct:account",
        "agkacct:switch",
        "agkacct:add",
        "agkacct:reconnect",
        "agkacct:refresh",
        "agkacct:close",
        "agkacct:claude-code",
        "agkacct:confirm-reconnect",
    ],
)
@pytest.mark.parametrize(
    "overrides",
    [
        {"user_id": 7},
        {"guild_id": 8},
        {"channel_id": 9},
    ],
)
async def test_every_callback_rechecks_owner_guild_and_channel(tmp_path, custom_id, overrides):
    adapter = FakeAdapter(tmp_path)
    adapter.prefer_calls = []
    runner = SpyRunner()
    view = ui.AccountControlView(adapter, runner=runner)
    interaction = FakeInteraction(custom_id, **overrides)

    await view.dispatch(interaction)

    assert interaction.response.messages[-1][1]["ephemeral"] is True
    assert runner.calls == []
    assert adapter.prefer_calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize("provider", ["openai-codex", "anthropic"])
async def test_switch_uses_canonical_preference_then_rereads_and_refreshes(tmp_path, provider):
    adapter = FakeAdapter(tmp_path)
    adapter.automatic_quota_rotation_enabled = True
    adapter.prefer_calls = []

    async def prefer(selected_provider, credential_id):
        adapter.prefer_calls.append((selected_provider, credential_id))
        return credential_id

    adapter._prefer_account_credential = prefer
    view = ui.AccountControlView(adapter, runner=SpyRunner())
    view.selected_provider = provider
    view.selected_credential_id = "credential-42"
    view.message = FakeMessage(ACCOUNT_CONTROL_MESSAGE_ID)
    interaction = FakeInteraction("agkacct:switch")

    await view.dispatch(interaction)

    assert adapter.prefer_calls == [(provider, "credential-42")]
    assert adapter.roster_calls == 1
    assert len(view.message.edits) == 1
    assert adapter.automatic_quota_rotation_enabled is True


@pytest.mark.asyncio
async def test_reconcile_adopts_exact_live_artifact_and_persists_mode_0600(tmp_path):
    guild = FakeGuild(existing=True)
    adapter = FakeAdapter(tmp_path)

    state = await reconcile_account_control_channel(guild, adapter)

    assert state.channel_id == ACCOUNT_CONTROL_CHANNEL_ID
    assert state.message_id == ACCOUNT_CONTROL_MESSAGE_ID
    assert guild.created_channels == []
    assert len(guild.get_channel(ACCOUNT_CONTROL_CHANNEL_ID).messages[ACCOUNT_CONTROL_MESSAGE_ID].edits) == 1
    state_path = tmp_path / "account_control_state.json"
    assert stat.S_IMODE(state_path.stat().st_mode) == 0o600
    assert json.loads(state_path.read_text()) == {
        "channel_id": ACCOUNT_CONTROL_CHANNEL_ID,
        "message_id": ACCOUNT_CONTROL_MESSAGE_ID,
    }
    channel = guild.get_channel(ACCOUNT_CONTROL_CHANNEL_ID)
    updates = dict(channel.permission_updates)
    assert updates[guild.default_role.id]["view_channel"] is False
    assert updates[ACCOUNT_CONTROL_OWNER_ID]["view_channel"] is True


@pytest.mark.asyncio
async def test_add_starts_one_openai_attempt_and_exposes_only_allowlisted_instructions(tmp_path):
    adapter = FakeAdapter(tmp_path)
    runner = SpyRunner()
    view = ui.AccountControlView(adapter, runner=runner)
    view.selected_provider = "openai-codex"
    interaction = FakeInteraction("agkacct:add")

    await view.start_add(interaction, "Agentik")

    assert runner.calls[:2] == [
        (
            "create",
            (
                "openai-codex",
                "add",
                "Agentik",
                None,
                ACCOUNT_CONTROL_OWNER_ID,
                ACCOUNT_CONTROL_GUILD_ID,
                ACCOUNT_CONTROL_CHANNEL_ID,
            ),
            {},
        ),
        ("start", "a" * 32),
    ]
    response = interaction.followups[-1][0]
    assert "https://auth.example/device" in response
    assert "ABCD-EFGH" in response
    assert "Agentik" in response
    assert "2000" in response
    assert "must-not-leak" not in response
    assert "access_token" not in response


@pytest.mark.asyncio
async def test_oauth_instructions_wait_for_delayed_redacted_runner_result(tmp_path):
    class DelayedRunner(SpyRunner):
        def __init__(self):
            super().__init__()
            self.result_calls = 0

        def oauth_result(self, _attempt):
            self.result_calls += 1
            if self.result_calls == 1:
                return {"status": "running"}
            return {
                "status": "running",
                "authorization_url": "https://auth.example/delayed",
                "device_code": "WAIT-1234",
            }

    runner = DelayedRunner()
    view = ui.AccountControlView(FakeAdapter(tmp_path), runner=runner)
    view.selected_provider = "openai-codex"
    interaction = FakeInteraction("agkacct:add")

    await view.start_add(interaction, "Agentik")

    assert runner.result_calls >= 2
    assert "https://auth.example/delayed" in interaction.followups[-1][0]
    assert "WAIT-1234" in interaction.followups[-1][0]


@pytest.mark.asyncio
async def test_refresh_finalizes_succeeded_selected_attempt_through_coordinator(tmp_path):
    class Store:
        def get(self, attempt_id):
            return SimpleNamespace(attempt_id=attempt_id, status="succeeded")

    class Coordinator:
        def __init__(self):
            self.calls = []

        def finalize(self, attempt_id):
            self.calls.append(attempt_id)
            return SimpleNamespace(status="committed")

    runner = SpyRunner()
    runner.store = Store()
    coordinator = Coordinator()
    view = ui.AccountControlView(
        FakeAdapter(tmp_path), runner=runner, coordinator=coordinator
    )
    view.selected_attempt_id = "d" * 32
    view.message = FakeMessage(ACCOUNT_CONTROL_MESSAGE_ID)

    await view.dispatch(FakeInteraction("agkacct:refresh"))

    assert coordinator.calls == ["d" * 32]
    assert view.selected_attempt_id == ""


@pytest.mark.asyncio
async def test_reconnect_requires_confirmation_then_starts_selected_replacement(tmp_path):
    adapter = FakeAdapter(tmp_path)
    runner = SpyRunner()
    view = ui.AccountControlView(adapter, runner=runner)
    view.selected_provider = "anthropic"
    view.selected_credential_id = "claude-1"
    view.selected_owner_name = "Loumna"

    await view.dispatch(FakeInteraction("agkacct:reconnect"))
    assert runner.calls == []

    interaction = FakeInteraction("agkacct:confirm-reconnect")
    await view.dispatch(interaction)

    create = runner.calls[0]
    assert create[0] == "create"
    assert create[1][:4] == ("anthropic", "reconnect", "Loumna", "claude-1")


@pytest.mark.asyncio
async def test_close_cancels_only_selected_live_attempt(tmp_path):
    runner = SpyRunner()
    view = ui.AccountControlView(FakeAdapter(tmp_path), runner=runner)
    view.selected_attempt_id = "b" * 32

    await view.dispatch(FakeInteraction("agkacct:close"))

    assert runner.calls == [("cancel", "b" * 32)]


@pytest.mark.asyncio
async def test_claude_modal_submission_targets_active_attempt_and_reauthorizes(tmp_path):
    runner = SpyRunner()
    view = ui.AccountControlView(FakeAdapter(tmp_path), runner=runner)
    view.selected_provider = "anthropic"
    view.selected_attempt_id = "c" * 32
    interaction = FakeInteraction("agkacct:claude-code")

    await view.submit_claude_code(interaction, "one-time-code#state")

    assert runner.calls == [
        (
            "submit",
            ("c" * 32, "one-time-code#state"),
            {"user_id": ACCOUNT_CONTROL_OWNER_ID, "channel_id": ACCOUNT_CONTROL_CHANNEL_ID},
        )
    ]


def test_adapter_registers_and_reconciles_persistent_center_on_ready_without_new_slash_command():
    source = (ROOT / "hermes/plugins/platforms/discord/adapter.py").read_text(encoding="utf-8")
    on_ready = source.split("async def on_ready():", 1)[1].split("async def on_message", 1)[0]

    assert "register_account_control_center" in on_ready
    assert "reconcile_account_control_channel" in on_ready
    assert "slash_account_control" not in source


@pytest.mark.asyncio
async def test_registered_persistent_view_is_reused_and_bound_to_adopted_post(tmp_path):
    class FakeBot:
        def __init__(self):
            self.views = []

        def add_view(self, view):
            self.views.append(view)

    bot = FakeBot()
    adapter = FakeAdapter(tmp_path)
    guild = FakeGuild(existing=True)

    ui.register_account_control_center(bot, adapter)
    ui.register_account_control_center(bot, adapter)
    await reconcile_account_control_channel(guild, adapter)

    assert len(bot.views) == 1
    assert adapter._account_control_view is bot.views[0]
    assert bot.views[0].message.id == ACCOUNT_CONTROL_MESSAGE_ID
