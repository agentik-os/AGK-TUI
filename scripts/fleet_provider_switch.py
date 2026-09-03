#!/usr/bin/env python3
"""Fleet provider / inference-mode switch for AGK Hermes faces.

Modes
-----
Legacy (auth+model sync — still available):
  sudo python3 .../fleet_provider_switch.py --provider nous --model 'upstage/solar-pro4:free'

Inference dual-mode via ROUTING SNAPSHOT only (preferred for /free /pro):
  sudo python3 .../fleet_provider_switch.py free [--apply-reload]
  sudo python3 .../fleet_provider_switch.py pro  [--apply-reload]
  sudo python3 .../fleet_provider_switch.py status

Rules
-----
- FREE/PRO never wipe OAuth / credential pools in auth.json.
- FREE only rewrites routing fields in config.yaml (+ PAID_MODELS_ALLOWED for cheap DeepSeek).
- FREE primary = DeepSeek V4 Flash cheap; :free slug unavailable 2026-09-03 (404).
- free ≠ unlimited (~50 req/day when OpenRouter :free exists).
- Dentistry CLIENT (clientdentistrygptee881c) EXCLUDED from /free by default.
- MoonBase client DISABLED — never started; excluded from /free.
- Nutrition gateways NEVER touched (operator + private nutrition-os).
- Prefer config swap + next-session pickup; soft-reload only when idle/safe.
- No Discord posts from this tool.
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
import pwd
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
import ssl
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover
    subprocess.check_call([sys.executable, "-m", "pip", "install", "--user", "pyyaml", "-q"])
    import yaml

DEFAULT_SRC = Path("/home/agentik/.hermes/auth.json")
OPS_DST_CANDIDATES = [
    Path("/usr/local/lib/agk-terminal/scripts/fleet_provider_switch.py"),
    Path("/home/operator/.hermes/ops/fleet_provider_switch.py"),
    Path("/home/mission/.hermes/ops/fleet_provider_switch.py"),
]
STATE_DIR = Path("/var/lib/agk-terminal/fleet-inference-mode")
MODE_PATH = STATE_DIR / "mode.json"
SNAPSHOT_DIR = STATE_DIR / "routing-snapshots"
# Preferred human path (symlink/mirror of SNAPSHOT_DIR)
OPS_SNAPSHOT_DIR = Path("/home/operator/.hermes/ops/inference-mode-snapshots")
SAFE_RELOAD = Path("/usr/local/lib/agk-terminal/scripts/station_safe_gateway_reload.py")

# OmniRoute FREE chain (Gareth Watch 2026-09-03) — DeepSeek via OpenRouter.
# Live probe: deepseek/deepseek-v4-flash:free -> HTTP 404
#   "This model is unavailable for free. The paid version is available now"
# FREE mode therefore uses ultra-cheap paid Flash as primary.
# free ≠ unlimited (~50 req/day when OpenRouter :free exists).
# OpenRouter FREE chain — true $0 (Gareth GO 13:31). DeepSeek flash is PRO fallback, not FREE.
FREE_PRIMARY = "nvidia/nemotron-3.5-lightning:free"
FREE_CHEAP = "minimax/minimax-m2.7:free"
FREE_HARD = "dots-studio/dots-3-note-preview:free"
FREE_FALLBACKS = [
    {"provider": "openrouter", "model": "minimax/minimax-m2.7:free"},
    {"provider": "openrouter", "model": "dots-studio/dots-3-note-preview:free"},
    {"provider": "openrouter", "model": "openrouter/free"},
]

FREE_NOTE = (
    "deepseek/deepseek-v4-flash:free unavailable (404); using paid cheap flash primary; "
    "fallbacks flash-0731 then v4-pro. free≠unlimited."
)

EXCLUDED_PROFILE_NAMES = {
    "clientdentistrygptee881c",
    "nutrition-os",
    "nutrition",
    "clientmoonbasecapital4cda09",  # disabled — leave alone
}
EXCLUDED_UNIT_SUBSTRINGS = (
    "nutrition",
    "clientdentistrygptee881c",
    "clientmoonbasecapital4cda09",
)
DO_NOT_START_SUBSTRINGS = (
    "nutrition",
    "clientmoonbasecapital4cda09",
)

PRO_DEFAULT_MODEL = {
    "provider": "anthropic",
    "default": "claude-opus-5",
    "model": "claude-opus-5",
    "persist_switch_by_default": True,
}
# OmniRoute PRO: Claude primary (Dentistry/Claude Max safe); DeepSeek does bulk;
# Codex kept for QA/review/complex fallback.
PRO_DEFAULT_FALLBACKS = [
    {"provider": "openrouter", "model": "deepseek/deepseek-v4-flash"},
    {"provider": "openrouter", "model": "deepseek/deepseek-v4-pro"},
    {"provider": "openai-codex", "model": "gpt-5.6-sol"},
]


def ts() -> str:
    return datetime.datetime.now(datetime.UTC).strftime("%Y%m%dT%H%M%SZ")


def chown_path(path: Path, user: str) -> None:
    u = pwd.getpwnam(user)
    os.chown(path, u.pw_uid, u.pw_gid)
    if path.is_dir():
        return
    # keep group as user primary


def fp_obj(obj) -> str:
    raw = json.dumps(obj, sort_keys=True, default=str).encode()
    return hashlib.sha256(raw).hexdigest()[:12]


def fp_entry(e: dict) -> str:
    keys = (
        "access_token",
        "refresh_token",
        "api_key",
        "token",
        "agent_key",
        "device_code",
        "label",
    )
    return fp_obj({k: e.get(k) for k in keys})


def run(cmd, timeout=120):
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def stop_units(user: str, units: list[str]) -> None:
    for unit in units:
        cmd = (
            "export XDG_RUNTIME_DIR=/run/user/$(id -u); "
            f"systemctl --user kill -s SIGKILL {unit} 2>/dev/null || true; "
            f"systemctl --user reset-failed {unit} 2>/dev/null || true; "
            f"systemctl --user stop {unit} 2>/dev/null || true; "
            f"systemctl --user is-active {unit} || true"
        )
        r = run(["sudo", "-u", user, "bash", "-lc", cmd], timeout=60)
        print(f"STOP {user} {unit} -> {(r.stdout or '').strip()}")


def start_units(user: str, units: list[str]) -> None:
    for unit in units:
        cmd = (
            "export XDG_RUNTIME_DIR=/run/user/$(id -u); "
            f"systemctl --user reset-failed {unit} 2>/dev/null || true; "
            f"systemctl --user start {unit}; sleep 2; "
            f"systemctl --user is-active {unit}"
        )
        r = run(["sudo", "-u", user, "bash", "-lc", cmd], timeout=90)
        print(f"START {user} {unit} -> {(r.stdout or '').strip()} {(r.stderr or '')[:120]}")


def face_auth_targets():
    """Legacy targets for --provider auth sync (includes clients)."""
    out = [
        ("operator", Path("/home/operator/.hermes"), "operator"),
        ("agentik", Path("/home/agentik/.hermes"), "agentik"),
        ("mission", Path("/home/mission/.hermes"), "mission"),
    ]
    for p in sorted(Path("/home/mission/.hermes/profiles").glob("client*")):
        if (p / "auth.json").exists():
            out.append((p.name, p, "mission"))
    return out


def probe_anthropic_and_mark(auth: dict) -> None:
    pool = (auth.get("credential_pool") or {}).get("anthropic") or []
    ctx = ssl.create_default_context()
    now = datetime.datetime.now(datetime.UTC).isoformat().replace("+00:00", "Z")
    for e in pool:
        tok = e.get("access_token") or ""
        label = e.get("label") or e.get("id") or "?"
        if not tok:
            e["last_status"] = "missing"
            e["last_error_message"] = "no access_token"
            e["last_status_at"] = now
            continue
        req = urllib.request.Request(
            "https://api.anthropic.com/api/oauth/profile",
            headers={
                "Authorization": f"Bearer {tok}",
                "anthropic-beta": "oauth-2025-04-20",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=15, context=ctx) as r:
                if r.status == 200:
                    e["last_status"] = "ok"
                    e["last_error_message"] = None
                    e["last_error_code"] = None
                    e["last_status_at"] = now
                    print(f"  ANTHROPIC {label}: ok")
                _ = r.read(40)
        except urllib.error.HTTPError as ex:
            body = b""
            try:
                body = ex.read()[:300]
            except Exception:
                pass
            msg = body.decode("utf-8", "replace")
            if ex.code == 401 or "revoked" in msg.lower():
                e["last_status"] = "revoked"
                e["last_error_code"] = 401
                e["last_error_message"] = "OAuth access token has been revoked (live probe)"
                e["last_error_reason"] = "revoked"
                e["last_status_at"] = now
                print(f"  ANTHROPIC {label}: REVOKED")
            elif ex.code == 429:
                e["last_status"] = "rate_limited"
                e["last_error_code"] = 429
                e["last_error_message"] = "rate_limit (live probe — still usable)"
                e["last_status_at"] = now
                print(f"  ANTHROPIC {label}: 429")
            else:
                e["last_status"] = f"http_{ex.code}"
                e["last_error_code"] = ex.code
                e["last_error_message"] = msg[:200]
                e["last_status_at"] = now
                print(f"  ANTHROPIC {label}: HTTP {ex.code}")
        except Exception as ex:
            e["last_status"] = "probe_error"
            e["last_error_message"] = str(ex)[:200]
            e["last_status_at"] = now
            print(f"  ANTHROPIC {label}: ERR {ex}")


def hermes_config_set(user: str, hermes_home: Path, key: str, value: str) -> None:
    cmd = (
        f"export HERMES_HOME={hermes_home}; "
        f"hermes config set {key} {json.dumps(value)}"
    )
    r = run(["sudo", "-u", user, "-H", "bash", "-lc", cmd], timeout=60)
    print(
        f"CONFIG_SET {user} {hermes_home.name} {key}={value} "
        f"rc={r.returncode} {(r.stdout or '')[:80]} {(r.stderr or '')[:120]}"
    )


def ensure_openrouter_env(profile: Path, owner: str, src_env: Path) -> None:
    if not src_env.exists():
        return
    lines = src_env.read_text().splitlines()
    want = [ln for ln in lines if ln.startswith("OPENROUTER_")]
    if not want:
        return
    dst = profile / ".env"
    existing = dst.read_text() if dst.exists() else ""
    if "OPENROUTER_API_KEY=" in existing:
        return
    with dst.open("a") as f:
        if existing and not existing.endswith("\n"):
            f.write("\n")
        f.write("\n".join(want) + "\n")
    chown_path(dst, owner)
    os.chmod(dst, 0o600)
    print(f"ENV_OPENROUTER appended -> {profile}")


def list_gateway_faces() -> list[dict]:
    """Discover running/installed hermes-gateway units with HERMES_HOME."""
    faces = []
    for user in ("operator", "agentik", "mission", "private"):
        try:
            uid = pwd.getpwnam(user).pw_uid
        except KeyError:
            continue
        cmd = (
            f"export XDG_RUNTIME_DIR=/run/user/{uid}; "
            "systemctl --user list-unit-files 'hermes-gateway*' --no-legend --no-pager"
        )
        r = run(["sudo", "-u", user, "bash", "-lc", cmd], timeout=60)
        units = []
        for line in (r.stdout or "").splitlines():
            parts = line.split()
            if not parts:
                continue
            unit = parts[0]
            if not unit.startswith("hermes-gateway") or not unit.endswith(".service"):
                continue
            units.append(unit)
        for unit in sorted(set(units)):
            show = run(
                [
                    "sudo",
                    "-u",
                    user,
                    "bash",
                    "-lc",
                    f"export XDG_RUNTIME_DIR=/run/user/{uid}; "
                    f"systemctl --user show {unit} -p Environment -p ActiveState -p FragmentPath",
                ],
                timeout=30,
            )
            env = {}
            active = ""
            for line in (show.stdout or "").splitlines():
                if line.startswith("Environment="):
                    # Environment=A=B C=D ...
                    raw = line[len("Environment=") :]
                    for tok in re.findall(r'(?:[^\s"]|"(?:\\.|[^"])*")+', raw):
                        if "=" in tok:
                            k, v = tok.split("=", 1)
                            env[k] = v.strip('"')
                elif line.startswith("ActiveState="):
                    active = line.split("=", 1)[1]
            home = env.get("HERMES_HOME") or ""
            if not home:
                # try EnvironmentFiles / drop-ins via cat
                cat = run(
                    [
                        "sudo",
                        "-u",
                        user,
                        "bash",
                        "-lc",
                        f"export XDG_RUNTIME_DIR=/run/user/{uid}; systemctl --user cat {unit}",
                    ],
                    timeout=30,
                )
                m = re.search(r'HERMES_HOME=([^\n"\']+)', cat.stdout or "")
                if m:
                    home = m.group(1).strip()
            if not home:
                continue
            profile = Path(home).name if "/profiles/" in home else "main"
            faces.append(
                {
                    "user": user,
                    "unit": unit,
                    "home": Path(home),
                    "profile": profile,
                    "active": active,
                }
            )
    return faces


def is_excluded(face: dict, *, for_free: bool) -> tuple[bool, str]:
    profile = face["profile"]
    unit = face["unit"]
    home = str(face["home"])
    if "nutrition" in profile or "nutrition" in unit or "nutrition" in home:
        return True, "nutrition_never"
    if profile == "clientmoonbasecapital4cda09" or "clientmoonbasecapital4cda09" in unit:
        return True, "moonbase_disabled"
    if any(s in unit for s in EXCLUDED_UNIT_SUBSTRINGS) or any(
        s in home for s in EXCLUDED_UNIT_SUBSTRINGS
    ):
        return True, "excluded_unit"
    if profile in EXCLUDED_PROFILE_NAMES:
        return True, "excluded_profile"
    if for_free and profile == "clientdentistrygptee881c":
        return True, "dentistry_excluded_from_free"
    return False, ""


def routing_snapshot_from_config(cfg: dict) -> dict:
    model = dict(cfg.get("model") or {})
    # keep only routing-relevant model keys
    keep = {
        k: model[k]
        for k in (
            "provider",
            "default",
            "model",
            "base_url",
            "persist_switch_by_default",
            "api_mode",
        )
        if k in model
    }
    return {
        "model": keep,
        "fallback_providers": cfg.get("fallback_providers"),
        "auxiliary_free_only": ((cfg.get("auxiliary") or {}) if isinstance(cfg.get("auxiliary"), dict) else {}).get(
            "free_only"
        ),
    }


def write_yaml(path: Path, data: dict, owner: str) -> None:
    text = yaml.safe_dump(data, sort_keys=False, default_flow_style=False, allow_unicode=True)
    path.write_text(text)
    chown_path(path, owner)
    os.chmod(path, 0o600)


def backup_file(path: Path, stamp: str) -> Path | None:
    if not path.exists():
        return None
    bak = path.with_suffix(path.suffix + f".bak-infermode-{stamp}")
    shutil.copy2(path, bak)
    return bak


def set_env_kv(env_path: Path, key: str, value: str, owner: str) -> None:
    lines = env_path.read_text().splitlines() if env_path.exists() else []
    out = []
    found = False
    for ln in lines:
        if ln.startswith(f"{key}=") or ln.startswith(f"export {key}="):
            out.append(f"{key}={value}")
            found = True
        else:
            out.append(ln)
    if not found:
        if out and out[-1].strip() != "":
            out.append("")
        out.append(f"{key}={value}")
    env_path.parent.mkdir(parents=True, exist_ok=True)
    env_path.write_text("\n".join(out) + "\n")
    chown_path(env_path, owner)
    os.chmod(env_path, 0o600)


def soft_clear_openrouter_exhausted(auth_path: Path, owner: str, stamp: str) -> None:
    """Clear exhausted *status* on openrouter pool entries without touching secrets."""
    if not auth_path.exists():
        return
    try:
        data = json.loads(auth_path.read_text())
    except Exception as ex:
        print(f"AUTH_SKIP {auth_path}: {ex}")
        return
    pool = (data.get("credential_pool") or {}).get("openrouter") or []
    changed = False
    for e in pool:
        if e.get("last_status") == "exhausted":
            e["last_status"] = "ok"
            e["last_error_code"] = None
            e["last_error_message"] = None
            e["last_error_reason"] = None
            e["last_status_at"] = datetime.datetime.now(datetime.UTC).timestamp()
            changed = True
    if not changed:
        return
    backup_file(auth_path, stamp)
    # credentials untouched — only status fields rewritten
    auth_path.write_text(json.dumps(data, indent=2) + "\n")
    chown_path(auth_path, owner)
    os.chmod(auth_path, 0o600)
    print(f"OPENROUTER_STATUS cleared exhausted -> ok ({auth_path})")


def apply_free_routing(cfg: dict) -> dict:
    cfg = json.loads(json.dumps(cfg))  # deep copy via json
    model = dict(cfg.get("model") or {})
    model["provider"] = "openrouter"
    model["default"] = FREE_PRIMARY
    model["model"] = FREE_PRIMARY
    model["persist_switch_by_default"] = True
    cfg["model"] = model
    cfg["fallback_providers"] = list(FREE_FALLBACKS)
    aux = dict(cfg.get("auxiliary") or {}) if isinstance(cfg.get("auxiliary"), dict) else {}
    # free_only False: FREE OmniRoute uses paid-cheap DeepSeek flash/pro fallbacks
    aux["free_only"] = False
    aux["inference_mode"] = "free"
    aux["inference_mode_note"] = FREE_NOTE
    cfg["auxiliary"] = aux
    return cfg


def restore_routing(cfg: dict, snap: dict) -> dict:
    cfg = json.loads(json.dumps(cfg))
    if snap.get("model"):
        model = dict(cfg.get("model") or {})
        model.update(snap["model"])
        cfg["model"] = model
    if "fallback_providers" in snap:
        cfg["fallback_providers"] = snap["fallback_providers"]
    if "auxiliary_free_only" in snap:
        aux = dict(cfg.get("auxiliary") or {}) if isinstance(cfg.get("auxiliary"), dict) else {}
        if snap["auxiliary_free_only"] is None:
            aux.pop("free_only", None)
        else:
            aux["free_only"] = bool(snap["auxiliary_free_only"])
        if aux:
            cfg["auxiliary"] = aux
        else:
            cfg.pop("auxiliary", None)
    if snap.get("auxiliary_free_only") in (None, False):
        aux = dict(cfg.get("auxiliary") or {}) if isinstance(cfg.get("auxiliary"), dict) else {}
        if "free_only" in aux:
            aux.pop("free_only", None)
            if aux:
                cfg["auxiliary"] = aux
            else:
                cfg.pop("auxiliary", None)
    return cfg


def ensure_state_dirs() -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    os.chmod(STATE_DIR, 0o755)
    try:
        OPS_SNAPSHOT_DIR.parent.mkdir(parents=True, exist_ok=True)
        if not OPS_SNAPSHOT_DIR.exists():
            OPS_SNAPSHOT_DIR.symlink_to(SNAPSHOT_DIR, target_is_directory=True)
        chown_path(OPS_SNAPSHOT_DIR.parent, "operator")
    except Exception as ex:
        print(f"OPS_SNAPSHOT_LINK_SKIP: {ex}")


def save_mode(mode: str, faces: list[str], extra: dict | None = None) -> None:
    ensure_state_dirs()
    payload = {
        "mode": mode,
        "updated_at": datetime.datetime.now(datetime.UTC).isoformat().replace("+00:00", "Z"),
        "faces": faces,
        **(extra or {}),
    }
    MODE_PATH.write_text(json.dumps(payload, indent=2) + "\n")


def load_mode() -> dict:
    if not MODE_PATH.exists():
        return {"mode": "unknown"}
    try:
        return json.loads(MODE_PATH.read_text())
    except Exception:
        return {"mode": "unknown"}


def snapshot_path_for(face: dict) -> Path:
    key = f"{face['user']}__{face['profile']}__{face['unit']}".replace("/", "_")
    return SNAPSHOT_DIR / f"{key}.json"


def safe_reload_face(face: dict) -> dict:
    if not SAFE_RELOAD.exists():
        return {"status": "no-safe-reload-script"}
    # Never nutrition / dentistry
    excl, reason = is_excluded(face, for_free=True)
    if excl and "nutrition" in reason:
        return {"status": "skipped", "reason": reason}
    r = run(
        [
            "sudo",
            "python3",
            str(SAFE_RELOAD),
            "--user",
            face["user"],
            "--unit",
            face["unit"],
            "--hermes-home",
            str(face["home"]),
            "--timeout",
            "120",
        ],
        timeout=180,
    )
    out = (r.stdout or "").strip()
    try:
        return json.loads(out.splitlines()[-1]) if out else {"status": "empty", "rc": r.returncode}
    except Exception:
        return {"status": "raw", "rc": r.returncode, "out": out[:300], "err": (r.stderr or "")[:200]}


def hard_bounce_face(face: dict) -> None:
    """SIGKILL+start for a single face entering FREE/PRO when necessary."""
    unit = face["unit"]
    home = str(face["home"])
    if any(s in unit or s in home for s in DO_NOT_START_SUBSTRINGS):
        print(f"BOUNCE_REFUSED do-not-start {unit}")
        return
    excl, reason = is_excluded(face, for_free=False)
    if "nutrition" in reason:
        print(f"BOUNCE_REFUSED nutrition {unit}")
        return
    stop_units(face["user"], [face["unit"]])
    start_units(face["user"], [face["unit"]])


def cmd_status() -> int:
    mode = load_mode()
    print("MODE", json.dumps(mode, indent=2))
    faces = list_gateway_faces()
    print(f"FACES_DISCOVERED {len(faces)}")
    for f in faces:
        excl, reason = is_excluded(f, for_free=True)
        cfg_path = f["home"] / "config.yaml"
        provider = default = "?"
        if cfg_path.exists():
            try:
                cfg = yaml.safe_load(cfg_path.read_text()) or {}
                m = cfg.get("model") or {}
                provider = m.get("provider")
                default = m.get("default") or m.get("model")
            except Exception as ex:
                provider = f"err:{ex}"
        flag = "EXCL" if excl else "INCL"
        print(
            f"  [{flag}] {f['user']} {f['profile']} {f['unit']} active={f['active']} "
            f"provider={provider} model={default} home={f['home']}"
            + (f" reason={reason}" if excl else "")
        )
    # openrouter key evidence
    for envp in (
        Path("/home/operator/.hermes/.env"),
        Path("/home/agentik/.hermes/.env"),
        Path("/home/mission/.hermes/.env"),
        Path("/home/private/.hermes/.env"),
    ):
        if not envp.exists():
            continue
        txt = envp.read_text()
        m = re.search(r"^OPENROUTER_API_KEY=(.*)$", txt, re.M)
        if m:
            print(f"KEY {envp} present len={len(m.group(1).strip().strip(chr(34)).strip(chr(39)))}")
        paid = re.search(r"^PAID_MODELS_ALLOWED=(.*)$", txt, re.M)
        if paid:
            print(f"PAID_MODELS_ALLOWED {envp}={paid.group(1)}")
    return 0


def dedupe_faces_by_home(faces: list[dict]) -> list[dict]:
    """One routing write per HERMES_HOME (multiple units may share a profile)."""
    seen = set()
    out = []
    for face in faces:
        key = (face["user"], str(face["home"]))
        if key in seen:
            continue
        seen.add(key)
        out.append(face)
    return out


def cmd_free(apply_reload: bool, force_bounce: bool, include_dentistry: bool) -> int:
    ensure_state_dirs()
    stamp = ts()
    faces = dedupe_faces_by_home(list_gateway_faces())
    changed = []
    skipped = []
    for face in faces:
        excl, reason = is_excluded(face, for_free=not include_dentistry)
        if excl:
            skipped.append((face, reason))
            continue
        home: Path = face["home"]
        cfg_path = home / "config.yaml"
        if not cfg_path.exists():
            skipped.append((face, "no_config"))
            continue
        owner = face["user"]
        snap_path = snapshot_path_for(face)
        cfg = yaml.safe_load(cfg_path.read_text()) or {}
        # save PRO routing snapshot once (or refresh if currently looks like PRO)
        snap = routing_snapshot_from_config(cfg)
        cur_default = str((snap.get("model") or {}).get("default") or "")
        cur_provider = (snap.get("model") or {}).get("provider")
        looks_free = (
            cur_provider == "openrouter"
            and (
                cur_default.endswith(":free")
                or cur_default.startswith("deepseek/deepseek-v4-flash")
                or cur_default in {FREE_PRIMARY, FREE_CHEAP, FREE_HARD}
                or "nemotron" in cur_default
                or "minimax" in cur_default
            )
        )
        if not looks_free and (
            not snap_path.exists()
            or cur_provider in {"anthropic", "openai-codex", "auto"}
        ):
            snap_path.write_text(json.dumps(snap, indent=2) + "\n")
            print(f"SNAPSHOT_SAVED {face['user']}/{face['profile']} -> {snap_path.name}")
        backup_file(cfg_path, stamp)
        new_cfg = apply_free_routing(cfg)
        write_yaml(cfg_path, new_cfg, owner)
        # .env PAID_MODELS_ALLOWED=false + ensure OPENROUTER key present
        env_path = home / ".env"
        backup_file(env_path, stamp)
        # inherit root key if needed
        root_env = Path(f"/home/{owner}/.hermes/.env")
        ensure_openrouter_env(home, owner, root_env)
        set_env_kv(env_path if env_path.exists() or True else root_env, "PAID_MODELS_ALLOWED", "false", owner)
        # also stamp owner root .env when face is profile
        if root_env.exists() and home != Path(f"/home/{owner}/.hermes"):
            # do not force root into free globally — only profile .env
            pass
        # soft-clear openrouter exhausted status (credentials untouched)
        soft_clear_openrouter_exhausted(home / "auth.json", owner, stamp)
        changed.append(face)
        print(
            f"FREE {face['user']}/{face['profile']} {face['unit']} "
            f"-> openrouter/{FREE_PRIMARY}"
        )

    # owner-root .env flag for operator convenience (does not touch nutrition configs)
    for user in ("operator", "agentik", "mission", "private"):
        root = Path(f"/home/{user}/.hermes/.env")
        if root.exists():
            backup_file(root, stamp)
            set_env_kv(root, "PAID_MODELS_ALLOWED", "false", user)
            print(f"ENV PAID_MODELS_ALLOWED=false -> {root} (FREE true $0 chain)")

    save_mode(
        "free",
        [f"{f['user']}/{f['profile']}/{f['unit']}" for f in changed],
        {
            "primary": FREE_PRIMARY,
            "fallbacks": FREE_FALLBACKS,
            "note": FREE_NOTE,
            "skipped": [f"{f['user']}/{f['profile']}:{reason}" for f, reason in skipped],
            "stamp": stamp,
        },
    )

    if apply_reload or force_bounce:
        homes = {(f["user"], str(f["home"])) for f in changed}
        for face in list_gateway_faces():
            if (face["user"], str(face["home"])) not in homes:
                continue
            if force_bounce:
                hard_bounce_face(face)
            else:
                result = safe_reload_face(face)
                print(f"RELOAD {face['unit']} -> {result}")
                if result.get("status") in {"busy", "already-in-progress"} and force_bounce:
                    hard_bounce_face(face)
    else:
        print("APPLY deferred: config swapped; gateways pick up on next session/restart (no reload)")

    print(f"DONE free changed={len(changed)} skipped={len(skipped)}")
    for face, reason in skipped:
        print(f"  SKIP {face['user']}/{face['profile']} {face['unit']} ({reason})")
    return 0


def cmd_pro(apply_reload: bool, force_bounce: bool) -> int:
    ensure_state_dirs()
    stamp = ts()
    faces = dedupe_faces_by_home(list_gateway_faces())
    changed = []
    skipped = []
    for face in faces:
        # nutrition never touched even on /pro restore
        excl, reason = is_excluded(face, for_free=False)
        if "nutrition" in reason:
            skipped.append((face, reason))
            continue
        # dentistry excluded from free — leave alone on pro unless snapshot exists
        home: Path = face["home"]
        cfg_path = home / "config.yaml"
        snap_path = snapshot_path_for(face)
        if not cfg_path.exists():
            skipped.append((face, "no_config"))
            continue
        owner = face["user"]
        cfg = yaml.safe_load(cfg_path.read_text()) or {}
        if snap_path.exists():
            snap = json.loads(snap_path.read_text())
        else:
            # synthesize PRO default if we never snapshotted
            snap = {
                "model": dict(PRO_DEFAULT_MODEL),
                "fallback_providers": list(PRO_DEFAULT_FALLBACKS),
                "auxiliary_free_only": False,
            }
            print(f"SNAPSHOT_MISSING using PRO defaults for {face['user']}/{face['profile']}")
        backup_file(cfg_path, stamp)
        new_cfg = restore_routing(cfg, snap)
        write_yaml(cfg_path, new_cfg, owner)
        env_path = home / ".env"
        if env_path.exists() or True:
            backup_file(env_path, stamp)
            set_env_kv(env_path, "PAID_MODELS_ALLOWED", "false", owner)
        changed.append(face)
        m = (new_cfg.get("model") or {})
        print(
            f"PRO {face['user']}/{face['profile']} {face['unit']} "
            f"-> {m.get('provider')}/{m.get('default') or m.get('model')}"
        )

    for user in ("operator", "agentik", "mission", "private"):
        root = Path(f"/home/{user}/.hermes/.env")
        if root.exists():
            backup_file(root, stamp)
            set_env_kv(root, "PAID_MODELS_ALLOWED", "false", user)

    save_mode(
        "pro",
        [f"{f['user']}/{f['profile']}/{f['unit']}" for f in changed],
        {
            "skipped": [f"{f['user']}/{f['profile']}:{reason}" for f, reason in skipped],
            "stamp": stamp,
        },
    )

    if apply_reload or force_bounce:
        homes = {(f["user"], str(f["home"])) for f in changed}
        for face in list_gateway_faces():
            if (face["user"], str(face["home"])) not in homes:
                continue
            if force_bounce:
                hard_bounce_face(face)
            else:
                result = safe_reload_face(face)
                print(f"RELOAD {face['unit']} -> {result}")
    else:
        print("APPLY deferred: config restored; gateways pick up on next session/restart (no reload)")

    print(f"DONE pro changed={len(changed)} skipped={len(skipped)}")
    return 0


def persist_self() -> None:
    src = Path(sys.argv[0]).resolve()
    for dst in OPS_DST_CANDIDATES:
        try:
            dst.parent.mkdir(parents=True, exist_ok=True)
            if dst.resolve() != src.resolve():
                shutil.copy2(src, dst)
            os.chmod(dst, 0o755)
            # ownership: scripts dir root; ops dirs by face user if possible
            if "operator" in str(dst):
                chown_path(dst, "operator")
            elif "mission" in str(dst):
                chown_path(dst, "mission")
            print("OPS_PERSISTED", dst)
        except PermissionError as ex:
            print(f"OPS_PERSIST_SKIP {dst}: {ex}")
        except Exception as ex:
            print(f"OPS_PERSIST_ERR {dst}: {ex}")


def install_wrappers() -> None:
    """Install /usr/local/bin/agk-free and agk-pro convenience wrappers."""
    body_free = """#!/usr/bin/env bash
