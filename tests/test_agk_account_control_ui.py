from __future__ import annotations

import importlib.util
import asyncio
import json
import stat
import sys
import threading
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
ACCOUNT_CONTROL_CATEGORY_ID = ui.ACCOUNT_CONTROL_CATEGORY_ID
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
    def __init__(self, channel_id: int, name: str, guild, overwrites=None, category=None):
        self.id = channel_id
        self.name = name
        self.guild = guild
        self.overwrites = overwrites or {}
        self.category = category
        self.type = "text"
        self.messages = {}
        self.sent = []
        self.permission_updates = []

    async def edit(self, **kwargs):
        if "overwrites" in kwargs:
            self.overwrites = dict(kwargs["overwrites"])
        return self

    async def set_permissions(self, target, **kwargs):
        self.permission_updates.append((target.id, kwargs))

    def can_view(self, role_id: int) -> bool:
        target = next(target for target in self.overwrites if target.id == role_id)
        return bool(self.overwrites[target].view_channel)

    async def fetch_message(self, message_id: int):
        if message_id not in self.messages:
            raise type("NotFound", (Exception,), {})(message_id)
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
        category = FakeSnowflake(ACCOUNT_CONTROL_CATEGORY_ID)
        category.type = "category"
        self._channels[category.id] = category
        if existing:
            channel = FakeChannel(
                ACCOUNT_CONTROL_CHANNEL_ID, "account-control", self, category=category
            )
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
        self.records = ()
        self.surface_refresh_reasons = []

    def load_account_roster(self):
        self.roster_calls += 1
        return self.records

    async def refresh_account_surfaces(self, *, reason):
        self.surface_refresh_reasons.append(reason)


@pytest.mark.asyncio
async def test_reconcile_fails_closed_when_exact_channel_is_missing(tmp_path):
    guild = FakeGuild(existing=False)
    adapter = FakeAdapter(tmp_path)

    with pytest.raises(RuntimeError, match="exact account control channel"):
        await reconcile_account_control_channel(guild, adapter)
    assert guild.created_channels == []


