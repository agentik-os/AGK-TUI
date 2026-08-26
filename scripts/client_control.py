#!/usr/bin/env python3
"""Transactional AGK client organizations and delivery governance."""

from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import fcntl
import hashlib
import hmac
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator

import yaml


SCHEMA_VERSION = 1
CLIENT_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,48}[a-z0-9]$")
SESSION_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,78}[a-z0-9]$")
ISSUE_RE = re.compile(r"^[A-Z][A-Z0-9]{1,15}-[1-9][0-9]*$")
REQUIRED_DIRS = (
    "repos",
    "knowledge",
    "projects",
    "artifacts",
    "deployments",
    "infrastructure",
    "automation",
    "scripts",
    "logs",
    "state/work",
    "state/reviews",
    "state/runs",
    "tmp",
)
REQUIRED_CONFIG = (
    "manifest.yaml",
    "runtime.yaml",
    "integrations.yaml",
    "permissions.yaml",
    "workflow.yaml",
    "team.yaml",
)
DISCORD_CHANNELS = (
    "cto-inbox",
    "reviews",
    "releases",
    "incidents",
    "client-status",
    "agent-activity",
)


class ClientError(RuntimeError):
    """A safe, user-facing client control failure."""


@dataclass(frozen=True)
class Layout:
    home: Path
    workspace: Path
    clients: Path
    system: Path
    registry: Path
    secrets: Path
    source: Path

    @classmethod
    def current(cls) -> "Layout":
        home = Path(os.environ.get("HOME") or Path.home()).expanduser().resolve()
        workspace = (
            Path(os.environ.get("AGK_CLIENT_WORKSPACE", home / "workspace"))
            .expanduser()
            .resolve()
        )
        install_root = (
            Path(
                os.environ.get("AGK_TERMINAL_ROOT", Path(__file__).resolve().parents[1])
            )
            .expanduser()
            .resolve()
        )
        source = install_root / "client"
        return cls(
            home=home,
            workspace=workspace,
            clients=workspace / "clients",
            system=workspace / "system",
            registry=workspace / "system" / "registry.yaml",
            secrets=home / ".config" / "agk" / "clients",
            source=source,
        )

    def client(self, slug: str) -> Path:
        validate_slug(slug)
        return self.clients / slug

    def secret_file(self, slug: str) -> Path:
        validate_slug(slug)
        return self.secrets / slug / "env"


def validate_slug(value: str) -> str:
    if not CLIENT_RE.fullmatch(value):
        raise ClientError("client id must be 3-50 lowercase letters, digits or hyphens")
    return value


def validate_name(value: str) -> str:
    value = value.strip()
    if not value or len(value) > 100 or any(ord(char) < 32 for char in value):
        raise ClientError("client name must be 1-100 printable characters")
    return value


def validate_issue(value: str) -> str:
    value = value.strip().upper()
    if not ISSUE_RE.fullmatch(value):
        raise ClientError("work requires a canonical Linear issue such as FOU-142")
    return value


def hermes_profile_id(slug: str) -> str:
    compact = re.sub(r"[^a-z0-9]", "", slug)[:24]
    digest = hashlib.sha256(slug.encode()).hexdigest()[:6]
    return f"client{compact}{digest}"


def branch_component(value: str) -> str:
    value = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return (value or "work")[:42].rstrip("-")


def yaml_document(path: Path) -> dict[str, Any]:
    try:
        value = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except FileNotFoundError as error:
        raise ClientError(f"required file is missing: {path}") from error
    except (OSError, yaml.YAMLError, ValueError) as error:
        raise ClientError(f"YAML is unreadable: {path}") from error
    if not isinstance(value, dict):
        raise ClientError(f"YAML root must be an object: {path}")
    return value


def atomic_text(path: Path, value: str, mode: int = 0o600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temp_path = Path(temporary)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(value)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temp_path, mode)
        os.replace(temp_path, path)
    finally:
        temp_path.unlink(missing_ok=True)


def atomic_yaml(path: Path, value: dict[str, Any], mode: int = 0o600) -> None:
    atomic_text(
        path,
        yaml.safe_dump(value, sort_keys=False, allow_unicode=True),
        mode,
    )


@contextlib.contextmanager
def registry_lock(layout: Layout) -> Iterator[None]:
    layout.system.mkdir(parents=True, exist_ok=True)
    lock_path = layout.system / ".client-registry.lock"
    with lock_path.open("a+", encoding="utf-8") as stream:
        os.chmod(lock_path, 0o600)
        fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
        yield


@contextlib.contextmanager
def client_lock(layout: Layout, slug: str, operation: str) -> Iterator[None]:
    slug = validate_slug(slug)
    if not re.fullmatch(r"[A-Za-z0-9.-]{1,80}", operation):
        raise ClientError("invalid client operation lock")
    directory = layout.client(slug) / "state" / ".locks"
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    path = directory / f"{operation}.lock"
    with path.open("a+", encoding="utf-8") as stream:
        os.chmod(path, 0o600)
        fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
        yield


@contextlib.contextmanager
def work_lock(layout: Layout, slug: str, work_id: str) -> Iterator[None]:
    if not re.fullmatch(r"WORK-[A-F0-9]{12}", work_id):
        raise ClientError("invalid AGK work id")
    with client_lock(layout, slug, work_id):
        yield


def load_registry(layout: Layout) -> dict[str, Any]:
    if not layout.registry.exists():
        return {"schema_version": SCHEMA_VERSION, "clients": []}
    value = yaml_document(layout.registry)
    clients = value.get("clients", [])
    if not isinstance(clients, list):
        raise ClientError("client registry 'clients' must be a list")
    value.setdefault("schema_version", SCHEMA_VERSION)
    return value


def registry_id(entry: object) -> str:
    if not isinstance(entry, dict):
        return ""
    return str(entry.get("id") or entry.get("slug") or "")


def default_file(layout: Layout, name: str) -> dict[str, Any]:
    return yaml_document(layout.source / "defaults" / name)


def bootstrap(layout: Layout, *, upgrade: bool) -> None:
    standard_source = layout.source / "CLIENT-STANDARD.md"
    if not standard_source.is_file():
        raise ClientError(f"installed client standard is missing: {standard_source}")
    layout.clients.mkdir(parents=True, exist_ok=True)
    layout.system.mkdir(parents=True, exist_ok=True)
    layout.secrets.mkdir(parents=True, exist_ok=True)
    os.chmod(layout.secrets, 0o700)
    standard_target = layout.system / "CLIENT-STANDARD.md"
    if upgrade or not standard_target.exists():
        atomic_text(standard_target, standard_source.read_text(encoding="utf-8"), 0o600)
    if not layout.registry.exists():
        atomic_yaml(
            layout.registry,
            {"schema_version": SCHEMA_VERSION, "clients": []},
            0o600,
        )


def render_template(source: Path, replacements: dict[str, str]) -> str:
    value = source.read_text(encoding="utf-8")
    for key, replacement in replacements.items():
        value = value.replace("{{" + key + "}}", replacement)
    leftovers = re.findall(r"\{\{[A-Z0-9_]+\}\}", value)
    if leftovers:
        raise ClientError(f"unresolved template markers in {source}: {leftovers}")
    return value


def integration_document(slug: str, args: argparse.Namespace) -> dict[str, Any]:
    prefix = f"client-{slug}"
    return {
        "schema_version": SCHEMA_VERSION,
        "composio": {
            "entity_id": prefix,
            "strict_account_selection": True,
        },
        "linear": {
            "enabled": bool(args.linear_workspace or args.linear_team),
            "account_alias": f"{prefix}-linear",
            "workspace_id": args.linear_workspace or None,
            "team_id": args.linear_team or None,
            "workflow_state_ids": {
                "todo": None,
                "in_progress": None,
                "agent_review": None,
                "automated_qa": None,
                "ready_for_cto": None,
                "cto_approved": None,
                "ready_to_deploy": None,
                "production": None,
                "verified": None,
                "done": None,
            },
            "webhook_id": None,
            "webhook_secret_set": False,
            "webhook_replay_window_seconds": 60,
        },
        "github": {
            "enabled": args.github_mode != "none",
            "account_alias": f"{prefix}-github",
            "access_mode": args.github_mode,
            "organization": args.github_org or None,
            "repositories": [],
            "ssh_host_alias": f"github-{slug}",
        },
        "discord": {
            "enabled": bool(args.discord_guild),
            "mode": args.discord_mode,
            "account_alias": f"{prefix}-discordbot",
            "guild_id": args.discord_guild or None,
            "category_id": None,
            "channels": {name.replace("-", "_"): None for name in DISCORD_CHANNELS},
        },
        "figma": {
            "enabled": False,
            "account_alias": f"{prefix}-figma",
            "team_id": None,
            "project_ids": [],
        },
    }


def manifest_document(slug: str, name: str, args: argparse.Namespace) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "client": {
            "id": slug,
            "name": name,
            "status": "active",
            "created": dt.date.today().isoformat(),
        },
        "profile": {
            "id": "mission",
            "hermes_profile": hermes_profile_id(slug),
            "session_prefix": f"client-{slug}",
        },
        "providers": {
            "primary": "hermes",
            "allowed": ["hermes", "codex", "claude", "opencode", "openrouter"],
        },
        "isolation": {
            "credentials": "client-scoped",
            "memory": "client-scoped",
            "repositories": "client-scoped",
            "runtime": "client-scoped",
            "cross_client_access": False,
        },
    }


