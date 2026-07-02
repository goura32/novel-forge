"""品質ゲート: レビュー結果に基づき工程の合否を判定する。

スコア採点は廃止し、指摘事項の深刻度（severity）のみで判定する。
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class QualityGateResult:
    """品質ゲートの判定結果。"""

    passed: bool
    issues: list[dict] = field(default_factory=list)

    @property
    def blocker_count(self) -> int:
        return sum(1 for i in self.issues if i.get("severity") == "致命的")

    @property
    def critical_count(self) -> int:
        return sum(1 for i in self.issues if i.get("severity") == "重大")

    @property
    def major_count(self) -> int:
        return sum(1 for i in self.issues if i.get("severity") == "重要")

    @property
    def minor_count(self) -> int:
        return sum(1 for i in self.issues if i.get("severity") == "軽微")

    @property
    def revision_needed(self) -> bool:
        """改稿が必要か。致命的・重大 issue、または重要 issue が2つ以上で true。"""
        return self.blocker_count > 0 or self.critical_count > 0 or self.major_count >= 2


class QualityGate:
    """品質ゲート判定エンジン。"""

    DEFAULT_MAX_RETRIES = 3

    def __init__(
        self,
        max_retries: int = DEFAULT_MAX_RETRIES,
        generation_max_retries: int | None = None,
        review_max_retries: int | None = None,
    ):
        self.max_retries = max_retries
        self.generation_max_retries = generation_max_retries or max_retries
        self.review_max_retries = review_max_retries or max_retries

    def _check(self, review_result: dict) -> QualityGateResult:
        """レビュー結果に基づき品質を判定する。

        判定ルール:
        - 致命的 issue が1つでもある → 不合格
        - 重大 issue が1つでもある → 不合格
        - 重要 issue が2つ以上ある → 不合格
        - 軽微 issue のみ、または issue なし → 合格
        """
        issues = review_result.get("issues", [])

        blocker_count = sum(1 for i in issues if i.get("severity") == "致命的")
        critical_count = sum(1 for i in issues if i.get("severity") == "重大")
        major_count = sum(1 for i in issues if i.get("severity") == "重要")

        passed = blocker_count == 0 and critical_count == 0 and major_count < 2

        return QualityGateResult(
            passed=passed,
            issues=issues,
        )

    def check_scene(self, review_result: dict) -> QualityGateResult:
        """レビュー結果に基づきシーン品質を判定する。"""
        return self._check(review_result)
