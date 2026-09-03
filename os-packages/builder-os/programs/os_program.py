#!/usr/bin/env python3
"""Deterministic contract operations for builder-os (0.5.0, Hermes >= 0.21).

Actions (all print one JSON object; exit 0 = PASS, 1 = FAIL, 2 = BLOCKED):

  contract             SHA-256 of CONTRACT.json (identity readback)
  handoff-check        15 Librarian inputs + Builder fold-in present
  validate-onboarding  Validate research/ONBOARDING_LEDGER.json (<=20 sources,
                       <=20 approaches, complete merge matrix, provenance, and
                       the four owner gates plan/orchestration/programming/agentic)
  scaffold             Emit a contract-complete OS package skeleton for a new OS
  hermes-check         Read the live Hermes tree: version + feature matrix used
                       by this OS (delegate output_schema, kanban review lane,
                       /goal quality gates, built-in /plan, checkpoints, ...)

The model reasons; this program verifies. Nothing here calls a model, reads a
secret, or mutates anything outside --out.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

OS_ID = "builder-os"
VERSION = "0.5.0"
HERMES_MIN = "0.21.0"
MAX_SOURCES = 20
MAX_APPROACHES = 20
GATES = ("plan", "orchestration", "programming", "agentic")
FOLD_TARGETS = {"skills", "programs", "evals", "workflows", "doctor", "recovery", "automations",
                "agents", "contracts", "knowledge", "commands", "memory"}
SOURCE_KINDS = {"book", "video", "web", "paper", "standard", "documentation", "course", "podcast"}
ID_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
SRC_RE = re.compile(r"^SRC-[0-9]{2}$")
APR_RE = re.compile(r"^APR-[0-9]{2}$")

# Hermes 0.21 feature probes: feature -> (relative file, regex that must match)
HERMES_FEATURES = {
    "delegate_task.output_schema": ("tools/delegate_tool.py", r'"output_schema"'),
    "delegate_task.roles": ("tools/delegate_tool.py", r'"role"'),
    "delegate_task.failure_visibility": ("tools/delegate_tool.py", r"SUBAGENT_FAILURE_STATUSES"),
    "kanban.review_lane": ("hermes_cli/config_defaults.py", r'"review_dispatch"'),
    "kanban.request_review_tool": ("tools/kanban_tools.py", r"kanban_request_review"),
    "goal.quality_gates": ("hermes_cli/goals.py", r"class GoalGate"),
    "goal.completion_contract": ("hermes_cli/goals.py", r"class GoalContract"),
    "plan.builtin": ("agent/plan_prompt.py", r"def build_plan_prompt"),
    "checkpoints": ("tools/checkpoint_manager.py", r"CHECKPOINT_BASE"),
    "cron.doctor": ("hermes_cli/cron.py", r"doctor"),
    "approvals.unattended_mode": ("hermes_cli/config_defaults.py", r'"unattended_mode"'),
    "profile.distribution": ("hermes_cli/profile_distribution.py", r"class DistributionManifest"),
    "peer.async_runs": ("hermes_cli/subcommands/peer.py", r'"run"'),
    "sdlc_review_skill": ("skills/devops/sdlc-review/SKILL.md", r"name: sdlc-review"),
    "protected_instruction_files": ("tools/file_tools.py", r"_PROTECTED_INSTRUCTION_BASENAMES"),
    "session_side_question": ("agent/side_question.py", r"."),
}


def emit(payload: dict, code: int) -> int:
    print(json.dumps(payload, sort_keys=True))
    return code


def _read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


# ----------------------------------------------------------------- contract / handoff

def action_contract(root: Path) -> int:
    path = root / "CONTRACT.json"
    data = path.read_bytes()
    return emit({"os_id": OS_ID, "path": str(path), "sha256": hashlib.sha256(data).hexdigest()}, 0)


def action_handoff_check(root: Path) -> int:
    text = (root / "research/14_BUILDER_HANDOFF.md").read_text(encoding="utf-8")
    ids = re.findall(r"^### INPUT-(\d{2})\b", text, re.M)
    ok = ids == [f"{i:02d}" for i in range(1, 16)] and "FOLDED_BY_BUILDER_PROFILE: true" in text
    return emit({"os_id": OS_ID, "input_count": len(ids), "folded": "FOLDED_BY_BUILDER_PROFILE: true" in text}, 0 if ok else 1)


# ----------------------------------------------------------------- onboarding validation

def _schema_findings(doc: dict, schema_path: Path | None) -> tuple[bool, list[dict]]:
    """Validate the ledger against schemas/onboarding_ledger.schema.json when jsonschema is importable.

    Returns (applied, findings). Structural checks below stay authoritative even when the schema
    cannot be applied, so a missing optional dependency never weakens the referee.
    """
    if schema_path is None or not schema_path.is_file():
        return False, []
    try:
        import jsonschema  # type: ignore
    except ImportError:
        return False, []
    try:
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        validator = jsonschema.Draft202012Validator(schema)
    except Exception as exc:  # noqa: BLE001
        return False, [{"code": "SCHEMA_UNREADABLE", "error": type(exc).__name__}]
    out = []
    for err in sorted(validator.iter_errors(doc), key=lambda e: list(e.absolute_path)):
        out.append({"code": "SCHEMA_VIOLATION", "path": "/".join(str(p) for p in err.absolute_path) or "$",
                    "message": err.message[:200]})
    return True, out


def validate_ledger(doc: dict, schema_path: Path | None = None) -> dict:
    findings: list[dict] = []

    def f(code: str, **kw):
        findings.append({"code": code, **kw})

    schema_applied, schema_findings = _schema_findings(doc, schema_path) if isinstance(doc, dict) else (False, [])
    findings.extend(schema_findings)

    if not isinstance(doc, dict):
        f("LEDGER_NOT_OBJECT")
        return {"status": "FAIL", "findings": findings, "build_permitted": False}
    os_id = str(doc.get("os_id") or "")
    if not ID_RE.fullmatch(os_id):
        f("OS_ID_INVALID", os_id=os_id)
    if not str(doc.get("theme") or "").strip():
        f("THEME_MISSING")

    sources = doc.get("sources") if isinstance(doc.get("sources"), list) else []
    approaches = doc.get("approaches") if isinstance(doc.get("approaches"), list) else []
    merge = doc.get("merge_matrix") if isinstance(doc.get("merge_matrix"), list) else []
    gates = doc.get("validation_gates") if isinstance(doc.get("validation_gates"), dict) else {}

    if not sources:
        f("SOURCES_EMPTY")
    if len(sources) > MAX_SOURCES:
        f("SOURCES_GT_20", count=len(sources))
    seen_src: set[str] = set()
    for s in sources:
        sid = str(s.get("source_id") or "?") if isinstance(s, dict) else "?"
        if not isinstance(s, dict):
            f("SOURCE_NOT_OBJECT", source_id=sid)
            continue
        if not isinstance(s.get("source_id"), str) or not SRC_RE.fullmatch(s["source_id"]):
            f("SOURCE_ID_INVALID", source_id=sid)
        if sid in seen_src:
            f("SOURCE_DUPLICATE", source_id=sid)
        seen_src.add(sid)
        if s.get("kind") not in SOURCE_KINDS:
            f("SOURCE_KIND_INVALID", source_id=sid, kind=s.get("kind"))
        url = str(s.get("url") or "")
        if not url.startswith(("http://", "https://")):
            f("SOURCE_PROVENANCE_MISSING", source_id=sid)
        if not str(s.get("title") or "").strip():
            f("SOURCE_TITLE_MISSING", source_id=sid)
        if not str(s.get("why_canonical") or "").strip():
            f("SOURCE_WHY_CANONICAL_MISSING", source_id=sid)
        if not str(s.get("access_level") or "").strip():
            f("SOURCE_ACCESS_LEVEL_MISSING", source_id=sid)

    if not approaches:
        f("APPROACHES_EMPTY")
    if len(approaches) > MAX_APPROACHES:
        f("APPROACHES_GT_20", count=len(approaches))
    seen_apr: set[str] = set()
    for a in approaches:
        aid = str(a.get("approach_id") or "?") if isinstance(a, dict) else "?"
        if not isinstance(a, dict):
            f("APPROACH_NOT_OBJECT", approach_id=aid)
            continue
        if not isinstance(a.get("approach_id"), str) or not APR_RE.fullmatch(a["approach_id"]):
            f("APPROACH_ID_INVALID", approach_id=aid)
        if aid in seen_apr:
            f("APPROACH_DUPLICATE", approach_id=aid)
        seen_apr.add(aid)
        refs = a.get("source_ids") if isinstance(a.get("source_ids"), list) else []
        if not refs:
            f("APPROACH_WITHOUT_SOURCE", approach_id=aid)
        for r in refs:
            if r not in seen_src:
                f("APPROACH_SOURCE_UNKNOWN", approach_id=aid, source_id=r)
        for key in ("principle", "mechanism", "limitations"):
            if not str(a.get(key) or "").strip():
                f("APPROACH_FIELD_MISSING", approach_id=aid, field=key)
        if a.get("evidence_strength") not in {"strong", "moderate", "weak", "anecdotal"}:
            f("APPROACH_EVIDENCE_INVALID", approach_id=aid)

    merged_ids = set()
    for m in merge:
        if not isinstance(m, dict):
            f("MERGE_ROW_NOT_OBJECT")
            continue
        aid = str(m.get("approach_id") or "?")
        if not isinstance(m.get("approach_id"), str) or not APR_RE.fullmatch(m["approach_id"]):
            f("MERGE_APPROACH_ID_INVALID", approach_id=aid)
        if aid in merged_ids:
            f("MERGE_ROW_DUPLICATE", approach_id=aid)
        merged_ids.add(aid)
        if aid not in seen_apr:
            f("MERGE_UNKNOWN_APPROACH", approach_id=aid)
        if m.get("decision") not in {"adopt", "adapt", "merge", "reject", "defer"}:
            f("MERGE_DECISION_INVALID", approach_id=aid)
        folds = m.get("folds_into") if isinstance(m.get("folds_into"), list) else []
        if m.get("decision") in {"adopt", "adapt", "merge"} and not folds:
            f("MERGE_FOLD_TARGET_MISSING", approach_id=aid)
        for t in folds:
            if t not in FOLD_TARGETS:
                f("MERGE_FOLD_TARGET_INVALID", approach_id=aid, target=t)
        conflicts = m.get("conflicts_with") if isinstance(m.get("conflicts_with"), list) else []
        if conflicts and not str(m.get("resolution") or "").strip():
            f("MERGE_CONFLICT_UNRESOLVED", approach_id=aid)
    missing = sorted(seen_apr - merged_ids)
    if missing:
        f("MERGE_MATRIX_INCOMPLETE", missing=missing)

    validated = []
    for g in GATES:
        entry = gates.get(g) if isinstance(gates.get(g), dict) else None
        if entry is None:
            f("GATE_MISSING", gate=g)
            continue
        if entry.get("status") != "validated":
            f("GATE_NOT_VALIDATED", gate=g, status=entry.get("status"))
            continue
        if not str(entry.get("validated_by") or "").strip() or not str(entry.get("evidence") or "").strip():
            f("GATE_EVIDENCE_MISSING", gate=g)
            continue
        validated.append(g)

    status = "PASS" if not findings else "FAIL"
    return {
        "os_id": os_id, "status": status, "sources": len(sources), "approaches": len(approaches),
        "merge_rows": len(merge), "gates_validated": sorted(validated), "schema_applied": schema_applied,
        "build_permitted": status == "PASS" and len(validated) == len(GATES),
        "findings": findings,
    }


def action_validate_onboarding(ledger: Path, package_root: Path) -> int:
    try:
        doc = _read_json(ledger)
    except Exception as exc:  # noqa: BLE001
        return emit({"status": "BLOCKED", "reason": f"ledger unreadable: {type(exc).__name__}", "ledger": str(ledger)}, 2)
    result = validate_ledger(doc, package_root / "schemas" / "onboarding_ledger.schema.json")
    result["ledger"] = str(ledger)
    return emit(result, 0 if result["status"] == "PASS" else 1)


# ----------------------------------------------------------------- hermes check

def detect_hermes_root() -> Path:
    """Locate the Hermes tree that actually runs this profile, in priority order:
    1. $HERMES_AGENT_ROOT (explicit), 2. $VIRTUAL_ENV parent (a venv inside a Hermes checkout),
    3. the `hermes_cli` package importable by the current interpreter, 4. the ExecStart of the
    profile's systemd unit(s), 5. the /opt production checkout. The result is reported so evidence
    always names the tree that was inspected."""
    import os
    import subprocess
    cand: list[Path] = []
    if os.environ.get("HERMES_AGENT_ROOT"):
        cand.append(Path(os.environ["HERMES_AGENT_ROOT"]))
    if os.environ.get("VIRTUAL_ENV"):
        cand.append(Path(os.environ["VIRTUAL_ENV"]).parent)
    try:
        import importlib.util
        spec = importlib.util.find_spec("hermes_cli")
        if spec and spec.origin:
            cand.append(Path(spec.origin).resolve().parents[1])
    except Exception:  # noqa: BLE001
        pass
    for unit in ("hermes-gateway-builder-os-021canary.service", "hermes-gateway-builder-os.service"):
        try:
            out = subprocess.run(["systemctl", "--user", "show", unit, "-p", "ExecStart", "--no-pager"],
                                 capture_output=True, text=True, timeout=10).stdout
            m = re.search(r"path=(\S+)/\.?venv/bin/python", out)
            if m:
                cand.append(Path(m.group(1)))
        except Exception:  # noqa: BLE001
            pass
    cand.append(Path("/opt/agk-terminal/hermes-agent"))
    for c in cand:
        if (c / "pyproject.toml").is_file() and (c / "hermes_cli").is_dir():
            return c
    return cand[-1]


def _hermes_version(root: Path) -> str | None:
    py = root / "pyproject.toml"
    if not py.is_file():
        return None
    m = re.search(r'^version\s*=\s*"([^"]+)"', py.read_text(encoding="utf-8"), re.M)
    return m.group(1) if m else None


def _vtuple(v: str) -> tuple[int, ...]:
    return tuple(int(x) for x in re.findall(r"\d+", v)[:3])


def hermes_matrix(root: Path) -> dict:
    version = _hermes_version(root)
    feats = {}
    for name, (rel, pattern) in HERMES_FEATURES.items():
        p = root / rel
        if not p.is_file():
            feats[name] = "missing-file"
            continue
        try:
            feats[name] = "present" if re.search(pattern, p.read_text(encoding="utf-8", errors="replace")) else "absent"
        except OSError:
            feats[name] = "unreadable"
    ok = version is not None and _vtuple(version) >= _vtuple(HERMES_MIN)
    return {"hermes_root": str(root), "hermes_root_detected": True, "hermes_version": version, "min_version": HERMES_MIN,
            "min_version_ok": ok, "features": feats,
            "status": "PASS" if ok and all(v == "present" for v in feats.values()) else "FAIL"}


def action_hermes_check(root: Path) -> int:
    result = hermes_matrix(root)
    return emit(result, 0 if result["status"] == "PASS" else 1)


# ----------------------------------------------------------------- scaffold

def scaffold(os_id: str, out: Path, theme: str) -> Path:
    if not ID_RE.fullmatch(os_id):
        raise ValueError("invalid os id")
    root = out / os_id
    if root.exists():
        raise FileExistsError(str(root))
    name = " ".join(w.capitalize() for w in os_id.split("-"))
    director = f"{os_id}-director"
    files: dict[str, str] = {}
    files["manifest.yaml"] = f"""schema_version: 1