def runtime_document(slug: str, runtime_type: str) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "client_id": slug,
        "type": runtime_type,
        "local": {"workspace": f"~/workspace/clients/{slug}", "containers": []},
        "vps": {"hosts": []},
        "cloud": {"providers": []},
        "environments": {
            "development": {"target": "local"},
            "staging": {"target": None},
            "production": {"target": None},
        },
    }


def validate_client_init(layout: Layout, args: argparse.Namespace) -> None:
    if bool(args.linear_workspace) != bool(args.linear_team):
        raise ClientError("Linear onboarding requires both workspace_id and team_id")
    if args.github_mode == "org" and not args.github_org:
        raise ClientError("GitHub org mode requires --github-org")
    if args.discord_guild and not str(args.discord_guild).isdigit():
        raise ClientError("Discord guild_id must contain digits only")
    for path in (
        layout.source / "CLIENT-STANDARD.md",
        *(layout.source / "defaults" / name for name in REQUIRED_CONFIG[3:]),
        *(
            layout.source / "templates" / name
            for name in ("README.md", "CLIENT.md", "AGENTS.md")
        ),
    ):
        if not path.is_file():
            raise ClientError(f"installed client template is missing: {path}")


def create_client(layout: Layout, args: argparse.Namespace) -> dict[str, Any]:
    slug = validate_slug(args.slug)
    name = validate_name(args.name)
    validate_client_init(layout, args)
    destination = layout.client(slug)
    secret_destination = layout.secret_file(slug).parent
    if destination.exists() or secret_destination.exists():
        raise ClientError(f"client already exists or has state: {slug}")
    if args.dry_run:
        return {
            "dry_run": True,
            "client_id": slug,
            "workspace": str(destination),
            "secret_store": str(layout.secret_file(slug)),
            "external_actions": [],
        }

    bootstrap(layout, upgrade=False)
    stage = layout.clients / f".{slug}.stage-{uuid.uuid4().hex}"
    secret_stage = layout.secrets / f".{slug}.stage-{uuid.uuid4().hex}"
    registered = False
    destination_created = False
    secret_created = False
    try:
        stage.mkdir(mode=0o700)
        for relative in REQUIRED_DIRS:
            (stage / relative).mkdir(mode=0o700, parents=True, exist_ok=True)
        replacements = {
            "CLIENT_ID": slug,
            "CLIENT_NAME": name,
            "CREATED_DATE": dt.date.today().isoformat(),
            "RUNTIME_TYPE": args.runtime,
            "HERMES_PROFILE": hermes_profile_id(slug),
        }
        template_root = layout.source / "templates"
        for filename in ("README.md", "CLIENT.md", "AGENTS.md"):
            atomic_text(
                stage / filename,
                render_template(template_root / filename, replacements),
                0o600,
            )
        shutil.copyfile(stage / "AGENTS.md", stage / "CLAUDE.md")
        os.chmod(stage / "CLAUDE.md", 0o600)
        config = stage / ".client"
        config.mkdir(mode=0o700)
        team = default_file(layout, "team.yaml")
        team["client_id"] = slug
        team["hermes_profile"] = hermes_profile_id(slug)
        atomic_yaml(config / "manifest.yaml", manifest_document(slug, name, args))
        atomic_yaml(config / "runtime.yaml", runtime_document(slug, args.runtime))
        atomic_yaml(config / "integrations.yaml", integration_document(slug, args))
        atomic_yaml(
            config / "permissions.yaml", default_file(layout, "permissions.yaml")
        )
        atomic_yaml(config / "workflow.yaml", default_file(layout, "workflow.yaml"))
        atomic_yaml(config / "team.yaml", team)

        secret_stage.mkdir(mode=0o700)
        secret_body = (
            f"# Secrets for AGK client {slug}. Never commit or print this file.\n"
            f"export AGK_CLIENT={slug}\n"
            f"export AGK_CLIENT_DIR={destination}\n"
            "\n# OAuth credentials stay in client-selected Composio accounts.\n"
            "# Add only credentials that cannot be managed by Composio below.\n"
        )
        atomic_text(secret_stage / "env", secret_body, 0o600)

        secret_stage.rename(secret_destination)
        secret_created = True
        stage.rename(destination)
        destination_created = True
        with registry_lock(layout):
            registry = load_registry(layout)
            if any(registry_id(item) == slug for item in registry["clients"]):
                raise ClientError(f"client is already registered: {slug}")
            registry["clients"].append(
                {
                    "id": slug,
                    "name": name,
                    "status": "active",
                    "runtime": args.runtime,
                    "created": dt.date.today().isoformat(),
                    "path": str(destination),
                }
            )
            atomic_yaml(layout.registry, registry, 0o600)
            registered = True
    except Exception:
        if not registered:
            shutil.rmtree(stage, ignore_errors=True)
            shutil.rmtree(secret_stage, ignore_errors=True)
            if destination_created:
                shutil.rmtree(destination, ignore_errors=True)
            if secret_created:
                shutil.rmtree(secret_destination, ignore_errors=True)
        raise
    return {
        "dry_run": False,
        "client_id": slug,
        "workspace": str(destination),
        "secret_store": str(layout.secret_file(slug)),
        "hermes_profile": hermes_profile_id(slug),
        "external_actions": [],
    }


def client_configs(layout: Layout, slug: str) -> dict[str, dict[str, Any]]:
    root = layout.client(slug) / ".client"
    return {name: yaml_document(root / name) for name in REQUIRED_CONFIG}


def doctor_one(layout: Layout, slug: str, *, online: bool) -> list[tuple[str, str]]:
    root = layout.client(slug)
    checks: list[tuple[str, str]] = []

    def ok(message: str) -> None:
        checks.append(("ok", message))

    def fail(message: str) -> None:
        checks.append(("fail", message))

    if not root.is_dir():
        return [("fail", f"workspace missing: {root}")]
    ok("workspace exists")
    if root.stat().st_mode & 0o077:
        fail("workspace must not be accessible to group/other")
    else:
        ok("workspace boundary mode is private")
    for relative in REQUIRED_DIRS:
        (ok if (root / relative).is_dir() else fail)(f"directory {relative}")
    for filename in REQUIRED_CONFIG:
        (ok if (root / ".client" / filename).is_file() else fail)(f"config {filename}")
    if any(level == "fail" for level, _ in checks):
        return checks
    configs = client_configs(layout, slug)
    manifest = configs["manifest.yaml"]
    identity = manifest.get("client", {})
    if isinstance(identity, dict) and identity.get("id") == slug:
        ok("manifest identity matches")
    else:
        fail("manifest identity mismatch")
    workflow = configs["workflow.yaml"]
    invariants = workflow.get("invariants", {})
    for key in (
        "linear_issue_required",
        "preserve_session_on_changes",
        "engineering_approval_is_not_deploy_authorization",
    ):
        (ok if isinstance(invariants, dict) and invariants.get(key) is True else fail)(
            f"workflow invariant {key}"
        )
    permissions = configs["permissions.yaml"].get("actions", {})
    delete_policy = (
        permissions.get("delete_database", {}) if isinstance(permissions, dict) else {}
    )
    if isinstance(delete_policy, dict) and delete_policy.get("agent_allowed") is False:
        ok("database deletion is forbidden")
    else:
        fail("database deletion policy is unsafe")
    secret = layout.secret_file(slug)
    if secret.is_file() and (secret.stat().st_mode & 0o777) == 0o600:
        ok("secret store exists with mode 0600")
    else:
        fail(f"secret store missing or unsafe: {secret}")
    leaks = []
    for pattern in (".env", "*.pem", "*.key", "auth.json", "credentials.json"):
        leaks.extend(root.rglob(pattern))
    if leaks:
        fail("secret-shaped files found inside client workspace")
    else:
        ok("no secret-shaped files inside client workspace")
    registry = load_registry(layout)
    if any(registry_id(item) == slug for item in registry["clients"]):
        ok("client is registered")
    else:
        fail("client is absent from registry")
    active = os.environ.get("AGK_CLIENT")
    if active and active != slug:
        fail(f"foreign client already loaded in shell: {active}")
    else:
        ok("no foreign client loaded")
    if online:
        checks.extend(composio_checks(configs["integrations.yaml"]))
    return checks


def parse_connections(value: object) -> dict[str, list[dict[str, Any]]]:
    if not isinstance(value, dict):
        raise ClientError("Composio connections response is not an object")
    result: dict[str, list[dict[str, Any]]] = {}
    for toolkit, raw in value.items():
        if not isinstance(raw, list):
            continue
        result[str(toolkit).lower()] = [item for item in raw if isinstance(item, dict)]
    return result


def composio_connections() -> dict[str, list[dict[str, Any]]]:
    executable = shutil.which("composio")
    if not executable:
        raise ClientError("Composio CLI is not installed in this profile")
    result = subprocess.run(
        [executable, "connections", "list"],
        text=True,
        capture_output=True,
        check=False,
        timeout=30,
    )
    if result.returncode:
        raise ClientError("Composio connection inventory failed")
    try:
        return parse_connections(json.loads(result.stdout))
    except json.JSONDecodeError as error:
        raise ClientError(
            "Composio connection inventory returned invalid JSON"
        ) from error


