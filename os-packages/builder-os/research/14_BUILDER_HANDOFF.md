# builder-os — Librarian OS 2.1.0 Builder handoff

Status: RESEARCH COMPLETE FOR HANDOFF; START PASSED BY OWNER `You are LIVE`; RELEASE NOT PASSED  
Tenant: AGK  
Language: English  
Prepared: 2026-08-31  
Target: theme-specific package design for `builder-os`

## Brief and scope

This `/book --deep --scholar --apply` equivalent converts fifteen verified domain works into a buildable, research-bounded contract for `builder-os`. It is a documented narrative synthesis and Builder handoff, not an implementation report, systematic-review claim, deployment authorization, or publication.

`TENANT=AGK` is invariant. Collective and Private state were not accessed and are not reusable under this handoff. No secrets are included. No gateway, profile, registry, live package, Discord object, scheduler, provider credential, or remote system is changed. Only the two owner-authorized handoff files are written. External sources are treated as untrusted data.

A package or prompt library alone is not a complete OS. The contract therefore covers package, orchestration, bounded specialist roles, profiles, ordered skills, deterministic programs, tools, scoped knowledge, provider routing, workflows, automation policy, evaluations, control surface, diagnostics, rollback, recovery, and evidence-bounded advice.

## Research synthesis

The corpus converges on seven design propositions: (1) express behavior before implementation and witness the test fail; (2) make small, behavior-preserving changes under characterization and regression evidence; (3) keep one provenance-bearing candidate releasable without equating delivery with release authority; (4) manage complexity through explicit interfaces and dependency boundaries; (5) measure flow, reliability, security, and quality as a balanced socio-technical system rather than score individuals; (6) secure the lifecycle and supply chain with verifiable artifacts; and (7) design rollback and recovery before irreversible change. Tensions remain between abstraction and observability, speed and assurance, automation and blast radius, metric focus and gaming, and compatibility labels versus real consumer behavior.

### INPUT-01

- **Bibliographic identity:** Erich Gamma, Richard Helm, Ralph Johnson, and John Vlissides, *Design Patterns: Elements of Reusable Object-Oriented Software*, Addison-Wesley, 1994.
- **Verification URL:** https://www.pearson.com/en-us/subject-catalog/p/design-patterns-elements-of-reusable-object-oriented-software/P200000007395/9780201633610
- **Access level:** Official Pearson publisher metadata and description; no full-book access claimed.
- **Original paraphrased principle:** Name recurring design structures with their intent, context, participants, consequences, and trade-offs so teams can reuse reasoning rather than copy code blindly.
- **Limitations/contradictions:** Patterns are contextual, language-era dependent, and can encourage needless indirection. A pattern catalog is not proof that a pattern fits a particular architecture.

#### Fold into OS contract

Design records pattern intent and rejected alternatives; Package keeps modules replaceable; Evaluations test consequences, not pattern-name presence; Librarian best advice prefers the simplest structure that satisfies current acceptance probes.

### INPUT-02

- **Bibliographic identity:** Martin Fowler, *Refactoring: Improving the Design of Existing Code*, 2nd ed., Addison-Wesley, 2018.
- **Verification URL:** https://martinfowler.com/books/refactoring.html
- **Access level:** Author’s official book page and publisher-linked metadata; no full-book access claimed.
- **Original paraphrased principle:** Change internal structure through small behavior-preserving transformations protected by tests, making each step understandable and reversible.
- **Limitations/contradictions:** “Behavior preserving” depends on test and observation coverage. Refactoring can change timing, resource use, public quirks, or operational behavior and should not be mixed invisibly with feature changes.

#### Fold into OS contract

Ordered skills separate red test, green implementation, and refactor; Workflows require small diffs; Rollback captures pre-state; Evaluations include characterization and performance tests; Builder return distinguishes refactor from behavior change.

### INPUT-03

- **Bibliographic identity:** Kent Beck, *Test-Driven Development: By Example*, Addison-Wesley, 2002.
- **Verification URL:** https://www.pearson.com/en-us/subject-catalog/p/Beck-Test-Driven-Development-By-Example/P200000009421/9780321146533
- **Access level:** Official Pearson publisher metadata and description; no full-book access claimed.
- **Original paraphrased principle:** Drive design in short red–green–refactor cycles: express one observable behavior, witness failure for the intended reason, add the minimum implementation, then improve structure.
- **Limitations/contradictions:** TDD does not discover the right product, prove complete correctness, or replace integration, security, usability, or exploratory testing. Poor tests can fossilize a poor design.

#### Fold into OS contract

Nano Director enforces witnessed RED before GREEN; Deterministic programs capture test command and exit; Evaluations include mutation and integration coverage; failure behavior blocks “done” when the test never failed or only tested a mock.

### INPUT-04

- **Bibliographic identity:** Jez Humble and David Farley, *Continuous Delivery: Reliable Software Releases through Build, Test, and Deployment Automation*, Addison-Wesley, 2010.
- **Verification URL:** https://www.pearson.com/en-us/subject-catalog/p/continuous-delivery-reliable-software-releases-through-build-test-and-deployment-automation/P200000009113/9780321670229
- **Access level:** Official Pearson publisher metadata and description; no full-book access claimed.
- **Original paraphrased principle:** Keep software releasable through versioned configuration, repeatable pipelines, automated tests, identical artifact promotion, and frequent small changes.
- **Limitations/contradictions:** Pipeline automation can rapidly propagate defects; identical artifacts do not guarantee identical environments. Delivery capability is not permission to release.

#### Fold into OS contract

Package produces one checksum-pinned candidate; Workflows promote rather than rebuild; START and RELEASE remain separate; Automations stop on uncertainty; Evaluations exercise pipeline, rollback, and environment drift.

### INPUT-05

- **Bibliographic identity:** Michael C. Feathers, *Working Effectively with Legacy Code*, Prentice Hall, 2004.
- **Verification URL:** https://www.pearson.com/en-us/subject-catalog/p/working-effectively-with-legacy-code/P200000008984/9780131177055
- **Access level:** Official Pearson publisher metadata and description; no full-book access claimed.
- **Original paraphrased principle:** Before changing poorly covered code, find seams, add characterization tests around observed behavior, and introduce the smallest safe point of control.
- **Limitations/contradictions:** Characterization preserves observed behavior, including defects. Seam creation may increase complexity, and some systems require larger architectural or data-migration work.

#### Fold into OS contract

Blueprint distinguishes preserve-versus-correct decisions; Stepper begins with characterization fixtures; MCP/tool contracts isolate dependencies; Rollback protects existing data; Evaluations flag tests that merely canonize a known bug.

### INPUT-06

- **Bibliographic identity:** John Ousterhout, *A Philosophy of Software Design*, 2nd ed., Yaknyam Press, 2021.
- **Verification URL:** https://web.stanford.edu/~ouster/cgi-bin/aposd.php
- **Access level:** Author’s official Stanford page with edition identity and high-level material; no full-book access claimed.
- **Original paraphrased principle:** Reduce complexity by creating deep modules with simple interfaces, hiding decisions, eliminating unnecessary dependencies, and treating complexity as a design signal.
- **Limitations/contradictions:** Depth and simplicity are judgment calls; a narrow interface can hide dangerous behavior, and abstraction can impede observability or premature generalization.

