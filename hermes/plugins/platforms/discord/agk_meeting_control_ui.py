"""Persistent owner-only meeting controls for canonical Meetings forum posts."""

from __future__ import annotations

import asyncio
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    import discord
except ImportError:  # pragma: no cover
    discord = None

MODULE_DIR = Path(__file__).resolve().parents[2] / "agentik_os"
if str(MODULE_DIR) not in sys.path:
    sys.path.insert(0, str(MODULE_DIR))

from meeting_actions import AtomicMeetingActions
from meeting_control import MeetingActionCoordinator, meeting_id_for_thread
from meeting_forum import meeting_lifecycle
from meeting_registry import AtomicMeetingRegistry

OWNER_ID = 1441423462492016821
GUILD_ID = 1541131439599386644
FORUM_ID = 1542526162062938152
STATE_PATH = Path("/var/lib/agk-meeting-registry/publication-state.json")
REGISTRY_PATH = Path("/var/lib/agk-meeting-registry/registry.json")
ACTIONS_PATH = Path("/var/lib/agk-meeting-registry/actions.json")


@dataclass(frozen=True)
class MeetingContext:
    meeting: dict[str, Any]
    bindings: list[dict[str, str]]


def authorized(interaction: Any) -> bool:
    return (
        int(getattr(getattr(interaction, "user", None), "id", 0)) == OWNER_ID
        and int(getattr(interaction, "guild_id", 0) or 0) == GUILD_ID
        and int(getattr(getattr(interaction, "channel", None), "parent_id", 0) or 0)
        == FORUM_ID
    )


def resolve_context(
    thread_id: int,
    *,
    publication_state: Path = STATE_PATH,
    registry_path: Path = REGISTRY_PATH,
    actions_path: Path = ACTIONS_PATH,
) -> MeetingContext:
    meeting_id = meeting_id_for_thread(publication_state, thread_id)
    if not meeting_id:
        raise ValueError("meeting thread is not registered")
    meetings = AtomicMeetingRegistry(registry_path).load()
    rows = [row for row in meetings if row.get("id") == meeting_id]
    bindings = AtomicMeetingActions(actions_path).load().get(meeting_id, [])
    if len(rows) != 1 or not bindings:
        raise ValueError("meeting provider binding is unavailable")
    return MeetingContext(rows[0], bindings)


