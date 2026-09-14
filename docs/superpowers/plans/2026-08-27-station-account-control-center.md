# Station Account Control Center Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and deploy a private Discord Account Control Center that lists, adds, and reconnects OpenAI Codex and Claude accounts and propagates every verified mutation to Hermes rotation, `/account`, and voice quota channels.

**Architecture:** Add focused account-control domain, OAuth-attempt, transaction, and Discord-UI modules beside the existing Discord adapter. Hermes' credential pool and the redacted alias registry remain canonical; durable OAuth runners execute as user-systemd sibling units so they survive gateway reloads. The existing account usage monitor consumes the same canonical state and reuses voice channels by provider plus owner nickname.

**Tech Stack:** Python 3.11+, Hermes Agent credential pool/auth CLI, discord.py persistent Views, asyncio, user systemd, JSON state with atomic mode-0600 writes, pytest via `uv run`.

**Spec:** `docs/superpowers/specs/2026-08-27-station-account-control-center-design.md`

## Global Constraints

- Discord guild: `1541131439599386644`.
- Discord category: `Tokens`, ID `1542505218569150585`.
- Authorized owner: Gareth, Discord user ID `1441423462492016821`.
- New channel: `account-control`, visible only to Gareth and Operator.
- Providers in v1: `openai-codex` and `anthropic` only.
- `auth.json` and `agent.credential_pool` remain the credential source of truth.
- `$HERMES_HOME/provider-account-aliases.json` remains the mode-0600 nickname source of truth.
- Never render passwords, account emails, JWT claims, access tokens, refresh tokens, API keys, or raw provider error bodies.
- Missing usage is `unavailable`, never `0%`.
- Candidate verification must pass before reconnect removes the old credential.
- OAuth attempts run outside the gateway cgroup and expire after 900 seconds.
- `station-account-capacity` and `claudecode-all-accounts` must not be recreated.
- Voice channel percentages remain percentage used; detailed account views may show used and remaining explicitly.
- No per-account gateway restart.

---

### Task 1: Canonical Account Roster and Alias Registry

**Files:**
- Create: `hermes/plugins/platforms/discord/agk_account_control.py`
- Modify: `hermes/plugins/platforms/discord/agk_account_usage_monitor.py`
- Test: `tests/test_agk_account_control.py`
- Test: `tests/test_agk_account_usage_monitor.py`

**Interfaces:**
- Produces: `AccountRecord`, `AliasRegistry`, `load_account_roster(hermes_home: Path) -> tuple[AccountRecord, ...]`, `render_account_roster(records) -> str`, `voice_binding_key(provider: str, owner_name: str) -> str`.
- Consumes: `agent.credential_pool.load_pool`, `agent.account_usage.fetch_account_usage`.

- [ ] **Step 1: Write failing roster and redaction tests**

```python
def test_roster_joins_nickname_by_stable_id_and_redacts_private_fields(tmp_path, fake_pool):
    registry = AliasRegistry(tmp_path / "provider-account-aliases.json")
    registry.replace({"openai-codex": {"ff5cab": "Agentik"}})
    records = load_account_roster(tmp_path, pool_loader=fake_pool)
    assert records[0].owner_name == "Agentik"
    rendered = render_account_roster(records)
    assert "Agentik" in rendered and "ff5cab" in rendered
    assert "@" not in rendered
    assert "access_token" not in rendered


def test_alias_registry_rebinds_nickname_atomically(tmp_path):
    registry = AliasRegistry(tmp_path / "provider-account-aliases.json")
    registry.bind("openai-codex", "Agentik", "old123")
    registry.bind("openai-codex", "Agentik", "new456")
    assert registry.credential_id("openai-codex", "Agentik") == "new456"
    assert registry.owner_name("openai-codex", "old123") is None
    assert registry.path.stat().st_mode & 0o777 == 0o600
```

- [ ] **Step 2: Run the tests and verify RED**

Run:

```bash
PYTHONPATH=/home/operator/src/hermes-agent uv run --with pytest --with httpx --with pyyaml pytest -q \
  tests/test_agk_account_control.py::test_roster_joins_nickname_by_stable_id_and_redacts_private_fields \
  tests/test_agk_account_control.py::test_alias_registry_rebinds_nickname_atomically
```

Expected: FAIL because `agk_account_control.py` and its interfaces do not exist.

- [ ] **Step 3: Implement the focused domain module**

Implement these exact public shapes:

```python
@dataclass(frozen=True)
class AccountRecord:
    provider: str
    credential_id: str
    owner_name: str
    status: str
    priority: int
    windows: tuple[UsageWindow, ...]

class AliasRegistry:
    def __init__(self, path: Path): ...
    def snapshot(self) -> dict[str, dict[str, str]]: ...
    def bind(self, provider: str, owner_name: str, credential_id: str) -> None: ...
    def remove_credential(self, provider: str, credential_id: str) -> None: ...
    def owner_name(self, provider: str, credential_id: str) -> str | None: ...
    def credential_id(self, provider: str, owner_name: str) -> str | None: ...

def load_account_roster(hermes_home: Path, *, pool_loader=load_pool) -> tuple[AccountRecord, ...]: ...
def render_account_roster(records: Iterable[AccountRecord]) -> str: ...
def voice_binding_key(provider: str, owner_name: str) -> str:
    return f"voice-owner:{provider}:{owner_name.casefold()}"
```

Use atomic temporary-file replacement and chmod `0600`. Whitelist provider, nickname, credential ID, status, priority, usage windows, and reset timestamps when rendering.

- [ ] **Step 4: Change voice state identity from credential ID to owner nickname**

Update `DiscordAccountUsageMonitor._sync_voice_channels()` to resolve the stored channel first by `voice_binding_key(provider, account.owner_name)`. During migration, accept an existing `voice:{provider}:{credential_id}` key, move its channel ID to the owner key, and remove the stale key after successful save.

- [ ] **Step 5: Run focused and existing monitor tests**

```bash
PYTHONPATH=/home/operator/src/hermes-agent uv run --with pytest --with httpx --with pyyaml pytest -q \
  tests/test_agk_account_control.py tests/test_agk_account_usage_monitor.py
```

Expected: all PASS.

- [ ] **Step 6: Commit Task 1**

```bash
git add hermes/plugins/platforms/discord/agk_account_control.py \
  hermes/plugins/platforms/discord/agk_account_usage_monitor.py \
  tests/test_agk_account_control.py tests/test_agk_account_usage_monitor.py
git commit -m "feat(discord): add canonical account roster"
```

---

### Task 2: Durable OAuth Attempt Store and Runner

**Files:**
- Create: `hermes/plugins/platforms/discord/agk_account_oauth.py`
- Create: `scripts/agk_provider_oauth_runner.py`
- Test: `tests/test_agk_account_oauth.py`

**Interfaces:**
- Produces: `OAuthAttempt`, `OAuthAttemptStore`, `OAuthRunner.start()`, `OAuthRunner.submit_claude_code()`, `OAuthRunner.cancel()`.
- Consumes: `hermes auth add <provider> --type oauth --label <alias> --no-browser --timeout 900`.

- [ ] **Step 1: Write failing attempt lifecycle tests**

```python
def test_only_one_live_attempt_per_provider_and_nickname(tmp_path):
    store = OAuthAttemptStore(tmp_path)
    first = store.create("openai-codex", "add", "Agentik", None, 1441423462492016821)
    second = store.create("openai-codex", "add", "Agentik", None, 1441423462492016821)
    assert store.get(first.attempt_id).status == "cancelled"
    assert store.get(second.attempt_id).status == "pending"


def test_claude_code_submission_rejects_wrong_owner_channel_or_expired_attempt(tmp_path):
    store = OAuthAttemptStore(tmp_path)
    attempt = store.create("anthropic", "add", "Loumna", None, 1441423462492016821)
    runner = OAuthRunner(store, fake_systemd())
    assert runner.submit_claude_code(attempt.attempt_id, "code#state", user_id=7, channel_id=1) is False
```