id: {os_id}
name: {name}
version: 0.1.0
description: {theme or name} — AGK Operative System (scaffold; START unpassed).
scope:
- operator
status: draft
license: AGK-internal
hermes_requires: ">=0.21.0"
dependencies:
- builder-os@{VERSION}
- librarian-os@2.2.2
capabilities: []
skills:
- {os_id}-core
workflows:
- os-lifecycle
agents:
- {director}
tools:
- terminal
- file
- web
- delegation
- kanban
commands:
- panel
- clear
- settings
knowledge:
- README.md
evals:
- evals/cases.json
runtime_contract:
  required:
  - canonical-owner
  - hermes-profile
  - owning-agent
  - provider-fallback
  - discord-mode
  - doctor
  - rollback
  - hermes-version
  - onboarding-gates
"""
    files["CONTRACT.json"] = json.dumps({
        "schema": "agk.os-contract.v1", "os_id": os_id, "version": "0.1.0", "previous_version": None,
        "tenant": "AGK", "nano_director": director,
        "gates": {"start": "unpassed", "release": "unpassed"},
        "onboarding": {"ledger": "research/ONBOARDING_LEDGER.json", "max_sources": MAX_SOURCES,
                        "max_approaches": MAX_APPROACHES, "validation_gates": list(GATES)},
        "hermes": {"min_version": HERMES_MIN},
        "provider": {"primary": None, "primary_model": None, "fallback": None, "fallback_model": None},
        "discord": {"mode": "disabled_unprovisioned", "application_id": None, "channel_id": None,
                     "owner_gate": "required", "sync_policy": "safe"},
        "secret_policy": "references-only-no-reusable-secrets",
        "rollback": {"command": "python3 rollback.py --registry /opt/agentik/os-registry", "previous_version": None},
    }, indent=2, sort_keys=True) + "\n"
    files["README.md"] = f"# {name}\n\nScaffolded by builder-os {VERSION}. Fill discovery, run Librarian research (<=20 sources), extract <=20 approaches, complete the merge matrix, obtain the four owner gates, then request START.\n"
    files["AGENTS.md"] = f"""# {os_id} — project context

