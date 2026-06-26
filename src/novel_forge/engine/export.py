"""Export, resume, status — export, resume, status, _assemble_manuscript, _generate_kdp_metadata, _generate_readiness_report."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from novel_forge.engine.base import NovelEngineBase
else:
    NovelEngineBase = object

_SLUG_DEFAULT = "vol"


class ExportMixin(NovelEngineBase):  # type: ignore[misc]
    """Export, resume, status methods for NovelEngine."""

    def export(self, volume_number: int | None = None) -> dict[str, Any]:
        vol_num = volume_number or self._state.current_volume
        self._state.current_volume = vol_num
        slug = getattr(self, "_slug", "?")
        self._log.info(f"Export started: volume={vol_num} slug='{slug}'")
        vol = self._current_volume()

        bb = self._bb_storage.load()
        self._bible_mgr.finalize(bb.continuity_notes)

        manuscript = self._assemble_manuscript(vol_num)
        metadata = self._generate_kdp_metadata(vol_num)
        report = self._generate_readiness_report(vol_num)

        vol.status = "出力済"
        if any(s.status == "強制出力済" for s in vol.scenes):
            vol.status = "強制出力済"
        self._state.status = vol.status
        self._save()

        exports_dir = self._series_dir / "exports"
        exports_dir.mkdir(parents=True, exist_ok=True)
        self._log.info(f"✓ Export: series='{vol_num}")
        return {
            "manuscript_path": str(exports_dir / f"{slug}_vol{vol_num:02d}.md"),
            "metadata_path": str(exports_dir / f"{slug}_vol{vol_num:02d}_metadata.json"),
            "report_path": str(exports_dir / f"{slug}_vol{vol_num:02d}_kdp_readiness_report.md"),
        }

    def _write_export(self, filename: str, content: str) -> None:
        exports_dir = self._series_dir / "exports"
        exports_dir.mkdir(parents=True, exist_ok=True)
        (exports_dir / filename).write_text(content, encoding="utf-8")

    def resume(self) -> dict[str, Any]:
        vol = self._current_volume()
        if vol.status in ("執筆中", "初稿済"):
            return {"action": "write", "status": vol.status}
        if self._state.status == "計画中":
            return {"action": "plan", "status": self._state.status}
        if self._state.status == "デザイン済":
            return {"action": "design", "status": self._state.status}
        if self._state.status in ("出力済", "強制出力済"):
            return {"action": "export", "status": self._state.status}
        return {"action": "plan", "status": self._state.status}

    def status(self) -> dict[str, Any]:
        vol = self._current_volume()
        return {
            "series_title": self._state.series_title,
            "status": self._state.status,
            "current_volume": self._state.current_volume,
            "volume_status": vol.status,
            "word_count": vol.word_count,
            "target_word_count": vol.target_word_count,
            "scenes_total": len(vol.scenes),
            "scenes_revised": sum(1 for s in vol.scenes if s.status == "修正済"),
            "scenes_force_exported": sum(
                1 for s in vol.scenes if s.status == "強制出力済"
            ),
        }

    def _assemble_manuscript(self, vol_num: int) -> str:
        chapters = []
        vol_dir = self._series_dir / f"vol{vol_num:02d}"
        chapter_files = sorted(
            p for p in vol_dir.glob("vol*_ch*/*.md")
            if p.stem == p.parent.name
        )
        for ch_path in chapter_files:
            chapters.append(ch_path.read_text(encoding="utf-8"))
        manuscript = "\n\n---\n\n".join(chapters)
        slug = getattr(self, "_slug", _SLUG_DEFAULT)
        self._write_export(f"{slug}_vol{vol_num:02d}.md", manuscript)
        return manuscript

    def _generate_kdp_metadata(self, vol_num: int) -> dict[str, Any]:
        plan_path = self._series_dir / "series_plan.json"
        title = self._state.series_title
        if plan_path.exists():
            plan = json.loads(plan_path.read_text(encoding="utf-8"))
            title = plan.get("title", title)
        metadata = {
            "title": title,
            "volume": vol_num,
            "language": self._lang,
        }
        slug = getattr(self, "_slug", _SLUG_DEFAULT)
        self._write_export(
            f"{slug}_vol{vol_num:02d}_metadata.json",
            json.dumps(metadata, ensure_ascii=False, indent=2),
        )
        return metadata

    def _generate_readiness_report(self, vol_num: int) -> str:
        vol = self._current_volume()
        force_count = sum(1 for s in vol.scenes if s.status == "強制出力済")
        revised_count = sum(1 for s in vol.scenes if s.status == "修正済")
        lines = [
            "# KDP 準備完了レポート",
            "",
            "## サマリー",
            f"- シリーズ: {self._state.series_title}",
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

        unresolved = self._bible_mgr.get_unresolved_foreshadowing()
        if unresolved:
            lines.extend(["", "## ⚠️ 未回収伏線"])
            for fh in unresolved:
                lines.append(f"- {fh.description}")

        incomplete_sp = self._bible_mgr.get_incomplete_subplots()
        if incomplete_sp:
            lines.extend(["", "## ⚠️ 未完了サブプロット"])
            for sp in incomplete_sp:
                lines.append(
                    f"- [{sp.status}] {sp.name}: {sp.progress_note or '進捗なし'}"
                )

        lines.extend(["", "## 提出前確認事項"])
        lines.append("- [ ] 表紙画像の準備")
        lines.append("- [ ] 商品説明文の最終確認")
        lines.append("- [ ] キーワード・カテゴリの確認")

        report = "\n".join(lines)
        slug = getattr(self, "_slug", _SLUG_DEFAULT)
        self._write_export(f"{slug}_vol{vol_num:02d}_kdp_readiness_report.md", report)
        return report
