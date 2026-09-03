#!/usr/bin/env python3
"""Flag Discord threads with message_count==0 within N minutes (AGK_THREAD_CREATE_AUTO_WAKE_V1)."""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

DEFAULT_PARENTS = [
    "1541820137148260432",  # operator・working
    "1541814383007764570",  # mission・working
    "1541820077278503072",  # private・idle
    "1541820106479501322",  # agentik・working
    "1541847685680603387",  # discord・idle
]


def read_token(env_path: Path) -> str:
    for line in env_path.read_text(encoding="utf-8").splitlines():
        if line.startswith("DISCORD_BOT_TOKEN="):
            return line.split("=", 1)[1].strip().strip("\"'")
    raise SystemExit(f"DISCORD_BOT_TOKEN missing in {env_path}")


def api(token: str, method: str, path: str):
    req = urllib.request.Request(
        "https://discord.com/api/v10" + path,
        method=method,
        headers={"Authorization": f"Bot {token}", "User-Agent": "AGK-EmptyThreadWatch/1.0"},
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return json.loads(resp.read() or b"{}")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")
        raise RuntimeError(f"HTTP {exc.code} {path}: {body[:200]}") from None


def snowflake_age_seconds(snowflake: str) -> float:
    ts = ((int(snowflake) >> 22) + 1420070400000) / 1000.0
    return time.time() - ts


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--minutes", type=float, default=30.0, help="Flag empty threads younger than N minutes")
    ap.add_argument("--home", default="/home/operator/.hermes", help="Hermes home for bot token")
    ap.add_argument("--guild", default="1541131439599386644")
    ap.add_argument("--parent", action="append", default=[], help="Parent channel id (repeatable)")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    parents = set(args.parent or DEFAULT_PARENTS)
    token = read_token(Path(args.home) / ".env")
    active = api(token, "GET", f"/guilds/{args.guild}/threads/active")
    threads = active.get("threads") if isinstance(active, dict) else []
    if not isinstance(threads, list):
        raise SystemExit("active threads payload malformed")
    flagged = []
    scanned = 0
    for row in threads:
        if not isinstance(row, dict):
            continue
        if str(row.get("parent_id") or "") not in parents:
            continue
        scanned += 1
        tid = str(row.get("id") or "")
        if not tid.isdigit():
            continue
        age_m = snowflake_age_seconds(tid) / 60.0
        if age_m > args.minutes:
            continue
        count = row.get("message_count")
        if count is None:
            try:
                meta = api(token, "GET", f"/channels/{tid}")
                count = meta.get("message_count", meta.get("total_message_sent"))
            except RuntimeError:
                count = None
        try:
            count_i = int(count) if count is not None else -1
        except (TypeError, ValueError):
            count_i = -1
        if count_i == 0:
            flagged.append(
                {
                    "thread_id": tid,
                    "name": row.get("name"),
                    "parent_id": row.get("parent_id"),
                    "owner_id": row.get("owner_id"),
                    "message_count": count_i,
                    "age_minutes": round(age_m, 2),
                    "url": f"https://discord.com/channels/{args.guild}/{tid}",
                }
            )
    payload = {
        "ok": True,
        "scanned_parent_threads": scanned,
        "flagged_empty": flagged,
        "minutes": args.minutes,
        "parents": sorted(parents),
        "contract": "AGK_THREAD_CREATE_AUTO_WAKE_V1",
    }
    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        print(f"AGK empty-thread watch: scanned={scanned} flagged={len(flagged)} window={args.minutes}m")
        for row in flagged:
            print(f"EMPTY {row['thread_id']} parent={row['parent_id']} age_m={row['age_minutes']} {row['name']} {row['url']}")
        if not flagged:
            print("No empty threads in window.")
    return 1 if flagged else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc), "error_class": type(exc).__name__}))
        raise SystemExit(2)
