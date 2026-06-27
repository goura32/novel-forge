"""Export, resume, status — export, resume, status methods for NovelEngine.

Standalone functions that accept NovelEngine as first argument.
No mixin classes.
"""

from __future__ import annotations

import json
from typing import Any

_SLUG_DEFAULT = "vol"


def export(engine, volume_number: int | None = None) -> dict[str, Any]:
    """Export manuscript for KDP."""
    vol_num = volume_number or engine.state.current_volume
    engine.state.current_volume = vol_num
    slug = getattr(engine, "_slug", "?")
    engine._log.info(f"Export started: volume={vol_num} slug='{slug}'")
    vol = engine._current_volume()

    bb = engine._bb_storage.load()
    engine._bible_mgr.finalize(bb.continuity_notes)

    _assemble_manuscript(engine, vol_num)
    _generate_kdp_metadata(engine, vol_num)
    _generate_readiness_report(engine, vol_num)

    vol.status = "出力済"
    if any(s.status == "強制出力済" for s in vol.scenes):
        vol.status = "強制出力済"
    engine._state.status = vol.status
    engine._save()

    exports_dir = engine._series_dir / "exports"
    exports_dir.mkdir(parents=True, exist_ok=True)
    engine._log.info(f"✓ Export: series='{vol_num}")
    return {
        "manuscript_path": str(exports_dir / f"{slug}_vol{vol_num:02d}.md"),
        "metadata_path": str(exports_dir / f"{slug}_vol{vol_num:02d}_metadata.json"),
        "report_path": str(exports_dir / f"{slug}_vol{vol_num:02d}_kdp_readiness_report.md"),
    }


def _write_export(engine, filename: str, content: str) -> None:
    exports_dir = engine._series_dir / "exports"
    exports_dir.mkdir(parents=True, exist_ok=True)
    (exports_dir / filename).write_text(content, encoding="utf-8")


def resume(engine) -> dict[str, Any]:
    """Resume from the last interrupted phase."""
    vol = engine._current_volume()
    if vol.status in ("執筆中", "初稿済"):
        return {"action": "write", "status": vol.status}
    if engine._state.status == "計画中":
        return {"action": "plan", "status": engine._state.status}
    if engine._state.status == "デザイン済":
        return {"action": "design", "status": engine._state.status}
    if engine._state.status in ("出力済", "強制出力済"):
        return {"action": "export", "status": engine._state.status}
    return {"action": "plan", "status": engine._state.status}


def status(engine) -> dict[str, Any]:
    """Show current project status."""
    vol = engine._current_volume()
    return {
        "series_title": engine._state.series_title,
        "status": engine._state.status,
        "current_volume": engine._state.current_volume,
        "volume_status": vol.status,
        "word_count": vol.word_count,
        "target_word_count": vol.target_word_count,
        "scenes_total": len(vol.scenes),
        "scenes_revised": sum(1 for s in vol.scenes if s.status == "修正済"),
        "scenes_force_exported": sum(1 for s in vol.scenes if s.status == "強制出力済"),
    }


def _assemble_manuscript(engine, vol_num: int) -> str:
    chapters = []
    vol_dir = engine._series_dir / f"vol{vol_num:02d}"
    chapter_files = sorted(p for p in vol_dir.glob("vol*_ch*/*.md") if p.stem == p.parent.name)
    for ch_path in chapter_files:
        chapters.append(ch_path.read_text(encoding="utf-8"))
    manuscript = "\n\n---\n\n".join(chapters)
    slug = getattr(engine, "_slug", _SLUG_DEFAULT)
    _write_export(engine, f"{slug}_vol{vol_num:02d}.md", manuscript)
    return manuscript


def _generate_kdp_metadata(engine, vol_num: int) -> dict[str, Any]:
    plan_path = engine._series_dir / "series_plan.json"
    title = engine._state.series_title
    if plan_path.exists():
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
        title = plan.get("title", title)
    metadata = {
        "title": title,
        "volume": vol_num,
        "language": engine._lang,
    }
    slug = getattr(engine, "_slug", _SLUG_DEFAULT)
    _write_export(
        engine,
        f"{slug}_vol{vol_num:02d}_metadata.json",
        json.dumps(metadata, ensure_ascii=False, indent=2),
    )
    return metadata


def _generate_readiness_report(engine, vol_num: int) -> str:
    vol = engine._current_volume()
    force_count = sum(1 for s in vol.scenes if s.status == "強制出力済")
    revised_count = sum(1 for s in vol.scenes if s.status == "修正済")
    lines = [
        "# KDP 準備完了レポート",
        "",
        "## サマリー",
        f"- シリーズ: {engine._state.series_title}",
        f"- 巻: {vol_num}",
        f"- ステータス: {vol.status}",
        f"- 総シーン数: {len(vol.scenes)}",
        f"- 完了シーン: {revised_count}",
        f"- force_exported シーン: {force_count}",
    ]
    if force_count > 0:
        lines.extend([
            "",
            "## ⚠️ 警告",
            "以下のシーンは品質ゲート不合格のまま出力されています:",
        ])
        for s in vol.scenes:
            if s.status == "強制出力済":
                lines.append(f"- シーン {s.scene_number}")

    unresolved = engine._bible_mgr.get_unresolved_foreshadowing()
    if unresolved:
        lines.extend(["", "## ⚠️ 未回収伏線"])
        for fh in unresolved:
            lines.append(f"- {fh.description}")

    incomplete_sp = engine._bible_mgr.get_incomplete_subplots()
    if incomplete_sp:
        lines.extend(["", "## ⚠️ 未完了サブプロット"])
        for sp in incomplete_sp:
            lines.append(f"- [{sp.status}] {sp.name}: {sp.progress_note or '進捗なし'}")

    lines.extend(["", "## 提出前確認事項"])
    lines.append("- [ ] 表紙画像の準備")
    lines.append("- [ ] 商品説明文の最終確認")
    lines.append("- [ ] キーワード・カテゴリの確認")

    report = "\n".join(lines)
    slug = getattr(engine, "_slug", _SLUG_DEFAULT)
    _write_export(engine, f"{slug}_vol{vol_num:02d}_kdp_readiness_report.md", report)
    return report