- [ ] **Step 2: Run tests and verify RED**

```bash
PYTHONPATH=/home/operator/src/hermes-agent uv run --with pytest --with pyyaml pytest -q tests/test_agk_account_oauth.py
```

Expected: FAIL because the module does not exist.

- [ ] **Step 3: Implement attempt records and mode-safe storage**

```python
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

class OAuthAttemptStore:
    def create(self, provider, operation, owner_name, target_credential_id, user_id,
               guild_id=1541131439599386644, channel_id=0) -> OAuthAttempt: ...
    def get(self, attempt_id: str) -> OAuthAttempt | None: ...
    def update(self, attempt_id: str, **changes) -> OAuthAttempt: ...
    def cancel_conflicts(self, provider: str, owner_name: str) -> None: ...
```

Persist only non-secret metadata in `$HERMES_HOME/state/account-oauth/attempts.json`, mode `0600`.

- [ ] **Step 4: Implement the sibling-unit runner**

`OAuthRunner.start()` creates one transient user-systemd unit named `agk-account-oauth-<attempt_id>.service`. Pass provider, alias, FIFO path, state path, and timeout as allowlisted argv. Do not pass codes or tokens in argv.

`scripts/agk_provider_oauth_runner.py` must:

- create mode-0600 FIFO and log;
- allocate a PTY using `script -qec`;
- run exactly `hermes auth add openai-codex|anthropic --type oauth --label <technical_alias> --no-browser --timeout 900`;
- parse only authorization URL/device code/status into a redacted result JSON;
- keep Claude's FIFO open until code submission;
- delete FIFO and raw log on every terminal path.

- [ ] **Step 5: Test command allowlisting, expiry, cancellation, and cleanup**

```bash
PYTHONPATH=/home/operator/src/hermes-agent uv run --with pytest --with pyyaml pytest -q tests/test_agk_account_oauth.py
```

Expected: all PASS; assertions confirm no OAuth code or credential appears in argv or retained JSON.

- [ ] **Step 6: Commit Task 2**

```bash
git add hermes/plugins/platforms/discord/agk_account_oauth.py \
  scripts/agk_provider_oauth_runner.py tests/test_agk_account_oauth.py
git commit -m "feat(auth): add durable Discord OAuth attempts"
```

---

### Task 3: Transactional Add and Reconnect Coordinator

**Files:**
- Create: `hermes/plugins/platforms/discord/agk_account_transactions.py`
- Test: `tests/test_agk_account_transactions.py`

**Interfaces:**
- Consumes: `OAuthAttemptStore`, `AliasRegistry`, Hermes credential pool, canonical credential removal.
- Produces: `AccountTransactionCoordinator.finalize(attempt_id) -> TransactionResult`.

- [ ] **Step 1: Write failing add/reconnect ordering tests**

```python
def test_reconnect_verifies_candidate_before_removing_old(tmp_path, fakes):
    result = coordinator(tmp_path, fakes).finalize("attempt-1")
    assert fakes.events == [
        "backup", "discover-candidate", "probe-candidate", "usage-candidate",
        "bind-nickname", "read-pool", "remove-old", "read-final-pool", "refresh-surfaces",
    ]
    assert result.status == "committed"


def test_failed_candidate_probe_preserves_old_credential(tmp_path, fakes):
    fakes.probe_ok = False
    result = coordinator(tmp_path, fakes).finalize("attempt-1")
    assert "remove-old" not in fakes.events
    assert result.status == "rolled_back"
```

- [ ] **Step 2: Run tests and verify RED**

```bash
PYTHONPATH=/home/operator/src/hermes-agent uv run --with pytest --with pyyaml pytest -q tests/test_agk_account_transactions.py
```

Expected: FAIL because the coordinator does not exist.

- [ ] **Step 3: Implement transaction types and coordinator**

