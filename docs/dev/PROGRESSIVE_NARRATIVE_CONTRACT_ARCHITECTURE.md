# Progressive Narrative Contract Architecture

> Japanese name: **段階的物語契約アーキテクチャ**<br>
> Short name: **PNCA**

## Status

This document is the authoritative design for the next destructive NovelForge
architecture.  It deliberately avoids a version-number name: this is a durable
model of authority and refinement, not a temporary compatibility generation.

## Decision: preserve four small authoring calls, not two giant calls

The initial redesign correctly separated **design authority** from **prose
rendering**, but incorrectly compressed physical design generation to two LLM
calls.  One call that simultaneously establishes the series premise, Canon seed,
volume/chapter topology, supporting admissions, and scene allocations is too large
and too cross-coupled for a local model.  It would exchange duplicated work for
schema failures, missed constraints, and shallow causal planning.

PNCA therefore has four **progressively narrower** design contracts:

```text
Brief
  ↓
Series Contract      one series: invariants and macro promises
  ↓
Volume Contract      one volume: bounded arc and chapter obligations
  ↓
Chapter Contract     one chapter: ordered scene slots and handoffs
  ↓
Scene Contract       one scene: executable narrative and Canon mutation
  ↓
Frozen Design Bundle
  ↓
Render / Write       prose only
  ↓
Strict Export
```

The four calls do **not** all decide “what happens” independently.  Each owns a
different resolution and may only refine the accepted parent contract.  This is
progressive specification, not four competing authors.

## Governing authority rule

> **Only the design chain creates story information.  Rendering converts an
> accepted Scene Contract to prose; prose, recaps, and reviews never create a
> later story fact or amend Canon.**

There is no planned-versus-realized Canon split and no post-draft Canon
reconciliation.  Design establishes Canon truth before any prose exists.

| Stage | Narrative authority | Canon authority | Must not decide |
|---|---|---:|---|
| Brief | Human request only | none | Missing authorial facts |
| Series Contract | series invariants and macro promises | creates Canon seed | volume/chapter/scene detail |
| Volume Contract | one volume's bounded dramatic arc | none | exact scene events or mutations |
| Chapter Contract | one chapter's ordered functional slots | none | scene-level Canon changes or prose |
| Scene Contract | one scene's executable events and requirements | creates one Canon event | facts outside its parent bounds |
| Render / Write | presentation only | none | durable story information |
| Summary / analysis | derived audit only | none | later writer or design inputs |
| Export | format conversion only | none | selection, design, or Canon updates |

## The four authoring contracts

### 1. Series Contract — macro scope only

**Input:** validated human Brief.

**Output:** `SeriesContract` and `CanonSeed`.

It establishes only facts that must remain stable for the whole series:

- premise, genre promise, target reader, tone, and ending policy;
- core thematic / causal arc and global non-negotiable requirements;
- Canon seed: world rules, series constraints, Core cast, opening locations,
  initial relationships, chronology, glossary, and opening state;
- volume count/order and a short purpose for each volume;
- stable requirement IDs that later contracts must reference.

It must **not** enumerate chapters, scene beats, scene cast, future exact
locations, one-off clues, or Canon mutations beyond the initial seed.  A Series
Contract is deliberately compact: it defines boundaries, not the entire novel.

```text
series requirement: req_series_mystery
  “The origin of the blank postcard is disclosed by the final volume.”

volume placement: vol_01
  “Establish the postcard's anomaly and make the siblings choose to investigate.”
```

The Series Contract acceptance transaction freezes:

```text
series.contract
series.contract.final_review
series.contract.acceptance
canon.seed
canon.frontier.root
```

The root frontier is created once and is bound to the Canon seed digest from its
first artifact.

### 2. Volume Contract — one volume, bounded arc only

**Input:** accepted Series Contract, relevant Series requirements, and the
selected pre-volume Canon frontier.

**Output:** `VolumeContract` for exactly one volume.

It refines the volume placement into a bounded dramatic contract:

- opening and closing dramatic pressure for the volume;
- chapter count/order and one purpose per chapter;
- requirements inherited from Series Contract and their intended chapter;
- approved admission budget for supporting entities;
- volume completion conditions and unresolved threads intentionally carried out.

It must **not** decide the exact events of a scene, exact dialogue, individual
CanonPatch operations, or a writer-facing state projection.  It can state that a
chapter must establish a clue; it cannot invent the clue's precise discovery
mechanism or mutate an artifact.

