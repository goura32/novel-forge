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
        # severity は任意の文字列。critical/致命的 を blocker とする。
        return sum(1 for i in self.issues if i.get("severity") in ("critical", "致命的"))

    @property
    def critical_count(self) -> int:
        # 旧スキーマ互換: critical/致命的 を blocker として扱う
        return sum(1 for i in self.issues if i.get("severity") in ("critical", "致命的"))

    @property
    def major_count(self) -> int:
        return sum(1 for i in self.issues if i.get("severity") in ("important", "重要"))

    @property
    def minor_count(self) -> int:
        return sum(1 for i in self.issues if i.get("severity") in ("minor", "軽微"))

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

        判定ルール（severity ベース）:
        - critical / 致命的 の issue が1件以上 → 不合格
        - important / minor のみ（または指摘なし） → 合格

        設計意図: review は物語の整合性を幅広く指摘することが望ましいが、
        出版不能な致命的欠陥（POV の視点破綻、読者に見える論理破綻など）
        のみをゲートの不合格事由とする。important/minor は警告として
        許容し、KDP レポートが「全シーン不合格」と誤警告することを防ぐ。
        """
        issues = review_result.get("issues", [])

        blocker = sum(1 for i in issues if i.get("severity") in ("critical", "致命的"))
        passed = blocker == 0

        return QualityGateResult(
            passed=passed,
            issues=issues,
        )

    def check_scene(self, review_result: dict) -> QualityGateResult:
        """レビュー結果に基づきシーン品質を判定する。"""
        return self._check(review_result)