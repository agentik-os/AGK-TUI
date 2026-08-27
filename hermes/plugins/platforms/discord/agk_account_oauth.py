"""Durable, non-secret OAuth attempt state and user-systemd runner control."""
from __future__ import annotations

import fcntl
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
import time
import uuid
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Callable

_PROVIDERS = {"openai-codex", "anthropic"}
_OPERATIONS = {"add", "reconnect"}
_LIVE_STATUSES = {"pending", "running", "awaiting-code", "code-submitted"}
_STATUSES = _LIVE_STATUSES | {"cancelled", "expired", "failed", "succeeded"}
_SAFE_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9 -]{0,63}\Z")
_SAFE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}\Z")
_SAFE_ATTEMPT = re.compile(r"[a-f0-9]{32}\Z")
_DEFAULT_GUILD_ID = 1541131439599386644
_TIMEOUT_SECONDS = 900


@dataclass(frozen=True)
class OAuthAttempt:
    attempt_id: str
    provider: str
    operation: str
    owner_name: str
    target_credential_id: str | None
    user_id: int
    guild_id: int
    channel_id: int
    created_at: float
    expires_at: float
    status: str
    runner_unit: str


def _safe_name(value: object) -> str:
    name = str(value).strip()
    folded = name.casefold()
    if not _SAFE_NAME.fullmatch(name) or folded.startswith(("sk-", "bearer ", "xox")):
        raise ValueError("owner_name must be a safe technical alias")
    return name


def _safe_optional_id(value: object | None) -> str | None:
    if value is None:
        return None
    identifier = str(value).strip()
    if not _SAFE_ID.fullmatch(identifier) or identifier.casefold().startswith(("sk-", "xox")):
        raise ValueError("target_credential_id must be a safe stable identifier")
    return identifier


def _systemd_call(argv: list[str]) -> int:
    return subprocess.run(argv, check=False, stdin=subprocess.DEVNULL).returncode


class OAuthAttemptStore:
    """Atomic mode-0600 attempt metadata below a Hermes home directory."""

    def __init__(self, hermes_home: Path, *, clock: Callable[[], float] = time.time):
        self.path = Path(hermes_home) / "state/account-oauth/attempts.json"
        self.lock_path = self.path.with_suffix(".lock")
        self.clock = clock

    def create(
        self,
        provider,
        operation,
        owner_name,
        target_credential_id,
        user_id,
        guild_id=_DEFAULT_GUILD_ID,
        channel_id=0,
    ) -> OAuthAttempt:
        provider = str(provider)
        operation = str(operation)
        if provider not in _PROVIDERS:
            raise ValueError("provider must be openai-codex or anthropic")
        if operation not in _OPERATIONS:
            raise ValueError("operation must be add or reconnect")
        owner_name = _safe_name(owner_name)
        target_credential_id = _safe_optional_id(target_credential_id)
        user_id, guild_id, channel_id = int(user_id), int(guild_id), int(channel_id)
        if min(user_id, guild_id, channel_id) < 0:
            raise ValueError("Discord IDs must be non-negative")
        now = float(self.clock())
        attempt = OAuthAttempt(
            attempt_id=uuid.uuid4().hex,
            provider=provider,
            operation=operation,
            owner_name=owner_name,
            target_credential_id=target_credential_id,
            user_id=user_id,
            guild_id=guild_id,
            channel_id=channel_id,
            created_at=now,
            expires_at=now + _TIMEOUT_SECONDS,
            status="pending",
            runner_unit="",
        )
        with self._locked():
            attempts = self._read_unlocked()
            owner_key = owner_name.casefold()
            attempts = [
                replace(item, status="cancelled")
                if item.provider == provider
                and item.owner_name.casefold() == owner_key
                and item.status in _LIVE_STATUSES
                else item
                for item in attempts
            ]
            attempts.append(attempt)
            self._write_unlocked(attempts)
        return attempt

    def get(self, attempt_id: str) -> OAuthAttempt | None:
        if not _SAFE_ATTEMPT.fullmatch(str(attempt_id)):
            return None
        with self._locked():
            return next(
                (item for item in self._read_unlocked() if item.attempt_id == attempt_id),
                None,
            )

    def update(self, attempt_id: str, **changes) -> OAuthAttempt:
        allowed = {"status", "runner_unit"}
        if not changes or set(changes) - allowed:
            raise ValueError("only status and runner_unit may be updated")
        if "status" in changes and changes["status"] not in _STATUSES:
            raise ValueError("invalid attempt status")
        if "runner_unit" in changes:
            expected = f"agk-account-oauth-{attempt_id}.service"
            if changes["runner_unit"] not in {"", expected}:
                raise ValueError("runner unit does not match attempt")
        with self._locked():
            attempts = self._read_unlocked()
            for index, item in enumerate(attempts):
                if item.attempt_id == attempt_id:
                    updated = replace(item, **changes)
                    attempts[index] = updated
                    self._write_unlocked(attempts)
                    return updated
        raise KeyError(attempt_id)

    def cancel_conflicts(self, provider: str, owner_name: str) -> None:
        if provider not in _PROVIDERS:
            raise ValueError("provider must be canonical")
        owner_key = _safe_name(owner_name).casefold()
        with self._locked():
            attempts = self._read_unlocked()
            updated = [
                replace(item, status="cancelled")
                if item.provider == provider
                and item.owner_name.casefold() == owner_key
                and item.status in _LIVE_STATUSES
                else item
                for item in attempts
            ]
            if updated != attempts:
                self._write_unlocked(updated)

    def _prepare_directory(self) -> None:
        self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.path.parent.chmod(0o700)

    def _locked(self):
        store = self

        class Lock:
            def __enter__(self):
                store._prepare_directory()
                self.fd = os.open(
                    store.lock_path,
                    os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0),
                    0o600,
                )
                os.fchmod(self.fd, 0o600)
                fcntl.flock(self.fd, fcntl.LOCK_EX)
                return self

            def __exit__(self, *_args):
                fcntl.flock(self.fd, fcntl.LOCK_UN)
                os.close(self.fd)

        return Lock()

    def _read_unlocked(self) -> list[OAuthAttempt]:
        if not self.path.exists():
            return []
        descriptor = os.open(self.path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        try:
            metadata = os.fstat(descriptor)
            if not stat.S_ISREG(metadata.st_mode):
                raise ValueError("attempt store must be a regular file")
            os.fchmod(descriptor, 0o600)
            with os.fdopen(descriptor, encoding="utf-8") as handle:
                descriptor = -1
                payload = json.load(handle)
        finally:
            if descriptor >= 0:
                os.close(descriptor)
        rows = payload.get("attempts") if isinstance(payload, dict) else None
        if not isinstance(rows, list):
            raise ValueError("invalid attempt store")
        return [OAuthAttempt(**row) for row in rows]

    def _write_unlocked(self, attempts: list[OAuthAttempt]) -> None:
        descriptor, name = tempfile.mkstemp(
            prefix=".attempts.", suffix=".new", dir=self.path.parent
        )
        temporary = Path(name)
        try:
            os.fchmod(descriptor, 0o600)
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                json.dump({"attempts": [asdict(item) for item in attempts]}, handle, indent=2)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.path)
            self.path.chmod(0o600)
        finally:
            temporary.unlink(missing_ok=True)


