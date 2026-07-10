"""Self-correction tracking for the v2 Canon pipeline (Phase 3 review telemetry).

This module is a *pure observer* of the canon review gate.  It records every
issue the review gate emits (schema violations, semantic preflight failures,
POV leaks, cast-relevant scope violations, stale review evidence) as a
structured :class:`CorrectionRecord` so that recurring mistakes can be
detected across scenes and pipeline runs.

Design contract
---------------
* This module NEVER mutates the Canon, a CanonEvent, or the materialized view.
  It is append-only telemetry keyed by a stable issue category.
* Records are persisted as JSONL so a long-running authoring session can
  accumulate a correction history across many scene designs.
* ``classify_review_issues`` turns the free-text ``ReviewResult.issues`` list
  into typed records by extracting the leading ``[category]`` tag that the
  review gate already stamps on every issue.

A recurring issue is simply one that appears >= ``min_count`` times under the
same stable ``recurring_key`` (category + normalized message).  Detecting
recurrence is the *self-correction* signal: the same class of mistake firing
repeatedly is what an author/LLM should be steered to fix at the prompt or
schema level rather than scene-by-scene.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# Leading "[category] message" tag stamped by review_scene_patch / validators.
_ISSUE_TAG_RE = re.compile(r"^\[([^\]]+)\]\s*(.*)$")

# Canonical category names (kept stable so recurring_key is comparable across runs).
SCHEMA = "canon_patch_schema"
SEMANTIC = "canon_patch_semantic"
POV_LEAK = "pov_leak"
CAST_RELEVANT = "cast_relevant"
REVIEW_EVIDENCE = "review_evidence"
UNCLASSIFIED = "unclassified"


def _classify_tag(tag: str) -> str:
    t = tag.lower()
    if t.startswith("canon_patch schema"):
        return SCHEMA
    if t.startswith("canon_patch semantic"):
        return SEMANTIC
    if t.startswith("pov_leak"):
        return POV_LEAK
    if t.startswith("cast_relevant"):
        return CAST_RELEVANT
    if t.startswith("review_evidence"):
        return REVIEW_EVIDENCE
    return UNCLASSIFIED


@dataclass
class CorrectionRecord:
    """One review-issue observation, normalized for recurrence tracking."""

    category: str
    message: str
    scene_id: str = ""
    source_ref: str = ""
    severity: str = "error"
    timestamp: str = ""
    recurring_key: str = ""

    def __post_init__(self) -> None:
        if not self.timestamp:
            self.timestamp = datetime.now(UTC).isoformat()
        if not self.recurring_key:
            self.recurring_key = self._derive_key()

    def _derive_key(self) -> str:
        # Normalize the message so trivial wording drift still groups together:
        # keep the category + a collapsed form of the message (alnum only, lower).
        norm = re.sub(r"[^a-z0-9]+", "_", self.message.lower()).strip("_")
        norm = norm[:120]  # cap to keep keys comparable but stable
        return f"{self.category}:{norm}"


@dataclass
class SelfCorrectionTracker:
    """Append-only telemetry store for review-gate issues.

    In-memory by default; optionally persisted to a JSONL file so a session
    across many scene designs accumulates a correction history.
    """

    path: Path | None = None
    records: list[CorrectionRecord] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.path is not None:
            self.path = Path(self.path)
            if self.path.exists():
                self._load()

    # -- ingestion ---------------------------------------------------------

    def record(self, record: CorrectionRecord) -> CorrectionRecord:
        self.records.append(record)
        if self.path is not None:
            self._append(record)
        return record

    def record_issues(
        self,
        issues: list[str],
        scene_id: str = "",
        source_ref: str = "",
        severity: str = "error",
    ) -> list[CorrectionRecord]:
        """Classify a ``ReviewResult.issues`` list and append typed records."""
        out: list[CorrectionRecord] = []
        for raw in issues:
            tag_match = _ISSUE_TAG_RE.match(raw)
            if tag_match:
                category = _classify_tag(tag_match.group(1))
                message = tag_match.group(2).strip()
            else:
                category = UNCLASSIFIED
                message = raw.strip()
            out.append(
                self.record(
                    CorrectionRecord(
                        category=category,
                        message=message,
                        scene_id=scene_id,
                        source_ref=source_ref,
                        severity=severity,
                    )
                )
            )
        return out

    # -- analysis ----------------------------------------------------------

    def categories(self) -> dict[str, int]:
        """Count records per category."""
        return dict(Counter(r.category for r in self.records))

    def recurring(self, min_count: int = 2) -> dict[str, list[CorrectionRecord]]:
        """Return recurring_key -> records for keys seen >= min_count times."""
        by_key: dict[str, list[CorrectionRecord]] = {}
        for r in self.records:
            by_key.setdefault(r.recurring_key, []).append(r)
        return {k: v for k, v in by_key.items() if len(v) >= min_count}

    def summarize(self) -> dict[str, Any]:
        """Compact summary for logs / readiness reports."""
        by_cat = self.categories()
        recur = self.recurring()
        return {
            "total": len(self.records),
            "by_category": by_cat,
            "recurring_count": len(recur),
            "recurring": {
                k: {"count": len(v), "category": v[0].category, "sample": v[0].message}
                for k, v in recur.items()
            },
        }

    # -- persistence -------------------------------------------------------

    def _append(self, record: CorrectionRecord) -> None:
        assert self.path is not None
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(asdict(record), ensure_ascii=False) + "\n")

    def _load(self) -> None:
        assert self.path is not None
        with self.path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    self.records.append(CorrectionRecord(**json.loads(line)))
                except (json.JSONDecodeError, TypeError):
                    continue


def classify_review_issues(
    issues: list[str],
    scene_id: str = "",
    source_ref: str = "",
) -> list[CorrectionRecord]:
    """Convenience: classify issues without retaining a tracker instance."""
    return SelfCorrectionTracker().record_issues(
        issues, scene_id=scene_id, source_ref=source_ref
    )


__all__ = [
    "CAST_RELEVANT",
    "CorrectionRecord",
    "POV_LEAK",
    "REVIEW_EVIDENCE",
    "SCHEMA",
    "SEMANTIC",
    "SelfCorrectionTracker",
    "UNCLASSIFIED",
    "classify_review_issues",
]
