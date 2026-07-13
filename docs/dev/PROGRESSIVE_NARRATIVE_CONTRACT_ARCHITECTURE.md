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
frontier, a `ParentRequirementLedger` compiled only from accepted parent authority,
and a deterministic transition packet from the previous accepted Scene Contract.

**Output:** one complete `SceneContract`, a disjoint Canon-effect declaration, an
output frontier binding, and a compiled writer view.

This is the sole stage that makes the exact narrative decision for a scene:

- POV, setting, cast, goal, conflict, required beats, turn, outcome, and hook;
- explicit mapping from each inherited requirement to scene-level implementation;
- either a non-empty typed `CanonPatch` or an explicit eventless no-effect declaration;
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
relocate their requirements.  Its deterministic candidate preflight requires a
mapping from all inherited requirement IDs to one of:

- `implemented` — concrete candidate scene beat IDs;
- `preserved` — an explicit non-disclosure or continuity constraint;
- `deferred` — permitted only when the parent contract explicitly allows a later
  target slot.

The candidate's beat IDs are a `CandidateCommitmentIndex`: they explain how this
candidate realizes **already-existing** parent obligations, but are not new hard
requirements used to accept the candidate.  Only after selection does the runtime
freeze those beat IDs as the scene's `AcceptedRequirementLedger`, which a draft
must later realize with prose evidence.  This avoids circular self-certification
without adding a fifth authoring call before Scene Contract generation.

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
parent requirement IDs consumed and their declared allocation/disposition
canon lineage root digest
input Canon frontier artifact ID and digest (when Canon is read)
prompt/schema/model configuration digests
```

A parent contract provides **requirements**; its child provides **implementation**.
Requirement refinement is bidirectional: a child reference proves only child-to-parent
provenance, so the parent ledger additionally records allowed cardinality and lifecycle
for every active obligation:

```text
unallocated → allocated → implemented | preserved | deferred | waived
```

An active requirement has an explicit cardinality (`exactly_once`, `one_or_more`,
`preserve_until`, or a named deferred target).  Parent acceptance rejects an illegal
allocation; terminal-scope acceptance requires selected realization evidence or a
separately pinned waiver.  The runtime never infers fulfillment from audit prose.

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
2. An accepted Scene Contract either atomically creates one Canon event and next
   frontier, or explicitly preserves its input frontier without an event.

Volume and Chapter Contracts may read the current frontier but produce no Canon
patch.  The design phase processes volumes, chapters, and scene contracts in reader
order.  Every `SceneSlotBinding` records one immutable `canon_source_id`, exact input
frontier artifact/digest, exact output frontier artifact/digest, and selected Scene
Contract artifact/digest.  The next SceneSlot must consume the immediately preceding
slot's output frontier by **digest equality**, not merely ancestry.  A revision keeps
the same source ID and rebuilds the affected suffix as a new branch; duplicate events
for one source must never coexist in an active frontier.

Canon effect is a disjoint typed union:

```text
canon_effect: "mutates"
  non-empty typed CanonPatch + one Canon event + replayed new output frontier

canon_effect: "none"
  no CanonPatch + no Canon event + output frontier exactly equals input frontier