```text
volume requirement: req_vol01_investigation
  inherited: req_series_mystery
  “By the end of vol_01, the siblings voluntarily enter the theatre inquiry.”

chapter placement: ch_03
  “Force the first irreversible choice; preserve uncertainty about the sender.”
```

A Volume Contract reads Canon in order to avoid impossible admissions or conflicts,
but it does not advance the frontier.  Its manifest records the seed lineage and
input frontier digest.

### 3. Chapter Contract — one chapter, functional scene slots only

**Input:** accepted Volume Contract, relevant parent requirements, and the exact
pre-chapter Canon frontier.

**Output:** `ChapterContract` containing ordered `SceneSlot`s.

A SceneSlot is intentionally smaller than a Scene Contract.  It assigns a
function, an inherited requirement, and an expected handoff; it does not write the
scene.

```jsonc
{
  "scene_slot_id": "slot_vol01_ch03_02",
  "order": 2,
  "parent_requirement_ids": ["req_vol01_investigation"],
  "function": "Make the protagonist commit to entering the closed theatre.",
  "must_preserve": ["The postcard sender remains unknown."],
  "expected_handoff": "The entry is possible, but the motive is still contested."
}
```

A Chapter Contract owns:

- scene count, order, and the functional purpose of every slot;
- allocation of parent requirements to slots;
- required causal handoffs between slots;
- which slots may introduce a supporting-entity admission already approved by the
  Volume Contract.

It must **not** specify a scene's exact beats, POV-safe observation, exact object
state, CanonPatch, or prose.  Therefore it stays small even when a chapter has
multiple scenes.

### 4. Scene Contract — one executable scene only

**Input:** one accepted SceneSlot, its parent contracts, the exact pre-scene Canon
frontier, and a deterministic transition packet from the previous accepted Scene
Contract.

**Output:** one complete `SceneContract`, its `CanonPatch`, its output Canon event,
and a compiled writer view.

This is the sole stage that makes the exact narrative decision for a scene:

- POV, setting, cast, goal, conflict, required beats, turn, outcome, and hook;
- explicit mapping from each inherited requirement to scene-level implementation;
- typed CanonPatch and explicit no-effect declaration when appropriate;
- end assertions checked against simulated post-patch Canon;
- writer-safe `start_context`, `narrative_contract`, `end_constraints`, and
  `presentation_constraints`.

```text
slot function
  “Make the protagonist commit to entering the closed theatre.”
        ↓ refined exactly once
scene required beat
  “After the warning bell rings inside the empty theatre, Ren takes the postcard
   through the service entrance despite Suzu's objection.”
        ↓ rendered by writer
prose evidence
  an exact span that realizes the required beat
```

A Scene Contract may refine its parents but cannot contradict them or silently
relocate their requirements.  The acceptance validator requires a mapping from
all inherited requirement IDs to one of:

- `implemented` — concrete scene beat IDs;
- `preserved` — an explicit non-disclosure or continuity constraint;
- `deferred` — permitted only when the parent contract explicitly allows a later
  target slot.

This makes hierarchy violations deterministic instead of relying on an LLM review
to notice them.

## Why this does not overload the LLM

| Concern | PNCA control |
|---|---|
| Giant series JSON | Series Contract is forbidden from chapter and scene detail. |
| A volume requires all scene events | Volume Contract creates only chapter purposes and requirement allocation. |
| A chapter emits full scenes | Chapter Contract emits compact SceneSlots, not Canon patches or prose. |
| Scene generation loses long-range intent | It receives only relevant parent requirements plus a sliced Canon frontier. |
| Repeated information drifts | Child contracts use parent requirement IDs and implementation mappings. |
| Context grows with the whole novel | Prompts use bounded, typed projections; no full Canon dump or previous prose chain. |
| Review calls become expensive | Invalid candidates fail deterministic preflight before LLM narrative review. |

The intended payload budget is therefore:

```text
Series Contract  = series invariants + one-line volume placements
Volume Contract  = one volume + one-line chapter placements
Chapter Contract = one chapter + compact functional scene slots
Scene Contract   = one scene + relevant Canon slice + typed patch
Writer           = one compiled scene contract, not a novel outline
```

The runtime should enforce these shape boundaries in prompt descriptions and
semantic validators rather than relying only on token budgets.  A model must never
be asked to output an all-series scene table, a full Canon dump, or prose in a
design contract.

