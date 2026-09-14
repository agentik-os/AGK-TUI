# Station Rules, Meetings, Provider Capacity, and Auto-Threads

**Date:** 2026-08-27  
**Status:** Design approved in chat, pending written-spec review  
**Owner:** Gareth  
**Operator:** AGK Operator  
**Canonical scope:** Station = Hermes + AGK + Discord

## 1. Objective

Deliver four coordinated Station capabilities without weakening Linux-user, client, project, credential, or conversation isolation:

1. a global AGK-TUI rule plane whose explicitly global rules are effective across Operator, Agentik, Mission, Private, and Collective;
2. a real-time meeting cockpit in Discord channel `1542526309211570226` for all Cal.com bookings and all relevant Google Calendar meetings under `x@agentik-os.com`;
3. live OpenAI Codex and Claude Code account-capacity panels rooted at Discord channel `1542505478679171164`;
4. lobby-style Discord channels where each root conversational message creates one thread linked to one canonical Hermes session visible and resumable from the TUI.

Every implementation phase must include a focused self-review for errors caused by broad context, ambiguous scope, incorrect identifiers, partial deployment, stale installed copies, and unsupported success claims.

## 2. Non-negotiable boundaries

- No secrets through Discord, chat, issue trackers, repositories, logs, URLs, or CLI arguments.
- No cross-user reads of conversations, memories, credentials, private files, or other private state.
- No client design contamination.
- No production deployment or paid service activation without explicit owner authorization.
- Do not claim all Stations are standardized until each target's loaded rules and templates are verified from Operator.
- Project rules remain in the project repository or workspace and never enter the global AGK-TUI rule registry automatically.
- A rule is distributed globally only when the owner explicitly classifies it as an AGK/Station rule.
- Existing legitimate local overlays, including `mission-discord-routing`, must survive global synchronization.
- Discord remains a control surface. Hermes sessions, meeting state, provider pools, and databases remain canonical.
- Use the existing `discord.py` transport. Do not deploy a second competing bot framework.
- Every Discord component and modal callback re-checks actor, guild, channel, profile, target, role, and permission.
- Sensitive and destructive actions use an ephemeral confirmation flow and exact-target readback.

## 3. Current verified state

Operator-side probes confirmed:

- `/etc/agk-terminal/rules.yaml` currently contains 11 canonical global rules.
- Operator, Agentik, and Private load those 11 rules directly from the system registry.
- Mission and Collective load the same 11 global rules plus the local `mission-discord-routing` overlay.
- Missing per-user overlay files in Operator, Agentik, or Private do not mean missing effective rules; the active loader inherits the system registry.
- The existing Discord adapter already contains an OpenAI/Claude account-usage monitor and thread primitives.
- Existing implementation evidence is not sufficient to declare the requested meeting cockpit, fleet-wide lobby auto-threading, or final capacity-channel readback complete.

## 4. Global Rule Plane

### 4.1 Authority

`config/rules.yaml` in the AGK-TUI release source is the versioned source. `/etc/agk-terminal/rules.yaml` is the installed canonical registry used by active Station loaders.

A new privileged Rule Plane operation accepts a typed rule with:

- immutable rule ID;
- title;
- content;
- enabled state;
- provider scope;
- explicit classification: `station_global` or `project_local`;
- authoring Station identity;
- owner approval evidence;
- revision metadata.

Only `station_global` rules can be promoted into the canonical registry. `project_local` rules are refused by the global operation and must be written in the relevant project context file.

### 4.2 Promotion from any Station identity

When Gareth says in Private, Mission, Agentik, Collective, or Operator that a rule is for AGK or the Station:

1. the originating agent submits a non-secret typed proposal to Operator through `station_interagent`;
2. Operator validates the rule ID, classification, provider scope, and owner authorization;
3. Operator updates the versioned source and installed registry atomically;
4. the synchronizer merges canonical rule IDs into every explicit home/profile projection;
5. local-only rules survive;
6. provider-native managed blocks are regenerated under the owning Linux user;
7. effective rules are loaded in a fresh process for each target and compared by ID and content hash;
8. the result reports every target as PASS, BLOCKED, or FAILED.

A profile cannot directly write another profile's files. Operator performs controlled distribution from the administrative boundary.

### 4.3 Project-rule isolation

Project rules live only in project context such as `AGENTS.md`, `.hermes.md`, `CLAUDE.md`, or `.cursorrules`. The global synchronizer must not scan project repositories for rules and must reject project filesystem paths as global rule inputs.

### 4.4 Acceptance

- A fixture global rule proposed from each Station identity becomes effective in all five targets.
- A fixture project rule cannot enter the canonical global registry.
- `mission-discord-routing` survives.
- No private content is read to perform synchronization.
- Installed source, release source, provider projections, and effective runtime output agree.

## 5. Meeting Registry and Cockpit

### 5.1 Scope

The registry includes:

- every Cal.com booking accessible through the owner-authorized connection;
- every relevant meeting from the Google Calendars associated with `x@agentik-os.com`;
- Google Meet, Zoom, and Microsoft Teams links;
- link-less calendar events as visible but unarmed meetings.

Focus blocks, meals, reminders, and ordinary events without a supported call link remain visible only when useful but do not schedule a bot.

### 5.2 Canonical identity and deduplication

One real meeting must produce one registry record, one Discord thread, and at most one Vexa bot.

Identity priority:

1. Google Calendar provider event UID;
2. Cal.com booking UID and destination-calendar UID;
3. normalized call URL plus bounded start-time window and organizer;
4. controlled reconciliation by time and participants.

Ambiguous candidates remain separate and raise an operator-visible reconciliation warning. The system never guesses a destructive merge.

### 5.3 Event flow

```text
Cal.com webhooks ─────────┐
Google Calendar sync ─────┼──> Meeting Registry ──> Discord cockpit/thread
Vexa lifecycle/webhook ───┤          │
Granola webhook/API ──────┘          └──> report reconciler
```

Cal.com and Granola webhooks require signature verification, bounded timestamps, event-ID deduplication, fast acknowledgement, and queued processing. Google Calendar receives periodic reconciliation so missed events do not create permanent drift.

### 5.4 Discord channel `1542526309211570226`

The channel contains a compact, edited-in-place upcoming-meetings surface. Every canonical meeting has exactly one durable thread.

The meeting interface provides native controls:

- Join call;
- Open thread;
- Refresh;
- Reschedule;
- Cancel;
- Disable or enable recording for the exact meeting;
- Send bot now;
- Remove bot.

Reschedule and Cancel require an ephemeral confirmation and authoritative readback from Cal.com or the source calendar before success is displayed.

### 5.5 Thread lifecycle

Before the call, the thread shows time, attendees, source, join URL, preparation context, and bot schedule state.

During the call, it shows lifecycle states such as `joining`, `awaiting_admission`, `recording`, `completed`, or `failed`. It does not stream a noisy full transcript by default.

After the call, the same thread receives an edited-in-place canonical report containing:

- summary;
- decisions;
- action items;
- owners and deadlines where supported by evidence;
- transcript link or attachment;
- source links for Granola and Vexa;
- capture-quality and reconciliation status.

Thread names remain bounded and clean, for example `2026-08-27 · Client discovery · completed`.

## 6. Meeting Capture: Vexa Pilot and Granola

### 6.1 Chosen architecture

Run a 30-day pilot of Vexa self-hosted on the AGK VPS, with Granola running in parallel. The pilot does not authorize paid deployment or production activation by itself.

Vexa runs on the VPS through isolated Docker workloads because it needs dynamic browser containers, scheduler control, temporary media storage, and predictable process/network access. Railway may host a small webhook/API component later, but it is not the initial meeting-bot runtime.

### 6.2 Bot behavior

- One named bot, such as `AGK Meeting Notes`, joins each eligible Meet, Zoom, or Teams meeting.
- It respects waiting rooms and platform policies.
- It never bypasses admission controls.
- Recording can be disabled per meeting.
- Failures are explicit and never reported as successful capture.
- Consent notices and recording policy must be configurable and legally reviewed for the operating jurisdictions.

### 6.3 Speaker attribution

The system distinguishes:

- diarization: separating Speaker A, Speaker B, and other voices;
- nominal attribution: mapping a voice segment to a named participant.

Vexa's diarized transcript is combined with call participant metadata, active-speaker events, calendar attendees, and visible participant names. The system must not claim perfect nominal attribution without pilot measurements. Ambiguous segments retain a speaker label rather than inventing a name.

### 6.4 Media retention

- Video capture is disabled by default.
- If a platform or temporary pipeline produces video despite the default, it is deleted within seven days at maximum and is not included in durable backups.
- Raw audio is retained for 30 days to support transcript and speaker corrections, then deleted through a verified retention job.
- Transcript and canonical report are retained durably.
- The daily retention job checks deletion outcomes and disk usage and raises a failure when cleanup cannot be verified.

### 6.5 Granola reconciliation

Granola remains available during the pilot. When both Vexa and Granola produce data for one meeting, the reconciler updates the same canonical thread and compares:

- transcript coverage;
- speaker attribution;
- decisions;
- action items;
- manual correction time.

After 30 days, Operator produces an evidence-based keep/remove decision. Granola is not cancelled automatically.

### 6.6 Pilot metrics and stop conditions

Target metrics:

- at least 98% bot join success for eligible meetings;
- at least 95% usable transcript coverage;
- measured speaker attribution quality acceptable to Gareth;
- comparable decision/action extraction to Granola;
- bounded manual correction time;
- no privacy, retention, or cross-channel incident.

Stop the rollout for repeated bot absence, material speaker-attribution failure, duplicate capture, unauthorized recording, cross-channel leakage, unverified media deletion, or impact on Station gateways.

## 7. Provider Capacity Surface

Reuse and harden the existing `DiscordAccountUsageMonitor`; do not create a second monitor.

