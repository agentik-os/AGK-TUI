import hashlib
import importlib.util
import json
import stat
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "hermes/plugins/platforms/discord/agk_account_transactions.py"


def load_transactions():
    assert MODULE.exists(), "transaction coordinator does not exist"
    spec = importlib.util.spec_from_file_location("agk_account_transactions", MODULE)
    assert spec and spec.loader
    loaded = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = loaded
    spec.loader.exec_module(loaded)
    return loaded


class FakeStore:
    def __init__(self, home: Path, attempt):
        self.path = home / "state/account-oauth/attempts.json"
        self.attempt = attempt

    def get(self, attempt_id):
        return self.attempt if attempt_id == self.attempt.attempt_id else None


class FakeAliasRegistry:
    def __init__(self, path: Path, events: list[str]):
        self.path = path
        self.events = events
        self.values = {"openai-codex": {"old123": "Agentik", "keep456": "Simono"}}
        self.fail_bind = False

    def snapshot(self):
        return {provider: dict(rows) for provider, rows in self.values.items()}

    def replace(self, values):
        self.values = {provider: dict(rows) for provider, rows in values.items()}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.values), encoding="utf-8")
        self.path.chmod(0o600)

    def bind(self, provider, owner_name, credential_id):
        self.events.append("bind-nickname")
        if self.fail_bind:
            raise OSError("registry write failed")
        rows = self.values.setdefault(provider, {})
        rows = {key: value for key, value in rows.items() if value.casefold() != owner_name.casefold()}
        rows[credential_id] = owner_name
        self.values[provider] = rows


class Fakes:
    def __init__(self, tmp_path: Path, *, operation="reconnect"):
        self.events = []
        self.probe_ok = True
        self.remove_old_ok = True
        self.remove_candidate_ok = True
        self.refresh_ok = True
        self.pool_ids = ["old123", "keep456", "new789"]
        self.attempt = SimpleNamespace(
            attempt_id="attempt-1",
            provider="openai-codex",
            operation=operation,
            owner_name="Agentik",
            target_credential_id="old123" if operation == "reconnect" else None,
            status="succeeded",
        )
        self.store = FakeStore(tmp_path, self.attempt)
        self.registry = FakeAliasRegistry(tmp_path / "provider-account-aliases.json", self.events)
        for name, value in (("auth.json", "private-auth"), ("config.yaml", "model: test\n")):
            (tmp_path / name).write_text(value, encoding="utf-8")
        self.registry.path.write_text("aliases-before", encoding="utf-8")
        self.registry.path.chmod(0o600)

    def pool_reader(self, provider):
        if "bind-nickname" not in self.events:
            self.events.append("discover-candidate")
        elif "remove-old" not in self.events:
            self.events.append("read-pool")
        else:
            self.events.append("read-final-pool")
        return [SimpleNamespace(id=value) for value in self.pool_ids]

    def probe(self, provider, entry):
        self.events.append("probe-candidate")
        return self.probe_ok

    def usage(self, provider, entry):
        self.events.append("usage-candidate")
        return {"availability": "available"}

    def remove(self, provider, credential_id):
        event = "remove-old" if credential_id == "old123" else "remove-candidate"
        self.events.append(event)
        if credential_id == "old123" and not self.remove_old_ok:
            return False
        if credential_id == "new789" and not self.remove_candidate_ok:
            return False
        self.pool_ids.remove(credential_id)
        return True

    def refresh(self):
        self.events.append("refresh-surfaces")
        if not self.refresh_ok:
            raise RuntimeError("presentation failed")


def coordinator(tmp_path, fakes):
    transactions = load_transactions()
    return transactions.AccountTransactionCoordinator(
        tmp_path,
        fakes.store,
        fakes.registry,
        pool_reader=fakes.pool_reader,
        pre_pool_ids=lambda _attempt: {"old123", "keep456"},
        probe_candidate=fakes.probe,
        fetch_usage=fakes.usage,
        remove_credential=fakes.remove,
        refresh_surfaces=fakes.refresh,
        backup_observer=lambda: fakes.events.append("backup"),
    )


def test_reconnect_verifies_candidate_before_removing_old(tmp_path):
    fakes = Fakes(tmp_path)

    result = coordinator(tmp_path, fakes).finalize("attempt-1")

    assert fakes.events == [
        "backup", "discover-candidate", "probe-candidate", "usage-candidate",
        "bind-nickname", "read-pool", "remove-old", "read-final-pool", "refresh-surfaces",
    ]
    assert result.status == "committed"
    assert result.old_credential_id == "old123"
    assert result.new_credential_id == "new789"