@pytest.mark.asyncio
async def test_reconcile_uses_exact_owner_snowflake_when_member_cache_is_empty(tmp_path):
    guild = FakeGuild(existing=True)
    guild.get_member = lambda _member_id: None
    adapter = FakeAdapter(tmp_path)

    state = await reconcile_account_control_channel(guild, adapter)

    assert state.channel_id == ACCOUNT_CONTROL_CHANNEL_ID
    channel = guild.get_channel(ACCOUNT_CONTROL_CHANNEL_ID)
    assert {int(target.id) for target in channel.overwrites} == {
        int(guild.default_role.id),
        ACCOUNT_CONTROL_OWNER_ID,
        int(guild.me.id),
    }
    assert channel.can_view(ACCOUNT_CONTROL_OWNER_ID) is True


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

    def oauth_result(self, attempt):
        return {
            "authorization_url": (
                "https://auth.openai.com/codex/device"
                if attempt.provider == "openai-codex"
                else "https://claude.ai/oauth/authorize"
            ),
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
        return "saved"

    adapter._prefer_account_credential = prefer
    adapter.records = (
        SimpleNamespace(
            provider=provider,
            credential_id="credential-42",
            owner_name="Agentik",
            status="ok",
            priority=0,
            windows=(),
        ),
    )
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
@pytest.mark.parametrize(
    "status,expected,forbidden",
    [
        ("missing", "no longer exists", "Preferred account updated"),
        ("unavailable", "not eligible", "Preferred account updated"),
    ],
)
async def test_switch_surfaces_canonical_rejection_status(tmp_path, status, expected, forbidden):
    adapter = FakeAdapter(tmp_path)
    adapter.records = ()

    async def prefer(_provider, _credential_id):
        return status

    adapter._prefer_account_credential = prefer
    view = ui.AccountControlView(adapter, runner=SpyRunner())
    view.selected_provider = "openai-codex"
    view.selected_credential_id = "credential-42"
    view.message = FakeMessage(ACCOUNT_CONTROL_MESSAGE_ID)
    interaction = FakeInteraction("agkacct:switch")

    await view.dispatch(interaction)

    assert expected in interaction.followups[-1][0]
    assert forbidden not in interaction.followups[-1][0]


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
    assert channel.overwrites[guild.default_role].view_channel is False
    assert channel.overwrites[guild.owner].view_channel is True


@pytest.mark.asyncio
async def test_reconcile_replaces_acl_with_exact_private_overwrite_set(tmp_path):
    guild = FakeGuild(existing=True)
    channel = guild.get_channel(ACCOUNT_CONTROL_CHANNEL_ID)
    intruder_role = FakeSnowflake(81)
    intruder_member = FakeSnowflake(82)
    channel.overwrites = {
        guild.default_role: SimpleNamespace(view_channel=False),
        guild.owner: SimpleNamespace(view_channel=True),
        guild.me: SimpleNamespace(view_channel=True),
        intruder_role: SimpleNamespace(view_channel=True),
        intruder_member: SimpleNamespace(view_channel=True),
    }

    await reconcile_account_control_channel(guild, FakeAdapter(tmp_path))

    assert {target.id for target in channel.overwrites} == {
        guild.default_role.id,
        ACCOUNT_CONTROL_OWNER_ID,
        guild.me.id,
    }
    assert channel.overwrites[guild.default_role].view_channel is False
    assert channel.overwrites[guild.owner].view_channel is True
    assert channel.overwrites[guild.me].view_channel is True


@pytest.mark.parametrize(
    "provider,url",
    [
        ("openai-codex", "https://auth.openai.com/codex/device#access_token=leak"),
        ("openai-codex", "https://token:leak@auth.openai.com/codex/device"),
        ("openai-codex", "https://auth.openai.com/codex/device?access-token=leak"),
        ("openai-codex", "https://evil.example/codex/device"),
        ("openai-codex", "https://auth.openai.com/private-token-value"),
        ("anthropic", "https://claude.ai/oauth/authorize?refresh_token=leak"),
    ],
)
def test_oauth_instructions_reject_adversarial_urls(tmp_path, provider, url):
    view = ui.AccountControlView(FakeAdapter(tmp_path), runner=SpyRunner())
    view.selected_provider = provider
    attempt = SimpleNamespace(owner_name="Agentik", expires_at=2000.0)

    rendered = view._oauth_instructions(attempt, {"authorization_url": url})

    assert url not in rendered
    assert "leak" not in rendered
    assert "private-token-value" not in rendered


def test_registration_constructs_production_runner_and_coordinator(tmp_path, monkeypatch):
    class FakeBot:
        def add_view(self, _view):
            pass

    adapter = FakeAdapter(tmp_path)
    built = SimpleNamespace(runner=object(), coordinator=object(), snapshot_store=object())
    monkeypatch.setattr(ui, "_build_account_control_services", lambda _adapter: built)

    ui.register_account_control_center(FakeBot(), adapter)

    assert adapter._account_control_oauth_runner is built.runner
    assert adapter._account_control_coordinator is built.coordinator
    assert adapter._account_control_snapshot_store is built.snapshot_store
    assert adapter._account_control_view.runner is built.runner
    assert adapter._account_control_view.coordinator is built.coordinator


@pytest.mark.asyncio
async def test_registered_production_services_finalize_on_refresh(tmp_path, monkeypatch):
    attempt_id = "f" * 32

    class Store:
        def get(self, _attempt_id):
            return SimpleNamespace(attempt_id=attempt_id, status="succeeded")

    class Coordinator:
        def __init__(self):
            self.calls = []

        def finalize(self, selected_attempt_id):
            self.calls.append(selected_attempt_id)
            return SimpleNamespace(status="committed")

    class FakeBot:
        def add_view(self, _view):
            pass

    runner = SpyRunner()
    runner.store = Store()
    coordinator = Coordinator()
    built = SimpleNamespace(
        runner=runner, coordinator=coordinator, snapshot_store=object()
    )
    monkeypatch.setattr(ui, "_build_account_control_services", lambda _adapter: built)
    adapter = FakeAdapter(tmp_path)

    ui.register_account_control_center(FakeBot(), adapter)
    view = adapter._account_control_view
    view.selected_attempt_id = attempt_id
    view.message = FakeMessage(ACCOUNT_CONTROL_MESSAGE_ID)
    interaction = FakeInteraction("agkacct:refresh")
    await view.dispatch(interaction)

    assert coordinator.calls == [attempt_id]
    assert "committed" in interaction.followups[-1][0].lower()


@pytest.mark.asyncio
async def test_reconcile_serializes_overlapping_calls(tmp_path):
    guild = FakeGuild(existing=True)
    adapter = FakeAdapter(tmp_path)
    channel = guild.get_channel(ACCOUNT_CONTROL_CHANNEL_ID)
    original_edit = channel.messages[ACCOUNT_CONTROL_MESSAGE_ID].edit

    async def delayed_edit(**kwargs):
        await asyncio.sleep(0.01)
        return await original_edit(**kwargs)

    channel.messages[ACCOUNT_CONTROL_MESSAGE_ID].edit = delayed_edit
    states = await asyncio.gather(
        reconcile_account_control_channel(guild, adapter),
        reconcile_account_control_channel(guild, adapter),
    )

    assert states[0] == states[1]
    assert channel.sent == []
    assert len(channel.messages) == 1


@pytest.mark.asyncio
async def test_reconcile_propagates_transient_fetch_failure_without_sending(tmp_path):
    guild = FakeGuild(existing=True)
    channel = guild.get_channel(ACCOUNT_CONTROL_CHANNEL_ID)

    async def fail_fetch(_message_id):
        raise OSError("transport timeout")

    channel.fetch_message = fail_fetch
    with pytest.raises(OSError, match="transport timeout"):
        await reconcile_account_control_channel(guild, FakeAdapter(tmp_path))
    assert channel.sent == []


@pytest.mark.asyncio
async def test_reconcile_loads_provider_roster_off_event_loop(tmp_path):
    guild = FakeGuild(existing=True)
    adapter = FakeAdapter(tmp_path)
    entered = threading.Event()
    release = threading.Event()

    def slow_loader():
        entered.set()
        release.wait(timeout=2)
        return ()

    adapter.load_account_roster = slow_loader
    task = asyncio.create_task(reconcile_account_control_channel(guild, adapter))
    while not entered.is_set():
        await asyncio.sleep(0)
    await asyncio.sleep(0)
    assert not task.done()
    release.set()
    await task


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
    assert "https://auth.openai.com/codex/device" in response
    assert "ABCD-EFGH" in response
    assert "Agentik" in response
    assert "2000" in response
    assert "must-not-leak" not in response
    assert "access_token" not in response


@pytest.mark.asyncio
async def test_add_modal_provider_context_is_immutable(tmp_path):
    runner = SpyRunner()
    view = ui.AccountControlView(FakeAdapter(tmp_path), runner=runner)
    view.selected_provider = "openai-codex"
    interaction = FakeInteraction("agkacct:add")

    await view.start_add_bound(interaction, "Agentik", "anthropic")

    assert runner.calls[0][1][0] == "anthropic"
    assert "https://claude.ai/oauth/authorize" in interaction.followups[-1][0]


def test_oauth_url_policy_uses_immutable_attempt_provider(tmp_path):
    view = ui.AccountControlView(FakeAdapter(tmp_path), runner=SpyRunner())
    view.selected_provider = "openai-codex"
    attempt = SimpleNamespace(
        provider="anthropic", owner_name="Agentik", expires_at=2000.0
    )

    rendered = view._oauth_instructions(
        attempt, {"authorization_url": "https://claude.ai/oauth/authorize"}
    )

    assert "https://claude.ai/oauth/authorize" in rendered


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
                "authorization_url": "https://auth.openai.com/codex/device",
                "device_code": "WAIT-1234",
            }

    runner = DelayedRunner()
    view = ui.AccountControlView(FakeAdapter(tmp_path), runner=runner)
    view.selected_provider = "openai-codex"
    interaction = FakeInteraction("agkacct:add")

    await view.start_add(interaction, "Agentik")

    assert runner.result_calls >= 2
    assert "https://auth.openai.com/codex/device" in interaction.followups[-1][0]
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
@pytest.mark.parametrize(
    "status,expected,cleared",
    [
        ("committed", "committed", True),
        ("rolled_back", "rolled back safely", True),
        ("reconciliation_required", "manual reconciliation is required", False),
        ("presentation_reconciliation_pending", "presentation refresh is pending", False),
    ],
)
async def test_refresh_surfaces_safe_transaction_outcome(tmp_path, status, expected, cleared):
    attempt_id = "d" * 32

    class Store:
        def get(self, _attempt_id):
            return SimpleNamespace(attempt_id=attempt_id, status="succeeded")

    class Coordinator:
        def finalize(self, _attempt_id):
            return SimpleNamespace(status=status, message="provider secret body")

    runner = SpyRunner()
    runner.store = Store()
    adapter = FakeAdapter(tmp_path)
    view = ui.AccountControlView(
        adapter, runner=runner, coordinator=Coordinator()
    )
    view.selected_attempt_id = attempt_id
    view.message = FakeMessage(ACCOUNT_CONTROL_MESSAGE_ID)
    interaction = FakeInteraction("agkacct:refresh")

    await view.dispatch(interaction)

    assert expected in interaction.followups[-1][0].lower()
    assert "provider secret body" not in interaction.followups[-1][0]
    assert bool(view.selected_attempt_id) is not cleared
    assert adapter.surface_refresh_reasons == (
        ["account-transaction"] if status == "committed" else []
    )


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
async def test_bound_reconnect_rejects_stale_account_context(tmp_path):
    runner = SpyRunner()
    adapter = FakeAdapter(tmp_path)
    view = ui.AccountControlView(adapter, runner=runner)
    interaction = FakeInteraction("agkacct:confirm-reconnect")

    await view.start_reconnect_bound(
        interaction, "anthropic", "claude-old", "Loumna"
    )

    assert runner.calls == []
    assert "stale" in interaction.response.messages[-1][0].lower()


