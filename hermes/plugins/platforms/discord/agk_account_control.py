"""Canonical, redacted account roster and owner alias registry."""
from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from agent.account_usage import fetch_account_usage
from agent.credential_pool import load_pool
from hermes_constants import reset_hermes_home_override, set_hermes_home_override


_PROVIDERS = ("openai-codex", "anthropic")
_SAFE_STATUSES = {"ok", "exhausted", "dead"}


@dataclass(frozen=True)
class UsageWindow:
    label: str
    remaining_percent: float | None
    reset_at: str | None


@dataclass(frozen=True)
class AccountRecord:
    provider: str
    credential_id: str
    owner_name: str
    status: str
    priority: int
    windows: tuple[UsageWindow, ...]


class AliasRegistry:
    """Mode-0600 credential-id to owner-nickname mappings."""

    def __init__(self, path: Path):
        self.path = Path(path)

    def snapshot(self) -> dict[str, dict[str, str]]:
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, TypeError, ValueError):
            return {}
        providers = payload.get("providers") if isinstance(payload, dict) else None
        if not isinstance(providers, dict):
            return {}
        result: dict[str, dict[str, str]] = {}
        for provider, rows in providers.items():
            if not isinstance(provider, str) or not isinstance(rows, list):
                continue
            aliases: dict[str, str] = {}
            for row in rows:
                if not isinstance(row, dict):
                    continue
                credential_id = str(row.get("credential_id") or "").strip()
                owner_name = str(row.get("owner_nickname") or "").strip()
                if credential_id and owner_name:
                    aliases[credential_id[:64]] = owner_name[:64]
            if aliases:
                result[provider] = aliases
        return result

    def replace(self, values: dict[str, dict[str, str]]) -> None:
        normalized: dict[str, dict[str, str]] = {}
        for provider, aliases in values.items():
            provider_name = str(provider).strip()
            if not provider_name or not isinstance(aliases, dict):
                continue
            rows: dict[str, str] = {}
            for credential_id, owner_name in aliases.items():
                stable_id = str(credential_id).strip()[:64]
                nickname = str(owner_name).strip()[:64]
                if stable_id and nickname:
                    rows[stable_id] = nickname
            if rows:
                normalized[provider_name] = rows
        payload = {
            "providers": {
                provider: [
                    {"credential_id": credential_id, "owner_nickname": owner_name}
                    for credential_id, owner_name in sorted(aliases.items())
                ]
                for provider, aliases in sorted(normalized.items())
            }
        }
        self._write(payload)

    def bind(self, provider: str, owner_name: str, credential_id: str) -> None:
        provider = str(provider).strip()
        owner_name = str(owner_name).strip()[:64]
        credential_id = str(credential_id).strip()[:64]
        if not provider or not owner_name or not credential_id:
            raise ValueError("provider, owner_name, and credential_id are required")
        aliases = self.snapshot()
        provider_aliases = aliases.setdefault(provider, {})
        owner_key = owner_name.casefold()
        provider_aliases = {
            stable_id: nickname
            for stable_id, nickname in provider_aliases.items()
            if nickname.casefold() != owner_key and stable_id != credential_id
        }
        provider_aliases[credential_id] = owner_name
        aliases[provider] = provider_aliases
        self.replace(aliases)

    def remove_credential(self, provider: str, credential_id: str) -> None:
        aliases = self.snapshot()
        provider_aliases = aliases.get(provider)
        if not provider_aliases or credential_id not in provider_aliases:
            return
        del provider_aliases[credential_id]
        if not provider_aliases:
            aliases.pop(provider, None)
        self.replace(aliases)

    def owner_name(self, provider: str, credential_id: str) -> str | None:
        return self.snapshot().get(provider, {}).get(credential_id)

    def credential_id(self, provider: str, owner_name: str) -> str | None:
        wanted = owner_name.casefold()
        return next(
            (
                credential_id
                for credential_id, nickname in self.snapshot().get(provider, {}).items()
                if nickname.casefold() == wanted
            ),
            None,
        )

    def _write(self, payload: dict) -> None:
        self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{self.path.name}.", suffix=".new", dir=self.path.parent
        )
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, indent=2)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            temporary.chmod(0o600)
            os.replace(temporary, self.path)
        finally:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass


def _usage_windows(provider: str, entry) -> tuple[UsageWindow, ...]:
    token = getattr(entry, "runtime_api_key", None) or getattr(entry, "access_token", None)
    if not token:
        return ()
    try:
        usage = fetch_account_usage(
            provider,
            base_url=getattr(entry, "base_url", None),
            api_key=token,
        )
    except Exception:
        return ()
    windows: list[UsageWindow] = []
    for window in (getattr(usage, "windows", ()) or ()):
        used = getattr(window, "used_percent", None)
        remaining = None if used is None else max(0.0, min(100.0, 100.0 - float(used)))
        reset_at = getattr(window, "reset_at", None)
        windows.append(
            UsageWindow(
                label=str(getattr(window, "label", None) or "Limit")[:100],
                remaining_percent=remaining,
                reset_at=reset_at.isoformat() if hasattr(reset_at, "isoformat") else None,
            )
        )
    return tuple(windows)


def load_account_roster(
    hermes_home: Path, *, pool_loader=load_pool
) -> tuple[AccountRecord, ...]:
    aliases = AliasRegistry(Path(hermes_home) / "provider-account-aliases.json").snapshot()
    records: list[AccountRecord] = []
    token = set_hermes_home_override(hermes_home)
    try:
        for provider in _PROVIDERS:
            pool = pool_loader(provider)
            for entry in pool.entries():
                raw_status = str(getattr(entry, "last_status", None) or "").lower()
                status = raw_status if raw_status in _SAFE_STATUSES else "unknown"
                windows = _usage_windows(provider, entry)
                if windows and status == "unknown":
                    status = "ok"
                credential_id = str(getattr(entry, "id", None) or "unknown")[:64]
                records.append(
                    AccountRecord(
                        provider=provider,
                        credential_id=credential_id,
                        owner_name=aliases.get(provider, {}).get(credential_id, ""),
                        status=status,
                        priority=int(getattr(entry, "priority", 0) or 0),
                        windows=windows,
                    )
                )
    finally:
        reset_hermes_home_override(token)
    return tuple(sorted(records, key=lambda record: (_PROVIDERS.index(record.provider), record.priority)))


def render_account_roster(records: Iterable[AccountRecord]) -> str:
    """Render only explicitly whitelisted, non-secret account fields."""
    lines = ["# Station · Account roster", ""]
    for record in records:
        owner = record.owner_name or "Unassigned"
        status = record.status if record.status in _SAFE_STATUSES else "unknown"
        lines.append(
            f"**{owner}** · `{record.provider}` · `{record.credential_id}` · "
            f"`{status}` · priority {record.priority}"
        )
        if not record.windows:
            lines.append("- Usage unavailable")
        for window in record.windows[:3]:
            remaining = window.remaining_percent
            usage = "unavailable" if remaining is None else f"{round(max(0.0, min(100.0, remaining)))}% remaining"
            reset = f" · resets {window.reset_at}" if window.reset_at else ""
            lines.append(f"- {window.label} · {usage}{reset}")
        lines.append("")
    return "\n".join(lines)


def voice_binding_key(provider: str, owner_name: str) -> str:
    return f"voice-owner:{provider}:{owner_name.casefold()}"
