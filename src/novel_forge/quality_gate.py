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

    def __init__(self, max_retries: int = 3):
        self.max_retries = max_retries

    def check(self, review_result: dict, stage: str = "scene") -> QualityGateResult:
        """レビュー結果に基づき品質を判定する。

        判定ルール（全工程共通）:
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
        return self.check(review_result, stage="scene")

    def check_volume(
        self,
        scene_results: list[dict],
        structural_validity: bool = True,
    ) -> dict:
        """巻全体の品質を判定する。

        判定ルール:
        - 全シーンの issues を集約し、check() と同じ基準で判定
        - structural_validity が false は巻デザイン未合格を意味し、不合格
        """
        all_issues: list[dict] = []
        for result in scene_results:
            all_issues.extend(result.get("issues", []))

        blocker_count = sum(1 for i in all_issues if i.get("severity") == "致命的")
        critical_count = sum(1 for i in all_issues if i.get("severity") == "重大")
        major_count = sum(1 for i in all_issues if i.get("severity") == "重要")

        passed = blocker_count == 0 and critical_count == 0 and major_count < 2 and structural_validity

        return {
            "passed": passed,
            "issue_count": len(all_issues),
            "blocker_count": blocker_count,
            "critical_count": critical_count,
            "major_count": major_count,
        }
