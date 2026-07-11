"""Review loop — pure functions shared across all phases.

Functions here are stateless: all dependencies (LLM client, quality gate,
logger, strict flag) are passed as arguments. This makes them easy to
test with simple mocks.
"""

from __future__ import annotations

import json
from typing import Any, cast

from novel_forge.llm_client import LLMError, SchemaValidationError
from novel_forge.logging_config import get_logger

_log = get_logger("novel_forge.engine.review")


def format_review_text(review: dict) -> str:
    """Build a human-readable review text from a review dict.

    Shared by plan, design, and scene writing phases.
    """
    lines = ["レビュー結果:"]
    for issue in review.get("issues", []):
        sev = issue.get("severity", "")
        field = issue.get("field", "")
        desc = issue.get("description", "")
        sug = issue.get("suggestion", "")
        before = issue.get("before", "")
        after = issue.get("after", "")
        lines.append(f"  [{sev}] ({field}): {desc}")
        if sug:
            lines.append(f"    提案: {sug}")
        if before or after:
            b_text = " / ".join(before) if isinstance(before, list) else str(before)
            a_text = " / ".join(after) if isinstance(after, list) else str(after)
            lines.append(f"    修正: {b_text} → {a_text}")
    return "\n".join(lines)


def _revision_issues(review: dict) -> list[dict]:
    """Return review issues that require another revision pass.

    Review prompts are instructed to emit only actionable issues.  The loop can
    therefore decide mechanically: zero issues means pass, one or more issues
    means revise.
    """

    return [issue for issue in review.get("issues", []) if isinstance(issue, dict)]


def _drop_resolved_issues(review: dict, result: dict) -> dict:
    """Remove stale issues whose suggested replacement is already present."""
    issues = review.get("issues", [])
    if not isinstance(issues, list):
        return review
    result_text = json.dumps(result, ensure_ascii=False)
    kept = []
    dropped = 0
    for issue in issues:
        if not isinstance(issue, dict):
            kept.append(issue)
            continue
        before = str(issue.get("before", "") or "")
        after = str(issue.get("after", "") or "")
        if before and after and before == after:
            dropped += 1
            continue
        # Drop only clearly stale issues: the old text is gone and the suggested
        # replacement is already present. If ``after`` is not present, keep the
        # issue because ``before`` may be only a location hint from the reviewer,
        # not a verbatim substring of the current JSON.
        if before and after and before not in result_text and after in result_text:
            dropped += 1
            continue
        kept.append(issue)
    if dropped:
        review = {**review, "issues": kept}
    return review


def _validation_errors(validate_fn, result: dict, kind: str, label: str) -> list[str]:
    """Run semantic validation and normalize schema exceptions to error strings."""
    try:
        return cast(list[str], validate_fn(result))
    except SchemaValidationError as e:
        path = " -> ".join(str(p) for p in e.absolute_path) if e.absolute_path else "?"
        _log.warning("  [%s] %s: path=%s msg=%s (exception)", label, kind, path, e.message)
        return [f"path={path} msg={e.message}"]