## Parent-to-child refinement contract

Each child artifact records immutable provenance:

```text
parent artifact IDs and content digests
parent requirement IDs consumed
canon lineage root digest
input Canon frontier artifact ID and digest (when Canon is read)
prompt/schema/model configuration digests
```

A parent contract provides **requirements**; its child provides **implementation**.

| Parent output | Child may do | Child may not do |
|---|---|---|
| Series requirement | Allocate it to a volume/chapter | Change its meaning or ending policy |
| Volume requirement | Allocate it to a chapter slot | Invent incompatible volume outcome |
| SceneSlot function | Choose concrete beats and Canon patch | Move it to a different slot without explicit deferment |
| Scene Contract | Render it as prose | Add durable facts or change Canon |

A rejected child never mutates its parent.  A changed accepted parent invalidates
its descendants by digest, and all affected descendants must be regenerated.

## Canon and writer boundary

### Canon mutation

Only two operations create Canon truth:

1. Series Contract acceptance creates `CanonSeed`.
2. Accepted Scene Contract atomically creates one Canon event and next frontier.

Volume and Chapter Contracts may read the current frontier but produce no Canon
patch.  The design phase processes volumes, chapters, and scene contracts in reader
order, so every scene sees the actual accepted design frontier of prior scenes.

All Canon references use one typed grammar:

```jsonc
// Existing entity
{"kind": "character", "id": "char_001"}

// Same-source creation
{"kind": "character", "creation_key": "attendant"}
```

A creation identity is `(source_id, kind, creation_key)`.  Equal human-readable
keys across different kinds are legal; duplicates of the same tuple are rejected.
Raw IDs in typed fields, `@created:<key>`, and bare creation-key references are not
public syntax.

### Writer input

The writer receives the `writer_view` from exactly one accepted Scene Contract:

```text
start_context             pre-scene Canon facts only
narrative_contract        title, goal, conflict, beats, turn, outcome, hook
end_constraints           state that prose must establish by scene end
presentation_constraints  POV, disclosure, style, cast, setting, object limits
```

The writer never receives raw Canon IDs, CanonPatch, events, full Canon, secret
author rationale, a live snapshot, or prior summary prose.

A deterministic transition packet derived from the prior accepted Scene Contract
and Canon frontier may supply an approved continuity boundary.  It never derives
facts from a draft.

## Acceptance, convergent review, and snapshots

### Root cause: a review/revise loop has no convergence guarantee

A serial `candidate → review → revise → review` loop is not a quality system.  It
mutates one current candidate repeatedly and assumes the next revision will retain
all previously repaired properties.  A reviewer can instead flag a different
problem, the revise step can regress a previously satisfied requirement, and the
next reviewer can correctly flag that regression.  More cycles only repeat the
state transition:

```text
repair A → regress B → repair B → regress A
```

A review count cap does not resolve this contradiction.  Selecting the final
candidate merely hides it; handing that candidate to a later stage spreads an
unresolved design defect.  PNCA therefore has **no generic review/revise loop**.
It replaces it with a bounded candidate process whose unresolved state is explicit.

### LLM uncertainty is a permanent architectural condition

Generation, revision, and review are all probabilistic LLM observations.  This is
true for every model size and does not disappear through more review rounds,
majority vote, reviewer self-reported confidence, or a stronger model.  PNCA must
therefore never treat an LLM review result as proof that a semantic requirement is
true or false.

Only structural checks are authoritative facts:

- schema / typed-reference validity;
- provenance, digest, and frontier lineage;
- deterministic Canon patch simulation and replay;
- explicit topology and requirement-ID membership.

Narrative completeness, causal clarity, reader comprehension, style, and whether a
beat is adequately realized in prose are **uncertain observations**.  They remain
valuable evidence, but they are not transformed into deterministic truth by review
repetition.

Every selection policy must declare how it handles such observations:

| Policy | Semantic risks after fixed candidate budget | Status |
|---|---|---|
| `conservative` | Stop at the owner scope for an explicit human decision. | `needs_decision` |
| `best_effort` | Select the policy-best candidate and preserve every unresolved risk. | `selected_with_semantic_risks` |

Both policies reject structural failures.  Neither labels unresolved semantic risks
as `passed`, and neither feeds an LLM's risk claim into later prompts as a new story
fact or mandatory correction.

