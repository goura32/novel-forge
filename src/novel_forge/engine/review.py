"""Review loop — pure functions shared across all phases.

Functions here are stateless: all dependencies (LLM client, quality gate,
logger, strict flag) are passed as arguments. This makes them easy to
test with simple mocks.
"""

from __future__ import annotations

from typing import Any

from novel_forge.logging_config import get_logger
from novel_forge.llm_client import SchemaValidationError

_log = get_logger("novel_forge.engine.review")


def format_review_text(review: dict) -> str:
    """Build a human-readable review text from a review dict.

    Shared by plan, design, and scene writing phases.
    """
    lines = ["レビュー結果:"]
    for issue in review.get("issues", []):
        sev = issue.get("severity", "")
        cat = issue.get("category", "")
        desc = issue.get("description", "")
        sug = issue.get("suggestion", "")
        before = issue.get("before", "")
        after = issue.get("after", "")
        lines.append(f"  [{sev}] {cat}: {desc}")
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
    strict: bool = False,
    on_revise=None,
) -> tuple[dict, dict]:
    """Generate → validate → review → revise loop. Returns (data, review).

    Stateful dependencies (LLM client, quality gate, strict) are passed
    in, not captured — making this fully testable with mocks.
    """
    max_retries = quality.max_retries
    seed_offset = 0
    result: dict = {}
    review: dict = {"issues": []}

    while seed_offset < max_retries:
        result = generate_fn(user_prompt, seed_offset)
        seed_offset += 1

        if llm._is_schema_echo(result):
            _log.warning("  [SCHEMA ECHO] %s retry=%d", kind, seed_offset - 1)
            continue

        try:
            errors = validate_fn(result)
        except SchemaValidationError as e:
            _log.warning("  [VALIDATION FAIL] %s: %s (exception)", kind, e)
            errors = [str(e)]
        if errors:
            _log.warning("  [VALIDATION FAIL] %s: %s attempt=%d/%d", kind, errors, seed_offset, max_retries)
            if seed_offset >= max_retries:
                if strict:
                    raise RuntimeError(f"  [VALIDATION FAIL] {kind}: {errors} (--strict mode)")
                _log.warning("  [VALIDATION FAIL] %s: max retries reached, still failing", kind)
                raise RuntimeError(f"  [VALIDATION FAIL] {kind}: validation failed after {max_retries} retries: {errors}")
            continue

        try:
            review = review_fn(result, system)
        except SchemaValidationError as e:
            _log.warning("  [REVIEW VALIDATION ERROR] %s: %s", kind, e)
            if strict:
                raise RuntimeError(f"{kind}: review validation failed (--strict mode)") from e
            # Force revision by injecting a critical issue
            review = {
                "issues": [{
                    "severity": "致命的",
                    "category": "バリデーションエラー",
                    "description": f"レビューのスキーマ検証に失敗しました: {str(e)[:200]}",
                    "suggestion": "スキーマに従ってレビューを再生成してください",
                    "before": "",
                    "after": "",
                }]
            }
            blocker = [i for i in review.get("issues", []) if i.get("severity") == "致命的"]
            critical = [i for i in review.get("issues", []) if i.get("severity") == "重大"]
            major = [i for i in review.get("issues", []) if i.get("severity") == "重要"]
            fatal_count = len(blocker) + len(critical)
            revision_needed = fatal_count > 0 or len(major) >= 2
            if not revision_needed:
                return result, review
            if seed_offset >= max_retries:
                _log.warning("  [REVIEW] %s: review validation failed, max retries reached", kind)
                raise RuntimeError(f"{kind}: review validation failed after {max_retries} retries")
            continue
        blocker = [i for i in review.get("issues", []) if i.get("severity") == "致命的"]
        critical = [i for i in review.get("issues", []) if i.get("severity") == "重大"]
        major = [i for i in review.get("issues", []) if i.get("severity") == "重要"]
        fatal_count = len(blocker) + len(critical)
        revision_needed = fatal_count > 0 or len(major) >= 2

        if not revision_needed:
            return result, review

        if seed_offset >= max_retries:
            msg = f"  [REVIEW] {kind}: revision needed but max retries reached ({seed_offset}/{max_retries})"
            if strict:
                raise RuntimeError(msg + " (--strict mode)")
            _log.warning(msg)
            return result, review

        result = revise_fn(result, review, system, seed_offset)
        seed_offset += 1

        if on_revise:
            on_revise(result, seed_offset)

        errors = validate_fn(result)
        if errors:
            if seed_offset >= max_retries:
                msg = f"  [POST-REVISION VALIDATION] {kind}: {errors} (max retries reached)"
                _log.error(msg)
                if strict:
                    raise RuntimeError(msg + " (--strict mode)")
            else:
                _log.warning(
                    "  [POST-REVISION VALIDATION] %s: %s attempt=%d/%d",
                    kind, errors, seed_offset, max_retries,
                )
            continue

        try:
            review = review_fn(result, system)
        except SchemaValidationError as e:
            _log.warning("  [REVIEW VALIDATION ERROR] %s: %s", kind, e)
            if strict:
                raise RuntimeError(f"{kind}: review validation failed (--strict mode)") from e
            # Force revision by injecting a critical issue
            review = {
                "issues": [{
                    "severity": "致命的",
                    "category": "バリデーションエラー",
                    "description": f"レビューのスキーマ検証に失敗しました: {str(e)[:200]}",
                    "suggestion": "スキーマに従ってレビューを再生成してください",
                    "before": "",
                    "after": "",
                }]
            }
            blocker = [i for i in review.get("issues", []) if i.get("severity") == "致命的"]
            critical = [i for i in review.get("issues", []) if i.get("severity") == "重大"]
            major = [i for i in review.get("issues", []) if i.get("severity") == "重要"]
            fatal_count = len(blocker) + len(critical)
            revision_needed = fatal_count > 0 or len(major) >= 2
            if not revision_needed:
                return result, review
            if seed_offset >= max_retries:
                _log.warning("  [REVIEW] %s: review validation failed, max retries reached", kind)
                raise RuntimeError(f"{kind}: review validation failed after {max_retries} retries")
            continue
        blocker = [i for i in review.get("issues", []) if i.get("severity") == "致命的"]
        critical = [i for i in review.get("issues", []) if i.get("severity") == "重大"]
        major = [i for i in review.get("issues", []) if i.get("severity") == "重要"]
        if len(blocker) == 0 and len(critical) == 0 and len(major) < 2:
            return result, review

    return result, review