### 7.1 Destination

Discord channel `1542505478679171164` is the requested OpenAI capacity destination. Claude Code receives a separate detailed panel under the same capacity area or an explicitly configured channel ID.

### 7.2 Presentation

Use compact edited-in-place messages with rows such as:

```text
Agentik-OpenAI · 94% · resets in 3d
Operator-Claude · 61% · resets in 2h
```

The exact label comes from a safe configured Station/account alias. Never display access tokens, credential values, email addresses, raw provider responses, or secret-bearing IDs.

Refresh every five minutes by editing the same message. Unknown usage is `unknown`, never healthy. Show provider/account health, remaining percentage, usage window, and reset time only when supported by real data.

### 7.3 Acceptance

- The exact configured Discord messages are fetched after publication.
- OpenAI and Claude are both represented.
- Refresh edits existing messages rather than flooding channels.
- Account counts and declared totals match the canonical credential pools.
- No secret or private identifier appears.

## 8. Station Lobby Auto-Threads

### 8.1 Behavior

Every configured conversational Discord channel becomes a lobby. A human root message creates exactly one Discord thread and exactly one canonical Hermes session. The bot responds inside the thread.

The thread carries the durable Hermes session ID through server-controlled metadata. The same session is visible, resumable, and archivable from the AGK TUI and Session Control Center.

### 8.2 Exclusions

System, quota, monitoring, health, and read-only publication channels do not auto-thread. The meeting channel uses the Meeting Registry's one-thread-per-meeting lifecycle rather than generic lobby behavior.

### 8.3 Synchronization

- Root message ID, thread ID, Hermes session ID, profile, guild, and parent channel are stored as a typed mapping.
- Follow-up messages in the thread route to the same Hermes session.
- Renames update presentation metadata without changing session identity.
- Archive/close actions operate on exact IDs and preserve unrelated sessions.
- Gateway restarts recover mappings without generating duplicate threads or sessions.

### 8.4 Discord interaction policy

Interactive questions render once. The native `Hermes needs your input` block is the only representation: no duplicate introductory prose, second embed, or repeated choice list.

### 8.5 Acceptance

- Root message to thread to Hermes session to TUI is proven end to end.
- Two simultaneous root messages produce two isolated threads and two sessions.
- A gateway restart does not duplicate either mapping.
- Monitoring and meeting channels follow their explicit exclusion behavior.
- No bot-to-bot response loop is introduced.

## 9. Deployment sequence

1. Global Rule Plane and effective fleet verification.
2. Existing Provider Capacity monitor wiring and Discord readback.
3. Lobby auto-thread pilot on Operator, then fleet rollout after end-to-end proof.
4. Read-only Meeting Registry for Cal.com and Google Calendar.
5. Discord meeting cockpit and non-destructive controls.
6. Confirmed Cal.com reschedule/cancel actions.
7. Isolated Vexa deployment and synthetic non-production meeting.
8. Granola signed-webhook reconciliation.
9. Thirty-day pilot, retention verification, and keep/remove decision.

Only affected services are reloaded. Gateway restarts are minimized because Discord command synchronization is rate-limited.

## 10. Testing and review gates

Every slice follows test-first implementation and includes:

- unit tests for IDs, merge logic, deduplication, authorization, retention, and redaction;
- integration tests against temporary Hermes homes and fixture databases;
- fake Discord and provider write tests for destructive flows;
- one real non-destructive user-visible Discord interaction;
- exact readback after every external write;
- installed/source checksum comparison;
- fresh effective-rule probes in all five targets;
- independent fail-closed code review;
- final completeness review against every requirement in this document.

A green unit suite alone is insufficient.

## 11. Explicitly out of scope

- Importing project rules into the global AGK registry.
- Reading another Linux user's private state to synchronize rules.
- Creating Discord applications or bots autonomously.
- Activating a paid meeting service or incurring spend without approval.
- Keeping durable meeting video.
- Claiming perfect named-speaker attribution before pilot evidence.
- Replacing Hermes session storage or Discord transport with a parallel system.
- Cancelling Granola automatically at the end of the pilot.

## 12. Definition of done

The mission is complete only when:

- all five Station targets load the same canonical AGK rules plus preserved legitimate local overlays;
- global rule promotion works from every Station identity and project-rule promotion fails closed;
- channel `1542505478679171164` displays verified live OpenAI and Claude capacity without secrets;
- lobby channels create one thread and one synchronized Hermes session per root message across the Station;
- channel `1542526309211570226` displays deduplicated Cal.com and `x@agentik-os.com` Google Calendar meetings with working Join and authorized management controls;
- a Vexa test meeting auto-joins, captures audio only, produces a diarized transcript, and updates the canonical Discord thread;
- Granola updates the same thread during the pilot;
- video is absent or deleted within seven days, audio is deleted after 30 days, and both outcomes are verified;
- all tests, real readbacks, gateway health checks, self-review, and independent review pass;
- every remaining blocker is reported explicitly rather than hidden behind partial success.
