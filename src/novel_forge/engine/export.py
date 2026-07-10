"""Export, resume, status — export, resume, status methods for NovelEngine.

Standalone functions that accept NovelEngine as first argument.
No mixin classes.
"""

from __future__ import annotations

import json
from typing import Any, cast

from novel_forge.canon.store import CanonEventStore
from novel_forge.semantic_validators import validate_volume_design_semantics

_SLUG_DEFAULT = "vol"


def export(engine, volume_number: int | None = None) -> dict[str, Any]:
    """Export manuscript for KDP."""
    vol_num = volume_number or engine.state.current_volume
    engine.state.current_volume = vol_num
    slug = getattr(engine, "_slug", "?")
    engine._log.info(f"Export started: volume={vol_num} slug='{slug}'")
    vol = engine._current_volume()

    # NOTE: Bible は design 段階で更新済。export は bible を参照・更新しない
    # （runtime discovery 禁止の原則）。未回収伏線・未完サブプロットは
    # v2 Canon（canon/ 配下の event-sourced store）から回収して読む。

    _export_preflight(engine, vol_num)
    _assemble_manuscript(engine, vol_num)
    _generate_kdp_metadata(engine, vol_num)
    _generate_readiness_report(engine, vol_num)

    vol.status = "出力済"
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


def _export_preflight(engine, vol_num: int) -> None:
    """Validate volume artifacts before writing KDP export files."""
    errors: list[str] = []
    vol = engine._current_volume()

    incomplete = [
        s.scene_number
        for s in vol.scenes
        if s.status not in ("修正済", "強制出力済")
    ]
    if incomplete:
        errors.append(
            "incomplete scenes: " + ", ".join(str(n) for n in sorted(incomplete))
        )

    try:
        design_data = engine._load_path(vol_num, f"vol{vol_num:02d}.json")
    except FileNotFoundError:
        errors.append(f"missing volume design: vol{vol_num:02d}.json")
        design_data = {}

    expected_scenes = _expected_scene_refs(design_data)
    errors.extend(validate_volume_design_semantics(design_data))
    if not expected_scenes:
        errors.append("volume design has no scenes")

    for chapter_number, scene_number in expected_scenes:
        scene_text = _read_scene_draft(engine, vol_num, chapter_number, scene_number)
        if scene_text is None:
            errors.append(
                f"missing scene draft: vol{vol_num:02d}_ch{chapter_number:02d}_sc{scene_number:02d}"
            )
            continue
        if not scene_text.strip():
            errors.append(
                f"empty scene draft: vol{vol_num:02d}_ch{chapter_number:02d}_sc{scene_number:02d}"
            )

    if errors:
        raise ValueError("Export preflight failed: " + "; ".join(errors))


def resume(engine) -> dict[str, Any]:
    """Resume from the last interrupted phase."""
    vol = engine._current_volume()
    if vol.status in ("執筆中", "初稿済"):
        return {"action": "write", "status": vol.status}
    if engine._state.status == "計画中":
        return {"action": "plan", "status": engine._state.status}
    if engine._state.status in ("企画済", "デザイン済"):
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
    chapters: list[str] = []
    design_data = engine._load_path(vol_num, f"vol{vol_num:02d}.json")
    scenes_by_chapter: dict[int, list[str]] = {}
    for chapter_number, scene_number in _expected_scene_refs(design_data):
        scene_text = _read_scene_draft(engine, vol_num, chapter_number, scene_number)
        if scene_text is None:
            continue
        scenes_by_chapter.setdefault(chapter_number, []).append(scene_text)
    for chapter_number in sorted(scenes_by_chapter):
        chapters.append("\n\n".join(scenes_by_chapter[chapter_number]))
    manuscript = "\n\n---\n\n".join(chapters)
    slug = getattr(engine, "_slug", _SLUG_DEFAULT)
    _write_export(engine, f"{slug}_vol{vol_num:02d}.md", manuscript)
    return manuscript


def _expected_scene_refs(design_data: dict[str, Any]) -> list[tuple[int, int]]:
    """Return (chapter_number, scene_number) pairs from volume design."""
    refs: set[tuple[int, int]] = set()
    for scene in design_data.get("scenes", []):
        scene_number = scene.get("number") or scene.get("scene_number")
        chapter_number = scene.get("chapter_number")
        if (
            isinstance(chapter_number, int)
            and isinstance(scene_number, int)
            and chapter_number > 0
            and scene_number > 0
        ):
            refs.add((chapter_number, scene_number))
    if refs:
        return sorted(refs)

    for chapter in design_data.get("chapters", []):
        chapter_number = chapter.get("number")
        if not isinstance(chapter_number, int) or chapter_number <= 0:
            continue
        for scene in chapter.get("scenes", []):
            scene_number = scene.get("number") or scene.get("scene_number")
            if isinstance(scene_number, int) and scene_number > 0:
                refs.add((chapter_number, scene_number))
    return sorted(refs)