### Requirement ledger is created before candidate generation

Every contract has an immutable `RequirementLedger` compiled from its parent
contracts and its own explicit acceptance conditions.  It is a finite, typed choice
list, not free-text issue history:

```jsonc
{
  "requirement_id": "req_scene_014_beat_02",
  "owner_scope": "scene_contract",
  "class": "hard",
  "statement": "Ren enters the theatre despite Suzu's objection.",
  "verification_mode": "prose_evidence",
  "allowed_next_owner": null
}
```

A reviewer may report a risk against an existing `requirement_id` and supply
grounded evidence.  It may not turn a newly invented taste, detail, or alternative
plot into a hard requirement after generation.  The report is an observation, not
proof that the requirement is violated.

A newly discovered concern is still preserved; it is classified as one of:

| Classification | Meaning | Effect |
|---|---|---|
| `observed_contract_risk` | LLM evidence suggests an existing requirement may be missing or contradicted. | Candidate risk vector changes; policy decides selection or repair. |
| `structural_failure` | Schema, typed reference, lineage, or deterministic simulation fails. | Candidate invalid. |
| `scope_escalation` | The problem may be real but its predeclared owner is a parent/sibling contract, not the current artifact. | Do not revise locally; return to named owner. |
| `editorial_note` | A grounded reader-facing improvement outside the ledger. | Immutable evidence only; never blocks Canon or selection. |

This does **not** suppress correct issues.  It prevents an unbounded stream of
subjective after-the-fact criteria from masquerading as a contract failure.  Every
reported issue remains in evidence; only explicit contractual obligations may enter
the candidate risk vector.

### Fixed three-audit assessment, not three revision cycles

The requested three reviews are three independent, same-candidate assessments.  No
review sees a candidate modified in response to a previous review.

```text
candidate C0
  ├─ audit 1: parent requirement coverage and scope
  ├─ audit 2: internal causal / disclosure consistency
  └─ audit 3: renderability or draft compliance
          ↓
  immutable assessment matrix for C0
```

Each audit receives the same candidate digest, the same RequirementLedger, and its
explicit review scope.  It returns requirement IDs, status, and evidence—not
free-form replacement prose, `before`/`after` text, or a mandatory repair
instruction.  An audit is an observation channel, not an author with authority to
rewrite the candidate.  Deterministic validation remains a separate, pre-review
gate:

- schema and parent-reference validation;
- parent requirement coverage / explicit deferment validation;
- Canon input-frontier lineage validation;
- for scenes: complete typed-ref resolution, stable-ID minting, dependency-DAG
  patch simulation, post-state assertion, and frontier replay.

The runtime never silently removes no-op operations or repairs an authoring
candidate.  A no-effect scene declares `canon_effect: "none"`; a malformed patch
is a structural failure.

### Audit disagreement is expected and remains unresolved evidence

Independent audits can make conflicting observations about the same requirement, or
can imply mutually incompatible ways to improve a candidate.  This is expected.  A
candidate payload and every audit observation are LLM-produced competing evidence;
the runtime has no semantic oracle that can declare either side correct.

The assessment matrix therefore records claims separately:

```jsonc
{
  "claim_id": "audit_2:req_scene_014_beat_02",
  "candidate_digest": "…",
  "requirement_id": "req_scene_014_beat_02",
  "observation": "risk_observed",
  "evidence": "…",
  "audit_scope": "causal_consistency"
}
```

When audits select the same `requirement_id` with incompatible observations, the
runtime records an `AssessmentDisagreement` using those explicit claim IDs.  This is
a mechanical comparison of typed IDs and enum values only; it does not inspect or
fuzzy-match prose.  Disagreement is never resolved by majority vote, an extra LLM
judge, confidence scores, or discarding the minority claim.

For observations against different requirements that imply competing repairs, no
runtime attempts to merge the natural-language rationale.  A later repair proposal
must declare the claim IDs it treats as assumptions.  Any incompatible assumptions
produce separate candidate branches rather than one prompt containing contradictory
repair instructions.

### Candidate set and uncertainty-aware selection

Candidates are immutable branches.  A repair never overwrites `C0`, and the three
audit outputs are never combined by majority vote into semantic truth.

