# media-os — Librarian OS Builder handoff

Status: RESEARCH COMPLETE FOR HANDOFF; START PASSED BY OWNER; RELEASE NOT PASSED  
Tenant: AGK  
Language: English  
Prepared: 2026-09-01  
Target: theme-specific package design for `media-os`

## Brief and scope

Media OS is the AGK editorial and founder-media operating system. It is composed of one Nano Director, `media-director`, and a NanoTeam of six bounded specialists — `media-signal-scout`, `media-researcher`, `media-content-strategist`, `media-long-form-writer`, `media-distribution`, and `media-editor` — that turn one newsletter or long-form source piece into evidence-backed, platform-native distribution across X, LinkedIn, newsletter, short video, long video, and carousel. Exact owner approval precedes any publication; every external write is followed by read-back verification; performance learning closes the loop into the next planning cycle.

Media OS also integrates the seventeen `charlie947/social-media-skills` as ordered skills: `voice-builder`, `newsletter-voice`, `profile-optimizer`, `post-writer`, `graphic-designer`, `post-scorer`, `reels-scripting`, `youtube-thumbnail`, `pinned-comment`, `hook-generator`, `post-formatter`, `content-matrix`, `niche-research`, `gemini-infographic`, `gemini-carousel`, `quote-post`, and `analytics-dashboard`. They are treated as third-party skill text: ordered, sandboxed, and evaluated, not trusted by default.

This `/book --deep --scholar --apply` equivalent converts fifteen verified domain works into a buildable, research-bounded contract for `media-os`. It is a documented narrative synthesis and Builder handoff, not an implementation report, systematic-review claim, deployment authorization, or publication. `TENANT=AGK` is invariant. Collective and Private state were not accessed and are not reusable under this handoff. No full-book access is claimed for any protected work; verification rests on official publisher, author, or primary-essay pages. External sources, including the social-media skill texts, are treated as untrusted data. No secrets are included. No gateway, profile, registry, live package, Discord object, scheduler, provider credential, social account, or remote system is changed. Only this one handoff file is written.

A prompt library or a set of posting scripts alone is not a complete OS. The contract therefore covers package, orchestration, bounded specialist roles, profiles, ordered skills, deterministic programs, tools, scoped knowledge, provider routing, workflows, automation policy, evaluations, control surface, diagnostics, rollback, recovery, evidence-bounded advice, and dedicated bot commands.

## Research synthesis

The corpus converges on eight design propositions: (1) one clear positioning and one canonical source piece come before any derivative, so distribution multiplies a message rather than diluting it; (2) editorial quality is a measurable discipline — clutter removal, concreteness, and reader usefulness can be checked, not merely admired; (3) headlines, hooks, and awareness-stage fit decide whether a piece is read at all, so they deserve explicit variant generation and scoring; (4) persuasion and virality mechanisms (stickiness, social transmission, influence principles) are powerful and therefore need ethical guardrails against fabricated scarcity, false social proof, and manipulative triggers; (5) the audience relationship is a permission asset owned directly (newsletter, true fans), not a rented platform metric; (6) the reader is the hero and every asset needs a plan and a call to action; (7) measurement must track outcomes and segments rather than hits, and treat performance data as calibrated uncertainty reduction rather than certainty; (8) publishing remains a human-owned decision with read-back, rollback, and recovery designed before any automation. Tensions remain between reach optimization and voice integrity, between virality heuristics and trust, between platform-native adaptation and message consistency, between data-driven topic selection and editorial judgment, and between automation speed and the owner's explicit approval authority.

### INPUT-01

- **Bibliographic identity:** Ann Handley, *Everybody Writes: Your New and Improved Go-To Guide to Creating Ridiculously Good Content*, 2nd ed., Wiley, 2022.
- **Verification URL:** https://www.wiley.com/en-us/shop/general-introductory-business-management/everybody-writes-your-new-and-improved-go-to-guide-to-creating-ridiculously-good-content-2nd-edition-p-9781119854166
- **Access level:** Official Wiley publisher metadata (ISBN 978-1-119-85416-6, October 2022) and description; no full-book access claimed.
- **Original paraphrased principle:** Treat writing as a repeatable craft process: an ugly first draft, a deliberate edit pass, and a quality bar that content must be useful to the reader, well made, and empathetic to why the reader is there.
- **Limitations/contradictions:** A craft process cannot supply a distinctive point of view or subject expertise; checklists can homogenize voice; the book addresses marketing writing and does not settle platform-specific format economics.

#### Fold into OS contract

OS layer: NanoTeam role `media-editor` and ordered skill `edit-pass`. Mechanism: every derivative carries a three-field editorial bar (reader usefulness, craft, empathy) recorded as a structured `EditorialReview` with pass/revise and named defects; the ugly-first-draft stage is an explicit workflow state so drafting and editing are never one step. Owner: agentic (`media-editor`) produces the review; a deterministic program validates that the review exists, is complete, and precedes approval. Acceptance test: an asset submitted for owner approval without a complete `EditorialReview` is rejected by the state machine with a typed blocker. Disposition: ADOPT.

### INPUT-02

- **Bibliographic identity:** William Zinsser, *On Writing Well: The Classic Guide to Writing Nonfiction*, 30th anniversary edition, HarperCollins (Harper Perennial), 2006; first published 1976.
- **Verification URL:** https://www.harpercollins.com/products/on-writing-well-william-zinsser
- **Access level:** Official HarperCollins publisher product page and edition metadata; no full-book access claimed.
- **Original paraphrased principle:** Clarity comes from removing clutter: cut unnecessary words, prefer plain language and active constructions, keep one idea per sentence, and let the writer's humanity remain in the prose.
- **Limitations/contradictions:** Simplicity targets can strip nuance or platform idiom; a word-reduction metric is not a quality metric; nonfiction prose norms differ from short-video script or carousel copy.

#### Fold into OS contract

OS layer: deterministic program `clutter-lint` plus `media-editor` cut pass. Mechanism: a rules-based linter reports sentence length distribution, passive-voice share, filler phrases, and jargon density per derivative and per platform profile; the editor's second pass targets a declared reduction band rather than a fixed word count. Owner: deterministic for measurement; agentic for the actual rewrite. Acceptance test: a fixture draft containing seeded filler phrases returns exact finding codes and counts; the linter never modifies text and produces identical output on replay. Disposition: ADOPT.

### INPUT-03

- **Bibliographic identity:** David Ogilvy, *Ogilvy on Advertising*, Vintage (Penguin Random House), 1985.
- **Verification URL:** https://www.penguinrandomhouse.com/books/124131/ogilvy-on-advertising-by-david-ogilvy/
- **Access level:** Official Penguin Random House publisher page (ISBN 9780394729039); no full-book access claimed.
- **Original paraphrased principle:** Research the product and audience before writing, and treat the headline as the decisive element because most readers never go past it; long, specific, informative copy outperforms clever vagueness when the reader is genuinely interested.
- **Limitations/contradictions:** Advertising-era heuristics predate feed algorithms and short video; "long copy" findings do not transfer directly to platforms that truncate; headline dominance can push toward clickbait if unchecked.

#### Fold into OS contract

OS layer: ordered skills `hook-generator` → `post-scorer` inside the `media-content-strategist` and `media-long-form-writer` roles. Mechanism: every derivative must be preceded by a minimum of ten headline/hook variants generated from the research brief, scored against a fixed rubric, with the chosen hook and its score recorded; research (`media-researcher`) is a mandatory predecessor of writing. Owner: agentic for generation and choice; deterministic for cardinality, ordering, and the clickbait guard (hook claims must be traceable to a source-piece claim). Acceptance test: a workflow run that attempts writing before a research brief, or approval with fewer than ten scored hooks or a hook lacking a source-claim reference, is blocked. Disposition: ADAPT.

