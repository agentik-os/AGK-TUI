# Station Account Control Center — Design

**Date:** 2026-08-27  
**Status:** Approved in Discord design review  
**Owner:** Gareth  
**Operating boundary:** Operator profile, AGK Discord server, `Tokens` category

## 1. Objective

Create one private Discord Account Control Center that lets Gareth inspect, add, and reconnect the Station's OpenAI Codex and Claude Code Max accounts without handling reusable secrets in Discord.

Every successful account mutation must propagate through the existing canonical systems:

1. Hermes credential pool and rotation;
2. redacted owner-nickname registry;
3. persistent Discord account roster;
4. the existing `/account` panel;
5. per-account voice quota channels;
6. automatic quota/failover operation.

The feature replaces the legacy `station-account-capacity` and `claudecode-all-accounts` text channels. Those channels have been removed and must never be recreated.

## 2. Scope

### Included

- A private text channel named `account-control` under Discord category `Tokens`.
- One persistent, idempotently upserted account roster post.
- Gareth-only interactive controls for OpenAI and Claude.
- Add-account and reconnect-account workflows.
- OpenAI device-code OAuth.
- Claude PKCE OAuth with one-time code submission.
- Exact-credential verification before pool mutation becomes final.
- Transactional replacement of an existing credential after successful reconnect.
- Automatic synchronization to `/account`, voice quota channels, and provider rotation.
- Installation/bootstrap support for future AGK Station deployments.

### Excluded

- Password collection.
- Access-token, refresh-token, API-key, email, JWT-claim, or raw provider-error display in Discord.
- Public account management.
- Adding providers other than `openai-codex` and `anthropic` in this first version.
- Rebuilding Hermes' credential-pool implementation or creating a second account database.
- Removing a working credential before its replacement has passed verification.

## 3. Security and authorization

The channel and its post are private to Gareth and the Operator bot. Channel permission overwrites must deny `VIEW_CHANNEL` to `@everyone` and allow only the authorized owner and Operator.

Every select, button, modal, and resumed callback must re-check all of:

- Discord guild ID;
- channel ID;
- authorized owner user ID;
- expected provider;
- immutable account or attempt identifier;
- attempt expiry.

The authorization check at initial panel creation is not sufficient.

Discord may carry only temporary OAuth material:

- OpenAI device URL and device code;
- Claude attempt-specific authorization URL;
- Claude one-time authorization code submitted through an ephemeral modal.

Discord must never receive passwords, reusable provider credentials, access tokens, refresh tokens, API keys, account emails, JWT claims, or raw provider response bodies.

## 4. Canonical data ownership

### Credential pool

Hermes `auth.json` and `agent.credential_pool` remain authoritative for credentials, priority, status, rotation, refresh, and removal.

### Owner nickname registry

`$HERMES_HOME/provider-account-aliases.json` remains the redacted identity map. It stores only stable technical aliases, owner-supplied nicknames, stable Hermes credential IDs, provider, redacted status, and verification metadata. It remains mode `0600`.

A nickname maps to exactly one active credential per provider. Pool order or priority must never be used as identity.

### Discord state

Discord stores message and channel IDs only. It is a control and presentation surface, not an account database.

## 5. Persistent Discord roster

The `account-control` channel contains one persistent post. Startup and refresh logic must edit the existing post rather than create duplicates.

The roster displays only:

- owner nickname;
- provider label (`OpenAI` or `Claude`);
- stable credential ID;
- state: `ok`, `exhausted`, `dead`, `unknown`, or `reconnect required`;
- provider quota-window label;
- percentage used and remaining;
- reset time when available.

Missing provider usage is rendered as `unavailable`, never `0%`.

The persistent view exposes:

- provider select: OpenAI / Claude;
- account select populated from the live pool;
- `Reconnect`;
- `Add account`;
- `Refresh`;
- `Close session` for an active temporary OAuth session.

The roster remains visible while sensitive interaction responses are ephemeral.

## 6. OAuth attempt model

Each OAuth attempt has an immutable record containing:

- random `attempt_id`;
- provider;
- operation: `add` or `reconnect`;
- owner nickname;
- target credential ID for reconnect, if any;
- Discord guild, channel, and owner user IDs;
- creation and expiry times;
- runner unit identity;
- relay/modal state;
- terminal status.

Only one live attempt may exist for the same provider and nickname. Starting a new attempt cancels and invalidates the previous one.

OAuth runners execute as bounded user-systemd sibling units, not gateway children. A gateway reload must not kill the active verifier, FIFO, or polling process. Runtime files use mode `0700/0600`, live under `$XDG_RUNTIME_DIR` and `$HERMES_HOME/state/oauth`, and are deleted after success, failure, cancellation, or timeout.

## 7. Add-account workflow

1. Gareth selects OpenAI or Claude and clicks `Add account`.
2. An ephemeral modal requests one non-sensitive owner nickname.
3. The server validates uniqueness and starts one bounded OAuth attempt.
4. OpenAI presents the provider verification URL and device code.
5. Claude presents one PKCE URL and later an ephemeral code-submission modal bound to that exact attempt.
6. Hermes inserts the candidate credential beside the existing pool.
7. The system discovers the exact new credential ID.
8. The candidate passes exact-credential verification.
9. The nickname registry is updated atomically.
10. The pool, persistent roster, `/account`, and voice monitor are refreshed.
11. A new voice quota channel is created for the nickname.

If any pre-commit step fails, the candidate is removed canonically and the previous pool remains unchanged.

## 8. Reconnect workflow

