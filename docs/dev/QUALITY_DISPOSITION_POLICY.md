# PNCA Quality Disposition Policy

## Purpose

PNCA treats every LLM output as a candidate. A bounded review/revision loop must not silently turn unresolved hard failures into accepted state, but it must also avoid an unbounded loop over editorial observations. This policy applies to `plan`, `design`, `write`, and `export`.

## Immutable disposition

Every publishable write candidate has a `pnca.quality_disposition` artifact. It pins:

- the subject artifact;
- the immutable review artifact(s) used for the decision;
- `clean` or `deferred` status; and
- each residual deferred finding, with its exact review artifact and issue index.

A bundle pins the disposition beside its draft and assessment. Export verifies that the disposition is derived from the same contract, WriterView, draft, and assessment as the selected bundle slot.

`clean` means no residual finding. `deferred` does **not** mean accepted-as-correct: it means residual editorial debt is explicit and traceable.

## Non-waivable failures

The following never become deferred automatically and must fail closed after the bounded repair budget:

1. schema, artifact identity, provenance, or snapshot failures;
2. Canon / admission / frontier failures;
3. parent-child topology or slot failures;
4. required state transition, required beat, or end-constraint failures;
5. POV facts that disclose unavailable knowledge, intent, memory, or secrets;
6. reader-blocking language contamination, schema leakage, or unreadable prose; and
7. any audit finding whose `constraint_kind` is not `quality`.

The final rule deliberately does not trust a model-provided severity label to lower a hard contract failure. In particular, `required_beat`, `end_constraint`, `pov_fact`, and `language_contamination` cannot become automatic editorial debt merely because a reviewer emitted `major` or `minor`.

## Deferred editorial debt

Only findings satisfying all of the following may be deferred:

- `constraint_kind == "quality"`;
- `severity` is `major` or `minor`;
- the final audit artifact is pinned; and
- no non-waivable finding remains.

Examples are repetition, weak rhythm, non-essential imagery, and a stylistic improvement that does not alter a Canon fact, required transition, or downstream contract.

## Bounded repair policy

1. Run deterministic structural and provenance validation before review.
2. Review the candidate and repair non-waivable findings within the configured bounded budget.
3. Re-review each new candidate as a new immutable attempt.
4. If a non-waivable finding remains, reject the candidate and do not select or export it.
5. When hard findings are absent, perform at most one editorial polish pass for actionable `major` / `minor` quality findings.
6. Re-review the polish output. Record any residual eligible findings as `deferred`; otherwise record `clean`.

No client-side hidden retry, fabricated coverage, severity rewriting, or text-level patching is permitted.

## Phase application

| Phase | Never progress with | May progress with recorded debt |
|---|---|---|
| Plan | incompatible final resolution, unstable identity / Canon assumptions, impossible event order | titles, thematic emphasis, non-essential subplots |
| Design | parent-child mismatch, missing slot, invalid state transition, admission/frontier break | scene-title, pacing, non-essential staging concerns |
| Write | unmet beat/end state, provenance break, secret-leaking POV fact, unreadable text | rhythm, repetition, non-essential stylistic concerns |
| Export | missing or invalid pinned disposition, any non-waivable selected residual | a bundle whose slots carry valid editorial debt dispositions |

## Operational consequences

A deferred finding remains immutable evidence; it is not deleted, relabelled, or interpreted as a clean pass. Publication policy may require a later final-polish run, but export must always retain the disposition input IDs so the manuscript is auditable.