@pytest.mark.asyncio
async def test_bound_claude_submit_rejects_changed_attempt(tmp_path):
    runner = SpyRunner()
    view = ui.AccountControlView(FakeAdapter(tmp_path), runner=runner)
    view.selected_provider = "anthropic"
    view.selected_attempt_id = "e" * 32
    interaction = FakeInteraction("agkacct:claude-code")

    await view.submit_claude_code(
        interaction, "one-time-code", attempt_id="c" * 32, provider="anthropic"
    )

    assert runner.calls == []
    assert "changed" in interaction.response.messages[-1][0].lower()


def test_roster_render_is_bounded_to_discord_content_limit(monkeypatch):
    monkeypatch.setattr(
        ui,
        "_load_roster_api",
        lambda: (lambda *_args: (), lambda _records: "x" * 5000),
    )

    rendered = ui._render_records(())

    assert len(rendered) <= 2000
    assert "truncated" in rendered.lower()


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ["switch", "refresh", "close", "claude"])
async def test_handled_action_failures_are_redacted_and_ephemeral(tmp_path, action):
    class FailingRunner(SpyRunner):
        def cancel(self, _attempt_id):
            raise RuntimeError("secret provider body")

        def submit_claude_code(self, *_args, **_kwargs):
            raise RuntimeError("secret provider body")

    adapter = FakeAdapter(tmp_path)
    runner = FailingRunner()
    view = ui.AccountControlView(adapter, runner=runner)
    view.message = FakeMessage(ACCOUNT_CONTROL_MESSAGE_ID)
    if action == "switch":
        view.selected_provider = "openai-codex"
        view.selected_credential_id = "credential-42"

        async def fail_prefer(*_args):
            raise RuntimeError("secret provider body")

        adapter._prefer_account_credential = fail_prefer
        interaction = FakeInteraction("agkacct:switch")
        await view.dispatch(interaction)
    elif action == "refresh":
        adapter.load_account_roster = lambda: (_ for _ in ()).throw(
            RuntimeError("secret provider body")
        )
        interaction = FakeInteraction("agkacct:refresh")
        await view.dispatch(interaction)
    elif action == "close":
        view.selected_attempt_id = "c" * 32
        interaction = FakeInteraction("agkacct:close")
        await view.dispatch(interaction)
    else:
        view.selected_provider = "anthropic"
        view.selected_attempt_id = "c" * 32
        interaction = FakeInteraction("agkacct:claude-code")
        await view.submit_claude_code(interaction, "code")

    content, kwargs = interaction.followups[-1]
    assert "secret provider body" not in content
    assert "RuntimeError" in content
    assert kwargs["ephemeral"] is True


