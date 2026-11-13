#!/usr/bin/env python3
"""Project AGK's managed global rule block into supported provider files."""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

import yaml

START = "<!-- AGK MANAGED RULES: START -->"
END = "<!-- AGK MANAGED RULES: END -->"


def rules_path() -> Path:
    configured = os.environ.get("AGK_RULES_CONFIG")
    if configured:
        return Path(configured).expanduser()
    user_rules = Path.home() / ".agentik" / "rules.yaml"
    if user_rules.is_file():
        return user_rules
    system_rules = Path("/etc/agk-terminal/rules.yaml")
    if system_rules.is_file():
        return system_rules
    configured_root = os.environ.get("AGK_TERMINAL_ROOT")
    if configured_root:
        return Path(configured_root) / "config" / "rules.yaml"
    candidates = [
        Path.home() / ".local/lib/agk-terminal/config/rules.yaml",
        Path("/usr/local/lib/agk-terminal/config/rules.yaml"),
    ]
    return next((path for path in candidates if path.is_file()), candidates[-1])


def load_rules(path: Path) -> list[dict]:
    document = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    rules = document.get("rules") or []
    return [
        rule
        for rule in rules
        if isinstance(rule, dict)
        and rule.get("enabled", True)
        and str(rule.get("content") or "").strip()
    ]


def applies(rule: dict, provider: str) -> bool:
    providers = rule.get("providers") or ["*"]
    return "*" in providers or provider in providers


def render(rules: list[dict], provider: str) -> str:
    """The managed block for one provider, or "" when no rule applies."""
    selected = [rule for rule in rules if applies(rule, provider)]
    if not selected:
        return ""
    lines = [START, "# AGK global rules", ""]
    for rule in selected:
        title = str(rule.get("title") or rule.get("id") or "Rule").strip()
        content = str(rule.get("content") or "").strip()
        lines.extend([f"## {title}", "", content, ""])
    lines.append(END)
    return "\n".join(lines) + "\n"


def merge(current: str, block: str) -> str:
    """Replace the managed block and nothing else.

    Only text between a START and the END that follows it is AGK's. A marker
    left alone by a manual edit is removed on its own, so the user's text
    around it is never swallowed by the next sync.
    """
    start = current.find(START)
    end = current.find(END, start + len(START)) if start >= 0 else -1
    if start >= 0 and end >= 0:
        before, after = current[:start], current[end + len(END):]
    else:
        before, after = current.replace(START, "").replace(END, ""), ""
    before, after = before.rstrip(), after.strip("\n")
    parts = [part for part in (before, block.rstrip("\n"), after) if part]
    return "\n\n".join(parts) + "\n" if parts else ""


def update(path: Path, block: str) -> bool:
    """Write the block into one instruction file; True when it changed."""
    if path.is_symlink():
        raise RuntimeError(f"refusing symlinked provider rules file: {path}")
    current = path.read_text(encoding="utf-8") if path.is_file() else ""
    updated = merge(current, block)
    if updated == current:
        return False
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    # The file is the user's: keep the permissions they gave it.
    mode = path.stat().st_mode & 0o777 if path.is_file() else 0o600
    temporary = path.with_name(f".{path.name}.agk-new")
    temporary.write_text(updated, encoding="utf-8")
    temporary.chmod(mode)
    temporary.replace(path)
    return True


def targets(home: Path) -> dict[str, tuple[Path, str]]:
    """Each provider's global instruction file and the CLI that reads it."""
    return {
        "claude": (home / ".claude" / "CLAUDE.md", "claude"),
        "codex": (home / ".codex" / "AGENTS.md", "codex"),
        "opencode": (home / ".config" / "opencode" / "AGENTS.md", "opencode"),
    }


def main() -> int:
    rules = load_rules(rules_path())
    for provider, (target, binary) in targets(Path.home()).items():
        # Do not create configuration for a provider that is not installed.
        if not target.parent.is_dir() and shutil.which(binary) is None:
            print(f"{provider}: not installed, skipped")
            continue
        try:
            changed = update(target, render(rules, provider))
        except (OSError, RuntimeError, UnicodeDecodeError) as error:
            # One unusual file must not keep the other providers out of date.
            print(f"{provider}: skipped ({error})", file=sys.stderr)
            continue
        print(f"{provider}: {target}{'' if changed else ' (unchanged)'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
