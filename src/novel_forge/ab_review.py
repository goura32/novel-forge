"""Reusable helpers for isolated A/B replay of ``write.draft.review``.

This module deliberately does not alter RuntimeWorkflow.  Experiments replay the
same saved writer context and draft through alternate review templates, then
persist each provider call as immutable evidence in an experiment workspace.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from novel_forge.prompts import _build_simplified_schema, render_prompt
from novel_forge.task_registry import DEFAULT_TASK_REGISTRY


@dataclass(frozen=True, slots=True)
class ReviewCase:
    """One fixed review input reconstructed from a persisted production request."""

    case_id: str
    writer_context: dict[str, Any]
    draft: dict[str, Any]
    source_attempt_id: str


def extract_case_from_request(
    *,
    case_id: str,
    request_payload: dict[str, Any],
    source_attempt_id: str,
) -> ReviewCase:
    """Extract fixed review inputs from an immutable ``write.draft.review`` request.

    The production prompt injects JSON after the two headings below.  JSON is
    decoded from its exact start rather than split on arbitrary content, so a
    scene body may itself contain Markdown-like text safely.
    """

    messages = request_payload.get("messages")
    if not isinstance(messages, list):
        raise ValueError("saved request has no messages list")
    user_content = next(
        (
            message.get("content")
            for message in messages
            if isinstance(message, dict) and message.get("role") == "user"
        ),
        None,
    )
    if not isinstance(user_content, str):
        raise ValueError("saved request has no user message")

    context = _decode_json_after_heading(user_content, "### writer context\n")
    draft = _decode_json_after_heading(user_content, "### 本文\n")
    if not isinstance(context, dict) or not isinstance(draft, dict):
        raise ValueError("saved review inputs must both be JSON objects")
    return ReviewCase(
        case_id=case_id,
        writer_context=context,
        draft=draft,
        source_attempt_id=source_attempt_id,
    )


def render_review_prompt(
    template_path: Path,
    *,
    writer_context: dict[str, Any],
    draft: dict[str, Any],
) -> str:
    """Render a review template with the canonical review schema."""

    template = template_path.read_text(encoding="utf-8")
    schema = DEFAULT_TASK_REGISTRY.load_schema("write.draft.review")
    return render_prompt(
        template,
        {
            "writer_context": json.dumps(writer_context, ensure_ascii=False),
            "draft": json.dumps(draft, ensure_ascii=False),
            "schema": _build_simplified_schema(schema),
        },
    )


def replay_ollama_options(configured: dict[str, Any], *, seed: int) -> dict[str, Any]:
    """Return replay options without overriding provider sampling controls.

    A/B replay must let the provider use the production default for temperature
    and top-p.  The seed is retained only to pair A/B calls reproducibly.
    """
    options = {key: value for key, value in configured.items() if key not in {"temperature", "top_p"}}
    return {**options, "seed": seed}


def actionability_summary(draft: dict[str, Any], review: dict[str, Any]) -> dict[str, int]:
    """Measure mechanical revision readiness without judging creative validity."""

    issues = review.get("issues", [])
    if not isinstance(issues, list):
        raise ValueError("review issues must be a list")
    draft_text = json.dumps(draft, ensure_ascii=False)
    actionable = 0
    missing_before = 0
    empty_after = 0
    for issue in issues:
        if not isinstance(issue, dict):
            missing_before += 1
            empty_after += 1
            continue
        before = issue.get("before")
        after = issue.get("after")
        has_before = isinstance(before, str) and bool(before) and before in draft_text
        has_after = isinstance(after, str) and bool(after)
        if not has_before:
            missing_before += 1
        if not has_after:
            empty_after += 1
        if has_before and has_after:
            actionable += 1
    return {
        "issue_count": len(issues),
        "actionable_issue_count": actionable,
        "missing_before_count": missing_before,
        "empty_after_count": empty_after,
    }


def _decode_json_after_heading(content: str, heading: str) -> Any:
    start = content.find(heading)
    if start < 0:
        raise ValueError(f"saved request missing heading: {heading.rstrip()}")
    raw = content[start + len(heading) :].lstrip()
    try:
        value, _ = json.JSONDecoder().raw_decode(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"saved request has invalid JSON after {heading.rstrip()}") from exc
    return value
