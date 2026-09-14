# AGK OS Control Center Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give every active OS and client exactly one canonical Hermes profile and owning agent, expose the cross-home inventory through a dynamic Discord `/os` control center, and onboard optional dedicated bots through owner OAuth followed by Tailnet Secure Input.

**Architecture:** A focused OS domain module builds a global metadata-only catalog from central/private registries, canonical ownership rules, local Hermes profile inventories, assignments and client manifests. Builder OS and profile migration enforce the runtime contract. A separate Discord UI module renders `/os` and delegates deterministic mutations to the domain/service layer. Tokens remain profile-local and enter only through the existing one-time Tailnet Secure Input pipeline.

**Tech Stack:** Python 3.11+, PyYAML, discord.py `discord.ui`, Hermes profile distributions, SQLite metadata-only inspection, systemd user gateways, Tailnet Secure Input, pytest, Rust AGK-TUI registry projection.

**Spec:** `docs/superpowers/specs/2026-08-28-os-control-center-design.md`

## Global Constraints

- One canonical Hermes profile per OS in exactly one owning Linux home.
- One dedicated profile per client, exclusively in Mission.
- `default` is reserved for the four environment control profiles.
- Agents bind to OS/client profiles; agent names are not profile identities by default.
- Native Hermes profile lists remain local; Fleet `/os` is the global catalog.
- Never copy `.env`, `auth.json`, raw state databases, memories, sessions or OAuth state across homes.
- Discord mode is exactly one of `disabled`, `environment`, or `dedicated`.
- Dedicated onboarding order is Application ID -> owner OAuth -> membership check -> Tailnet Secure Input -> doctor -> exact gateway -> E2E readback.
- Never create a Discord application or accept OAuth autonomously.
- No fleet-wide gateway restart; use exact safe reload/start semantics.
- Existing Task 9 Personal OS migration is reused and revalidated rather than rebuilt.
- Every mutation is preview-first, atomic, idempotent, backed up and read back.

---

### Task 1: Canonical cross-home OS/profile catalog

**Files:**
- Create: `hermes/plugins/platforms/discord/agk_os_control.py`
- Create: `tests/test_agk_os_control.py`
- Modify: `scripts/fleet_snapshot.py`
- Modify: `tests/test_fleet_snapshot.py`

**Interfaces:**
- Consumes: `/opt/agentik/os-registry/state/index.json`, `/home/private/.agentik/os-registry`, per-home `.agentik/os-assignments.yaml`, local Hermes profile metadata, Mission client manifests.
- Produces: `ProfileRecord`, `OsControlRecord`, `canonical_owner(os_id)`, `build_os_catalog(paths)`, and Fleet snapshot rows with explicit `profile_state` and `owner_environment`.

- [ ] **Step 1: Write failing ownership and inventory tests**

```python
def test_canonical_owners_are_stable():
    assert canonical_owner("builder-os") == "operator"
    assert canonical_owner("evaluation-os") == "operator"
    assert canonical_owner("research-os") == "agentik"
    assert canonical_owner("strategy-os") == "agentik"
    assert canonical_owner("nutrition-os") == "private"


def test_private_catalog_exposes_thirteen_os_not_three_aggregators(fixture):
    rows = build_os_catalog(fixture.paths)
    private = [row for row in rows if row.owner_environment == "private"]
    assert {row.os_id for row in private} == fixture.personal_os_ids
    assert all(row.profile_id == row.os_id for row in private)
    assert {row.profile_state for row in private} == {"missing"}


def test_client_profile_is_mission_only(fixture):
    rows = build_os_catalog(fixture.paths)
    client = next(row for row in rows if row.client_id == "dentistrygpt")
    assert client.owner_environment == "mission"
    assert client.profile_id == "clientdentistrygptee881c"
```

- [ ] **Step 2: Run RED**

Run:
`uv run --with pytest --with pyyaml python -m pytest -q tests/test_agk_os_control.py tests/test_fleet_snapshot.py`

Expected: collection failure because `agk_os_control.py` and the normalized rows do not exist.