```text
C0 + assessment(C0)
  ├─ structurally valid, no observed contract risks → selected_without_observed_risks
  ├─ repair hypothesis H1(claim IDs …) → C1          → re-assess whole ledger
  ├─ repair hypothesis H2(conflicting IDs …) → C2    → re-assess whole ledger
  ├─ fresh generation → C3                           → re-assess whole ledger
  └─ scope escalation                                → parent/sibling owner
```

A repair proposal is not a merged instruction list.  It is one explicitly named
hypothesis over a non-conflicting set of audit claim IDs.  Its candidate input
contains that hypothesis, the full RequirementLedger, and the requirements the
source candidate appears to satisfy.  Competing hypotheses create different branches;
no LLM is asked to reconcile contradictory reviewer advice in one response.  Every
resulting candidate is assessed against the *entire* ledger again, never only against
the claims that motivated it.

The selection record stores every candidate's requirement-state observations, all
audit claims, every `AssessmentDisagreement`, the selected hypothesis if any, and the
selection policy/rationale.  A `satisfied → risk-observed` regression is never erased
or hidden; it changes the candidate's explicit risk vector.  This uses explicit
requirement IDs, not forbidden fuzzy matching, free-text issue deletion, or
mechanical prose replacement.

No automatic selection claims semantic correctness.  When candidate branches differ
only through unresolved LLM observations, `conservative` stops.  `best_effort` may
select only through a policy pinned *before* the run—for example, retain the baseline
candidate, prioritize a named user requirement class, or apply an explicit user choice.
The record must say that the outcome is a policy choice among competing evidence, not
that the chosen candidate or its reviews were proven right.

There is no open-ended local repair loop.  The configured candidate budget bounds
cost, not truth.  When it is exhausted:

- structural failure means no candidate is selectable;
- an owner-scope conflict emits an immutable `scope_escalation`;
- unresolved semantic observations follow the declared `conservative` or
  `best_effort` policy from the uncertainty section.

Under `best_effort`, a selected candidate carries its complete risk vector and any
`assessment_disagreement_ids` as `selected_with_semantic_risks`.  Downstream prompts
receive the selected contract, not the review claims.  The risks and disagreements
remain in snapshots, run status, and export manifest for audit; they never silently
become Canon facts or revision instructions.

### Escalate to the owner that can actually resolve the problem

A review selects a requirement ID; its `owner_scope` is predeclared in the
RequirementLedger.  The runtime therefore does not trust a reviewer's free-text
claim about which layer should change.  A real scope escalation becomes an explicit
design decision, not another local rewrite.

| Failure source | Correct owner | Forbidden response |
|---|---|---|
| Missing scene beat or prose evidence | Scene Contract / draft renderer | Alter Series or Canon silently |
| Incompatible SceneSlot obligations | Chapter Contract | Keep rewriting the scene indefinitely |
| Impossible chapter outcome or admission | Volume Contract | Invent an unapproved Canon fact |
| Series invariant, ending, or world-rule conflict | Series Contract | Patch it inside a scene |
| Schema, reference, digest, or frontier defect | Candidate generation / deterministic layer | Human narrative waiver |

Changing an accepted parent creates a new parent artifact and invalidates descendants
by digest.  The affected scope is then designed again from that new authority.
This is deliberate backtracking, not a hidden retry loop.  When `best_effort`
permits risk carrying, only the immutable risk evidence propagates for audit—not a
new story fact, Canon mutation, or next-prompt instruction.

### Structural gates are fail-closed; semantic review is uncertainty-aware

| Finding | Selection result |
|---|---|
| Parse/schema/typed-reference failure | candidate invalid |
| Provenance or frontier failure | candidate invalid |
| Deterministic parent-requirement membership failure | candidate invalid or predeclared scope escalation |
| LLM-observed ledger risk | repair branch, `conservative` decision, or `best_effort` risk-carrying selection |
| Editorial preference | immutable optional evidence; not an authority gate |

A human waiver may cover a named narrative requirement only when release policy
permits it and the waiver becomes a new explicit acceptance input.  Structural,
lineage, digest, and typed-reference failures are never waivable.  A waiver is not
an implicit “continue after review cap” switch, and a `best_effort` selection is
never relabelled `passed`.

A selected scene is an atomic snapshot boundary:

```text
scene.contract
scene.contract.requirement_ledger
scene.contract.assessment_matrix
scene.contract.assessment_disagreements
scene.contract.acceptance  ← selection policy / hypothesis / rationale pinned
canon.frontier  ← output of this exact scene contract
```

