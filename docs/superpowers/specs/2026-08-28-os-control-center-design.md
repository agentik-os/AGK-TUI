# AGK OS Control Center and Dedicated Runtime Contract

Date: 2026-08-28
Status: approved design
Owner: Operator / `administrator`
Primary repository: AGK-TUI

## 1. Purpose

Make every installed AGK Operative System a complete, inspectable runtime product rather than only a package or skill. Every OS must have a dedicated Hermes profile and at least one owning agent. Discord integration remains optional: an OS may reuse its environment bot through explicit routing, or use a dedicated Discord application and gateway.

Expose the lifecycle through one registry-driven `/os` Discord control center. The control center must guarantee that reusable bot tokens never enter Discord and can only be installed through one-time Tailnet Secure Input after the application is installed in the exact AGK guild.

## 2. Non-goals

- Do not create Discord applications, accept OAuth grants, solve CAPTCHA, enable privileged intents, or fabricate tokens automatically.
- Do not copy tokens, OAuth refresh credentials, memories, sessions, or private state between Linux homes or Hermes profiles.
- Do not require a dedicated Discord bot for every OS.
- Do not make text-only slash output the primary interface.
- Do not restart the whole gateway fleet for one OS.
- Do not impose Station owner styling on client-facing products.

## 3. Required OS runtime contract

An OS may be marked `active` only when all required objects are present and verified:

1. versioned package and immutable registry entry;
2. dedicated Hermes profile;
3. at least one owning agent;
4. provider and fallback policy;
5. skills, tools and MCP/Composio allowlists;
6. doctor, update and rollback contracts;
7. explicit Discord mode;
8. current acceptance evidence.

### 3.1 Discord modes

`environment`:
- reuse the owning environment bot;
- create an explicit channel/profile route;
- never copy the environment bot token into the OS profile;
- do not create a second gateway.

`dedicated`:
- use a dedicated Discord application and bot identity;
- store the token only in the OS profile secret store;
- use a dedicated gateway unit;
- require exact identity, guild membership, channel access and end-to-end proof.

`disabled`:
- no Discord route or token;
- package/profile/agent lifecycle remains valid.

## 4. Registry schema

Each current-version OS registry entry gains a normalized runtime section:

```yaml
runtime_contract:
  hermes:
    profile_id: builder-os
    owner_environment: operator
    required: true
    provider: openai-codex
    model: gpt-5.6-sol
    fallback:
      provider: agk-gemma-local
      model: gemma4:26b
    doctor_state: ready
  agents:
    required: true
    owner_ids: [master-os-builder]
  discord:
    mode: environment | dedicated | disabled
    application_id: null
    guild_id: "1541131439599386644"
    category_id: null
    channel_id: null
    gateway_unit: null
    secure_input_state: not-required | owner-prerequisite | ready | installed
  lifecycle:
    state: staged | active | blocked | rollback-ready
    active_version: 0.2.0
    rollback_version: 0.1.0
    last_doctor_evidence: null
```

Rules:
- profile and agent fields are mandatory for every active OS;
- Discord application IDs are public metadata;
- tokens and credential-derived values never enter the registry;
- current version is one registry row per OS; previous package bytes remain as rollback artifacts outside the active index;
- mutations are atomic and idempotent.

## 5. Builder OS changes

Builder OS advances from `0.1.0` to the next compatible release and adds an `os-runtime-delivery` stage after package build.

The stage must:

1. create or reconcile the dedicated Hermes profile;
2. create or reconcile at least one owning agent;
3. configure provider and fallback without copying credentials;
4. choose Discord mode explicitly;
5. generate doctor and rollback evidence;
6. refuse `COMPLETE` while a required object is absent;
7. append the runtime contract to the registry and package verification report.

Master OS Builder's complete-delivery workflow remains authoritative. The compact Builder OS manifest and build-cycle must reference the same profile/agent/Discord invariants so lightweight builds cannot bypass them.

## 6. Discord `/os` control center

`/os` opens one `discord.ui.View` generated from the live OS registry.

### 6.1 Main interaction

- one OS select, paginated at 25 entries;
- concise status for package, profile, agent, provider, Discord and gateway;
- buttons: `Install`, `Repair`, `Doctor`, `Discord`, `Refresh`, `Back`, `Close`;
- no decorative embed grid or duplicate prose;
- authorization rechecked on every select, button and modal callback;
- sensitive mutations use ephemeral staged confirmation;
- typed commands remain compatibility fallback.

### 6.2 State machine

```text
ABSENT
  -> PACKAGE_READY
  -> PROFILE_READY
  -> AGENT_READY
  -> PROVIDER_READY
  -> DISCORD_DISABLED | ENVIRONMENT_ROUTE_READY | DEDICATED_OWNER_PREREQUISITE
  -> DOCTOR_READY
  -> ACTIVE
```

Any failed gate moves the OS to `BLOCKED` with one exact next action. `Repair` resumes from the first failed invariant and never repeats completed stages.

## 7. Dedicated bot onboarding

The secure order is mandatory:

1. Owner creates the Discord application and bot in the Developer Portal.
2. Owner enters the public Application ID in an `/os` modal.
3. `/os` generates a least-privilege OAuth URL locked to the AGK guild.
4. Owner authorizes the application in Discord.
5. `Refresh` verifies that the exact application bot is a guild member and that the target channel exists.
6. Only then does `Secure Input` become available.
7. Secure Input creates a random, expiring Tailnet HTTPS route.
8. The token is submitted only through that route.
9. The installer validates `/users/@me`, `/oauth2/applications/@me`, exact bot/application identity, exact guild membership and expected Application ID.
10. The token is atomically written as `DISCORD_BOT_TOKEN` to the dedicated OS profile `.env`, mode `0600`.
11. The route self-destructs before the terminal HTTP response completes.
12. The dedicated gateway is installed, enabled and started only after profile doctor passes.