```python
@dataclass(frozen=True)
class TransactionResult:
    status: str
    provider: str
    owner_name: str
    old_credential_id: str | None
    new_credential_id: str | None
    message: str

class AccountTransactionCoordinator:
    def finalize(self, attempt_id: str) -> TransactionResult: ...
```

The coordinator must:

1. create mode-0700 backup directory with mode-0600 `auth.json`, `config.yaml`, alias registry, and SHA-256 manifest;
2. compare pre/post pool IDs to discover exactly one candidate;
3. run exact-credential inference;
4. fetch usage or record `unavailable`;
5. bind nickname atomically;
6. re-read candidate;
7. remove old credential only on reconnect and only after prior gates;
8. assert final counts;
9. request UI/monitor refresh;
10. remove OAuth artifacts.

- [ ] **Step 4: Add rollback and reconciliation-required tests**

Cover registry write failure, candidate cleanup, canonical old-removal failure, duplicate candidate IDs, and post-commit presentation failure. Old-removal failure must return `reconciliation_required` and retain both credentials rather than fabricate success.

- [ ] **Step 5: Run tests**

```bash
PYTHONPATH=/home/operator/src/hermes-agent uv run --with pytest --with pyyaml pytest -q tests/test_agk_account_transactions.py
```

Expected: all PASS.

- [ ] **Step 6: Commit Task 3**

```bash
git add hermes/plugins/platforms/discord/agk_account_transactions.py \
  tests/test_agk_account_transactions.py
git commit -m "feat(auth): add transactional account replacement"
```

---

### Task 4: Private Persistent Discord Account Control Center

**Files:**
- Create: `hermes/plugins/platforms/discord/agk_account_control_ui.py`
- Modify: `hermes/plugins/platforms/discord/adapter.py`
- Test: `tests/test_agk_account_control_ui.py`

**Interfaces:**
- Consumes: roster APIs from Task 1, OAuth runner from Task 2, transaction coordinator from Task 3.
- Produces: `register_account_control_center(bot, adapter)`, `AccountControlView`, `reconcile_account_control_channel()`.

- [ ] **Step 1: Write failing channel permission and post-idempotency tests**

```python
async def test_reconcile_creates_private_channel_and_one_persistent_post(fake_guild, adapter):
    state = await reconcile_account_control_channel(fake_guild, adapter)
    state2 = await reconcile_account_control_channel(fake_guild, adapter)
    assert state.channel_id == state2.channel_id
    assert state.message_id == state2.message_id
    assert fake_guild.created_channels[0].name == "account-control"
    assert fake_guild.created_channels[0].can_view(1441423462492016821)
    assert not fake_guild.created_channels[0].can_view(fake_guild.default_role.id)
```

- [ ] **Step 2: Write failing callback authorization tests**

For every custom ID prefix below, invoke with wrong user, wrong guild, and wrong channel and assert ephemeral rejection with no runner/coordinator call:

```text
agkacct:provider
agkacct:account
agkacct:switch
agkacct:add
agkacct:reconnect
agkacct:refresh
agkacct:close
agkacct:claude-code
agkacct:confirm-reconnect
```

- [ ] **Step 3: Run UI tests and verify RED**

```bash
PYTHONPATH=/home/operator/src/hermes-agent uv run --with pytest --with pytest-asyncio --with pyyaml pytest -q tests/test_agk_account_control_ui.py
```

Expected: FAIL because the UI module does not exist.

- [ ] **Step 4: Implement persistent channel/post reconciliation**

```python
@dataclass(frozen=True)
class AccountControlState:
    channel_id: int
    message_id: int

async def reconcile_account_control_channel(guild, adapter) -> AccountControlState: ...
def register_account_control_center(bot, adapter) -> None: ...
```

Persist state at `$HERMES_HOME/account_control_state.json`, mode `0600`. Use stable component IDs and `timeout=None`. Register the view through `bot.add_view(AccountControlView(...))` at startup.

- [ ] **Step 5: Implement exact user flows**

