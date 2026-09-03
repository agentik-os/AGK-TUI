#!/usr/bin/env python3
"""Keep Discord Station cards and child threads aligned with live work. Never stops a gateway."""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

API = "https://discord.com/api/v10"


def load_env(home: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    env_path = home / ".env"
    if env_path.exists():
        for raw in env_path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def token_from(home: Path) -> str:
    env = load_env(home)
    token = env.get("DISCORD_BOT_TOKEN") or env.get("DISCORD_TOKEN") or ""
    if not token:
        raise SystemExit("discord token missing")
    return token


def discord(token: str, method: str, path: str, body: Any | None = None) -> Any:
    data = None if body is None else json.dumps(body, ensure_ascii=False).encode("utf-8")
    headers = {"Authorization": f"Bot {token}", "User-Agent": "AGK-StationProgress/1.0"}
    if data is not None:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(API + path, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            raw = response.read()
            return json.loads(raw.decode() or "{}") if raw else {}
    except urllib.error.HTTPError as error:
        err = error.read().decode("utf-8", "replace")
        raise RuntimeError(f"Discord {method} {path} HTTP {error.code}") from None


def live_leases(home: Path, now: float) -> list[dict[str, Any]]:
    db = home / "state.db"
    if not db.exists():
        return []
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    rows = []
    try:
        for row in con.execute(
            "SELECT conversation_id, holder, acquired_at, expires_at FROM session_turn_leases"
        ):
            if float(row["expires_at"] or 0) > now:
                rows.append(dict(row))
    except sqlite3.Error:
        return []
    return rows


def open_delegations(home: Path, session_id: str) -> list[dict[str, Any]]:
    db = home / "state.db"
    if not db.exists() or not session_id:
        return []
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    out = []
    try:
        for row in con.execute(
            "SELECT delegation_id, parent_session_id, state, dispatched_at, completed_at FROM async_delegations WHERE parent_session_id=?",
            (session_id,),
        ):
            out.append(dict(row))
    except sqlite3.Error:
        return []
    return out


def render(label: str, objective: str, items: list[dict], status: str, extra: str = "") -> str:
    from gateway.station_action_message import render_action_message

    text = render_action_message(label, objective, items, status=status)
    if extra:
        text = text.rstrip() + "\n\nSESSIONS\n" + extra
    return text[:1900]


def sync_card(home: Path, token: str, now: float) -> dict[str, Any]:
    import sys

    sys.path.insert(0, "/opt/agk-terminal/hermes-agent")
    state_path = home / "gateway" / "station_action_messages.json"
    cards = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {}
    leases = live_leases(home, now)
    reports = []
    lease_sessions = {row["conversation_id"] for row in leases}
    for key, card in cards.items():
        if not isinstance(card, dict):
            continue
        session_id = ""
        # session_id is not on the card; recover from sessions.json
        reports.append(sync_one(home, token, key, card, lease_sessions, now))
    return {"leases": len(leases), "cards": reports}


def session_id_for_thread(home: Path, thread_id: str) -> str:
    sessions = json.loads((home / "sessions" / "sessions.json").read_text(encoding="utf-8"))
    rec = sessions.get(f"agent:main:discord:thread:{thread_id}:{thread_id}") or {}
    return str(rec.get("session_id") or "")


def sync_one(home: Path, token: str, key: str, card: dict, lease_sessions: set[str], now: float) -> dict[str, Any]:
    chat_id = str(card.get("chat_id") or card.get("thread_id") or "")
    message_id = str(card.get("message_id") or "")
    if not chat_id.isdigit() or not message_id.isdigit():
        return {"key": key, "status": "skip"}
    session_id = session_id_for_thread(home, chat_id)
    live = session_id in lease_sessions
    items = card.get("items") if isinstance(card.get("items"), list) else []
    # items may have been persisted as objects
    if items and isinstance(items[0], dict):
        pass
    else:
        items = []
    children = open_delegations(home, session_id)
    running_children = [row for row in children if row.get("state") not in {"completed", "failed", "error", "cancelled"}]
    extra_lines = []
    child_map = card.get("child_threads") if isinstance(card.get("child_threads"), dict) else {}
    parent = chat_id
    for row in running_children:
        did = str(row["delegation_id"])
        if did in child_map:
            extra_lines.append(f"→ {did} https://discord.com/channels/{card.get('guild_id') or '1541131439599386644'}/{child_map[did]}")
            continue
        name = f"session-{did[-8:]}"[:100]
        try:
            # AGK_THREAD_CREATE_AUTO_WAKE_V1: never leave child session threads empty.
            starter = f"Child session `{did}` for live work. Parent <#{parent}>."
            thread = discord(token, "POST", f"/channels/{parent}/threads", {
                "name": name,
                "type": 11,
                "auto_archive_duration": 1440,
            })
            tid = str(thread.get("id") or "")
            if tid.isdigit():
                child_map[did] = tid
                filled = False
                for _attempt in range(3):
                    try:
                        discord(token, "POST", f"/channels/{tid}/messages", {
                            "content": starter
                        })
                        meta = discord(token, "GET", f"/channels/{tid}")
                        if int(meta.get("message_count") or meta.get("total_message_sent") or 0) >= 1:
                            filled = True
                            break
                    except RuntimeError:
                        pass
                if not filled:
                    raise RuntimeError(f"AGK_THREAD_CREATE_AUTO_WAKE_V1 FAILED wake: empty child thread {tid}")
                extra_lines.append(f"→ {did} <#{tid}>")
        except RuntimeError:
            extra_lines.append(f"→ {did} (thread pending)")
    if live:
        status = "RUNNING"
        blocked = None
        if not items:
            items = [{"id": "live", "content": "Background turn in progress", "status": "in_progress"}]
        else:
            # keep existing items; mark first pending as in_progress for the bar
            found = False
            new_items = []
            for item in items:
                row = dict(item)
                if not found and row.get("status") in {"pending", "in_progress"}:
                    row["status"] = "in_progress"
                    found = True
                new_items.append(row)
            items = new_items
    else:
        status = str(card.get("status") or "RUNNING")
        blocked = card.get("blocked_reason")
    extra = "\n".join(extra_lines)
    try:
        from gateway.station_action_message import render_action_message
        content = render_action_message(
            str(card.get("label") or "Station"),
            str(card.get("objective") or "Executing requested action"),
            items,
            status=status,
            blocked_reason=None if live else blocked,
        )
        if extra:
            content = (content.rstrip() + "\n\nSESSIONS\n" + extra)[:1900]
        discord(token, "PATCH", f"/channels/{chat_id}/messages/{message_id}", {"content": content})
        card["status"] = status
        if live:
            card["blocked_reason"] = None
        card["child_threads"] = child_map
        card["items"] = items
        return {"key": key, "status": "edited", "live": live, "children": list(child_map)}
    except Exception as error:
        return {"key": key, "status": "error", "error": type(error).__name__}


def create_progress_test(token: str, parent_id: str) -> dict[str, Any]:
    seed = discord(token, "POST", f"/channels/{parent_id}/messages", {
        "content": "Station progress test (display only, no mission)."
    })
    seed_id = str(seed.get("id") or "")
    thread = discord(token, "POST", f"/channels/{parent_id}/threads", {
        "name": "station-progress-test",
        "type": 11,
        "auto_archive_duration": 60,
        "message": {"content": "Station progress test thread."},
    })
    # fallback start thread from seed
    thread_id = str(thread.get("id") or "")
    if not thread_id.isdigit() and seed_id.isdigit():
        thread = discord(token, "POST", f"/channels/{parent_id}/messages/{seed_id}/threads", {
            "name": "station-progress-test",
            "auto_archive_duration": 60,
        })
        thread_id = str(thread.get("id") or "")
    if not thread_id.isdigit():
        raise RuntimeError("could not create test thread")
    from gateway.station_action_message import render_action_message
    items0 = [
        {"id": "a", "content": "Read live Station card", "status": "completed"},
        {"id": "b", "content": "Render progress bar", "status": "in_progress"},
        {"id": "c", "content": "Open child session thread", "status": "pending"},
    ]
    msg = discord(token, "POST", f"/channels/{thread_id}/messages", {
        "content": render_action_message("agentik", "Verify Discord shows live work", items0, status="RUNNING")
    })
    mid = str(msg.get("id") or "")
    child = discord(token, "POST", f"/channels/{parent_id}/threads", {
        "name": "session-child-test",
        "type": 11,
        "auto_archive_duration": 60,
        "message": {"content": f"Child session of <#{thread_id}>. Progress parent stays in that thread."},
    })
    child_id = str(child.get("id") or "")
    items1 = [
        {"id": "a", "content": "Read live Station card", "status": "completed"},
        {"id": "b", "content": "Render progress bar", "status": "completed"},
        {"id": "c", "content": "Open child session thread", "status": "in_progress"},
    ]
    extra = f"→ child-test <#{child_id}>" if child_id.isdigit() else ""
    content = render_action_message("agentik", "Verify Discord shows live work", items1, status="RUNNING")
    if extra:
        content = (content.rstrip() + "\n\nSESSIONS\n" + extra)[:1900]
    if mid.isdigit():
        discord(token, "PATCH", f"/channels/{thread_id}/messages/{mid}", {"content": content})
    time.sleep(2)
    items2 = [
        {"id": "a", "content": "Read live Station card", "status": "completed"},
        {"id": "b", "content": "Render progress bar", "status": "completed"},
        {"id": "c", "content": "Open child session thread", "status": "completed"},
    ]
    content = render_action_message("agentik", "Verify Discord shows live work", items2, status="COMPLETE")
    if extra:
        content = (content.rstrip() + "\n\nSESSIONS\n" + extra)[:1900]
    if mid.isdigit():
        discord(token, "PATCH", f"/channels/{thread_id}/messages/{mid}", {"content": content})
    return {
        "thread_id": thread_id,
        "message_id": mid,
        "child_id": child_id,
        "url": f"https://discord.com/channels/1541131439599386644/{thread_id}",
        "child_url": f"https://discord.com/channels/1541131439599386644/{child_id}" if child_id.isdigit() else None,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--home", default="/home/agentik/.hermes")
    parser.add_argument("--sync-live", action="store_true")
    parser.add_argument("--test-parent", default="")
    args = parser.parse_args()
    home = Path(args.home)
    os.environ.setdefault("HERMES_HOME", str(home))
    import sys
    sys.path.insert(0, "/opt/agk-terminal/hermes-agent")
    token = token_from(home)
    report: dict[str, Any] = {}
    if args.sync_live:
        report["sync"] = sync_card(home, token, time.time())
    if args.test_parent:
        report["test"] = create_progress_test(token, args.test_parent)
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