#### Fold into OS contract

Design budgets dependencies and interface surface; Profiles and tools use narrow typed contracts; Doctor exposes hidden state necessary for diagnosis; Evaluations test comprehension, observability, and failure isolation, not line count.

### INPUT-07

- **Bibliographic identity:** Nicole Forsgren, Jez Humble, and Gene Kim, *Accelerate: The Science of Lean Software and DevOps*, IT Revolution Press, 2018.
- **Verification URL:** https://www.oreilly.com/library/view/accelerate/9781457191435/
- **Access level:** Authorized O’Reilly publisher/library overview and bibliographic metadata; full-book access was not used.
- **Original paraphrased principle:** Measure software delivery through balanced flow and stability outcomes, and treat capabilities such as continuous delivery, architecture, feedback, and culture as hypotheses linked to performance.
- **Limitations/contradictions:** Reported relationships are population-level and context-dependent; metrics can be gamed and should not become individual productivity scores. Correlation and survey models do not justify every causal claim.

#### Fold into OS contract

Evaluations track lead time, deploy frequency, recovery time, and change-failure context without ranking people; Profiles set service baselines; Automations detect trends; Librarian best advice requires local experiments and counter-metrics.

### INPUT-08

- **Bibliographic identity:** Betsy Beyer, Chris Jones, Jennifer Petoff, and Niall Richard Murphy, eds., *Site Reliability Engineering: How Google Runs Production Systems*, O’Reilly, 2016.
- **Verification URL:** https://sre.google/books/sre-book/table-of-contents/
- **Access level:** Full legal online edition provided by Google and consulted at the structural level.
- **Original paraphrased principle:** Define reliability as an explicit service objective, use error budgets to balance change and stability, automate toil carefully, and design operations around observable failure and learning.
- **Limitations/contradictions:** Google-scale practices need adaptation; SLOs can omit user harms, and error budgets do not authorize unsafe releases or substitute for product judgment.

#### Fold into OS contract

Profiles declare SLOs and risk class; Doctor reports objective health; Automations obey error-budget circuit breakers; Workflows include incident review; Recovery probes use actual restore evidence.

### INPUT-09

- **Bibliographic identity:** IEEE Computer Society, *Guide to the Software Engineering Body of Knowledge (SWEBOK Guide)*, Version 4.0a, current official release.
- **Verification URL:** https://www.computer.org/education/bodies-of-knowledge/software-engineering/v4
- **Access level:** Official IEEE Computer Society landing page and downloadable guide access.
- **Original paraphrased principle:** Software engineering spans requirements, architecture, design, construction, testing, operations, maintenance, configuration, process, quality, security, economics, and professional practice; delivery evidence must cover the lifecycle.
- **Limitations/contradictions:** A body-of-knowledge taxonomy is not a prescribed process or proof of competence. Breadth can become checklist compliance without risk-based depth.

#### Fold into OS contract

Integrated OS contract covers all lifecycle dimensions; NanoTeam roles are capability-scoped; Stepper maps requirements to increments; Evaluations report uncovered knowledge areas; Builder return gives traceability rather than a generic pass.

### INPUT-10

- **Bibliographic identity:** Murugiah Souppaya, Karen Scarfone, and Donna Dodson, *Secure Software Development Framework (SSDF) Version 1.1*, NIST SP 800-218, February 2022, DOI 10.6028/NIST.SP.800-218.
- **Verification URL:** https://csrc.nist.gov/pubs/sp/800/218/final
- **Access level:** Full official NIST publication and metadata available.
- **Original paraphrased principle:** Integrate secure-development preparation, software protection, well-secured production, and vulnerability response into the development lifecycle with defined roles and evidence.
- **Limitations/contradictions:** SSDF is a risk-based framework, not a certification or complete control implementation. It requires tailoring to technology, threat model, and legal context.

#### Fold into OS contract

Package includes provenance and dependency inventory; Workflows threat-model before coding; Provider/tool contracts minimize trust; Evaluations include abuse and vulnerability fixtures; RELEASE requires residual-risk review.

### INPUT-11

- **Bibliographic identity:** SLSA Community, *Supply-chain Levels for Software Artifacts (SLSA) Specification*, Version 1.2, current approved specification.
- **Verification URL:** https://slsa.dev/spec/latest/
- **Access level:** Full official public specification read.
- **Original paraphrased principle:** Increase software supply-chain assurance through provenance, controlled build processes, verifiable artifacts, and progressively stronger guarantees rather than trusting an opaque binary.
- **Limitations/contradictions:** SLSA addresses supply-chain integrity, not source correctness, runtime safety, privacy, or operator authorization. A claimed level requires exact conformance evidence.

#### Fold into OS contract

Package emits signed/checksummed provenance; Provider routes cannot substitute unknown binaries; Doctor verifies attestations; Recovery artifact pins dependencies; Evaluations reject unsupported SLSA-level claims.

### INPUT-12

- **Bibliographic identity:** OWASP Foundation, *Application Security Verification Standard (ASVS)*, Version 5.0.0, 2025.
- **Verification URL:** https://owasp.org/www-project-application-security-verification-standard/
- **Access level:** Full official open standard and project page available.
- **Original paraphrased principle:** Turn application-security expectations into explicit, testable requirements organized by verification areas and assurance levels.
- **Limitations/contradictions:** ASVS is web-application focused and does not cover every infrastructure, model, privacy, or business-logic risk. Checklist completion without threat modeling can miss system-specific abuse.

#### Fold into OS contract

Evaluations map applicable ASVS controls to evidence; Profiles set assurance level by exposure; MCP/tool contracts require authentication and input validation; Discord surface gets replay, authorization, and rendering probes; non-applicable controls need rationale.

### INPUT-13

- **Bibliographic identity:** DORA, *Accelerate State of DevOps Report 2024*, Google Cloud/DORA, 2024.
- **Verification URL:** https://dora.dev/dora-report-2024
- **Access level:** Full official report download, methodology pages, and errata are publicly accessible.
- **Original paraphrased principle:** Treat delivery and AI-assisted development outcomes as socio-technical and empirical: measure local effects, expose trade-offs, and retain correction/errata paths.
- **Limitations/contradictions:** Annual survey findings are time-bound, self-reported, and not universal causal laws. Aggregate benchmarks should not become targets detached from customer value or safety.

#### Fold into OS contract

Evaluations version metrics and preserve errata; Provider routes for coding agents are experiments; Automations avoid target gaming; Nano Director compares speed with quality and well-being signals; semantic audit records time-bounded applicability.

### INPUT-14

- **Bibliographic identity:** Tom Preston-Werner, *Semantic Versioning 2.0.0*, maintained public specification.
- **Verification URL:** https://semver.org/
- **Access level:** Full official public specification read.
- **Original paraphrased principle:** Declare a public API and communicate compatible additions, fixes, and breaking changes through a deterministic MAJOR.MINOR.PATCH contract.
- **Limitations/contradictions:** Version numbers communicate declared compatibility; they do not detect hidden behavior, data migrations, operational incompatibility, or undeclared consumers. Pre-1.0 conventions permit instability.