def composio_checks(integrations: dict[str, Any]) -> list[tuple[str, str]]:
    try:
        connections = composio_connections()
    except ClientError as error:
        return [("fail", str(error))]
    checks = []
    toolkit_map = {
        "linear": "linear",
        "github": "github",
        "discord": "discordbot",
        "figma": "figma",
    }
    for section, toolkit in toolkit_map.items():
        config = integrations.get(section, {})
        if not isinstance(config, dict) or not config.get("enabled"):
            continue
        selector = str(config.get("account_alias") or "")
        candidates = connections.get(toolkit, [])
        match = next(
            (
                item
                for item in candidates
                if selector
                in {
                    str(item.get("alias") or ""),
                    str(item.get("word_id") or ""),
                    str(item.get("id") or ""),
                }
            ),
            None,
        )
        if match and str(match.get("status") or "").upper() == "ACTIVE":
            checks.append(("ok", f"Composio {section} account is active: {selector}"))
        elif match:
            checks.append(
                ("fail", f"Composio {section} account is not active: {selector}")
            )
        else:
            checks.append(
                ("fail", f"Composio {section} account alias is missing: {selector}")
            )
    return checks


def show_doctor(layout: Layout, slug: str | None, online: bool) -> int:
    bootstrap(layout, upgrade=False)
    registry = load_registry(layout)
    known = [registry_id(item) for item in registry["clients"] if registry_id(item)]
    targets = [validate_slug(slug)] if slug else known
    if not targets:
        print("AGK CLIENT SYSTEM READY · 0 clients · onboarding pending")
        return 0
    failed = False
    for target in targets:
        print(f"CLIENT {target}")
        for level, message in doctor_one(layout, target, online=online):
            marker = "✓" if level == "ok" else "✗"
            print(f"  {marker} {message}")
            failed |= level == "fail"
    return 1 if failed else 0


def integration_plan(layout: Layout, slug: str) -> dict[str, Any]:
    config = client_configs(layout, slug)["integrations.yaml"]
    commands = []
    for section, toolkit in (
        ("linear", "linear"),
        ("github", "github"),
        ("discord", "discordbot"),
        ("figma", "figma"),
    ):
        item = config.get(section, {})
        if isinstance(item, dict) and item.get("enabled"):
            alias = str(item.get("account_alias") or "")
            commands.append(
                {
                    "integration": section,
                    "command": [
                        "agk",
                        "composio",
                        "connect",
                        toolkit,
                        "--alias",
                        alias,
                        "--no-browser",
                    ],
                    "account_alias": alias,
                }
            )
    return {"client_id": slug, "external_writes": False, "connections": commands}


def discord_plan(layout: Layout, slug: str) -> dict[str, Any]:
    configs = client_configs(layout, slug)
    integrations = configs["integrations.yaml"]
    discord = integrations.get("discord", {})
    if not isinstance(discord, dict) or not discord.get("enabled"):
        raise ClientError("Discord is not enabled for this client")
    guild_id = str(discord.get("guild_id") or "")
    if not guild_id.isdigit():
        raise ClientError("Discord guild_id must be configured before provisioning")
    manifest = configs["manifest.yaml"].get("client", {})
    client_name = (
        str(manifest.get("name") or slug) if isinstance(manifest, dict) else slug
    )
    return {
        "client_id": slug,
        "account_alias": discord.get("account_alias"),
        "guild_id": guild_id,
        "mode": discord.get("mode"),
        "category": f"AGK · {client_name}",
        "channels": list(DISCORD_CHANNELS),
        "idempotent": True,
        "rollback_on_failure": True,
        "external_writes": True,
    }


def unwrap_proxy_payload(value: object) -> object:
    current = value
    for _ in range(3):
        if isinstance(current, dict) and set(current).intersection({"data", "result"}):
            candidate = current.get("data", current.get("result"))
            if candidate is current:
                break
            current = candidate
            continue
        break
    return current


def composio_proxy(
    method: str,
    url: str,
    account: str,
    data: dict[str, Any] | None = None,
) -> object:
    executable = shutil.which("composio")
    if not executable:
        raise ClientError("Composio CLI is not installed in this profile")
    command = [
        executable,
        "proxy",
        url,
        "--toolkit",
        "discordbot",
        "--account",
        account,
        "-X",
        method,
    ]
    if data is not None:
        command.extend(["-H", "content-type: application/json", "-d", json.dumps(data)])
    result = subprocess.run(
        command,
        text=True,
        capture_output=True,
        check=False,
        timeout=30,
    )
    if result.returncode:
        raise ClientError(f"Composio Discord {method} failed")
    if not result.stdout.strip():
        return {}
    try:
        return unwrap_proxy_payload(json.loads(result.stdout))
    except json.JSONDecodeError as error:
        raise ClientError("Composio Discord proxy returned invalid JSON") from error


def composio_execute(tool: str, account: str, data: dict[str, Any]) -> object:
    executable = shutil.which("composio")
    if not executable:
        raise ClientError("Composio CLI is not installed in this profile")
    result = subprocess.run(
        [
            executable,
            "execute",
            tool,
            "--account",
            account,
            "-d",
            json.dumps(data),
        ],
        text=True,
        capture_output=True,
        check=False,
        timeout=45,
    )
    if result.returncode:
        raise ClientError(f"Composio tool failed: {tool}")
    try:
        value = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise ClientError(f"Composio tool returned invalid JSON: {tool}") from error
    for item in nested_objects(value):
        if item.get("successful") is False:
            raise ClientError(f"Composio tool reported failure: {tool}")
        if item.get("success") is False:
            raise ClientError(f"Composio tool reported failure: {tool}")
    return value


def nested_objects(value: object) -> Iterator[dict[str, Any]]:
    if isinstance(value, dict):
        yield value
        for item in value.values():
            yield from nested_objects(item)
    elif isinstance(value, list):
        for item in value:
            yield from nested_objects(item)


def linear_issue_from_response(value: object, identifier: str) -> dict[str, Any]:
    for item in nested_objects(value):
        if str(item.get("identifier") or "").upper() == identifier:
            return item
    raise ClientError(f"Linear did not return the expected issue: {identifier}")


def linear_sync_plan(layout: Layout, slug: str, work_id: str) -> dict[str, Any]:
    _, work = load_work(layout, slug, work_id)
    integrations = client_configs(layout, slug)["integrations.yaml"]
    linear = integrations.get("linear", {})
    if not isinstance(linear, dict) or not linear.get("enabled"):
        raise ClientError("Linear is not enabled for this client")
    account = str(linear.get("account_alias") or "")
    team_id = str(linear.get("team_id") or "")
    state_ids = linear.get("workflow_state_ids", {})
    state = str(work.get("status") or "")
    state_id = state_ids.get(state) if isinstance(state_ids, dict) else None
    issue = str(work.get("linear", {}).get("issue") or "")
    evidence = work.get("evidence", {})
    repository = work.get("repository", {})
    comment_body = "\n".join(
        (
            f"## AGK delivery update · {work_id}",
            "",
            f"- Status: `{state}`",
            f"- Session: `{work.get('agent', {}).get('session')}`",
            f"- Branch: `{repository.get('branch')}`",
            f"- Pull request: {repository.get('pull_request') or 'pending'}",
            f"- Commit: `{repository.get('commit') or 'pending'}`",
            f"- CI / QA / Security: {bool(evidence.get('ci_passed'))} / "
            f"{bool(evidence.get('qa_passed'))} / {bool(evidence.get('security_passed'))}",
            f"- Preview: {evidence.get('staging_preview') or 'pending'}",
            f"- Risk: {evidence.get('risk') or 'unrated'}",
        )
    )
    digest = hashlib.sha256(comment_body.encode()).hexdigest()[:16]
    marker = f"<!-- agk:{slug}:{work_id}:{digest} -->"
    comment = f"{comment_body}\n\n{marker}"
    return {
        "client_id": slug,
        "work_id": work_id,
        "issue": issue,
        "account_alias": account,
        "team_id": team_id,
        "agk_status": state,
        "linear_state_id": state_id,
        "state_mapping_ready": bool(state_id),
        "comment": comment,
        "comment_marker": marker,
        "external_writes": True,
    }


def linear_sync_apply(layout: Layout, args: argparse.Namespace) -> dict[str, Any]:
    if not args.yes:
        raise ClientError(
            "Linear synchronization requires --yes after reviewing the plan"
        )
    slug = validate_slug(args.slug)
    with work_lock(layout, slug, args.work_id):
        return linear_sync_apply_locked(layout, args, slug)


