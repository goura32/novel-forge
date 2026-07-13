# PNCA Implementation Plan

> Governing contract: `PROGRESSIVE_NARRATIVE_CONTRACT_ARCHITECTURE.md`.
>
> This is a destructive migration.  The finished public path has no legacy
> workflow fallback, no compatibility shim, and no mutable state authority.

## Baseline

- Starting commit: `a658e99`.
- Full test baseline: `334 passed` with the existing review-cap warning.
- Static baseline: Ruff and mypy are clean.
- The old `RuntimeWorkflow.accept_scene_design()` is not PNCA-compatible: it
  publishes a Canon frontier before its selected scene artifact and self-heals
  no-op patches.  It must never remain reachable from the finished PNCA CLI.

## Non-negotiable implementation rules

1. Write a focused failing test before every production behavior change.
2. Canon authority is only `CanonSeed` plus accepted mutating Scene Contracts;
   `canon_effect: "none"` preserves the exact input frontier without an event.
3. A selected state is visible only through `AcceptanceCommit`; prepared
   artifacts are never selected.
4. Structural validation is deterministic.  Audit/review outputs are immutable
   observations, never semantic truth or automatic Canon authority.
5. Every downstream read is pinned to one immutable selection snapshot and its
   DesignBundle; no production path selects a latest artifact or live Canon.
6. Raw audit artifacts are retained.  CandidatePolicy validates worst-case
   prompt budgets before a provider call; no truncation or silent omission.

## Commit-sized phases

### Phase 1 — PNCA contracts and structural validators

Create `novel_forge/pnca/contracts.py` and `novel_forge/pnca/validation.py`.

- Define Pydantic models for Series/Volume/Chapter/Scene contracts,
  requirement ledgers, CandidatePolicy/Plan, FrontierBinding, OperationRecord,
  AcceptanceCommit, and BundleSlotRecord/DesignBundle.
- Implement structural-only validators for requirement ownership/disposition,
  deferred target slots, AdmissionAllowance consumption, SceneSlot ordering,
  and no-effect/mutating patch separation.
- Add `tests/test_pnca_contracts.py` using no LLM and no repository mocks.
- RED tests cover invalid deferment, duplicate requirement fulfillment,
  unapproved admission, malformed frontier binding, and no-effect event use.

Gate: targeted PNCA tests, then full pytest, Ruff, and mypy for new modules.

### Phase 2 — Immutable repository acceptance transaction

Extend `RunRepository` with an atomic PNCA acceptance protocol.

- Stage immutable role artifacts normally.
- Add `commit_acceptance()` that validates required roles and publishes one
  descendant selection snapshot plus one AcceptanceCommit record.
- Add exact FrontierBinding validation: selected input snapshot, frontier ID,
  frontier digest, source SceneContract, and output parent frontier are equal,
  not merely ancestors.
- Add OperationRecord lookup/state transitions for idempotent resume and
  `superseded` base-snapshot conflicts.
- Prohibit a selected `canon.frontier` without the causal selected Scene
  Contract and evidence roles.

Gate: crash-before-commit, idempotent-resume, divergent-base, and
frontier-only-state RED regressions; full gate after green.

### Phase 3 — PNCA task/artifact registry and bounded candidate batches

Replace the fixed operation cartesian product and `_TASK_VARIABLES` duplicate
source of truth.

- Extend task registry into TaskSpec + ArtifactSpec with permitted input roles,
  prompt/schema digests, output type, logical-key template, retry/budget class,
  and idempotency scope.
- Add registered PNCA task families: contract candidate, three ContractAudits,
  ReviewSynthesis, revision candidate, selection-synthesis, writer, DraftAudit.
- Add CandidatePlan accounting before every provider call.  Parse/schema
  responses consume their reserved execution credit; no-response transport
  failure does not create a second candidate credit.
- Enforce all raw audit inputs for synthesis and policy-level worst-case input
  budget before calls.

Gate: registry-role tests, fake-client dispatch tests, candidate-credit resume
regressions, and prompt/schema alignment checks.

### Phase 4 — PNCA progressive orchestration and Canon transition

Create a PNCA workflow that owns Series → Volume → Chapter → Scene progression.

- Generate contracts only within their allowed resolution and parent-pinned
  artifacts.
- Run exactly three independent ContractAudits per candidate and persist every
  raw output.  ReviewSynthesis may recommend but cannot mutate authority.
- Select structurally valid candidates under the pinned conservative/best-effort
  policy; scope-escalation observations create a DecisionRecord only.
- Compile SceneContract typed Canon patch and commit it through Phase 2's
  AcceptanceCommit.  Remove `accept_scene_design()` from public use.
- Use canonical root / previous selected SceneContract transition packets for
  first and subsequent SceneSlots.

Gate: fake-runner Series→Scene integration; no audit claim in later authoring
inputs; suffix rebuild and exact frontier tests.

### Phase 5 — writer boundary, bundle-pinned export, and CLI cutover

- Compile a single pre-frontier writer view plus post-patch end constraints.
- Make DraftAudit a separate observation task over an accepted SceneContract
  and draft; it cannot change Canon.
- Build and validate DesignBundle topology before render/export.
- Export exclusively from explicit bundle/snapshot inputs and manifest all
  selected evidence digests; strict release evaluates policy-defined open
  observations without asserting semantic proof.
- Wire plan/design/write/export/resume/complete CLI commands to PNCA workflow.

Gate: fresh-process bundle export, broken topology rejection, no global-frontier
read, CLI wiring tests, and fake end-to-end pipeline.

### Phase 6 — destructive retirement and operational validation

- Remove old generate→review→revise orchestration, old task resources, legacy
  tests, `accept_scene_design()`, and any latest-ready production fallback.
- Refresh user and developer docs from live CLI behavior.
- Run full pytest, Ruff, mypy, `uv build`, and diff checks.
- Run a minimal real-model smoke in background with the configured
  `qwen3.6:35b-a3b-mtp-q4_K_M`, inspect immutable raw evidence, then run the
  strict bundle-pinned export verification.

## Completion criteria

PNCA is complete only when public CLI execution reaches the PNCA workflow end
to end, legacy authority paths are unreachable, every acceptance test in the
governing PNCA contract has an executable regression test, and a real model
run produces a verifiable bundle-pinned export.