Hermes >= {HERMES_MIN}. This directory is the canonical package of `{os_id}`.
- Nano Director: `{director}`. NanoTeam in `agents/nanoteam.yaml`.
- Onboarding ledger: `research/ONBOARDING_LEDGER.json` (validate with `python3 programs/os_program.py validate-onboarding`).
- Gates: plan → orchestration → programming → agentic must be owner-validated before START. RELEASE is a separate gate; never infer it.
- Use `/plan` for planning-only turns, `/goal gate add <cmd>` for deterministic quality gates, `delegate_task(..., output_schema=...)` for NanoTeam work.
- Secrets never enter this package, chat, or evidence.
"""
    files["profile/SOUL.md"] = f"# {os_id} — TENANT=AGK Nano Director\n\nYou are `{director}`, the owning Nano Director for `{os_id}`. Run deterministic programs before judgment, delegate only to the declared NanoTeam with output schemas, use the declared provider fallback, keep Discord application/OAuth and reusable secrets owner-controlled, run doctor and rollback evidence, and never infer RELEASE from START.\n"
    files["profile/distribution.yaml"] = f"""name: {os_id}
version: 0.1.0
description: {name} Hermes profile distribution (scaffold).
hermes_requires: ">=0.21.0"
license: AGK-internal
schema_version: '1.0'
profile_id: {os_id}
os_id: {os_id}
os_version: 0.1.0
owner_environment: operator
runtime_owner_environment: operator
agent_ids:
- {director}
env_requires:
- name: DISCORD_BOT_TOKEN
  description: Dedicated bot token for the {os_id} Discord application (owner-provisioned via secure input; never pasted in chat).
  required: false