1. Gareth selects an existing nickname and clicks `Reconnect`.
2. An ephemeral confirmation identifies only nickname, provider, and stable credential ID.
3. A candidate credential is connected beside the old credential.
4. The candidate passes exact-credential inference and usage verification.
5. The nickname mapping moves atomically from the old credential ID to the new one.
6. The new credential is re-read from the live pool.
7. The old credential is removed through Hermes' canonical credential-removal path.
8. The final pool is re-read and must contain the new credential exactly once and the old credential zero times.
9. The existing voice channel is retained by provider plus owner nickname and rebound to the new credential ID.
10. The roster and `/account` refresh immediately.

The old credential must not be removed if candidate verification, registry writing, or final pool reconciliation fails.

## 9. Exact-credential verification

### OpenAI Codex

Create a temporary mode-`0700` Hermes home containing only the candidate credential and minimal Codex configuration. Run one tiny bounded inference probe. Record only credential ID, exit status, and pass/fail. Delete the temporary home.

### Claude

Run one bounded child inference with only the candidate OAuth token injected through the child environment. The token is never placed in argv or output. Record only credential ID, exit status, and pass/fail.

### Usage

Fetch usage with the canonical account-usage API. Store/render only whitelisted windows, used/remaining percentages, reset timestamps, and availability status.

## 10. Synchronization behavior

After every successful transaction:

- `/account` reads the new live pool on Refresh;
- the persistent roster post is edited immediately;
- the provider pool rotation contains the new credential;
- a replaced credential is absent from rotation;
- a new account produces one voice channel;
- a reconnected account reuses its existing voice channel by provider plus nickname;
- the monitor state updates from the old credential ID to the new one;
- provider quota refresh continues every five minutes;
- voice channel names continue to show percentage used;
- detailed account views may continue to show explicit used and remaining percentages.

No gateway restart is required for individual account additions or reconnections.

## 11. Error handling and rollback

Before a mutation, create a timestamped mode-`0700` backup containing mode-`0600` copies of `auth.json`, `config.yaml`, the nickname registry, and a SHA-256 manifest.

Failure rules:

- timeout or cancellation: remove attempt artifacts; do not mutate the pool;
- stale Claude code: reject it and require a fresh URL/attempt;
- wrong user/channel/alias: reject without revealing attempt state;
- candidate authentication failure: remove only the candidate;
- registry write failure: retain old credential and remove candidate;
- old-credential removal failure: retain both temporarily, mark reconciliation required, and do not claim success;
- post/voice refresh failure after committed credential mutation: retain the committed pool, mark presentation reconciliation pending, and retry from canonical state.

Raw provider error bodies are redacted before logs and never displayed in Discord.

## 12. Discord lifecycle

The account-control view uses stable namespaced component IDs and is registered as a persistent view at gateway startup.

The system records only the channel ID and persistent message ID in the Operator profile state. Startup reconciliation:

1. resolves or creates the private `account-control` channel;
2. verifies permission overwrites;
3. fetches the stored post;
4. edits it if present or creates exactly one replacement if missing;
5. removes no unrelated messages;
6. registers the persistent view;
7. renders current canonical state.

## 13. Installation and release boundaries

The feature must be applied consistently to:

- AGK-TUI canonical source;
- Station overlay/bootstrap mirror;
- active shared Hermes installation;
- Operator profile plugin copy;
- future-install configuration and tests.

Only Operator's gateway is reloaded for deployment. OAuth attempts themselves run outside the gateway cgroup and do not trigger reloads.

The removed legacy text-channel names must not remain in auto-create paths or bootstrap configuration.

## 14. Test strategy

### Unit tests

- redacted roster rendering;
- nickname-to-credential reconciliation independent of pool order;
- persistent message idempotency;
- component authorization on every callback;
- attempt expiry and stale-code rejection;
- one live attempt per provider/nickname;
- add and reconnect state machines;
- candidate-before-old replacement ordering;
- rollback paths;
- voice-channel reuse by nickname;
- new-account voice-channel creation;
- no secret fields in Discord or logs.

### Integration tests

- fake systemd runner with bounded OAuth fixtures;
- OpenAI device-flow start/poll/success/failure;
- Claude PKCE start/code/success/failure;
- exact credential count changes;
- canonical removal path;
- pool rotation after add/reconnect;
- `/account`, roster, and voice monitor refresh from the same fixtures;
- gateway restart while a sibling OAuth attempt remains alive.

### Live acceptance

- private channel exists under `Tokens`;
- permission overwrites are read back;
- exactly one roster post exists;
- every current OpenAI and Claude nickname appears once;
- `Refresh` works in the exact channel;
- one non-destructive OAuth start/cancel path is exercised;
- no duplicate text or voice channels appear;
- legacy channels remain absent;
- Operator gateway remains active with no restart loop or Discord sync storm.

## 15. Acceptance criteria

The feature is complete only when all of the following are verified:

- private `account-control` channel and one persistent roster post;
- Gareth-only channel visibility and callback authorization;
- live OpenAI and Claude roster with correct owner nicknames;
- functional OpenAI device-link/code workflow;
- functional Claude link/code workflow;
- add-account and reconnect-account paths;
- verified candidate before automatic old-credential replacement;
- no pool mutation on failed OAuth;
- automatic propagation to `/account`, provider rotation, and voice channels;
- voice-channel reuse for reconnect and creation for add;
- no reusable secret or private provider identity exposed;
- durable OAuth attempts independent from gateway lifetime;
- cleanup of temporary artifacts;
- synchronized canonical, bootstrap, installed, and profile copies;
- future AGK installations provision the same control surface;
- deleted legacy channels are not recreated.
