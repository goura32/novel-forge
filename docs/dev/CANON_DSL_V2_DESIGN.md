# NovelForge v2: design-authoritative pipeline

## Status and scope

This is the authoritative specification for the destructive v2 rewrite.  It
supersedes the current `plan → volume → chapter → scene → write → summary`
implementation wherever they disagree.  Compatibility with the current task
names, schemas, artifacts, or runs is explicitly out of scope.

The governing premise is simple:

> **Only design creates story information.  Writing renders approved design as
> prose.  Prose and summaries never amend Canon, determine later facts, or
> become an authoring input.**

There is no planned-versus-realized Canon split and no post-draft Canon
reconciliation.  A reviewed design decision is Canon truth before prose exists.

## Why the current pipeline must not be incrementally repaired

The existing runtime has a sound immutable-artifact foundation, but its authoring
boundaries are duplicated and its writer boundary is incomplete.

- `design.volume`, `design.chapter`, and `design.scene` all author overlapping
  answers to “what happens next”.  A chapter scene seed and its expanded scene
  can disagree without an explicit ownership rule.
- `write_volume()` passes only `writer_context` and `previous_summary`; it omits
  the reviewed `goal`, `conflict`, `key_events`, `turning_point`, `outcome`, and
  `ending_hook` that the writer must render.
- The current writer context may be built from a post-patch Canon projection,
  even though the writer prompt calls it an opening fact.
- A summary is fed to the next writer.  Its omissions or inventions can thereby
  become de facto story facts despite not being a Canon event.
- Generic review caps can select an issue-bearing draft and label it `passed`.

These are structural faults, not prompt wording problems.  V2 replaces the
pipeline boundaries rather than adding adapters around them.

## V2 artifact vocabulary

| Term | Meaning | Can be selected? |
|---|---|---:|
| **Attempt** | One generate, review, revise, or deterministic-validation execution with immutable raw evidence. | No |
| **Candidate** | A schema-valid payload produced by an attempt. | No |
| **Review evidence** | Immutable assessment tied to the exact candidate digest. It never mutates a candidate. | No |
| **Acceptance record** | Immutable proof that named candidate, review, validators, and policy satisfy an acceptance decision. | Yes, as evidence only |
| **Selection snapshot** | The complete immutable input set available to a later phase or resume operation. | Yes |
| **Input frontier** | The exact Canon seed lineage and pre-scene frontier read by a Canon-consuming artifact. | N/A |

An `artifact.ready` marker only proves durable storage and digest integrity.  It
never means that an artifact is selected, reviewed, or publication-ready.

## The complete v2 pipeline

```text
[0] Brief intake                 human constraints; no story facts generated
          ↓
[1] SeriesDesign                 sole macro-authoring boundary
          ↓                       SeriesBlueprint + CanonSeed
[2] Sequential SceneContract     sole scene-authoring boundary
    design                        Contract + CanonEvent + next frontier
          ↓
[3] DesignBundle freeze          ordered contracts + terminal checkpoints
          ↓
[4] Render / Write               contract → prose only
          ↓
[5] Optional prose analysis      non-authoritative derived artifacts only
          ↓
[6] Export                       pure rendering of a pinned bundle
```

Only stages **[1]** and **[2]** create durable story information.

### 0. Brief intake

The Brief is a human-owned request, not a Canon or a model-authored artifact.  It
contains genre, audience, desired premise, required and forbidden elements,
length/topology constraints, and operating policy.  The runtime validates only
its structure and completeness; it does not invent omitted authorial facts.

### 1. SeriesDesign: the only macro-authoring task

`SeriesDesign` replaces the current independently generated plan, volume design,
and chapter design tasks.  It is generated/reviewed/revised as one authoring
artifact and produces:

- `SeriesBlueprint`: premise, thematic and causal macro arc, stable volume and
  chapter placements, expected scene topology, and unresolved-series policy;
- stable `intent_id` values for each volume/chapter narrative commitment;
- approved supporting-character admission intents;
- `CanonSeed`: series constraints, world rules, Core cast, initial locations,
  initial relationships, chronology, glossary, and opening state.

A volume or chapter is therefore a **placement and aggregation view**, not a
second LLM authority that reauthors scene events.  Scene contracts must cite a
parent `intent_id`; they concretize it but never silently replace it.

A SeriesDesign acceptance transaction creates exactly one root selection snapshot:

```text
series.design
series.design.final_review
series.design.acceptance
canon.seed
canon.frontier.root  (already bound to canon.seed digest)
```

The root frontier is created once.  V2 does not commit an unbound root and then
create a duplicate lineage-bound root.

### 2. SceneContract: the only scene-authoring task

Scene contracts are designed sequentially in reader order.  Each one consumes:

- the accepted SeriesBlueprint and its parent `intent_id`;
- the exact **pre-scene** Canon frontier;
- the preceding accepted SceneContract's deterministic transition packet;
- no draft, summary, live mutable state, or timestamp-selected artifact.

It produces one complete authorial decision:

```jsonc
{
  "contract_version": 2,
  "scene_id": "scn_...",
  "placement": {"volume_id": "vol_01", "chapter_id": "ch_01", "ordinal": 1},
  "parent_intent_id": "intent_...",
  "input_frontier": {"seed_digest": "sha256:...", "frontier_digest": "sha256:..."},

  "author_contract": {
    "scope": {"pov": {}, "setting": {}, "cast": []},
    "narrative": {
      "title": "...",
      "goal": "...",
      "conflict": "...",
      "required_beats": [{"id": "beat_01", "order": 1, "requirement": "..."}],
      "turning_point": {"id": "turn_01", "requirement": "..."},
      "outcome": {"id": "out_01", "requirement": "..."},
      "ending_hook": {"id": "hook_01", "requirement": "..."}
    },
    "canon_patch": {}
  },

  "writer_view": {
    "start_context": {},
    "narrative_contract": {},
    "end_constraints": {},
    "presentation_constraints": {}
  }
}
```

`writer_view` is compiled deterministically and is the only payload that may
cross to writer/reviewer prompts:

- `start_context` is projected **only from the pre-scene Canon**;
- `narrative_contract` is a safe rendering of the reviewed title, goal,
  conflict, requirement IDs, beats, turn, outcome, and hook;
- `end_constraints` are compiled from the simulated post-patch Canon and the
  approved outcome.  They are targets to establish, never opening facts;
- `presentation_constraints` contain writer-safe POV, disclosure, style, cast,
  setting, and object constraints.

Writer prompts receive neither raw Canon IDs, patches, events, digest values,
secret propositions, author-only rationale, nor a prior prose summary.

#### CanonPatch v2 grammar

Every reference in scope, create payloads, and updates has one typed object form.

```jsonc
// Existing entity
{"kind": "character", "id": "char_001"}

// Entity created in this same source patch
{"kind": "character", "creation_key": "attendant"}
```

Raw IDs in typed fields, `@created:<key>`, and bare `{"creation_key":"..."}`
are not public v2 syntax.  A created entity identity is
`(source_id, kind, creation_key)`, so an artifact and a foreshadowing may share a
human-readable creation key while duplicate `(kind, creation_key)` is rejected.

The runtime performs whole-patch work before any LLM review:

1. schema/model validation;
2. collect creates and mint all stable IDs;
3. resolve every typed reference, kind expectation, existence, and cycle;
4. dependency-DAG simulation of creates and mutations;
5. compare deterministic end assertions against the simulated Canon;
6. build writer-safe pre/post views.

The runtime never silently removes a no-op or “repairs” a candidate patch.  A
scene with no durable Canon effect declares `canon_effect: "none"`; a malformed
or pointless patch is returned to revision as a design failure.

#### Scene acceptance is atomic

A scene is selected only when all of these agree on the exact candidate digest:

- scene narrative review;
- typed patch schema and deterministic preflight;
- CanonPatch semantic review where needed;
- simulated event and replay validation;
- compiled writer view and end assertions.

One acceptance transaction publishes both the SceneContract and its output Canon
frontier in **one** selection snapshot.  There is no intermediate snapshot in
which Canon advanced but its causal SceneContract is absent.

```text
scene.contract
scene.contract.final_review
scene.contract.patch_review
scene.contract.acceptance
canon.frontier  ← output frontier from this exact contract
```

After all contracts are accepted, `DesignBundle` is frozen.  It is an index, not
a giant duplicate payload: it records ordered contract IDs, parent intents,
expected scene topology, per-volume end-frontier checkpoints, and the terminal
series frontier.  Writing consumes this bundle only after design is complete.

### 3. Render / Write: a non-authoritative renderer

The writer receives exactly one selected scene's `writer_view`, plus an optional
**deterministic transition packet** compiled from the preceding accepted contract
and Canon frontier.  It does not read prior draft prose, summaries, Canon, or a
live snapshot.

Writer freedom is limited to language, dialogue, sensory detail, pacing, and
other non-durable presentation choices.  It must not establish an unplanned
character, named item, ability, rule, relationship, knowledge, lasting state,
or causal result.

A draft compliance reviewer is a hard gate.  It returns a typed status for every
requirement ID and a verifiable text span:

```text
requirement_id → satisfied | missing | contradicted
text_span      → must occur in the exact draft payload
```

It also reports start-context violations, end-constraint failures, unplanned
durable facts, and disclosure violations.  Editorial prose feedback is a
separate optional lane; it cannot alter Canon or acceptance authority.

### 4. Summary and prose analysis

A summary is not on the forward authoring path.

- It cannot be an input to the next scene design or writer task.
- It cannot amend Canon, generate a patch, or replace a missing requirement.
- It may exist as an optional, draft-grounded recap, search index, or human
  audit artifact.
- A summary that is produced must be explicitly marked derived and must not
  appear in `DesignBundle` or writer input lineage.

The former “continuity handoff” responsibility moves to the deterministic
transition packet derived from approved contracts, not from prose.  This prevents
summary hallucinations or draft deviations from creating later story facts.