There is no snapshot where Canon advanced but the causal Scene Contract is not
selected.  A Volume Contract and Chapter Contract are also snapshot-pinned upon
acceptance so resume always uses explicit inputs.

## Design bundle, render, summary, export

After all scene contracts for a target volume are accepted, the runtime creates a
`DesignBundle` index containing ordered contract IDs, contract digests, required
placement topology, parent contracts, and the volume-end Canon frontier checkpoint.
It does not duplicate full scene payloads.

Render begins only from an accepted frozen bundle.  Every draft is assessed against
its contract requirement IDs and evidence claims.  A deterministic structural
violation cannot be selected.  A model-observed omission, contradiction,
disclosure concern, or unplanned-durable-fact concern enters the draft's semantic
risk vector and follows the selected `conservative` or `best_effort` policy; it is
never silently converted into a passing result.

A prose recap may be created for people, search, and audit.  It is marked derived:

- never input to later design;
- never input to the next writer;
- never a Canon source;
- never a substitute for required-beat evidence.

Export is a pure derivation from an explicit DesignBundle/snapshot.  It validates
ordered topology, selected draft and assessment evidence, artifact/manifest digests,
the bundle's pinned volume-end frontier replay, the pinned semantic-risk / waiver
policy, and any assessment-disagreement IDs plus selection rationale.  A
`selected_with_semantic_risks` export must expose those risks and disagreements in
its manifest; strict export may reject it when the selected release policy requires
no open semantic risks.  Export never reads a current global frontier, creates a
selection snapshot, or mutates Canon.

## Implementation migration order

1. Add the four contract schemas and complete Japanese field descriptions:
   `series_contract`, `volume_contract`, `chapter_contract`, `scene_contract`.
2. Add requirement IDs, parent-refinement mappings, input-frontier provenance,
   acceptance records, and DesignBundle schemas/tests.
3. Implement typed Canon references with `(source_id, kind, creation_key)` identity
   plus whole-patch stable-ID resolution and DAG simulation.
4. Replace current design orchestration with sequential Series → Volume → Chapter
   → Scene acceptance.  Volume/Chapter become narrow contracts, not duplicate
   free-form scene authors.
5. Compile `writer_view`, replace `writer_context`, and remove summary as a
   forward input.
6. Add RequirementLedger, fixed same-candidate three-audit assessment,
   AssessmentDisagreement records, immutable risk vectors, hypothesis branches,
   policy-labelled `conservative` / `best_effort` selection, and strict
   bundle-pinned export.  Delete generic cap-driven `review → revise` advancement.
7. Delete old DSL aliases, duplicate payload assembly, old task resources, and
   compatibility tests.  No compatibility shim remains.

## Minimum acceptance tests

- Series/Volume/Chapter prompts cannot emit lower-level executable content outside
  their contract scope.
- Every child requirement maps to an accepted parent requirement and cannot silently
  change or drop it.
- A Scene Contract cannot be accepted without a selected parent SceneSlot and exact
  pre-scene frontier provenance.
- The same human-readable creation key works across entity kinds; duplicate
  `(kind, creation_key)` within one source fails before review.
- Writer input contains only one compiled writer view; altering a summary cannot
  alter any later writer request.
- Three review calls assess the same candidate digest and cannot observe one
  another's revision; their outputs never become semantic truth through voting.
- Conflicting observations for the same requirement ID create an
  `AssessmentDisagreement`; no majority vote, extra LLM judge, confidence score, or
  minority-claim deletion resolves it.
- Competing repair hypotheses create separate immutable candidate branches.  No
  repair prompt receives contradictory reviewer instructions, and each branch pins
  its assumed claim IDs.
- A revision/fresh candidate is assessed against the complete RequirementLedger;
  a newly observed regression remains in its risk vector rather than disappearing.
- Structural failure is never selectable.  At exhausted candidate budget,
  `conservative` yields `needs_decision`, while `best_effort` yields
  `selected_with_semantic_risks` with all evidence pinned and no risk claim injected
  into downstream prompts.
- A selected Scene Contract and its output frontier always appear in the same
  selection snapshot.
- Export rejects missing/duplicated scene slots, unreviewed drafts, digest mismatch,
  broken frontier chain, or future-volume Canon events.
- A real-model run completes Series → per-volume/Chapter/Scene design → bundle →
  render → strict export, with raw request/response/parsed/validation evidence
  inspected for each contract layer.
