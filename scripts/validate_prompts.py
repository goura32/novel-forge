#!/usr/bin/env python3
"""
プロンプトテンプレートと実装のプレースホルダ整合性を検証するスクリプト。

使用方法:
    python scripts/validate_prompts.py
    python scripts/validate_prompts.py --prompts-dir /path/to/prompts --src-dir /path/to/src
"""

from __future__ import annotations

import argparse
import ast
import re
import sys
from pathlib import Path


def extract_placeholders(text: str) -> set[str]:
    """テキストから {placeholder} を抽出する。"""
    return set(re.findall(r"\{([a-z_]+)\}", text))


def _literal_prompt_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str) and node.value.endswith(".md"):
        return node.value
    return None


def _literal_dict_keys(node: ast.AST) -> set[str]:
    if not isinstance(node, ast.Dict):
        return set()
    keys: set[str] = set()
    for key in node.keys:
        if isinstance(key, ast.Constant) and isinstance(key.value, str):
            keys.add(key.value)
    return keys


def load_rendering_calls(src_dir: Path) -> dict[str, set[str]]:
    """ソースコードから render() 呼び出しを抽出し、プロンプト名 → 渡されているキー のマップを返す。"""
    rendering_map: dict[str, set[str]] = {}

    for py_file in src_dir.rglob("*.py"):
        try:
            tree = ast.parse(py_file.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if not isinstance(node.func, ast.Attribute) or node.func.attr != "render":
                continue
            if len(node.args) < 2:
                continue
            prompt_name = _literal_prompt_name(node.args[0])
            if prompt_name is None:
                continue
            rendering_map.setdefault(prompt_name, set()).update(_literal_dict_keys(node.args[1]))

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

        # 未使用テンプレートは将来用/手動用としてここでは警告対象にしない。
        if md_file.name not in rendering_map:
            continue

        implemented_keys = rendering_map[md_file.name]
        missing = placeholders - implemented_keys
        if missing:
            issues.append({
                "file": md_file.name,
                "type": "MISSING_PLACEHOLDER",
                "placeholders": sorted(missing),
                "implemented_keys": sorted(implemented_keys),
            })

        # 実装側の余剰キーは互換性維持や共通context渡しで意図的に使うため許容する。

    return issues


def main() -> int:
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
        print()

    return 1


if __name__ == "__main__":
    sys.exit(main())