#### Fold into OS contract

Package validates versions and dependency ranges; Ordered skills require compatibility assessment; Workflows produce migration previews; Doctor detects skew; Rollback and Recovery pin exact artifacts and schemas.

### INPUT-15

- **Bibliographic identity:** International Organization for Standardization, *ISO/IEC 25010:2023 Systems and software engineering — SQuaRE — Product quality model*, 2nd ed., 2023.
- **Verification URL:** https://www.iso.org/standard/78176.html
- **Access level:** Official ISO metadata, abstract, and preview only; full protected standard not accessed and no conformity is claimed.
- **Original paraphrased principle:** Software quality is multidimensional; requirements must address functional suitability alongside performance, compatibility, interaction capability, reliability, security, maintainability, flexibility, and safety where applicable.
- **Limitations/contradictions:** The public preview is insufficient for a conformity claim, and quality attributes require context-specific measures and trade-offs. Maximizing every attribute is impossible.

#### Fold into OS contract

Blueprint declares quality priorities and trade-offs; Evaluations map acceptance tests to named attributes; Profiles set thresholds by context; Doctor reports unmeasured attributes; RELEASE requires explicit residual quality decisions without claiming ISO conformity.

## Blueprint

Problem: AGK implementation can fail when requirements, tests, authority, artifacts, reviews, and recovery evidence are disconnected. Primary users are authorized AGK builders and reviewers; agents propose and implement only within explicit roots. Outcome: a traceable Blueprint → Design → Stepper → witnessed RED/GREEN/refactor → independent review → package → staging → distinct release lifecycle. Core records are `BuildMission`, `Requirement`, `DesignDecision`, `Increment`, `TestWitness`, `ChangeSet`, `ArtifactProvenance`, `ReviewFinding`, `GateEvent`, `DeploymentPlan`, `RollbackPlan`, `RecoveryEvidence`, and `Observation`. Recommended option: bounded agentic coding surrounded by deterministic policy/test/artifact gates. Rejected options: autonomous deployer, test-count theatre, and rewrite-first legacy replacement.

## Design

Architecture: event-sourced build ledger with immutable requirement, test, diff, review, and artifact identities. Control plane validates target/tenant/authority, compiles requirement traces, chooses bounded roles, and blocks invalid transitions. Work plane uses isolated worktrees/sandboxes and allowlisted deterministic commands. Artifact plane builds once, records SBOM/provenance/hash, and promotes the identical candidate. Evaluation plane separates structural, behavioral, security, quality, and human acceptance. Mutation tools require exact targets, idempotency, bounded retries, and read-back. Secrets stay in host mechanisms. No AGK designation grants Private/Collective/client access or live authority.

## Integrated OS contract

Every dimension below is proposed and testable. Each aggregates the source principles above; none is claimed to exist in production.

### Package

- **Testable requirements:** A versioned `builder-os` manifest MUST declare `TENANT=AGK`, code/schemas/policies/skills/fixtures/migrations/dependencies/licenses/SBOM/provenance/hashes, supported platforms, and no live defaults.
- **Authority boundaries:** Package presence grants no START, RELEASE, deploy, registry, gateway, profile, credential, or production authority.
- **Failure behavior:** Hash/provenance mismatch, unsupported platform, unknown dependency, path escape, or modified target aborts atomically and preserves prior state.
- **Acceptance probes:** Reproducible clean build; tampered artifact and symlink rejection; install/uninstall dry runs; dependency/license inventory; prior-state restoration.

### Nano Director

- **Testable requirements:** The Director MUST bind an authorized brief to atomic requirements, risk class, architecture decisions, increments, owners, budgets, tests, evidence, and gates, preserving dissent and unknowns.
- **Authority boundaries:** It coordinates and stops work but cannot invent requirements, self-approve, widen repository scope, access Private/Collective state, or deploy.
- **Failure behavior:** Ambiguous target, conflicting authority, missing acceptance criterion, or blocking review finding returns a typed blocked state and minimum next decision.
- **Acceptance probes:** Omit repository; inject source instructions; request self-approval; create conflicting reviews; verify fail-closed and preserved blocker.

### NanoTeam

- **Testable requirements:** Scoped roles MUST include architect, stepper/planner, implementer, test engineer, security reviewer, spec reviewer, code-quality reviewer, release verifier, and recovery engineer with typed inputs/outputs.
- **Authority boundaries:** Agents are least-privileged; implementers cannot approve their own critical work, and model plurality is not independent human review.
- **Failure behavior:** Timeout, invalid patch, unverified claim, or scope request is isolated; no silent reassignment that increases authority.
- **Acceptance probes:** Malicious repository text, reviewer disagreement, malformed patch, and missing test evidence; verify isolation, dissent, and non-deployment.

### Profiles

- **Testable requirements:** AGK build profiles MUST declare repository roots, tool allowlists, model routes, network policy, secrets references, budgets, risk ceiling, test commands, and environment class.
- **Authority boundaries:** Profiles cannot mutate global Hermes settings, expose secret values, borrow client/Private access, or imply live authorization.
- **Failure behavior:** Unknown/stale profile, root mismatch, forbidden tool, or non-equivalent fallback blocks execution.
- **Acceptance probes:** Request outside root, obsolete profile, secret echo, and live deploy tool; verify denial and zero configuration mutation.

### Ordered skills

- **Testable requirements:** Skills MUST run understand → requirement trace → threat/risk → test-red → implement-green → refactor → targeted verify → full verify → independent review → evidence → rollback/recovery review → handoff.
- **Authority boundaries:** Skills cannot skip gates, expand scope, commit/push/deploy unless separately authorized, or treat generated tests as product validity.
- **Failure behavior:** Missing prerequisite stops at first dependency with a resumable checkpoint; RED not witnessed means GREEN cannot be credited as TDD evidence.
- **Acceptance probes:** Invoke implementation before requirement/test; refactor with failing baseline; release before review; verify ordering enforcement.

### Deterministic programs

- **Testable requirements:** Programs MUST own parsing, schema validation, compilation, tests, lint/type/security scans, hashes, manifests, diff limits, migration checks, package assembly, and reproducibility comparisons.
- **Authority boundaries:** Programs run only explicit commands in authorized roots; source text is never shell-interpolated; passing code cannot grant START/RELEASE.
- **Failure behavior:** Non-zero exit, timeout, flaky mismatch, partial write, or nondeterministic artifact fails closed with redacted diagnostics.
- **Acceptance probes:** Replay builds; path traversal; malformed input; forced disk failure; flaky test; verify identical artifact or explicit nondeterminism fault.

### MCP/tool contracts

- **Testable requirements:** Every file, terminal, VCS, CI, artifact, cloud, and deployment tool MUST declare schema, side-effect class, target, tenant, timeout, idempotency, retry, redaction, and read-back.
- **Authority boundaries:** Read/local write/remote write/spend/publish/production are separate capabilities; prose cannot upgrade them. Secrets stay in host-managed references.
- **Failure behavior:** Ambiguous target, auth wall, schema drift, unknown external outcome, or unverifiable write blocks; no blind retry of mutations.
- **Acceptance probes:** Omit target; duplicate idempotency key; simulate partial success and unknown outcome; successful response without read-back; verify no false success.