class CommandRunner:
    def execute(
        self, slug: str, data: dict[str, Any], *, account: str
    ) -> dict[str, Any]:
        result = subprocess.run(
            [
                "/home/operator/.local/bin/composio",
                "execute",
                slug,
                "--account",
                account,
                "-d",
                json.dumps(data, separators=(",", ":")),
            ],
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError("Composio meeting action failed")
        value = json.loads(result.stdout)
        if not isinstance(value, dict):
            raise TypeError("Composio returned invalid meeting action data")
        return value


async def _deny(interaction: Any) -> None:
    if interaction.response.is_done():
        await interaction.followup.send("Not authorized.", ephemeral=True)
    else:
        await interaction.response.send_message("Not authorized.", ephemeral=True)


async def _apply_tag(interaction: Any, name: str) -> None:
    parent = interaction.channel.parent
    tags = {tag.name: tag for tag in getattr(parent, "available_tags", [])}
    tag = tags.get(name)
    if tag:
        await interaction.channel.edit(applied_tags=[tag])


async def _execute_cancel(interaction: Any) -> None:
    context = await asyncio.to_thread(resolve_context, int(interaction.channel_id))
    coordinator = MeetingActionCoordinator(CommandRunner())
    result = await asyncio.to_thread(
        coordinator.cancel,
        context.bindings,
        reason="Owner canceled from AGK Meetings forum",
    )
    await _apply_tag(interaction, "Canceled")
    await interaction.followup.send(
        f"Canceled and verified through `{result['source']}`. The canonical post will refresh on the next sync.",
        ephemeral=True,
    )


_ViewBase = discord.ui.View if discord else object


class MeetingControlView(_ViewBase):
    def __init__(self) -> None:
        super().__init__(timeout=None)

    async def _authorize(self, interaction: Any) -> bool:
        if authorized(interaction):
            return True
        await _deny(interaction)
        return False

    @discord.ui.button(
        label="Refresh",
        style=discord.ButtonStyle.secondary,
        custom_id="agkmeet:refresh",
    )
    async def refresh(self, interaction: Any, _button: Any) -> None:
        if not await self._authorize(interaction):
            return
        await interaction.response.defer(ephemeral=True)
        context = await asyncio.to_thread(resolve_context, int(interaction.channel_id))
        status = meeting_lifecycle(context.meeting, now=discord.utils.utcnow())
        await _apply_tag(interaction, status)
        await interaction.followup.send(
            f"Status refreshed: **{status}**. Calendar reconciliation runs every five minutes.",
            ephemeral=True,
        )

    @discord.ui.button(
        label="Reschedule",
        style=discord.ButtonStyle.primary,
        custom_id="agkmeet:reschedule",
    )
    async def reschedule(self, interaction: Any, _button: Any) -> None:
        if not await self._authorize(interaction):
            return
        await interaction.response.send_modal(RescheduleModal())

    @discord.ui.button(
        label="Cancel",
        style=discord.ButtonStyle.danger,
        custom_id="agkmeet:cancel",
    )
    async def cancel(self, interaction: Any, _button: Any) -> None:
        if not await self._authorize(interaction):
            return
        await interaction.response.defer(ephemeral=True)
        context = await asyncio.to_thread(resolve_context, int(interaction.channel_id))
        await interaction.followup.send(
            f"Cancel **{context.meeting['title']}**? This updates the source calendar and notifies attendees where supported.",
            view=CancelConfirmView(),
            ephemeral=True,
        )

    @discord.ui.button(
        label="Granola",
        style=discord.ButtonStyle.secondary,
        custom_id="agkmeet:granola",
    )
    async def granola(self, interaction: Any, _button: Any) -> None:
        if not await self._authorize(interaction):
            return
        await interaction.response.defer(ephemeral=True)
        result = await asyncio.to_thread(_granola_status)
        await interaction.followup.send(result, ephemeral=True)


class CancelConfirmView(discord.ui.View if discord else object):
    def __init__(self) -> None:
        super().__init__(timeout=60)

    @discord.ui.button(label="Confirm cancel", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: Any, _button: Any) -> None:
        if not authorized(interaction):
            await _deny(interaction)
            return
        await interaction.response.defer(ephemeral=True)
        try:
            await _execute_cancel(interaction)
        except (
            OSError,
            ValueError,
            TypeError,
            RuntimeError,
            subprocess.SubprocessError,
        ) as exc:
            await interaction.followup.send(
                f"Cancellation failed safely (`{type(exc).__name__}`). No success was recorded.",
                ephemeral=True,
            )


class RescheduleModal(discord.ui.Modal if discord else object):
    start = discord.ui.TextInput(
        label="New start (ISO 8601 + timezone)",
        placeholder="2026-09-01T10:00:00+02:00",
        min_length=20,
        max_length=35,
    )

    def __init__(self) -> None:
        super().__init__(title="Reschedule meeting", timeout=300)

    async def on_submit(self, interaction: Any) -> None:
        if not authorized(interaction):
            await _deny(interaction)
            return
        await interaction.response.defer(ephemeral=True)
        try:
            context = await asyncio.to_thread(
                resolve_context, int(interaction.channel_id)
            )
            result = await asyncio.to_thread(
                MeetingActionCoordinator(CommandRunner()).reschedule,
                context.bindings,
                start=str(self.start),
            )
            await _apply_tag(interaction, "Upcoming")
            await interaction.followup.send(
                f"Rescheduled to `{result['start']}` and verified through `{result['source']}`.",
                ephemeral=True,
            )
        except (
            OSError,
            ValueError,
            TypeError,
            RuntimeError,
            subprocess.SubprocessError,
        ) as exc:
            await interaction.followup.send(
                f"Reschedule failed safely (`{type(exc).__name__}`). No success was recorded.",
                ephemeral=True,
            )


def _granola_status() -> str:
    listed = subprocess.run(
        ["/home/operator/.local/bin/composio", "link", "granola_mcp", "--list"],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    try:
        value = json.loads(listed.stdout)
    except ValueError:
        value = {}
    if value.get("total", 0):
        return "Granola MCP is connected. Reports are reconciled into this conversation after the meeting."
    linked = subprocess.run(
        [
            "/home/operator/.local/bin/composio",
            "link",
            "granola_mcp",
            "--no-wait",
            "--no-browser",
            "--alias",
            "granola-owner",
        ],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    try:
        url = json.loads(linked.stdout).get("redirect_url")
    except ValueError:
        url = None
    return (
        f"Granola authorization is required: {url}"
        if isinstance(url, str) and url.startswith("https://")
        else "Granola authorization is not ready. Ask Operator in #general."
    )


def register_meeting_control(client: Any) -> MeetingControlView:
    view = MeetingControlView()
    client.add_view(view)
    return view
