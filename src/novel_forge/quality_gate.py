from __future__ import annotations

from novel_forge.kanji_data import COMMON_USE_KANJI
from novel_forge.models import QualityGateResult

_JIS_KANJI: set[str] | None = None


def _build_jis_kanji() -> set[str]:
    """JIS X 0208 + JIS X 0212 + JIS X 0213 の漢字セットを構築する。"""
    kanji: set[str] = set()

    def _is_cjk(ch: str) -> bool:
        cp = ord(ch)
        return (
            (0x3400 <= cp <= 0x4DBF)
            or (0x4E00 <= cp <= 0x9FFF)
            or (0x20000 <= cp <= 0x2A6DF)
        )

    # JIS X 0208 (EUC-JP 2-byte)
    for row in range(0x21, 0x54):
        for cell in range(0x21, 0x7F):
            try:
                euc = bytes([row | 0x80, cell | 0x80])
                ch = euc.decode("euc-jp", errors="strict")
                if len(ch) == 1 and _is_cjk(ch):
                    kanji.add(ch)
            except (UnicodeDecodeError, ValueError):
                pass

    # JIS X 0212 (EUC-JP 3-byte with SS2)
    for row in range(0x21, 0x7F):
        for cell in range(0x21, 0x7F):
            try:
                euc = bytes([0x8E, row | 0x80, cell | 0x80])
                ch = euc.decode("euc-jp", errors="strict")
                if len(ch) == 1 and _is_cjk(ch):
                    kanji.add(ch)
            except (UnicodeDecodeError, ValueError):
                pass

    # JIS X 0213 via shift_jis_2004
    for row in range(0x21, 0x7F):
        for cell in range(0x21, 0x7F):
            try:
                sj = bytes([row | 0x80, cell | 0x80])
                ch = sj.decode("shift_jis_2004", errors="strict")
                if len(ch) == 1 and _is_cjk(ch):
                    kanji.add(ch)
            except (UnicodeDecodeError, ValueError):
                pass

    return kanji


def _get_jis_kanji() -> set[str]:
    """遅延初期化された JIS 漢字セット + 常用漢字・人名用漢字を返す。"""
    global _JIS_KANJI
    if _JIS_KANJI is None:
        _JIS_KANJI = _build_jis_kanji()
        # 常用漢字（2136字）+ 人名用漢字（863字）のうちJIS未収録分を追加
        # これらは日本語として正しい漢字
        _JIS_KANJI.update(COMMON_USE_KANJI)
    return _JIS_KANJI


def find_non_japanese_kanji(text: str) -> list[str]:
    """
    テキスト中の JIS 漢字セットに含まれない CJK 漢字を検出する。
    ただし、常用漢字・人名用漢字は日本語として許可する。
    Returns: 検出された文字のリスト（重複あり、出現順）
    """
    jis = _get_jis_kanji()
    result: list[str] = []
    for ch in text:
        cp = ord(ch)
        is_cjk = (
            (0x3400 <= cp <= 0x4DBF)
            or (0x4E00 <= cp <= 0x9FFF)
            or (0x20000 <= cp <= 0x2A6DF)
        )
        if is_cjk and ch not in jis:
            # JIS未収録のCJK漢字 → 簡体字の可能性が高い
            result.append(ch)
    return result


class QualityGate:
    """シーン・巻の品質を評価し、合格/不合格を判定する。"""

    PASS_THRESHOLD = 70.0
    DEFAULT_MAX_RETRIES = 2

    def __init__(self, max_retries: int = DEFAULT_MAX_RETRIES):
        self.max_retries = max_retries

    def check_scene(self, review_result: dict) -> QualityGateResult:
        """レビュー結果に基づきシーン品質を判定する。"""
        score = review_result.get("score", 0.0)
        issues = review_result.get("issues", [])
        critical_count = sum(
            1 for i in issues if i.get("severity") in ("critical", "blocker")
        )
        # revision_needed が明示的に false の場合のみ、score 閾値でパスを許可
        # revision_needed が true または欠落している場合は不合格とする
        revision_needed = review_result.get("revision_needed", True)
        threshold = self.PASS_THRESHOLD
        passed = score >= threshold and critical_count == 0 and not revision_needed
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
        max_score = 100.0
        if force_exported_count > 0:
            max_score = 50.0
        avg_score = min(avg_score, max_score)
        passed = avg_score >= self.PASS_THRESHOLD and structural_validity
        return {
            "passed": passed,
            "score": avg_score,
            "force_exported_count": force_exported_count,
        }
