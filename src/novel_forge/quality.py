from __future__ import annotations

from novel_forge.models import QualityGateResult


class QualityGate:
    """シーン・巻の品質を評価し、合格/不合格を判定する。"""

    PASS_THRESHOLD = 7.0
    MAX_RETRIES = 3

    def check_scene(self, review_result: dict) -> QualityGateResult:
        """レビュー結果に基づきシーン品質を判定する。"""
        score = review_result.get("score", 0.0)
        issues = review_result.get("issues", [])
        critical_count = sum(1 for i in issues if i.get("severity") == "critical")
        passed = score >= self.PASS_THRESHOLD and critical_count == 0
        return QualityGateResult(
            passed=passed,
            score=score,
            issues=issues,
        )

    def check_volume(
        self,
        scene_scores: list[float],
        structural_validity: bool = True,
        force_exported_count: int = 0,
    ) -> dict:
        """巻全体の品質を判定する。"""
        avg_score = sum(scene_scores) / len(scene_scores) if scene_scores else 0.0
        max_score = 10.0
        if force_exported_count > 0:
            max_score = 5.0
        avg_score = min(avg_score, max_score)
        passed = avg_score >= self.PASS_THRESHOLD and structural_validity
        return {
            "passed": passed,
            "score": avg_score,
            "force_exported_count": force_exported_count,
        }
