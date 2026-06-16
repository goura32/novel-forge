from novel_forge.quality import QualityGate, find_non_japanese_kanji


class TestFindNonJapaneseKanji:
    def test_clean_japanese(self):
        text = "吾輩は猫である。名前はまだ無一郎。"
        assert find_non_japanese_kanji(text) == []

    def test_simplified_chinese(self):
        text = "转窗间炸污锋东气猎"  # 簡体字
        bad = find_non_japanese_kanji(text)
        assert len(bad) > 0

    def test_mixed_text(self):
        text = "東京タワーの近くで転んだ"  # 転 is Japanese, not simplified
        assert find_non_japanese_kanji(text) == []

    def test_simplified_in_japanese(self):
        text = "彼は転んだことがある"  # All Japanese kanji
        assert find_non_japanese_kanji(text) == []

    def test_empty_text(self):
        assert find_non_japanese_kanji("") == []

    def test_no_kanji(self):
        assert find_non_japanese_kanji("Hello World! こんにちは") == []


class TestQualityGateKanji:
    def test_check_kanji_clean(self):
        qg = QualityGate()
        assert qg.check_kanji("吾輩は猫である") == []

    def test_check_kanji_with_simplified(self):
        qg = QualityGate()
        bad = qg.check_kanji("转窗间炸污锋东气猎")
        assert len(bad) > 0

    def test_check_kanji_unique(self):
        qg = QualityGate()
        result = qg.check_kanji("猫猫猫")  # 猫 is JIS
        assert result == []
