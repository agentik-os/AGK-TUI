from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
MODULE = ROOT / "hermes/plugins/platforms/discord/agk_os_control_ui.py"
SPEC = importlib.util.spec_from_file_location("agk_os_control_ui_tested", MODULE)
assert SPEC and SPEC.loader
ui = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = ui
SPEC.loader.exec_module(ui)


def record(index: int):
    return ui.OsViewRecord(
        os_id=f"os-{index:02d}", name=f"OS {index:02d}", version="1.0.0",
        owner_environment="private", profile_id=f"os-{index:02d}",
        profile_state="missing", agent_state="declared", discord_mode="disabled",
        discord_state="disabled", doctor_state="blocked",
    )


def test_select_paginates_after_twenty_five_entries():
    view = ui.OsControlView([record(i) for i in range(31)], owner_ids={1})
    select = next(child for child in view.children if isinstance(child, ui.OsSelect))
    assert len(select.options) == 25
    assert view.has_next_page is True
    assert len(view.children) <= 8


def test_compact_copy_contains_current_state_and_no_paths_or_secrets():
    view = ui.OsControlView([record(1)], owner_ids={1})
    content = view.render_content()
    assert "OS 01" in content
    assert "Profile: missing" in content
    assert "Next: Install profile" in content
    assert "/home/" not in content
    assert "TOKEN" not in content.upper()


class Response:
    def __init__(self):
        self.messages = []

    async def send_message(self, content, **kwargs):
        self.messages.append((content, kwargs))


class Interaction:
    def __init__(self, user_id):
        self.user = type("User", (), {"id": user_id})()
        self.response = Response()


@pytest.mark.asyncio
async def test_every_callback_rechecks_owner_authorization():
    view = ui.OsControlView([record(1)], owner_ids={1})
    interaction = Interaction(2)
    assert await view.interaction_check(interaction) is False
    assert interaction.response.messages == [("Not authorized", {"ephemeral": True})]


class Tree:
    def __init__(self):
        self.commands = []

    def add_command(self, command, override=False):
        self.commands.append((command, override))


class Bot:
    def __init__(self):
        self.tree = Tree()


def test_register_adds_exact_os_application_command():
    bot = Bot()
    ui.register_os_control_center(bot, lambda: [record(1)], owner_ids={1})
    assert len(bot.tree.commands) == 1
    command, override = bot.tree.commands[0]
    assert command.name == "os"
    assert override is True