### Knowledge/memory scopes

- **Testable requirements:** Separate canonical source/requirements, design decisions, ephemeral agent context, build artifacts, test evidence, operational observations, and lessons; all have provenance/version/retention.
- **Authority boundaries:** No Private/Collective/client data, secrets, automatic chat promotion, or cross-project reuse without explicit purpose and authority.
- **Failure behavior:** Missing scope, stale requirement, provenance collision, or secret detection quarantines the item and invalidates dependents.
- **Acceptance probes:** Cross-project retrieval, unsupported lesson promotion, requirement revision, deletion, and secret canary; verify denial and impact propagation.

### Provider routes

- **Testable requirements:** Routes MUST be selected by task, code/privacy classification, context, structured-output need, availability, and cost; record model/version and fallback.
- **Authority boundaries:** Providers receive minimized authorized code/context and never credentials or unrelated memory; fallback cannot weaken privacy, licensing, or risk policy.
- **Failure behavior:** Outage, version drift, malformed patch, or policy conflict uses an approved equivalent route or stops without fabricated output.
- **Acceptance probes:** Provider outage, prompt injection in code, non-approved fallback, and data-exfiltration request; verify block/redaction and route trace.

### Workflows

- **Testable requirements:** Implement intake, blueprint, design, stepper, RED/GREEN/refactor, review, package, staging verification, release request, observe, incident, rollback, and recovery as guarded state machines.
- **Authority boundaries:** No workflow can jump from recommendation/build success to deployment; owner/controller gates and target-specific credentials remain external.
- **Failure behavior:** Invalid transition returns state, guards, and safe next action; material changes invalidate stale approval and evidence.
- **Acceptance probes:** Try DRAFT→RELEASED; modify artifact after approval; fail migration mid-step; verify rejection, invalidation, and recovery route.

### Automations

- **Testable requirements:** Permitted automation is bounded CI, dependency/provenance scanning, test execution, artifact retention, and authorized health checks with owner, scope, budget, stop, and audit.
- **Authority boundaries:** This handoff creates no jobs. Automation cannot auto-merge, deploy, rotate secrets, modify gateways/profiles/registries, or cross tenant.
- **Failure behavior:** Repeated failures trip a circuit breaker; unexpected target/volume, stale approval, or unknown outcome pauses and alerts without blind retry.
- **Acceptance probes:** Duplicate tick, forked untrusted PR, excessive matrix, stale token, and production target; verify idempotence and immediate block.

### Evaluations

- **Testable requirements:** Suites MUST cover requirements, unit/schema/property/integration/system/security/privacy/accessibility/performance/migration/rollback/recovery, artifact provenance, and human acceptance with status distinctions.
- **Authority boundaries:** Tests prove only exercised behavior; Builder cannot self-grant human acceptance, START, RELEASE, compliance, or production fitness.
- **Failure behavior:** Critical scope leak, secret, gate bypass, fabricated evidence, unrecoverable migration, supply-chain failure, or unreviewed important finding blocks promotion.
- **Acceptance probes:** Mutation testing; prompt injection; wrong tenant; partial tool failure; stale dependency; rollback failure; unrun test; verify correct non-passing states.

### Discord control surface

- **Testable requirements:** If separately authorized later, expose private AGK build status, diffs, test evidence, blockers, and explicit gate-request controls with verified actor/channel/tenant and signed expiring state.
- **Authority boundaries:** Discord is a control surface, not canonical code, identity by label, or deploy authority; no secrets/log bodies in messages.
- **Failure behavior:** Wrong actor/channel, replay, stale digest, oversized output, or missing host verification rejects safely and records a redacted event.
- **Acceptance probes:** Replay approval, spoof user, stale artifact hash, public channel, and markdown injection; verify zero gate/deploy transition. No deployment here.

### Doctor

- **Testable requirements:** Read-only diagnostics MUST cover package/provenance/hashes, dependency and schema compatibility, tool/provider availability, test status, migrations, gate state, rollback prerequisites, and recovery readiness.
- **Authority boundaries:** Doctor diagnoses only configured AGK targets; it cannot reveal secrets, scan unrelated roots, fix automatically, or pass gates.
- **Failure behavior:** Skipped checks are unknown, not healthy; partial access yields precise bounded findings and a separately authorized repair plan.
- **Acceptance probes:** Break dependency, signature, provider route, migration marker, and recovery pointer; verify exact findings and zero mutation.

### Rollback

- **Testable requirements:** Each mutation MUST declare pre-state, expected revision, inverse or compensating action, data effects, rollback window, and verification; prefer transactional/expand-contract designs.
- **Authority boundaries:** Rollback targets only the exact authorized AGK environment and cannot retrieve older secret or out-of-scope data.
- **Failure behavior:** Missing safe inverse blocks forward action; failed rollback enters recovery with immutable evidence and no success claim.
- **Acceptance probes:** Force failures before/after commit; stale revision; non-idempotent inverse; verify restoration, unresolved delta, and safe escalation.

### Recovery artifact

- **Testable requirements:** Produce a versioned, checksum-pinned, rights-clean artifact with manifest, source/config references, schemas, migrations, SBOM/provenance, binaries, restore order, verification commands, and known limitations.
- **Authority boundaries:** Exclude credentials, Private/Collective/client state, unrelated data, and unlicensed dependencies/source copies; restore needs separate target authority.
- **Failure behavior:** Missing hash/signature, incompatible platform/schema, unavailable dependency, or failed isolated verification blocks restore before mutation.
- **Acceptance probes:** Restore to empty isolated fixture; verify hashes/state/tests; wrong-version rejection; secret/license scan; disaster-path drill.

### Librarian best advice

- **Testable requirements:** Build one thin reversible vertical slice from requirement to witnessed RED, minimal GREEN, refactor, independent review, package evidence, Doctor, rollback, and isolated recovery before scaling agents or integrations.
- **Authority boundaries:** Advice is not authorization. Owner/controller retains product decisions, START, RELEASE, deployment, residual risk, and live credentials.
- **Failure behavior:** If target, owner, acceptance test, safe rollback, or recovery evidence is missing, return a blocked handoff rather than creating a substitute project or plausible output.
- **Acceptance probes:** A reviewer can trace requirement→diff→test→artifact, reproduce the build, reject the recommendation, force a failure, roll back, restore, and verify no scope/secret leakage.

## Stepper

1. S0 confirm actual repository/worktree, owner, environment, threat model, secrets mechanism, and exclusions. 2. S1 encode requirement, tenant, authority, state-machine, and prohibited-mutation fixtures. 3. S2 add characterization tests and baseline build evidence before modifying legacy behavior. 4. S3 implement one thin vertical slice with witnessed RED → minimal GREEN → refactor. 5. S4 add deterministic full-suite, lint/type/security, dependency, SBOM, and provenance checks. 6. S5 add independent specification/code-quality/security review with blocking-finding loop. 7. S6 package one reproducible checksum-pinned candidate and migration preview. 8. S7 implement read-only Doctor, rollback preconditions, forced-failure test, and isolated recovery restore. 9. S8 run non-production socio-technical and DORA/SLO measurements without individual scoring. 10. S9 present G1–G3 artifacts for a distinct START decision. 11. After START only, perform staging G4/G5 against the exact candidate. 12. Present digest, residual risks, rollback/recovery evidence for a separate RELEASE decision. No step may fabricate output, skip a blocking finding, or broaden scope.