- [ ] **Step 3: Implement the domain records and metadata-only catalog**

```python
@dataclass(frozen=True)
class ProfileRecord:
    environment: str
    linux_user: str
    profile_id: str
    kind: str
    os_id: str | None
    client_id: str | None
    distribution: str | None
    version: str | None
    gateway_state: str
    doctor_state: str


@dataclass(frozen=True)
class OsControlRecord:
    os_id: str
    version: str
    owner_environment: str
    profile_id: str
    profile_state: str
    agent_ids: tuple[str, ...]
    agent_state: str
    discord_mode: str
    discord_state: str
    lifecycle_state: str


CANONICAL_OWNERS = {
    "builder-os": "operator",
    "evaluation-os": "operator",
    "research-os": "agentik",
    "strategy-os": "agentik",
    "youtube-os": "agentik",
    "nutrition-os": "private",
    "alignment-os": "private",
    "decision-os": "private",
    "goal-life-strategy-os": "private",
    "habit-tracker-os": "private",
    "health-energy-os": "private",
    "identity-shift-os": "private",
    "intuitive-os": "private",
    "journal-os": "private",
    "mentor-os": "private",
    "mindset-os": "private",
    "oto100m-os": "private",
    "social-intelligence-os": "private",
}
```

Profile roots are canonicalized, symlinks rejected, and only manifest/config metadata is read. No session title, message, memory or secret value enters the catalog.

- [ ] **Step 4: Replace Fleet's central-only OS projection**

Import the domain module in `fleet_snapshot.py`, include Private's local registry, and emit one row per canonical OS with `owner_environment`, `profile_id`, `profile_state`, `agent_state`, `discord_mode`, and `doctor_state`. Preserve redaction and existing schema compatibility.

- [ ] **Step 5: Run GREEN and snapshot privacy tests**

Run:
`uv run --with pytest --with pyyaml python -m pytest -q tests/test_agk_os_control.py tests/test_fleet_snapshot.py tests/test_fleet_dashboard.py`

Expected: all pass; encoded snapshots contain no absolute private paths, prompt text, messages or secrets.

- [ ] **Step 6: Commit**

```bash
git add hermes/plugins/platforms/discord/agk_os_control.py scripts/fleet_snapshot.py tests/test_agk_os_control.py tests/test_fleet_snapshot.py
git commit -m "feat(os): add canonical cross-home profile catalog"
```

### Task 2: Builder OS runtime contract

**Files:**
- Modify: `os-packages/builder-os/manifest.yaml`
- Modify: `os-packages/builder-os/workflows/build-cycle.yaml`
- Modify: `hermes/agents/master-os-builder/workflow.yaml`
- Create: `tests/test_builder_os_runtime_contract.py`

**Interfaces:**
- Consumes: `OsControlRecord` invariants from Task 1.
- Produces: Builder OS `0.2.0` package contract and `os-runtime-delivery` stage.

- [ ] **Step 1: Write failing Builder contract tests**

```python
def test_builder_os_requires_profile_agent_and_discord_mode():
    manifest = yaml.safe_load(BUILDER_MANIFEST.read_text())
    assert manifest["version"] == "0.2.0"
    assert "runtime-contract" in manifest["capabilities"]
    assert "os-runtime-delivery" in manifest["workflows"]


def test_build_cycle_cannot_finish_before_runtime_delivery():
    workflow = yaml.safe_load(BUILD_CYCLE.read_text())
    stages = {row["id"]: row for row in workflow["stages"]}
    assert stages["os-runtime-delivery"]["requires"] == ["verify"]
    assert stages["complete"]["requires"] == ["os-runtime-delivery"]
```

- [ ] **Step 2: Run RED**

Run:
`uv run --with pytest --with pyyaml python -m pytest -q tests/test_builder_os_runtime_contract.py`

Expected: version/stage assertions fail.

- [ ] **Step 3: Update Builder OS and Master OS Builder workflow**

