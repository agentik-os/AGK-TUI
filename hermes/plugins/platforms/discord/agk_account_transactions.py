"""Transactional finalization for Station account add and reconnect flows.

The coordinator deliberately accepts pool, probe, removal, usage, and refresh
callables.  This keeps credential material inside the canonical Hermes seams and
lets ordering and failure handling be verified without mutating live accounts.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import stat
import time
from collections import Counter
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from hermes.plugins.platforms.discord.agk_account_control import AliasRegistry
    from hermes.plugins.platforms.discord.agk_account_oauth import OAuthAttemptStore

_SAFE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}\Z")


@dataclass(frozen=True)
class TransactionResult:
    status: str
    provider: str
    owner_name: str
    old_credential_id: str | None
    new_credential_id: str | None
    message: str


class AccountTransactionCoordinator:
    """Finalize one successful OAuth attempt without risking the old account."""

    def __init__(
        self,
        hermes_home: Path,
        attempt_store: "OAuthAttemptStore",
        alias_registry: "AliasRegistry | None" = None,
        *,
        pool_reader: Callable[[str], Iterable[Any]] | None = None,
        pre_pool_ids: Callable[[Any], Iterable[str]],
        probe_candidate: Callable[[str, Any], bool],
        fetch_usage: Callable[[str, Any], Any] | None = None,
        remove_credential: Callable[[str, str], bool] | None = None,
        refresh_surfaces: Callable[[], Any],
        backup_observer: Callable[[], Any] | None = None,
    ):
        self.hermes_home = Path(hermes_home)
        self.attempt_store = attempt_store
        if alias_registry is None:
            from hermes.plugins.platforms.discord.agk_account_control import AliasRegistry

            alias_registry = AliasRegistry(self.hermes_home / "provider-account-aliases.json")
        self.alias_registry = alias_registry
        self.pool_reader = pool_reader or self._read_pool
        # The OAuth initiator must supply its immutable pre-OAuth pool-ID
        # snapshot. Inferring it from aliases would be unsafe when an existing
        # canonical credential has not been named yet.
        self.pre_pool_ids = pre_pool_ids
        self.probe_candidate = probe_candidate
        self.fetch_usage = fetch_usage or self._fetch_usage
        self.remove_credential = remove_credential or self._remove_credential
        self.refresh_surfaces = refresh_surfaces
        self.backup_observer = backup_observer

    def finalize(self, attempt_id: str) -> TransactionResult:
        attempt = self.attempt_store.get(attempt_id)
        if attempt is None:
            return self._result("rolled_back", None, None, None, None, "OAuth attempt is unavailable.")
        provider = attempt.provider
        owner_name = attempt.owner_name
        old_id = attempt.target_credential_id if attempt.operation == "reconnect" else None
        candidate_id: str | None = None
        aliases_before = self.alias_registry.snapshot()
        committed = False

        if attempt.status != "succeeded":
            self._cleanup_oauth_artifacts(attempt_id)
            return self._result(
                "rolled_back", provider, owner_name, old_id, None,
                "OAuth attempt did not complete successfully.",
            )
        if (
            attempt.operation not in {"add", "reconnect"}
            or (attempt.operation == "add" and attempt.target_credential_id is not None)
            or (attempt.operation == "reconnect" and old_id is None)
        ):
            self._cleanup_oauth_artifacts(attempt_id)
            return self._result(
                "rolled_back", provider, owner_name, old_id, None,
                "OAuth attempt metadata is invalid.",
            )

        try:
            self._create_backup(attempt_id)
            if self.backup_observer is not None:
                self.backup_observer()

            before_ids = tuple(self._stable_id(value) for value in self.pre_pool_ids(attempt))
            if len(set(before_ids)) != len(before_ids) or (old_id and old_id not in before_ids):
                return self._result(
                    "reconciliation_required", provider, owner_name, old_id, None,
                    "Pre-OAuth pool snapshot requires canonical reconciliation.",
                )
            pool = list(self.pool_reader(provider))
            post_ids = [self._entry_id(entry) for entry in pool]
            candidate_ids = set(post_ids) - set(before_ids)
            if len(candidate_ids) != 1:
                if candidate_ids:
                    return self._result(
                        "reconciliation_required", provider, owner_name, old_id, None,
                        "Candidate credentials require canonical reconciliation.",
                    )
                return self._rollback(
                    attempt, aliases_before, None,
                    "Candidate credential could not be uniquely discovered.",
                )
            candidate_id = next(iter(candidate_ids))
            if post_ids.count(candidate_id) != 1:
                return self._rollback(
                    attempt, aliases_before, candidate_id,
                    "Candidate credential appeared more than once.",
                )
            candidate = next(entry for entry in pool if self._entry_id(entry) == candidate_id)

            if not bool(self.probe_candidate(provider, candidate)):
                return self._rollback(
                    attempt, aliases_before, candidate_id,
                    "Candidate credential verification failed.",
                )

            # Usage is an observational gate: provider-side usage may be
            # unavailable even though exact-credential inference succeeded.
            try:
                usage_result = self.fetch_usage(provider, candidate)
                usage_unavailable = usage_result is None or usage_result == "unavailable"
                del usage_result
            except Exception:  # provider clients expose no stable base error
                usage_unavailable = True

            try:
                self.alias_registry.bind(provider, owner_name, candidate_id)
            except Exception:
                return self._rollback(
                    attempt, aliases_before, candidate_id,
                    "Nickname registry update failed.",
                )

            rebound_pool = list(self.pool_reader(provider))
            rebound_ids = [self._entry_id(entry) for entry in rebound_pool]
            if rebound_ids.count(candidate_id) != 1 or (old_id and rebound_ids.count(old_id) != 1):
                return self._rollback(
                    attempt, aliases_before, candidate_id,
                    "Candidate pool reconciliation failed.",
                )

            if old_id is not None:
                try:
                    removed = bool(self.remove_credential(provider, old_id))
                except Exception:
                    removed = False
                if not removed:
                    retained_ids = [
                        self._entry_id(entry) for entry in self.pool_reader(provider)
                    ]
                    both_retained = (
                        retained_ids.count(old_id) == 1
                        and retained_ids.count(candidate_id) == 1
                    )
                    return self._result(
                        "reconciliation_required", provider, owner_name, old_id, candidate_id,
                        (
                            "Both credentials were retained; canonical reconciliation is required."
                            if both_retained
                            else "Canonical credential state requires reconciliation."
                        ),
                    )

            final_pool = list(self.pool_reader(provider))
            final_ids = [self._entry_id(entry) for entry in final_pool]
            expected_count = len(before_ids) + (1 if old_id is None else 0)
            final_ok = (
                final_ids.count(candidate_id) == 1
                and (old_id is None or old_id not in final_ids)
                and len(final_ids) == expected_count
            )
            if not final_ok:
                return self._result(
                    "reconciliation_required", provider, owner_name, old_id, candidate_id,
                    "Canonical pool reconciliation is required.",
                )
            committed = True

            try:
                self.refresh_surfaces()
            except Exception:
                return self._result(
                    "presentation_reconciliation_pending", provider, owner_name,
                    old_id, candidate_id,
                    "Credential change committed; presentation refresh is pending.",
                )
            return self._result(
                "committed", provider, owner_name, old_id, candidate_id,
                (
                    "Credential change committed; usage unavailable."
                    if usage_unavailable
                    else "Credential change committed."
                ),
            )
        except Exception:
            if committed:
                return self._result(
                    "presentation_reconciliation_pending", provider, owner_name,
                    old_id, candidate_id,
                    "Credential change committed; presentation refresh is pending.",
                )
            return self._rollback(
                attempt, aliases_before, candidate_id,
                "Transaction rolled back safely.",
            )
        finally:
            self._cleanup_oauth_artifacts(attempt_id)

    def _rollback(self, attempt, aliases_before, candidate_id, message) -> TransactionResult:
        clean = True
        try:
            self.alias_registry.replace(aliases_before)
        except Exception:
            clean = False
        if candidate_id is not None:
            try:
                removed = bool(self.remove_credential(attempt.provider, candidate_id))
                remaining = [
                    self._entry_id(entry) for entry in self.pool_reader(attempt.provider)
                ]
                clean = removed and candidate_id not in remaining and clean
            except Exception:
                clean = False
        status = "rolled_back" if clean else "reconciliation_required"
        safe_message = message if clean else "Candidate cleanup requires canonical reconciliation."
        old_id = attempt.target_credential_id if attempt.operation == "reconnect" else None
        return self._result(
            status, attempt.provider, attempt.owner_name, old_id, candidate_id, safe_message
        )

    def _create_backup(self, attempt_id: str) -> Path:
        attempt_id = self._stable_id(attempt_id)
        backup = (
            self.hermes_home / "state/account-transactions/backups"
            / f"{time.time_ns()}-{attempt_id}"
        )
        backup.mkdir(mode=0o700, parents=True, exist_ok=False)
        backup.chmod(0o700)
        sources = (
            ("auth.json", self.hermes_home / "auth.json"),
            ("config.yaml", self.hermes_home / "config.yaml"),
            ("provider-account-aliases.json", self.alias_registry.path),
        )
        manifest: dict[str, str] = {}
        for name, source in sources:
            target = backup / name
            data = self._read_backup_source(source)
            descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            target.chmod(0o600)
            manifest[name] = hashlib.sha256(data).hexdigest()
        payload = (json.dumps({"sha256": manifest}, indent=2, sort_keys=True) + "\n").encode()
        manifest_path = backup / "SHA256SUMS.json"
        descriptor = os.open(manifest_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        manifest_path.chmod(0o600)
        return backup

    @staticmethod
    def _read_backup_source(path: Path) -> bytes:
        try:
            descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        except FileNotFoundError:
            return b""
        try:
            metadata = os.fstat(descriptor)
            if not stat.S_ISREG(metadata.st_mode):
                raise ValueError("backup source must be a regular file")
            with os.fdopen(descriptor, "rb") as handle:
                descriptor = -1
                return handle.read()
        finally:
            if descriptor >= 0:
                os.close(descriptor)

    def _read_pool(self, provider: str) -> list[Any]:
        from agent.credential_pool import load_pool
        from hermes_constants import reset_hermes_home_override, set_hermes_home_override

        token = set_hermes_home_override(self.hermes_home)
        try:
            return load_pool(provider).entries()
        finally:
            reset_hermes_home_override(token)

    @staticmethod
    def _fetch_usage(provider: str, entry: Any) -> Any:
        from agent.account_usage import fetch_account_usage

        token = getattr(entry, "runtime_api_key", None) or getattr(entry, "access_token", None)
        if not token:
            return "unavailable"
        return fetch_account_usage(
            provider,
            base_url=getattr(entry, "base_url", None),
            api_key=token,
        )

    def _remove_credential(self, provider: str, credential_id: str) -> bool:
        from agent.credential_pool import load_pool
        from agent.credential_sources import find_removal_step
        from hermes_cli.auth import suppress_credential_source
        from hermes_constants import reset_hermes_home_override, set_hermes_home_override

        token = set_hermes_home_override(self.hermes_home)
        try:
            pool = load_pool(provider)
            entries = pool.entries()
            indexes = [index for index, entry in enumerate(entries, 1) if entry.id == credential_id]
            if len(indexes) != 1:
                return False
            removed = pool.remove_index(indexes[0])
            if removed is None:
                return False
            step = find_removal_step(provider, removed.source or "")
            if step is not None:
                try:
                    result = step.remove_fn(provider, removed)
                    if result.suppress:
                        suppress_credential_source(provider, removed.source)
                except Exception:
                    try:
                        suppress_credential_source(provider, removed.source)
                    except Exception:
                        # The pool row was already removed. Return success for
                        # that mutation and let the mandatory final live-pool
                        # reconciliation detect any source resurrection.
                        pass
            return True
        finally:
            reset_hermes_home_override(token)

    def _cleanup_oauth_artifacts(self, attempt_id: str) -> None:
        parent = self.attempt_store.path.parent
        for suffix in (".fifo", ".result.json", ".result.raw.log"):
            path = parent / f"{attempt_id}{suffix}"
            try:
                if path.is_dir():
                    shutil.rmtree(path)
                else:
                    path.unlink(missing_ok=True)
            except OSError:
                pass

    @staticmethod
    def _entry_id(entry: Any) -> str:
        return AccountTransactionCoordinator._stable_id(getattr(entry, "id", ""))

    @staticmethod
    def _stable_id(raw: Any) -> str:
        value = str(raw).strip()
        folded = value.casefold()
        if (
            not _SAFE_ID.fullmatch(value)
            or folded.startswith(("sk-", "xox", "bearer_"))
            or len(value) >= 48
        ):
            raise ValueError("pool entry has no stable credential ID")
        return value

    @staticmethod
    def _result(status, provider, owner_name, old_id, new_id, message) -> TransactionResult:
        return TransactionResult(status, provider or "", owner_name or "", old_id, new_id, message)
