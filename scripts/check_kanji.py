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


def build_jis_kanji_set():
    """
    Build set of all kanji in JIS X 0208 and JIS X 0213 using EUC-JP codec.
    
    JIS X 0208:Rows 16-83, 94 cells = ~6355 kanji
    JIS X 0213: Plane 1 extends 0208, Plane 2 adds more
    
    Together these cover:
    - 常用漢字 2136字 (2010 revision)
    - 人名用漢字 861字
    - Plus many additional kanji used in Japanese names/places
    """
    kanji = set()
    
    # === JIS X 0208 (EUC-JP 2-byte) ===
    # Kanji rows: 16-83 (0x21-0x53), cells: 1-94 (0x21-0x7E)
    for row in range(0x21, 0x54):
        for cell in range(0x21, 0x7F):
            try:
                euc = bytes([row | 0x80, cell | 0x80])
                ch = euc.decode('euc-jp', errors='strict')
                if len(ch) == 1 and _is_cjk_ideograph(ch):
                    kanji.add(ch)
            except (UnicodeDecodeError, ValueError):
                pass
    
    # === JIS X 0212 (EUC-JP 3-byte with SS2=0x8E) ===
    for row in range(0x21, 0x7F):
        for cell in range(0x21, 0x7F):
            try:
                euc = bytes([0x8E, row | 0x80, cell | 0x80])
                ch = euc.decode('euc-jp', errors='strict')
                if len(ch) == 1 and _is_cjk_ideograph(ch):
                    kanji.add(ch)
            except (UnicodeDecodeError, ValueError):
                pass
    
    # === JIS X 0213 Plane 2 (Shift_JIS-2004 2-byte, EUC 3-byte) ===
    # JIS X 0213 Plane 2 uses different encoding, we handle it separately
    # via shift_jis_2004 codec which covers all of 0213
    for row in range(0x21, 0x7F):
        for cell in range(0x21, 0x7F):
            try:
                sj = bytes([row | 0x80, cell | 0x80])
                ch = sj.decode('shift_jis_2004', errors='strict')
                if len(ch) == 1 and _is_cjk_ideograph(ch):
                    kanji.add(ch)
            except (UnicodeDecodeError, ValueError):
                pass
    
    return kanji


def _is_cjk_ideograph(ch):
    """Check if char is a CJK Unified Ideograph."""
    cp = ord(ch)
    return ((0x3400 <= cp <= 0x4DBF) or 
            (0x4E00 <= cp <= 0x9FFF) or
            (0x20000 <= cp <= 0x2A6DF))


def check_text(text, jis_kanji):
    """
    Check text for non-Japanese kanji.
    
    Returns list of (line_num, char, context) tuples.
    """
    lines = text.split('\n')
    issues = []
    
    for i, line in enumerate(lines, 1):
        for char in line:
            if _is_cjk_ideograph(char) and char not in jis_kanji:
                context = max(line[:60], '')
                issues.append((i, char, context))
    
    return issues


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    
    print("Building JIS kanji set...")
    jis_kanji = build_jis_kanji_set()
    print(f"JIS kanji set: {len(jis_kanji)} characters")
    print()
    
    total_issues = 0
    for filepath in sys.argv[1:]:
        text = Path(filepath).read_text(encoding='utf-8')
        issues = check_text(text, jis_kanji)
        
        print(f"=== {filepath} ===")
        print(f"  Lines: {text.count(chr(10))}, Chars: {len(text)}")
        
        if not issues:
            print("  ✅ All kanji are in JIS set")
        else:
            print(f"  ⚠️  {len(issues)} non-JIS kanji found:")
            for line_num, char, ctx in issues:
                name = unicodedata.name(char, '???')[:35]
                print(f"    L{line_num:4d}  {char} U+{ord(char):04X} | {name} | {ctx}")
            total_issues += len(issues)
        print()
    
    if total_issues == 0:
        print("✅ No issues found across all files")
    else:
        print(f"⚠️  Total: {total_issues} non-JISS kanji across all files")


if __name__ == "__main__":
    main()