Add mandatory gates for canonical owner/profile, owning agent, provider/fallback, explicit Discord mode, doctor, rollback and registry readback. Keep application creation/OAuth as owner prerequisites.

- [ ] **Step 4: Install Builder OS side by side and verify immutable source/registry equality**

Run the existing core package installer against a temporary registry first, compare deterministic tree digests, then install `builder-os@0.2.0` while retaining `0.1.0` as rollback bytes outside the active index.

- [ ] **Step 5: Run GREEN**

Run:
`uv run --with pytest --with pyyaml python -m pytest -q tests/test_builder_os_runtime_contract.py tests/test_install_contract.py`

Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add os-packages/builder-os hermes/agents/master-os-builder/workflow.yaml tests/test_builder_os_runtime_contract.py
git commit -m "feat(builder): require complete OS runtime delivery"
```

### Task 3: Profile provisioning and safe ownership migration

**Files:**
- Create: `scripts/os_profile_migration.py`
- Create: `tests/test_os_profile_migration.py`
- Modify: `install.sh`
- Modify: `scripts/install-hermes-fleet-dashboard.sh`
- Modify: `tests/test_install_contract.py`

**Interfaces:**
- Consumes: `build_os_catalog()` and canonical ownership map.
- Produces: `build_migration_plan()`, `apply_profile_plan()`, `verify_profile_plan()`, `rollback_profile_plan()`, CLI `inspect|plan|apply|verify|rollback`.

- [ ] **Step 1: Write failing path, preview and rollback tests**

```python
def test_plan_is_read_only_and_creates_one_profile_per_os(fixture):
    before = fixture.digest()
    plan = build_migration_plan(fixture.paths)
    assert fixture.digest() == before
    assert {row.profile_id for row in plan.create} == fixture.expected_profile_ids


def test_cross_home_secret_copy_is_rejected(fixture):
    operation = CopyPath(fixture.operator / ".env", fixture.private / ".env")
    with pytest.raises(MigrationError, match="secret copy"):
        validate_operation(operation)


def test_rollback_removes_only_transaction_owned_profiles(fixture):
    receipt = apply_profile_plan(fixture.plan)
    rollback_profile_plan(receipt)
    assert fixture.preexisting_profile.is_dir()
    assert not fixture.created_profile.exists()
```

- [ ] **Step 2: Run RED**

Run:
`uv run --with pytest --with pyyaml python -m pytest -q tests/test_os_profile_migration.py tests/test_install_contract.py`

Expected: missing module/installer integration failures.

- [ ] **Step 3: Implement generic profile provisioning**

Use Hermes profile distribution semantics, canonical kebab validation, no-follow path guards, per-home UID execution, transaction manifests and profile doctor. Public plans include IDs/statuses only.

- [ ] **Step 4: Integrate the existing Task 9 Personal OS package**

Task 9 is authoritative for the 13 Private profiles. Validate its Operator bundle checksum, source registry digest, 13 distributions, staged mapping and migration scripts. Wrap it with the generic transaction receipt instead of rewriting its row-copy algorithm.

- [ ] **Step 5: Define the live migration order**

1. Operator `builder-os` canary.
2. Operator `evaluation-os`.
3. Agentik `research-os` and `strategy-os`, preserving legacy aliases.
4. Private 13 Personal OS profiles from Task 9.
5. Mission Dentistry metadata normalization.
6. Nutrition ownership transfer last, after Private profile doctor and new Private-local Secure Input.

- [ ] **Step 6: Run GREEN and dry-run all homes**

Run:
`uv run --with pytest --with pyyaml python -m pytest -q tests/test_os_profile_migration.py tests/test_agk_os_control.py tests/test_install_contract.py`

Then:
`python3 scripts/os_profile_migration.py plan --all --json`

Expected: mutation false; one canonical owner per OS; 13 Private creates; no secret-copy operation; Dentistry remains Mission-local.

- [ ] **Step 7: Commit**

```bash
git add scripts/os_profile_migration.py install.sh scripts/install-hermes-fleet-dashboard.sh tests/test_os_profile_migration.py tests/test_install_contract.py
git commit -m "feat(os): add recoverable profile ownership migration"
```

### Task 4: Dynamic Discord `/os` read-only control center

**Files:**
- Create: `hermes/plugins/platforms/discord/agk_os_control_ui.py`
- Create: `tests/test_discord_os_control_ui.py`
- Modify: `hermes/plugins/platforms/discord/adapter.py`
- Modify: `hermes/plugins/agentik_os/__init__.py`

**Interfaces:**
- Consumes: `build_os_catalog()` and `OsControlRecord`.
- Produces: `OsControlView`, `OsSelect`, `register_os_control_center(bot, adapter)`, slash command `/os`.

- [ ] **Step 1: Write failing UI and authorization tests**

```python
@pytest.mark.asyncio
async def test_os_command_returns_one_compact_view(fake_interaction, catalog):
    await os_command(fake_interaction)
    assert fake_interaction.response.ephemeral is True
    assert isinstance(fake_interaction.response.view, OsControlView)
    assert len(fake_interaction.response.view.children) <= 8