@pytest.mark.asyncio
@pytest.mark.skipif(ui.discord is None, reason="runtime modal test requires discord.py")
@pytest.mark.parametrize(
    "overrides",
    [{"user_id": 7}, {"guild_id": 8}, {"channel_id": 9}],
)
async def test_claude_modal_submission_reauthorizes_before_stale_check(
    tmp_path, overrides
):
    view = ui.AccountControlView(FakeAdapter(tmp_path), runner=SpyRunner())
    view.selected_provider = "anthropic"
    view.selected_attempt_id = "e" * 32
    modal = object.__new__(ui.ClaudeCodeModal)
    modal.parent = view
    modal.provider = "anthropic"
    modal.attempt_id = "c" * 32
    interaction = FakeInteraction("agkacct:claude-code", **overrides)

    await modal.on_submit(interaction)

    assert "not authorized" in interaction.response.messages[-1][0]
    assert interaction.response.messages[-1][1]["ephemeral"] is True


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
    adapter._account_control_oauth_runner = SpyRunner()
    adapter._account_control_coordinator = object()
    adapter._account_control_snapshot_store = object()
    guild = FakeGuild(existing=True)

    ui.register_account_control_center(bot, adapter)
    ui.register_account_control_center(bot, adapter)
    await reconcile_account_control_channel(guild, adapter)

    assert len(bot.views) == 1
    assert adapter._account_control_view is bot.views[0]
    assert bot.views[0].message.id == ACCOUNT_CONTROL_MESSAGE_ID