The response may expose only bot ID, username, application ID, guild ID and least-privilege invite URL. It must never echo, hash, log or return the token.

## 8. Environment-bot onboarding

When `discord.mode=environment`:

- `/os` verifies the environment bot identity and exact channel;
- it writes only non-secret route metadata to the OS runtime contract;
- it installs a profile/channel routing binding;
- the environment profile remains the sole token owner;
- no new gateway service is created;
- bot-authored messages remain ignored unless an explicit inter-agent delegation requires them.

## 9. Profile and agent provisioning

Dedicated profiles use canonical kebab IDs and remain under the owning Linux user's Hermes root. Provisioning must reject traversal, symlinked profile roots and cross-home destinations.

Each profile declares:
- SOUL/persona;
- provider, model and fallback;
- skills and toolsets;
- MCP/Composio policy;
- memory scope;
- approval policy;
- OS registry identity;
- optional Discord home channel and gateway.

At least one registry-backed owning agent must reference the profile and OS. Installation is incomplete if the agent manifest, prompt or profile binding is missing.

## 10. Migration of current OS inventory

The migration is preview-first and non-destructive.

- Builder OS: dedicated profile `builder-os`; owning agent `master-os-builder`; environment bot by default.
- Evaluation OS: dedicated profile `evaluation-os`; owning agent `evidence-auditor`; Discord disabled by default.
- Research OS: dedicated profile `research-os`; owning agent `oracle`; Discord disabled by default.
- Strategy OS: dedicated profile `strategy-os`; owning agent `product-strategy`; Discord disabled by default.
- Nutrition OS: preserve dedicated profile `nutrition-os`; owning agent `nutrition-specialist`; dedicated bot mode remains blocked until owner OAuth installs application `1542135948475637861` into AGK, then Secure Input validates and stores the token.

Existing profile data, secrets, memories, sessions and OAuth state are preserved. Migration never silently activates a new Discord bot or channel.

## 11. Failure handling

- Missing application: owner prerequisite, no token form.
- Application absent from guild: show OAuth action, no token form.
- Token identity mismatch: reject and keep no bytes.
- Token bot not in exact guild: reject and keep no bytes.
- Existing token belongs to another profile/OS: reject reuse.
- Provider unavailable: fallback required before activation.
- Gateway down: enabled/non-masked units are eligible for bounded watchdog start; maintenance/drain markers prevent recovery.
- Discord 429: honor `retry_after`; do not restart gateways to force command sync.
- Any durable archive/registry/profile write failure: abort before process termination or activation.

## 12. Security boundaries

- No Discord token in commands, modals, messages, artifacts, logs or registry.
- Secure Input is Tailnet-only, HTTPS, no-store, CSRF-protected, size-limited, attempt-limited and expiring.
- The owning profile `.env` is the only dedicated-token destination.
- Application creation, OAuth authorization, intents and billing remain owner-controlled.
- Every callback rechecks owner authorization.
- Destructive lifecycle actions require exact target restatement and ephemeral confirmation.
- Cross-profile actions run under the owning UID and expose only bounded public metadata to Operator.

## 13. Acceptance matrix

### Automated

- registry schema and migration tests;
- Builder OS manifest/workflow tests;
- profile path and symlink boundary tests;
- agent/profile binding tests;
- `/os` View, select pagination, callback authorization and confirmation tests;
- dedicated/environment/disabled mode tests;
- Application ID and OAuth URL tests;
- Secure Input RED/GREEN adversarial tests;
- token non-disclosure tests;
- gateway unit generation and watchdog tests;
- doctor/update/rollback tests;
- install and future-install mirror tests.

### Live canary

- install one OS profile and owning agent;
- verify provider and fallback inference;
- verify `/os` status and controls in Discord;
- verify owner OAuth prerequisite state without creating an application;
- verify Secure Input using a non-production dummy credential path where safe;
- for an already authorized real bot, verify identity, websocket, inbound non-empty text, authorization, inference, outbound response and native readback;
- exercise rollback and confirm no unrelated gateway PID changes.

## 14. Rollout

1. add schema and read-only catalog projection;
2. add Builder OS invariants;
3. add profile/agent reconciliation functions;
4. add `/os` read-only UI;
5. add Discord mode mutations and confirmations;
6. integrate OAuth prerequisite and Secure Input;
7. migrate current OS entries in dry-run;
8. apply profile/agent migrations;
9. run one live canary;
10. activate `/os` for Operator;
11. verify full fleet and retain rollback manifests.

No fleet-wide gateway restart is permitted. Reload only the exact gateway whose command registry or profile runtime changed, using Station safe reload semantics.

## 15. Completion criteria

The mission is complete only when:

- every active OS has a dedicated Hermes profile and owning agent;
- every OS has an explicit Discord mode;
- Builder OS enforces the contract;
- `/os` is a real dynamic Discord View;
- dedicated bot onboarding follows Application ID -> OAuth -> Secure Input;
- token storage and non-disclosure tests pass;
- migrated OS doctors pass;
- a live canary passes runtime and rollback acceptance;
- Discord and gateway mutations are read back exactly;
- source, installed and future-install copies agree;
- all affected tests and full acceptance suites pass.