@pytest.mark.asyncio
async def test_every_callback_rechecks_owner(fake_interaction):
    fake_interaction.user.id = 2
    view = OsControlView(..., owner_ids={1})
    await view.refresh.callback(fake_interaction)
    assert fake_interaction.response.content == "Not authorized"


def test_select_paginates_after_twenty_five_entries(catalog_of_31):
    view = OsControlView(catalog_of_31, ...)
    assert len(view.os_select.options) == 25
    assert view.has_next_page is True
```

- [ ] **Step 2: Run RED**

Run:
`uv run --with pytest --with pytest-asyncio --with pyyaml python -m pytest -q tests/test_discord_os_control_ui.py`

Expected: module/classes absent.

- [ ] **Step 3: Implement read-only View**

Render one title, one current state, one exact blocker/next action and controls `Install`, `Repair`, `Doctor`, `Discord`, `Refresh`, `Back`, `Close`. Finite choices use selects; no secrets or filesystem paths appear.

- [ ] **Step 4: Register `/os` without fleet-wide command churn**

Add registration to the adapter's dynamic command registry. Preserve existing UI-only command mode and fingerprint/diff sync. Do not restart any gateway in this task.

- [ ] **Step 5: Run GREEN**

Run:
`uv run --with pytest --with pytest-asyncio --with pyyaml python -m pytest -q tests/test_discord_os_control_ui.py tests/test_discord_station_session_ui.py tests/test_agk_account_control_ui.py`

Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add hermes/plugins/platforms/discord/agk_os_control_ui.py hermes/plugins/platforms/discord/adapter.py hermes/plugins/agentik_os/__init__.py tests/test_discord_os_control_ui.py
git commit -m "feat(discord): add registry-driven OS control center"
```

### Task 5: `/os` lifecycle mutations and dedicated-bot Secure Input

**Files:**
- Modify: `hermes/plugins/platforms/discord/agk_os_control.py`
- Modify: `hermes/plugins/platforms/discord/agk_os_control_ui.py`
- Modify: `scripts/tailnet_secure_input.py`
- Modify: `scripts/install-discord-token.py`
- Modify: `scripts/agk_control.py`
- Create: `tests/test_os_discord_onboarding.py`
- Modify: `tests/test_tailnet_secure_input.py`

**Interfaces:**
- Consumes: profile migration service and existing Secure Input installer.
- Produces: `record_application_id()`, `oauth_invite_url()`, `verify_guild_membership()`, `create_os_secure_input()`, `install_os_gateway()`, lifecycle action callbacks.

- [ ] **Step 1: Write failing onboarding state-machine tests**