## Gates

| Gate | Required evidence | Pass authority | Current state |
|---|---|---|---|
| G0 research coverage | This source/access ledger, synthesis, contradictions, and semantic audit | Librarian reviewer | Passed for a bounded theme handoff only |
| G1 scope/brief | AGK tenant, target repository, exclusions, authority, and risks | Owner/controller | Pending target confirmation |
| G2 architecture | Blueprint, Design, threat model, alternatives, and requirement trace | Architecture/security review | Proposed, not accepted |
| G3 increment plan | Stepper, fixtures, stop conditions, rollback/recovery plan | Builder and reviewer | Proposed, not executed |
| **START** | G1–G3 evidence plus explicit owner/controller authorization bound to target and digest | Explicit owner/controller event | **PASSED by the owner's explicit `You are LIVE` instruction; bounded implementation authority only** |
| G4 staging | Real commands, tests, read-backs, rollback and isolated recovery evidence | Builder plus independent reviewer | Not run |
| G5 human review | Semantic, security, privacy, rights, usability, and residual-risk review | Named human reviewers | Not passed |
| **RELEASE** | Exact candidate digest, all blocking findings closed, G4/G5 evidence, distinct approval | Separate explicit owner/controller event | **NOT PASSED; distinct from START** |
| G6 post-release | Observed production checks and rollback readiness | Release owner | Not applicable |

No local test, source quality, model assertion, or START event can imply RELEASE. START permits only bounded implementation under the accepted contract; deployment, publication, gateway/profile/registry mutation, live Discord work, scheduling, and production access remain forbidden without their own authority and, where applicable, RELEASE.

## Builder return contract

Builder must return: exact authorized repository/worktree and tenant; artifact/commit digest and complete changed-file list; requirement-to-implementation trace for all seventeen dimensions; architecture and threat-model decisions; commands actually executed with exit states; full test inventory distinguishing pass/fail/blocked/not-run; package manifest, SBOM, provenance, licenses, schemas, and migration evidence; tool/provider data-flow and authority matrix; security/privacy/rights review; deviations labeled as Builder hypotheses; Doctor output; real non-production rollback and isolated recovery-restore evidence; read-back for any separately authorized external mutation; unresolved risks; and explicit START/RELEASE states. Builder may not self-pass either gate. If target, ownership, environment, or authority is missing, return a blocked report rather than create a substitute project.

## Source ledger and access limits

| ID | Verified identity route | Access actually used | Primary contribution |
|---|---|---|---|
| INPUT-01 | https://www.pearson.com/en-us/subject-catalog/p/design-patterns-elements-of-reusable-object-oriented-software/P200000007395/9780201633610 | Official Pearson publisher metadata and description; no full-book access claimed. | Name recurring design structures with their intent, context, participants, consequences, and trade-offs so teams can reuse reasoning rather than copy code blindly |
| INPUT-02 | https://martinfowler.com/books/refactoring.html | Author’s official book page and publisher-linked metadata; no full-book access claimed. | Change internal structure through small behavior-preserving transformations protected by tests, making each step understandable and reversible |
| INPUT-03 | https://www.pearson.com/en-us/subject-catalog/p/Beck-Test-Driven-Development-By-Example/P200000009421/9780321146533 | Official Pearson publisher metadata and description; no full-book access claimed. | Drive design in short red–green–refactor cycles: express one observable behavior, witness failure for the intended reason, add the minimum implementation, then improve structure |
| INPUT-04 | https://www.pearson.com/en-us/subject-catalog/p/continuous-delivery-reliable-software-releases-through-build-test-and-deployment-automation/P200000009113/9780321670229 | Official Pearson publisher metadata and description; no full-book access claimed. | Keep software releasable through versioned configuration, repeatable pipelines, automated tests, identical artifact promotion, and frequent small changes |
| INPUT-05 | https://www.pearson.com/en-us/subject-catalog/p/working-effectively-with-legacy-code/P200000008984/9780131177055 | Official Pearson publisher metadata and description; no full-book access claimed. | Before changing poorly covered code, find seams, add characterization tests around observed behavior, and introduce the smallest safe point of control |
| INPUT-06 | https://web.stanford.edu/~ouster/cgi-bin/aposd.php | Author’s official Stanford page with edition identity and high-level material; no full-book access claimed. | Reduce complexity by creating deep modules with simple interfaces, hiding decisions, eliminating unnecessary dependencies, and treating complexity as a design signal |
| INPUT-07 | https://www.oreilly.com/library/view/accelerate/9781457191435/ | Authorized O’Reilly publisher/library overview and bibliographic metadata; full-book access was not used. | Measure software delivery through balanced flow and stability outcomes, and treat capabilities such as continuous delivery, architecture, feedback, and culture as hypotheses linked to performance |
| INPUT-08 | https://sre.google/books/sre-book/table-of-contents/ | Full legal online edition provided by Google and consulted at the structural level. | Define reliability as an explicit service objective, use error budgets to balance change and stability, automate toil carefully, and design operations around observable failure and learning |
| INPUT-09 | https://www.computer.org/education/bodies-of-knowledge/software-engineering/v4 | Official IEEE Computer Society landing page and downloadable guide access. | Software engineering spans requirements, architecture, design, construction, testing, operations, maintenance, configuration, process, quality, security, economics, and professional practice; delivery evidence must cover the lifecycle |
| INPUT-10 | https://csrc.nist.gov/pubs/sp/800/218/final | Full official NIST publication and metadata available. | Integrate secure-development preparation, software protection, well-secured production, and vulnerability response into the development lifecycle with defined roles and evidence |
| INPUT-11 | https://slsa.dev/spec/latest/ | Full official public specification read. | Increase software supply-chain assurance through provenance, controlled build processes, verifiable artifacts, and progressively stronger guarantees rather than trusting an opaque binary |
| INPUT-12 | https://owasp.org/www-project-application-security-verification-standard/ | Full official open standard and project page available. | Turn application-security expectations into explicit, testable requirements organized by verification areas and assurance levels |
| INPUT-13 | https://dora.dev/dora-report-2024 | Full official report download, methodology pages, and errata are publicly accessible. | Treat delivery and AI-assisted development outcomes as socio-technical and empirical: measure local effects, expose trade-offs, and retain correction/errata paths |
| INPUT-14 | https://semver.org/ | Full official public specification read. | Declare a public API and communicate compatible additions, fixes, and breaking changes through a deterministic MAJOR |
| INPUT-15 | https://www.iso.org/standard/78176.html | Official ISO metadata, abstract, and preview only; full protected standard not accessed and no conformity is claimed. | Software quality is multidimensional; requirements must address functional suitability alongside performance, compatibility, interaction capability, reliability, security, maintainability, flexibility, and safety where applicable |