### INPUT-04

- **Bibliographic identity:** Eugene M. Schwartz, *Breakthrough Advertising*, Prentice-Hall, 1966; currently republished by Brian Kurtz / Titans Marketing.
- **Verification URL:** https://breakthroughadvertisingbook.com/breakthrough-advertising-book/
- **Access level:** Official current-publisher site with author preface and edition history; no full-book access claimed.
- **Original paraphrased principle:** Match the message to the reader's stage of awareness (from unaware to most aware) and to the market's sophistication, because copy that assumes the wrong stage fails regardless of craft.
- **Limitations/contradictions:** Awareness stages are a heuristic taxonomy, not measured states; sophistication assessments are subjective; the framework was written for direct-response mail-order and needs adaptation for follower relationships.

#### Fold into OS contract

OS layer: `media-content-strategist` role and a deterministic `awareness-tag` schema in the content-matrix. Mechanism: each derivative declares a target awareness stage and a market-sophistication assumption; the `content-matrix` skill must produce a spread across stages rather than clustering on "most aware"; the rationale is preserved as a strategist hypothesis. Owner: agentic assignment; deterministic schema validation and distribution check. Acceptance test: a distribution plan where all derivatives share a single awareness stage without an explicit owner waiver is flagged as a plan defect; missing stage fields fail schema validation. Disposition: ADAPT.

### INPUT-05

- **Bibliographic identity:** Al Ries and Jack Trout, *Positioning: The Battle for Your Mind*, McGraw-Hill, 2001 (20th anniversary edition; first published 1981).
- **Verification URL:** https://www.mheducation.com/highered/mhp/product/positioning-battle-your-mind.html
- **Access level:** Official McGraw Hill product page (ISBN 9780071705875, © 2001); no full-book access claimed.
- **Original paraphrased principle:** Positioning is what you occupy in the audience's mind relative to alternatives; own one clear idea, avoid line extension that blurs it, and accept that repositioning is costly.
- **Limitations/contradictions:** Positioning theory assumes a fairly stable category; founder media often creates categories; "one word" discipline can under-serve multi-topic founders and must be balanced against genuine range.

#### Fold into OS contract

OS layer: ordered skills `voice-builder` and `profile-optimizer`; knowledge scope `positioning-record`; Doctor check. Mechanism: a single versioned `PositioningRecord` (audience, category, one-idea claim, contrast, forbidden drifts) is the root document every specialist reads; profile copy, bios, and pinned content derive from it; Doctor reports drift when recently approved derivatives contradict the record. Owner: owner-authored and versioned; deterministic drift detection is advisory, agentic interpretation is required. Acceptance test: change the positioning record and verify all dependent artifacts are marked stale; submit a derivative tagged with a forbidden drift and verify the strategist must attach an explicit exception. Disposition: ADOPT.

### INPUT-06

- **Bibliographic identity:** Chip Heath and Dan Heath, *Made to Stick: Why Some Ideas Survive and Others Die*, Random House, 2007.
- **Verification URL:** https://www.penguinrandomhouse.com/books/77687/made-to-stick-by-chip-heath-and-dan-heath/
- **Access level:** Official Penguin Random House publisher page (ISBN 9781400064281, published January 2007); no full-book access claimed.
- **Original paraphrased principle:** Ideas that survive are simple (core message), unexpected, concrete, credible, emotional, and carried by stories; the writer's own expertise is the main obstacle because it hides what the audience does not yet know.
- **Limitations/contradictions:** The traits are illustrated by cases rather than proven causally; "unexpected" can degrade into gimmick; concreteness competes with brevity on short formats.

#### Fold into OS contract

OS layer: evaluation rubric inside `post-scorer` and `carousel`/`quote-post` skills. Mechanism: the derivative scorer uses six named dimensions (simple, unexpected, concrete, credible, emotional, story) with a required "curse of knowledge" check where the editor states one assumption the reader may not share; credibility must cite the source piece or a verified source. Owner: agentic scoring; deterministic completeness of the six fields and the assumption statement. Acceptance test: a scored asset missing any dimension or the assumption statement fails; a "credible" score above threshold without a citation is rejected. Disposition: ADAPT.

### INPUT-07

- **Bibliographic identity:** Jonah Berger, *Contagious: Why Things Catch On*, Simon & Schuster, 2013.
- **Verification URL:** https://jonahberger.com/books/contagious/
- **Access level:** Author's official book page with publisher identity and ISBN; no full-book access claimed.
- **Original paraphrased principle:** Sharing is driven by social currency, environmental triggers, emotional arousal, public visibility, practical value, and stories; content designed around these is more likely to be passed on.
- **Limitations/contradictions:** Virality research is largely observational; high-arousal emotion can favor outrage; optimizing for shares can conflict with positioning and trust, and platform algorithms change what "public" means.

#### Fold into OS contract

OS layer: `media-distribution` role and `content-matrix` skill, evaluated as an EXPERIMENT track. Mechanism: distribution plans tag each derivative with the intended transmission mechanism (e.g., practical value, trigger, story) and the plan must include at least one practical-value derivative per source piece; high-arousal negative framing requires an explicit owner flag; trigger-based timing is hypothesis-tested against performance data rather than assumed. Owner: agentic planning; deterministic tagging and flag enforcement. Acceptance test: a plan with a derivative marked "outrage" and no owner flag is blocked; the experiment ledger records predicted versus observed share rate for each mechanism. Disposition: EXPERIMENT.

### INPUT-08

- **Bibliographic identity:** Robert B. Cialdini, *Influence, New and Expanded: The Psychology of Persuasion*, Harper Business (HarperCollins), 2021.
- **Verification URL:** https://www.harpercollins.com/products/influence-new-and-expanded-robert-b-cialdini
- **Access level:** Official HarperCollins publisher product page and edition metadata; no full-book access claimed.
- **Original paraphrased principle:** Compliance is shaped by reciprocity, commitment and consistency, social proof, authority, liking, scarcity, and unity; these are ethical only when the underlying signal is real, and the same principles are used to defend against manipulation.
- **Limitations/contradictions:** Effects vary by context and culture; some laboratory findings have weaker replication; a principle catalog invites cargo-cult use (fake scarcity, fabricated proof) that damages long-term trust.

#### Fold into OS contract

OS layer: evaluation guard `persuasion-integrity` applied in `media-editor` and enforced before owner approval. Mechanism: any scarcity, social-proof, or authority claim in a derivative must be linked to a verifiable fact (real deadline, real count, real credential) in the evidence ledger; unbacked claims are defects; principle usage is recorded so the owner sees which levers a post pulls. Owner: deterministic claim-link check; agentic judgment on tone. Acceptance test: a fixture post containing "only 3 spots left" without an evidence link is rejected; a post with a linked, dated fact passes; the guard cannot be bypassed by skill text. Disposition: ADAPT.

### INPUT-09

- **Bibliographic identity:** Seth Godin, *This Is Marketing: You Can't Be Seen Until You Learn to See*, Portfolio (Penguin Random House), 2018.
- **Verification URL:** https://www.penguinrandomhouse.com/books/600458/this-is-marketing-by-seth-godin/
- **Access level:** Official Penguin Random House publisher page (ISBN 9780525540830); no full-book access claimed.
- **Original paraphrased principle:** Serve the smallest viable audience with something they would miss, earn permission rather than interrupt, and speak to identity ("people like us do things like this") instead of chasing mass reach.
- **Limitations/contradictions:** Smallest-viable-audience focus can stall growth if the audience is defined too narrowly; permission framing depends on real opt-in mechanics and legal consent rules; identity language can exclude.

