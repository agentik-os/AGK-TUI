#!/usr/bin/env python3
"""Validate a Discord bot token from stdin and store it in one isolated Hermes vault."""
from __future__ import annotations

import argparse
import json
import os
import re
import tempfile
import urllib.error
import urllib.request
from pathlib import Path


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise urllib.error.HTTPError(req.full_url, code, "redirect refused", headers, fp)


_BOT_ID = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def canonical_bot_id(value: str) -> str:
    bot_id = str(value or "")
    if not _BOT_ID.fullmatch(bot_id):
        raise ValueError("bot id must use canonical lowercase kebab grammar")
    return bot_id


def invite_url(application_id: str) -> str:
    return (
        "https://discord.com/oauth2/authorize?client_id="
        + str(application_id)
        + "&scope=bot%20applications.commands&permissions=274877975552"
    )


def _discord_json(path: str, token: str):
    request = urllib.request.Request(
        "https://discord.com/api/v10" + path,
        headers={"Authorization": "Bot " + token, "Accept": "application/json", "User-Agent": "AGK-Station/1"},
    )
    try:
        with urllib.request.build_opener(NoRedirect).open(request, timeout=15) as response:
            return json.loads(response.read())
    except Exception as exc:
        raise ValueError("Discord rejected the credential") from exc


def validate_discord_token(secret: str) -> dict:
    identity = _discord_json("/users/@me", secret)
    guild_rows = _discord_json("/users/@me/guilds", secret)
    application = _discord_json("/oauth2/applications/@me", secret)
    if not isinstance(identity, dict) or not identity.get("id"):
        raise ValueError("Discord identity validation failed")
    if not isinstance(application, dict) or not application.get("id"):
        raise ValueError("Discord application validation failed")
    application_bot = application.get("bot")
    if not isinstance(application_bot, dict) or str(application_bot.get("id") or "") != str(identity["id"]):
        raise ValueError("Discord application identity does not match the bot")
    if not isinstance(guild_rows, list):
        raise ValueError("Discord guild validation failed")
    guilds = [str(row.get("id")) for row in guild_rows if isinstance(row, dict) and row.get("id")]
    return {
        "id": str(identity["id"]),
        "username": str(identity.get("username") or "bot")[:100],
        "application_id": str(application["id"]),
        "guilds": guilds,
    }


def _inside(path: Path, root: Path) -> bool:
    target, allowed = path.resolve(), root.resolve()
    return target == allowed or allowed in target.parents


def install_token(
    secret: str,
    target: Path,
    *,
    expected_guild: str,
    expected_application: str | None = None,
    allowed_root: Path | None = None,
    bot_id: str | None = None,
) -> dict:
    value = str(secret or "").strip()
    if not value or len(value) > 4096:
        raise ValueError("invalid credential length")
    root = (allowed_root or Path.home() / ".hermes").resolve()
    target = Path(target).resolve()
    if not _inside(target, root):
        raise ValueError("target escapes the isolated Station vault")
    key = "DISCORD_BOT_TOKEN"
    if bot_id is not None:
        key = "DISCORD_BOT_" + canonical_bot_id(bot_id).replace("-", "_").upper() + "_TOKEN"
    identity = validate_discord_token(value)
    if expected_application is not None and str(identity.get("application_id") or "") != str(expected_application):
        raise ValueError("bot does not match the expected application")
    if str(expected_guild) not in set(identity.get("guilds") or []):
        raise ValueError("bot does not have access to the exact guild")
    current = target.read_text(encoding="utf-8").splitlines() if target.is_file() else []
    output = []
    replaced = False
    for line in current:
        if line.startswith(key + "="):
            output.append(key + "=" + value)
            replaced = True
        else:
            output.append(line)
    if not replaced:
        output.append(key + "=" + value)
    target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(prefix=f".{target.name}.discord-token-", dir=target.parent)
    temporary = Path(temporary_name)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write("\n".join(output) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(target)
    except Exception:
        try:
            os.close(fd)
        except OSError:
            pass
        temporary.unlink(missing_ok=True)
        raise
    result = {"id": identity["id"], "username": identity["username"], "guild_id": str(expected_guild)}
    if identity.get("application_id"):
        result["application_id"] = str(identity["application_id"])
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", type=Path, required=True)
    parser.add_argument("--allowed-root", type=Path)
    parser.add_argument("--expected-guild", required=True)
    parser.add_argument("--expected-application")
    parser.add_argument("--bot-id", type=canonical_bot_id)
    args = parser.parse_args()
    secret = os.read(0, 8193).decode("utf-8", "strict")
    if len(secret.encode()) > 8192:
        raise SystemExit("credential rejected")
    try:
        result = install_token(
            secret,
            args.target,
            expected_guild=args.expected_guild,
            expected_application=args.expected_application,
            allowed_root=args.allowed_root,
            bot_id=args.bot_id,
        )
    except ValueError:
        print(json.dumps({"status": "REJECTED"}))
        return 1
    result["invite_url"] = invite_url(result["application_id"])
    print(json.dumps({"status": "INSTALLED", **result}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
