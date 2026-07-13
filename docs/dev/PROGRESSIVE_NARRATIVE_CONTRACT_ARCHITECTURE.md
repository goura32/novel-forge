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

## Acceptance, review, and snapshots

### Deterministic preflight comes first

Before narrative review, every candidate undergoes the checks appropriate to its
layer:

- schema and parent-reference validation;
- parent requirement coverage / deferment validation;
- Canon input-frontier lineage validation;
- for scenes: complete typed-ref resolution, stable-ID minting, dependency-DAG
  patch simulation, post-state assertion, and frontier replay.

The runtime never silently removes no-op operations or repairs an authoring
candidate.  A no-effect scene declares `canon_effect: "none"`; a malformed patch
returns as a specific validation failure for revision.

### Compliance is fail-closed; editorial feedback is separate

| Finding | Selection result |
|---|---|
| Parse/schema/typed-reference failure | candidate invalid |
| Parent-contract or frontier failure | candidate invalid |
| Scene/draft compliance blocker | revise, regenerate, or stop unselected |
| Editorial preference | optional evidence; not an authority gate |

At a review limit, a fully compliant prior candidate may be selected.  If none
exists, the unit is `needs_decision`; an issue-bearing candidate is never labelled
`passed`.  An explicit human waiver may cover a narrative blocker only when the
release policy permits it; structural, lineage, digest, and typed-reference
failures are never waivable.

A selected scene is an atomic snapshot boundary:

```text
scene.contract
scene.contract.final_review
scene.contract.patch_review
scene.contract.acceptance
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

Render begins only from an accepted frozen bundle.  Every draft is checked against
its contract requirement IDs and evidence spans.  A draft that omits a required
beat, contradicts the start/end state, leaks a forbidden fact, or creates an
unplanned durable fact cannot be selected.

A prose recap may be created for people, search, and audit.  It is marked derived:

- never input to later design;
- never input to the next writer;
- never a Canon source;
- never a substitute for required-beat evidence.

Export is a pure derivation from an explicit DesignBundle/snapshot.  It validates
ordered topology, selected draft and compliance evidence, artifact/manifest
digests, the bundle's pinned volume-end frontier replay, and waiver policy.  It
never reads a current global frontier, creates a selection snapshot, or mutates
Canon.

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
6. Add fail-closed contract compliance reviews and strict bundle-pinned export.
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
- Draft selection fails at every review limit when requirement evidence is missing
  or contradicted.
- A selected Scene Contract and its output frontier always appear in the same
  selection snapshot.
- Export rejects missing/duplicated scene slots, unreviewed drafts, digest mismatch,
  broken frontier chain, or future-volume Canon events.
- A real-model run completes Series → per-volume/Chapter/Scene design → bundle →
  render → strict export, with raw request/response/parsed/validation evidence
  inspected for each contract layer.