- Provider select → account select.
- `Switch` calls the existing canonical `_prefer_account_credential(provider, credential_id)` path, re-reads the pool, and refreshes the post. Cover OpenAI and Claude separately and assert automatic quota rotation remains enabled.
- `Add account` → owner-nickname modal → start attempt → ephemeral OAuth instructions.
- `Reconnect` → ephemeral confirmation → start attempt.
- OpenAI response shows only verification URL, device code, alias, and expiry.
- Claude response shows URL and `Submit code` button; modal writes one-time code to the exact active FIFO after re-authorization.
- `Refresh` reloads canonical roster and edits the one persistent post.
- `Close session` cancels only the selected live attempt.

- [ ] **Step 6: Integrate adapter startup without another slash command**

Import and call `register_account_control_center()` during Discord `on_ready`. Do not add a one-off slash command; the persistent post is the primary interface and `/account` remains the compatibility/ephemeral account panel.

- [ ] **Step 7: Run UI and existing Discord tests**

```bash
PYTHONPATH=/home/operator/src/hermes-agent uv run --with pytest --with pytest-asyncio --with pyyaml pytest -q \
  tests/test_agk_account_control_ui.py tests/test_discord_station_session_ui.py \
  tests/test_agk_account_usage_monitor.py
```

Expected: all PASS.

- [ ] **Step 8: Commit Task 4**

```bash
git add hermes/plugins/platforms/discord/agk_account_control_ui.py \
  hermes/plugins/platforms/discord/adapter.py tests/test_agk_account_control_ui.py
git commit -m "feat(discord): add private account control center"
```

---

### Task 5: Bootstrap, Legacy-Channel Removal, and Cross-Surface Refresh

**Files:**
- Modify: `scripts/sync-hermes.sh`
- Modify: `install.sh`
- Modify: `hermes/plugins/platforms/discord/agk_account_usage_monitor.py`
- Modify: `hermes/plugins/platforms/discord/adapter.py`
- Modify: `tests/test_agk_account_usage_monitor.py`
- Create: `tests/test_agk_account_control_install.py`
- Mirror: `/home/operator/src/Station/overlay/` matching changed canonical files.

**Interfaces:**
- Consumes: account-control channel/post reconciler and owner-keyed voice bindings.
- Produces: future-install configuration and immediate cross-surface refresh hook.

- [ ] **Step 1: Write failing install and legacy-name tests**

```python
def test_future_install_enables_private_account_control_center():
    source = Path("scripts/sync-hermes.sh").read_text() + Path("install.sh").read_text()
    assert "account_control_category_id" in source
    assert "1542505218569150585" in source
    assert "account_control_owner_user_id" in source
    assert "1441423462492016821" in source


def test_legacy_text_channels_are_not_auto_created():
    source = Path("hermes/plugins/platforms/discord/agk_account_usage_monitor.py").read_text()
    assert 'create_text_channel(self.config.claude_channel_name' not in source
    assert '"station-account-capacity"' not in source
```

- [ ] **Step 2: Run tests and verify RED**

```bash
PYTHONPATH=/home/operator/src/hermes-agent uv run --with pytest --with pyyaml pytest -q tests/test_agk_account_control_install.py
```

Expected: FAIL on missing config and remaining legacy auto-create behavior.

- [ ] **Step 3: Implement bootstrap config through `hermes config set`**

Configure Operator only:

```text
platforms.discord.extra.account_control_enabled=true
platforms.discord.extra.account_control_category_id=1542505218569150585
platforms.discord.extra.account_control_owner_user_id=1441423462492016821
platforms.discord.extra.account_control_channel_name=account-control
platforms.discord.extra.account_control_oauth_timeout_seconds=900
```

Do not hand-edit `config.yaml` and do not place non-secret settings in `.env`.

- [ ] **Step 4: Remove legacy text-panel auto-creation**

The usage monitor must no longer search for or create `claudecode-all-accounts` or `station-account-capacity`. Detailed roster information moves to `account-control`. Voice monitoring remains independent.

- [ ] **Step 5: Add immediate refresh hook**

After a committed transaction, invoke:

```python
await adapter.refresh_account_surfaces(reason="account-transaction")
```

This method re-renders the persistent post and calls one monitor refresh without restarting the gateway.

- [ ] **Step 6: Synchronize Station overlay and run install tests**

```bash
PYTHONPATH=/home/operator/src/hermes-agent uv run --with pytest --with pytest-asyncio --with pyyaml pytest -q \
  tests/test_agk_account_control_install.py tests/test_agk_account_control.py \
  tests/test_agk_account_oauth.py tests/test_agk_account_transactions.py \
  tests/test_agk_account_control_ui.py tests/test_agk_account_usage_monitor.py
```

Expected: all PASS.

- [ ] **Step 7: Commit Task 5**

```bash
git add scripts/sync-hermes.sh install.sh hermes/plugins/platforms/discord \
  tests/test_agk_account_control_install.py tests/test_agk_account_usage_monitor.py
git commit -m "feat(station): provision account control center"
```

---

### Task 6: Independent Review, Recoverable Deployment, and Live Acceptance

**Files:**
- Deploy changed plugin/scripts into `/opt/agk-terminal/hermes-agent`, `/usr/local/lib/agk-terminal`, and `/home/operator/.hermes`.
- Preserve backups under `/home/operator/workspace/account-control-deploy/<timestamp>/`.

**Interfaces:**
- Consumes: all prior tasks.
- Produces: verified live `account-control` channel and persistent post.

- [ ] **Step 1: Run independent code review**

Review the task diff for authorization bypass, secret leakage, shell injection, OAuth-attempt races, incorrect credential removal, duplicate channels/messages, and gateway-child OAuth processes. Apply only findings that are reproducible and in scope.

- [ ] **Step 2: Run focused and full affected quality gates**

```bash
PYTHONPATH=/home/operator/src/hermes-agent uv run --with pytest --with pytest-asyncio --with httpx --with pyyaml pytest -q \
  tests/test_agk_account_control.py tests/test_agk_account_oauth.py \
  tests/test_agk_account_transactions.py tests/test_agk_account_control_ui.py \
  tests/test_agk_account_control_install.py tests/test_agk_account_usage_monitor.py
python3 -m py_compile hermes/plugins/platforms/discord/agk_account_*.py \
  hermes/plugins/platforms/discord/adapter.py scripts/agk_provider_oauth_runner.py
git diff --check
```

Expected: zero failures, zero compile errors, zero whitespace errors.

- [ ] **Step 3: Create recoverable backup and deploy identical copies**

Back up every target file with SHA-256 manifest. Install canonical files to active shared runtime, bootstrap mirror, and Operator profile. Verify all deployed hashes match canonical source.

- [ ] **Step 4: Reload only Operator once**

Use the existing one-shot sibling timer pattern so the command survives its own gateway reload. Do not restart Agentik, Mission, Private, Collective, or Nutrition.

- [ ] **Step 5: Read back the live Discord artifact**

Verify through Discord REST:

- one `account-control` text channel under `Tokens`;
- denied `@everyone` visibility and allowed Gareth/Operator visibility;
- one persistent roster message;
- every current nickname appears exactly once;
- both legacy channel IDs return `404` and no channel with either legacy name exists;
- all current voice quota channels remain present.

- [ ] **Step 6: Exercise one non-destructive OAuth start/cancel**

Start one attempt, verify the URL/device data appears only ephemerally, verify its systemd sibling unit exists, cancel it, and assert FIFO/log/unit cleanup. Do not authorize or mutate a live provider account in this acceptance step.

- [ ] **Step 7: Verify runtime health and no sync storm**

Read Operator gateway PID/status and bounded logs. Require `active/running`, no restart loop, no account-control traceback, no leaked secret, and no repeated Discord command synchronization.

- [ ] **Step 8: Commit deployment metadata only if the repository tracks it**

Do not commit backups, OAuth state, message IDs, channel IDs discovered at runtime, or secrets. Report real channel ID, message ID, tests, hashes, and gateway PID in the final response only.