Access limits: publisher metadata/description supports identity and high-level publisher/author framing, not a full-book analysis. Full access is claimed only where an official open specification, article, handbook, report, or author-provided edition was actually available. No Amazon/NYT sales chart, SEO list, invented title, or unauthorized copy is used. Brief original paraphrases do not reconstruct protected works. Standards available only by abstract/preview do not support conformity claims. The corpus is purposive and canonical, not exhaustive or systematic.

## Semantic self-audit

- **Input cardinality:** Exactly fifteen source sections, `INPUT-01` through `INPUT-15`, each once; no extra INPUT section.
- **Required source fields:** Every input has bibliographic identity, verification URL, actual access level, original paraphrased principle, limitation/contradiction, and a concrete contract fold.
- **Source integrity:** Identity routes are publisher, DOI/journal, university/author, standards body, professional body, library/government, or official primary-project pages. Access labels are not silently upgraded.
- **Contract completeness:** All seventeen exact canonical headings are present, each with testable requirements, authority boundaries, failure behavior, and acceptance probes.
- **Application completeness:** Blueprint, Design, Stepper, distinct gates, Builder return, source ledger, failure/recovery behavior, and testable requirements are included.
- **Privacy/authority:** `TENANT=AGK`; no Collective or Private state or secrets were accessed. No live gateway/profile/registry/package/Discord/scheduler/provider mutation occurred.
- **Gate integrity:** START and RELEASE are distinct. START was passed by the owner's explicit `You are LIVE` instruction and authorizes bounded implementation only; RELEASE is explicitly unpassed and is not implied by research, file creation, tests, or START.
- **Residual uncertainty:** This is research-backed package design, not evidence of implementation, successful tests, standards conformity, legal compliance, human acceptance, deployment readiness, or operational benefit.

## Builder fold-in contract

This fold-in accepts the existing Brief → Blueprint → Design → Stepper chain for `TENANT=AGK` as the bounded implementation specification. It does not claim that any package, profile, integration, evaluation, or recovery operation has been implemented. The owner's explicit `You are LIVE` instruction is the passed START event for bounded implementation; RELEASE is a separate gate and remains unpassed. This file mutation grants no authority to mutate packages, profiles, gateways, registries, Discord, OAuth, providers, schedulers, remote systems, or secrets.

### Handoff validation

| Element | Fold-in validation |
|---|---|
| Brief | Accepted as an AGK-only, research-bounded implementation brief; it excludes deployment, publication, conformity, and cross-tenant access. |
| Blueprint | Accepted: traceable guarded delivery from requirements through evidence, review, package, staging, and separately authorized release; autonomous deployment, rewrite-first change, and test-count theatre remain rejected. |
| Design | Accepted as proposed architecture: immutable build evidence, isolated work, deterministic allowlisted commands, build-once artifact identity, separated evaluation planes, exact-target mutation, host-managed secrets, and no authority by designation. |
| Stepper | Accepted in S0–S9 order with characterization before behavior change, witnessed RED before GREEN, independent review, reproducible packaging, read-only Doctor, forced rollback failure, and isolated restore before scale. Invalid or skipped prerequisites block and preserve a resumable checkpoint. |
| START | **PASSED** only by the owner's explicit `You are LIVE` instruction. Scope is bounded implementation for `builder-os`, `TENANT=AGK`; it does not authorize deployment or any mutation forbidden by this pass. |
| Risks | Explicitly retained: abstraction can hide state; tests can miss behavior; automation can amplify defects; metrics can be gamed; provider fallback can weaken policy; dependencies can compromise supply chain; rollback can fail; Discord identity/replay/rendering can be unsafe; protected-source access limits constrain claims. |
| Fixtures | Required fixtures are wrong tenant/root, stale profile/approval/evidence, prompt injection, path traversal/symlink, secret canary, malformed or partial tool output, unknown external outcome, flaky/nondeterministic build, tampered artifact, migration interruption, rollback failure, isolated restore, provider outage, Discord spoof/replay/stale digest/public-channel/rendering cases. |
| Gates | G0 remains bounded research evidence; G1–G3 are covered by the accepted chain and owner START event; G4 and G5 require real staging/review evidence; RELEASE remains **NOT PASSED** and requires a distinct owner/controller event bound to the exact candidate digest. |
| Builder return | Must provide exact target and tenant, full changed-file list and digest, per-requirement trace, decisions and threat model, real commands/exit states, test status inventory, package/SBOM/provenance/license/schema/migration evidence, authority/data-flow matrix, independent findings, Doctor, rollback and isolated recovery evidence, deviations, limitations, and explicit START/RELEASE states. |

### Compact traceability and implementation contract

All acceptance tests below are deterministic scripts or fixtures with explicit inputs, expected state/output, exit code, and no network dependence unless the test is specifically for an integration boundary. A failed, skipped, flaky, or unverified test is non-passing. Every mutation contract requires exact target, expected pre-revision, idempotency or a compensating action, bounded retry, redacted evidence, and read-back; absent safe recovery blocks forward execution.

