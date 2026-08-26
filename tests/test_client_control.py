import hashlib
import hmac
import importlib.util
import json
import subprocess
import sys
from argparse import Namespace
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "agk_client_control", ROOT / "scripts" / "client_control.py"
)
assert SPEC and SPEC.loader
client_control = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = client_control
SPEC.loader.exec_module(client_control)


def init_args(slug="test-client", **overrides):
    values = {
        "slug": slug,
        "name": "Test Client",
        "runtime": "hybrid",
        "github_mode": "org",
        "github_org": "test-org",
        "linear_workspace": "workspace-id",
        "linear_team": "team-id",
        "discord_mode": "shared-command-center",
        "discord_guild": "123456789012345678",
        "dry_run": False,
    }
    values.update(overrides)
    return Namespace(**values)


@pytest.fixture
def layout(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("AGK_CLIENT_WORKSPACE", str(home / "workspace"))
    monkeypatch.setenv("AGK_TERMINAL_ROOT", str(ROOT))
    return client_control.Layout.current()


def declare_repository(layout, slug, repository="test-org/product"):
    path = layout.client(slug) / ".client" / "integrations.yaml"
    value = client_control.yaml_document(path)
    value["github"]["repositories"] = [repository]
    client_control.atomic_yaml(path, value)
    return repository


def make_work(layout, slug="test-client"):
    repository = declare_repository(layout, slug)
    return client_control.create_work(
        layout,
        Namespace(
            slug=slug,
            issue="FOU-142",
            title="Attachment classification",
            role="backend-engineer",
            provider="hermes",
            repo=repository,
            branch=None,
            session=None,
            target="staging",
        ),
    )


def test_bootstrap_is_safe_with_no_real_client(layout):
    client_control.bootstrap(layout, upgrade=True)

    assert client_control.load_registry(layout)["clients"] == []
    assert "NO LINEAR ISSUE" in (layout.system / "CLIENT-STANDARD.md").read_text(
        encoding="utf-8"
    )
    assert client_control.show_doctor(layout, None, online=False) == 0


def test_dry_run_makes_no_files_or_external_calls(layout, monkeypatch):
    monkeypatch.setattr(
        client_control.subprocess,
        "run",
        lambda *args, **kwargs: pytest.fail("dry-run attempted an external process"),
    )

    result = client_control.create_client(layout, init_args("dry-client", dry_run=True))

    assert result["dry_run"] is True
    assert result["external_actions"] == []
    assert not layout.workspace.exists()


def test_client_init_is_transactional_private_and_registered(layout):
    result = client_control.create_client(layout, init_args())
    root = layout.client("test-client")

    assert result["external_actions"] == []
    assert root.is_dir()
    assert (root.stat().st_mode & 0o077) == 0
    assert (layout.secret_file("test-client").stat().st_mode & 0o777) == 0o600
    assert client_control.load_registry(layout)["clients"][0]["id"] == "test-client"
    assert (root / ".client" / "workflow.yaml").is_file()
    assert (root / ".client" / "team.yaml").is_file()
    assert client_control.show_doctor(layout, "test-client", online=False) == 0

    with pytest.raises(client_control.ClientError, match="already exists"):
        client_control.create_client(layout, init_args())


def test_integration_plan_requires_client_scoped_composio_aliases(layout):
    client_control.create_client(layout, init_args())

    plan = client_control.integration_plan(layout, "test-client")

    aliases = {item["account_alias"] for item in plan["connections"]}
    assert aliases == {
        "client-test-client-linear",
        "client-test-client-github",
        "client-test-client-discordbot",
    }
    assert all("--alias" in item["command"] for item in plan["connections"])
    assert plan["external_writes"] is False


def test_no_linear_issue_or_unregistered_repository_means_no_work(layout):
    client_control.create_client(layout, init_args())
    args = Namespace(
        slug="test-client",
        issue="not-an-issue",
        title="Unsafe work",
        role="backend-engineer",
        provider="hermes",
        repo="test-org/product",
        branch=None,
        session=None,
        target="development",
    )

    with pytest.raises(client_control.ClientError, match="Linear issue"):
        client_control.create_work(layout, args)

    args.issue = "FOU-142"
    with pytest.raises(client_control.ClientError, match="not declared"):
        client_control.create_work(layout, args)
    assert not list((layout.client("test-client") / "state" / "work").iterdir())


def test_request_changes_preserves_the_exact_execution_context(layout):
    client_control.create_client(layout, init_args())
    work = make_work(layout)
    path, record = client_control.load_work(layout, "test-client", work["id"])
    original = {
        "session": record["agent"]["session"],
        "repo": record["repository"]["repo"],
        "branch": record["repository"]["branch"],
        "issue": record["linear"]["issue"],
    }
    record["status"] = "ready_for_cto"
    client_control.atomic_yaml(path, record)

    resumed = client_control.request_changes(
        layout,
        Namespace(
            slug="test-client",
            work_id=work["id"],
            feedback="Handle corrupted PDF files and expose retry.",
            actor="cto-user",
        ),
    )

    assert resumed["status"] == "in_progress"
    assert resumed["agent"]["session"] == original["session"]
    assert resumed["repository"]["repo"] == original["repo"]
    assert resumed["repository"]["branch"] == original["branch"]
    assert resumed["linear"]["issue"] == original["issue"]
    assert resumed["events"][-1]["resumed_context"]["session"] == original["session"]


def test_delivery_gates_separate_approval_deploy_and_run_evidence(layout):
    client_control.create_client(layout, init_args())
    work = make_work(layout)
    work_id = work["id"]
    for target in ("agent_review", "automated_qa"):
        client_control.transition_work(
            layout, "test-client", work_id, target, actor="backend-agent"
        )

    with pytest.raises(client_control.ClientError, match="evidence is incomplete"):
        client_control.transition_work(
            layout, "test-client", work_id, "ready_for_cto", actor="qa-agent"
        )

    client_control.update_evidence(
        layout,
        Namespace(
            slug="test-client",
            work_id=work_id,
            actor="qa-agent",
            pull_request="https://github.test/pr/284",
            commit="882ba43",
            ci="passed",
            qa="passed",
            security="passed",
            preview="https://staging.test/FOU-142",
            risk="low",
            production_health=None,
            linear_done=False,
        ),
    )
    client_control.transition_work(
        layout, "test-client", work_id, "ready_for_cto", actor="qa-agent"
    )
    approved = client_control.approve_work(
        layout,
        Namespace(
            slug="test-client",
            work_id=work_id,
            approval_id="ENG-APPROVAL-1",
            actor="cto-user",
        ),
    )
    assert approved["status"] == "cto_approved"

    with pytest.raises(client_control.ClientError, match="must be separate"):
        client_control.authorize_deploy(
            layout,
            Namespace(
                slug="test-client",
                work_id=work_id,
                approval_id="ENG-APPROVAL-1",
                actor="cto-user",
            ),
        )
    authorized = client_control.authorize_deploy(
        layout,
        Namespace(
            slug="test-client",
            work_id=work_id,
            approval_id="PROD-AUTH-1",
            actor="cto-user",
        ),
    )
    assert authorized["status"] == "ready_to_deploy"

    run = client_control.start_run(
        layout,
        Namespace(
            slug="test-client",
            work_id=work_id,
            action="deploy_production",
            actor="release-manager",
            machine="test-prod-01",
            commit="882ba43",
            before="v1.4.21",
            after="v1.4.22",
            approval_id="PROD-AUTH-1",
            rollback_available=True,
        ),
    )
    with pytest.raises(client_control.ClientError, match="forbidden"):
        client_control.start_run(
            layout,
            Namespace(
                slug="test-client",
                work_id=work_id,
                action="delete_database",
                actor="any-agent",
                machine="test-prod-01",
                commit="882ba43",
                before=None,
                after=None,
                approval_id="PROD-AUTH-1",
                rollback_available=False,
            ),
        )
    client_control.complete_run(
        layout,
        Namespace(
            slug="test-client",
            run_id=run["id"],
            result="success",
            evidence=["health-check:pending"],
        ),
    )
    _, production = client_control.load_work(layout, "test-client", work_id)
    assert production["status"] == "production"

    client_control.update_evidence(
        layout,
        Namespace(
            slug="test-client",
            work_id=work_id,
            actor="sre-agent",
            pull_request=None,
            commit=None,
            ci=None,
            qa=None,
            security=None,
            preview=None,
            risk=None,
            production_health="passed",
            linear_done=False,
        ),
    )
    client_control.transition_work(
        layout, "test-client", work_id, "verified", actor="sre-agent"
    )
    with pytest.raises(client_control.ClientError, match="Linear completion"):
        client_control.transition_work(
            layout, "test-client", work_id, "done", actor="release-manager"
        )
    client_control.update_evidence(
        layout,
        Namespace(
            slug="test-client",
            work_id=work_id,
            actor="linear-sync",
            pull_request=None,
            commit=None,
            ci=None,
            qa=None,
            security=None,
            preview=None,
            risk=None,
            production_health=None,
            linear_done=True,
        ),
    )
    done = client_control.transition_work(
        layout, "test-client", work_id, "done", actor="release-manager"
    )
    assert done["status"] == "done"


def test_review_card_only_exposes_the_valid_human_action(layout):
    client_control.create_client(layout, init_args())
    record = make_work(layout)
    record["status"] = "ready_for_cto"

    labels = {
        button["label"] for button in client_control.review_card(record)["buttons"]
    }
    assert "APPROVE" in labels
    assert "DEPLOY" not in labels

    record["status"] = "ready_to_deploy"
    labels = {
        button["label"] for button in client_control.review_card(record)["buttons"]
    }
    assert "DEPLOY" in labels
    assert "APPROVE" not in labels


def test_linear_webhook_uses_raw_body_hmac_and_replay_window():
    secret = "test-signing-secret"
    now_ms = 1_787_745_600_000
    body = json.dumps(
        {"type": "Issue", "action": "update", "webhookTimestamp": now_ms},
        separators=(",", ":"),
    ).encode()
    signature = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()

    verified = client_control.verify_linear_webhook(
        body, signature, secret, now_ms=now_ms
    )
    assert verified["type"] == "Issue"

    with pytest.raises(client_control.ClientError, match="signature"):
        client_control.verify_linear_webhook(
            body + b" ", signature, secret, now_ms=now_ms
        )
    with pytest.raises(client_control.ClientError, match="replay window"):
        client_control.verify_linear_webhook(
            body, signature, secret, now_ms=now_ms + 61_000
        )


def test_discord_plan_has_no_write_and_apply_is_idempotent_in_contract(
    layout, monkeypatch
):
    client_control.create_client(layout, init_args())
    plan = client_control.discord_plan(layout, "test-client")
    assert plan["external_writes"] is True
    assert plan["idempotent"] is True
    assert plan["rollback_on_failure"] is True

    remote = []
    counter = iter(range(100, 200))

    def fake_proxy(method, url, account, data=None):
        assert account == "client-test-client-discordbot"
        if method == "GET":
            return list(remote)
        if method == "POST":
            value = {"id": str(next(counter)), **data}
            remote.append(value)
            return value
        if method == "DELETE":
            channel_id = url.rsplit("/", 1)[-1]
            remote[:] = [item for item in remote if item["id"] != channel_id]
            return {}
        raise AssertionError(method)

    monkeypatch.setattr(client_control, "composio_proxy", fake_proxy)
    first = client_control.discord_apply(
        layout, Namespace(slug="test-client", yes=True)
    )
    second = client_control.discord_apply(
        layout, Namespace(slug="test-client", yes=True)
    )

    assert len(first["created_resource_ids"]) == 7
    assert second["created_resource_ids"] == []
    assert len(remote) == 7


def test_discord_apply_rolls_back_remote_resources_when_local_commit_fails(
    layout, monkeypatch
):
    client_control.create_client(layout, init_args())
    remote = []
    deleted = []
    counter = iter(range(200, 300))

    def fake_proxy(method, url, account, data=None):
        assert account == "client-test-client-discordbot"
        if method == "GET":
            return list(remote)
        if method == "POST":
            value = {"id": str(next(counter)), **data}
            remote.append(value)
            return value
        if method == "DELETE":
            channel_id = url.rsplit("/", 1)[-1]
            deleted.append(channel_id)
            remote[:] = [item for item in remote if item["id"] != channel_id]
            return {}
        raise AssertionError(method)

    original_atomic_yaml = client_control.atomic_yaml

    def fail_integration_commit(path, value, mode=0o600):
        if path.name == "integrations.yaml":
            raise OSError("simulated local commit failure")
        return original_atomic_yaml(path, value, mode)

    monkeypatch.setattr(client_control, "composio_proxy", fake_proxy)
    monkeypatch.setattr(client_control, "atomic_yaml", fail_integration_commit)

    with pytest.raises(client_control.ClientError, match="rolled back"):
        client_control.discord_apply(layout, Namespace(slug="test-client", yes=True))

    assert remote == []
    assert len(deleted) == 7


def test_agent_session_start_is_bound_and_cannot_bypass_review_state(
    layout, monkeypatch
):
    client_control.create_client(layout, init_args())
    work = make_work(layout)
    manifest = client_control.client_configs(layout, "test-client")["manifest.yaml"]
    profile = manifest["profile"]["hermes_profile"]
    profile_home = layout.home / ".hermes" / "profiles" / profile
    profile_home.mkdir(parents=True)
    (profile_home / "config.yaml").write_text("model: test\n", encoding="utf-8")

    class FakeRuntime:
        def has_session(self, _session):
            return True

    class FakeRegistry:
        def __init__(self):
            self.runtime = FakeRuntime()
            self.records = {}
            self.created_command = None

        def get(self, name):
            return self.records.get(name)

        def create(self, *, name, command, client, mission, **_kwargs):
            self.created_command = command
            record = {
                "id": "runtime-1",
                "name": name,
                "client": client,
                "mission": mission,
                "rmux_session": "rmux-runtime-1",
            }
            self.records[name] = record
            return record

    registry = FakeRegistry()
    monkeypatch.setattr(
        client_control, "agk_runtime", lambda _layout: (object(), registry)
    )
    started = client_control.start_work_session(layout, "test-client", work["id"])

    assert started["created"] is True
    assert registry.created_command[1:3] == ["-p", profile]

    work_path, record = client_control.load_work(layout, "test-client", work["id"])
    record["status"] = "ready_for_cto"
    client_control.atomic_yaml(work_path, record)
    with pytest.raises(client_control.ClientError, match="IN_PROGRESS"):
        client_control.start_work_session(layout, "test-client", work["id"])


def test_client_activation_creates_a_blank_isolated_hermes_profile(layout, monkeypatch):
    client_control.create_client(layout, init_args())
    manifest = client_control.client_configs(layout, "test-client")["manifest.yaml"]
    profile = manifest["profile"]["hermes_profile"]
    profile_home = layout.home / ".hermes" / "profiles" / profile
    commands = []
    monkeypatch.setattr(client_control.shutil, "which", lambda name: "/bin/hermes")

    def fake_run(command, **_kwargs):
        commands.append(command)
        profile_home.mkdir(parents=True)
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr(client_control.subprocess, "run", fake_run)
    result = client_control.activate_client(
        layout, Namespace(slug="test-client", yes=True)
    )

    assert result["created"] is True
    assert result["setup_required"] is True
    assert result["next_command"] == f"hermes --profile {profile} setup"
    assert "--no-alias" in commands[0]
    assert "--clone" not in commands[0]
    assert (profile_home / "SOUL.md").is_file()
    assert (profile_home / "AGK-CLIENT.md").read_text(encoding="utf-8") == (
        layout.client("test-client") / "AGENTS.md"
    ).read_text(encoding="utf-8")


def test_client_provider_commands_keep_hermes_and_openrouter_in_profile(
    layout, monkeypatch
):
    monkeypatch.setattr(
        client_control.shutil,
        "which",
        lambda name: f"/tools/{name}",
    )
    workspace = layout.workspace / "clients" / "test-client"

    hermes = client_control.provider_command("hermes", "clientprofile", workspace)
    openrouter = client_control.provider_command(
        "openrouter", "clientprofile", workspace
    )
    codex = client_control.provider_command("codex", "clientprofile", workspace)

    assert hermes == [
        "/tools/hermes",
        "-p",
        "clientprofile",
        "--in",
        str(workspace),
    ]
    assert openrouter[:3] == ["/tools/hermes", "-p", "clientprofile"]
    assert openrouter[-2:] == ["--in", str(workspace)]
    assert "stealth/ox-alpha" in openrouter
    assert codex == ["/tools/codex"]


def test_failed_production_completion_leaves_the_run_running(layout):
    client_control.create_client(layout, init_args())
    work = make_work(layout)
    work_path, record = client_control.load_work(layout, "test-client", work["id"])
    record["status"] = "ready_to_deploy"
    record["approvals"]["production"] = {"id": "PROD-AUTH-1"}
    client_control.atomic_yaml(work_path, record)
    run = client_control.start_run(
        layout,
        Namespace(
            slug="test-client",
            work_id=work["id"],
            action="deploy_production",
            actor="release-manager",
            machine="test-prod-01",
            commit="882ba43",
            before="v1",
            after="v2",
            approval_id="PROD-AUTH-1",
            rollback_available=True,
        ),
    )
    record["status"] = "in_progress"
    client_control.atomic_yaml(work_path, record)

    with pytest.raises(client_control.ClientError, match="READY_TO_DEPLOY"):
        client_control.complete_run(
            layout,
            Namespace(
                slug="test-client",
                run_id=run["id"],
                result="success",
                evidence=["health-check:passed"],
            ),
        )

    persisted = client_control.yaml_document(
        layout.client("test-client") / "state" / "runs" / f"{run['id']}.yaml"
    )
    assert persisted["status"] == "running"


def test_online_doctor_requires_the_exact_client_alias(layout, monkeypatch):
    client_control.create_client(layout, init_args())
    monkeypatch.setattr(
        client_control,
        "composio_connections",
        lambda: {
            "linear": [{"status": "ACTIVE", "word_id": "client-test-client-linear"}],
            "github": [{"status": "ACTIVE", "alias": "client-test-client-github"}],
            "discordbot": [{"status": "ACTIVE", "id": "client-test-client-discordbot"}],
        },
    )

    checks = client_control.doctor_one(layout, "test-client", online=True)
    assert not [message for level, message in checks if level == "fail"]

    monkeypatch.setattr(
        client_control,
        "composio_connections",
        lambda: {
            "linear": [{"status": "ACTIVE", "word_id": "default-linear"}],
            "github": [{"status": "ACTIVE", "word_id": "default-github"}],
            "discordbot": [{"status": "ACTIVE", "word_id": "default-discord"}],
        },
    )
    checks = client_control.doctor_one(layout, "test-client", online=True)
    assert any(
        "alias is missing" in message for level, message in checks if level == "fail"
    )


def test_linear_sync_is_client_scoped_mapped_and_comment_idempotent(
    layout, monkeypatch
):
    client_control.create_client(layout, init_args())
    work = make_work(layout)
    config_path = layout.client("test-client") / ".client" / "integrations.yaml"
    integrations = client_control.yaml_document(config_path)
    integrations["linear"]["workflow_state_ids"]["in_progress"] = "state-started"
    client_control.atomic_yaml(config_path, integrations)
    calls = []
    comments = []

    def fake_execute(tool, account, data):
        assert account == "client-test-client-linear"
        calls.append((tool, data))
        if tool == "LINEAR_GET_LINEAR_ISSUE":
            return {
                "data": {
                    "issue": {
                        "identifier": "FOU-142",
                        "team": {"id": "team-id"},
                        "comments": {"nodes": [{"body": body} for body in comments]},
                    }
                }
            }
        if tool == "LINEAR_CREATE_LINEAR_COMMENT":
            comments.append(data["body"])
        if tool == "LINEAR_RUN_QUERY_OR_MUTATION":
            return {
                "data": {
                    "issue": {
                        "identifier": "FOU-142",
                        "state": {"id": "state-started"},
                    }
                }
            }
        return {"data": {"success": True}}

    monkeypatch.setattr(client_control, "composio_execute", fake_execute)
    first = client_control.linear_sync_apply(
        layout, Namespace(slug="test-client", work_id=work["id"], yes=True)
    )
    second = client_control.linear_sync_apply(
        layout, Namespace(slug="test-client", work_id=work["id"], yes=True)
    )

    assert first["comment_created"] is True
    assert second["comment_created"] is False
    assert len(comments) == 1
    mutations = [data for tool, data in calls if tool == "LINEAR_RUN_QUERY_OR_MUTATION"]
    assert all(item["variables"]["stateId"] == "state-started" for item in mutations)
    _, persisted = client_control.load_work(layout, "test-client", work["id"])
    assert persisted["linear"]["status_sync"] == "in_progress"


def test_linear_sync_refuses_an_unmapped_state_before_any_external_call(
    layout, monkeypatch
):
    client_control.create_client(layout, init_args())
    work = make_work(layout)
    monkeypatch.setattr(
        client_control,
        "composio_execute",
        lambda *_args, **_kwargs: pytest.fail(
            "unmapped sync attempted an external call"
        ),
    )

    with pytest.raises(client_control.ClientError, match="no Linear workflow state"):
        client_control.linear_sync_apply(
            layout, Namespace(slug="test-client", work_id=work["id"], yes=True)
        )


def test_discord_review_delivery_is_explicit_and_locally_idempotent(
    layout, monkeypatch
):
    client_control.create_client(layout, init_args())
    work = make_work(layout)
    work_path, record = client_control.load_work(layout, "test-client", work["id"])
    record["status"] = "ready_for_cto"
    client_control.atomic_yaml(work_path, record)
    config_path = layout.client("test-client") / ".client" / "integrations.yaml"
    integrations = client_control.yaml_document(config_path)
    integrations["discord"]["channels"]["reviews"] = "987654321012345678"
    client_control.atomic_yaml(config_path, integrations)
    calls = []

    def fake_proxy(method, url, account, data=None):
        calls.append((method, url, account, data))
        assert account == "client-test-client-discordbot"
        return {"id": "555555555555555555"}

    monkeypatch.setattr(client_control, "composio_proxy", fake_proxy)
    with pytest.raises(client_control.ClientError, match="requires --yes"):
        client_control.discord_review_apply(
            layout, Namespace(slug="test-client", work_id=work["id"], yes=False)
        )
    assert calls == []

    first = client_control.discord_review_apply(
        layout, Namespace(slug="test-client", work_id=work["id"], yes=True)
    )
    second = client_control.discord_review_apply(
        layout, Namespace(slug="test-client", work_id=work["id"], yes=True)
    )

    assert first["created"] is True
    assert second["created"] is False
    assert len(calls) == 1
    payload = calls[0][3]
    labels = {
        button["label"] for row in payload["components"] for button in row["components"]
    }
    assert {"REQUEST CHANGES", "APPROVE"} <= labels
    assert payload["allowed_mentions"] == {"parse": []}

    client_control.request_changes(
        layout,
        Namespace(
            slug="test-client",
            work_id=work["id"],
            feedback="Fix the retry behavior.",
            actor="cto-user",
        ),
    )
    work_path, record = client_control.load_work(layout, "test-client", work["id"])
    record["status"] = "ready_for_cto"
    client_control.atomic_yaml(work_path, record)
    revised = client_control.discord_review_apply(
        layout, Namespace(slug="test-client", work_id=work["id"], yes=True)
    )
    assert revised["created"] is True
    assert len(calls) == 2


def test_discord_review_actions_revalidate_gates_and_queue_deploy(layout):
    client_control.create_client(layout, init_args())
    work = make_work(layout)
    work_path, record = client_control.load_work(layout, "test-client", work["id"])
    record["status"] = "ready_for_cto"
    client_control.atomic_yaml(work_path, record)
    prefix = f"agk:review:test-client:{work['id']}"

    approved = client_control.apply_review_action(
        layout,
        Namespace(
            custom_id=prefix + ":approve",
            actor="discord:42",
            decision_id="discord-approval-1",
            feedback=None,
        ),
    )
    assert approved["status"] == "cto_approved"
    client_control.authorize_deploy(
        layout,
        Namespace(
            slug="test-client",
            work_id=work["id"],
            approval_id="discord-production-1",
            actor="discord:42",
        ),
    )
    queued = client_control.apply_review_action(
        layout,
        Namespace(
            custom_id=prefix + ":deploy",
            actor="discord:42",
            decision_id="discord-deploy-1",
            feedback=None,
        ),
    )
    duplicate = client_control.apply_review_action(
        layout,
        Namespace(
            custom_id=prefix + ":deploy",
            actor="discord:42",
            decision_id="discord-deploy-1",
            feedback=None,
        ),
    )

    assert queued == {
        "action": "deploy",
        "client_id": "test-client",
        "work_id": work["id"],
        "status": "queued",
        "created": True,
    }
    assert duplicate["created"] is False