def linear_sync_apply_locked(
    layout: Layout, args: argparse.Namespace, slug: str
) -> dict[str, Any]:
    plan = linear_sync_plan(layout, slug, args.work_id)
    account = str(plan["account_alias"] or "")
    state_id = str(plan["linear_state_id"] or "")
    if not account:
        raise ClientError("Linear Composio account alias is not configured")
    if not plan["team_id"]:
        raise ClientError("Linear team_id is not configured")
    if not state_id:
        raise ClientError(
            f"no Linear workflow state id is mapped for AGK status {plan['agk_status']}"
        )

    raw_issue = composio_execute(
        "LINEAR_GET_LINEAR_ISSUE",
        account,
        {"issue_id": plan["issue"]},
    )
    issue = linear_issue_from_response(raw_issue, str(plan["issue"]))
    team = issue.get("team", {})
    if not isinstance(team, dict) or str(team.get("id") or "") != plan["team_id"]:
        raise ClientError("Linear issue belongs to a different client team")
    comments = issue.get("comments", {})
    marker_exists = any(
        plan["comment_marker"] in str(item.get("body") or "")
        for item in nested_objects(comments)
    )

    mutation = """mutation AGKIssueState($issueId: String!, $stateId: String!) {
  issueUpdate(id: $issueId, input: {stateId: $stateId}) {
    success
    issue { id identifier state { id name type } }
  }
}"""
    mutation_result = composio_execute(
        "LINEAR_RUN_QUERY_OR_MUTATION",
        account,
        {
            "query_or_mutation": mutation,
            "variables": {"issueId": plan["issue"], "stateId": state_id},
        },
    )
    updated_issue = linear_issue_from_response(mutation_result, str(plan["issue"]))
    updated_state = updated_issue.get("state", {})
    if (
        not isinstance(updated_state, dict)
        or str(updated_state.get("id") or "") != state_id
    ):
        raise ClientError(
            "Linear issue state did not match the requested workflow state"
        )
    comment_created = False
    if not marker_exists:
        composio_execute(
            "LINEAR_CREATE_LINEAR_COMMENT",
            account,
            {"issueId": plan["issue"], "body": plan["comment"]},
        )
        comment_created = True

    path, work = load_work(layout, slug, args.work_id)
    work.setdefault("linear", {})["status_sync"] = plan["agk_status"]
    work_event(
        work,
        "work.linear_synced",
        state_id=state_id,
        comment_created=comment_created,
    )
    atomic_yaml(path, work)
    return {
        "client_id": slug,
        "work_id": args.work_id,
        "issue": plan["issue"],
        "status": plan["agk_status"],
        "comment_created": comment_created,
    }


def discord_apply(layout: Layout, args: argparse.Namespace) -> dict[str, Any]:
    if not args.yes:
        raise ClientError(
            "Discord provisioning requires --yes after reviewing the plan"
        )
    slug = validate_slug(args.slug)
    with client_lock(layout, slug, "discord-provision"):
        return discord_apply_locked(layout, slug)


def discord_apply_locked(layout: Layout, slug: str) -> dict[str, Any]:
    plan = discord_plan(layout, slug)
    account = str(plan["account_alias"] or "")
    if not account:
        raise ClientError("Discord Composio account alias is not configured")
    guild_id = str(plan["guild_id"])
    base = "https://discord.com/api/v10"
    raw_channels = composio_proxy("GET", f"{base}/guilds/{guild_id}/channels", account)
    if not isinstance(raw_channels, list):
        raise ClientError("Discord channel inventory is not a list")
    channels = [item for item in raw_channels if isinstance(item, dict)]
    created: list[str] = []
    try:
        category = next(
            (
                item
                for item in channels
                if item.get("type") == 4 and item.get("name") == plan["category"]
            ),
            None,
        )
        if category is None:
            value = composio_proxy(
                "POST",
                f"{base}/guilds/{guild_id}/channels",
                account,
                {"name": plan["category"], "type": 4},
            )
            if not isinstance(value, dict) or not str(value.get("id") or "").isdigit():
                raise ClientError("Discord category creation returned no id")
            category = value
            created.append(str(value["id"]))
        category_id = str(category.get("id") or "")
        if not category_id.isdigit():
            raise ClientError("Discord category id is invalid")
        channel_ids: dict[str, str] = {}
        for name in DISCORD_CHANNELS:
            existing = next(
                (
                    item
                    for item in channels
                    if item.get("type") == 0
                    and item.get("name") == name
                    and str(item.get("parent_id") or "") == category_id
                ),
                None,
            )
            if existing is None:
                value = composio_proxy(
                    "POST",
                    f"{base}/guilds/{guild_id}/channels",
                    account,
                    {
                        "name": name,
                        "type": 0,
                        "parent_id": category_id,
                        "topic": f"AGK {slug} · {name}",
                    },
                )
                if (
                    not isinstance(value, dict)
                    or not str(value.get("id") or "").isdigit()
                ):
                    raise ClientError(
                        f"Discord channel creation returned no id: {name}"
                    )
                existing = value
                created.append(str(value["id"]))
            channel_ids[name.replace("-", "_")] = str(existing["id"])

        config_path = layout.client(slug) / ".client" / "integrations.yaml"
        integrations = yaml_document(config_path)
        discord = integrations.get("discord")
        if not isinstance(discord, dict):
            raise ClientError("Discord integration config changed during apply")
        discord["category_id"] = category_id
        discord["channels"] = channel_ids
        atomic_yaml(config_path, integrations)
    except Exception as error:
        rollback_errors = []
        for channel_id in reversed(created):
            try:
                composio_proxy("DELETE", f"{base}/channels/{channel_id}", account)
            except ClientError as rollback_error:
                rollback_errors.append(str(rollback_error))
        suffix = (
            f"; rollback failures: {len(rollback_errors)}" if rollback_errors else ""
        )
        raise ClientError(
            f"Discord provisioning failed and was rolled back{suffix}: {error}"
        ) from error
    return {
        "client_id": slug,
        "category_id": category_id,
        "channels": channel_ids,
        "created_resource_ids": created,
    }


def activate_client(layout: Layout, args: argparse.Namespace) -> dict[str, Any]:
    if not args.yes:
        raise ClientError("Hermes client-profile activation requires --yes")
    slug = validate_slug(args.slug)
    manifest = client_configs(layout, slug)["manifest.yaml"]
    profile = manifest.get("profile", {})
    profile_id = (
        str(profile.get("hermes_profile") or "") if isinstance(profile, dict) else ""
    )
    if not re.fullmatch(r"[a-z0-9]+", profile_id):
        raise ClientError("client Hermes profile id is invalid")
    profile_home = layout.home / ".hermes" / "profiles" / profile_id
    created = False
    if not profile_home.is_dir():
        hermes = shutil.which("hermes")
        if not hermes:
            raise ClientError("Hermes is not installed in this profile")
        result = subprocess.run(
            [
                hermes,
                "profile",
                "create",
                profile_id,
                "--no-alias",
                "--description",
                f"Isolated AGK execution context for client {slug}.",
            ],
            text=True,
            capture_output=True,
            check=False,
            timeout=60,
        )
        if result.returncode or not profile_home.is_dir():
            raise ClientError("Hermes client profile creation failed")
        created = True
    instructions = (layout.client(slug) / "AGENTS.md").read_text(encoding="utf-8")
    atomic_text(
        profile_home / "AGK-CLIENT.md",
        instructions,
        0o600,
    )
    soul = profile_home / "SOUL.md"
    if not soul.exists():
        atomic_text(soul, instructions, 0o600)
    setup_required = not (profile_home / "config.yaml").is_file()
    return {
        "client_id": slug,
        "hermes_profile": profile_id,
        "created": created,
        "setup_required": setup_required,
        "next_command": (
            f"hermes --profile {profile_id} setup" if setup_required else None
        ),
    }


def agk_runtime(layout: Layout) -> tuple[Any, Any]:
    script_dir = str(Path(__file__).resolve().parent)
    if script_dir not in sys.path:
        sys.path.insert(0, script_dir)
    try:
        from agk_control import Environment, RuntimeRegistry  # type: ignore
    except (ImportError, OSError) as error:
        raise ClientError("AGK runtime registry is unavailable") from error
    environment = Environment.current()
    if environment.home.resolve() != layout.home:
        raise ClientError("AGK client runtime resolved a different profile HOME")
    return environment, RuntimeRegistry(environment)


def provider_command(provider: str, profile_id: str, workspace: Path) -> list[str]:
    if provider in {"hermes", "openrouter"}:
        hermes = shutil.which("hermes") or "hermes"
        command = [hermes, "-p", profile_id]
        if provider == "openrouter":
            command.extend(
                [
                    "--provider",
                    "openrouter",
                    "--model",
                    os.environ.get("AGK_OPENROUTER_MODEL", "stealth/ox-alpha"),
                ]
            )
        command.extend(["--in", str(workspace)])
        return command
    script_dir = str(Path(__file__).resolve().parent)
    if script_dir not in sys.path:
        sys.path.insert(0, script_dir)
    try:
        from agk_control import default_command  # type: ignore
    except (ImportError, OSError) as error:
        raise ClientError("AGK provider command registry is unavailable") from error
    try:
        return default_command(provider)
    except ValueError as error:
        raise ClientError(f"unsupported client work provider: {provider}") from error


