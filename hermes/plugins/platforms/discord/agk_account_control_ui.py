"""Private persistent Discord account control center for the AGK Station."""
from __future__ import annotations

import asyncio
import json
import os
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from urllib.parse import parse_qsl, urlparse

try:
    import discord
except ImportError:  # pragma: no cover - source-contract tests run without discord.py
    discord = None

def _load_roster_api():
    try:
        from .agk_account_control import load_account_roster, render_account_roster
    except ImportError:  # pragma: no cover - direct-file test loading
        from agk_account_control import load_account_roster, render_account_roster
    return load_account_roster, render_account_roster

ACCOUNT_CONTROL_GUILD_ID = 1541131439599386644
ACCOUNT_CONTROL_CATEGORY_ID = 1542505218569150585
ACCOUNT_CONTROL_CHANNEL_ID = 1542563923809796140
ACCOUNT_CONTROL_MESSAGE_ID = 1542563946135814278
ACCOUNT_CONTROL_OWNER_ID = 1441423462492016821
ACCOUNT_CONTROL_CHANNEL_NAME = "account-control"


@dataclass(frozen=True)
class AccountControlState:
    channel_id: int
    message_id: int


def _hermes_home(adapter: Any) -> Path:
    configured = getattr(adapter, "hermes_home", None)
    if configured is not None:
        return Path(configured)
    from hermes_constants import get_hermes_home

    return Path(get_hermes_home())


def _state_path(adapter: Any) -> Path:
    return _hermes_home(adapter) / "account_control_state.json"


