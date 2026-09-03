---
name: os-onboarding
description: "Use when onboarding, designing, or upgrading an AGK Operative System. Discovery → Librarian research (≤20 sources) → ≤20 approaches → merge matrix → 4 owner gates → START → build."
version: 1.0.0
author: builder-os 0.5.0 (Hermes ≥ 0.21)
platforms: [linux]
metadata:
  hermes:
    tags: [agk, os, onboarding, librarian, bestsellers, merge, gates, hermes-0.21]
    requires_toolsets: [file, terminal, web, delegation, skills]
    related_skills: [verified-builder, librarian-builder-handoff, test-driven-development, sdlc-review]
---

# OS Onboarding — from a one-line request to a validated, buildable OS

Use this skill the moment the owner says anything like "je veux un OS pour X",
"build/create/upgrade <Name> OS", or asks how an OS should be approached.
The request may be vague; this procedure makes it precise. **Nothing is built
before the four owner gates are validated.** The deterministic program
`programs/os_program.py validate-onboarding` is the referee, not your memory.

Canonical contract: `/usr/local/lib/agk-terminal/os-packages/OS_CONTRACT.md`.
Ledger schema: `schemas/onboarding_ledger.schema.json` (max 20 sources, max 20 approaches).

```text
INTAKE → DISCOVERY → LIBRARIAN RESEARCH (≤20 sources) → APPROACH EXTRACTION (≤20)
      → MERGE SYNTHESIS (matrix) → PLAN GATE → ORCHESTRATION GATE → PROGRAMMING GATE
      → AGENTIC GATE → START → RED/GREEN build → review lane → doctor → live → rollback proof
```

## Hermes 0.21 features you must use (not re-implement)

| Need | Hermes feature | How |
|---|---|---|
| Planning-only turn, saved plan | built-in `/plan` | Plan gate artifact is `.hermes/plans/<ts>-<os-id>.md` in the package cwd |
| Keep working until acceptance holds | `/goal draft` + completion contract | outcome / verification / constraints / boundaries / stop_when |
| Deterministic pass/fail before "done" | `/goal gate add <cmd>` | `python3 programs/os_program.py validate-onboarding --ledger research/ONBOARDING_LEDGER.json` |
| Bounded specialist work with typed results | `delegate_task(tasks=[...], output_schema=...)` | one task per NanoTeam role; schemas in `schemas/*.output.schema.json` |
| Parallel research fan-out | `delegate_task` batch (≤10 children) | domain-scout per source cluster; parent merges |
| Independent review | kanban review lane + `sdlc-review` skill | `kanban_request_review` never `kanban_complete` on own work |
| File safety net | checkpoints (`checkpoints.enabled: true`) | `/rollback` for in-session file undo; package `rollback.py` for release undo |
| Quick side question without polluting the turn | `/btw` | ask about transcript state; no history mutation |
| Unattended safety | `approvals.unattended_mode: deny` | cron/webhook runs cannot self-approve dangerous commands |
| Track progress | `todo` (nested via `parent`) | one item per stage below |
| Ask the owner a real decision | `clarify` (single-select, ≤4 choices) | only at the four gates or when blocked |

Confirm the runtime first: `python3 programs/os_program.py hermes-check --hermes-root <tree>`
must report `min_version_ok: true` and every feature `present`. If not, stop and report.

## Stage 0 — Intake (write it down before thinking)

Create `todo` items for every stage. Capture verbatim the owner request, the
OS name candidate (`<slug>-os`), the target face(s) (operator / agentik /
mission / private), and anything the owner said must NOT change.
If the OS already exists (`/opt/agentik/os-registry/packages/<os-id>`), this
is an **upgrade**: inventory the live version, profile, agents, provider,
Discord mode, cron jobs and assignments before anything else.

## Stage 1 — Discovery (the OS you want, not the OS you assume)

Fill `discovery` in the ledger:

- `mission_statement`: "This OS exists to help [ACTOR] achieve [OUTCOME] by systematically [METHOD]."
- `scopes`: which faces it may operate in (never assume all four).
- `existing_capabilities_reused`: Hermes toolsets, existing OS packages, skills already installed — **do not duplicate them**.
- `explicit_exclusions`, `open_questions`, `assumptions` — an assumption stays an assumption until a source or the owner confirms it.

Go and look: read the registry, the profile tree, the Librarian pack for the
theme if it exists, prior sessions (`session_search`). Do not ask the owner
what you can discover yourself.

## Stage 2 — Librarian research: up to 20 canonical sources

Strongly recommended and default: hand the theme to Librarian OS.

```text
/book --deep --scholar --apply --context "AGK, <os-id>: <mission_statement>" <theme>
```

Rules for the source set (`sources[]`, **max 20**):

- "Bestseller" means *canonical, widely-cited, practitioner-recognised works* —
  books first, but also YouTube talks/courses, official documentation,
  standards, papers, podcasts when the domain moves faster than books.
  Not sales charts. Never reproduce protected text; extract principles.