def start_work_session(layout: Layout, slug: str, work_id: str) -> dict[str, Any]:
    path, record = load_work(layout, slug, work_id)
    if record.get("status") != "in_progress":
        raise ClientError("only IN_PROGRESS work can start or resume its agent session")
    profile = client_configs(layout, slug)["manifest.yaml"].get("profile", {})
    profile_id = (
        str(profile.get("hermes_profile") or "") if isinstance(profile, dict) else ""
    )
    profile_home = layout.home / ".hermes" / "profiles" / profile_id
    if not profile_home.is_dir():
        raise ClientError(
            f"activate the client Hermes profile first: agk client activate {slug} --yes"
        )
    if not (profile_home / "config.yaml").is_file():
        raise ClientError(
            f"finish isolated Hermes setup first: hermes --profile {profile_id} setup"
        )
    _environment, registry = agk_runtime(layout)
    session = str(record.get("agent", {}).get("session") or "")
    existing = registry.get(session)
    if existing is not None:
        if existing["client"] != slug or existing["mission"] != work_id:
            raise ClientError("session name is already bound to another AGK context")
        if not registry.runtime.has_session(existing["rmux_session"]):
            registry.restart_frontend(existing)
        runtime = registry.get(session)
        if runtime is None:
            raise ClientError("AGK failed to restore the preserved session")
        created = False
    else:
        provider = str(record.get("agent", {}).get("provider") or "hermes")
        runtime = registry.create(
            name=session,
            kind=provider,
            cwd=layout.client(slug),
            client=slug,
            project=str(record.get("repository", {}).get("repo") or ""),
            mission=work_id,
            command=provider_command(provider, profile_id, layout.client(slug)),
        )
        created = True
    record.setdefault("agent", {})["runtime_id"] = runtime["id"]
    record["status"] = "in_progress"
    work_event(
        record,
        "work.session_started" if created else "work.session_resumed",
        runtime_id=runtime["id"],
    )
    atomic_yaml(path, record)
    return {
        "client_id": slug,
        "work_id": work_id,
        "session": session,
        "runtime_id": runtime["id"],
        "created": created,
    }


def resume_work_session(layout: Layout, args: argparse.Namespace) -> dict[str, Any]:
    path, record = load_work(layout, args.slug, args.work_id)
    if record.get("status") != "in_progress":
        raise ClientError("only IN_PROGRESS work can resume its agent session")
    _, registry = agk_runtime(layout)
    session = str(record.get("agent", {}).get("session") or "")
    runtime = registry.get(session)
    if runtime is None:
        raise ClientError(
            "the preserved AGK session is missing; do not create a replacement"
        )
    if runtime["client"] != args.slug or runtime["mission"] != args.work_id:
        raise ClientError("the preserved session is bound to another AGK context")
    if not registry.runtime.has_session(runtime["rmux_session"]):
        registry.restart_frontend(runtime)
    feedback = args.feedback.strip() if args.feedback else ""
    if feedback:
        issue = record.get("linear", {}).get("issue")
        registry.runtime.send_input(
            runtime["rmux_session"],
            f"REQUEST CHANGES for {issue}. Resume this exact mission and context.\n\n{feedback}",
        )
    work_event(
        record,
        "work.session_resumed",
        runtime_id=runtime["id"],
        feedback_injected=bool(feedback),
    )
    atomic_yaml(path, record)
    return {
        "client_id": args.slug,
        "work_id": args.work_id,
        "session": session,
        "runtime_id": runtime["id"],
    }


def load_work(layout: Layout, slug: str, work_id: str) -> tuple[Path, dict[str, Any]]:
    if not re.fullmatch(r"WORK-[A-F0-9]{12}", work_id):
        raise ClientError("invalid AGK work id")
    path = layout.client(slug) / "state" / "work" / f"{work_id}.yaml"
    return path, yaml_document(path)


def work_event(record: dict[str, Any], event: str, **data: Any) -> None:
    record.setdefault("events", []).append(
        {
            "event": event,
            "at": dt.datetime.now(dt.timezone.utc).isoformat(),
            **data,
        }
    )
    record["updated_at"] = dt.datetime.now(dt.timezone.utc).isoformat()


def create_work(layout: Layout, args: argparse.Namespace) -> dict[str, Any]:
    slug = validate_slug(args.slug)
    issue = validate_issue(args.issue)
    configs = client_configs(layout, slug)
    roles = configs["team.yaml"].get("roles", {})
    if not isinstance(roles, dict) or args.role not in roles:
        raise ClientError(f"unknown client team role: {args.role}")
    providers = configs["manifest.yaml"].get("providers", {})
    allowed_providers = (
        providers.get("allowed", []) if isinstance(providers, dict) else []
    )
    if args.provider not in allowed_providers:
        raise ClientError(f"provider is not allowed for this client: {args.provider}")
    github = configs["integrations.yaml"].get("github", {})
    repositories = github.get("repositories", []) if isinstance(github, dict) else []
    if args.repo not in repositories:
        raise ClientError(
            "repository is not declared in .client/integrations.yaml: " + args.repo
        )
    work_id = "WORK-" + uuid.uuid4().hex[:12].upper()
    title = validate_name(args.title)
    branch = args.branch or f"feat/{issue}-{branch_component(title)}"
    session = args.session or f"{slug}-{args.role}-{issue.lower()}"
    if not SESSION_RE.fullmatch(session):
        raise ClientError("session must use lowercase canonical AGK naming")
    now = dt.datetime.now(dt.timezone.utc).isoformat()
    record: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "id": work_id,
        "client_id": slug,
        "title": title,
        "status": "in_progress",
        "linear": {"issue": issue, "status_sync": "pending"},
        "agent": {"role": args.role, "provider": args.provider, "session": session},
        "repository": {
            "repo": args.repo,
            "branch": branch,
            "pull_request": None,
            "commit": None,
        },
        "environment": {"target": args.target},
        "evidence": {
            "ci_passed": False,
            "qa_passed": False,
            "security_passed": False,
            "staging_preview": None,
            "risk": None,
        },
        "approvals": {"engineering": None, "production": None},
        "created_at": now,
        "updated_at": now,
        "events": [],
    }
    work_event(record, "work.created", issue=issue, session=session)
    path = layout.client(slug) / "state" / "work" / f"{work_id}.yaml"
    atomic_yaml(path, record)
    return record


def transition_work(
    layout: Layout,
    slug: str,
    work_id: str,
    target: str,
    *,
    actor: str,
) -> dict[str, Any]:
    path, record = load_work(layout, slug, work_id)
    workflow = client_configs(layout, slug)["workflow.yaml"]
    transitions = workflow.get("transitions", {})
    current = str(record.get("status") or "")
    allowed = transitions.get(current, []) if isinstance(transitions, dict) else []
    if target not in allowed:
        raise ClientError(f"invalid work transition: {current} -> {target}")
    if target in {"cto_approved", "ready_to_deploy", "production"}:
        raise ClientError(f"{target} requires its dedicated governed command")
    if target == "ready_for_cto":
        repository = record.get("repository", {})
        evidence = record.get("evidence", {})
        missing = []
        if not isinstance(repository, dict) or not repository.get("pull_request"):
            missing.append("pull_request")
        for key in ("ci_passed", "qa_passed", "security_passed", "staging_preview"):
            if not isinstance(evidence, dict) or not evidence.get(key):
                missing.append(key)
        if missing:
            raise ClientError(
                "READY_FOR_CTO evidence is incomplete: " + ", ".join(missing)
            )
    if target == "verified":
        evidence = record.get("evidence", {})
        if not isinstance(evidence, dict) or not evidence.get(
            "production_health_verified"
        ):
            raise ClientError("VERIFIED requires production health evidence")
    if target == "done":
        linear = record.get("linear", {})
        if not isinstance(linear, dict) or linear.get("status_sync") != "done":
            raise ClientError("DONE requires authoritative Linear completion")
    record["status"] = target
    work_event(
        record, "work.transitioned", actor=actor, previous=current, current=target
    )
    atomic_yaml(path, record)
    return record


def update_evidence(layout: Layout, args: argparse.Namespace) -> dict[str, Any]:
    path, record = load_work(layout, args.slug, args.work_id)
    repository = record.setdefault("repository", {})
    evidence = record.setdefault("evidence", {})
    changed: list[str] = []
    if args.pull_request is not None:
        repository["pull_request"] = args.pull_request
        changed.append("pull_request")
    if args.commit is not None:
        repository["commit"] = args.commit
        changed.append("commit")
    for argument, key in (
        (args.ci, "ci_passed"),
        (args.qa, "qa_passed"),
        (args.security, "security_passed"),
        (args.production_health, "production_health_verified"),
    ):
        if argument is not None:
            evidence[key] = argument == "passed"
            changed.append(key)
    if args.preview is not None:
        evidence["staging_preview"] = args.preview
        changed.append("staging_preview")
    if args.risk is not None:
        evidence["risk"] = args.risk
        changed.append("risk")
    if args.linear_done:
        record.setdefault("linear", {})["status_sync"] = "done"
        changed.append("linear_marked_done")
    if not changed:
        raise ClientError("no evidence update was provided")
    work_event(record, "work.evidence_updated", actor=args.actor, fields=changed)
    atomic_yaml(path, record)
    return record