```

Mixed forms, empty/no-op mutation patches, or silent mutation cleanup are structural
failures.  A no-effect scene is not repaired into an empty event merely to make every
scene look alike.

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

| Policy | Semantic observations after fixed candidate budget | Contract status | Canon frontier |
|---|---|---|---|
| `conservative` | Stop at the named owner scope for an explicit decision. | `needs_decision` | Does not advance |
| `best_effort` | A selection-synthesis LLM recommends from every candidate and all raw audit/synthesis artifacts under the pinned policy. | `selected_with_semantic_observations` | Advances only through the selected contract's explicit transaction |

Both policies reject structural failures.  Neither labels unresolved semantic observations
as `passed`, and neither feeds an LLM's observation into later prompts as a new story
fact or mandatory correction.  An audit never advances Canon.  Under `best_effort`, the
**selection transaction** makes the selected contract the design authority; its declared
Canon effect advances only because that contract was selected, never because an audit was
considered semantically true.

### Parent ledger before generation; accepted ledger after selection

Before candidate generation, every contract receives an immutable
`ParentRequirementLedger` compiled only from accepted parent contracts, human acceptance
inputs, and deterministic topology rules.  It is a finite, typed choice list—not free-text
issue history and not a candidate's self-authored beat list:

```jsonc
{
  "requirement_id": "req_vol01_investigation",
  "owner_scope": "volume_contract",
  "class": "hard",
  "statement": "By the end of vol_01, the siblings voluntarily enter the theatre inquiry.",
  "verification_mode": "child_implementation",
  "allowed_next_owner": "chapter_contract"
}
```

A candidate provides a `CandidateCommitmentIndex` that maps these pre-existing IDs to
candidate beat IDs, preservation declarations, or permitted named deferments.  The index
is structurally validated for membership, cardinality, and allowed target slots; it cannot
introduce a new hard requirement or redefine a parent requirement.

After selection, the selected contract's concrete beat IDs become its
`AcceptedRequirementLedger`.  Only this post-selection ledger is used to assess a draft's
prose evidence.  A reviewer may report a risk against an existing parent or accepted
requirement ID and supply grounded evidence.  It may not turn a newly invented taste,
detail, or alternative plot into a hard requirement.  The report is an observation, not
proof that the requirement is violated.

A newly discovered concern is still preserved; it is classified as one of:

| Classification | Meaning | Effect |
|---|---|---|
| `observed_contract_risk` | LLM evidence suggests an existing requirement may be missing or contradicted. | Preserve it in the raw audit batch; ReviewSynthesis and policy decide the next LLM action. |
| `structural_failure` | Schema, typed reference, lineage, or deterministic simulation fails. | Candidate invalid. |
| `scope_escalation` | The problem may be real but its predeclared owner is a parent/sibling contract, not the current artifact. | Do not revise locally; return to named owner. |
| `editorial_note` | A grounded reader-facing improvement outside the ledger. | Immutable evidence only; never blocks Canon or selection. |

This does **not** suppress correct issues.  It prevents an unbounded stream of
subjective after-the-fact criteria from masquerading as a contract failure.  Every
reported issue remains in the raw audit evidence; only explicit contractual
obligations may be selected by an audit through the relevant ledger.

### CandidatePolicy is pinned before any LLM call

Every candidate batch starts with one immutable `CandidatePolicy` artifact.  It fixes
`max_candidates`, `max_revision_candidates`, `max_fresh_candidates`, exactly three
**ContractAudit** profiles, any separately declared fixed `DraftAudit` profile, mechanical
retry ceilings, provider/model configuration digests, and per-candidate / per-audit /
per-synthesis / total-batch byte and token budgets.

The runtime never truncates, drops, or runtime-summarizes a raw audit to fit a later
prompt.  It bounds output at source.  If the complete required batch cannot fit its
pinned budget, the batch has a durable `budget_exhausted` outcome; it is not a
zero-risk audit.  Audit transport, parse, or schema failure likewise becomes an
immutable `AuditFailureArtifact` referencing the candidate and request evidence.
`conservative` resolves that state through `needs_decision`; `best_effort` may select
only when its pinned policy explicitly permits the named failure outcome.

### Fixed three-audit assessment, not three revision cycles

The requested three reviews are three independent, same-candidate assessments.  No
review sees a candidate modified in response to a previous review.

```text
candidate C0
  ├─ ContractAudit 1: parent requirement coverage and scope
  ├─ ContractAudit 2: internal causal / disclosure consistency
  └─ ContractAudit 3: Canon feasibility and writer-view renderability
          ↓
  immutable assessment matrix for C0
```

Each ContractAudit receives the same candidate digest, the same `ParentRequirementLedger`,
and its explicit review scope.  Draft compliance is a separate `DraftAudit` performed only
after a selected Scene Contract has frozen its `AcceptedRequirementLedger`.  An audit returns requirement
IDs, status, and evidence locators—not free-form replacement prose, `before`/`after` text,
or a mandatory repair instruction.  An audit is an observation channel, not an author with
authority to rewrite the candidate.  Deterministic validation remains a separate,
pre-review gate:

- schema and parent-reference validation;
- parent requirement coverage / explicit deferment validation;
- Canon input-frontier lineage validation;
- for scenes: complete typed-ref resolution, stable-ID minting, dependency-DAG
  patch simulation, post-state assertion, and frontier replay.

The runtime never silently removes no-op operations or repairs an authoring
candidate.  A no-effect scene declares `canon_effect: "none"`; a malformed patch
is a structural failure.

### ReviewSynthesis receives every audit artifact verbatim

Independent audits can disagree, misread the candidate, or imply incompatible
improvements.  This is expected.  A candidate payload and every audit artifact are
LLM-produced evidence; the runtime has no semantic oracle that can decide which is
correct.

The runtime therefore does **not** detect, classify, vote on, or merge semantic
conflicts between audit outputs.  Comparing matching requirement IDs or enum values
cannot establish whether their free-text evidence, interpretations, or proposed
changes actually conflict.  It preserves the complete raw audit artifacts in a
stable order and passes all of them, unchanged, to a dedicated `ReviewSynthesis` LLM:

```text
candidate C0 + ParentRequirementLedger + raw audit 1 + raw audit 2 + raw audit 3
                                            ↓
                                 ReviewSynthesis (LLM artifact)
                                            ↓
