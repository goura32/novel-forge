#!/usr/bin/env python3
"""Quick quality check for a novel-forge output directory."""
import json
import sys
from pathlib import Path


def check_series(series_dir: Path):
    print(f"=== {series_dir.name} ===\n")

    # Series plan
    plan_path = series_dir / "series_plan.json"
    if plan_path.exists():
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
        print(f"タイトル: {plan.get('title', 'N/A')}")
        print(f"slug: {plan.get('slug', 'N/A')}")
        print(f"ジャンル: {plan.get('genre', [])}")
        print(f"巻数: {len(plan.get('planned_volumes', []))}")
        print(f"キャラクター数: {len(plan.get('main_characters', []))}")
    else:
        print("series_plan.json が見つかりません")
        return

    # Volumes
    for vol_dir in sorted(series_dir.glob("vol*")):
        if not vol_dir.is_dir():
            continue
        print(f"\n--- {vol_dir.name} ---")

        # Outline
        outline_path = vol_dir / "outline.json"
        if outline_path.exists():
            outline = json.loads(outline_path.read_text(encoding="utf-8"))
            print(f"  タイトル: {outline.get('title', 'N/A')}")
            print(f"  前提: {outline.get('premise', 'N/A')[:80]}...")
            print(f"  章数: {len(outline.get('chapters', []))}")
            print(f"  シーン数: {len(outline.get('scenes', []))}")
            for ch in outline.get("chapters", []):
                ch_scenes = [s for s in outline.get("scenes", []) if s.get("chapter_number") == ch["number"]]
                print(f"    Ch{ch['number']}: {ch['title']} ({ch.get('purpose', '?')}) - {len(ch_scenes)}シーン")
        else:
            print("  outline.json が見つかりません")

        # Scene drafts
        scene_files = sorted(vol_dir.glob("**/*_sc*.md"))
        print(f"  シーンファイル数: {len(scene_files)}")
        for sf in scene_files:
            text = sf.read_text(encoding="utf-8")
            # Check for English words
            import re
            english_words = re.findall(r'\b[a-zA-Z]{3,}\b', text)
            # Filter allowed technical terms
            allowed = {'CPU', 'GPU', 'SSD', 'USB', 'URL', 'HTML', 'RAM', 'ROM', 'DNS', 'VPN', 'SSH', 'FTP', 'API', 'SDK', 'LAN', 'WAN', 'GPS', 'LED', 'LCD', 'OLED', 'DNA', 'RNA', 'CT', 'MRI', 'IoT', 'PC', 'AI', 'ICU'}
            disallowed = [w for w in english_words if w not in allowed and len(w) > 3]
            if disallowed:
                print(f"    ⚠ {sf.name}: 英語混入の可能性: {disallowed[:5]}")

    # Exports
    exports_dir = series_dir.parent / "exports"
    if not exports_dir.exists():
        exports_dir = series_dir / "exports"
    if exports_dir.exists():
        print("\n--- 出力ファイル ---")
        for f in sorted(exports_dir.iterdir()):
            print(f"  {f.name} ({f.stat().st_size:,} bytes)")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        check_series(Path(sys.argv[1]))
    else:
        # Find most recent series dir
        base = Path("/mnt/hdd/novel")
        series_dirs = sorted(base.glob("2026*/"), reverse=True)
        if series_dirs:
            check_series(series_dirs[0])
        else:
            print("シリーズディレクトリが見つかりません")
