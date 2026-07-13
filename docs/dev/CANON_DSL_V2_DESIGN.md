# Canon DSL v2 design

## Status

Approved design direction for the incompatible v2 migration.  Legacy DSL compatibility is not a goal.

## Core premise

**Design is the sole producer of new story information.**  A reviewed SceneDesign
is the authorial truth: it selects the scene's start conditions, required events,
end conditions, and Canon mutations.  Writing does not discover, amend, or commit
Canon information.  It renders that contract as prose and is rejected/revised if
it fails to do so.

Therefore v2 deliberately does **not** have a planned-vs-realized Canon frontier
or a post-draft Canon reconciliation step.

## Authority and lifecycle

| Stage | May create/change Canon? | Authoritative output |
|---|---:|---|
| Plan | yes | Canon seed: series constraints, world rules, Core cast, initial state |
| Volume / chapter design | no | stable DesignIntents: approved narrative commitments and admissions |
| Scene design + review | yes | SceneContract plus a fully validated CanonPatch and CanonEvent |
| Draft / revise / summary | no | prose and compliance evidence only |
| Export | no | immutable selected artifacts and Canon frontier |

A scene CanonEvent is committed only after scene design review passes.  The next
scene design reads that post-event Canon.  This is intentional: later design is
allowed to rely on already-approved earlier-scene outcomes.

## SceneContract

A reviewed scene must persist an explicit writer-facing contract.  The writer must
not infer dramatic requirements from a post-patch state projection.

```jsonc
{
  "start_context": { /* deterministic projection of Canon before this patch */ },
  "narrative_contract": {
    "title": "…",
    "goal": "POV character's concrete objective in this scene",
    "conflict": "the specific obstacle to that objective",
    "required_beats": ["observable event in narrative order"],
    "turning_point": "irreversible choice, discovery, or reversal",
    "outcome": "result that prose must establish by scene end",
    "ending_hook": "unresolved pressure requiring the next scene"
  },
  "end_constraints": { /* deterministic projection of relevant post-patch state */ }
}
```

`start_context` is factual at the opening of the scene.  `end_constraints` is a
required end state, **not** an opening fact.  Writer prompts must use this
terminology and provide all three sections.  The existing single `writer_context`
field is replaced by this contract.

The draft reviewer receives the same contract and checks:

1. every required beat, turning point, outcome, and ending hook is actually
   represented in prose;
2. prose starts from the permitted start context and reaches the end constraints;
3. prose introduces no durable entity, rule, relationship, ability, or factual
   change absent from the approved design;
4. POV and disclosure boundaries hold.

A summary is a prose-grounded continuity handoff and compliance evidence.  It
never mutates Canon or proposes a replacement Canon patch.

## One typed reference grammar

Every Canon reference, in SceneContract, CanonPatch create payloads, and CanonPatch
updates, uses one object grammar.

```jsonc
// Existing Canon entity
{"kind": "character", "id": "char_001"}

// Entity created in this same scene patch
{"kind": "character", "creation_key": "attendant"}
```

`@created:<key>`, raw stable-ID strings in typed fields, and bare
`{"creation_key":"…"}` are removed from the public v2 grammar.

The explicit `kind` is required for both variants.  It makes reference validation
local and permits one source to create an artifact and a foreshadowing with the
same human-readable concept key without ambiguous resolution.  Stable IDs are
minted by `(source_id, kind, creation_key)`.

## Patch application

Patch application is not section-order dependent.

1. Parse and validate the complete patch against v2 models/schema.
2. Collect every create payload and mint stable IDs for `(source, kind,
   creation_key)` tuples.
3. Resolve every typed reference and validate expected kinds, existence,
   self-reference rules, and cycles.
4. Apply creates and mutations in a dependency DAG order.
5. Persist one CanonEvent containing the resolved patch and minted IDs.

Duplicate `(kind, creation_key)` values in one source are rejected before review
selection.  Equal keys in different kinds are legal.  This replaces the current
source-global bare-key rule that stopped the real-model run when an artifact and a
foreshadowing both used `fh_black_mist_origin`.

## Character admission lifecycle

| Importance | Admission authority | Scene behavior |
|---|---|---|
| `core` | Plan seed only | reference and mutate existing Core only |
| `supporting` | approved chapter DesignIntent | scene fulfills an intent by creating the approved entity |
| `minor` | SceneContract | scene may create directly when continuity tracking is warranted |

A supporting admission references a stable `intent_id`; it is not a free-text
`parent_design_intent` object.  A one-scene role remains local prose/cast data and
is not a Canon character.  Promotion is an explicit DesignIntent-backed action,
not an accidental side effect of a scene create.

## Field descriptions are contracts

Every prompt-facing JSON field needs a Japanese description that tells the model:

- what concrete content to write;
- its temporal meaning (opening state, required event, or end state);
- whether it creates Canon information or only describes it;
- its reader/downstream consumer; and
- what adjacent field it must not duplicate.

P0 fields to document in `design_scene` are `title`, `goal`, `conflict`,
`key_events`, `hook`, `turning_point`, `emotional_arc`, `outcome`, `ending_hook`,
`sensory_focus`, `subtext`, and `foreshadowing`.  Schema descriptions, generate
prompts, review prompts, revise prompts, and deterministic validators must express
the same rules.

## Migration acceptance tests

1. Writer receives `start_context`, `narrative_contract`, and `end_constraints`;
   it receives no raw Canon IDs, event log, or author-only truth.
2. A draft that omits a required beat or outcome is rejected by draft review and
   revised; it cannot become the selected draft.
3. A draft adding an unplanned durable entity/rule/change is rejected; summary
   does not repair Canon.
4. Same-patch references work across all entity kinds and all create/update fields.
5. An artifact and foreshadowing may share a human-readable creation key; duplicate
   `(kind, creation_key)` cannot pass candidate preflight.
6. Core creation outside Plan and supporting creation without an approved intent
   are rejected by model, committed schema, preflight, and applier.
7. A clean real-model run reaches design, writing, summary, and export with the
   v2 schema; raw attempts are reviewed for generic prompt/schema failures.
