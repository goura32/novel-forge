#!/usr/bin/env python3
"""
プロンプトテンプレートと実装のプレースホルダ整合性を検証するスクリプト。

使用方法:
    python scripts/validate_prompts.py
    python scripts/validate_prompts.py --prompts-dir /path/to/prompts --src-dir /path/to/src
"""

import argparse
import re
import sys
from pathlib import Path


def extract_placeholders(text: str) -> set[str]:
    """テキストから {placeholder} を抽出する。"""
    return set(re.findall(r'\{([a-z_]+)\}', text))


def load_rendering_calls(src_dir: Path) -> dict[str, set[str]]:
    """ソースコードから render() 呼び出しを抽出し、プロンプト名 → 渡されているキー のマップを返す。"""
    rendering_map: dict[str, set[str]] = {}

    for py_file in src_dir.rglob("*.py"):
        content = py_file.read_text(encoding="utf-8")

        # Prompts.render("filename.md", {...}) のパターンを検索
        pattern = r'render\(\s*["\']([^"\']+\.md)["\']\s*,\s*\{([^}]+)\}'
        for match in re.finditer(pattern, content):
            prompt_name = match.group(1)
            keys_str = match.group(2)
            # キーを抽出: "key": value の key 部分
            keys = set(re.findall(r'"([a-z_]+)"\s*:', keys_str))
            if prompt_name not in rendering_map:
                rendering_map[prompt_name] = set()
            rendering_map[prompt_name].update(keys)

        # 単純な render("filename.md", {...}) のパターンも検索
        pattern2 = r'render\(\s*["\']([^"\']+\.md)["\']\s*,\s*\{'
        for match in re.finditer(pattern2, content):
            prompt_name = match.group(1)
            if prompt_name not in rendering_map:
                rendering_map[prompt_name] = set()

    return rendering_map


def validate_prompts(prompts_dir: Path, src_dir: Path) -> list[dict]:
    """プロンプトと実装の整合性を検証する。"""
    rendering_map = load_rendering_calls(src_dir)
    issues = []

    for md_file in sorted(prompts_dir.glob("*.md")):
        content = md_file.read_text(encoding="utf-8")
        placeholders = extract_placeholders(content)

        # {schema} は自動置換されるので除外
        placeholders.discard("schema")

        # 実装側で渡されているキーを取得
        implemented_keys = rendering_map.get(md_file.name, set())

        # 未置換プレースホルダを検出
        missing = placeholders - implemented_keys
        if missing:
            issues.append({
                "file": md_file.name,
                "type": "MISSING_PLACEHOLDER",
                "placeholders": sorted(missing),
                "implemented_keys": sorted(implemented_keys),
            })

        # 実装側で渡されていないキーを検出（プロンプトにないキー）
        extra = implemented_keys - placeholders
        if extra:
            issues.append({
                "file": md_file.name,
                "type": "EXTRA_KEY",
                "keys": sorted(extra),
            })

    return issues


def main():
    parser = argparse.ArgumentParser(description="Validate prompt placeholders against implementation")
    parser.add_argument("--prompts-dir", type=Path, default=Path("prompts"))
    parser.add_argument("--src-dir", type=Path, default=Path("src"))
    args = parser.parse_args()

    issues = validate_prompts(args.prompts_dir, args.src_dir)

    if not issues:
        print("✅ All prompt placeholders are consistent with implementation.")
        return 0

    print(f"❌ Found {len(issues)} issue(s):\n")
    for issue in issues:
        if issue["type"] == "MISSING_PLACEHOLDER":
            print(f"  ⚠️  {issue['file']}:")
            print(f"      Missing placeholders: {', '.join(issue['placeholders'])}")
            print(f"      Implemented keys: {', '.join(issue['implemented_keys'])}")
        elif issue["type"] == "EXTRA_KEY":
            print(f"  ℹ️  {issue['file']}:")
            print(f"      Extra keys in implementation: {', '.join(issue['keys'])}")
        print()

    return 1


if __name__ == "__main__":
    sys.exit(main())
