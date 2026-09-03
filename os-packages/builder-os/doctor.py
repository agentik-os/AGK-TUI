#!/usr/bin/env python3
"""Read-only package doctor for builder-os 0.5.0 (Hermes >= 0.21).

Checks: required files, contract identity, RELEASE gate, Librarian handoff (15 inputs + fold-in),
recovery ZIP content, Hermes version/feature matrix (when --hermes-root exists), onboarding ledger
schema validity, NanoTeam/agents consistency, ordered skills, and a secret-file scan.
Never mutates, never reads secret values, never passes a gate.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import zipfile
from pathlib import Path

sys.dont_write_bytecode = True  # read-only doctor: never leave __pycache__ inside the package

OS_ID = "builder-os"
VERSION = "0.5.0"
HERMES_MIN = "0.21.0"
REQUIRED = [
    "manifest.yaml", "CONTRACT.json", "README.md", "AGENTS.md",
    "profile/distribution.yaml", "profile/SOUL.md", "profile/config.yaml",
    "agents/nano-director.md", "agents/nanoteam.yaml", "skills/order.yaml",
    "skills/os-onboarding/SKILL.md", "profile/skills/os-onboarding/SKILL.md",
    "programs/os_program.py", "schemas/onboarding_ledger.schema.json",
    "schemas/domain_scout.output.schema.json", "schemas/review.output.schema.json",
    "schemas/test_report.output.schema.json", "schemas/recovery_audit.output.schema.json",
    "contracts/tools.yaml", "contracts/scopes.yaml", "contracts/providers.yaml",
    "workflow.yaml", "workflows/os-onboarding.yaml", "workflows/build-cycle.yaml", "workflows/os-runtime-delivery.yaml",
    "automations/automations.yaml", "evals/cases.json", "commands/discord.yaml", "commands/HOW_TO_PIN.md",
    "doctor.py", "rollback.py", "research/14_BUILDER_HANDOFF.md", "research/15_INPUTS_LEDGER.json",
]
AGENTS = ["master-os-builder", "domain-scout", "specification-reviewer", "test-engineer", "recovery-auditor"]
SECRET_NAMES = {".env", "auth.json", "state.db", "credentials.json"}
SECRET_PATTERNS = re.compile(r"(sk-[A-Za-z0-9]{20,}|ghp_[A-Za-z0-9]{30,}|xox[baprs]-[A-Za-z0-9-]{10,}|[MN][A-Za-z\d]{23,}\.[\w-]{6}\.[\w-]{27,})")


def _vt(v: str):
    return tuple(int(x) for x in re.findall(r"\d+", v)[:3])


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--package-root", type=Path, default=Path(__file__).resolve().parent)
    p.add_argument("--recovery-extraction", action="store_true")
    p.add_argument("--hermes-root", type=Path, default=None, help="Hermes tree (default: auto-detect the one running this profile)")
    a = p.parse_args()
    root = a.package_root.resolve()
    findings: list[dict] = []
    checks: dict[str, str] = {}

    def F(code, **kw):
        findings.append({"code": code, **kw})

    # 1. files
    for rel in REQUIRED:
        if not (root / rel).is_file():
            F("MISSING_FILE", path=rel)
    checks["required_files"] = "FAIL" if any(f["code"] == "MISSING_FILE" for f in findings) else "PASS"

    # 2. contract
    try:
        c = json.loads((root / "CONTRACT.json").read_text(encoding="utf-8"))
        if c.get("os_id") != OS_ID or c.get("version") != VERSION or c.get("tenant") != "AGK":
            F("CONTRACT_IDENTITY")
        if c.get("gates", {}).get("release") != "unpassed":
            F("RELEASE_GATE")
        if c.get("hermes", {}).get("min_version") != HERMES_MIN:
            F("CONTRACT_HERMES_MIN")
        ob = c.get("onboarding", {})
        if ob.get("max_sources") != 20 or ob.get("max_approaches") != 20 or ob.get("validation_gates") != ["plan", "orchestration", "programming", "agentic"]:
            F("CONTRACT_ONBOARDING")
        checks["contract_identity"] = "PASS" if not any(f["code"].startswith(("CONTRACT", "RELEASE")) for f in findings) else "FAIL"
    except Exception as e:  # noqa: BLE001
        F("CONTRACT_PARSE", error=type(e).__name__)
        checks["contract_identity"] = "FAIL"

    # 3. handoff
    try:
        t = (root / "research/14_BUILDER_HANDOFF.md").read_text(encoding="utf-8")
        ids = re.findall(r"^### INPUT-(\d{2})\b", t, re.M)
        if ids != [f"{i:02d}" for i in range(1, 16)] or "FOLDED_BY_BUILDER_PROFILE: true" not in t:
            F("HANDOFF")
        if "## Builder fold-in contract — Hermes 0.21 / 0.5.0" not in t:
            F("HANDOFF_FOLDIN_050")
        checks["handoff"] = "PASS" if not any(f["code"].startswith("HANDOFF") for f in findings) else "FAIL"
    except Exception as e:  # noqa: BLE001
        F("HANDOFF_READ", error=type(e).__name__)
        checks["handoff"] = "FAIL"

    # 4. recovery
    if not a.recovery_extraction:
        archive = root / "recovery" / f"{OS_ID}-{VERSION}.zip"
        try:
            with zipfile.ZipFile(archive) as z:
                names = z.namelist()
                if not {"CONTRACT.json", "doctor.py", "rollback.py", "manifest.yaml", "AGENTS.md", "schemas/onboarding_ledger.schema.json"} <= set(names):
                    F("RECOVERY_CONTENT")
                if names != sorted(names) or any(i.date_time != (1980, 1, 1, 0, 0, 0) for i in z.infolist()):
                    F("RECOVERY_NOT_DETERMINISTIC")
                if any(Path(n).name in SECRET_NAMES or "__pycache__" in n or n.endswith(".pyc") for n in names):
                    F("RECOVERY_UNSAFE_ENTRY")
            checks["recovery"] = "PASS" if not any(f["code"].startswith("RECOVERY") for f in findings) else "FAIL"
        except Exception as e:  # noqa: BLE001
            F("RECOVERY_READ", error=type(e).__name__)
            checks["recovery"] = "FAIL"
    else:
        checks["recovery"] = "SKIPPED"

    # 5. hermes version + features (tree auto-detected unless --hermes-root given)
    import importlib.util
    _spec = importlib.util.spec_from_file_location("agk_os_program", root / "programs" / "os_program.py")
    _osp = importlib.util.module_from_spec(_spec)  # type: ignore[arg-type]
    try:
        _spec.loader.exec_module(_osp)  # type: ignore[union-attr]
    except Exception as e:  # noqa: BLE001
        _osp = None
        F("PROGRAM_IMPORT", error=type(e).__name__)
    hr = a.hermes_root or (_osp.detect_hermes_root() if _osp else Path("/opt/agk-terminal/hermes-agent"))
    checks["hermes_root"] = str(hr)
    py = hr / "pyproject.toml"
    if py.is_file():
        m = re.search(r'^version\s*=\s*"([^"]+)"', py.read_text(encoding="utf-8"), re.M)
        ver = m.group(1) if m else None
        if not ver:
            F("HERMES_VERSION_UNKNOWN", root=str(hr))
        elif _vt(ver) < _vt(HERMES_MIN):
            F("HERMES_VERSION_TOO_OLD", found=ver, required=HERMES_MIN)
        else:
            try:
                mx = _osp.hermes_matrix(hr)
                absent = sorted(k for k, v in mx["features"].items() if v != "present")
                if absent:
                    F("HERMES_FEATURES_ABSENT", features=absent)
            except Exception as e:  # noqa: BLE001
                F("HERMES_MATRIX_ERROR", error=type(e).__name__)
        checks["hermes_version"] = "PASS" if not any(f["code"].startswith("HERMES") for f in findings) else "FAIL"
    else:
        checks["hermes_version"] = "UNKNOWN"

    # 6. onboarding schema
    try:
        schema = json.loads((root / "schemas/onboarding_ledger.schema.json").read_text(encoding="utf-8"))
        if schema["properties"]["sources"]["maxItems"] != 20 or schema["properties"]["approaches"]["maxItems"] != 20:
            F("ONBOARDING_SCHEMA_LIMITS")
        try:
            import jsonschema  # type: ignore
            jsonschema.Draft202012Validator.check_schema(schema)
        except ImportError:
            pass
        checks["onboarding_schema"] = "PASS" if not any(f["code"].startswith("ONBOARDING") for f in findings) else "FAIL"
    except Exception as e:  # noqa: BLE001
        F("ONBOARDING_SCHEMA_READ", error=type(e).__name__)
        checks["onboarding_schema"] = "FAIL"

    # 7. agents
    try:
        import yaml  # type: ignore
        team = yaml.safe_load((root / "agents/nanoteam.yaml").read_text(encoding="utf-8"))
        role_ids = {r["id"] for r in team.get("roles", [])}
        if role_ids != set(AGENTS) - {"master-os-builder"} or team.get("director") != "master-os-builder":
            F("NANOTEAM_ROLES", roles=sorted(role_ids))
        for r in team.get("roles", []):
            if r.get("may_self_approve") is not False:
                F("NANOTEAM_SELF_APPROVE", role=r.get("id"))
            if not (root / str(r.get("output_schema", ""))).is_file():
                F("NANOTEAM_SCHEMA_MISSING", role=r.get("id"))
        for aid in AGENTS:
            ay = root / "profile/agents" / aid / "agent.yaml"
            pm = root / "profile/agents" / aid / "prompt.md"
            if not ay.is_file() or not pm.is_file():
                F("AGENT_FILES", agent=aid)
                continue
            data = yaml.safe_load(ay.read_text(encoding="utf-8")) or {}
            if data.get("id") != aid or data.get("version") != VERSION:
                F("AGENT_IDENTITY", agent=aid)
            if len(pm.read_text(encoding="utf-8")) < 1200:
                F("AGENT_PROMPT_THIN", agent=aid)
        checks["agents"] = "PASS" if not any(f["code"].startswith(("NANOTEAM", "AGENT")) for f in findings) else "FAIL"
        order = yaml.safe_load((root / "skills/order.yaml").read_text(encoding="utf-8"))
        if (order.get("ordered_skills") or [None])[0] != "os-onboarding":
            F("SKILLS_ORDER_ONBOARDING_FIRST")
        for s in order.get("ordered_skills", []):
            if not (root / "profile/skills" / s / "SKILL.md").is_file():
                F("SKILL_NOT_SHIPPED", skill=s)
        checks["skills_order"] = "PASS" if not any(f["code"].startswith("SKILL") for f in findings) else "FAIL"
    except Exception as e:  # noqa: BLE001
        F("AGENTS_PARSE", error=type(e).__name__)
        checks["agents"] = checks.get("agents", "FAIL")
        checks["skills_order"] = checks.get("skills_order", "FAIL")

    # 8. secrets
    for path in root.rglob("*"):
        if path.is_symlink():
            F("SYMLINK", path=str(path.relative_to(root)))
            continue
        if not path.is_file():
            continue
        if path.name in SECRET_NAMES or path.name.startswith(".env"):
            F("SECRET_FILE", path=str(path.relative_to(root)))
            continue
        if path.suffix in {".zip", ".png", ".jpg", ".pyc"}:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if SECRET_PATTERNS.search(text):
            F("SECRET_PATTERN", path=str(path.relative_to(root)))
    checks["no_secrets"] = "PASS" if not any(f["code"].startswith(("SECRET", "SYMLINK")) for f in findings) else "FAIL"

    out = {"status": "PASS" if not findings else "FAIL", "os_id": OS_ID, "version": VERSION,
           "hermes_min": HERMES_MIN, "mode": "recovery-extraction" if a.recovery_extraction else "package",
           "checks": checks, "findings": findings}
    print(json.dumps(out, sort_keys=True))
    return 0 if not findings else 1


if __name__ == "__main__":
    raise SystemExit(main())
