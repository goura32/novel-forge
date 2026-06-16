from __future__ import annotations

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
    """遅延初期化された JIS 漢字セットを返す。"""
    global _JIS_KANJI
    if _JIS_KANJI is None:
        _JIS_KANJI = _build_jis_kanji()
    return _JIS_KANJI


def find_non_japanese_kanji(text: str) -> list[str]:
    """
    テキスト中の JIS 漢字セットに含まれない CJK 漢字を検出する。
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
            result.append(ch)
    return result


class QualityGate:
    """シーン・巻の品質を評価し、合格/不合格を判定する。"""

    PASS_THRESHOLD = 7.0
    MAX_RETRIES = 3

    def check_scene(self, review_result: dict) -> QualityGateResult:
        """レビュー結果に基づきシーン品質を判定する。"""
        score = review_result.get("score", 0.0)
        issues = review_result.get("issues", [])
        critical_count = sum(
            1 for i in issues if i.get("severity") in ("critical", "blocker")
        )
        passed = score >= self.PASS_THRESHOLD and critical_count == 0
        return QualityGateResult(
            passed=passed,
            score=score,
            issues=issues,
        )

    def check_kanji(self, draft_text: str) -> list[str]:
        """
        ドラフトテキスト中の非日本語漢字（簡体字等）を検出する。
        Returns: 検出された文字のリスト（空なら問題なし）
        """
        return find_non_japanese_kanji(draft_text)

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