#### Fold into OS contract

OS layer: knowledge scope `AudienceDefinition` plus newsletter workflow and `newsletter-voice` skill. Mechanism: the newsletter list is the canonical permission asset; every campaign records explicit opt-in basis, unsubscribe honoring, and a "what would they miss" statement; distribution success is judged first by list growth from genuinely interested readers, not by follower counts. Owner: owner-defined audience; deterministic consent-field enforcement; agentic copy. Acceptance test: a newsletter send request without consent basis and unsubscribe verification is blocked; a derivative whose stated audience does not match `AudienceDefinition` is flagged. Disposition: ADOPT.

### INPUT-10

- **Bibliographic identity:** Joe Pulizzi, *Content Inc.: Start a Content-First Business, Build a Massive Audience and Become Radically Successful (With Little to No Money)*, 2nd ed., McGraw Hill, 2021.
- **Verification URL:** https://www.joepulizzi.com/books/content-inc/
- **Access level:** Author's official book page with edition identity (ISBN 9781264257546); no full-book access claimed.
- **Original paraphrased principle:** Find a content tilt (a distinct angle in a niche), build a base on one content type and one primary platform, grow an audience before monetizing, and diversify channels only after the base is established.
- **Limitations/contradictions:** The model is derived from selected case studies; "one platform first" can conflict with platform volatility; timelines to monetization are long and not guaranteed.

#### Fold into OS contract

OS layer: Nano Director doctrine "one source piece first" and workflow sequencing. Mechanism: the newsletter/long-form source piece is the canonical base; no derivative is drafted until the source piece is approved; the content tilt is recorded next to the positioning record; channel diversification is a planned phase, not a default fan-out. Owner: deterministic sequencing gate; agentic tilt articulation. Acceptance test: a request to generate X or LinkedIn derivatives from an unapproved source piece is rejected; the tilt statement must exist before `niche-research` outputs are accepted. Disposition: ADOPT.

### INPUT-11