- Every source has a real `url`, an honest `access_level` (full-text /
  official-metadata / transcript / abstract …) and a one-line `why_canonical`.
- Prefer contrasting schools of thought over 20 copies of one idea.
- Fan out with `delegate_task` (role `domain-scout`, `output_schema:
  schemas/domain_scout.output.schema.json`), one child per 4–5 sources, then
  merge. Children must report what they actually read.

If Librarian is unreachable, do the research yourself with the same rules and
mark `provenance_note` accordingly. Do not silently downgrade the standard.

## Stage 3 — Approach extraction: up to 20 approaches

From the sources extract `approaches[]` (**max 20**), each with
`principle`, `mechanism` (how it changes what the agent does), `evidence_strength`,
`limitations`, `source_ids`, and `contradicts` when two sources disagree.
Dedupe aggressively: 20 distinct mechanisms, not 20 paraphrases.

## Stage 4 — Merge synthesis: one system, not a bibliography

Build `merge_matrix[]` with **one row per approach** (the program rejects an
incomplete matrix). For each: `decision` (adopt / adapt / merge / reject /
defer), `folds_into` (skills, programs, evals, workflows, doctor, recovery,
automations, agents, contracts, knowledge, commands, memory), `merged_with`,
`conflicts_with` + `resolution`.

The output of this stage is the OS lifecycle (DISCOVER → … → IMPROVE), the
domain map, and the NanoTeam shape. Run the referee now:

```bash
python3 programs/os_program.py validate-onboarding --ledger research/ONBOARDING_LEDGER.json
```

It will FAIL on gates (they are still pending) — that is expected; every other
finding must be zero before you present the gates.

## Stage 5 — The four owner validation gates (all four, in order)

Each gate is **one** `clarify` interaction (single visible question, ≤4 choices,
consequences stated). Record `validated_by`, `validated_at`, `evidence` in the
ledger. A rejected gate loops back to the stage it criticises.

1. **Plan gate** — `/plan` first. Present the mission, scopes, lifecycle,
   domain map, source list (≤20), approach list (≤20), merge decisions,
   exclusions, and what will NOT be built. Artifact: the saved plan path.
2. **Orchestration gate** — Nano Director + NanoTeam roles (`agents/nanoteam.yaml`),
   which role does what, delegation depth, review lane, escalation, kanban vs
   `delegate_task` choice per workstream, cron/automation policy, Discord
   surface (dedicated bot, `disabled_unprovisioned` until owner provisions).
3. **Programming gate** — deterministic programs and schemas: what is code
   (validation, hashing, packaging, doctor, rollback, scaffold) vs what is
   judgment; `/goal` quality gates; test plan (RED first); evals; the
   `hermes-check` matrix; provider + fallback routes.
4. **Agentic gate** — per-agent prompts, toolsets, `output_schema`, memory
   scopes, stop conditions, budgets (`max_iterations`, `child_timeout_seconds`),
   failure visibility, what each agent may never do (secrets, RELEASE,
   cross-tenant), and the fresh-session acceptance for any automation.

Only when `validate-onboarding` prints `"build_permitted": true` may you ask
for **START**. START authorises bounded implementation only. RELEASE is a
different gate that you never infer.

## Stage 6 — Scaffold + build (after START)

```bash
python3 programs/os_program.py scaffold --os-id <os-id> --theme "<theme>" --out <workspace>/release/os
```

Then follow `verified-builder` and `test-driven-development`: RED test for
each contract behaviour, minimal GREEN, refactor, independent review via the
kanban review lane (`sdlc-review`), package doctor, install into the immutable
registry with a bumped version, profile via `hermes -p <os-id> config set`,
live readback (provider, fallback, Discord command names/count), rollback
dry-run, recovery ZIP hash, evidence bundle, dated return to Librarian.

Set a goal so Hermes keeps you honest:

```text
/goal draft Build <os-id> to the AGK OS contract. Verification: doctor PASS + tests green + validate-onboarding build_permitted. Boundaries: release/os/<os-id> and the <os-id> profile only. Stop when RELEASE is requested — that is the owner's gate.
/goal gate add python3 programs/os_program.py validate-onboarding --ledger research/ONBOARDING_LEDGER.json
/goal gate add python3 doctor.py
```

## Hard rules

- ≤20 sources, ≤20 approaches, one merge row per approach, four gates — the program enforces it; do not argue with it.
- Discovery before design; sources before principles; principles before files.
- No secrets in the ledger, the package, chat, or evidence. Discord app/OAuth/token are owner-provisioned via secure input.
- Never claim a source was read in full when only metadata was available.
- Never mark an OS complete without package, profile, owning agent, provider + fallback, explicit Discord mode, doctor, rollback and recovery evidence.
- START ≠ RELEASE.