def _read_scene_draft(
    engine, vol_num: int, chapter_number: int, scene_number: int
) -> str | None:
    ch_dir = engine._series_dir / f"vol{vol_num:02d}" / f"vol{vol_num:02d}_ch{chapter_number:02d}"
    candidates = sorted(
        ch_dir.glob(f"vol{vol_num:02d}_ch{chapter_number:02d}_sc{scene_number:02d}_v*.md")
    )
    if candidates:
        return cast(str, candidates[-1].read_text(encoding="utf-8"))
    plain = ch_dir / f"vol{vol_num:02d}_ch{chapter_number:02d}_sc{scene_number:02d}.md"
    if plain.exists():
        return cast(str, plain.read_text(encoding="utf-8"))
    return None


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


def _final_review_issues(scene: Any) -> list[dict[str, Any]]:
    """Return persisted final-review issues in a stable, report-safe shape."""
    quality_gate = getattr(scene, "quality_gate", {})
    raw_issues = (
        quality_gate.get("issues", [])
        if isinstance(quality_gate, dict)
        else getattr(quality_gate, "issues", [])
    )
    if not isinstance(raw_issues, list):
        return []
    return [issue for issue in raw_issues if isinstance(issue, dict)]


def _report_series_title(engine) -> str:
    """Use the planned title when state has not been populated yet."""
    title = str(engine._state.series_title or "")
    plan_path = engine._series_dir / "series_plan.json"
    if plan_path.exists():
        try:
            plan = json.loads(plan_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            plan = {}
        planned_title = plan.get("title") if isinstance(plan, dict) else None
        if isinstance(planned_title, str) and planned_title.strip():
            title = planned_title
    return title or "（シリーズ名未設定）"


def _generate_readiness_report(engine, vol_num: int) -> str:
    """Write a human-review report; it deliberately makes no publication decision."""
    vol = engine._current_volume()
    scene_issues = [(scene, _final_review_issues(scene)) for scene in vol.scenes]
    scenes_with_issues = sum(1 for _, issues in scene_issues if issues)
    issue_total = sum(len(issues) for _, issues in scene_issues)
    slug = getattr(engine, "_slug", _SLUG_DEFAULT)
    manuscript_path = engine._series_dir / "exports" / f"{slug}_vol{vol_num:02d}.md"

    lines = [
        "# KDP 人間確認レポート",
        "",
        "> このレポートは機械的な合否判定を行いません。最終的な出版判断は、原稿と各シーンの最終レビュー指摘事項を人が確認して行います。",
        "",
        "## 確認対象",
        f"- 原稿: `{manuscript_path}`",
        f"- シリーズ: {_report_series_title(engine)}",
        f"- 巻: {vol_num}",
        f"- 総シーン数: {len(vol.scenes)}",
        f"- 最終レビュー指摘あり: {scenes_with_issues} シーン",
        f"- 最終レビュー指摘総数: {issue_total} 件",
        "",
        "## 各シーンの最終レビュー指摘事項",
    ]
    for scene, issues in scene_issues:
        if not issues:
            lines.extend(["", f"### シーン {scene.scene_number} — 指摘なし"])
            continue
        lines.extend(["", f"### シーン {scene.scene_number} — 指摘 {len(issues)}件"])
        for issue in issues:
            severity = str(issue.get("severity") or "未分類")
            field = str(issue.get("field") or "未分類")
            description = str(issue.get("description") or "内容なし")
            suggestion = str(issue.get("suggestion") or "")
            lines.append(f"- **{severity}** · `{field}`")
            lines.append(f"  - 内容: {description}")
            if suggestion:
                lines.append(f"  - 対応案: {suggestion}")

    # NOTE: recover() regenerates the materialized canon/bible.json cache if its
    # digest mismatches the replayed seed+events. This is a cache-repair side
    # effect only — export() never mutates the Canon (no events written).
    canon_store = CanonEventStore(engine._series_dir / "canon")
    canon = canon_store.recover()
    unresolved = [fh for fh in canon.foreshadowing if fh.status == "planted"]
    if unresolved:
        lines.extend(["", "## 未回収伏線（人間確認）"])
        for fh in unresolved:
            lines.append(f"- {fh.description}")

    incomplete_sp = [sp for sp in canon.subplots if sp.status == "active"]
    if incomplete_sp:
        lines.extend(["", "## 未完了サブプロット（人間確認）"])
        for sp in incomplete_sp:
            lines.append(f"- [{sp.status}] {sp.name}: {sp.current_state or '進捗なし'}")

    lines.extend(["", "## 提出前確認事項"])
    lines.append("- [ ] 原稿と最終レビュー指摘事項を確認")
    lines.append("- [ ] 表紙画像の準備")
    lines.append("- [ ] 商品説明文の最終確認")
    lines.append("- [ ] キーワード・カテゴリの確認")

    report = "\n".join(lines)
    _write_export(engine, f"{slug}_vol{vol_num:02d}_kdp_readiness_report.md", report)
    return report