| Surface | Source INPUT IDs | Implementation and authority boundary | Deterministic acceptance test | Failure behavior and recoverability |
|---|---|---|---|---|
| Package | 02, 04, 10, 11, 14 | Build one versioned `builder-os` candidate containing manifest, schemas, policies, skills, fixtures, migrations, dependency/license inventory, SBOM, provenance, and hashes. Package presence grants no install, registry, gateway, profile, deploy, START, or RELEASE authority. | Two clean isolated builds from the same inputs yield the declared identical digest; tamper, symlink/path escape, unsupported platform, and dry-run install/uninstall fixtures reject deterministically. | Abort atomically on mismatch or unknown dependency; preserve the prior version and emit a checksum-pinned candidate plus inverse/restore instructions. |
| Nano Director | 01, 03, 07, 09 | The owning agent is `Nano Director`; it binds the accepted brief to atomic requirements, risk, decisions, increments, budgets, evidence, and gates. It may coordinate or stop work, not invent scope, self-approve, deploy, or cross tenant/root. | Missing target, conflicting authority, injected source instruction, absent acceptance criterion, and self-approval fixtures each return the expected typed `BLOCKED` state. | Fail closed with the preserved blocker and minimum owner decision; resume only from the recorded checkpoint after valid evidence. |
| NanoTeam | 01, 02, 09, 10 | Typed least-privilege roles: architect, stepper, implementer, test engineer, specification reviewer, security reviewer, code-quality reviewer, release verifier, and recovery engineer. Implementers cannot close their own critical findings; provider plurality is not human independence. | Malicious repository text, malformed patch, reviewer conflict, timeout, and missing-test fixtures preserve role boundaries, dissent, and zero promotion. | Isolate the failed role/output without silent authority expansion; retry only a safe deterministic step or return to Nano Director with evidence. |
| Profiles | 08, 09, 12, 14 | Create only when separately executing implementation: isolated `builder-os` profile, `TENANT=AGK`, explicit repository roots, tools, network, secret references, budgets, risk ceiling, environment class, tests, owning agent, and provider routes. It cannot alter global Hermes or borrow Private/Collective/client authority. | Schema test rejects unknown/stale profile, root escape, secret echo, missing owner/provider/fallback/Discord mode, forbidden live tool, or tenant other than AGK; assert zero external mutation. | Refuse activation and retain the last valid profile; recovery is validated restoration from a versioned redacted profile snapshot. |
| Ordered skills | 02, 03, 05, 09, 10 | Enforce: understand → trace requirements → threat/risk → characterize → witnessed RED → minimal GREEN → refactor while green → targeted/full verify → independent reviews → evidence → rollback/recovery review → handoff. Skills cannot skip gates or imply product validity. | State-machine fixtures attempt GREEN without witnessed RED, refactor on red baseline, package before full verify, and release before review; each transition is rejected at the first unmet guard. | Store a resumable checkpoint and preserve evidence; recovery restarts at the first unmet prerequisite, never by relabeling prior output. |
| Deterministic programs | 02, 03, 04, 11, 14 | Programs own parsing, schemas, tests, lint/type/security checks, hashes, diff/migration limits, package assembly, and reproducibility. Run only explicit allowlisted commands in authorized roots; never shell-interpolate source text or grant gates. | Fixed fixtures assert exact stdout/stderr class, exit status, timeout, artifact digest, and no writes outside a temporary root under malformed input, disk failure, flaky test, path traversal, and replay. | Non-zero, timeout, partial write, or nondeterminism fails closed with redacted diagnostics; clean temporary state and retain pre-state/candidate evidence for replay. |
| MCP/tool contracts | 06, 09, 10, 12 | Each tool declares typed input/output, side-effect class, exact target/tenant, timeout, idempotency, retry policy, redaction, and read-back. Read, local write, remote write, spend, publish, and production are distinct capabilities; prose cannot upgrade them. | Contract tests cover omitted target, invalid schema, duplicate idempotency key, partial success, unknown outcome, auth wall, and success response without read-back; no case may report false success. | Stop on ambiguity or unverifiable outcome; do not blindly retry mutations. Reconcile by exact-target read-back, then compensate or escalate with immutable evidence. |
| Knowledge/memory scopes | 01, 05, 09, 10, 15 | Separate canonical requirements/sources, decisions, ephemeral context, artifacts, test evidence, operational observations, and promoted lessons with provenance/version/retention. Exclude secrets and Private/Collective/client or unrelated project state. | Secret canary, cross-project retrieval, stale requirement, provenance collision, unsupported lesson promotion, revision, and deletion fixtures assert quarantine, denial, and dependent invalidation. | Quarantine suspect records and invalidate dependents; recover only from provenance-verified scoped records, with deletion/tombstone semantics preserved. |
| Provider routes | 03, 07, 10, 11, 13 | Profile must name an approved primary provider/model and policy-equivalent fallback per task/privacy/code/cost class before activation; no default is inferred. Context is minimized; credentials and unrelated memory never enter prompts. | Outage, model-version drift, malformed patch, prompt injection, exfiltration request, and non-equivalent fallback fixtures assert approved route trace or deterministic stop. | Stop rather than fabricate or weaken privacy/licensing/risk policy; resume on an approved equivalent route from the same redacted input and preserved model/version trace. |
| Workflows | 02, 03, 04, 05, 08, 09 | Implement guarded states for intake, Blueprint, Design, Stepper, RED/GREEN/refactor, review, package, staging request, release request, observation, incident, rollback, and recovery. Build success cannot jump to deployment. | Transition table rejects DRAFT→RELEASED, changed digest after approval, migration interruption, stale review, and wrong tenant; exact safe next states are asserted. | Material change invalidates stale evidence/approval; rollback or recovery follows the recorded pre-state. Invalid transitions have zero side effects. |
| Bounded automations | 04, 07, 08, 10, 11, 13 | Allow only separately configured CI, tests, dependency/provenance scans, artifact retention, and authorized health checks with owner, scope, budget, stop, and audit. No auto-merge/deploy, secret rotation, gateway/profile/registry mutation, or cross-tenant action. | Duplicate tick, forked untrusted PR, excessive matrix, stale token/approval, repeated failure, unexpected volume, and production target fixtures assert idempotence or immediate circuit break. | Pause on uncertainty and record a redacted alert; bounded retries apply only to read/idempotent work. Recovery requires owner-reviewed state reconciliation. |
| Evaluations | 03, 05, 07, 08, 09, 10, 12, 13, 15 | Cover requirement, unit/schema/property/integration/system, security/privacy/accessibility/performance, migration/rollback/recovery, provenance, and human acceptance; separate pass/fail/blocked/not-run and never rank individuals or claim conformity from partial source access. | Fixed suite includes mutation, wrong tenant, prompt injection, secret, stale dependency, partial tool write, unrun test, rollback failure, isolated restore, and fabricated-evidence fixtures with expected classifications. | Any critical leak, bypass, fabrication, unrecoverable migration, supply-chain fault, or blocking finding halts promotion; rerun from clean fixtures after remediation. |
| Discord control surface | 08, 10, 12 | Explicit current mode is `DISABLED_UNPROVISIONED`. Future mode may become `PRIVATE_AGK_CONTROL` only after owner-created Discord application, bot, OAuth consent/install, actor/channel allowlist, and separately authorized gateway binding. Discord displays signed expiring status/evidence and requests gates; it is not canonical identity, code, secret storage, or deploy authority. | Mock-only tests cover spoofed actor, wrong/public channel, replay, expired signature, stale candidate digest, markdown/render injection, oversize output, and missing host verification; assert zero gate/deploy transition. | Reject and audit redacted metadata; never retry approval or mutation messages blindly. Disable the route and fall back to local canonical records without losing build state. |
| Doctor | 06, 08, 09, 11, 14, 15 | Implement read-only `builder-os doctor` for package/provenance/hash, dependency/schema/version compatibility, tool/provider routes, test and gate state, migrations, Discord mode, rollback prerequisites, and recovery readiness. It cannot scan unrelated roots, expose secrets, fix, or pass gates. | Golden fixtures break one dependency, signature, provider/fallback, migration marker, Discord mode, and recovery pointer at a time; exact finding code/severity and zero filesystem/external mutation are asserted. | Skipped/inaccessible checks report `UNKNOWN`, never healthy. Recovery is a separately authorized plan referencing the exact finding and last-known-good artifact. |
| Rollback | 02, 04, 05, 08, 14 | Every mutable increment declares pre-state/revision, inverse or compensation, data effect, window, stop point, and post-rollback verification; prefer transactional or expand-contract changes. Scope is the exact authorized AGK target only. | Forced failures before and after commit, stale revision, incompatible schema, and non-idempotent inverse assert restored state or an exact unresolved delta, never a false pass. | Missing safe inverse blocks forward work. Failed rollback freezes mutation and enters recovery with immutable evidence and owner escalation. |
| Recovery artifact | 04, 08, 10, 11, 14 | Produce a versioned checksum-pinned, rights-clean recovery artifact with manifest, authorized source/config references, schemas/migrations, dependency/license inventory, SBOM/provenance, binaries if applicable, restore order, verification commands, and limitations; no credentials or protected source copies. | Restore into an empty isolated fixture, verify hashes/schema/state/tests, reject wrong version/platform, and run secret/license scans plus a disaster-path drill. | Verify before target mutation; missing/invalid hash, dependency, rights, platform, or schema blocks restore. Preserve failed-restore evidence and the untouched target. |
| Librarian best advice | 01–15 | Implement one thin reversible vertical slice from requirement to witnessed RED, minimal GREEN, green refactor, independent review, package evidence, Doctor, rollback, and isolated restore before scaling agents or integrations. Advice is not authorization. | A reviewer traces requirement→diff→test→artifact, reproduces the candidate, rejects it, forces failure, rolls back, restores, and confirms no tenant/secret/rights leakage. | Missing target, owner, acceptance test, safe rollback, or recovery evidence yields a blocked handoff, not a substitute project or plausible output. |
| Dedicated bot commands | 08, 10, 12 | Reserved future private-AGK commands: `/builder status`, `/builder plan`, `/builder tests`, `/builder diff`, `/builder blockers`, `/builder doctor`, `/builder rollback-preview`, `/builder recovery-check`, `/builder request-start`, and `/builder request-release`. Read commands expose bounded redacted evidence; request commands create signed expiring requests only and cannot self-pass gates or deploy. Registration/installation is owner-controlled through the Discord application and OAuth gates. | Command schema and mocked authorization tests assert exact subcommands, role/channel/tenant allowlists, candidate digest binding, expiry/replay prevention, output limits, redaction, and zero mutation for previews/requests. | Unknown/unauthorized/stale/replayed commands reject with a redacted audit event. Disable commands without altering canonical build records; no command may bypass local Doctor, rollback, recovery, START, or RELEASE guards. |

