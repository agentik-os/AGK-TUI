from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

import discord

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "hermes"))
sys.path.insert(1, "/opt/agk-terminal/hermes-agent")

from gateway.config import PlatformConfig  # noqa: E402
import plugins.platforms.discord  # noqa: E402

SOURCE_PACKAGE = str(ROOT / "hermes/plugins/platforms/discord")
plugins.platforms.discord.__path__.insert(0, SOURCE_PACKAGE)
ADAPTER = ROOT / "hermes/plugins/platforms/discord/adapter.py"
SPEC = importlib.util.spec_from_file_location(
    "plugins.platforms.discord.adapter_scope_tested", ADAPTER
)
assert SPEC and SPEC.loader
adapter_module = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = adapter_module
SPEC.loader.exec_module(adapter_module)
DiscordAdapter = adapter_module.DiscordAdapter


class TextChannel:
    def __init__(self, channel_id: int):
        self.id = channel_id
        self.name = "outside"
        self.parent_id = None


def test_bot_mentions_cannot_bypass_profile_channel_allowlist():
    adapter = DiscordAdapter(PlatformConfig(
        enabled=True,
        token="fake-token",
        extra={"allowed_channels": ["1542137541572956193"], "allow_bots": "all"},
    ))
    adapter._client = SimpleNamespace(user=SimpleNamespace(id=1542135948475637861, bot=True))
    author = SimpleNamespace(id=1541816910587625492, bot=True)
    message = SimpleNamespace(
        id=1,
        type=discord.MessageType.default,
        author=author,
        channel=TextChannel(1541820137148260432),
        guild=SimpleNamespace(id=1541131439599386644),
        mentions=[adapter._client.user],
        content="<@1542135948475637861> wake outside your OS channel",
    )

    admitted, _role_authorized = adapter._discord_message_admission(message, claim=False)

    assert admitted is False
