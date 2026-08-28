"""Registry-driven Discord `/os` control center."""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Callable, Iterable

import discord
from discord import app_commands


@dataclass(frozen=True)
class OsViewRecord:
    os_id: str
    name: str
    version: str
    owner_environment: str
    profile_id: str
    profile_state: str
    agent_state: str
    discord_mode: str
    discord_state: str
    doctor_state: str


def records_from_snapshot(path: Path) -> list[OsViewRecord]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    organisations = payload.get("organisations") if isinstance(payload, dict) else {}
    if not isinstance(organisations, dict):
        return []
    rows: dict[str, OsViewRecord] = {}
    for environment, station in organisations.items():
        if not isinstance(station, dict):
            continue
        for item in station.get("os") or []:
            if not isinstance(item, dict) or not item.get("id"):
                continue
            owner_value = item.get("owner_environment")
            if not owner_value:
                continue
            owner = str(owner_value)
            if owner != environment:
                continue
            record = OsViewRecord(
                os_id=str(item["id"]), name=str(item.get("name") or item["id"]),
                version=str(item.get("version") or ""), owner_environment=owner,
                profile_id=str(item.get("profile_id") or item["id"]),
                profile_state=str(item.get("profile_state") or "missing"),
                agent_state=str(item.get("agent_state") or "missing"),
                discord_mode=str(item.get("discord_mode") or "disabled"),
                discord_state=str(item.get("discord_state") or "disabled"),
                doctor_state=str(item.get("doctor_state") or "blocked"),
            )
            rows[record.os_id] = record
    return sorted(rows.values(), key=lambda row: (row.owner_environment, row.name.casefold(), row.os_id))


def _next_action(record: OsViewRecord) -> str:
    if record.profile_state != "ready":
        return "Install profile"
    if record.agent_state != "ready":
        return "Bind owning agent"
    if record.doctor_state != "ready":
        return "Run doctor"
    if record.discord_state == "owner-prerequisite":
        return "Complete Discord OAuth"
    return "No action"


class OsSelect(discord.ui.Select):
    def __init__(self, parent: "OsControlView"):
        self.parent_view = parent
        options = [
            discord.SelectOption(
                label=record.name[:100],
                value=record.os_id,
                description=f"{record.owner_environment} · {record.profile_state} · {record.version}"[:100],
                default=record.os_id == parent.selected_id,
            )
            for record in parent.page_records[:25]
        ]
        if parent.has_next_page and len(options) == 25:
            options[-1] = discord.SelectOption(label="Next page", value="__next__", description="Show more OS entries")
        super().__init__(placeholder="Choose an Operative System", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        value = self.values[0]
        if value == "__next__":
            self.parent_view.page += 1
            self.parent_view.selected_id = self.parent_view.page_records[0].os_id
        else:
            self.parent_view.selected_id = value
        self.parent_view.rebuild()
        await interaction.response.edit_message(content=self.parent_view.render_content(), view=self.parent_view)


class OsControlView(discord.ui.View):
    page_size = 25

    def __init__(self, records: Iterable[OsViewRecord], *, owner_ids: set[int], timeout: float = 900):
        super().__init__(timeout=timeout)
        self.records = tuple(sorted(records, key=lambda row: (row.owner_environment, row.name.casefold(), row.os_id)))
        self.owner_ids = {int(value) for value in owner_ids}
        self.page = 0
        self.selected_id = self.records[0].os_id if self.records else ""
        self.rebuild()

    @property
    def page_records(self) -> tuple[OsViewRecord, ...]:
        start = self.page * self.page_size
        return self.records[start:start + self.page_size]

    @property
    def has_next_page(self) -> bool:
        return (self.page + 1) * self.page_size < len(self.records)

    @property
    def selected(self) -> OsViewRecord | None:
        return next((record for record in self.records if record.os_id == self.selected_id), None)

    def rebuild(self) -> None:
        self.clear_items()
        if self.records:
            self.add_item(OsSelect(self))
        for item in (self.install, self.repair, self.doctor, self.discord_setup, self.refresh, self.back, self.close):
            self.add_item(item)

    def render_content(self) -> str:
        record = self.selected
        if record is None:
            return "**OS Control**\nNo registered Operative Systems."
        return "\n".join([
            f"**{record.name} · {record.version}**",
            f"Owner: `{record.owner_environment}` · Profile: {record.profile_state} · Agent: {record.agent_state}",
            f"Discord: {record.discord_mode}/{record.discord_state} · Doctor: {record.doctor_state}",
            f"Next: {_next_action(record)}",
        ])

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if int(interaction.user.id) in self.owner_ids:
            return True
        await interaction.response.send_message("Not authorized", ephemeral=True)
        return False

    async def _read_only(self, interaction: discord.Interaction, action: str) -> None:
        await interaction.response.send_message(f"{action} requires a staged confirmation.", ephemeral=True)

    @discord.ui.button(label="Install", style=discord.ButtonStyle.primary, row=1)
    async def install(self, interaction: discord.Interaction, _button: discord.ui.Button):
        await self._read_only(interaction, "Install")

    @discord.ui.button(label="Repair", style=discord.ButtonStyle.secondary, row=1)
    async def repair(self, interaction: discord.Interaction, _button: discord.ui.Button):
        await self._read_only(interaction, "Repair")

    @discord.ui.button(label="Doctor", style=discord.ButtonStyle.secondary, row=1)
    async def doctor(self, interaction: discord.Interaction, _button: discord.ui.Button):
        await self._read_only(interaction, "Doctor")

    @discord.ui.button(label="Discord", style=discord.ButtonStyle.secondary, row=1)
    async def discord_setup(self, interaction: discord.Interaction, _button: discord.ui.Button):
        await self._read_only(interaction, "Discord setup")

    @discord.ui.button(label="Refresh", style=discord.ButtonStyle.secondary, row=2)
    async def refresh(self, interaction: discord.Interaction, _button: discord.ui.Button):
        self.rebuild()
        await interaction.response.edit_message(content=self.render_content(), view=self)

    @discord.ui.button(label="Back", style=discord.ButtonStyle.secondary, row=2)
    async def back(self, interaction: discord.Interaction, _button: discord.ui.Button):
        if self.page > 0:
            self.page -= 1
            self.selected_id = self.page_records[0].os_id
        self.rebuild()
        await interaction.response.edit_message(content=self.render_content(), view=self)

    @discord.ui.button(label="Close", style=discord.ButtonStyle.danger, row=2)
    async def close(self, interaction: discord.Interaction, _button: discord.ui.Button):
        self.stop()
        await interaction.response.edit_message(content="OS Control closed.", view=None)


def register_os_control_center(
    bot,
    catalog_loader: Callable[[], Iterable[OsViewRecord]],
    *,
    owner_ids: set[int],
) -> app_commands.Command:
    async def command_callback(interaction: discord.Interaction):
        view = OsControlView(catalog_loader(), owner_ids=owner_ids)
        await interaction.response.send_message(view.render_content(), view=view, ephemeral=True)

    command = app_commands.Command(
        name="os",
        description="Inspect and operate registered AGK Operative Systems.",
        callback=command_callback,
    )
    bot.tree.add_command(command, override=True)
    return command