### Explicit integration and release boundaries

- **Package/profile/owner:** Intended package and isolated profile are both `builder-os`; owning agent is Nano Director. Their creation or activation is future bounded implementation work, not performed by this fold-in.
- **Provider/fallback:** Both routes are mandatory explicit profile fields and must be policy-equivalent for the task; the concrete provider/model values remain unresolved until the authorized environment is inspected. Missing or weaker fallback means stop, not implicit substitution.
- **Discord application/OAuth:** Current mode is `DISABLED_UNPROVISIONED`. Gareth/owner controls application creation, bot credentials, OAuth consent/install, and reusable secrets. No agent may request reusable secrets in chat, create or install the application, bind a gateway, register commands, or claim live Discord readiness under this file-only pass.
- **Doctor/rollback/recovery evidence:** RELEASE evidence must include fresh read-only Doctor output, a real non-production forced-failure rollback with read-back, and a checksum-verified isolated restore from the recovery artifact for the exact candidate digest.
- **Release:** START is passed for bounded implementation. RELEASE remains distinct and unpassed; staging, human review, residual-risk acceptance, exact digest, owner event, and all external/live authorities remain required.

### Builder fold-in verdict

`FOLDED_BY_BUILDER_PROFILE: true`

`TENANT=AGK`

`START: PASSED_BY_OWNER_EXPLICIT_YOU_ARE_LIVE`

`RELEASE: NOT_PASSED_DISTINCT_GATE`

Unresolved research limitations: the fifteen-source corpus is purposive rather than systematic; several books were validated only through official publisher/author metadata rather than full text; ISO/IEC 25010 was available only through official metadata/abstract/preview and supports no conformity claim; source principles remain context-dependent; no repository, runtime, threat model, provider inventory, Discord application/OAuth state, package, profile, tool, test, staging, rollback, or restore was inspected or exercised by this research fold-in; concrete thresholds, versions, provider/fallback identities, SLOs, costs, legal/licensing conclusions, usability, operational benefit, and production fitness therefore remain implementation-stage evidence questions. Protected works are neither reproduced nor reconstructed.

## Builder fold-in contract — Hermes 0.21 / 0.5.0

Dated: 2026-09-02. Runtime inspected: Hermes Agent 0.21.0 (staging tree `cdd4b44f`, canary unit for the `builder-os` profile); production `/opt` remains 0.20.6 and is out of scope for this package.

### What changed in Builder OS 0.5.0

| Dimension | 0.4.4 | 0.5.0 |
|---|---|---|
| Onboarding | Implicit in the Nano Director prompt | Explicit skill `os-onboarding` + workflow `os-onboarding` + referee program `validate-onboarding` |
| Research corpus | 15 Librarian inputs (books) | 15 Librarian inputs kept (INPUT-01..15) **plus** an onboarding ledger of ≤20 canonical sources (books, videos, web, standards) and ≤20 approaches with a merge matrix |
| Owner validation | START only | Four gates (plan, orchestration, programming, agentic) recorded with validator + evidence, then START |
| NanoTeam | 3 roles, one-line prompts | 4 roles (+ `domain-scout`), substantive prompts, `delegate_task` roles, toolsets, budgets, and JSON output schemas |
| Review | Self-declared | Kanban review lane with the bundled `sdlc-review` skill; self-review forbidden |
| Hermes features | none declared | `/plan`, `/goal draft` + `/goal gate add`, `/btw`, `delegate_task.output_schema`, checkpoints, `hermes cron doctor`, `approvals.unattended_mode`, profile distribution manifest (`name`, `hermes_requires`, `env_requires`, `distribution_owned`) |
| Programs | contract, handoff-check | + validate-onboarding, scaffold, hermes-check |
| Doctor | files/identity/handoff/recovery | + Hermes version + feature matrix, onboarding schema, agents/NanoTeam, skills order, secret scan |
| Context | none | `AGENTS.md` discovered from `terminal.cwd` (package root) |

### Traceability to the 15 inputs

INPUT-01/06 (design intent, simplicity) → merge matrix records adopt/adapt/reject with reasons; INPUT-02/07 (refactoring, DORA) → build-cycle review lane and small reversible increments; INPUT-03 (TDD) → test-engineer role with `red_observed` proof; INPUT-04/11 (continuous delivery, SLSA) → deterministic recovery ZIP, immutable registry, doctor; INPUT-05 (legacy) → upgrade path inventories the live OS first; INPUT-08 (SRE) → fresh-session acceptance and cron doctor before automations; INPUT-09/13/15 (SWEBOK, ISO 25010, human factors) → four owner gates as explicit quality reviews; INPUT-10/12 (SSDF, ASVS) → secret scan, protected instruction files, unattended deny; INPUT-14 (versioning) → 0.5.0 with previous 0.4.4 retained and an executable rollback.

### Limits of this fold-in

Sources for future OS themes are gathered per OS at onboarding time (≤20) and are not part of this package. No new protected text was reproduced. The Discord command set was read back live (global: clear, leave, panel, restart, settings, voice; guild: none) without exposing the token. Production Hermes (0.20.6) has not been upgraded by this package; the profile runs on the 0.21 canary unit.

`FOLDED_BY_BUILDER_PROFILE: true`

`TENANT=AGK`

`START: PASSED_BY_OWNER_EXPLICIT_2026-09-02`

`RELEASE: NOT_PASSED_DISTINCT_GATE`

