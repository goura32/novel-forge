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
            lines.append(f"    修正: {before} → {after}")
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

    while generation_cycles < max_generation:
        try:
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
            review = review_fn(result, system)
            review = _drop_resolved_issues(review, result)
            review_cycles += 1
        except SchemaValidationError as e:
            path = " -> ".join(str(p) for p in e.absolute_path) if e.absolute_path else "?"
            _log.warning("  [REVIEW VALIDATION ERROR] %s: path=%s msg=%s", kind, path, e.message)
            if review_cycles >= review_max - 1:
                raise RuntimeError(f"{kind}: review validation failed after {review_max} retries") from e
            review = {
                "issues": [
                    {
                        "severity": "致命的",
                        "field": "review",
                        "description": f"レビューのスキーマ検証に失敗しました: {str(e)[:200]}",
                        "suggestion": "スキーマに従ってレビューを再生成してください",
                        "before": "",
                        "after": "",
                    }
                ]
            }
            review_cycles += 1

        if len(_revision_issues(review)) == 0:
            return result, review

        if review_cycles >= review_max:
            msg = f"  [REVIEW] {kind}: revision needed but max count reached ({review_cycles}/{review_max})"
            raise RuntimeError(msg)

        while generation_cycles < max_generation:
            try:
                revised = revise_fn(result, review, system, generation_cycles)
            except SchemaValidationError as e:
                path = " -> ".join(str(p) for p in e.absolute_path) if e.absolute_path else "?"
                _log.warning(
                    "  [REVISION VALIDATION ERROR] %s: path=%s msg=%s attempt=%d/%d",
                    kind,
                    path,
                    e.message,
                    generation_cycles,
                    max_generation,
                )
                if generation_cycles >= max_generation - 1:
                    raise RuntimeError(
                        f"{kind}: revision validation failed after {max_generation} retries: path={path} msg={e.message}"
                    ) from e
                generation_cycles += 1
                continue
            except LLMError as e:
                _log.warning(
                    "  [REVISION LLM ERROR] %s: msg=%s attempt=%d/%d",
                    kind,
                    str(e)[:200],
                    generation_cycles,
                    max_generation,
                )
                if generation_cycles >= max_generation - 1:
                    raise RuntimeError(
                        f"{kind}: revision failed after {max_generation} retries: msg={str(e)[:200]}"
                    ) from e
                generation_cycles += 1
                continue

            generation_cycles += 1
            errors = _validation_errors(validate_fn, revised, kind, "POST-REVISION VALIDATION")
            if errors:
                _log.warning(
                    "  [POST-REVISION VALIDATION] %s: %s attempt=%d/%d",
                    kind,
                    errors,
                    generation_cycles,
                    max_generation,
                )
                if generation_cycles >= max_generation:
                    raise RuntimeError(f"{kind}: post-revision validation failed after {max_generation} retries: {errors}")
                continue

            result = revised
            break
        else:
            raise RuntimeError(f"{kind}: revision failed after {max_generation} retries")