def request_changes(layout: Layout, args: argparse.Namespace) -> dict[str, Any]:
    feedback = args.feedback.strip()
    if not feedback:
        raise ClientError("request changes requires non-empty feedback")
    path, record = load_work(layout, args.slug, args.work_id)
    current = str(record.get("status") or "")
    if current not in {"ready_for_cto", "cto_approved", "ready_to_deploy"}:
        raise ClientError(f"request changes is not valid from {current}")
    immutable = {
        "client_id": record.get("client_id"),
        "issue": record.get("linear", {}).get("issue"),
        "repo": record.get("repository", {}).get("repo"),
        "branch": record.get("repository", {}).get("branch"),
        "session": record.get("agent", {}).get("session"),
    }
    record["status"] = "in_progress"
    record["approvals"] = {"engineering": None, "production": None}
    work_event(
        record,
        "work.changes_requested",
        actor=args.actor,
        feedback=feedback,
        resumed_context=immutable,
    )
    atomic_yaml(path, record)
    return record


def approve_work(layout: Layout, args: argparse.Namespace) -> dict[str, Any]:
    path, record = load_work(layout, args.slug, args.work_id)
    if record.get("status") != "ready_for_cto":
        raise ClientError("engineering approval requires READY_FOR_CTO")
    approval = {
        "id": args.approval_id,
        "actor": args.actor,
        "at": dt.datetime.now(dt.timezone.utc).isoformat(),
    }
    record.setdefault("approvals", {})["engineering"] = approval
    record["status"] = "cto_approved"
    work_event(record, "work.engineering_approved", **approval)
    atomic_yaml(path, record)
    return record


def authorize_deploy(layout: Layout, args: argparse.Namespace) -> dict[str, Any]:
    path, record = load_work(layout, args.slug, args.work_id)
    if record.get("status") != "cto_approved":
        raise ClientError("deployment authorization requires CTO_APPROVED")
    engineering = record.get("approvals", {}).get("engineering", {})
    if args.approval_id == engineering.get("id"):
        raise ClientError(
            "deployment authorization must be separate from engineering approval"
        )
    approval = {
        "id": args.approval_id,
        "actor": args.actor,
        "at": dt.datetime.now(dt.timezone.utc).isoformat(),
    }
    record.setdefault("approvals", {})["production"] = approval
    record["status"] = "ready_to_deploy"
    work_event(record, "work.production_authorized", **approval)
    atomic_yaml(path, record)
    return record


def apply_review_action(layout: Layout, args: argparse.Namespace) -> dict[str, Any]:
    match = re.fullmatch(
        r"agk:review:([a-z0-9][a-z0-9-]{1,48}[a-z0-9]):"
        r"(WORK-[A-F0-9]{12}):(changes|approve|deploy)",
        args.custom_id,
    )
    if not match:
        raise ClientError("invalid AGK Discord review action")
    slug, work_id, action = match.groups()
    actor = validate_name(args.actor)
    decision_id = str(args.decision_id or "").strip()
    if not decision_id or len(decision_id) > 100:
        raise ClientError("review action requires a bounded Discord interaction id")
    with work_lock(layout, slug, work_id):
        return apply_review_action_locked(
            layout, args, slug, work_id, action, actor, decision_id
        )


def apply_review_action_locked(
    layout: Layout,
    args: argparse.Namespace,
    slug: str,
    work_id: str,
    action: str,
    actor: str,
    decision_id: str,
) -> dict[str, Any]:
    if action == "approve":
        record = approve_work(
            layout,
            argparse.Namespace(
                slug=slug,
                work_id=work_id,
                approval_id=decision_id,
                actor=actor,
            ),
        )
        return {
            "action": action,
            "client_id": slug,
            "work_id": work_id,
            "status": record["status"],
        }
    if action == "changes":
        record = request_changes(
            layout,
            argparse.Namespace(
                slug=slug,
                work_id=work_id,
                feedback=args.feedback or "",
                actor=actor,
            ),
        )
        result = {
            "action": action,
            "client_id": slug,
            "work_id": work_id,
            "status": record["status"],
            "session_resumed": False,
        }
        if record.get("agent", {}).get("runtime_id"):
            try:
                resume_work_session(
                    layout,
                    argparse.Namespace(
                        slug=slug,
                        work_id=work_id,
                        feedback=args.feedback,
                    ),
                )
                result["session_resumed"] = True
            except ClientError as error:
                result["session_resume_error"] = str(error)
        return result

    path, record = load_work(layout, slug, work_id)
    if record.get("status") != "ready_to_deploy":
        raise ClientError("DEPLOY requires READY_TO_DEPLOY")
    existing = record.get("deployment_request", {})
    if isinstance(existing, dict) and existing.get("id"):
        if existing.get("id") != decision_id:
            raise ClientError("a production deployment request is already queued")
        return {
            "action": action,
            "client_id": slug,
            "work_id": work_id,
            "status": "queued",
            "created": False,
        }
    request = {
        "id": decision_id,
        "actor": actor,
        "at": dt.datetime.now(dt.timezone.utc).isoformat(),
    }
    record["deployment_request"] = request
    work_event(record, "work.production_deploy_requested", **request)
    atomic_yaml(path, record)
    return {
        "action": action,
        "client_id": slug,
        "work_id": work_id,
        "status": "queued",
        "created": True,
    }


def review_card(record: dict[str, Any]) -> dict[str, Any]:
    evidence = record.get("evidence", {})
    repo = record.get("repository", {})
    lines = [
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"🛠 CTO REVIEW · {str(record.get('client_id')).upper()}",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"{record.get('linear', {}).get('issue')} · {record.get('title')}",
        f"Agent · {record.get('agent', {}).get('role')}",
        f"Session · {record.get('agent', {}).get('session')}",
        f"PR · {repo.get('pull_request') or 'pending'}",
        f"CI · {'PASS' if evidence.get('ci_passed') else 'PENDING'}",
        f"QA · {'PASS' if evidence.get('qa_passed') else 'PENDING'}",
        f"Security · {'PASS' if evidence.get('security_passed') else 'PENDING'}",
        f"Risk · {evidence.get('risk') or 'unrated'}",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
    ]
    prefix = f"agk:review:{record.get('client_id')}:{record.get('id')}"
    buttons = [
        {
            "label": "OPEN PREVIEW",
            "style": "link",
            "url": evidence.get("staging_preview"),
        },
        {
            "label": "REQUEST CHANGES",
            "style": "danger",
            "custom_id": prefix + ":changes",
        },
    ]
    if record.get("status") == "ready_for_cto":
        buttons.append(
            {"label": "APPROVE", "style": "success", "custom_id": prefix + ":approve"}
        )
    if record.get("status") == "ready_to_deploy":
        buttons.append(
            {"label": "DEPLOY", "style": "primary", "custom_id": prefix + ":deploy"}
        )
    return {
        "content": "\n".join(lines),
        "buttons": [
            button for button in buttons if button.get("url") or "url" not in button
        ],
    }


def discord_review_plan(layout: Layout, slug: str, work_id: str) -> dict[str, Any]:
    _, work = load_work(layout, slug, work_id)
    if work.get("status") not in {"ready_for_cto", "ready_to_deploy"}:
        raise ClientError(
            "Discord review cards require READY_FOR_CTO or READY_TO_DEPLOY"
        )
    discord = client_configs(layout, slug)["integrations.yaml"].get("discord", {})
    if not isinstance(discord, dict) or not discord.get("enabled"):
        raise ClientError("Discord is not enabled for this client")
    channels = discord.get("channels", {})
    channel_key = "reviews" if work.get("status") == "ready_for_cto" else "releases"
    channel_id = channels.get(channel_key) if isinstance(channels, dict) else None
    card = review_card(work)
    revision = sum(
        1
        for event in work.get("events", [])
        if isinstance(event, dict) and event.get("event") == "work.changes_requested"
    )
    return {
        "client_id": slug,
        "work_id": work_id,
        "account_alias": discord.get("account_alias"),
        "channel": channel_key,
        "channel_id": channel_id,
        "revision": revision,
        "card": card,
        "external_writes": True,
        "idempotent": True,
    }


def discord_components(card: dict[str, Any]) -> list[dict[str, Any]]:
    style_codes = {"primary": 1, "success": 3, "danger": 4, "link": 5}
    components = []
    for button in card.get("buttons", []):
        if not isinstance(button, dict):
            continue
        style = str(button.get("style") or "")
        item: dict[str, Any] = {
            "type": 2,
            "style": style_codes.get(style, 2),
            "label": str(button.get("label") or "Action")[:80],
        }
        if style == "link":
            item["url"] = button.get("url")
        else:
            custom_id = str(button.get("custom_id") or "")
            if not custom_id or len(custom_id) > 100:
                raise ClientError("Discord review button custom_id is invalid")
            item["custom_id"] = custom_id
        components.append(item)
    if len(components) > 5:
        raise ClientError("Discord review card exceeds one action row")
    return [{"type": 1, "components": components}] if components else []


def discord_review_apply(layout: Layout, args: argparse.Namespace) -> dict[str, Any]:
    if not args.yes:
        raise ClientError(
            "Discord review delivery requires --yes after reviewing the plan"
        )
    slug = validate_slug(args.slug)
    with work_lock(layout, slug, args.work_id):
        return discord_review_apply_locked(layout, args, slug)