- **Bibliographic identity:** Nicolas Cole, *The Art and Business of Online Writing: How to Beat the Game of Capturing and Keeping Attention*, independently published, 2020.
- **Verification URL:** https://books.google.com/books/about/The_Art_and_Business_of_Online_Writing.html?id=JO2PEQAAQBAJ
- **Access level:** Google Books bibliographic record and author identity (author site https://www.nicolascole.com/); no full-book access claimed; self-published work, so no traditional publisher page exists.
- **Original paraphrased principle:** Treat online writing as a data-informed game: study which categories and headline formats already earn attention, practice in public, build a library of proven pieces, and repurpose that library across formats.
- **Limitations/contradictions:** Optimizing for proven categories can produce sameness; the evidence is the author's own experience; the "game" framing can drift into engagement bait unless bounded by positioning and integrity guards.

#### Fold into OS contract

OS layer: performance-learning loop feeding `content-matrix` and `analytics-dashboard`; knowledge scope `ContentLibrary`. Mechanism: approved pieces and their observed performance are stored as a searchable library; the strategist proposes next topics from library evidence and headline-format outcomes, with each proposal labeled as data-derived or judgment-derived; repurposing draws from the library rather than fresh invention. Owner: deterministic library indexing and provenance; agentic proposal. Acceptance test: a topic proposal cites at least one library record or is labeled judgment-derived; library entries without provenance and performance timestamp are rejected. Disposition: ADAPT.

### INPUT-12

- **Bibliographic identity:** Donald Miller, *Building a StoryBrand 2.0: Clarify Your Message So Customers Will Listen*, HarperCollins Leadership, 2025 (original edition 2017).
- **Verification URL:** https://storybrand.com/building-a-storybrand-book-new/
- **Access level:** Author/company official book page with edition identity (ISBN 9781400248872); no full-book access claimed.
- **Original paraphrased principle:** Position the customer as the hero and the brand as the guide: name the problem, offer a plan, give a clear call to action, and state what is at stake, so the message survives the reader's limited attention.
- **Limitations/contradictions:** A single narrative template can flatten thought-leadership pieces that are exploratory; forced calls to action reduce trust on platforms where readers expect ideas, not offers.

#### Fold into OS contract

OS layer: deterministic `asset-script` schema used by `post-writer`, `reels-scripting`, and `gemini-carousel`. Mechanism: each derivative carries a compact script record (reader-as-hero, problem, plan, call to action, stakes); the call to action may be "reply", "read", "subscribe", or "none — idea piece" but must be declared; the editor checks that the founder is framed as guide, not hero. Owner: deterministic schema; agentic content. Acceptance test: a derivative with an undeclared call to action or a hero field naming the founder fails validation; idea pieces pass with an explicit "none" value. Disposition: ADAPT.

### INPUT-13

- **Bibliographic identity:** Kevin Kelly, "1,000 True Fans", *The Technium* (kk.org), essay, 2008 (updated 2016).
- **Verification URL:** https://kk.org/thetechnium/1000-true-fans/
- **Access level:** Full official essay publicly available on the author's site and read at the structural level.
- **Original paraphrased principle:** A creator can sustain a practice with a modest number of true fans who buy what is produced, provided the relationship is direct and the creator keeps most of the value rather than routing it through intermediaries.
- **Limitations/contradictions:** The arithmetic assumes a per-fan spend that many audiences do not reach; discovery still runs through platforms; the essay is a thesis, not an empirical study, and it is one of the two permitted essay-class sources in this handoff.

#### Fold into OS contract

OS layer: evaluations and `analytics-dashboard` metric set; owner economics view. Mechanism: the dashboard tracks direct-relationship proxies (newsletter replies, referrals, paid conversions, repeat engagement) as first-class outcomes separate from platform reach; distribution plans state which derivatives are for discovery versus deepening; no monetization automation is created. Owner: deterministic metric definitions; agentic interpretation; owner decides economics. Acceptance test: a performance report lacking direct-relationship metrics is incomplete; a plan with no deepening derivative for a source piece is flagged. Disposition: EXPERIMENT.

### INPUT-14

- **Bibliographic identity:** Avinash Kaushik, *Web Analytics 2.0: The Art of Online Accountability and Science of Customer Centricity*, Wiley (Sybex), 2009.
- **Verification URL:** https://www.wiley.com/en-us/shop/general-introductory-computer-science/web-analytics-2.0-the-art-of-online-accountability-and-science-of-customer-centricity-p-9780470529393
- **Access level:** Official Wiley publisher metadata (ISBN 978-0-470-52939-3, October 2009) and description; no full-book access claimed.
- **Original paraphrased principle:** Measure outcomes rather than hits, define macro and micro conversions, segment every metric before acting on it, and apply a "so what" test to any report that does not lead to a decision.
- **Limitations/contradictions:** Written for web-property analytics before short-video and algorithmic feeds; platform-reported metrics are opaque and non-comparable; over-segmentation on small founder audiences yields noise.

#### Fold into OS contract

OS layer: `analytics-dashboard` ordered skill and deterministic `metrics-schema` program. Mechanism: each platform profile declares its macro outcome and micro outcomes; every report segments by source piece, platform, format, and awareness stage; each report ends with a decision or an explicit "no decision warranted"; vanity-only reports are non-conforming. Owner: deterministic schema and report validation; agentic decision proposal. Acceptance test: a report with follower count as the only metric fails; a report missing the decision field fails; identical input data yields identical computed metrics on replay. Disposition: ADOPT.

### INPUT-15

- **Bibliographic identity:** Douglas W. Hubbard, *How to Measure Anything: Finding the Value of Intangibles in Business*, 3rd ed., Wiley, 2014.
- **Verification URL:** https://hubbardresearch.com/publications/how-to-measure-anything-study-guide/
- **Access level:** Author's official company page for the book and study guide, plus Wiley catalog identity (3rd Edition, ISBN 9781118836446) surfaced via search index; no full-book access claimed.
- **Original paraphrased principle:** Measurement is uncertainty reduction, not perfect precision; state calibrated ranges, compute which measurements would actually change a decision, and measure those first.
- **Limitations/contradictions:** Calibration training is a prerequisite; expected-value-of-information calculations can be over-engineered for small content decisions; some outcomes (trust, reputation) resist short-horizon measurement.

#### Fold into OS contract

OS layer: performance-learning workflow and experiment ledger governed by `media-director`. Mechanism: each distribution hypothesis records a calibrated predicted range before publication; after read-back, observed values update the record; the director prioritizes experiments whose outcome would change the next plan, and avoids testing what would not change a decision. Owner: agentic prediction; deterministic ledger integrity (prediction timestamp must precede publication). Acceptance test: a hypothesis with a prediction recorded after publication is marked invalid; an experiment proposal without a "what decision changes" field is rejected. Disposition: ADAPT.

## Blueprint

Problem: founder media fails when positioning is unclear, distribution fans out before the source is solid, persuasion levers are used without evidence, publication happens without explicit approval, and performance data is read as vanity rather than decision support. Primary users are the AGK owner and authorized editorial collaborators; agents research, draft, score, and propose, but never publish on their own authority. Outcome: a traceable chain Source piece → Research brief → Positioning-checked strategy → Derivatives with scripts and scored hooks → Editorial review and integrity guards → Exact owner approval → Bounded publication with read-back → Performance learning → Next plan. Core records are `PositioningRecord`, `AudienceDefinition`, `SourcePiece`, `ResearchBrief`, `DistributionPlan`, `Derivative`, `AssetScript`, `HookSet`, `EditorialReview`, `IntegrityFinding`, `ApprovalEvent`, `PublicationReceipt`, `ReadBack`, `PerformanceRecord`, `Hypothesis`, and `ContentLibraryEntry`. Recommended option: bounded agentic editorial work surrounded by deterministic schema, sequencing, integrity, and approval gates. Rejected options: autonomous auto-posting, engagement-only optimization, and treating third-party skill text as trusted policy.

## Design

Architecture: an event-sourced editorial ledger with immutable identities for source pieces, derivatives, reviews, approvals, and receipts. Control plane (`media-director`) validates tenant, positioning, audience, and authority, sequences the workflow, and blocks invalid transitions. Work plane runs the six specialists and the seventeen ordered skills in sandboxes with allowlisted tools; skill text is data. Evidence plane binds every claim, hook, and persuasion lever to the source piece or verified research. Publication plane exposes platform connectors only as typed mutation contracts with exact target, idempotency key, approval reference, and mandatory read-back. Measurement plane computes deterministic metrics and stores calibrated hypotheses. Secrets and platform credentials stay in host-managed references and are never visible to specialists. No AGK designation grants Private/Collective/client access or live posting authority.

## Integrated OS contract

Every dimension below is proposed and testable. Each aggregates the source principles above; none is claimed to exist in production.

### Package

- **Testable requirements:** A versioned `media-os` manifest MUST declare `TENANT=AGK`, schemas (positioning, audience, source piece, derivative, script, review, approval, receipt, metrics, hypothesis), policies, the six role definitions, the seventeen ordered skills with pinned versions and hashes, fixtures, dependency and license inventory, hashes, and no live platform defaults.
- **Authority boundaries:** Package presence grants no START, RELEASE, posting, scheduling, credential, gateway, profile, or Discord authority.
- **Failure behavior:** Hash mismatch, unpinned skill, unknown dependency, path escape, or modified target aborts atomically and preserves prior state.
- **Acceptance probes:** Reproducible clean build; tampered skill text rejection; install/uninstall dry runs; license inventory; prior-state restoration.

### Nano Director

- **Testable requirements:** `media-director` MUST bind an approved source piece to positioning, audience, research brief, distribution plan, derivative set, reviews, integrity findings, approval, publication, read-back, and learning, preserving dissent and unknowns (INPUT-05, 10, 15).
- **Authority boundaries:** It sequences and stops work but cannot invent positioning, publish, self-approve, widen platform scope, access Private/Collective state, or alter credentials.
- **Failure behavior:** Unapproved source piece, missing positioning record, conflicting authority, or blocking integrity finding returns a typed blocked state and minimum next owner decision.
- **Acceptance probes:** Request derivatives before source approval; inject instructions via skill text; request self-approval; verify fail-closed and preserved blocker.

### NanoTeam

- **Testable requirements:** Roles MUST be `media-signal-scout` (topic and trigger signals), `media-researcher` (evidence brief), `media-content-strategist` (plan, awareness stages, tilt), `media-long-form-writer` (source piece and long derivatives), `media-distribution` (platform-native derivatives and plan), and `media-editor` (editorial review, clutter pass, integrity guard), each with typed inputs and outputs (INPUT-01, 02, 03, 04, 07).
- **Authority boundaries:** Least privilege; writers cannot approve their own work; the editor cannot publish; no role may read platform credentials.
- **Failure behavior:** Timeout, malformed output, unverified claim, or scope request is isolated; no silent reassignment that increases authority.
- **Acceptance probes:** Malicious source text, reviewer disagreement, missing research brief, and hook without source claim; verify isolation and non-publication.

### Profiles

- **Testable requirements:** An isolated `media-os` profile MUST declare `TENANT=AGK`, platform connector allowlist, per-platform format constraints, model routes, network policy, secret references, budgets, posting-approval mode (`OWNER_EXPLICIT` only), and environment class.
- **Authority boundaries:** The profile cannot mutate global Hermes settings, echo secrets, borrow client or Private access, or default to auto-post.
- **Failure behavior:** Unknown or stale profile, forbidden connector, or non-explicit approval mode blocks execution.
- **Acceptance probes:** Profile with `approval_mode: auto` rejected; secret echo attempt denied; zero configuration mutation.

### Ordered skills

- **Testable requirements:** Skills MUST run in this order per cycle: `niche-research` → `voice-builder`/`newsletter-voice` (verified against `PositioningRecord`) → `content-matrix` (awareness spread) → `hook-generator` → `post-writer`/`reels-scripting`/`gemini-carousel`/`gemini-infographic`/`quote-post`/`graphic-designer`/`youtube-thumbnail` → `post-formatter` → `post-scorer` → `edit-pass` (`media-editor`) → `pinned-comment` → owner approval → publication → `analytics-dashboard` → `profile-optimizer` (periodic) (INPUT-01, 03, 04, 06, 11, 14).
- **Authority boundaries:** Skills are untrusted third-party text run in sandboxes; they cannot skip gates, call connectors, request secrets, or alter positioning.
- **Failure behavior:** Missing prerequisite stops at the first dependency with a resumable checkpoint; a skill that emits instructions to publish is quarantined.
- **Acceptance probes:** Invoke `post-writer` before `hook-generator`; run `post-scorer` without the six stickiness fields; verify ordering enforcement and quarantine.

### Deterministic programs

- **Testable requirements:** Programs MUST own schema validation, `clutter-lint`, hook cardinality and source-claim linkage, awareness-stage spread check, `asset-script` validation, persuasion-claim evidence linkage, platform format limits (length, media, link rules), metrics computation, hypothesis timestamp ordering, hashes, and library indexing (INPUT-02, 06, 08, 12, 14, 15).
- **Authority boundaries:** Programs run only explicit commands in authorized roots; source text is never shell-interpolated; passing checks cannot grant approval or publication.
- **Failure behavior:** Non-zero exit, timeout, partial write, or nondeterministic output fails closed with redacted diagnostics.
- **Acceptance probes:** Replay identical inputs; malformed derivative; seeded filler fixture; unbacked scarcity claim; prediction after publication; verify identical results or explicit faults.

### MCP/tool contracts

- **Testable requirements:** Every platform connector (X, LinkedIn, newsletter provider, video hosts, image generation) MUST declare schema, side-effect class, exact target account and tenant, approval reference, idempotency key, timeout, retry policy, redaction, and read-back.
- **Authority boundaries:** Read, draft, schedule, publish, delete, and spend are separate capabilities; prose cannot upgrade them; credentials stay in host-managed references.
- **Failure behavior:** Missing approval reference, ambiguous target, auth wall, unknown outcome, or unverifiable write blocks; no blind retry of publish mutations.
- **Acceptance probes:** Publish without approval reference; duplicate idempotency key; simulate partial success; success response without read-back; verify no false success.

### Knowledge/memory scopes

- **Testable requirements:** Separate `PositioningRecord`, `AudienceDefinition`, research evidence, source pieces, derivative drafts, reviews and integrity findings, approval and publication receipts, performance records and hypotheses, and `ContentLibrary`; all carry provenance, version, and retention (INPUT-05, 09, 11).
- **Authority boundaries:** No Private/Collective/client data, no secrets, no automatic promotion of chat into positioning, no cross-tenant reuse.
- **Failure behavior:** Missing scope, stale positioning, provenance collision, or secret detection quarantines the item and marks dependents stale.
- **Acceptance probes:** Positioning revision propagates staleness; library entry without provenance rejected; secret canary quarantined.

### Provider routes

- **Testable requirements:** Routes MUST be selected by task class (research, long-form drafting, short-form adaptation, scoring, image generation, analytics), privacy classification, structured-output need, cost, and availability; primary and policy-equivalent fallback are explicit profile fields; model and version are recorded per artifact.
- **Authority boundaries:** Providers receive minimized context and never credentials, audience personal data beyond aggregate, or unrelated memory; fallback cannot weaken privacy or rights policy.
- **Failure behavior:** Outage, drift, or policy conflict uses an approved equivalent route or stops without fabricated output.
- **Acceptance probes:** Provider outage; injection inside research text; non-approved fallback; verify block and route trace.

### Workflows

- **Testable requirements:** Implement intake, source-piece drafting and approval, research brief, strategy, derivative generation, editorial review, integrity guard, owner approval, publication with read-back, performance capture, hypothesis update, and library promotion as guarded state machines (INPUT-01, 03, 10, 12, 15).
- **Authority boundaries:** No workflow can jump from draft or score to published; owner approval is an external event bound to the exact derivative hash.
- **Failure behavior:** Invalid transition returns state, guards, and safe next action; editing an approved derivative invalidates its approval.
- **Acceptance probes:** Attempt DRAFT→PUBLISHED; modify derivative after approval; fail read-back; verify rejection and invalidation.

### Automations

- **Testable requirements:** Permitted automation is bounded signal scanning, metrics collection, library indexing, staleness checks, and Doctor runs with owner, scope, budget, stop, and audit; scheduled publishing exists only as a queue of already-approved derivatives with per-item owner approval.
- **Authority boundaries:** This handoff creates no jobs. Automation cannot approve, publish unapproved content, reply on the owner's behalf, follow/unfollow, spend, or cross tenant.
- **Failure behavior:** Repeated failures trip a circuit breaker; unexpected volume, stale approval, or unknown outcome pauses and alerts without blind retry.
- **Acceptance probes:** Duplicate tick; expired approval; queue item hash mismatch; verify idempotence and immediate block.

### Evaluations

- **Testable requirements:** Suites MUST cover schema validity, sequencing, editorial bar, clutter metrics, hook cardinality and linkage, awareness spread, stickiness rubric completeness, persuasion-integrity, script completeness, consent fields, metrics schema and decision field, hypothesis ordering, connector contracts, and human acceptance with pass/fail/blocked/not-run distinctions (INPUT-01 through 15).
- **Authority boundaries:** Tests prove only exercised behavior; the Builder cannot self-grant human acceptance, START, RELEASE, or publication.
- **Failure behavior:** Unbacked persuasion claim, publication without approval, secret exposure, tenant leak, or fabricated evidence blocks promotion.
- **Acceptance probes:** Fake scarcity fixture; founder-as-hero fixture; vanity-only report; post-publication prediction; wrong tenant; verify correct non-passing states.

### Discord control surface

- **Testable requirements:** If separately authorized later, expose private AGK editorial status, pending derivatives with previews and scores, integrity findings, approval requests, publication receipts, and performance digests with verified actor, channel, and tenant and signed expiring state, rendered as dynamic views (selects for derivative choice, buttons for Approve/Revise/Reject/Refresh, modals only for free-form non-secret notes).
- **Authority boundaries:** Discord is a control surface, not canonical content storage, identity by label, credential storage, or publication authority; approvals bind to the derivative hash.
- **Failure behavior:** Wrong actor, replay, stale hash, oversized preview, or missing host verification rejects safely and records a redacted event.
- **Acceptance probes:** Replay approval; spoof user; stale derivative hash; public channel; verify zero publication. Current mode is `DISABLED_UNPROVISIONED`.

### Doctor

- **Testable requirements:** Read-only `media-os doctor` MUST report package hashes, skill pin integrity, positioning-record presence and drift signals, audience consent configuration, connector contract availability (without credentials), approval-mode setting, queue state, metrics freshness, hypothesis ledger integrity, and recovery readiness (INPUT-05, 09, 14).
- **Authority boundaries:** Doctor diagnoses only configured AGK targets; it cannot reveal secrets, post, fix automatically, or pass gates.
- **Failure behavior:** Skipped checks are unknown, not healthy; partial access yields bounded findings and a separately authorized repair plan.
- **Acceptance probes:** Break skill pin, remove positioning record, set approval mode to auto, stale metrics; verify exact findings and zero mutation.

### Rollback

- **Testable requirements:** Each publish mutation MUST declare pre-state, target, approval reference, inverse action (delete/unpublish/retract note where the platform allows), data effects, rollback window, and verification; where deletion is impossible, a correction derivative path is predeclared.
- **Authority boundaries:** Rollback targets only the exact authorized AGK account and cannot delete unrelated content or older records.
- **Failure behavior:** Missing safe inverse blocks publication; failed rollback enters recovery with immutable evidence and no success claim.
- **Acceptance probes:** Force failure after publish; platform refuses delete; stale receipt; verify restoration or exact unresolved delta and escalation.

### Recovery artifact

- **Testable requirements:** Produce a versioned, checksum-pinned, rights-clean artifact with manifest, schemas, positioning and audience records, source pieces and approved derivatives, receipts, performance and hypothesis ledgers, library index, skill pins, restore order, verification commands, and known limitations.
- **Authority boundaries:** Exclude credentials, subscriber personal data beyond what the owner authorizes, Private/Collective/client state, and third-party skill text whose license forbids redistribution; restore needs separate target authority.
- **Failure behavior:** Missing hash, incompatible schema, or failed isolated verification blocks restore before mutation.
- **Acceptance probes:** Restore into an empty isolated fixture; verify hashes and ledger integrity; wrong-version rejection; secret and license scan.

### Librarian best advice

- **Testable requirements:** Build one thin reversible vertical slice — one approved source piece, one positioning record, one derivative per platform with scored hooks, editorial review, integrity guard, owner approval, mocked publication with read-back, a performance record, and a calibrated hypothesis — before scaling skills, automations, or connectors (INPUT-10, 15).
- **Authority boundaries:** Advice is not authorization; the owner retains positioning, approval, publication, economics, and credentials.
- **Failure behavior:** If positioning, audience definition, approval mode, safe rollback, or recovery evidence is missing, return a blocked handoff rather than a plausible substitute.
- **Acceptance probes:** A reviewer traces source → derivative → review → approval → receipt → metrics → hypothesis, forces a failure, rolls back, restores, and confirms no tenant or secret leakage.

### Dedicated bot commands

- **Testable requirements:** Reserved future private-AGK commands: `/media status`, `/media queue`, `/media preview <derivative>`, `/media scores <derivative>`, `/media integrity <derivative>`, `/media approve <derivative-hash>`, `/media revise <derivative>`, `/media reject <derivative>`, `/media receipts`, `/media metrics`, `/media doctor`, `/media rollback-preview <receipt>`, and `/media recovery-check`, each reachable through a dynamic view generated from the live registry.
- **Authority boundaries:** Read commands expose bounded redacted evidence; `approve` creates a signed, expiring, hash-bound approval event and never publishes by itself; registration is owner-controlled through the Discord application and OAuth gates.
- **Failure behavior:** Unknown, unauthorized, stale, or replayed commands reject with a redacted audit event; no command bypasses Doctor, rollback, recovery, START, or RELEASE guards.
- **Acceptance probes:** Mocked authorization tests assert subcommands, allowlists, hash binding, expiry, replay prevention, output limits, redaction, and zero mutation for previews.

## Stepper

1. S0 confirm actual workspace, owner, target platforms, credential mechanism, consent and rights constraints, and exclusions. 2. S1 encode tenant, positioning, audience, sequencing, approval-mode, and prohibited-mutation fixtures. 3. S2 implement schemas and deterministic programs (`clutter-lint`, hook linkage, awareness spread, `asset-script`, persuasion-integrity, metrics, hypothesis ordering) with witnessed RED → minimal GREEN → refactor. 4. S3 implement `media-director` state machine and the six role contracts with typed inputs and outputs. 5. S4 wrap the seventeen ordered skills as pinned, sandboxed, untrusted text with quarantine tests. 6. S5 implement mocked connectors with approval binding, idempotency, read-back, and rollback preview. 7. S6 implement `analytics-dashboard` metrics schema, decision field, and calibrated hypothesis ledger. 8. S7 implement read-only Doctor, forced rollback failure, and isolated recovery restore. 9. S8 run the thin vertical slice end to end with mocked publication and record evidence. 10. S9 present G1–G3 artifacts for the recorded START decision. 11. After START only, perform staging G4/G5 against the exact candidate with mocked or owner-authorized sandbox accounts. 12. Present digest, residual risks, rollback and recovery evidence for a separate RELEASE decision. No step may fabricate output, publish, skip a blocking finding, or broaden scope.

## Gates

| Gate | Required evidence | Pass authority | Current state |
|---|---|---|---|
| G0 research coverage | This source/access ledger, synthesis, contradictions, and semantic audit | Librarian reviewer | Passed for a bounded theme handoff only |
| G1 scope/brief | AGK tenant, target platforms, exclusions, authority, consent and rights constraints | Owner/controller | Pending target confirmation |
| G2 architecture | Blueprint, Design, threat model, alternatives, and requirement trace | Architecture/security review | Proposed, not accepted |
| G3 increment plan | Stepper, fixtures, stop conditions, rollback/recovery plan | Builder and reviewer | Proposed, not executed |
| **START** | G1–G3 evidence plus explicit owner authorization bound to target and digest | Explicit owner/controller event | **PASSED by the owner; bounded implementation authority only** |
| G4 staging | Real commands, tests, mocked or sandbox publication with read-back, rollback and isolated recovery evidence | Builder plus independent reviewer | Not run |
| G5 human review | Semantic, editorial, security, privacy, consent, rights, and residual-risk review | Named human reviewers | Not passed |
| **RELEASE** | Exact candidate digest, all blocking findings closed, G4/G5 evidence, distinct approval | Separate explicit owner/controller event | **NOT PASSED; distinct from START** |
| G6 post-release | Observed live publication checks, read-back, and rollback readiness | Release owner | Not applicable |

No local test, source quality, model assertion, or START event can imply RELEASE. START permits only bounded implementation under the accepted contract; live publication, scheduling, connector credentials, gateway/profile/registry mutation, live Discord work, and production access remain forbidden without their own authority and, where applicable, RELEASE.

## Builder return contract

Builder must return: exact authorized workspace and tenant; artifact digest and complete changed-file list; requirement-to-implementation trace for all eighteen dimensions; architecture and threat-model decisions; commands actually executed with exit states; full test inventory distinguishing pass/fail/blocked/not-run; package manifest, skill pin hashes, licenses, and schemas; connector contract and authority matrix; consent, privacy, and rights review; deviations labeled as Builder hypotheses; Doctor output; real non-production rollback and isolated recovery-restore evidence; read-back for any separately authorized external mutation; unresolved risks; and explicit START/RELEASE states. Builder may not self-pass either gate or publish anything. If target, ownership, positioning, approval mode, or authority is missing, return a blocked report rather than create a substitute project.

## Source ledger and access limits

| ID | Verified identity route | Access actually used | Primary contribution |
|---|---|---|---|
| INPUT-01 | https://www.wiley.com/en-us/shop/general-introductory-business-management/everybody-writes-your-new-and-improved-go-to-guide-to-creating-ridiculously-good-content-2nd-edition-p-9781119854166 | Official Wiley metadata and description; no full-book access claimed. | Editorial quality bar and draft/edit separation |
| INPUT-02 | https://www.harpercollins.com/products/on-writing-well-william-zinsser | Official HarperCollins product page; no full-book access claimed. | Clutter removal and clarity as measurable discipline |
| INPUT-03 | https://www.penguinrandomhouse.com/books/124131/ogilvy-on-advertising-by-david-ogilvy/ | Official Penguin Random House page; no full-book access claimed. | Research first; headline as decisive element with variant scoring |
| INPUT-04 | https://breakthroughadvertisingbook.com/breakthrough-advertising-book/ | Official current-publisher site and preface; no full-book access claimed. | Awareness stage and market sophistication tagging |
| INPUT-05 | https://www.mheducation.com/highered/mhp/product/positioning-battle-your-mind.html | Official McGraw Hill product page; no full-book access claimed. | Single versioned positioning record and drift detection |
| INPUT-06 | https://www.penguinrandomhouse.com/books/77687/made-to-stick-by-chip-heath-and-dan-heath/ | Official Penguin Random House page; no full-book access claimed. | Six-dimension stickiness rubric and curse-of-knowledge check |
| INPUT-07 | https://jonahberger.com/books/contagious/ | Author's official book page; no full-book access claimed. | Transmission-mechanism tagging as experiment track with outrage flag |
| INPUT-08 | https://www.harpercollins.com/products/influence-new-and-expanded-robert-b-cialdini | Official HarperCollins product page; no full-book access claimed. | Persuasion-integrity guard requiring evidence links |
| INPUT-09 | https://www.penguinrandomhouse.com/books/600458/this-is-marketing-by-seth-godin/ | Official Penguin Random House page; no full-book access claimed. | Smallest viable audience and permission asset with consent fields |
| INPUT-10 | https://www.joepulizzi.com/books/content-inc/ | Author's official book page; no full-book access claimed. | One source piece first; content tilt; phased diversification |
| INPUT-11 | https://books.google.com/books/about/The_Art_and_Business_of_Online_Writing.html?id=JO2PEQAAQBAJ | Google Books bibliographic record plus author site; self-published; no full-book access claimed. | Data-informed content library and repurposing loop |
| INPUT-12 | https://storybrand.com/building-a-storybrand-book-new/ | Author/company official book page; no full-book access claimed. | Reader-as-hero asset script with declared call to action |
| INPUT-13 | https://kk.org/thetechnium/1000-true-fans/ | Full official essay publicly available on the author's site. | Direct-relationship metrics separate from reach |
| INPUT-14 | https://www.wiley.com/en-us/shop/general-introductory-computer-science/web-analytics-2.0-the-art-of-online-accountability-and-science-of-customer-centricity-p-9780470529393 | Official Wiley metadata and description; no full-book access claimed. | Outcome and segment metrics with mandatory decision field |
| INPUT-15 | https://hubbardresearch.com/publications/how-to-measure-anything-study-guide/ | Author's official company page plus Wiley catalog identity via search index; no full-book access claimed. | Calibrated hypotheses and value-of-information experiment selection |

Access limits: publisher, author, and bibliographic pages support identity and high-level framing, not a full-book analysis. Full access is claimed only for the single public essay (INPUT-13). One essay-class source is used, within the two-essay ceiling. Justin Welsh material was excluded because it is not a book. No Amazon sales chart, SEO list, invented title, or unauthorized copy is used. Brief original paraphrases do not reconstruct protected works. Direct fetches of three Wiley pages returned HTTP 403 to a plain client; their identity was confirmed through the extraction backend or search-index titles and ISBNs, and this is stated rather than upgraded. The corpus is purposive and canonical, not exhaustive or systematic. Alternates verified but not folded: Ryan Holiday, *Perennial Seller* (Portfolio, 2017) at https://www.penguinrandomhouse.com/books/534365/perennial-seller-by-ryan-holiday/ and Daniel Priestley, *Oversubscribed*, 2nd ed. (Wiley, 2020) at https://www.wiley.com/en-us/Oversubscribed%3A+How+To+Get+People+Lining+Up+To+Do+Business+With+You%2C+2nd+Edition-p-00038069.

## Semantic self-audit

- **Input cardinality:** Exactly fifteen source sections, `INPUT-01` through `INPUT-15`, each once; no extra INPUT section.
- **Required source fields:** Every input has bibliographic identity, verification URL, actual access level, original paraphrased principle, limitation/contradiction, and a concrete contract fold naming layer, mechanism, owner, acceptance test, and disposition.
- **Non-duplication:** The fifteen folds address distinct mechanisms: editorial bar, clutter lint, hook scoring, awareness tagging, positioning record, stickiness rubric, transmission experiments, persuasion integrity, permission asset, source-first sequencing, content library, asset script, direct-relationship metrics, outcome metrics, and calibrated hypotheses.
- **Source integrity:** Identity routes are publisher, author, current-publisher, or bibliographic-record pages. Access labels are not silently upgraded.
- **Contract completeness:** All eighteen dimensions are present, each with testable requirements, authority boundaries, failure behavior, and acceptance probes.
- **Third-party skills:** The seventeen social-media skills are integrated as ordered, pinned, sandboxed, untrusted text; none is treated as policy.
- **Privacy/authority:** `TENANT=AGK`; no Collective or Private state or secrets were accessed. No live gateway/profile/registry/package/Discord/scheduler/provider/social-account mutation occurred.
- **Gate integrity:** START and RELEASE are distinct. START was passed by the owner and authorizes bounded implementation only; RELEASE is explicitly unpassed and is not implied by research, file creation, tests, or START.
- **Residual uncertainty:** This is research-backed package design, not evidence of implementation, successful tests, audience results, platform compliance, legal or consent compliance, human acceptance, or operational benefit.

## Builder fold-in contract

This fold-in accepts the Brief → Blueprint → Design → Stepper chain for `TENANT=AGK` as the bounded implementation specification for `media-os`. It does not claim that any package, profile, skill wrapper, connector, evaluation, or recovery operation has been implemented. The owner's START is the passed event for bounded implementation; RELEASE is a separate gate and remains unpassed. This file mutation grants no authority to mutate packages, profiles, gateways, registries, Discord, OAuth, providers, schedulers, social accounts, remote systems, or secrets.

### Handoff validation

| Element | Fold-in validation |
|---|---|
| Brief | Accepted as an AGK-only, research-bounded editorial-OS brief; it excludes publication, scheduling, monetization automation, and cross-tenant access. |
| Blueprint | Accepted: traceable chain from source piece through research, strategy, derivatives, review, integrity guard, explicit approval, read-back publication, and learning; autonomous posting and engagement-only optimization remain rejected. |
| Design | Accepted as proposed architecture: event-sourced editorial ledger, director-controlled sequencing, sandboxed untrusted skills, evidence-bound claims, typed publication contracts with approval binding and read-back, deterministic metrics, host-managed secrets. |
| Stepper | Accepted in S0–S9 order with deterministic programs before role orchestration, mocked connectors before any live account, and Doctor/rollback/restore before scale. Invalid or skipped prerequisites block and preserve a resumable checkpoint. |
| START | **PASSED** by the owner. Scope is bounded implementation for `media-os`, `TENANT=AGK`; it does not authorize publication or any mutation forbidden by this pass. |
| Risks | Explicitly retained: reach optimization can erode voice; virality heuristics can favor outrage; persuasion levers can be misused; platform metrics are opaque; small audiences yield noisy segments; third-party skill text can carry injected instructions; deletion is not always possible after publication; consent rules vary by jurisdiction. |
| Fixtures | Required fixtures are wrong tenant, missing positioning record, unapproved source piece, skill-text injection, hook without source claim, single-stage awareness plan, fake scarcity claim, founder-as-hero script, missing consent basis, vanity-only report, post-publication prediction, approval hash mismatch, connector partial success, read-back failure, rollback refusal, isolated restore, and Discord spoof/replay/stale-hash cases. |
| Gates | G0 remains bounded research evidence; G1–G3 are covered by the accepted chain and owner START; G4 and G5 require real staging and review evidence; RELEASE remains **NOT PASSED** and requires a distinct owner event bound to the exact candidate digest. |
| Builder return | Must provide exact target and tenant, changed-file list and digest, per-requirement trace across eighteen dimensions, decisions and threat model, real commands and exit states, test status inventory, package and skill-pin evidence, connector authority matrix, consent/privacy/rights review, Doctor, rollback and isolated recovery evidence, deviations, limitations, and explicit START/RELEASE states. |

### Compact traceability and implementation contract

All acceptance tests below are deterministic scripts or fixtures with explicit inputs, expected state/output, exit code, and no network dependence unless the test specifically targets a mocked connector boundary. A failed, skipped, flaky, or unverified test is non-passing. Every publish mutation requires exact target, approval reference bound to the derivative hash, idempotency key, bounded retry, redacted evidence, and read-back; absent safe rollback or a predeclared correction path blocks forward execution.

| Surface | Source INPUT IDs | Implementation and authority boundary | Deterministic acceptance test | Failure behavior and recoverability |
|---|---|---|---|---|
| Package | 01, 05, 10, 11 | One versioned `media-os` candidate with schemas, policies, six role contracts, seventeen pinned skills, fixtures, licenses, and hashes; no live connector defaults. | Two clean builds yield the same digest; tampered skill text and unpinned skill are rejected. | Abort atomically; preserve prior version; emit checksum-pinned candidate. |
| Nano Director | 05, 10, 15 | `media-director` sequences source → research → strategy → derivatives → review → approval → publish → learn; cannot publish, approve, or invent positioning. | Derivative request before source approval and self-approval fixtures return typed `BLOCKED`. | Fail closed with preserved blocker; resume from checkpoint only after valid evidence. |
| NanoTeam | 01, 02, 03, 04, 07 | Six typed roles; writers do not approve, editor does not publish, no role reads credentials. | Malicious source text, missing brief, and reviewer conflict fixtures preserve boundaries and zero publication. | Isolate failed role output; return to director with evidence. |
| Profiles | 09, 14 | Isolated `media-os` profile with connector allowlist, format limits, `OWNER_EXPLICIT` approval mode, routes, secret references, budgets. | Schema test rejects `auto` approval, secret echo, unknown connector, non-AGK tenant. | Refuse activation; retain last valid profile; restore from redacted snapshot. |
| Ordered skills | 01, 03, 04, 06, 11, 14 | Seventeen skills pinned and sandboxed in the declared order; skill text is untrusted data. | Out-of-order invocation and skill emitting publish instructions are rejected/quarantined. | Resumable checkpoint at first unmet prerequisite; quarantine with redacted evidence. |
| Deterministic programs | 02, 06, 08, 12, 14, 15 | Schema validation, clutter lint, hook linkage, awareness spread, asset script, persuasion integrity, format limits, metrics, hypothesis ordering, library index. | Fixed fixtures assert exact finding codes, exit status, and replay identity. | Fail closed with redacted diagnostics; no partial writes. |
| MCP/tool contracts | 08, 09, 13 | Typed connectors with side-effect class, target, approval reference, idempotency, timeout, retry, redaction, read-back; publish/delete/spend distinct. | Publish without approval reference, duplicate key, partial success, missing read-back: no false success. | Stop on ambiguity; reconcile by read-back; compensate or escalate. |
| Knowledge/memory scopes | 05, 09, 11 | Positioning, audience, evidence, drafts, reviews, receipts, performance, library separated with provenance and retention. | Positioning revision marks dependents stale; unprovenanced library entry rejected; secret canary quarantined. | Quarantine and invalidate dependents; recover only from provenance-verified records. |
| Provider routes | 03, 11, 15 | Explicit primary and policy-equivalent fallback per task class; minimized context; model/version recorded per artifact. | Outage, injection, non-equivalent fallback fixtures assert route trace or stop. | Stop rather than fabricate; resume on approved route with preserved trace. |
| Workflows | 01, 03, 10, 12, 15 | Guarded states from intake to learning; approval bound to derivative hash; edit invalidates approval. | DRAFT→PUBLISHED, post-approval edit, and read-back failure are rejected with exact next states. | Zero side effects on invalid transition; rollback follows recorded pre-state. |
| Bounded automations | 07, 13, 14 | Signal scan, metrics collection, indexing, staleness checks, Doctor; queue of approved items only; no auto-approve or auto-post. | Duplicate tick, expired approval, hash mismatch assert idempotence or circuit break. | Pause and alert; bounded retries only for read/idempotent work. |
| Evaluations | 01–15 | Cover schema, sequencing, editorial, clutter, hooks, awareness, stickiness, integrity, script, consent, metrics, hypotheses, connectors, human acceptance. | Fake scarcity, founder-as-hero, vanity report, late prediction, wrong tenant fixtures classified correctly. | Any bypass, fabrication, or leak halts promotion; rerun from clean fixtures. |
| Discord control surface | 08, 09 | Mode `DISABLED_UNPROVISIONED`; future `PRIVATE_AGK_CONTROL` with dynamic views, hash-bound approvals, verified actor/channel/tenant. | Mock tests for spoof, replay, stale hash, public channel, oversize preview assert zero publication. | Reject and audit; disable route without losing canonical records. |
| Doctor | 05, 09, 14 | Read-only diagnostics for hashes, skill pins, positioning presence/drift, consent config, connector availability, approval mode, queue, metrics freshness, recovery readiness. | Golden fixtures break one element at a time; exact finding code and zero mutation asserted. | Skipped checks report `UNKNOWN`; repair is a separately authorized plan. |
| Rollback | 08, 12 | Each publish declares pre-state, inverse (delete/unpublish) or predeclared correction path, window, verification; exact account only. | Forced post-publish failure, platform delete refusal, stale receipt assert restoration or exact unresolved delta. | Missing inverse or correction path blocks publish; failed rollback enters recovery. |
| Recovery artifact | 05, 09, 11 | Checksum-pinned, rights-clean artifact of records, ledgers, index, skill pins, restore order; no credentials or unlicensed skill text. | Isolated restore verifies hashes and ledger integrity; wrong version and secret/license scans reject. | Verify before mutation; preserve failed-restore evidence and untouched target. |
| Librarian best advice | 10, 15 | One thin vertical slice end to end with mocked publication before scale. Advice is not authorization. | Reviewer traces source→receipt→hypothesis, forces failure, rolls back, restores, checks leakage. | Missing positioning, approval mode, rollback, or recovery evidence yields a blocked handoff. |
| Dedicated bot commands | 08, 09, 14 | `/media status|queue|preview|scores|integrity|approve|revise|reject|receipts|metrics|doctor|rollback-preview|recovery-check`; approve creates a signed hash-bound event only. | Mocked authorization tests assert allowlists, hash binding, expiry, replay prevention, redaction, zero mutation for reads. | Unknown/stale/replayed commands reject with redacted audit; no command bypasses guards. |

### Explicit integration and release boundaries

- **Package/profile/owner:** Intended package and isolated profile are both `media-os`; owning agent is `media-director`. Their creation or activation is future bounded implementation work, not performed by this fold-in.
- **Provider/fallback:** Both routes are mandatory explicit profile fields and must be policy-equivalent for the task; concrete provider/model values remain unresolved until the authorized environment is inspected.
- **Social-media skills:** The seventeen `charlie947/social-media-skills` are integrated only as pinned, hashed, sandboxed skill text with quarantine tests; their license and redistribution terms must be checked before inclusion in any recovery artifact.
- **Platform connectors and credentials:** No connector is bound and no credential is referenced by this file. Owner controls account authorization, OAuth consent, and reusable secrets through host mechanisms; no agent may request reusable secrets in chat.
- **Discord application/OAuth:** Current mode is `DISABLED_UNPROVISIONED`. Owner controls application creation, bot credentials, OAuth consent/install, and gateway binding.
- **Doctor/rollback/recovery evidence:** RELEASE evidence must include fresh read-only Doctor output, a real non-production forced-failure rollback with read-back, and a checksum-verified isolated restore for the exact candidate digest.
- **Release:** START is passed for bounded implementation. RELEASE remains distinct and unpassed; staging, human review, residual-risk acceptance, exact digest, owner event, and all external/live authorities remain required.

### Builder fold-in verdict

`FOLDED_BY_BUILDER_PROFILE: true`

FOLDED_BY_BUILDER_PROFILE: true

`TENANT=AGK`

`START: PASSED_BY_OWNER`

`RELEASE: NOT_PASSED_DISTINCT_GATE`
