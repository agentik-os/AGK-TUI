#!/usr/bin/env python3
"""Synchronize Cal.com and Google Calendar into AGK Discord meeting surfaces."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from collections.abc import Callable, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

MODULE_DIR = Path(__file__).resolve().parents[1] / "hermes" / "plugins" / "agentik_os"
sys.path.insert(0, str(MODULE_DIR))

from meeting_live import (
    ComposioMeetingSource,
    PersistentDiscordMeetingClient,
    run_live_sync,
)


class CommandComposioRunner:
    def __init__(
        self,
        command: Sequence[str] = ("composio",),
        *,
        run: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
    ) -> None:
        self.command = tuple(command)
        self.run = run

    def _invoke(self, arguments: list[str]) -> dict[str, Any]:
        result = self.run(
            [*self.command, *arguments],
            check=False,
            capture_output=True,
            text=True,
            timeout=180,
        )
        if result.returncode != 0:
            raise RuntimeError("Composio read failed")
        try:
            value = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise RuntimeError("Composio returned invalid JSON") from exc
        if not isinstance(value, dict):
            raise TypeError("Composio returned an invalid payload")
        return value

    def execute(
        self, slug: str, data: dict[str, Any], *, account: str
    ) -> dict[str, Any]:
        return self._invoke(
            [
                "execute",
                slug,
                "--account",
                account,
                "-d",
                json.dumps(data, separators=(",", ":")),
            ]
        )

    def proxy(self, url: str, *, toolkit: str, account: str) -> dict[str, Any]:
        return self._invoke(["proxy", url, "--toolkit", toolkit, "--account", account])


class DiscordRestTransport:
    def __init__(
        self,
        token: str,
        *,
        open_request: Callable[..., Any] = urllib.request.urlopen,
    ) -> None:
        if not token:
            raise ValueError("Discord bot token is required")
        self.token = token
        self.open_request = open_request

    def request(
        self, method: str, path: str, payload: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        if not path.startswith("/") or ".." in path:
            raise ValueError("invalid Discord API path")
        body = json.dumps(payload).encode() if payload is not None else None
        request = urllib.request.Request(
            "https://discord.com/api/v10" + path,
            data=body,
            headers={
                "Authorization": "Bot " + self.token,
                "Content-Type": "application/json",
                "User-Agent": "AGK-Meeting-Registry/1.0",
            },
            method=method,
        )
        try:
            with self.open_request(request, timeout=30) as response:
                raw = response.read()
        except urllib.error.HTTPError as exc:
            if method == "GET" and exc.code == 404:
                raise KeyError(path) from None
            raise RuntimeError("Discord API request failed") from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            raise RuntimeError("Discord API request failed") from exc
        if not raw:
            return {}
        try:
            value = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise RuntimeError("Discord API returned invalid JSON") from exc
        if not isinstance(value, dict):
            raise TypeError("Discord API returned an invalid payload")
        return value


def _config(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError("meeting registry config must be a JSON object")
    expected = {"cal_account", "google_account", "horizon_days"}
    if set(value) != expected:
        raise ValueError("meeting registry config fields are invalid")
    if not all(
        isinstance(value[key], str) and value[key]
        for key in ("cal_account", "google_account")
    ):
        raise ValueError("meeting account selectors are invalid")
    horizon = value.get("horizon_days")
    if not isinstance(horizon, int) or not 1 <= horizon <= 90:
        raise ValueError("meeting horizon is invalid")
    return value


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config", type=Path, default=Path("/etc/agk-terminal/meeting-registry.json")
    )
    parser.add_argument(
        "--registry",
        type=Path,
        default=Path("/var/lib/agk-meeting-registry/registry.json"),
    )
    parser.add_argument(
        "--publication-state",
        type=Path,
        default=Path("/var/lib/agk-meeting-registry/publication-state.json"),
    )
    args = parser.parse_args(argv)
    config = _config(args.config)
    token = os.environ.get("DISCORD_BOT_TOKEN", "")
    source = ComposioMeetingSource(
        CommandComposioRunner(),
        cal_account=config["cal_account"],
        google_account=config["google_account"],
    )
    discord = PersistentDiscordMeetingClient(
        DiscordRestTransport(token), args.publication_state
    )
    result = run_live_sync(
        source=source,
        discord=discord,
        registry_path=args.registry,
        now=datetime.now(timezone.utc),
        horizon_days=config["horizon_days"],
    )
    print(
        json.dumps(
            {
                "registry": result["registry"],
                "actions": result["actions"],
                "meeting_count": result["meeting_count"],
                "events": result["discord"]["events"],
                "meeting_post_count": len(result["discord"]["meeting_posts"]),
                "forum_created": sum(
                    status == "created" for status in result["forum"].values()
                ),
                "forum_updated": sum(
                    status == "updated" for status in result["forum"].values()
                ),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