```python
def test_secure_input_is_hidden_before_oauth_membership(os_record):
    os_record.discord_mode = "dedicated"
    os_record.application_id = "123"
    os_record.guild_member = False
    assert allowed_os_actions(os_record) == {"oauth", "refresh", "back", "close"}


def test_secure_input_targets_only_the_os_profile(os_record, tmp_path):
    request = create_os_secure_input(os_record, roots=fixture_roots(tmp_path))
    assert request.target == tmp_path / "private/.hermes/profiles/nutrition-os/.env"
    assert request.installer[-2:] == ["--expected-application", os_record.application_id]


def test_token_is_never_returned_or_hashed(adversarial_submission):
    result, logs, files = adversarial_submission.run()
    assert adversarial_submission.token not in repr(result)
    assert adversarial_submission.token not in logs
    assert adversarial_submission.token not in repr(files)
```

- [ ] **Step 2: Run RED**

Run:
`uv run --with pytest --with pytest-asyncio --with pyyaml python -m pytest -q tests/test_os_discord_onboarding.py tests/test_tailnet_secure_input.py`

Expected: state-machine/application binding absent.

- [ ] **Step 3: Extend token installer with expected application binding**

Add CLI `--expected-application`. Require `/users/@me.id == /oauth2/applications/@me.id == expected_application`, exact guild membership, and exact target containment before atomic mode-0600 write.

- [ ] **Step 4: Implement `/os` Discord onboarding states**

Application modal accepts digits only and is non-secret. OAuth URL uses least privileges and fixed AGK guild. `Refresh` performs read-only membership/channel checks. Secure Input appears only after membership. Gateway install/start is exact and doctor-gated.

- [ ] **Step 5: Add lifecycle confirmations**

`Install`, `Repair`, and rollback-capable mutations show an ephemeral confirmation naming OS, owner home, profile ID, changes and exclusions. The callback rechecks authorization and current registry digest before applying.

- [ ] **Step 6: Run GREEN and adversarial suite**

Run:
`uv run --with pytest --with pytest-asyncio --with pyyaml python -m pytest -q tests/test_os_discord_onboarding.py tests/test_tailnet_secure_input.py tests/test_agk_account_control_install.py`

Expected: all pass; no secret disclosure; concurrent submission admits one installer; malformed output fails closed.

- [ ] **Step 7: Commit**

```bash
git add hermes/plugins/platforms/discord/agk_os_control.py hermes/plugins/platforms/discord/agk_os_control_ui.py scripts/tailnet_secure_input.py scripts/install-discord-token.py scripts/agk_control.py tests/test_os_discord_onboarding.py tests/test_tailnet_secure_input.py
git commit -m "feat(os): secure dedicated Discord bot onboarding"
```

### Task 6: Source/install synchronization and migration canary

**Files:**
- Modify: `install.sh`
- Modify: `scripts/sync-hermes.sh`
- Modify: `scripts/install-shared-hermes.sh`
- Modify: `tests/test_install_contract.py`
- Create: `docs/OS-PROFILE-MIGRATION.md`

**Interfaces:**
- Consumes: all source modules/scripts from Tasks 1-5.
- Produces: byte-identical installed/future-install copies, rollback manifests, canary evidence.

- [ ] **Step 1: Write failing packaging assertions**

Assert installers package `agk_os_control.py`, `agk_os_control_ui.py`, `os_profile_migration.py`, updated Secure Input scripts, Builder OS 0.2.0, migration docs and tests. Assert exact owner/mode/paths.

- [ ] **Step 2: Run RED**

Run:
`uv run --with pytest --with pyyaml python -m pytest -q tests/test_install_contract.py`

Expected: new assets absent from install/sync contracts.

- [ ] **Step 3: Update install/sync assets**

Install scripts atomically with root ownership where global and owning-user permissions where profile-local. Do not reload gateways.

- [ ] **Step 4: Run full source acceptance**

Run:
`./scripts/test.sh`

Expected: Rust, Python, npm, typecheck and build all pass.

- [ ] **Step 5: Deploy installed copies with rollback backup**

Create `/var/backups/station/os-control-center/<UTC>/`, install tested bytes, compile Python, compare source/installed SHA-256, and verify no gateway PID changed.

- [ ] **Step 6: Apply Operator Builder OS canary**

Create/reconcile `builder-os` under Operator, bind `master-os-builder`, verify provider/fallback inference, doctor, catalog and rollback. Do not enable dedicated Discord mode.