class OAuthRunner:
    """Launch and control one sibling transient user unit per OAuth attempt."""

    def __init__(
        self,
        store: OAuthAttemptStore,
        systemd: Callable[[list[str]], int] = _systemd_call,
        *,
        runner_script: Path | None = None,
        fifo_writer: Callable[[Path, str], None] | None = None,
    ):
        self.store = store
        self.systemd = systemd
        self.runner_script = Path(runner_script or Path(__file__).resolve().parents[4] / "scripts/agk_provider_oauth_runner.py")
        self._fifo_writer = fifo_writer or self._write_fifo

    def fifo_path(self, attempt: OAuthAttempt) -> Path:
        return self.store.path.parent / f"{attempt.attempt_id}.fifo"

    def result_path(self, attempt: OAuthAttempt) -> Path:
        return self.store.path.parent / f"{attempt.attempt_id}.result.json"

    def start(self, attempt_id: str) -> OAuthAttempt:
        attempt = self.store.get(attempt_id)
        if attempt is None:
            raise KeyError(attempt_id)
        if attempt.status != "pending" or float(self.store.clock()) >= attempt.expires_at:
            if float(self.store.clock()) >= attempt.expires_at and attempt.status in _LIVE_STATUSES:
                self.store.update(attempt_id, status="expired")
            raise ValueError("attempt is not startable")
        unit = f"agk-account-oauth-{attempt.attempt_id}.service"
        argv = [
            "systemd-run", "--user", "--unit", unit, "--collect", "--quiet",
            sys.executable, str(self.runner_script),
            "--provider", attempt.provider,
            "--alias", attempt.owner_name,
            "--fifo", str(self.fifo_path(attempt)),
            "--state", str(self.result_path(attempt)),
            "--timeout", str(_TIMEOUT_SECONDS),
        ]
        if self.systemd(argv) != 0:
            self.store.update(attempt_id, status="failed", runner_unit=unit)
            raise RuntimeError("OAuth sibling unit failed to start")
        return self.store.update(attempt_id, status="running", runner_unit=unit)

    def submit_claude_code(
        self, attempt_id: str, code: str, *, user_id: int, channel_id: int
    ) -> bool:
        attempt = self.store.get(attempt_id)
        now = float(self.store.clock())
        if attempt is None or attempt.provider != "anthropic":
            return False
        if now >= attempt.expires_at:
            if attempt.status in _LIVE_STATUSES:
                self.store.update(attempt_id, status="expired")
            return False
        if (
            int(user_id) != attempt.user_id
            or int(channel_id) != attempt.channel_id
            or attempt.status not in {"pending", "running", "awaiting-code"}
        ):
            return False
        value = str(code)
        if not value or "\n" in value or "\r" in value or len(value.encode("utf-8")) > 4096:
            return False
        try:
            self._fifo_writer(self.fifo_path(attempt), value + "\n")
        except OSError:
            return False
        self.store.update(attempt_id, status="code-submitted")
        return True

    def cancel(self, attempt_id: str) -> bool:
        attempt = self.store.get(attempt_id)
        if attempt is None:
            return False
        if attempt.runner_unit:
            expected = f"agk-account-oauth-{attempt.attempt_id}.service"
            if attempt.runner_unit != expected:
                raise ValueError("invalid recorded runner unit")
            self.systemd(["systemctl", "--user", "stop", attempt.runner_unit])
        for path in (
            self.fifo_path(attempt),
            self.result_path(attempt),
            self.result_path(attempt).with_suffix(".raw.log"),
        ):
            path.unlink(missing_ok=True)
        self.store.update(attempt_id, status="cancelled")
        return True

    @staticmethod
    def _write_fifo(path: Path, value: str) -> None:
        descriptor = os.open(
            path,
            os.O_WRONLY | os.O_NONBLOCK | getattr(os, "O_NOFOLLOW", 0),
        )
        try:
            if not stat.S_ISFIFO(os.fstat(descriptor).st_mode):
                raise OSError("OAuth input path is not a FIFO")
            os.write(descriptor, value.encode("utf-8"))
        finally:
            os.close(descriptor)