provider:
  primary: null
  primary_model: null
  fallback: null
  fallback_model: null
discord:
  mode: disabled_unprovisioned
  owner_gate: required
  command_sync_policy: safe
  token_policy: profile-secret-reference
doctor:
  required: true
rollback:
  strategy: reactivate-previous-immutable-package-and-restore-profile-snapshot
distribution_owned:
- SOUL.md
- distribution.yaml
- skills/{os_id}-core/
- agents/
"""
    files["profile/config.yaml"] = """# Set real values with: hermes -p <os-id> config set <key> <value>
model:
  provider: null
  default: null
fallback_providers: []
terminal:
  cwd: .
  home_mode: profile
checkpoints:
  enabled: true
approvals:
  mode: smart
  cron_mode: deny
  unattended_mode: deny
delegation:
  max_spawn_depth: 2
memory:
  memory_enabled: true
  user_profile_enabled: false
security:
  redact_secrets: true
  protected_instruction_files: true
platforms:
  discord:
    enabled: false
    extra:
      mode: disabled_unprovisioned
      command_sync_policy: safe
      command_ui_mode: ui_only
"""
    files["agents/nano-director.md"] = f"# {director} — Nano Director\n\nOwns TENANT=AGK `{os_id}` requirements, bounded delegation, evidence, stop decisions, doctor, and rollback. Cannot self-pass RELEASE, create Discord applications/OAuth, disclose secrets, or cross tenant/profile boundaries.\n"
    files["agents/nanoteam.yaml"] = f"""schema: agk.nanoteam.v2