- [ ] **Step 7: Apply the 13-profile Private migration**

Run Task 9 dry-run against current registry/session hashes. Abort on any drift. Back up Private's profile metadata and state using the Task 9 transaction contract, apply 13 profiles, verify exact per-table counts/hashes and 13/13 doctors. Keep the three aggregate profiles live as rollback aliases during acceptance.

- [ ] **Step 8: Normalize Mission client metadata**

Add distribution/profile metadata for DentistryGPT without renaming its stable profile or touching secrets/state. Verify gateway identity and client manifest binding.

- [ ] **Step 9: Commit**

```bash
git add install.sh scripts/sync-hermes.sh scripts/install-shared-hermes.sh tests/test_install_contract.py docs/OS-PROFILE-MIGRATION.md
git commit -m "build(os): package control center and profile migration"
```

### Task 7: Live `/os` rollout, E2E and final gate

**Files:**
- Create: `reports/os-control-center/<UTC>/manifest.json`
- Create: `reports/os-control-center/<UTC>/verification.md`
- Update: completion evidence through the installed CompletionStore contract.

**Interfaces:**
- Consumes: deployed code, migrated profiles and registry.
- Produces: live Discord receipt, profile/agent/doctor matrix, rollback proof and final completion verdict.

- [ ] **Step 1: Verify pre-reload fleet invariants**

Record all gateway PIDs/NRestarts, active agents, drain markers, registry digest and profile counts. Require only `administrator` plus explicitly active unrelated runtimes.

- [ ] **Step 2: Reload only Operator safely**

Use `sudo station gateway safe-reload operator --timeout 1800` only after `active_agents=0`. Verify new PID, Discord connection, zero marker and no command-sync 429.

- [ ] **Step 3: Exercise live `/os` read-only flow**

Open `/os` in AGK, read back the interaction, select Operator/Agentik/Mission/Private OS entries, paginate, Refresh/Back/Close, and verify callback authorization with an unauthorized test identity fixture.

- [ ] **Step 4: Exercise a dedicated-bot prerequisite flow without creating an app**

Select Nutrition, record the existing public Application ID, verify owner OAuth is still required if the app is absent from AGK, and confirm Secure Input remains unavailable until membership. Do not fabricate owner authorization.

- [ ] **Step 5: Exercise an already authorized bot E2E**

Use DentistryGPT or another already authorized dedicated bot: service active, expected identity, websocket, non-empty inbound message, authorization, provider/fallback inference, outbound reply and native message readback.

- [ ] **Step 6: Verify full profile matrix**

Require:
- Operator: `default`, `builder-os`, `evaluation-os` plus explicitly retained control profiles.
- Agentik: `default`, `research-os`, `strategy-os`, `youtube-os` plus classified legacy profiles.
- Mission: `default`, `collective`, DentistryGPT and one profile per registered client.
- Private: `default` plus 13 dedicated Personal OS profiles; three aggregates retained only as rollback aliases until the explicit cleanup gate.

Fleet global count must equal the union of local profile inventories.

- [ ] **Step 7: Rollback drill**

Rollback the canary profile/catalog transaction, verify prior state and gateway PIDs, then reapply idempotently and confirm zero duplicate rows/files/profiles.

- [ ] **Step 8: Full final verification**

Run Station doctor, AGK doctor, system/user failed-unit checks, all gateway checks, full source suite, profile doctors, Discord receipts, registry integrity and secret scans. Persist exact PASS/PARTIAL/BLOCKED per criterion.

- [ ] **Step 9: Completion gate and final report**

Attach artifacts/evidence to the exact mission requirements, run the canonical gate, request trusted Oracle only when all evidence is bound, and report `classification`, `permit_done`, `completion_oracle_passed`, ledger digest and rollback paths. Owner OAuth prerequisites remain BLOCKED rather than fabricated.

- [ ] **Step 10: Commit final evidence references**

```bash
git add reports/os-control-center
git commit -m "test(os): record control center acceptance"
```
