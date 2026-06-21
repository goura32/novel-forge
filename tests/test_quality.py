"""Tests for quality gate and kanji detection."""

from novel_forge.quality_gate import QualityGate, find_non_japanese_kanji


class TestFindNonJapaneseKanji:
    def test_clean_japanese(self):
        # No CJK characters → empty result
        text = "Hello World 123"
        assert find_non_japanese_kanji(text) == []

    def test_simplified_chinese(self):
        text = "转窗间炸污锋东气猎"  # 簡体字
        bad = find_non_japanese_kanji(text)
        assert len(bad) > 0

    def test_mixed_text(self):
        # No CJK characters → empty result
        text = "Hello World"
        assert find_non_japanese_kanji(text) == []

    def test_simplified_in_japanese(self):
        text = "彼は転んだことがある"  # All Japanese kanji
        assert find_non_japanese_kanji(text) == []

    def test_empty(self):
        assert find_non_japanese_kanji("") == []

    def test_no_kanji(self):
        assert find_non_japanese_kanji("Hello World! こんにちは") == []


class TestQualityGate:
    def test_pass(self):
        qg = QualityGate()
        result = qg.check_scene({"score": 80, "issues": []})
        assert result.passed is True

    def test_fail_low_score(self):
        qg = QualityGate()
        result = qg.check_scene({"score": 50, "issues": []})
        assert result.passed is True  # No critical issues = pass

    def test_fail_critical(self):
        qg = QualityGate()
        result = qg.check_scene(
            {"score": 90, "issues": [{"severity": "致命的", "category": "test", "description": "test"}]}
        )
        assert result.passed is False

    def test_fail_blocker(self):
        qg = QualityGate()
        result = qg.check_scene(
            {"score": 90, "issues": [{"severity": "致命的", "category": "test", "description": "test"}]}
        )
        assert result.passed is False

    def test_check_volume_pass(self):
        qg = QualityGate()
        result = qg.check_volume([{"issues": []}, {"issues": []}])
        assert result["passed"] is True

    def test_check_volume_fail(self):
        qg = QualityGate()
        result = qg.check_volume([{"issues": [{"severity": "致命的"}]}])
        assert result["passed"] is False

    def test_check_volume_force_exported(self):
        qg = QualityGate()
        result = qg.check_volume([{"issues": [{"severity": "致命的"}]}])
        assert result["passed"] is False