def _read_state(adapter: Any) -> AccountControlState | None:
    path = _state_path(adapter)
    try:
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    except OSError:
        return None
    try:
        with os.fdopen(descriptor, encoding="utf-8") as handle:
            descriptor = -1
            payload = json.load(handle)
        return AccountControlState(
            channel_id=int(payload["channel_id"]),
            message_id=int(payload["message_id"]),
        )
    except (KeyError, TypeError, ValueError, OSError):
        return None
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def _write_state(adapter: Any, state: AccountControlState) -> None:
    path = _state_path(adapter)
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".new", dir=path.parent)
    temporary = Path(name)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(asdict(state), handle, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        path.chmod(0o600)
    finally:
        temporary.unlink(missing_ok=True)


def _permission(**values):
    return discord.PermissionOverwrite(**values) if discord else SimpleNamespace(**values)


def _load_records(adapter: Any):
    loader = getattr(adapter, "load_account_roster", None)
    if callable(loader):
        return tuple(loader())
    load, _renderer = _load_roster_api()
    return tuple(load(_hermes_home(adapter)))


def _render_records(records: Any) -> str:
    try:
        _load, renderer = _load_roster_api()
    except ImportError:
        return "# Station · Account roster\n\nNo connected accounts."
    return renderer(records)


def _render(adapter: Any) -> str:
    return _render_records(_load_records(adapter))


_ViewBase = discord.ui.View if discord else object


class AccountControlView(_ViewBase):
    """Persistent owner-only controls for canonical account operations."""

    def __init__(
        self,
        adapter: Any,
        *,
        runner: Any = None,
        coordinator: Any = None,
        channel_id: int = ACCOUNT_CONTROL_CHANNEL_ID,
    ):
        if discord:
            super().__init__(timeout=None)
        else:
            super().__init__()
            self.timeout = None
        self.adapter = adapter
        self.runner = runner or getattr(adapter, "_account_control_oauth_runner", None)
        self.coordinator = coordinator or getattr(adapter, "_account_control_coordinator", None)
        self.channel_id = int(channel_id)
        self.selected_provider = ""
        self.selected_credential_id = ""
        self.selected_attempt_id = ""
        self.selected_owner_name = ""
        self.records: tuple[Any, ...] = ()
        self.message = None
        if discord:
            self._build_components()

    def _build_components(self) -> None:
        self.clear_items()
        provider = discord.ui.Select(
            placeholder="Choose OpenAI or Claude",
            options=[
                discord.SelectOption(label="OpenAI / ChatGPT", value="openai-codex"),
                discord.SelectOption(label="Anthropic / Claude", value="anthropic"),
            ],
            custom_id="agkacct:provider",
            row=0,
        )
        provider.callback = self.dispatch
        self.add_item(provider)
        matching = [
            record
            for record in self.records
            if getattr(record, "provider", None) == self.selected_provider
        ][:25]
        account_options = [
            discord.SelectOption(
                label=(
                    f"{getattr(record, 'owner_name', '') or 'Unassigned'} · "
                    f"{getattr(record, 'credential_id', 'unknown')}"
                )[:100],
                value=str(getattr(record, "credential_id", ""))[:100],
                description=f"Status: {getattr(record, 'status', 'unknown')}"[:100],
            )
            for record in matching
            if getattr(record, "credential_id", None)
        ]
        account = discord.ui.Select(
            placeholder="Choose an account",
            options=account_options or [
                discord.SelectOption(label="No account available", value="none")
            ],
            custom_id="agkacct:account",
            disabled=not account_options,
            row=1,
        )
        account.callback = self.dispatch
        self.add_item(account)
        for label, custom_id, style, row in (
            ("Switch", "agkacct:switch", discord.ButtonStyle.primary, 2),
            ("Add account", "agkacct:add", discord.ButtonStyle.success, 2),
            ("Reconnect", "agkacct:reconnect", discord.ButtonStyle.secondary, 2),
            ("Refresh", "agkacct:refresh", discord.ButtonStyle.secondary, 3),
            ("Close session", "agkacct:close", discord.ButtonStyle.danger, 3),
        ):
            button = discord.ui.Button(label=label, style=style, custom_id=custom_id, row=row)
            button.callback = self.dispatch
            self.add_item(button)

    async def _authorized(self, interaction: Any) -> bool:
        allowed = (
            int(getattr(getattr(interaction, "user", None), "id", 0)) == ACCOUNT_CONTROL_OWNER_ID
            and int(getattr(interaction, "guild_id", 0) or 0) == ACCOUNT_CONTROL_GUILD_ID
            and int(getattr(interaction, "channel_id", 0) or 0) == self.channel_id
        )
        if allowed:
            return True
        if not interaction.response.is_done():
            await interaction.response.send_message(
                "This private account control action is not authorized.", ephemeral=True
            )
        return False

    async def dispatch(self, interaction: Any) -> None:
        """Route every stable component ID through the same fail-closed gate."""
        if not await self._authorized(interaction):
            return
        custom_id = str((getattr(interaction, "data", None) or {}).get("custom_id") or "")
        values = (getattr(interaction, "data", None) or {}).get("values") or []
        if custom_id == "agkacct:provider":
            await self._select_provider(interaction, values)
        elif custom_id == "agkacct:account":
            await self._select_account(interaction, values)
        elif custom_id == "agkacct:switch":
            await self._switch(interaction)
        elif custom_id == "agkacct:refresh":
            await interaction.response.defer(ephemeral=True)
            await self.refresh_message()
            await interaction.followup.send("Account roster refreshed.", ephemeral=True)
        elif custom_id == "agkacct:add":
            if self.selected_provider not in {"openai-codex", "anthropic"}:
                await interaction.response.send_message("Select a provider first.", ephemeral=True)
            elif discord:
                await interaction.response.send_modal(OwnerNicknameModal(self))
            else:
                await interaction.response.send_message(
                    "Submit an owner nickname to start OAuth.", ephemeral=True
                )
        elif custom_id == "agkacct:reconnect":
            await self._request_reconnect(interaction)
        elif custom_id == "agkacct:confirm-reconnect":
            await self.start_reconnect(interaction)
        elif custom_id == "agkacct:claude-code":
            if self.selected_provider != "anthropic" or not self.selected_attempt_id:
                await interaction.response.send_message(
                    "No active Claude OAuth attempt is selected.", ephemeral=True
                )
            elif discord:
                await interaction.response.send_modal(ClaudeCodeModal(self))
            else:
                await interaction.response.send_message(
                    "Submit the one-time Claude code.", ephemeral=True
                )
        elif custom_id == "agkacct:close":
            await self.close_attempt(interaction)
        else:
            await interaction.response.send_message("Unknown account action.", ephemeral=True)

    async def _select_provider(self, interaction: Any, values: list[Any]) -> None:
        provider = str(values[0]) if values else ""
        if provider not in {"openai-codex", "anthropic"}:
            await interaction.response.send_message("Choose a canonical provider.", ephemeral=True)
            return
        self.selected_provider = provider
        self.selected_credential_id = ""
        self.selected_owner_name = ""
        self.records = await asyncio.to_thread(_load_records, self.adapter)
        if discord:
            self._build_components()
        await interaction.response.edit_message(content=_render_records(self.records), view=self)

    async def _select_account(self, interaction: Any, values: list[Any]) -> None:
        credential_id = str(values[0]) if values else ""
        if not self.selected_provider or not credential_id or len(credential_id) > 128:
            await interaction.response.send_message("Choose a valid account.", ephemeral=True)
            return
        selected = next(
            (
                record
                for record in self.records
                if getattr(record, "provider", None) == self.selected_provider
                and str(getattr(record, "credential_id", "")) == credential_id
            ),
            None,
        )
        if selected is None:
            await interaction.response.send_message(
                "That account is no longer in the canonical pool. Refresh first.", ephemeral=True
            )
            return
        self.selected_credential_id = credential_id
        self.selected_owner_name = str(getattr(selected, "owner_name", "") or "")
        await interaction.response.edit_message(content=_render_records(self.records), view=self)

    async def _switch(self, interaction: Any) -> None:
        if self.selected_provider not in {"openai-codex", "anthropic"} or not self.selected_credential_id:
            await interaction.response.send_message(
                "Choose a provider and account before switching.", ephemeral=True
            )
            return
        await interaction.response.defer(ephemeral=True)
        await self.adapter._prefer_account_credential(
            self.selected_provider, self.selected_credential_id
        )
        await self.refresh_message()
        await interaction.followup.send(
            "Preferred account updated. Automatic quota rotation remains enabled.",
            ephemeral=True,
        )

    def _ensure_runner(self) -> Any:
        if self.runner is not None:
            return self.runner
        try:
            from .agk_account_oauth import OAuthAttemptStore, OAuthRunner
        except ImportError:  # pragma: no cover - direct-file loading
            from agk_account_oauth import OAuthAttemptStore, OAuthRunner
        self.runner = OAuthRunner(OAuthAttemptStore(_hermes_home(self.adapter)))
        self.adapter._account_control_oauth_runner = self.runner
        return self.runner

    async def start_add(self, interaction: Any, owner_name: str) -> None:
        if not await self._authorized(interaction):
            return
        await self._start_oauth(interaction, "add", str(owner_name).strip(), None)

    async def _request_reconnect(self, interaction: Any) -> None:
        if (
            self.selected_provider not in {"openai-codex", "anthropic"}
            or not self.selected_credential_id
            or not getattr(self, "selected_owner_name", "")
        ):
            await interaction.response.send_message(
                "Select a named account before reconnecting.", ephemeral=True
            )
            return
        if discord:
            await interaction.response.send_message(
                "Reconnect replaces the selected credential only after verification.",
                view=ReconnectConfirmView(self),
                ephemeral=True,
            )
        else:
            await interaction.response.send_message(
                "Confirm reconnect to replace the selected credential.", ephemeral=True
            )

    async def start_reconnect(self, interaction: Any) -> None:
        if not await self._authorized(interaction):
            return
        owner_name = str(getattr(self, "selected_owner_name", "") or "")
        if not self.selected_credential_id or not owner_name:
            await interaction.response.send_message(
                "The selected account is unavailable for reconnect.", ephemeral=True
            )
            return
        await self._start_oauth(
            interaction, "reconnect", owner_name, self.selected_credential_id
        )

    async def _start_oauth(
        self,
        interaction: Any,
        operation: str,
        owner_name: str,
        credential_id: str | None,
    ) -> None:
        if self.selected_provider not in {"openai-codex", "anthropic"}:
            await interaction.response.send_message("Select a provider first.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        runner = self._ensure_runner()
        try:
            attempt = await asyncio.to_thread(
                runner.create,
                self.selected_provider,
                operation,
                owner_name,
                credential_id,
                ACCOUNT_CONTROL_OWNER_ID,
                ACCOUNT_CONTROL_GUILD_ID,
                self.channel_id,
            )
            started = await asyncio.to_thread(runner.start, attempt.attempt_id)
        except Exception as exc:  # noqa: BLE001 - runner seams expose no common base
            await interaction.followup.send(
                f"OAuth attempt could not start ({type(exc).__name__}).", ephemeral=True
            )
            return
        self.selected_attempt_id = attempt.attempt_id
        payload = await self._wait_for_oauth_result(runner, attempt)
        text = self._oauth_instructions(attempt, payload)
        kwargs: dict[str, Any] = {"ephemeral": True}
        if discord and self.selected_provider == "anthropic":
            kwargs["view"] = ClaudeSubmitView(self)
        await interaction.followup.send(text, **kwargs)
        del started

    async def _wait_for_oauth_result(self, runner: Any, attempt: Any) -> dict[str, Any]:
        """Wait briefly for the sibling runner's redacted URL/code artifact."""
        payload: dict[str, Any] = {}
        for index in range(100):
            payload = await asyncio.to_thread(self._oauth_result, runner, attempt)
            if payload.get("authorization_url"):
                return payload
            if payload.get("status") in {"cancelled", "expired", "failed", "succeeded"}:
                return payload
            if index < 99:
                await asyncio.sleep(0.1)
        return payload

    @staticmethod
    def _oauth_result(runner: Any, attempt: Any) -> dict[str, Any]:
        seam = getattr(runner, "oauth_result", None)
        if callable(seam):
            payload = seam(attempt)
            return payload if isinstance(payload, dict) else {}
        result_path = getattr(runner, "result_path", lambda _attempt: None)(attempt)
        if result_path is None:
            return {}
        try:
            with open(result_path, encoding="utf-8") as handle:
                payload = json.load(handle)
        except (OSError, TypeError, ValueError):
            return {}
        return payload if isinstance(payload, dict) else {}

    def _oauth_instructions(self, attempt: Any, payload: dict[str, Any]) -> str:
        raw_url = str(payload.get("authorization_url") or "")
        parsed = urlparse(raw_url)
        forbidden = {"access_token", "refresh_token", "token", "password", "secret"}
        safe_url = ""
        if parsed.scheme in {"http", "https"} and parsed.netloc:
            keys = {key.casefold() for key, _value in parse_qsl(parsed.query, keep_blank_values=True)}
            if not keys.intersection(forbidden):
                safe_url = raw_url[:1000]
        device_code = str(payload.get("device_code") or "")[:128]
        lines = [
            f"Provider: `{self.selected_provider}`",
            f"Alias: `{attempt.owner_name}`",
            f"Expires: `{int(float(attempt.expires_at))}`",
        ]
        if safe_url:
            lines.append(f"Verification URL: {safe_url}")
        if self.selected_provider == "openai-codex" and device_code:
            lines.append(f"Device code: `{device_code}`")
        if self.selected_provider == "anthropic":
            lines.append("Open the URL, then use **Submit code** once.")
        return "\n".join(lines)

    async def close_attempt(self, interaction: Any) -> None:
        if not self.selected_attempt_id:
            await interaction.response.send_message("No live OAuth attempt is selected.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        attempt_id = self.selected_attempt_id
        cancelled = await asyncio.to_thread(self._ensure_runner().cancel, attempt_id)
        if cancelled:
            self.selected_attempt_id = ""
        await interaction.followup.send(
            "OAuth attempt closed." if cancelled else "OAuth attempt was already closed.",
            ephemeral=True,
        )

    async def submit_claude_code(self, interaction: Any, code: str) -> None:
        if not await self._authorized(interaction):
            return
        if self.selected_provider != "anthropic" or not self.selected_attempt_id:
            await interaction.response.send_message(
                "No active Claude OAuth attempt is selected.", ephemeral=True
            )
            return
        await interaction.response.defer(ephemeral=True)
        submitted = await asyncio.to_thread(
            self._ensure_runner().submit_claude_code,
            self.selected_attempt_id,
            str(code),
            user_id=ACCOUNT_CONTROL_OWNER_ID,
            channel_id=self.channel_id,
        )
        await interaction.followup.send(
            "Claude code submitted once." if submitted else "Claude code was rejected or expired.",
            ephemeral=True,
        )

    async def _finalize_succeeded_attempt(self) -> None:
        if not self.selected_attempt_id or self.coordinator is None or self.runner is None:
            return
        store = getattr(self.runner, "store", None)
        if store is None:
            return
        attempt = await asyncio.to_thread(store.get, self.selected_attempt_id)
        if attempt is None or getattr(attempt, "status", None) != "succeeded":
            return
        result = await asyncio.to_thread(
            self.coordinator.finalize, self.selected_attempt_id
        )
        if getattr(result, "status", "") in {
            "committed",
            "rolled_back",
            "reconciliation_required",
            "presentation_reconciliation_pending",
        }:
            self.selected_attempt_id = ""

    async def refresh_message(self) -> None:
        await self._finalize_succeeded_attempt()
        self.records = await asyncio.to_thread(_load_records, self.adapter)
        if discord:
            self._build_components()
        content = _render_records(self.records)
        if self.message is not None:
            await self.message.edit(content=content, view=self)


if discord:
    class OwnerNicknameModal(discord.ui.Modal, title="Add provider account"):
        owner_name = discord.ui.TextInput(
            label="Owner nickname",
            placeholder="Technical alias only",
            min_length=1,
            max_length=64,
        )

        def __init__(self, parent: AccountControlView):
            super().__init__(timeout=300, custom_id="agkacct:add-modal")
            self.parent = parent

        async def on_submit(self, interaction: Any) -> None:
            await self.parent.start_add(interaction, str(self.owner_name))


    class ClaudeCodeModal(discord.ui.Modal, title="Submit Claude code"):
        code = discord.ui.TextInput(
            label="One-time code",
            min_length=1,
            max_length=4000,
        )

        def __init__(self, parent: AccountControlView):
            super().__init__(timeout=300, custom_id="agkacct:claude-code-modal")
            self.parent = parent
            self.attempt_id = parent.selected_attempt_id

        async def on_submit(self, interaction: Any) -> None:
            if self.parent.selected_attempt_id != self.attempt_id:
                await interaction.response.send_message(
                    "The selected OAuth attempt changed. Open a new code modal.", ephemeral=True
                )
                return
            await self.parent.submit_claude_code(interaction, str(self.code))


    class ReconnectConfirmView(discord.ui.View):
        def __init__(self, parent: AccountControlView):
            super().__init__(timeout=60)
            self.parent = parent
            confirm = discord.ui.Button(
                label="Confirm reconnect",
                style=discord.ButtonStyle.danger,
                custom_id="agkacct:confirm-reconnect",
            )
            confirm.callback = parent.dispatch
            self.add_item(confirm)


    class ClaudeSubmitView(discord.ui.View):
        def __init__(self, parent: AccountControlView):
            super().__init__(timeout=900)
            submit = discord.ui.Button(
                label="Submit code",
                style=discord.ButtonStyle.primary,
                custom_id="agkacct:claude-code",
            )
            submit.callback = parent.dispatch
            self.add_item(submit)
else:  # pragma: no cover - placeholders keep direct source tests importable
    OwnerNicknameModal = ClaudeCodeModal = ReconnectConfirmView = ClaudeSubmitView = object


async def _fetch_message(channel: Any, message_id: int | None):
    if not message_id:
        return None
    try:
        return await channel.fetch_message(int(message_id))
    except Exception:  # noqa: BLE001 - discord.py exposes multiple not-found types
        return None


async def reconcile_account_control_channel(guild: Any, adapter: Any) -> AccountControlState:
    """Adopt or create the single private channel and persistent pinned post."""
    if int(getattr(guild, "id", 0)) != ACCOUNT_CONTROL_GUILD_ID:
        raise PermissionError("account control center belongs to the exact Station guild")

    saved = _read_state(adapter)
    owner = guild.get_member(ACCOUNT_CONTROL_OWNER_ID)
    if owner is None:
        raise RuntimeError("account control owner is not a guild member")
    channel = guild.get_channel(ACCOUNT_CONTROL_CHANNEL_ID)
    if channel is None and saved is not None:
        channel = guild.get_channel(saved.channel_id)
    if channel is None:
        overwrites = {
            guild.default_role: _permission(view_channel=False),
            owner: _permission(view_channel=True, read_message_history=True, send_messages=True),
        }
        bot_member = getattr(guild, "me", None)
        if bot_member is not None:
            overwrites[bot_member] = _permission(
                view_channel=True,
                read_message_history=True,
                send_messages=True,
                manage_messages=True,
            )
        category = guild.get_channel(ACCOUNT_CONTROL_CATEGORY_ID)
        if category is None and hasattr(guild, "create_category"):
            category = await guild.create_category("Station", overwrites=overwrites)
        channel = await guild.create_text_channel(
            ACCOUNT_CONTROL_CHANNEL_NAME,
            category=category,
            overwrites=overwrites,
            reason="AGK private account control center",
        )

    if getattr(channel, "guild", guild) is not guild and int(channel.guild.id) != ACCOUNT_CONTROL_GUILD_ID:
        raise PermissionError("account control channel escaped the Station guild")

    if hasattr(channel, "set_permissions"):
        await channel.set_permissions(
            guild.default_role,
            view_channel=False,
            reason="Keep AGK account control private",
        )
        await channel.set_permissions(
            owner,
            view_channel=True,
            read_message_history=True,
            send_messages=True,
            reason="Authorize exact AGK account owner",
        )
        bot_member = getattr(guild, "me", None)
        if bot_member is not None:
            await channel.set_permissions(
                bot_member,
                view_channel=True,
                read_message_history=True,
                send_messages=True,
                manage_messages=True,
                reason="Allow AGK account control reconciliation",
            )

    message = await _fetch_message(channel, ACCOUNT_CONTROL_MESSAGE_ID)
    if message is None and saved is not None and saved.channel_id == int(channel.id):
        message = await _fetch_message(channel, saved.message_id)
    view = getattr(adapter, "_account_control_view", None)
    if view is None:
        view = AccountControlView(adapter, channel_id=int(channel.id))
        adapter._account_control_view = view
    view.channel_id = int(channel.id)
    content = _render(adapter)
    if message is None:
        message = await channel.send(content=content, view=view)
    else:
        await message.edit(content=content, view=view)
    if not getattr(message, "pinned", False):
        await message.pin(reason="Persistent AGK account control center")
    view.message = message
    state = AccountControlState(channel_id=int(channel.id), message_id=int(message.id))
    _write_state(adapter, state)
    return state


def register_account_control_center(bot: Any, adapter: Any) -> None:
    """Register the durable view once; reconciliation binds its one message."""
    if getattr(adapter, "_account_control_view_registered", False):
        return
    view = getattr(adapter, "_account_control_view", None)
    if view is None:
        view = AccountControlView(adapter)
        adapter._account_control_view = view
    bot.add_view(view)
    adapter._account_control_view_registered = True
