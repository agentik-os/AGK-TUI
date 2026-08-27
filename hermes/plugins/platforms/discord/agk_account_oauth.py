"""Durable, non-secret OAuth attempt state and user-systemd runner control."""
from __future__ import annotations

import fcntl
import json
import os
import re
import select
import stat
import subprocess
import sys
import tempfile
import time
import uuid
from collections.abc import Callable
from dataclasses import asdict, dataclass, replace
from pathlib import Path

_PROVIDERS = {"openai-codex", "anthropic"}
_OPERATIONS = {"add", "reconnect"}
_LIVE_STATUSES = {
    "pending",
    "starting",
    "running",
    "awaiting-code",
    "submitting",
    "code-submitted",
    "cancelling",
}
_TERMINAL_STATUSES = {"cancelled", "expired", "failed", "succeeded"}
_STATUSES = _LIVE_STATUSES | _TERMINAL_STATUSES
_ALLOWED_TRANSITIONS = {
    "pending": {"starting", "running", "awaiting-code", "submitting", "cancelled", "expired", "failed"},
    "starting": {"running", "cancelling", "cancelled", "expired", "failed"},
    "running": {"awaiting-code", "submitting", "code-submitted", "cancelling", "cancelled", "expired", "failed", "succeeded"},
    "awaiting-code": {"submitting", "code-submitted", "cancelling", "cancelled", "expired", "failed", "succeeded"},
    "submitting": {"pending", "running", "awaiting-code", "code-submitted", "cancelling", "cancelled", "expired", "failed", "succeeded"},
    "code-submitted": {"cancelling", "cancelled", "expired", "failed", "succeeded"},
    "cancelling": {"running", "awaiting-code", "submitting", "code-submitted", "cancelled", "expired", "failed"},
    "cancelled": set(),
    "expired": set(),
    "failed": set(),
    "succeeded": set(),
}
_SAFE_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9 -]{0,63}\Z")
_SAFE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}\Z")
_SAFE_ATTEMPT = re.compile(r"[a-f0-9]{32}\Z")
_DEFAULT_GUILD_ID = 1541131439599386644
_TIMEOUT_SECONDS = 900
_SYSTEMCTL_INACTIVE_CODES = {3, 4}


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
        attempt = self._build_attempt(
            provider,
            operation,
            owner_name,
            target_credential_id,
            user_id,
            guild_id,
            channel_id,
        )
        with self._locked():
            attempts = self._normalize_unlocked(self._read_unlocked())
            conflicts = self._matching_live(attempts, attempt.provider, attempt.owner_name)
            if any(item.runner_unit for item in conflicts):
                raise RuntimeError("running conflict requires runner-aware replacement")
            conflict_ids = {item.attempt_id for item in conflicts}
            attempts = [
                replace(item, status="cancelled") if item.attempt_id in conflict_ids else item
                for item in attempts
            ]
            attempts.append(attempt)
            self._write_unlocked(attempts)
        return attempt

    def conflicts(self, provider: str, owner_name: str) -> list[OAuthAttempt]:
        if provider not in _PROVIDERS:
            raise ValueError("provider must be canonical")
        owner_name = _safe_name(owner_name)
        with self._locked():
            attempts = self._normalize_unlocked(self._read_unlocked())
            self._write_if_changed_unlocked(attempts)
            return self._matching_live(attempts, provider, owner_name)

    def get(self, attempt_id: str) -> OAuthAttempt | None:
        if not _SAFE_ATTEMPT.fullmatch(str(attempt_id)):
            return None
        with self._locked():
            original = self._read_unlocked()
            attempts = self._normalize_unlocked(original)
            if attempts != original:
                self._write_unlocked(attempts)
            return next((item for item in attempts if item.attempt_id == attempt_id), None)

    def update(self, attempt_id: str, **changes) -> OAuthAttempt:
        allowed = {"status", "runner_unit"}
        if not changes or set(changes) - allowed:
            raise ValueError("only status and runner_unit may be updated")
        if "status" in changes and changes["status"] not in _STATUSES:
            raise ValueError("invalid attempt status")
        self._validate_runner_unit(attempt_id, changes.get("runner_unit"))
        with self._locked():
            attempts = self._normalize_unlocked(self._read_unlocked())
            for index, item in enumerate(attempts):
                if item.attempt_id != attempt_id:
                    continue
                target_status = changes.get("status", item.status)
                if (
                    target_status != item.status
                    and target_status not in _ALLOWED_TRANSITIONS[item.status]
                ):
                    raise ValueError("invalid attempt status transition")
                updated = replace(item, **changes)
                attempts[index] = updated
                self._write_unlocked(attempts)
                return updated
        raise KeyError(attempt_id)

    def transition(
        self,
        attempt_id: str,
        expected: set[str],
        *,
        status: str,
        runner_unit: str | None = None,
    ) -> OAuthAttempt | None:
        if status not in _STATUSES:
            raise ValueError("invalid attempt status")
        self._validate_runner_unit(attempt_id, runner_unit)
        with self._locked():
            attempts = self._normalize_unlocked(self._read_unlocked())
            for index, item in enumerate(attempts):
                if item.attempt_id != attempt_id or item.status not in expected:
                    return None
                changes = {"status": status}
                if runner_unit is not None:
                    changes["runner_unit"] = runner_unit
                updated = replace(item, **changes)
                attempts[index] = updated
                self._write_unlocked(attempts)
                return updated
        return None

    def reserve_submission(
        self, attempt_id: str, *, user_id: int, channel_id: int
    ) -> tuple[OAuthAttempt, str] | None:
        with self._locked():
            attempts = self._normalize_unlocked(self._read_unlocked())
            for index, item in enumerate(attempts):
                if item.attempt_id != attempt_id:
                    continue
                if (
                    item.provider != "anthropic"
                    or int(user_id) != item.user_id
                    or int(channel_id) != item.channel_id
                    or item.status not in {"pending", "running", "awaiting-code"}
                ):
                    return None
                previous = item.status
                reserved = replace(item, status="submitting")
                attempts[index] = reserved
                self._write_unlocked(attempts)
                return reserved, previous
        return None

    def cancel_conflicts(self, provider: str, owner_name: str) -> None:
        conflicts = self.conflicts(provider, owner_name)
        if any(item.runner_unit for item in conflicts):
            raise RuntimeError("running conflict requires runner-aware cancellation")
        for item in conflicts:
            self.transition(item.attempt_id, _LIVE_STATUSES, status="cancelled")

    def _build_attempt(
        self, provider, operation, owner_name, target_credential_id, user_id, guild_id, channel_id
    ) -> OAuthAttempt:
        provider, operation = str(provider), str(operation)
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
        return OAuthAttempt(
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

    @staticmethod
    def _matching_live(
        attempts: list[OAuthAttempt], provider: str, owner_name: str
    ) -> list[OAuthAttempt]:
        owner_key = owner_name.casefold()
        return [
            item
            for item in attempts
            if item.provider == provider
            and item.owner_name.casefold() == owner_key
            and item.status in _LIVE_STATUSES
        ]

    @staticmethod
    def _validate_runner_unit(attempt_id: str, runner_unit: str | None) -> None:
        if runner_unit is None:
            return
        expected = f"agk-account-oauth-{attempt_id}.service"
        if runner_unit not in {"", expected}:
            raise ValueError("runner unit does not match attempt")

    def _normalize_unlocked(self, attempts: list[OAuthAttempt]) -> list[OAuthAttempt]:
        now = float(self.clock())
        normalized = []
        for item in attempts:
            terminal = self._terminal_result_status(item.attempt_id)
            if item.status in _LIVE_STATUSES and terminal is not None:
                item = replace(item, status=terminal)
            elif item.status in _LIVE_STATUSES and now >= item.expires_at:
                item = replace(item, status="expired")
            normalized.append(item)
        return normalized

    def _terminal_result_status(self, attempt_id: str) -> str | None:
        path = self.path.parent / f"{attempt_id}.result.json"
        try:
            descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        except OSError:
            return None
        try:
            if not stat.S_ISREG(os.fstat(descriptor).st_mode):
                return None
            with os.fdopen(descriptor, encoding="utf-8") as handle:
                descriptor = -1
                payload = json.load(handle)
        except (OSError, ValueError, json.JSONDecodeError):
            return None
        finally:
            if descriptor >= 0:
                os.close(descriptor)
        status_value = payload.get("status") if isinstance(payload, dict) else None
        return status_value if status_value in _TERMINAL_STATUSES else None

    def _write_if_changed_unlocked(self, attempts: list[OAuthAttempt]) -> None:
        if attempts != self._read_unlocked():
            self._write_unlocked(attempts)

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
            raise TypeError("invalid attempt store")
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
        fifo_writer: Callable[[Path, str], int] | None = None,
    ):
        self.store = store
        self.systemd = systemd
        self.runner_script = Path(
            runner_script
            or Path(__file__).resolve().parents[4] / "scripts/agk_provider_oauth_runner.py"
        )
        self._fifo_writer = fifo_writer or self._write_fifo

    def create(self, provider, operation, owner_name, target_credential_id, user_id, guild_id=_DEFAULT_GUILD_ID, channel_id=0) -> OAuthAttempt:
        for conflict in self.store.conflicts(str(provider), str(owner_name)):
            if not self.cancel(conflict.attempt_id):
                raise RuntimeError("conflicting OAuth attempt could not be stopped")
        return self.store.create(
            provider,
            operation,
            owner_name,
            target_credential_id,
            user_id,
            guild_id,
            channel_id,
        )

    def fifo_path(self, attempt: OAuthAttempt) -> Path:
        return self.store.path.parent / f"{attempt.attempt_id}.fifo"

    def result_path(self, attempt: OAuthAttempt) -> Path:
        return self.store.path.parent / f"{attempt.attempt_id}.result.json"

    def start(self, attempt_id: str) -> OAuthAttempt:
        attempt = self.store.get(attempt_id)
        if attempt is None:
            raise KeyError(attempt_id)
        now = float(self.store.clock())
        if attempt.status != "pending" or now >= attempt.expires_at:
            raise ValueError("attempt is not startable")
        unit = f"agk-account-oauth-{attempt.attempt_id}.service"
        reserved = self.store.transition(
            attempt_id, {"pending"}, status="starting", runner_unit=unit
        )
        if reserved is None:
            raise ValueError("attempt is not startable")
        remaining = max(0.001, reserved.expires_at - float(self.store.clock()))
        argv = [
            "systemd-run",
            "--user",
            "--unit",
            unit,
            "--collect",
            "--quiet",
            "--property",
            f"RuntimeMaxSec={remaining:.3f}s",
            sys.executable,
            str(self.runner_script),
            "--provider",
            reserved.provider,
            "--alias",
            reserved.owner_name,
            "--fifo",
            str(self.fifo_path(reserved)),
            "--state",
            str(self.result_path(reserved)),
            "--timeout",
            str(_TIMEOUT_SECONDS),
            "--deadline",
            repr(reserved.expires_at),
        ]
        returncode = self.systemd(argv)
        if returncode != 0:
            terminal = self.store.transition(
                attempt_id, {"starting"}, status="failed", runner_unit=""
            ) or self.store.transition(
                attempt_id, {"cancelling"}, status="cancelled", runner_unit=""
            )
            if terminal is not None:
                self._cleanup(terminal)
            raise RuntimeError("OAuth sibling unit failed to start")
        started = self.store.transition(
            attempt_id, {"starting"}, status="running", runner_unit=unit
        )
        if started is None:
            stopped = self._stop_unit(unit)
            if stopped:
                self.store.transition(
                    attempt_id, {"cancelling"}, status="cancelled"
                )
                self._cleanup(reserved)
            raise ValueError("attempt was cancelled while starting")
        return started

    def submit_claude_code(
        self, attempt_id: str, code: str, *, user_id: int, channel_id: int
    ) -> bool:
        value = str(code)
        payload = (value + "\n").encode("utf-8")
        if (
            not value
            or "\n" in value
            or "\r" in value
            or len(payload) > select.PIPE_BUF
        ):
            return False
        reservation = self.store.reserve_submission(
            attempt_id, user_id=int(user_id), channel_id=int(channel_id)
        )
        if reservation is None:
            return False
        attempt, previous_status = reservation
        try:
            written = self._fifo_writer(self.fifo_path(attempt), value + "\n")
        except OSError:
            self.store.transition(
                attempt_id, {"submitting"}, status=previous_status
            )
            return False
        if written != len(payload):
            self.store.transition(
                attempt_id, {"submitting"}, status=previous_status
            )
            return False
        submitted = self.store.transition(
            attempt_id, {"submitting"}, status="code-submitted"
        )
        return submitted is not None

    def cancel(self, attempt_id: str) -> bool:
        attempt = self.store.get(attempt_id)
        if attempt is None:
            return False
        if attempt.status in _TERMINAL_STATUSES:
            return attempt.status == "cancelled"
        previous_status = attempt.status
        if attempt.runner_unit:
            expected = f"agk-account-oauth-{attempt.attempt_id}.service"
            if attempt.runner_unit != expected:
                raise ValueError("invalid recorded runner unit")
            reserved = self.store.transition(
                attempt_id, _LIVE_STATUSES, status="cancelling"
            )
            if reserved is None:
                return False
            if not self._stop_unit(attempt.runner_unit):
                if previous_status != "starting":
                    self.store.transition(
                        attempt_id, {"cancelling"}, status=previous_status
                    )
                return False
            cancelled = self.store.transition(
                attempt_id, {"cancelling"}, status="cancelled"
            )
            if cancelled is None:
                return False
        else:
            cancelled = self.store.transition(
                attempt_id, _LIVE_STATUSES, status="cancelled"
            )
            if cancelled is None:
                return False
        self._cleanup(attempt)
        return True

    def _stop_unit(self, unit: str) -> bool:
        if self.systemd(["systemctl", "--user", "stop", unit]) != 0:
            return False
        activity = self.systemd(
            ["systemctl", "--user", "is-active", "--quiet", unit]
        )
        if activity not in _SYSTEMCTL_INACTIVE_CODES:
            return False
        self.systemd(["systemctl", "--user", "reset-failed", unit])
        return True

    def _cleanup(self, attempt: OAuthAttempt) -> None:
        for path in (
            self.fifo_path(attempt),
            self.result_path(attempt),
            self.result_path(attempt).with_suffix(".raw.log"),
        ):
            path.unlink(missing_ok=True)

    @staticmethod
    def _write_fifo(path: Path, value: str) -> int:
        descriptor = os.open(
            path,
            os.O_WRONLY | os.O_NONBLOCK | getattr(os, "O_NOFOLLOW", 0),
        )
        try:
            if not stat.S_ISFIFO(os.fstat(descriptor).st_mode):
                raise OSError("OAuth input path is not a FIFO")
            payload = value.encode("utf-8")
            written = os.write(descriptor, payload)
            if written != len(payload):
                raise BlockingIOError("partial OAuth FIFO write")
            return written
        finally:
            os.close(descriptor)
