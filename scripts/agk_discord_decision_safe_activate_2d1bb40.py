#!/usr/bin/env python3
from __future__ import annotations
import fcntl, json, os, subprocess, time
from pathlib import Path

RELEASE = "2d1bb40ab62942e86fc72462dfb137fe662f76b2"
SAFE = "/usr/local/lib/agk-terminal/scripts/station_safe_gateway_reload.py"
REPORT = Path("/var/lib/agk-station/discord-decision-activation-2d1bb40.json")
LOCK = Path("/run/agk-station/discord-decision-activation-2d1bb40.lock")
RUNTIME_FILES = (
    Path("/usr/local/lib/agk-terminal/hermes-core/gateway/run.py"),
    Path("/usr/local/lib/agk-terminal/hermes-core/tools/clarify_gateway.py"),
)
TARGETS = (('operator', 1000, 'hermes-gateway-builder-os.service', '/home/operator/.hermes/profiles/builder-os'), ('operator', 1000, 'hermes-gateway-connector-os.service', '/home/operator/.hermes/profiles/connector-os'), ('operator', 1000, 'hermes-gateway-icebreaker-os.service', '/home/operator/.hermes/profiles/icebreaker-os'), ('operator', 1000, 'hermes-gateway-relationship-os.service', '/home/operator/.hermes/profiles/relationship-os'), ('operator', 1000, 'hermes-gateway.service', '/home/operator/.hermes'), ('agentik', 1001, 'hermes-gateway-collective.service', '/home/agentik/.hermes/profiles/collective'), ('agentik', 1001, 'hermes-gateway.service', '/home/agentik/.hermes'), ('mission', 1002, 'hermes-gateway-clientdentistrygptee881c.service', '/home/mission/.hermes/profiles/clientdentistrygptee881c'), ('mission', 1002, 'hermes-gateway-clientloumna7b2934.service', '/home/mission/.hermes/profiles/clientloumna7b2934'), ('mission', 1002, 'hermes-gateway-clientmoonbasecapital4cda09.service', '/home/mission/.hermes/profiles/clientmoonbasecapital4cda09'), ('mission', 1002, 'hermes-gateway.service', '/home/mission/.hermes'), ('private', 1003, 'hermes-gateway-alignment-os.service', '/home/private/.hermes/profiles/alignment-os'), ('private', 1003, 'hermes-gateway-decision-os.service', '/home/private/.hermes/profiles/decision-os'), ('private', 1003, 'hermes-gateway-goal-life-strategy-os.service', '/home/private/.hermes/profiles/goal-life-strategy-os'), ('private', 1003, 'hermes-gateway-habit-tracker-os.service', '/home/private/.hermes/profiles/habit-tracker-os'), ('private', 1003, 'hermes-gateway-health-energy-os.service', '/home/private/.hermes/profiles/health-energy-os'), ('private', 1003, 'hermes-gateway-identity-shift-os.service', '/home/private/.hermes/profiles/identity-shift-os'), ('private', 1003, 'hermes-gateway-intuitive-os.service', '/home/private/.hermes/profiles/intuitive-os'), ('private', 1003, 'hermes-gateway-journal-os.service', '/home/private/.hermes/profiles/journal-os'), ('private', 1003, 'hermes-gateway-librarian-os.service', '/home/private/.hermes/profiles/librarian-os'), ('private', 1003, 'hermes-gateway-life-designer.service', '/home/private/.hermes/profiles/life-designer'), ('private', 1003, 'hermes-gateway-mentor-os.service', '/home/private/.hermes/profiles/mentor-os'), ('private', 1003, 'hermes-gateway-mindset-os.service', '/home/private/.hermes/profiles/mindset-os'), ('private', 1003, 'hermes-gateway-nutrition-os.service', '/home/private/.hermes/profiles/nutrition-os'), ('private', 1003, 'hermes-gateway-oto100m-os.service', '/home/private/.hermes/profiles/oto100m-os'), ('private', 1003, 'hermes-gateway-social-intelligence-os.service', '/home/private/.hermes/profiles/social-intelligence-os'), ('private', 1003, 'hermes-gateway.service', '/home/private/.hermes'))
DEADLINE = time.monotonic() + 86400


def call(cmd):
    return subprocess.run(cmd, text=True, capture_output=True, check=False)


def gateway_state(home):
    try:
        return json.loads((Path(home) / "gateway_state.json").read_text())
    except Exception:
        return {}


def process_start_epoch(pid):
    try:
        ticks = int(Path(f"/proc/{pid}/stat").read_text().split()[21])
        btime = next(int(line.split()[1]) for line in Path("/proc/stat").read_text().splitlines() if line.startswith("btime "))
        return btime + ticks / os.sysconf("SC_CLK_TCK")
    except Exception:
        return 0.0


def current(row):
    state = gateway_state(row["home"])
    pid = int(state.get("pid") or 0)
    package_mtime = max(path.stat().st_mtime for path in RUNTIME_FILES)
    platform = state.get("platforms", {}).get("discord", {})
    ok = (
        pid > 0
        and process_start_epoch(pid) >= package_mtime
        and state.get("gateway_state") == "running"
        and platform.get("state") == "connected"
        and int(platform.get("writer_pid") or 0) == pid
    )
    return ok, state


def publish(results, pending):
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    payload = {"release": RELEASE, "targets": len(TARGETS), "results": results, "pending": list(pending.values())}
    temp = REPORT.with_suffix(".tmp")
    temp.write_text(json.dumps(payload, indent=2) + "\n")
    os.replace(temp, REPORT)


rows = [{"user": user, "uid": uid, "unit": unit, "home": home} for user, uid, unit, home in TARGETS]
LOCK.parent.mkdir(parents=True, exist_ok=True)
with LOCK.open("w") as lock:
    fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    results = []
    pending = {(row["user"], row["unit"]): row for row in rows}
    for key, row in list(pending.items()):
        ok, state = current(row)
        if ok:
            results.append({**row, "status": "already-current", "pid": int(state.get("pid") or 0), "verified": True})
            pending.pop(key)
    publish(results, pending)
    while pending and time.monotonic() < DEADLINE:
        progressed = False
        for key, row in list(pending.items()):
            before = gateway_state(row["home"])
            if before.get("active_agents") != 0:
                continue
            old_pid = int(before.get("pid") or 0)
            cp = call(["/usr/bin/python3", SAFE, "--user", row["user"], "--unit", row["unit"], "--hermes-home", row["home"], "--timeout", "1800"])
            try:
                payload = json.loads((cp.stdout.strip().splitlines() or ["{}"])[-1])
            except Exception:
                payload = {"status": "invalid-output", "returncode": cp.returncode}
            ok, after = current(row)
            new_pid = int(after.get("pid") or 0)
            if payload.get("status") == "reloaded" and ok and new_pid != old_pid:
                results.append({**row, **payload, "pid": new_pid, "gateway_state": after.get("gateway_state"), "verified": True})
                pending.pop(key)
                progressed = True
            elif payload.get("status") not in {"busy", "already-in-progress"}:
                results.append({**row, **payload, "pid": new_pid, "verified": False})
                pending.pop(key)
                progressed = True
            publish(results, pending)
        if pending:
            time.sleep(10 if progressed else 30)
    for row in pending.values():
        results.append({**row, "status": "timeout", "active_agents": gateway_state(row["home"]).get("active_agents"), "verified": False})
    publish(results, {})
    failed = [row for row in results if not row.get("verified")]
    print(json.dumps({"release": RELEASE, "targets": len(TARGETS), "verified": len(results) - len(failed), "failed": failed}))
    raise SystemExit(1 if failed else 0)
