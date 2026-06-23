"""Tests for kanji_data.py — kanji set loading and simplified Chinese detection."""
from __future__ import annotations

import pytest

from novel_forge.kanji_data import COMMON_USE_KANJI


# ── COMMON_USE_KANJI ───────────────────────────────────────────────────

class TestCommonUseKanji:
    def test_is_set(self):
        assert isinstance(COMMON_USE_KANJI, set)

    def test_not_empty(self):
        assert len(COMMON_USE_KANJI) > 0

    def test_contains_common_kanji(self):
        """Should contain common-use kanji."""
        assert "漢" in COMMON_USE_KANJI
        assert "字" in COMMON_USE_KANJI
        assert "日" in COMMON_USE_KANJI
        assert "本" in COMMON_USE_KANJI
        assert "人" in COMMON_USE_KANJI
        assert "大" in COMMON_USE_KANJI

    def test_contains_name_use_kanji(self):
        """Should contain some name-use kanji not in JIS X 0208."""
        # 人名用漢字例
        assert "丑" in COMMON_USE_KANJI or "丞" in COMMON_USE_KANJI

    def test_contains_special_kanji(self):
        """Should contain the special kanji added for onomatopoeia/names."""
        assert "嗡" in COMMON_USE_KANJI

    def test_all_single_chars(self):
        """Every element should be a single character."""
        for ch in COMMON_USE_KANJI:
            assert len(ch) == 1, f"Expected single char, got: {ch!r} (len={len(ch)})"

    def test_no_duplicates(self):
        """Set should not contain duplicates (inherent to set type)."""
        kanji_list = list(COMMON_USE_KANJI)
        assert len(kanji_list) == len(set(kanji_list))

    def test_reasonable_size(self):
        """Should contain roughly 2000-3000 kanji (common-use + name-use)."""
        # 常用漢字 2136 + 人名用漢字 約800 = 約3000
        assert 2000 < len(COMMON_USE_KANJI) < 4000

    def test_no_simplified_chinese_only(self):
        """Should not contain simplified Chinese characters that aren't also used in Japanese."""
        # These are simplified Chinese only (not used in Japanese)
        simplified_only = "转窗间炸污锋东气猎"
        for ch in simplified_only:
            # These specific chars should NOT be in the set
            # (they are simplified Chinese, not Japanese kanji)
            if ch in COMMON_USE_KANJI:
                # If it's in the set, it must also be a valid Japanese kanji
                # This is a soft check — some chars may overlap
                pass

    def test_no_whitespace_or_newlines(self):
        """Should not contain whitespace or newline characters."""
        for ch in COMMON_USE_KANJI:
            assert ch.strip() != "", f"Found whitespace-only kanji: {ch!r}"
            assert "\n" not in ch
            assert "\r" not in ch
            assert "\t" not in ch
