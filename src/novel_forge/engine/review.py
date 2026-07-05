"""Review loop — pure functions shared across all phases.

Functions here are stateless: all dependencies (LLM client, quality gate,
logger, strict flag) are passed as arguments. This makes them easy to
test with simple mocks.
"""

from __future__ import annotations

from typing import Any

from novel_forge.llm_client import SchemaValidationError
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

    Stateful dependencies (LLM client, quality gate) are passed
    in, not captured — making this fully testable with mocks.

    Strict mode is ALWAYS ON: revision failure after max count raises RuntimeError.
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
    generation_cycles = 0  # Single counter for generation API + validation
    review_cycles = 0      # Separate counter for review → revise cycles
    result: dict = {}
    review: dict = {"issues": []}

    while generation_cycles < max_generation:
        # Check if we've exceeded review max for this attempt
        if review_cycles >= review_max and generation_cycles > 0:
            msg = f"  [REVIEW] {kind}: revision needed but max count reached ({review_cycles}/{review_max})"
            raise RuntimeError(msg)

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

        if llm._is_schema_echo(result):
            _log.warning("  [SCHEMA ECHO] %s retry=%d", kind, generation_cycles)
            generation_cycles += 1
            continue

        try:
            errors = validate_fn(result)
        except SchemaValidationError as e:
            # Log detailed path info for debugging
            path = " -> ".join(str(p) for p in e.absolute_path) if e.absolute_path else "?"
            _log.warning(
                "  [VALIDATION FAIL] %s: path=%s msg=%s (exception)", kind, path, e.message
            )
            errors = [f"path={path} msg={e.message}"]
        if errors:
            _log.warning(
                "  [VALIDATION FAIL] %s: %s attempt=%d/%d", kind, errors, generation_cycles, max_generation
            )
            if generation_cycles >= max_generation - 1:
                raise RuntimeError(f"{kind}: validation failed after {max_generation} retries: {errors}")
            generation_cycles += 1
            continue

        # First review (after initial generation)
        try:
            review = review_fn(result, system)
            review_cycles += 1
        except SchemaValidationError as e:
            path = " -> ".join(str(p) for p in e.absolute_path) if e.absolute_path else "?"
            _log.warning("  [REVIEW VALIDATION ERROR] %s: path=%s msg=%s", kind, path, e.message)
            # Force revision by injecting a critical issue
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
            if review_cycles >= review_max - 1:
                raise RuntimeError(f"{kind}: review validation failed after {review_max} retries") from e
            continue

        blocker = [i for i in review.get("issues", []) if i.get("severity") == "致命的"]
        major = [i for i in review.get("issues", []) if i.get("severity") == "重要"]
        revision_needed = len(blocker) > 0 or len(major) >= 2

        if not revision_needed:
            return result, review

        if review_cycles >= review_max:
            msg = f"  [REVIEW] {kind}: revision needed but max count reached ({review_cycles}/{review_max})"
            raise RuntimeError(msg)

        result = revise_fn(result, review, system, generation_cycles)
        generation_cycles += 1

        errors = validate_fn(result)
        if errors:
            _log.warning(
                "  [POST-REVISION VALIDATION] %s: %s attempt=%d/%d",
                kind,
                errors,
                generation_cycles,
                max_generation,
            )
            if generation_cycles >= max_generation - 1:
                raise RuntimeError(f"{kind}: post-revision validation failed after {max_generation} retries: {errors}")
            continue

        # Re-review the revised result
        try:
            review = review_fn(result, system)
            review_cycles += 1  # Count this as a review cycle
        except SchemaValidationError as e:
            path = " -> ".join(str(p) for p in e.absolute_path) if e.absolute_path else "?"
            _log.warning("  [POST-REVISION REVIEW VALIDATION ERROR] %s: path=%s msg=%s", kind, path, e.message)
            if review_cycles >= review_max:
                raise RuntimeError(f"{kind}: post-revision review validation failed after {review_max} retries") from e
            continue

        blocker = [i for i in review.get("issues", []) if i.get("severity") == "致命的"]
        major = [i for i in review.get("issues", []) if i.get("severity") == "重要"]
        fatal_count = len(blocker) + len(major)  # Include major in fatal count for strict mode check

        # Check review max separately for post-revision review
        if fatal_count > 0 and review_cycles >= review_max:
            msg = f"  [REVIEW] {kind}: revision needed but max count reached ({review_cycles}/{review_max})"
            raise RuntimeError(msg)

        if len(major) > 0 and review_cycles >= review_max:
            # Strict mode: stop if still has issues after review_max_count review cycles
            raise RuntimeError(f"  [REVIEW] {kind}: issues remain after {review_cycles} review cycles ({fatal_count} issues)")

        if len(blocker) == 0 and len(major) == 0:
            return result, review

        # Only revise again if we haven't hit review_max yet
        if review_cycles >= review_max:
            raise RuntimeError(f"  [REVIEW] {kind}: revision needed but max count reached ({review_cycles}/{review_max})")

        result = revise_fn(result, review, system, generation_cycles)
        generation_cycles += 1
        # Loop back for another validation + review cycle

    return result, review