def test_failed_candidate_probe_preserves_old_credential(tmp_path):
    fakes = Fakes(tmp_path)
    fakes.probe_ok = False

    result = coordinator(tmp_path, fakes).finalize("attempt-1")

    assert "remove-old" not in fakes.events
    assert "old123" in fakes.pool_ids
    assert result.status == "rolled_back"


def test_backup_is_private_complete_and_checksummed_before_discovery(tmp_path):
    fakes = Fakes(tmp_path)

    result = coordinator(tmp_path, fakes).finalize("attempt-1")

    assert result.status == "committed"
    backups = list((tmp_path / "state/account-transactions/backups").iterdir())
    assert len(backups) == 1
    backup = backups[0]
    assert stat.S_IMODE(backup.stat().st_mode) == 0o700
    manifest_path = backup / "SHA256SUMS.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))["sha256"]
    assert set(manifest) == {"auth.json", "config.yaml", "provider-account-aliases.json"}
    for name, digest in manifest.items():
        copied = backup / name
        assert stat.S_IMODE(copied.stat().st_mode) == 0o600
        assert hashlib.sha256(copied.read_bytes()).hexdigest() == digest
    assert stat.S_IMODE(manifest_path.stat().st_mode) == 0o600


def test_registry_write_failure_restores_aliases_and_removes_only_candidate(tmp_path):
    fakes = Fakes(tmp_path)
    original = fakes.registry.snapshot()
    fakes.registry.fail_bind = True

    result = coordinator(tmp_path, fakes).finalize("attempt-1")

    assert result.status == "rolled_back"
    assert fakes.registry.snapshot() == original
    assert "old123" in fakes.pool_ids and "new789" not in fakes.pool_ids
    assert "remove-old" not in fakes.events


def test_candidate_cleanup_failure_requires_reconciliation(tmp_path):
    fakes = Fakes(tmp_path)
    fakes.probe_ok = False
    fakes.remove_candidate_ok = False

    result = coordinator(tmp_path, fakes).finalize("attempt-1")

    assert result.status == "reconciliation_required"
    assert "new789" in fakes.pool_ids and "old123" in fakes.pool_ids
    assert "remove-old" not in fakes.events


def test_old_removal_failure_retains_both_and_never_fabricates_success(tmp_path):
    fakes = Fakes(tmp_path)
    fakes.remove_old_ok = False

    result = coordinator(tmp_path, fakes).finalize("attempt-1")

    assert result.status == "reconciliation_required"
    assert {"old123", "new789"}.issubset(fakes.pool_ids)
    assert "refresh-surfaces" not in fakes.events


def test_duplicate_candidate_ids_are_not_committed(tmp_path):
    fakes = Fakes(tmp_path)
    fakes.pool_ids.append("new789")

    result = coordinator(tmp_path, fakes).finalize("attempt-1")

    assert result.status == "reconciliation_required"
    assert "remove-old" not in fakes.events


def test_post_commit_refresh_failure_preserves_pool_and_marks_presentation_pending(tmp_path):
    fakes = Fakes(tmp_path)
    fakes.refresh_ok = False

    result = coordinator(tmp_path, fakes).finalize("attempt-1")

    assert result.status == "presentation_reconciliation_pending"
    assert "new789" in fakes.pool_ids and "old123" not in fakes.pool_ids


def test_add_commits_one_candidate_without_removing_existing_credentials(tmp_path):
    fakes = Fakes(tmp_path, operation="add")
    fakes.attempt.owner_name = "Loumna"

    result = coordinator(tmp_path, fakes).finalize("attempt-1")

    assert result.status == "committed"
    assert result.old_credential_id is None
    assert set(fakes.pool_ids) == {"old123", "keep456", "new789"}
    assert "remove-old" not in fakes.events


def test_usage_failure_is_recorded_as_unavailable_without_blocking_commit(tmp_path):
    fakes = Fakes(tmp_path)

    def unavailable(provider, entry):
        fakes.events.append("usage-candidate")
        raise RuntimeError("provider usage unavailable")

    fakes.usage = unavailable

    result = coordinator(tmp_path, fakes).finalize("attempt-1")

    assert result.status == "committed"
    assert "usage unavailable" in result.message.casefold()


def test_terminal_paths_remove_oauth_artifacts_without_retaining_credentials(tmp_path):
    fakes = Fakes(tmp_path)
    fakes.probe_ok = False
    artifacts = [
        fakes.store.path.parent / "attempt-1.fifo",
        fakes.store.path.parent / "attempt-1.result.json",
        fakes.store.path.parent / "attempt-1.result.raw.log",
    ]
    fakes.store.path.parent.mkdir(parents=True, exist_ok=True)
    for artifact in artifacts:
        artifact.write_text("private material", encoding="utf-8")

    result = coordinator(tmp_path, fakes).finalize("attempt-1")

    assert result.status == "rolled_back"
    assert all(not artifact.exists() for artifact in artifacts)
