#!/usr/bin/env python3
"""
check_kanji.py - Check for non-Japanese kanji in text files.

Detects CJK Unified Ideographs that are NOT in the JIS X 0208 + JIS X 0213
character set (which covers all 常用漢字 and 人名用漢字).

Usage:
    python check_kanji.py <file1> [file2] ...
"""
import sys
import unicodedata
from pathlib import Path

from novel_forge.quality import find_non_japanese_kanji


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    total_issues = 0
    for filepath in sys.argv[1:]:
        text = Path(filepath).read_text(encoding="utf-8")
        bad_chars = find_non_japanese_kanji(text)

        print(f"=== {filepath} ===")
        print(f"  Lines: {text.count(chr(10))}, Chars: {len(text)}")

        if not bad_chars:
            print("  ✅ All kanji are in JIS set")
        else:
            # 行番号・コンテキスト付きで出力
            lines = text.split("\n")
            char_to_lines: dict[str, list[int]] = {}
            for i, line in enumerate(lines, 1):
                for ch in line:
                    if ch in bad_chars:
                        char_to_lines.setdefault(ch, []).append(i)

            unique_chars = list(dict.fromkeys(bad_chars))  # 重複排除・順序保持
            print(f"  ⚠️  {len(bad_chars)} non-JIS kanji found ({len(unique_chars)} unique):")
            for ch in unique_chars:
                name = unicodedata.name(ch, "???")[:35]
                line_nums = char_to_lines.get(ch, [])
                first_line = line_nums[0] if line_nums else "?"
                ctx = lines[int(first_line) - 1][:60] if isinstance(first_line, int) else ""
                print(f"    {ch} U+{ord(ch):04X} | {name} | L{first_line} | {ctx}")
            total_issues += len(bad_chars)
        print()

    if total_issues == 0:
        print("✅ No issues found across all files")
    else:
        print(f"⚠️  Total: {total_issues} non-JIS kanji across all files")


if __name__ == "__main__":
    main()