def discord_review_apply_locked(
    layout: Layout, args: argparse.Namespace, slug: str
) -> dict[str, Any]:
    plan = discord_review_plan(layout, slug, args.work_id)
    account = str(plan["account_alias"] or "")
    channel_id = str(plan["channel_id"] or "")
    if not account:
        raise ClientError("Discord Composio account alias is not configured")
    if not channel_id.isdigit():
        raise ClientError(f"Discord #{plan['channel']} channel is not provisioned")
    path, work = load_work(layout, slug, args.work_id)
    delivery = work.get("discord_review", {})
    if (
        isinstance(delivery, dict)
        and delivery.get("message_id")
        and str(delivery.get("channel_id") or "") == channel_id
        and delivery.get("status") == work.get("status")
        and delivery.get("revision") == plan["revision"]
    ):
        return {
            "client_id": slug,
            "work_id": args.work_id,
            "channel_id": channel_id,
            "message_id": delivery["message_id"],
            "created": False,
        }

    card = plan["card"]
    payload = {
        "content": card["content"],
        "components": discord_components(card),
        "allowed_mentions": {"parse": []},
    }
    value = composio_proxy(
        "POST",
        f"https://discord.com/api/v10/channels/{channel_id}/messages",
        account,
        payload,
    )
    if not isinstance(value, dict) or not str(value.get("id") or "").isdigit():
        raise ClientError("Discord review delivery returned no message id")
    message_id = str(value["id"])
    try:
        work["discord_review"] = {
            "channel": plan["channel"],
            "channel_id": channel_id,
            "message_id": message_id,
            "status": work.get("status"),
            "revision": plan["revision"],
            "sent_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        }
        work_event(work, "work.discord_review_sent", message_id=message_id)
        atomic_yaml(path, work)
    except Exception as error:
        try:
            composio_proxy(
                "DELETE",
                f"https://discord.com/api/v10/channels/{channel_id}/messages/{message_id}",
                account,
            )
        except ClientError as rollback_error:
            raise ClientError(
                f"Discord review local commit failed; message rollback also failed: {rollback_error}"
            ) from error
        raise ClientError(
            "Discord review local commit failed and message was rolled back"
        ) from error
    return {
        "client_id": slug,
        "work_id": args.work_id,
        "channel_id": channel_id,
        "message_id": message_id,
        "created": True,
    }


def start_run(layout: Layout, args: argparse.Namespace) -> dict[str, Any]:
    slug = validate_slug(args.slug)
    with work_lock(layout, slug, args.work_id):
        return start_run_locked(layout, args, slug)


def start_run_locked(
    layout: Layout, args: argparse.Namespace, slug: str
) -> dict[str, Any]:
    _, work = load_work(layout, slug, args.work_id)
    permissions = client_configs(layout, slug)["permissions.yaml"].get("actions", {})
    policy = permissions.get(args.action, {}) if isinstance(permissions, dict) else {}
    if not isinstance(policy, dict) or not policy:
        raise ClientError(f"unknown governed action: {args.action}")
    if (
        policy.get("agent_allowed") is False
        or policy.get("human_approval") == "forbidden"
    ):
        raise ClientError(f"action is forbidden by client policy: {args.action}")
    if policy.get("issue_required") and not work.get("linear", {}).get("issue"):
        raise ClientError("governed action requires a Linear issue")
    if policy.get("human_approval") == "required" and not args.approval_id:
        raise ClientError(f"action requires human approval: {args.action}")
    if args.action == "deploy_production":
        production = work.get("approvals", {}).get("production", {})
        if work.get(
            "status"
        ) != "ready_to_deploy" or args.approval_id != production.get("id"):
            raise ClientError(
                "production deploy requires its recorded deployment authorization"
            )
        run_dir = layout.client(slug) / "state" / "runs"
        for candidate in run_dir.glob("RUN-*.yaml"):
            existing = yaml_document(candidate)
            if (
                existing.get("work_id") == args.work_id
                and existing.get("action") == "deploy_production"
                and existing.get("status") == "running"
            ):
                raise ClientError("a production Run is already active for this work")
    run_id = "RUN-" + uuid.uuid4().hex[:12].upper()
    now = dt.datetime.now(dt.timezone.utc).isoformat()
    record = {
        "schema_version": SCHEMA_VERSION,
        "id": run_id,
        "client_id": slug,
        "work_id": args.work_id,
        "linear_issue": work.get("linear", {}).get("issue"),
        "action": args.action,
        "policy_level": policy.get("level"),
        "actor": args.actor,
        "machine": args.machine,
        "commit": args.commit,
        "before": args.before,
        "after": args.after,
        "approval_id": args.approval_id,
        "rollback_available": args.rollback_available,
        "status": "running",
        "result": None,
        "started_at": now,
        "finished_at": None,
        "evidence": [],
    }
    path = layout.client(slug) / "state" / "runs" / f"{run_id}.yaml"
    atomic_yaml(path, record)
    return record


def complete_run(layout: Layout, args: argparse.Namespace) -> dict[str, Any]:
    slug = validate_slug(args.slug)
    if not re.fullmatch(r"RUN-[A-F0-9]{12}", args.run_id):
        raise ClientError("invalid AGK run id")
    with client_lock(layout, slug, args.run_id):
        return complete_run_locked(layout, args, slug)


def complete_run_locked(
    layout: Layout, args: argparse.Namespace, slug: str
) -> dict[str, Any]:
    path = layout.client(slug) / "state" / "runs" / f"{args.run_id}.yaml"
    record = yaml_document(path)
    if record.get("status") != "running":
        raise ClientError("only a running AGK Run can be completed")
    if record.get("client_id") != slug:
        raise ClientError("AGK Run belongs to a different client boundary")

    production_success = (
        record.get("action") == "deploy_production" and args.result == "success"
    )
    context = (
        work_lock(layout, slug, str(record.get("work_id")))
        if production_success
        else contextlib.nullcontext()
    )
    with context:
        work_path: Path | None = None
        work: dict[str, Any] | None = None
        if production_success:
            work_path, work = load_work(layout, slug, str(record.get("work_id")))
            if work.get("status") != "ready_to_deploy":
                raise ClientError("production Run completed outside READY_TO_DEPLOY")

        record["status"] = "completed" if args.result == "success" else "failed"
        record["result"] = args.result
        record["finished_at"] = dt.datetime.now(dt.timezone.utc).isoformat()
        record["evidence"] = args.evidence
        atomic_yaml(path, record)
        if work_path is not None and work is not None:
            work["status"] = "production"
            work_event(
                work,
                "work.production_deployed",
                run_id=record.get("id"),
                machine=record.get("machine"),
                commit=record.get("commit"),
            )
            atomic_yaml(work_path, work)
    return record


def verify_linear_webhook(
    raw_body: bytes,
    signature: str,
    secret: str,
    *,
    now_ms: int | None = None,
    replay_window_seconds: int = 60,
) -> dict[str, Any]:
    if not secret:
        raise ClientError("Linear webhook secret is unavailable")
    try:
        received = bytes.fromhex(signature)
    except ValueError as error:
        raise ClientError("Linear-Signature is not valid hexadecimal") from error
    expected = hmac.new(secret.encode(), raw_body, hashlib.sha256).digest()
    if not hmac.compare_digest(received, expected):
        raise ClientError("Linear webhook signature is invalid")
    try:
        payload = json.loads(raw_body)
        timestamp = int(payload["webhookTimestamp"])
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise ClientError("Linear webhook timestamp is missing or invalid") from error
    current = int(time.time() * 1000) if now_ms is None else now_ms
    if abs(current - timestamp) > replay_window_seconds * 1000:
        raise ClientError("Linear webhook is outside the replay window")
    return payload


def print_json(value: object) -> None:
    print(json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False))


def list_clients(layout: Layout) -> list[dict[str, Any]]:
    registry = load_registry(layout)
    return [item for item in registry["clients"] if isinstance(item, dict)]


