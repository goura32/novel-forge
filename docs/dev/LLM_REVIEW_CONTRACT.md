# LLM Review Contract

## Goal

NovelForge must not turn structurally ambiguous LLM output into accepted Canon state. The runtime is designed as a fail-closed production pipeline: an LLM candidate becomes selected output only after generation, review, revision, and deterministic validation all pass.

## Universal loop

Every LLM-authored artifact uses the same gate:

```text
generate → LLM review + deterministic contract review → revise → … → accept
```

| Stage | LLM artifact | Deterministic checks | On issue |
|---|---|---|---|
| Plan | `plan_concept` | required seed fields, strict slug | revise |
| Volume/chapter | design schemas | required structural children | revise |
| Scene | ID-only scene design | Canon ID membership, intent DSL compiler, strict CanonPatch schema, semantic preflight | revise |
| Draft | prose draft | schema plus review grounding | revise |
| Summary | writer handoff | schema plus draft-grounded review | revise |

The configured review count is an attempt budget, **not** permission to accept unresolved defects. Reaching the budget raises `RuntimeContractError`; no selection snapshot advances.

## Canon identity boundary

Scene design receives a compact `canon_context` whose entities contain both a narrative label and an opaque Canon ID. The model must return the provided IDs exactly:

- character fields: `pov_character_id`, `character_ids`
- location field: `location_id`
- update targets: `canon_updates[].target_id` and `holder_id`

The runtime does not resolve display names, aliases, substrings, invented IDs, or missing values. A mismatch is a reviewable contract violation and triggers revision.

## Intent DSL instead of LLM-authored CanonPatch

A complete CanonPatch has entity-specific operation structures and typed references. Asking an LLM to construct it directly produced repeated category errors (`artifacts.state_updates`, character-shaped artifact creates, missing reference kinds). The LLM-facing scene schema now exposes only these operations:

- `set_character_state`
- `set_location_state`
- `set_artifact_condition`
- `transfer_artifact`

`RuntimeWorkflow._compile_scene_updates` is the only compiler from that DSL to the strict CanonPatch model. It accepts only existing IDs and never injects defaults or rewrites approximate fields. The existing Canon schema and semantic preflight remain the final authority before a Canon Event is published.

## Explicitly prohibited recovery paths

The runtime must not use any of the following as a way to advance a candidate:

- partial/name/alias location or character resolution
- falling back to a first Canon entity
- inferred `EntityRef.kind`
- `extra="ignore"` on CanonPatch
- schema-error warnings that still permit application
- normalizing near-miss CanonPatch field names
- assigning a default stable ID to an LLM-created entity
- selecting `review_limit_reached` content

If a requested narrative requires a Canon entity that does not yet exist, it must be introduced through an explicit, separately designed Canon expansion workflow; a scene design must not silently invent it.

## Evidence

Each generate/review/revise call has its own immutable attempt. A selected artifact therefore has an auditable trail from candidate through final empty-issue review. Raw LLM input/output capture remains bound to the attempt under the repository retention policy.