### 5. Review, retry, and human decisions

V2 distinguishes four results; a generic review cap never turns one into another.

| Result | Selection effect |
|---|---|
| Schema/structural failure | candidate invalid; bounded regenerate/revise attempt only |
| Deterministic contract failure | candidate invalid; never selectable |
| LLM compliance blocker | candidate unselected; revise/regenerate or stop |
| Editorial suggestion | may be recorded; does not affect Canon selection |

At a review limit, the runtime selects the last fully compliant candidate if one
exists.  Otherwise it fails the unit as `needs_decision`; it does not label an
issue-bearing artifact `passed`.  A human waiver is an explicit immutable decision
artifact referencing the candidate and every waived issue.  Structural, typed-ref,
frontier, and digest failures are never waivable.  Strict export rejects unresolved
or waived blocker issues unless an explicit release policy permits that waiver.

Every selected SeriesDesign, SceneContract, draft, and optional summary retains its
final review evidence and an acceptance record.  Review evidence is not discarded
by a generic `generate → review → revise` helper.

### 6. Immutable provenance and snapshots

Every Canon-consuming artifact records:

```text
canon_lineage_root_digest
input_canon_frontier_artifact_id
input_canon_frontier_digest
input artifact IDs and payload digests
prompt/schema/model configuration digests
```

Scene contracts and events additionally record their output frontier ID/digest.
A candidate cannot be accepted if its recorded pre-frontier is not an ancestor of
the selected frontier.  The bundle preserves a volume-end frontier checkpoint, so
exporting an earlier volume never includes later-volume Canon events.

Snapshots are created only at these receive boundaries:

1. accepted SeriesDesign + root Canon;
2. each accepted SceneContract + output frontier, atomically;
3. frozen DesignBundle;
4. each accepted draft (and optional derived analyses) for resume.

Candidate persistence remains append-only, but candidates never become the input
of a later stage merely because they are ready.

### 7. Export: a strict pure derivation

Export accepts an explicit DesignBundle / selection snapshot (CLI supports a
specific snapshot selector; current snapshot is a convenience default only).  It
creates no selection snapshot and mutates no Canon or design artifact.

Before rendering, strict export validates:

1. selected snapshot, ready markers, payload digests, manifest digests, and
   canonical slot map;
2. exactly one accepted contract and accepted draft for every bundle scene, with
   unique ordered placement and no gaps;
3. draft compliance evidence and acceptance status for every scene;
4. root seed plus the bundle's pinned volume-end/terminal frontier replay;
5. every contract's pre/output frontier chain and every required input artifact;
6. any waiver/release-decision policy.

Its manifest pins the selection snapshot ID/digest, ordered slot map, all source
artifact IDs/digests, seed/frontier digests, final Canon projection digest,
renderer version, policy version, and final review/waiver IDs.  Repeating an
export for the same snapshot and renderer must yield the same ordered inputs.

## Destructive migration boundaries

The following current concepts are deleted rather than adapted:

- independent `design.volume` and `design.chapter` LLM authoring tasks;
- duplicate chapter scene seeds and final-volume scene payload copies;
- `writer_context` as the sole writer boundary;
- `previous_summary` / `_writer_handoff()` as writer or design input;
- `@created:` and bare `CreationRef` syntax;
- runtime patch normalizers that silently alter accepted authoring content;
- fail-open selection at review caps and unconditional `quality_status="passed"`;
- export against an unpinned current global Canon frontier.

## Implementation order and acceptance tests

1. Define `SeriesDesign`, `SceneContract`, `DesignBundle`, acceptance-record,
   compliance-review, and transition-packet schemas with complete Japanese field
   descriptions.
2. Implement typed v2 references, tuple identity, whole-patch resolution, and
   DAG simulation before author prompt migration.
3. Replace plan/volume/chapter/scene orchestration with SeriesDesign followed by
   sequential atomic SceneContract acceptance; retain all attempt evidence.
4. Compile writer views from pre/post Canon; replace writer/reviewer task inputs;
   delete summary forward handoff.
5. Make compliance selection fail closed; preserve editorial review separately.
6. Implement DesignBundle-pinned strict export and provenance checks.
7. Delete legacy prompts, schemas, task registry rows, runtime adapters, docs,
   and tests.  No compatibility shim is retained.

Minimum acceptance tests:

- one atomic snapshot contains a SceneContract and exactly its output frontier;
- no Canon-consuming artifact can commit without its input-frontier provenance;
- same-key create references work across kinds; duplicate `(kind, creation_key)`
  fails before review;
- writer input contains the contract writer view only, and a changed summary cannot
  change any later writer request;
- pre-scene facts cannot contain post-patch state; end constraints do;
- missing/contradicted requirement evidence or an unplanned durable fact prevents
  draft selection at every review cap;
- a bundle export rejects missing, unordered, unreviewed, wrong-frontier, or
  digest-mismatched input and never includes a future volume's Canon events;
- a clean real-model run reaches SeriesDesign → full DesignBundle → render →
  strict export, with raw request/response/parsed/validation evidence reviewed.
