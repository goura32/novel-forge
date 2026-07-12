"""Semantic validation for review payloads that feed automatic revision."""

from typing import Any

_EDITABLE_DRAFT_FIELDS = ("title", "content")


def validate_draft_review_actionability(
    draft: dict[str, Any], review: dict[str, Any]
) -> list[str]:
    """Return errors for issues that cannot be applied as direct draft replacements.

    The JSON schema remains tolerant. This boundary protects the automatic
    review→revise edge: a reviewer may only cite a non-empty exact span from an
    editable string in the current draft and must provide a distinct non-empty
    replacement.
    """
    editable_values = [
        value
        for field in _EDITABLE_DRAFT_FIELDS
        if isinstance((value := draft.get(field)), str)
    ]
    issues = review.get("issues")
    if not isinstance(issues, list):
        return ["issues must be a list"]

    errors: list[str] = []
    for index, raw_issue in enumerate(issues):
        if not isinstance(raw_issue, dict):
            errors.append(f"issues[{index}] must be an object")
            continue
        before = raw_issue.get("before")
        after = raw_issue.get("after")
        if not isinstance(before, str) or not before.strip():
            errors.append(f"issues[{index}].before must be a non-empty exact draft span")
        elif not any(before in value for value in editable_values):
            errors.append(f"issues[{index}].before is not present in an editable draft field")
        if not isinstance(after, str) or not after.strip():
            errors.append(f"issues[{index}].after must be a non-empty replacement")
        elif isinstance(before, str) and after == before:
            errors.append(f"issues[{index}].after must differ from before")
    return errors