C0 + ParentRequirementLedger + all raw audits + synthesis → revision LLM → C1
```

`ReviewSynthesis` may organize the full set of observations, explain tensions it
perceives, identify which requirements appear implicated, and prepare a coherent
revision context.  Its schema contains the candidate digest, ordered source-audit
artifact IDs/digests, existing requirement IDs, evidence locators, advisory text, and
unresolved-tension records.  It may not make an audit artifact disappear, relabel an
audit as false, invent a story fact or Canon change, or turn its interpretation into a
deterministic result.  The source candidate and every raw audit remain first-class
inputs to the revision LLM and immutable evidence in the run record.

The revision boundary is explicit: selected parent contracts, the relevant ledger, and
the allowed Canon projection are authority; candidate data, raw audits, and synthesis
are serialized as untrusted evidence data.  Citation existence and digest binding may
be validated structurally, but the runtime never decides whether evidence is
semantically correct, conflicting, or complete.

The only other machine interpretation at this boundary is structural: validate the
audit artifact schema and provenance, preserve all artifacts, and inject the complete
ordered batch.  There is no semantic disagreement detector, majority vote, confidence
gate, free-text merge, fuzzy matching, or mechanical prose replacement.

### Candidate set and uncertainty-aware selection

Candidates are immutable branches.  A revision never overwrites `C0`, and neither a
synthesis nor a later audit establishes semantic truth.

```text
C0 + raw audits + ReviewSynthesis S0 → revision → C1
C1 + raw audits + ReviewSynthesis S1 → revision → C2
fresh generation                      → C3
```

Each revision receives the source candidate, the relevant parent or accepted ledger,
**all** raw audit artifacts for that candidate, and the associated `ReviewSynthesis`.
It is never given a mechanically filtered issue list or a runtime-generated conflict
classification.  Every resulting candidate is re-assessed against the complete relevant
ledger with a fresh complete audit batch and synthesis artifact.

The selection record stores every candidate, its complete raw audit batch, each
synthesis artifact, and the policy/rationale used for the operational outcome.  No
raw issue is erased because a synthesis did not mention it, and no candidate is
considered semantically proven correct because a synthesis preferred it.

At a bounded candidate budget, `conservative` returns `needs_decision` when semantic
observations remain.  It persists a resumable `DecisionRecord` containing candidate IDs,
complete evidence IDs, owner scope, pinned policy, permitted resolutions, decision
actor/reason, and the exact resulting parent or waiver artifact; resume refuses to cross
an unresolved record.  Under `best_effort`, a final **selection-synthesis LLM** receives
every structurally eligible candidate, all raw audits, all ReviewSynthesis artifacts, and
the policy pinned before the run.  It returns a recommendation and rationale.  The runtime
records that policy-directed recommendation as `selected_with_semantic_observations`; it
does not claim the selected candidate or the selection-synthesis LLM is semantically
correct.

There is no open-ended local repair loop.  The configured candidate budget bounds cost,
not truth.  When it is exhausted:

- structural failure means no candidate is selectable;
- an owner-scope conflict is preserved for the authoritative owner to consider;
- an audit/budget failure follows only the outcome explicitly permitted by the pinned policy;
- unresolved semantic observations follow the declared `conservative` or `best_effort` policy.

Under `best_effort`, downstream prompts receive the selected contract, not audit claims as
story facts or mechanical revision instructions.  The selected contract's Canon effect is
published only in its atomic selection transaction; complete audits and syntheses remain
in snapshots, run status, and export manifest for audit.

### Escalate to the owner that can actually resolve the problem

A review selects a requirement ID; its `owner_scope` is predeclared in the relevant
`ParentRequirementLedger` or `AcceptedRequirementLedger`.  The runtime therefore does not
trust a reviewer's free-text claim about which layer should change.  A real scope escalation
becomes an explicit design decision, not another local rewrite.

| Failure source | Correct owner | Forbidden response |
|---|---|---|
| Missing scene beat or prose evidence | Scene Contract / draft renderer | Alter Series or Canon silently |
| Incompatible SceneSlot obligations | Chapter Contract | Keep rewriting the scene indefinitely |
| Impossible chapter outcome or admission | Volume Contract | Invent an unapproved Canon fact |
| Series invariant, ending, or world-rule conflict | Series Contract | Patch it inside a scene |
| Schema, reference, digest, or frontier defect | Candidate generation / deterministic layer | Human narrative waiver |

Changing an accepted parent creates a new parent artifact and invalidates descendants
by digest.  The affected scope is then designed again from that new authority.  This is
deliberate backtracking, not a hidden retry loop.  When `best_effort` permits risk carrying,
audit evidence propagates only as audit metadata—not as a new story fact or next-prompt
instruction—while the separately selected contract may still advance its declared Canon
effect through its atomic selection transaction.

### Structural gates are fail-closed; semantic review is uncertainty-aware

| Finding | Selection result |
|---|---|
| Parse/schema/typed-reference failure | candidate invalid |
| Provenance or frontier failure | candidate invalid |
| Deterministic parent-requirement membership failure | candidate invalid or predeclared scope escalation |
| LLM-observed ledger risk | full raw-audit batch → `ReviewSynthesis` → revision, `conservative` decision, or `best_effort` selection-synthesis |
| Editorial preference | immutable optional evidence; not an authority gate |

A human waiver may cover a named narrative requirement only when release policy
permits it and the waiver becomes a new explicit acceptance input.  Structural,
lineage, digest, and typed-reference failures are never waivable.  A waiver is not
an implicit “continue after review cap” switch, and a `best_effort` selection is
never relabelled `passed`.

A selected scene is an atomic snapshot boundary.  The runtime stages immutable artifacts
first, then creates exactly one descendant selection snapshot:

```text
scene.contract
scene.contract.parent_requirement_ledger
scene.contract.accepted_requirement_ledger
scene.contract.raw_audits | audit_failures
scene.contract.review_synthesis
scene.contract.acceptance  ← selection policy / selection-synthesis rationale pinned
canon.patch | canon.event  ← only for canon_effect: "mutates"
canon.frontier             ← exact output of this scene contract or same input frontier
scene.slot_binding
workflow.cursor
```

A crash before snapshot publication may leave unselected staged artifacts, but there is no
selected snapshot where Canon advanced without its causal Scene Contract, slot binding, and
acceptance record.  A Volume Contract and Chapter Contract are also snapshot-pinned upon
acceptance so resume always uses explicit inputs.  Resume is idempotent: it reuses a
matching selected binding, rejects mismatched slot/source/frontier state, and never
recreates an already-selected Canon event.

## Design bundle, render, summary, export

After all scene contracts for a target volume are accepted, the runtime creates a
`DesignBundle` index containing ordered `SceneSlotBinding`s, selected contract IDs/digests,
parent contracts, required placement topology, and the volume-end Canon frontier checkpoint.
It does not duplicate full scene payloads.  The bundle validator rejects missing, duplicate,
out-of-order, foreign-volume, or non-contiguous frontier bindings before render begins.

Render begins only from an accepted frozen bundle.  A deterministic compiler creates each
writer view from the selected Scene Contract plus its exact **pre-scene** frontier:
`start_context` cannot contain the scene's new event effects.  `end_constraints` are derived
separately from the selected contract plus its simulated post-patch state, so the writer knows
what prose must establish without receiving raw Canon, patch operations, or internal IDs.
Every draft is assessed against the contract's `AcceptedRequirementLedger` and evidence claims.
A deterministic structural violation cannot be selected.  A model-observed omission,
contradiction, disclosure concern, or unplanned-durable-fact concern is preserved in the
draft's complete raw audit batch and passed unchanged to `ReviewSynthesis`; it follows the
selected `conservative` or `best_effort` policy and is never silently converted into a
passing result.

A prose recap may be created for people, search, and audit.  It is marked derived:

- never input to later design;
- never input to the next writer;
- never a Canon source;
- never a substitute for required-beat evidence.

Export is a pure derivation from an explicit DesignBundle/snapshot.  It validates
ordered topology, selected draft and assessment evidence, artifact/manifest digests,
the bundle's pinned volume-end frontier replay, the pinned semantic-observation /
waiver policy, and the complete raw audits, ReviewSynthesis artifacts, and
selection-synthesis rationale.  A `selected_with_semantic_observations` export must
expose those artifacts in its manifest; strict export may reject it when the selected
release policy requires no open semantic observations.  Export never reads a current
global frontier, creates a selection snapshot, or mutates Canon.

## Implementation migration order

1. Add the four contract schemas and complete Japanese field descriptions:
   `series_contract`, `volume_contract`, `chapter_contract`, `scene_contract`.
2. Add `ParentRequirementLedger`, `CandidateCommitmentIndex`,
   `AcceptedRequirementLedger`, bidirectional allocation/lifecycle, `CandidatePolicy`,
   `DecisionRecord`, `SceneSlotBinding`, `WorkflowCursor`, and `DesignBundle` schemas
   with fake-runner tests before orchestration changes.
3. Extend repository primitives with atomic multi-slot selection publication, exact
   SceneSlot frontier equality, idempotent cursor resume, and dependency-closure
   invalidation.  Retire the public path that first selects a frontier and later
   selects its causal scene artifact.
4. Implement typed Canon references with `(source_id, kind, creation_key)` identity,
   disjoint `canon_effect` validation, whole-patch stable-ID resolution, DAG simulation,
   and replay.  `canon_effect: "none"` must preserve the input frontier without an event.
5. Replace the fixed `generate → review → revise` task assumption with an explicit PNCA
   task registry: contract candidate, ContractAudit profiles, ReviewSynthesis, revision,
   selection-synthesis, writer, and DraftAudit.  Every task declares prompt, schema,
   exact input artifact types, output artifact type, policy/ledger/frontier digests, and
   retry/failure behavior.
6. Replace current design orchestration with sequential Series → Volume → Chapter →
   Scene candidate selection.  Volume/Chapter remain narrow contracts, not duplicate
   free-form scene authors.  Implement conservative and best-effort selection plus
   resumable `needs_decision`; delete generic cap-driven `review → revise` advancement.
7. Compile pre-frontier `writer_view` and post-patch `end_constraints`, remove summary
   as a forward input, then build strict bundle-pinned export from slot bindings.
8. Delete old DSL aliases, duplicate payload assembly, obsolete task resources, legacy
   acceptance tests, and compatibility paths.  No compatibility shim remains.

## Minimum acceptance tests

- Contract prompts and schemas expose only their permitted resolution and input artifacts;
  CI does not claim to decide whether free prose is “scene-level enough.”
- Every active parent requirement has a legal allocation/disposition; `exactly_once`
  requirements cannot vanish or be fulfilled twice, and terminal scopes require selected
  realization evidence or a pinned waiver.
- A Scene Contract cannot be accepted without its selected parent SceneSlot, immutable
  source ID, and exact pre-scene frontier digest.  Revisions rebuild the affected suffix
  and cannot leave duplicate active events for one source.
- `canon_effect: "none"` has no patch/event and preserves the exact input frontier;
  `canon_effect: "mutates"` rejects empty/no-op patches and replay failure.
- A simulated crash between staging and snapshot publication leaves no selected
  frontier-only state.  The selected snapshot contains the scene contract, ledgers,
  complete audit/failure evidence, acceptance record, slot binding, cursor, and output frontier.
- Candidate / audit / synthesis batch overflow never truncates or drops raw evidence;
  audit failure is explicit and follows only the pinned policy.
- Three ContractAudits assess the same candidate digest and cannot observe one another's
  revision.  DraftAudit is a separate task over a selected contract and its
  `AcceptedRequirementLedger`.
- ReviewSynthesis receives candidate, relevant ledger, and every raw audit artifact
  verbatim.  Its citations bind to existing audit artifacts; the runtime does not detect,
  classify, vote on, merge, or delete semantic conflicts.
- A revision receives the complete raw audit batch and synthesis, not a mechanically
  filtered issue list.  A later selection-synthesis receives every eligible candidate and
  all of its raw audits/syntheses.
- Structural failure is never selectable.  `conservative` cannot resume across an
  unresolved `DecisionRecord`; `best_effort` records `selected_with_semantic_observations`
  and never injects audit claims into downstream prompts.
- Writer input contains only one compiled pre-frontier writer view plus separate end
  constraints; altering a summary cannot alter any later writer request.
- Export rejects missing/duplicated/out-of-order scene slots, unreviewed drafts, digest
  mismatch, broken frontier chain, foreign/future-volume Canon events, or an open-risk
  lineage when strict release policy forbids it.
- A real-model run completes Series → per-volume/Chapter/Scene design → bundle → render
  → strict export, with raw request/response/parsed/validation evidence inspected for
  every PNCA task type.