def generate_and_review(
    generate_fn,
    validate_fn,
    review_fn,
    revise_fn,
    system: str,
    user_prompt: str,
    kind: str,
    llm: Any,
    quality: Any,
    engine: Any | None = None,
    generation_max_count: int | None = None,
    review_max_count: int | None = None,
) -> tuple[dict, dict]:
    """Generate → validate → review → revise loop. Returns (data, review).

    Generation retries re-run the original prompt after invalid model output or
    semantic validation failure. Review/revision cycles keep revising the current
    result until review passes or the review limit is reached.
    """
    max_generation = (
        generation_max_count
        if generation_max_count is not None
        else quality.generation_max_count
    )
    review_max = (
        review_max_count
        if review_max_count is not None
        else quality.review_max_count
    )
    generation_cycles = 0
    review_cycles = 0
    result: dict = {}
    review: dict = {"issues": []}

    # Destructive-redesign: every generation/review/revise call is wrapped in an
    # immutable attempt so the raw LLM request/response + parsed JSON are captured
    # against a fixed attempt directory (or skipped entirely in non-verbose mode).

    while generation_cycles < max_generation:
        try:
            if engine is not None and hasattr(engine, "_begin_attempt"):
                engine._begin_attempt(f"{kind}.generate", "generation", retry_number=generation_cycles + 1)
            result = generate_fn(user_prompt, generation_cycles)
        except SchemaValidationError as e:
            path = " -> ".join(str(p) for p in e.absolute_path) if e.absolute_path else "?"
            _log.warning(
                "  [GENERATE VALIDATION ERROR] %s: path=%s msg=%s attempt=%d/%d",
                kind,
                path,
                e.message,
                generation_cycles,
                max_generation,
            )
            if generation_cycles >= max_generation - 1:
                raise RuntimeError(
                    f"{kind}: generate validation failed after {max_generation} retries: path={path} msg={e.message}"
                ) from e
            generation_cycles += 1
            continue
        except LLMError as e:
            _log.warning(
                "  [GENERATE LLM ERROR] %s: msg=%s attempt=%d/%d",
                kind,
                str(e)[:200],
                generation_cycles,
                max_generation,
            )
            if generation_cycles >= max_generation - 1:
                raise RuntimeError(
                    f"{kind}: generate failed after {max_generation} retries: msg={str(e)[:200]}"
                ) from e
            generation_cycles += 1
            continue

        if llm._is_schema_echo(result) is True:
            _log.warning("  [SCHEMA ECHO] %s retry=%d", kind, generation_cycles)
            if generation_cycles >= max_generation - 1:
                raise RuntimeError(f"{kind}: schema echo failed after {max_generation} retries")
            generation_cycles += 1
            continue

        errors = _validation_errors(validate_fn, result, kind, "VALIDATION FAIL")
        if errors:
            _log.warning(
                "  [VALIDATION FAIL] %s: %s attempt=%d/%d", kind, errors, generation_cycles, max_generation
            )
            if generation_cycles >= max_generation - 1:
                raise RuntimeError(f"{kind}: validation failed after {max_generation} retries: {errors}")
            generation_cycles += 1
            continue
        break
    else:
        return result, review

    while True:
        try:
            if engine is not None and hasattr(engine, "_begin_attempt"):
                engine._begin_attempt(f"{kind}.review", "review", retry_number=review_cycles + 1)
            review = review_fn(result, system)
            review_cycles += 1
        except SchemaValidationError as e:
            path = " -> ".join(str(p) for p in e.absolute_path) if e.absolute_path else "?"
            _log.warning("  [REVIEW VALIDATION ERROR] %s: path=%s msg=%s", kind, path, e.message)
            if review_cycles >= review_max - 1:
                raise RuntimeError(f"{kind}: review validation failed after {review_max} retries") from e
            review_cycles += 1
            continue
        except LLMError as e:
            _log.warning(
                "  [REVIEW LLM ERROR] %s: msg=%s attempt=%d/%d",
                kind,
                str(e)[:200],
                review_cycles + 1,
                review_max,
            )
            if review_cycles >= review_max - 1:
                raise RuntimeError(
                    f"{kind}: review failed after {review_max} retries: msg={str(e)[:200]}"
                ) from e
            review_cycles += 1
            continue

        if len(_revision_issues(review)) == 0:
            return result, review

        if review_cycles >= review_max:
            _log.warning(
                "  [REVIEW ABANDONED] %s: 改訂が必要だが max_review_count に達したため改訂を諦めて次工程へ進みます (%d/%d)。"
                " 未解決の指摘 %d 件（次工程ではこれを前提として処理）:",
                kind,
                review_cycles,
                review_max,
                len(_revision_issues(review)),
            )
            for issue in _revision_issues(review):
                _log.warning(
                    "    - [%s] (%s): %s",
                    issue.get("severity", ""),
                    issue.get("field", ""),
                    issue.get("description", ""),
                )
            return result, review

        for revision_attempt in range(max_generation):
            seed_offset = generation_cycles + revision_attempt
            try:
                if engine is not None and hasattr(engine, "_begin_attempt"):
                    engine._begin_attempt(f"{kind}.revise", "revision", retry_number=revision_attempt + 1)
                revised = revise_fn(result, review, system, seed_offset)
            except SchemaValidationError as e:
                path = " -> ".join(str(p) for p in e.absolute_path) if e.absolute_path else "?"
                _log.warning(
                    "  [REVISION VALIDATION ERROR] %s: path=%s msg=%s attempt=%d/%d",
                    kind,
                    path,
                    e.message,
                    revision_attempt + 1,
                    max_generation,
                )
                if revision_attempt >= max_generation - 1:
                    raise RuntimeError(
                        f"{kind}: revision validation failed after {max_generation} retries: path={path} msg={e.message}"
                    ) from e
                continue
            except LLMError as e:
                _log.warning(
                    "  [REVISION LLM ERROR] %s: msg=%s attempt=%d/%d",
                    kind,
                    str(e)[:200],
                    revision_attempt + 1,
                    max_generation,
                )
                if revision_attempt >= max_generation - 1:
                    raise RuntimeError(
                        f"{kind}: revision failed after {max_generation} retries: msg={str(e)[:200]}"
                    ) from e
                continue

            errors = _validation_errors(validate_fn, revised, kind, "POST-REVISION VALIDATION")
            if errors:
                _log.warning(
                    "  [POST-REVISION VALIDATION] %s: %s attempt=%d/%d",
                    kind,
                    errors,
                    revision_attempt + 1,
                    max_generation,
                )
                if revision_attempt >= max_generation - 1:
                    raise RuntimeError(f"{kind}: post-revision validation failed after {max_generation} retries: {errors}")
                continue

            result = revised
            generation_cycles += 1
            break
        else:
            raise RuntimeError(f"{kind}: revision failed after {max_generation} retries")
