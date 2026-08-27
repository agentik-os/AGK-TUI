"""Transactional finalization for Station account add and reconnect flows.

The coordinator deliberately accepts pool, probe, removal, usage, and refresh
callables.  This keeps credential material inside the canonical Hermes seams and
lets ordering and failure handling be verified without mutating live accounts.
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
import shutil
import stat
import tempfile
import time
from collections import Counter
from collections.abc import Callable, Iterable, Iterator
from contextlib import contextmanager
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
        attempt_store: OAuthAttemptStore,
        alias_registry: AliasRegistry | None = None,
        *,
        pool_reader: Callable[[str], Iterable[Any]] | None = None,
        pre_pool_ids: Callable[[Any], Iterable[str]],
        probe_candidate: Callable[[str, Any], bool],
        fetch_usage: Callable[[str, Any], Any] | None = None,
        remove_credential: Callable[[str, str], bool] | None = None,
        refresh_surfaces: Callable[[], Any],
        backup_observer: Callable[[], Any] | None = None,
        artifact_remover: Callable[[Path], Any] | None = None,
    ):
        self.hermes_home = Path(hermes_home)
        self.attempt_store = attempt_store
        if alias_registry is None:
            from hermes.plugins.platforms.discord.agk_account_control import (
                AliasRegistry,
            )

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
        self.artifact_remover = artifact_remover or self._remove_artifact

    def finalize(self, attempt_id: str) -> TransactionResult:
        """Serialize, claim, and durably memoize one transaction outcome.

        Lock ordering is transaction lock -> attempt-store lock -> alias/pool
        operations.  No attempt-store lock is held while credential seams run.
        """
        try:
            stable_attempt_id = self._stable_id(attempt_id)
        except ValueError:
            return self._result(
                "rolled_back", None, None, None, None, "OAuth attempt is unavailable."
            )

        with self._transaction_lock():
            try:
                state = self._read_transaction_state(stable_attempt_id)
            except Exception:  # noqa: BLE001 - injected seams expose no stable error base.
                return self._result(
                    "reconciliation_required", None, None, None, None,
                    "Transaction state requires reconciliation.",
                )

            if state is not None:
                try:
                    replay = self._result_from_state(state)
                except Exception:  # noqa: BLE001 - private state may be malformed.
                    return self._result(
                        "reconciliation_required", None, None, None, None,
                        "Transaction state requires reconciliation.",
                    )
                if replay is not None:
                    cleanup_ok = self._cleanup_oauth_artifacts(stable_attempt_id)
                    replay = self._apply_cleanup_result(replay, cleanup_ok)
                    try:
                        self._write_terminal_state(stable_attempt_id, replay)
                    except Exception:  # noqa: BLE001 - atomic persistence seam.
                        return self._persistence_reconciliation(replay)
                    return replay
                if state.get("phase") == "irreversible":
                    replay = self._result(
                        "reconciliation_required",
                        state.get("provider"),
                        state.get("owner_name"),
                        state.get("old_credential_id"),
                        state.get("new_credential_id"),
                        "Canonical credential state requires reconciliation.",
                    )
                    cleanup_ok = self._cleanup_oauth_artifacts(stable_attempt_id)
                    replay = self._apply_cleanup_result(replay, cleanup_ok)
                    try:
                        self._write_terminal_state(stable_attempt_id, replay)
                    except Exception:  # noqa: BLE001 - atomic persistence seam.
                        return self._persistence_reconciliation(replay)
                    return replay
                return self._result(
                    "reconciliation_required", None, None, None, None,
                    "Transaction state requires reconciliation.",
                )

            result = self._finalize_locked(stable_attempt_id)
            cleanup_ok = self._cleanup_oauth_artifacts(stable_attempt_id)
            result = self._apply_cleanup_result(result, cleanup_ok)
            try:
                self._write_terminal_state(stable_attempt_id, result)
            except Exception:  # noqa: BLE001 - injected seams expose no stable error base.
                return self._persistence_reconciliation(result)
            return result

    def _finalize_locked(self, attempt_id: str) -> TransactionResult:
        attempt = self.attempt_store.get(attempt_id)
        if attempt is None:
            return self._result("rolled_back", None, None, None, None, "OAuth attempt is unavailable.")
        provider = attempt.provider
        owner_name = attempt.owner_name
        old_id = attempt.target_credential_id if attempt.operation == "reconnect" else None
        candidate_id: str | None = None
        aliases_before = self.alias_registry.snapshot()
        committed = False
        irreversible = False

        if attempt.status != "succeeded":
            return self._result(
                "rolled_back", provider, owner_name, old_id, None,
                "OAuth attempt did not complete successfully.",
            )
        if (
            attempt.operation not in {"add", "reconnect"}
            or (attempt.operation == "add" and attempt.target_credential_id is not None)
            or (attempt.operation == "reconnect" and old_id is None)
        ):
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
            expected_with_candidate = Counter(before_ids)
            expected_with_candidate[candidate_id] += 1
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
            except Exception:  # noqa: BLE001 - provider clients have no stable error base.
                usage_unavailable = True

            try:
                self.alias_registry.bind(provider, owner_name, candidate_id)
            except Exception:  # noqa: BLE001 - injected seams expose no stable error base.
                return self._rollback(
                    attempt, aliases_before, candidate_id,
                    "Nickname registry update failed.",
                )

            rebound_pool = list(self.pool_reader(provider))
            rebound_ids = [self._entry_id(entry) for entry in rebound_pool]
            if Counter(rebound_ids) != expected_with_candidate:
                return self._rollback(
                    attempt, aliases_before, candidate_id,
                    "Candidate pool reconciliation failed.",
                )

            if old_id is not None:
                # Calling canonical removal crosses an irreversible boundary:
                # the seam may mutate successfully and then fail to report it.
                # No exception after this point may clean up the candidate.
                irreversible = True
                self._write_transaction_state(
                    attempt_id,
                    {
                        "version": 1,
                        "phase": "irreversible",
                        "provider": provider,
                        "owner_name": owner_name,
                        "old_credential_id": old_id,
                        "new_credential_id": candidate_id,
                    },
                )
                try:
                    removed = bool(self.remove_credential(provider, old_id))
                except Exception:  # noqa: BLE001 - injected seams expose no stable error base.
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
            expected_final = expected_with_candidate.copy()
            if old_id is not None:
                expected_final[old_id] -= 1
                if not expected_final[old_id]:
                    del expected_final[old_id]
            if Counter(final_ids) != expected_final:
                return self._result(
                    "reconciliation_required", provider, owner_name, old_id, candidate_id,
                    "Canonical pool reconciliation is required.",
                )
            committed = True

            try:
                self.refresh_surfaces()
            except Exception:  # noqa: BLE001 - injected seams expose no stable error base.
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
        except Exception:  # noqa: BLE001 - injected seams expose no stable error base.
            if committed:
                return self._result(
                    "presentation_reconciliation_pending", provider, owner_name,
                    old_id, candidate_id,
                    "Credential change committed; presentation refresh is pending.",
                )
            if irreversible:
                return self._result(
                    "reconciliation_required", provider, owner_name,
                    old_id, candidate_id,
                    "Canonical credential state requires reconciliation.",
                )
            return self._rollback(
                attempt, aliases_before, candidate_id,
                "Transaction rolled back safely.",
            )

    def _rollback(self, attempt, aliases_before, candidate_id, message) -> TransactionResult:
        clean = True
        try:
            self.alias_registry.replace(aliases_before)
        except Exception:  # noqa: BLE001 - injected seams expose no stable error base.
            clean = False
        if candidate_id is not None:
            try:
                removed = bool(self.remove_credential(attempt.provider, candidate_id))
                remaining = [
                    self._entry_id(entry) for entry in self.pool_reader(attempt.provider)
                ]
                clean = removed and candidate_id not in remaining and clean
            except Exception:  # noqa: BLE001 - injected seams expose no stable error base.
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
        from hermes_constants import (
            reset_hermes_home_override,
            set_hermes_home_override,
        )

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
        from hermes_constants import (
            reset_hermes_home_override,
            set_hermes_home_override,
        )

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
                except Exception:  # noqa: BLE001 - injected seams expose no stable error base.
                    try:
                        suppress_credential_source(provider, removed.source)
                    except Exception:  # noqa: BLE001, S110 - final readback detects it.
                        # The pool row is already gone; reconciliation detects
                        # any source resurrection without exposing provider data.
                        pass
            return True
        finally:
            reset_hermes_home_override(token)

    @property
    def _transaction_dir(self) -> Path:
        return self.hermes_home / "state/account-transactions"

    @contextmanager
    def _transaction_lock(self) -> Iterator[None]:
        directory = self._transaction_dir
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        directory.chmod(0o700)
        lock_path = directory / ".finalize.lock"
        descriptor = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o600)
        try:
            os.fchmod(descriptor, 0o600)
            fcntl.flock(descriptor, fcntl.LOCK_EX)
            yield
        finally:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
            os.close(descriptor)

    def _transaction_state_path(self, attempt_id: str) -> Path:
        return self._transaction_dir / f"{self._stable_id(attempt_id)}.json"

    def _read_transaction_state(self, attempt_id: str) -> dict[str, Any] | None:
        path = self._transaction_state_path(attempt_id)
        try:
            descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        except FileNotFoundError:
            return None
        try:
            metadata = os.fstat(descriptor)
            if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > 16_384:
                raise ValueError("invalid transaction state")
            with os.fdopen(descriptor, encoding="utf-8") as handle:
                descriptor = -1
                payload = json.load(handle)
        finally:
            if descriptor >= 0:
                os.close(descriptor)
        if not isinstance(payload, dict) or payload.get("version") != 1:
            raise ValueError("invalid transaction state")
        return payload

    def _write_transaction_state(self, attempt_id: str, payload: dict[str, Any]) -> None:
        directory = self._transaction_dir
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        directory.chmod(0o700)
        destination = self._transaction_state_path(attempt_id)
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{destination.name}.", suffix=".new", dir=directory
        )
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, indent=2, sort_keys=True)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            temporary.chmod(0o600)
            os.replace(temporary, destination)
            destination.chmod(0o600)
            directory_descriptor = os.open(directory, os.O_RDONLY)
            try:
                os.fsync(directory_descriptor)
            finally:
                os.close(directory_descriptor)
        finally:
            temporary.unlink(missing_ok=True)

    def _write_terminal_state(self, attempt_id: str, result: TransactionResult) -> None:
        self._write_transaction_state(
            attempt_id,
            {
                "version": 1,
                "phase": "terminal",
                "result": {
                    "status": result.status,
                    "provider": result.provider,
                    "owner_name": result.owner_name,
                    "old_credential_id": result.old_credential_id,
                    "new_credential_id": result.new_credential_id,
                    "message": result.message,
                },
            },
        )

    def _result_from_state(self, state: dict[str, Any]) -> TransactionResult | None:
        if state.get("phase") != "terminal" or not isinstance(state.get("result"), dict):
            return None
        payload = state["result"]
        if payload.get("status") not in {
            "committed",
            "rolled_back",
            "reconciliation_required",
            "presentation_reconciliation_pending",
        }:
            raise ValueError("invalid transaction result")
        old_id = payload.get("old_credential_id")
        new_id = payload.get("new_credential_id")
        if old_id is not None:
            old_id = self._stable_id(old_id)
        if new_id is not None:
            new_id = self._stable_id(new_id)
        return self._result(
            payload["status"],
            str(payload.get("provider") or ""),
            str(payload.get("owner_name") or ""),
            old_id,
            new_id,
            str(payload.get("message") or ""),
        )

    @staticmethod
    def _remove_artifact(path: Path) -> None:
        if path.is_dir() and not path.is_symlink():
            shutil.rmtree(path)
        else:
            path.unlink(missing_ok=True)

    def _cleanup_oauth_artifacts(self, attempt_id: str) -> bool:
        parent = self.attempt_store.path.parent
        clean = True
        paths = [parent / f"{attempt_id}{suffix}" for suffix in (
            ".fifo", ".result.json", ".result.raw.log"
        )]
        for path in paths:
            try:
                self.artifact_remover(path)
            except OSError:
                clean = False
        return clean and all(not os.path.lexists(path) for path in paths)

    def _persistence_reconciliation(self, result: TransactionResult) -> TransactionResult:
        return self._result(
            "reconciliation_required",
            result.provider,
            result.owner_name,
            result.old_credential_id,
            result.new_credential_id,
            "Transaction outcome persistence requires reconciliation.",
        )

    def _apply_cleanup_result(
        self, result: TransactionResult, cleanup_ok: bool
    ) -> TransactionResult:
        if cleanup_ok:
            return result
        if result.status == "reconciliation_required":
            return self._result(
                result.status, result.provider, result.owner_name,
                result.old_credential_id, result.new_credential_id,
                "Credential state and OAuth artifact cleanup require reconciliation.",
            )
        return self._result(
            "presentation_reconciliation_pending",
            result.provider,
            result.owner_name,
            result.old_credential_id,
            result.new_credential_id,
            "Credential state finalized; OAuth artifact security cleanup is pending.",
        )

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
