"""品質ゲート: レビュー結果に基づき工程の合否を判定する。

スコア採点とLLMによる出版可否判定は廃止し、指摘事項の件数のみで判定する。
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
        # 旧スキーマ互換: "重大" も致命的として扱う
        return sum(1 for i in self.issues if i.get("severity") in ("重大", "致命的"))

    @property
    def major_count(self) -> int:
        return sum(1 for i in self.issues if i.get("severity") == "重要")

    @property
    def minor_count(self) -> int:
        return sum(1 for i in self.issues if i.get("severity") == "軽微")

    @property
    def revision_needed(self) -> bool:
        """改稿が必要か。指摘事項が1件以上あれば true。"""
        return len(self.issues) > 0


class QualityGate:
    """品質ゲート判定エンジン。"""

    DEFAULT_MAX_RETRIES = 1

    def __init__(self, max_retries: int = DEFAULT_MAX_RETRIES, generation_count: int | None = None, review_count: int | None = None):
        self.max_retries = max_retries
        self.generation_max_count = generation_count or max_retries
        self.review_max_count = review_count or max_retries

    def _check(self, review_result: dict) -> QualityGateResult:
        """レビュー結果に基づき品質を判定する。

        判定ルール:
        - issue が1件以上ある → 不合格
        - issue なし → 合格
        """
        issues = review_result.get("issues", [])

        passed = len(issues) == 0

        return QualityGateResult(
            passed=passed,
            issues=issues,
        )

    def check_scene(self, review_result: dict) -> QualityGateResult:
        """レビュー結果に基づきシーン品質を判定する。"""
        return self._check(review_result)