def command_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="agk client")
    commands = parser.add_subparsers(dest="command", required=True)
    bootstrap_cmd = commands.add_parser("bootstrap")
    bootstrap_cmd.add_argument("--upgrade", action="store_true")
    init = commands.add_parser("init", aliases=["provision"])
    init.add_argument("slug")
    init.add_argument("--name", required=True)
    init.add_argument(
        "--runtime",
        choices=("local", "vps", "hybrid", "cloud", "external"),
        default="local",
    )
    init.add_argument(
        "--github-mode",
        choices=("dedicated", "org", "app", "token", "deploy-key", "none"),
        default="none",
    )
    init.add_argument("--github-org")
    init.add_argument("--linear-workspace")
    init.add_argument("--linear-team")
    init.add_argument(
        "--discord-mode",
        choices=("shared-command-center", "dedicated-bot"),
        default="shared-command-center",
    )
    init.add_argument("--discord-guild")
    init.add_argument("--dry-run", action="store_true")
    commands.add_parser("list")
    show = commands.add_parser("show")
    show.add_argument("slug")
    doctor = commands.add_parser("doctor")
    doctor.add_argument("slug", nargs="?")
    doctor.add_argument("--online", action="store_true")
    env = commands.add_parser("env")
    env.add_argument("slug")
    activate = commands.add_parser("activate")
    activate.add_argument("slug")
    activate.add_argument("--yes", action="store_true")
    integrations = commands.add_parser("integrations")
    integrations.add_argument("action", choices=("plan", "verify"))
    integrations.add_argument("slug")
    linear = commands.add_parser("linear")
    linear.add_argument("action", choices=("plan", "apply"))
    linear.add_argument("slug")
    linear.add_argument("work_id")
    linear.add_argument("--yes", action="store_true")
    discord = commands.add_parser("discord")
    discord.add_argument(
        "action", choices=("plan", "apply", "review-plan", "review-apply")
    )
    discord.add_argument("slug")
    discord.add_argument("work_id", nargs="?")
    discord.add_argument("--yes", action="store_true")

    work = commands.add_parser("work")
    work_sub = work.add_subparsers(dest="work_command", required=True)
    work_create = work_sub.add_parser("create")
    work_create.add_argument("slug")
    work_create.add_argument("--issue", required=True)
    work_create.add_argument("--title", required=True)
    work_create.add_argument("--role", required=True)
    work_create.add_argument(
        "--provider",
        choices=("hermes", "codex", "claude", "opencode", "openrouter"),
        default="hermes",
    )
    work_create.add_argument("--repo", required=True)
    work_create.add_argument("--branch")
    work_create.add_argument("--session")
    work_create.add_argument(
        "--target",
        choices=("development", "staging", "production"),
        default="development",
    )
    transition = work_sub.add_parser("transition")
    transition.add_argument("slug")
    transition.add_argument("work_id")
    transition.add_argument("target")
    transition.add_argument("--actor", required=True)
    changes = work_sub.add_parser("request-changes")
    changes.add_argument("slug")
    changes.add_argument("work_id")
    changes.add_argument("--feedback", required=True)
    changes.add_argument("--actor", required=True)
    evidence = work_sub.add_parser("evidence")
    evidence.add_argument("slug")
    evidence.add_argument("work_id")
    evidence.add_argument("--actor", required=True)
    evidence.add_argument("--pull-request")
    evidence.add_argument("--commit")
    evidence.add_argument("--ci", choices=("passed", "failed"))
    evidence.add_argument("--qa", choices=("passed", "failed"))
    evidence.add_argument("--security", choices=("passed", "failed"))
    evidence.add_argument("--preview")
    evidence.add_argument("--risk", choices=("low", "medium", "high", "critical"))
    evidence.add_argument("--production-health", choices=("passed", "failed"))
    evidence.add_argument("--linear-done", action="store_true")
    approve = work_sub.add_parser("approve")
    approve.add_argument("slug")
    approve.add_argument("work_id")
    approve.add_argument("--approval-id", required=True)
    approve.add_argument("--actor", required=True)
    deploy = work_sub.add_parser("authorize-deploy")
    deploy.add_argument("slug")
    deploy.add_argument("work_id")
    deploy.add_argument("--approval-id", required=True)
    deploy.add_argument("--actor", required=True)
    card = work_sub.add_parser("review-card")
    card.add_argument("slug")
    card.add_argument("work_id")
    review_action = work_sub.add_parser("review-action")
    review_action.add_argument("custom_id")
    review_action.add_argument("--actor", required=True)
    review_action.add_argument("--decision-id", required=True)
    review_action.add_argument("--feedback")
    work_show = work_sub.add_parser("show")
    work_show.add_argument("slug")
    work_show.add_argument("work_id")
    work_start = work_sub.add_parser("start")
    work_start.add_argument("slug")
    work_start.add_argument("work_id")
    work_resume = work_sub.add_parser("resume")
    work_resume.add_argument("slug")
    work_resume.add_argument("work_id")
    work_resume.add_argument("--feedback")

    run_cmd = commands.add_parser("run")
    run_sub = run_cmd.add_subparsers(dest="run_command", required=True)
    run_start = run_sub.add_parser("start")
    run_start.add_argument("slug")
    run_start.add_argument("work_id")
    run_start.add_argument("--action", required=True)
    run_start.add_argument("--actor", required=True)
    run_start.add_argument("--machine", required=True)
    run_start.add_argument("--commit", required=True)
    run_start.add_argument("--before")
    run_start.add_argument("--after")
    run_start.add_argument("--approval-id")
    run_start.add_argument("--rollback-available", action="store_true")
    run_complete = run_sub.add_parser("complete")
    run_complete.add_argument("slug")
    run_complete.add_argument("run_id")
    run_complete.add_argument("--result", choices=("success", "failure"), required=True)
    run_complete.add_argument("--evidence", action="append", default=[])

    webhook = commands.add_parser("verify-linear-webhook")
    webhook.add_argument("--body", type=Path, required=True)
    webhook.add_argument("--signature", required=True)
    webhook.add_argument("--secret-env", default="LINEAR_WEBHOOK_SECRET")
    webhook.add_argument("--now-ms", type=int)
    webhook.add_argument("--replay-window", type=int, default=60)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = command_parser()
    args = parser.parse_args(argv)
    layout = Layout.current()
    try:
        if args.command == "bootstrap":
            bootstrap(layout, upgrade=args.upgrade)
            print_json(
                {
                    "status": "ready",
                    "workspace": str(layout.workspace),
                    "clients": len(list_clients(layout)),
                }
            )
            return 0
        if args.command in {"init", "provision"}:
            print_json(create_client(layout, args))
            return 0
        if args.command == "list":
            print_json(list_clients(layout))
            return 0
        if args.command == "show":
            print_json(client_configs(layout, validate_slug(args.slug)))
            return 0
        if args.command == "doctor":
            return show_doctor(layout, args.slug, args.online)
        if args.command == "env":
            slug = validate_slug(args.slug)
            active = os.environ.get("AGK_CLIENT")
            if active and active != slug:
                raise ClientError(
                    f"client {active} is already loaded; open a new shell"
                )
            secret = layout.secret_file(slug)
            if not secret.is_file() or (secret.stat().st_mode & 0o777) != 0o600:
                raise ClientError(f"client secret store is missing or unsafe: {secret}")
            sys.stdout.write(secret.read_text(encoding="utf-8"))
            return 0
        if args.command == "activate":
            print_json(activate_client(layout, args))
            return 0
        if args.command == "integrations":
            if args.action == "plan":
                print_json(integration_plan(layout, validate_slug(args.slug)))
                return 0
            checks = composio_checks(
                client_configs(layout, args.slug)["integrations.yaml"]
            )
            print_json(
                {
                    "client_id": args.slug,
                    "checks": [
                        {"status": level, "message": message}
                        for level, message in checks
                    ],
                }
            )
            return 1 if any(level == "fail" for level, _ in checks) else 0
        if args.command == "linear":
            print_json(
                linear_sync_plan(layout, validate_slug(args.slug), args.work_id)
                if args.action == "plan"
                else linear_sync_apply(layout, args)
            )
            return 0
        if args.command == "discord":
            if args.action == "plan":
                print_json(discord_plan(layout, validate_slug(args.slug)))
            elif args.action == "apply":
                print_json(discord_apply(layout, args))
            else:
                if not args.work_id:
                    raise ClientError(f"Discord {args.action} requires an AGK work id")
                print_json(
                    discord_review_plan(layout, validate_slug(args.slug), args.work_id)
                    if args.action == "review-plan"
                    else discord_review_apply(layout, args)
                )
            return 0
        if args.command == "work":
            if args.work_command == "create":
                print_json(create_work(layout, args))
            elif args.work_command == "transition":
                print_json(
                    transition_work(
                        layout, args.slug, args.work_id, args.target, actor=args.actor
                    )
                )
            elif args.work_command == "request-changes":
                print_json(request_changes(layout, args))
            elif args.work_command == "evidence":
                print_json(update_evidence(layout, args))
            elif args.work_command == "approve":
                print_json(approve_work(layout, args))
            elif args.work_command == "authorize-deploy":
                print_json(authorize_deploy(layout, args))
            elif args.work_command == "review-card":
                _, record = load_work(layout, args.slug, args.work_id)
                print_json(review_card(record))
            elif args.work_command == "review-action":
                print_json(apply_review_action(layout, args))
            elif args.work_command == "start":
                print_json(start_work_session(layout, args.slug, args.work_id))
            elif args.work_command == "resume":
                print_json(resume_work_session(layout, args))
            else:
                _, record = load_work(layout, args.slug, args.work_id)
                print_json(record)
            return 0
        if args.command == "run":
            print_json(
                start_run(layout, args)
                if args.run_command == "start"
                else complete_run(layout, args)
            )
            return 0
        if args.command == "verify-linear-webhook":
            payload = verify_linear_webhook(
                args.body.read_bytes(),
                args.signature,
                os.environ.get(args.secret_env, ""),
                now_ms=args.now_ms,
                replay_window_seconds=args.replay_window,
            )
            print_json(
                {
                    "verified": True,
                    "type": payload.get("type"),
                    "action": payload.get("action"),
                }
            )
            return 0
    except (ClientError, OSError, subprocess.SubprocessError) as error:
        print(f"AGK client error: {error}", file=sys.stderr)
        return 1
    parser.error("unhandled client command")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