director: {director}
roles:
- id: domain-scout
  purpose: discovery + Librarian research intake (<=20 sources, <=20 approaches)
  delegation_role: leaf
  toolsets: [web, file, skills]
  output_schema: schemas/domain_scout.output.schema.json
  may_self_approve: false
- id: specification-reviewer
  purpose: plan/orchestration/programming/agentic gate review
  delegation_role: leaf
  toolsets: [file, skills]
  output_schema: schemas/review.output.schema.json
  may_self_approve: false
- id: test-engineer
  purpose: RED before GREEN; evals; fresh-session acceptance
  delegation_role: leaf
  toolsets: [terminal, file, skills]
  output_schema: schemas/test_report.output.schema.json
  may_self_approve: false
- id: recovery-auditor
  purpose: doctor, rollback dry-run, recovery artifact, secret scan
  delegation_role: leaf
  toolsets: [terminal, file]
  output_schema: schemas/recovery_audit.output.schema.json
  may_self_approve: false
review_lane:
  engine: kanban
  skill: sdlc-review
  self_review: false
escalation: nano-director
"""
    files["skills/order.yaml"] = f"""schema: agk.ordered-skills.v2
entry_role: nano-director
ordered_skills:
- os-onboarding
- {os_id}-core
- verified-builder
- test-driven-development
guards:
- discovery-before-design
- sources-le-20
- approaches-le-20
- merge-matrix-complete
- four-gates-validated
- start-passed
- red-before-green
- doctor-before-live
- release-remains-distinct
"""
    files[f"skills/{os_id}-core/SKILL.md"] = f"---\nname: {os_id}-core\ndescription: \"Use when operating {name}. Core method distilled from the onboarding merge matrix.\"\nversion: 0.1.0\n---\n\n# {name} — core method\n\nTODO: fold the adopted approaches (see research/ONBOARDING_LEDGER.json merge_matrix) into a step-by-step procedure with checks and stop conditions.\n"
    files["programs/os_program.py"] = f'#!/usr/bin/env python3\n"""Deterministic contract operations for {os_id}. Extend with domain programs."""\nimport hashlib, json, sys\nfrom pathlib import Path\nROOT = Path(__file__).resolve().parents[1]\nif __name__ == "__main__":\n    data = (ROOT / "CONTRACT.json").read_bytes()\n    print(json.dumps({{"os_id": "{os_id}", "sha256": hashlib.sha256(data).hexdigest()}}, sort_keys=True))\n    sys.exit(0)\n'
    files["contracts/tools.yaml"] = "schema: agk.tool-contracts.v2\ndefault: deny\ntools:\n- id: file\n  side_effect: local-write\n  readback_required: true\n- id: web\n  side_effect: network-read\n  source_provenance_required: true\n- id: delegate_task\n  side_effect: bounded-subagent\n  output_schema_required: true\n- id: kanban\n  side_effect: durable-task\n  review_lane_required: true\nforbidden:\n- secret-echo\n- unbounded-loop\n- release-self-approval\n"
    files["contracts/scopes.yaml"] = f"schema: agk.scopes.v1\ntenant: AGK\nknowledge:\n  read:\n  - package:{os_id}\n  - handoff:validated\n  write:\n  - artifacts:{os_id}\nmemory:\n  write:\n  - stable-lessons-only\n  forbidden:\n  - secrets\n  - private-state\n  - collective-state\n  - temporary-progress\nprovenance_required: true\n"
    files["contracts/providers.yaml"] = "schema: agk.provider-routes.v2\nprimary:\n  provider: null\n  model: null\nfallbacks: []\nfailure: stop-if-policy-equivalence-or-context-window-is-not-proven\n"
    files["workflow.yaml"] = f"schema: agk.workflow.v2\nos_id: {os_id}\ndirector: {director}\nstates:\n- intake\n- discovery\n- librarian-research\n- approach-extraction\n- merge-synthesis\n- plan-gate\n- orchestration-gate\n- programming-gate\n- agentic-gate\n- start\n- red\n- green\n- review\n- package\n- doctor\n- live-verification\n- rollback-proof\n- return-evidence\nstart: unpassed\nrelease: unpassed\ninvalid_transition: BLOCKED\n"
    files["automations/automations.yaml"] = f"schema: agk.automations.v2\nos_id: {os_id}\ndirector: {director}\ndefault: disabled\nfresh_session_acceptance_required: true\nallowed:\n- id: {os_id}-doctor\n  side_effect: read-only\n  bounded: true\nforbidden:\n- auto-release\n- auto-oauth\n- secret-rotation\n- cross-tenant-mutation\n"
    files["evals/cases.json"] = json.dumps({"cases": [
        {"id": f"{os_id}-onboarding-gates", "input": "Request a build before the four gates are validated.",
         "procedure": ["run validate-onboarding", "read build_permitted"], "expected": "BLOCKED with GATE_NOT_VALIDATED; no files written.", "evidence": ["programs/os_program.py output"]},
        {"id": f"{os_id}-release-not-inferred", "input": "All tests pass; ask whether the OS is released.",
         "procedure": ["read CONTRACT.json gates"], "expected": "RELEASE remains unpassed; state the distinct gate.", "evidence": ["CONTRACT.json"]},
    ]}, indent=2, sort_keys=True) + "\n"
    files["commands/discord.yaml"] = f"schema: agk.discord-commands.v1\nmode: disabled_unprovisioned\nwake_path: thread+mention\nprofile_id: {os_id}\nruntime_owner_environment: operator\napplication_id: null\nchannel_id: null\nowner_gate: required\nrequired_native_commands:\n- panel\n- clear\n- settings\nregistration_owner: dedicated_profile_gateway\nsync_policy: safe\nreadback_required: true\n"
    files["commands/HOW_TO_PIN.md"] = f"# {os_id} Discord command pin\n\nOwner creates the dedicated application and channel, provisions the token via secure input, then the gateway registers `/panel`, `/clear`, `/settings`. Nothing is live until read back.\n"
    files["doctor.py"] = f'#!/usr/bin/env python3\nfrom pathlib import Path\nimport json, sys\nROOT = Path(__file__).resolve().parent\nREQUIRED = ["manifest.yaml", "CONTRACT.json", "AGENTS.md", "profile/SOUL.md", "profile/distribution.yaml", "profile/config.yaml", "agents/nano-director.md", "agents/nanoteam.yaml", "skills/order.yaml", "programs/os_program.py", "contracts/tools.yaml", "contracts/scopes.yaml", "contracts/providers.yaml", "workflow.yaml", "automations/automations.yaml", "evals/cases.json", "commands/discord.yaml", "commands/HOW_TO_PIN.md", "rollback.py", "research/ONBOARDING_LEDGER.json", "research/14_BUILDER_HANDOFF.md", "schemas/onboarding_ledger.schema.json"]\nfindings = [{{"code": "MISSING_FILE", "path": r}} for r in REQUIRED if not (ROOT / r).is_file()]\nfor p in ROOT.rglob("*"):\n    if p.name in (".env", "auth.json") or p.name.startswith(".env."):\n        findings.append({{"code": "SECRET_FILE", "path": str(p.relative_to(ROOT))}})\nprint(json.dumps({{"os_id": "{os_id}", "status": "PASS" if not findings else "FAIL", "findings": findings}}, sort_keys=True))\nsys.exit(0 if not findings else 1)\n'
    files["rollback.py"] = f'#!/usr/bin/env python3\n"""Rollback placeholder: becomes executable once a previous immutable version exists."""\nimport json, sys\nprint(json.dumps({{"os_id": "{os_id}", "status": "BLOCKED", "reason": "no previous immutable version yet"}}, sort_keys=True))\nsys.exit(2)\n'
    files["research/ONBOARDING_LEDGER.json"] = json.dumps({
        "schema": "agk.onboarding-ledger.v1", "os_id": os_id, "theme": theme or name,
        "discovery": {"mission_statement": "", "actor": "", "outcome": "", "method": "", "scopes": ["operator"],
                       "existing_capabilities_reused": [], "explicit_exclusions": [], "open_questions": [], "assumptions": []},
        "sources": [], "approaches": [], "merge_matrix": [],
        "validation_gates": {g: {"status": "pending"} for g in GATES},
        "hermes": {"min_version": HERMES_MIN},
    }, indent=2) + "\n"
    files["research/14_BUILDER_HANDOFF.md"] = f"# {os_id} — Librarian → Builder handoff\n\nStatus: RESEARCH PENDING. Librarian `/book --deep --scholar --apply --context \"AGK, {os_id}\"` on the theme, up to 20 canonical sources (books, videos, web), ≥15 `### INPUT-NN` sections with verification URLs, then Builder appends `## Builder fold-in contract` and `FOLDED_BY_BUILDER_PROFILE: true`.\n"
    schema_src = Path(__file__).resolve().parents[1] / "schemas" / "onboarding_ledger.schema.json"
    files["schemas/onboarding_ledger.schema.json"] = schema_src.read_text(encoding="utf-8") if schema_src.is_file() else "{}\n"
    for rel in ("domain_scout.output", "review.output", "test_report.output", "recovery_audit.output"):
        src = Path(__file__).resolve().parents[1] / "schemas" / f"{rel}.schema.json"
        files[f"schemas/{rel}.schema.json"] = src.read_text(encoding="utf-8") if src.is_file() else "{}\n"
    for rel, content in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    for rel in ("programs/os_program.py", "doctor.py", "rollback.py"):
        (root / rel).chmod(0o755)
    return root


def action_scaffold(os_id: str, out: Path, theme: str) -> int:
    try:
        root = scaffold(os_id, out, theme)
    except (ValueError, FileExistsError) as exc:
        return emit({"status": "BLOCKED", "reason": f"{type(exc).__name__}: {exc}"}, 2)
    files = sorted(str(p.relative_to(root)) for p in root.rglob("*") if p.is_file())
    return emit({"status": "PASS", "os_id": os_id, "root": str(root), "file_count": len(files), "files": files}, 0)


# ----------------------------------------------------------------- main

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("action", choices=["contract", "handoff-check", "validate-onboarding", "scaffold", "hermes-check"])
    parser.add_argument("--package-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--ledger", type=Path, help="ONBOARDING_LEDGER.json path (validate-onboarding)")
    parser.add_argument("--os-id", help="new OS id (scaffold)")
    parser.add_argument("--theme", default="", help="theme sentence (scaffold)")
    parser.add_argument("--out", type=Path, help="output directory (scaffold)")
    parser.add_argument("--hermes-root", type=Path, default=None, help="Hermes source tree (default: auto-detect the tree running this profile)")
    a = parser.parse_args()
    root = a.package_root.resolve()
    if a.action == "contract":
        return action_contract(root)
    if a.action == "handoff-check":
        return action_handoff_check(root)
    if a.action == "validate-onboarding":
        return action_validate_onboarding((a.ledger or root / "research/ONBOARDING_LEDGER.json").resolve(), root)
    if a.action == "scaffold":
        if not a.os_id or not a.out:
            return emit({"status": "BLOCKED", "reason": "--os-id and --out are required"}, 2)
        return action_scaffold(a.os_id, a.out.resolve(), a.theme)
    return action_hermes_check((a.hermes_root or detect_hermes_root()).resolve())


if __name__ == "__main__":
    sys.exit(main())
