from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from novel_forge.models import (
    ProjectState,
    VolumeProgress,
    SceneRecord,
    VolumeOutline,
    SeriesPlan,
)
from novel_forge.storage import StateStorage, BlackboardStorage, BibleStorage
from novel_forge.ollama_client import LLMClient
from novel_forge.prompts import PromptManager, PromptLoader
from novel_forge.schemas import validate_or_raise
from novel_forge.quality import QualityGate


class NovelEngine:
    def __init__(
        self,
        workdir: Path,
        model: str = "qwen3.6:35b-a3b-mtp-q4_K_M",
        lang: str = "ja",
        llm_client: LLMClient | None = None,
        prompt_manager: PromptManager | None = None,
    ):
        self._workdir = workdir
        self._lang = lang
        self._storage = StateStorage(workdir)
        self._blackboard_storage = BlackboardStorage(workdir)
        self._bible_storage = BibleStorage(workdir)
        self._llm = llm_client or LLMClient(model=model)
        self._prompts = prompt_manager or PromptManager()
        self._quality = QualityGate()
        self._state = self._storage.load()

    @property
    def state(self) -> ProjectState:
        return self._state

    @property
    def workdir(self) -> Path:
        return self._workdir

    def _save(self) -> None:
        self._storage.save(self._state)

    def _current_volume(self) -> VolumeProgress:
        vol_num = self._state.current_volume
        for v in self._state.volumes:
            if v.volume_number == vol_num:
                return v
        vol = VolumeProgress(volume_number=vol_num)
        self._state.volumes.append(vol)
        return vol

    def _load_schema(self, name: str) -> dict[str, Any]:
        from novel_forge.schemas import get_schema
        return get_schema(name)

    # ── plan ──────────────────────────────────────────────────────────

    def plan(self, keywords: str) -> dict[str, Any]:
        system = self._prompts.render("system.md", {"lang": self._lang})
        user = self._prompts.render(
            "series_plan.md",
            {"keywords": keywords, "lang": self._lang},
        )
        schema = self._load_schema("series_plan")
        result = self._llm.complete_json("series_plan", system, user, schema)
        series_plan = SeriesPlan(**result)
        self._state.series_title = series_plan.title
        self._state.status = "planned"
        self._save()
        return result

    # ── outline ───────────────────────────────────────────────────────

    def outline(self, volume_number: int | None = None) -> dict[str, Any]:
        vol_num = volume_number or self._state.current_volume
        system = self._prompts.render("system.md", {"lang": self._lang})
        series_plan = self._get_series_plan_summary()
        user = self._prompts.render(
            "volume_outline.md",
            {
                "series_plan": series_plan,
                "volume_number": str(vol_num),
                "genre": str(self._state.volumes[0].volume_number) if self._state.volumes else "fantasy",
                "lang": self._lang,
            },
        )
        schema = self._load_schema("volume_outline")
        result = self._llm.complete_json("volume_outline", system, user, schema)
        outline = VolumeOutline(**result)
        vol = self._current_volume()
        vol.status = "outlined"
        self._state.status = "outlined"
        self._save_path(vol_num, "outline.json", result)
        self._save()
        return result

    # ── write ─────────────────────────────────────────────────────────

    def write(self, volume_number: int | None = None) -> list[dict[str, Any]]:
        vol_num = volume_number or self._state.current_volume
        outline_data = self._load_path(vol_num, "outline.json")
        outline = VolumeOutline(**outline_data)
        vol = self._current_volume()
        results = []
        for chapter in outline.chapters:
            for scene in chapter.scenes:
                record = self._get_or_create_scene_record(vol, scene.number)
                if record.status in ("revised", "force_exported"):
                    continue
                result = self._write_scene(outline, chapter, scene, record)
                results.append(result)
        vol.status = "drafted"
        self._state.status = "drafting"
        self._save()
        return results

    def _write_scene(self, outline, chapter, scene, record) -> dict[str, Any]:
        system = self._prompts.render("system.md", {"lang": self._lang})
        context = self._build_context()
        continuity = self._build_continuity(record.scene_number)
        user = self._prompts.render(
            "scene_draft.md",
            {
                "series_plan": self._get_series_plan_summary(),
                "outline": outline.model_dump_json(),
                "scene": scene.model_dump_json(),
                "context": context,
                "continuity": continuity,
                "lang": self._lang,
            },
        )
        draft = self._llm.complete_json("scene_draft", system, user)
        record.status = "drafted"
        record.quality_retries = 0
        self._save()
        return {"scene_number": record.scene_number, "status": record.status}

    # ── export ────────────────────────────────────────────────────────

    def export(self, volume_number: int | None = None) -> dict[str, Any]:
        vol_num = volume_number or self._state.current_volume
        vol = self._current_volume()
        self._finalize_bible()
        manuscript = self._assemble_manuscript(vol_num)
        metadata = self._generate_kdp_metadata(vol_num)
        report = self._generate_readiness_report(vol_num)
        vol.status = "exported"
        if any(s.status == "force_exported" for s in vol.scenes):
            vol.status = "force_exported"
        self._state.status = vol.status
        self._save()
        return {
            "manuscript_path": str(self._workdir / "exports" / "manuscript.md"),
            "metadata_path": str(self._workdir / "exports" / "metadata.json"),
            "report_path": str(self._workdir / "exports" / "kdp_readiness_report.md"),
        }

    # ── resume ────────────────────────────────────────────────────────

    def resume(self) -> dict[str, Any]:
        if self._state.status == "planned":
            return {"action": "plan", "status": self._state.status}
        elif self._state.status == "outlined":
            return {"action": "outline", "status": self._state.status}
        elif self._state.status in ("drafting", "drafted"):
            return {"action": "write", "status": self._state.status}
        elif self._state.status in ("exported", "force_exported"):
            return {"action": "export", "status": self._state.status}
        return {"action": "plan", "status": self._state.status}

    # ── status ────────────────────────────────────────────────────────

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
            "scenes_revised": sum(1 for s in vol.scenes if s.status == "revised"),
            "scenes_force_exported": sum(
                1 for s in vol.scenes if s.status == "force_exported"
            ),
        }

    # ── helpers ───────────────────────────────────────────────────────

    def _get_series_plan_summary(self) -> str:
        plan_path = self._workdir / ".novel-forge" / "series_plan.json"
        if plan_path.exists():
            data = json.loads(plan_path.read_text(encoding="utf-8"))
            return json.dumps(data, ensure_ascii=False)
        return "{}"

    def _build_context(self) -> str:
        bb = self._blackboard_storage.load()
        bible = self._bible_storage.load()
        parts = []
        if bb.facts:
            parts.append("## 事実記録\n" + "\n".join(
                f"- {f.subject} {f.predicate} {f.object}" for f in bb.facts[-20:]
            ))
        if bible.characters:
            parts.append("## キャラクター\n" + "\n".join(
                f"- {c.name}: {c.personality}" for c in bible.characters
            ))
        return "\n\n".join(parts)

    def _build_continuity(self, scene_number: int) -> str:
        bb = self._blackboard_storage.load()
        prev_key = str(scene_number - 1)
        summary = bb.scene_summaries.get(prev_key, "")
        notes = "\n".join(bb.continuity_notes[-5:]) if bb.continuity_notes else ""
        parts = []
        if summary:
            parts.append(f"## 前シーン要約\n{summary}")
        if notes:
            parts.append(f"## 引き継ぎメモ\n{notes}")
        return "\n\n".join(parts) if parts else "（最初のシーン）"

    def _get_or_create_scene_record(
        self, vol: VolumeProgress, scene_number: int
    ) -> SceneRecord:
        for s in vol.scenes:
            if s.scene_number == scene_number:
                return s
        record = SceneRecord(scene_number=scene_number)
        vol.scenes.append(record)
        return record

    def _save_path(self, vol_num: int, filename: str, data: Any) -> None:
        path = self._workdir / ".novel-forge" / "volumes" / f"vol{vol_num:02d}" / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        content = json.dumps(data, ensure_ascii=False, indent=2) if isinstance(data, dict) else str(data)
        path.write_text(content, encoding="utf-8")

    def _load_path(self, vol_num: int, filename: str) -> dict:
        path = self._workdir / ".novel-forge" / "volumes" / f"vol{vol_num:02d}" / filename
        return json.loads(path.read_text(encoding="utf-8"))

    def _finalize_bible(self) -> None:
        pass

    def _assemble_manuscript(self, vol_num: int) -> str:
        export_dir = self._workdir / "exports"
        export_dir.mkdir(parents=True, exist_ok=True)
        chapters = []
        vol_dir = self._workdir / ".novel-forge" / "volumes" / f"vol{vol_num:02d}"
        for ch_path in sorted(vol_dir.glob("chapters/ch*.md")):
            chapters.append(ch_path.read_text(encoding="utf-8"))
        manuscript = "\n\n---\n\n".join(chapters)
        (export_dir / "manuscript.md").write_text(manuscript, encoding="utf-8")
        return manuscript

    def _generate_kdp_metadata(self, vol_num: int) -> dict[str, Any]:
        export_dir = self._workdir / "exports"
        export_dir.mkdir(parents=True, exist_ok=True)
        metadata = {
            "title": self._state.series_title,
            "volume": vol_num,
            "language": self._lang,
        }
        (export_dir / "metadata.json").write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return metadata

    def _generate_readiness_report(self, vol_num: int) -> str:
        export_dir = self._workdir / "exports"
        export_dir.mkdir(parents=True, exist_ok=True)
        vol = self._current_volume()
        force_count = sum(1 for s in vol.scenes if s.status == "force_exported")
        lines = [
            "# KDP 準備完了レポート",
            f"",
            f"## サマリー",
            f"- シリーズ: {self._state.series_title}",
            f"- 巻: {vol_num}",
            f"- ステータス: {vol.status}",
            f"- 総シーン数: {len(vol.scenes)}",
            f"- 完了シーン: {sum(1 for s in vol.scenes if s.status == 'revised')}",
            f"- force_exported シーン: {force_count}",
        ]
        if force_count > 0:
            lines.extend(["", "## ⚠️ 警告", "以下のシーンは品質ゲート3回不合格のまま出力されています:"])
            for s in vol.scenes:
                if s.status == "force_exported":
                    lines.append(f"- シーン {s.scene_number}")
        report = "\n".join(lines)
        (export_dir / "kdp_readiness_report.md").write_text(report, encoding="utf-8")
        return report