set -euo pipefail
exec sudo -n python3 /usr/local/lib/agk-terminal/scripts/fleet_provider_switch.py free "$@"
"""
    body_pro = """#!/usr/bin/env bash
set -euo pipefail
exec sudo -n python3 /usr/local/lib/agk-terminal/scripts/fleet_provider_switch.py pro "$@"
"""
    body_status = """#!/usr/bin/env bash
set -euo pipefail
exec sudo -n python3 /usr/local/lib/agk-terminal/scripts/fleet_provider_switch.py status "$@"
"""
    for name, body in (
        ("agk-free", body_free),
        ("agk-pro", body_pro),
        ("agk-inference-mode", body_status),
    ):
        path = Path("/usr/local/bin") / name
        try:
            path.write_text(body)
            os.chmod(path, 0o755)
            print("WRAPPER", path)
        except Exception as ex:
            print(f"WRAPPER_SKIP {path}: {ex}")


def legacy_provider_main(args) -> int:
    src_root = Path(args.source).parent
    src_auth = json.loads(Path(args.source).read_text())
    pool = list((src_auth.get("credential_pool") or {}).get(args.provider) or [])
    if not pool:
        print("NO_POOL", file=sys.stderr)
        return 2
    print(
        f"SOURCE provider={args.provider} n={len(pool)} "
        f"label={pool[0].get('label')} fp={fp_entry(pool[0])} model={args.model}"
    )

    op_units = ["hermes-gateway.service"]
    mi_units = [
        "hermes-gateway.service",
        "hermes-gateway-clientdentistrygptee881c.service",
        "hermes-gateway-clientloumna7b2934.service",
        "hermes-gateway-clientmoonbasecapital4cda09.service",
    ]
    ag_units = ["hermes-gateway.service"]

    stop_units("operator", op_units)
    stop_units("mission", mi_units)
    stop_units("agentik", ag_units)

    stamp = ts()
    shared_src = src_root / "shared" / "nous_auth.json"
    fps = set()

    for name, root, owner in face_auth_targets():
        auth_path = root / "auth.json"
        if not auth_path.exists():
            print("SKIP", name)
            continue
        shutil.copy2(auth_path, auth_path.with_suffix(auth_path.suffix + f".bak-fleetswitch-{stamp}"))
        d = json.loads(auth_path.read_text())
        d.setdefault("credential_pool", {})[args.provider] = json.loads(json.dumps(pool))
        d["active_provider"] = args.provider
        d["updated_at"] = datetime.datetime.now(datetime.UTC).isoformat().replace("+00:00", "Z")
        if args.probe_anthropic:
            print(f"## probe anthropic {name}")
            probe_anthropic_and_mark(d)
        auth_path.write_text(json.dumps(d, indent=2) + "\n")
        chown_path(auth_path, owner)
        os.chmod(auth_path, 0o600)
        fps.add(fp_entry(pool[0]))
        print(f"WROTE auth {name} active={args.provider} fp={fp_entry(pool[0])}")

        if args.provider == "nous" and shared_src.exists():
            shared_dst = root / "shared" / "nous_auth.json"
            shared_dst.parent.mkdir(parents=True, exist_ok=True)
            if shared_dst.exists():
                shutil.copy2(shared_dst, shared_dst.with_suffix(shared_dst.suffix + f".bak-{stamp}"))
            shutil.copy2(shared_src, shared_dst)
            chown_path(shared_dst, owner)
            os.chmod(shared_dst, 0o600)
            print(f"WROTE shared_nous {name} fp={fp_obj(json.loads(shared_dst.read_text()))}")

        hermes_config_set(owner, root, "model.provider", args.provider)
        hermes_config_set(owner, root, "model.default", args.model)
        hermes_config_set(owner, root, "model.persist_switch_by_default", "true")

        if name.startswith("client"):
            ensure_openrouter_env(root, owner, Path("/home/mission/.hermes/.env"))

    print("FINGERPRINTS", sorted(fps))

    if args.restart:
        start_units("operator", op_units)
        start_units("mission", mi_units)
        start_units("agentik", ag_units)

    if not args.no_persist:
        persist_self()

    for name, root, owner in face_auth_targets():
        cfg = root / "config.yaml"
        if not cfg.exists():
            continue
        txt = cfg.read_text()
        ok_p = f"provider: {args.provider}" in txt
        ok_m = args.model in txt
        print(f"VERIFY {name} provider_ok={ok_p} model_ok={ok_m}")

    print("DONE")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd")

    p_free = sub.add_parser("free", help="OmniRoute FREE: DeepSeek V4 Flash cheap (+pro fallback); free≠unlimited")
    p_free.add_argument("--apply-reload", action="store_true", help="Soft-reload idle gateways via station_safe_gateway_reload")
    p_free.add_argument("--force-bounce", action="store_true", help="SIGKILL+start faces (never nutrition)")
    p_free.add_argument("--include-dentistry", action="store_true", help="Include clientdentistrygptee881c (default: excluded)")

    p_pro = sub.add_parser("pro", help="Restore saved PRO routing snapshots")
    p_pro.add_argument("--apply-reload", action="store_true")
    p_pro.add_argument("--force-bounce", action="store_true")

    sub.add_parser("status", help="Show inference mode + face routing")
    sub.add_parser("install", help="Persist script + install agk-free/agk-pro wrappers")

    # legacy flags (when no subcommand)
    ap.add_argument("--provider", default=None)
    ap.add_argument("--model", default="upstage/solar-pro4:free")
    ap.add_argument("--source", default=str(DEFAULT_SRC))
    ap.add_argument("--restart", action="store_true")
    ap.add_argument("--probe-anthropic", action="store_true")
    ap.add_argument("--no-persist", action="store_true")

    args = ap.parse_args()

    if args.cmd == "free":
        if not args.no_persist:
            persist_self()
            install_wrappers()
        return cmd_free(args.apply_reload, args.force_bounce, args.include_dentistry)
    if args.cmd == "pro":
        if not args.no_persist:
            persist_self()
            install_wrappers()
        return cmd_pro(args.apply_reload, args.force_bounce)
    if args.cmd == "status":
        return cmd_status()
    if args.cmd == "install":
        persist_self()
        install_wrappers()
        return 0
    if args.provider:
        return legacy_provider_main(args)

    ap.print_help()
    print("\nHint: use subcommands: free | pro | status | install", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
