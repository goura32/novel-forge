"""NovelForge engine — orchestration layer.

Coordinates plan → outline → write → export pipeline.
Delegates scene writing to SceneWriter, context building to ContextBuilder,
and Bible management to BibleManager.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from novel_forge.bible_manager import BibleManager
from novel_forge.context_builder import ContextBuilder
from novel_forge.models import (
    ProjectState,
    VolumeProgress,
    SceneRecord,
    VolumeOutline,
)
from novel_forge.ollama_client import LLMClient, load_config
from novel_forge.prompts import PromptManager
from novel_forge.quality import QualityGate
from novel_forge.schemas import get_schema
from novel_forge.scene_writer import SceneWriter
from novel_forge.storage import StateStorage, BlackboardStorage, BibleStorage


class NovelEngine:
    def __init__(
        self,
        workdir: Path,
        model: str = "qwen3.6:35b-a3b-mtp-q4_K_M",
        lang: str = "ja",
        llm_client: LLMClient | None = None,
        prompt_manager: PromptManager | None = None,
        config: dict[str, Any] | None = None,
    ):
        self._workdir = workdir
        self._lang = lang
        self._storage = StateStorage(workdir)
        self._bb_storage = BlackboardStorage(workdir)
        self._bible_storage = BibleStorage(workdir)

        cfg = config if config is not None else load_config()
        if llm_client is None:
            llm_cfg = cfg.get("llm", {})
            model = llm_cfg.get("model", model)
            timeout = llm_cfg.get("timeout_seconds", 600)
            max_retries = llm_cfg.get("max_retries", 2)
            num_predict = llm_cfg.get("num_predict", 65536)
            num_ctx = llm_cfg.get("num_ctx", None)
            host = llm_cfg.get("ollama_host", None)
            if host:
                import os
                os.environ["OLLAMA_HOST"] = host
            llm_client = LLMClient(
                model=model,
                raw_log_dir=workdir / ".novel-forge" / "raw_logs",
                timeout_seconds=timeout,
                max_retries=max_retries,
                num_predict=num_predict,
                num_ctx=num_ctx,
                ollama_options=llm_cfg.get("ollama_options"),
            )
        self._llm = llm_client
        self._prompts = prompt_manager or PromptManager()
        self._quality = QualityGate()
        self._state = self._storage.load()

        # Sub-components
        self._ctx_builder = ContextBuilder(workdir, self._bb_storage, self._bible_storage)
        self._bible_mgr = BibleManager(self._bible_storage)
        self._scene_writer = SceneWriter(
            workdir, self._llm, self._prompts, self._quality,
            self._bb_storage, self._bible_storage,
        )

    @property
    def state(self) -> ProjectState:
        return self._state

    @property
    def workdir(self) -> Path:
        return self._workdir

    # ── helpers ───────────────────────────────────────────────────────

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

    def _save_path(self, vol_num: int, filename: str, data: Any) -> None:
        if vol_num == 0:
            path = self._workdir / ".novel-forge" / filename
        else:
            path = self._workdir / ".novel-forge" / "volumes" / f"vol{vol_num:02d}" / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        content = (
            json.dumps(data, ensure_ascii=False, indent=2)
            if isinstance(data, dict)
            else str(data)
        )
        path.write_text(content, encoding="utf-8")

    def _load_path(self, vol_num: int, filename: str) -> dict:
        path = self._workdir / ".novel-forge" / "volumes" / f"vol{vol_num:02d}" / filename
        return json.loads(path.read_text(encoding="utf-8"))

    def _get_or_create_scene_record(
        self, vol: VolumeProgress, scene_number: int
    ) -> SceneRecord:
        for s in vol.scenes:
            if s.scene_number == scene_number:
                return s
        record = SceneRecord(scene_number=scene_number)
        vol.scenes.append(record)
        return record

    # ── plan ──────────────────────────────────────────────────────────

    def plan(self, keywords: str) -> dict[str, Any]:
        system = self._prompts.render("system.md", {"lang": self._lang})
        user = self._prompts.render(
            "series_plan.md",
            {"keywords": keywords, "lang": self._lang},
        )
        schema = get_schema("series_plan")
        result = self._llm.complete_json("series_plan", system, user, schema)

        if result.get("slug") and len(result["slug"]) > 256:
            result["slug"] = result["slug"][:256].rstrip("-")

        for i, vol in enumerate(result.get("planned_volumes", []), 1):
            vol["number"] = i

        review = self._review_series_plan(result)

        self._state.series_title = result.get("title", "")
        self._state.status = "計画中"
        self._save_path(0, "series_plan.json", result)
        self._save_path(0, "series_plan_review.json", review)
        self._save()
        return result

    def _review_series_plan(self, plan: dict[str, Any]) -> dict[str, Any]:
        system = self._prompts.render("system.md", {"lang": self._lang})
        filtered = {
            "title": plan.get("title", ""),
            "logline": plan.get("logline", ""),
            "genre": plan.get("genre", ""),
            "target_audience": plan.get("target_audience", ""),
            "themes": plan.get("themes", []),
            "selling_points": plan.get("selling_points", []),
            "world_summary": plan.get("world", {}).get("summary", ""),
            "world_rules": plan.get("world", {}).get("rules", []),
            "main_characters": [
                {"name": c.get("name", ""), "arc": c.get("arc", "")}
                for c in plan.get("main_characters", [])
            ],
            "planned_volumes": [
                {"title": v.get("title", ""), "premise": v.get("premise", "")}
                for v in plan.get("planned_volumes", [])
            ],
        }
        lines = [
            f"タイトル: {filtered['title']}",
            f"あらすじ: {filtered['logline']}",
            f"ジャンル: {filtered['genre']}",
            f"ターゲット読者: {filtered['target_audience']}",
            f"テーマ: {', '.join(filtered['themes'])}",
            f"売りポイント: {'; '.join(filtered['selling_points'])}",
            f"世界観: {filtered['world_summary']}",
            f"世界観ルール: {'; '.join(filtered['world_rules'])}",
            "メインキャラクター:",
        ]
        for c in filtered["main_characters"]:
            lines.append(f"  - {c['name']}: {c['arc']}")
        lines.append("各巻:")
        for v in filtered["planned_volumes"]:
            lines.append(f"  - {v['title']}: {v['premise']}")
        plan_text = "\n".join(lines)
        user = self._prompts.render(
            "series_plan_review.md",
            {"series_plan": plan_text, "lang": self._lang},
        )
        schema = get_schema("series_plan_review")
        return self._llm.complete_json("series_plan_review", system, user, schema)

    # ── outline ───────────────────────────────────────────────────────

    def outline(self, volume_number: int | None = None) -> dict[str, Any]:
        vol_num = volume_number or self._state.current_volume
        self._state.current_volume = vol_num
        system = self._prompts.render("system.md", {"lang": self._lang})
        series_plan = self._ctx_builder.get_series_plan_summary()
        genre = self._ctx_builder.get_genre()
        user = self._prompts.render(
            "volume_outline.md",
            {
                "series_plan": series_plan,
                "volume_number": str(vol_num),
                "genre": genre,
                "lang": self._lang,
            },
        )
        schema = get_schema("volume_outline")
        result = self._llm.complete_json("volume_outline", system, user, schema)

        # Flatten nested chapters→scenes and assign sequential numbers
        flat_chapters = []
        flat_scenes = []
        scene_counter = 1
        for ch_idx, ch in enumerate(result.get("chapters", []), 1):
            ch["number"] = ch_idx
            flat_chapters.append(ch)
            for sc in ch.get("scenes", []):
                sc["number"] = scene_counter
                sc["chapter_number"] = ch_idx
                flat_scenes.append(sc)
                scene_counter += 1
        result["chapters"] = flat_chapters
        result["scenes"] = flat_scenes

        vol = self._current_volume()
        vol.status = "アウトライン済"
        self._state.status = "アウトライン済"
        self._save_path(vol_num, "outline.json", result)
        self._save()
        return result

    # ── write ─────────────────────────────────────────────────────────

    def write(self, volume_number: int | None = None) -> list[dict[str, Any]]:
        vol_num = volume_number or self._state.current_volume
        self._state.current_volume = vol_num
        outline_data = self._load_path(vol_num, "outline.json")
        outline = VolumeOutline(**outline_data)

        # Deduplicate chapters
        seen_chapters = {}
        for ch in outline.chapters:
            if ch.number not in seen_chapters:
                seen_chapters[ch.number] = ch
        outline.chapters = sorted(seen_chapters.values(), key=lambda c: c.number)

        vol = self._current_volume()
        vol.status = "執筆中"
        results = []

        # Clear stale chapters on resume
        chapters_dir = (
            self._workdir / ".novel-forge" / "volumes" / f"vol{vol_num:02d}" / "chapters"
        )
        if chapters_dir.exists():
            for ch_file in chapters_dir.glob("ch*.md"):
                ch_file.unlink()

        for chapter in outline.chapters:
            chapter_scenes: list[str] = []
            ch_scenes = [s for s in outline.scenes if s.chapter_number == chapter.number]
            for scene in ch_scenes:
                record = self._get_or_create_scene_record(vol, scene.number)
                if record.status in ("修正済", "強制出力済"):
                    chapter_scenes.append(
                        self._scene_writer.load_scene_draft(
                            vol_num, scene.number, chapter.number
                        )
                    )
                    continue
                result = self._scene_writer.write_scene(
                    outline=outline,
                    chapter=chapter,
                    scene=scene,
                    record=record,
                    vol_num=vol_num,
                    lang=self._lang,
                    build_context_fn=self._ctx_builder.build_context,
                    build_continuity_fn=lambda sn, vn: self._ctx_builder.build_continuity(
                        sn, vn, self._scene_writer.load_scene_draft
                    ),
                    get_series_plan_summary_fn=self._ctx_builder.get_series_plan_summary,
                    get_outline_summary_fn=self._ctx_builder.get_outline_summary,
                    get_scene_summary_fn=self._ctx_builder.get_scene_summary,
                )
                results.append(result)
                chapter_scenes.append(
                    self._scene_writer.load_scene_draft(
                        vol_num, scene.number, chapter.number
                    )
                )
                # Post-scene: summarize + bible update
                draft_text = self._scene_writer.load_scene_draft(
                    vol_num, scene.number, chapter.number
                )
                self._scene_writer.summarize_scene(
                    record.scene_number, draft_text, self._lang
                )
                self._scene_writer.update_bible_from_scene(
                    record.scene_number,
                    draft_text,
                    self._lang,
                    self._bible_mgr.to_text,
                )
                self._save()

            self._scene_writer.assemble_chapter(vol_num, chapter, chapter_scenes)

        vol.status = "初稿済"
        self._state.status = "初稿済"
        self._save()
        return results

    # ── export ────────────────────────────────────────────────────────

    def export(self, volume_number: int | None = None) -> dict[str, Any]:
        vol_num = volume_number or self._state.current_volume
        self._state.current_volume = vol_num
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
        return {
            "manuscript_path": str(self._workdir / "exports" / f"vol{vol_num:02d}_manuscript.md"),
            "metadata_path": str(self._workdir / "exports" / f"vol{vol_num:02d}_metadata.json"),
            "report_path": str(self._workdir / "exports" / f"vol{vol_num:02d}_kdp_readiness_report.md"),
        }

    # ── resume ────────────────────────────────────────────────────────

    def resume(self) -> dict[str, Any]:
        vol = self._current_volume()
        if vol.status in ("執筆中", "初稿済"):
            return {"action": "write", "status": vol.status}
        if self._state.status == "計画中":
            return {"action": "plan", "status": self._state.status}
        elif self._state.status == "アウトライン済":
            return {"action": "outline", "status": self._state.status}
        elif self._state.status in ("出力済", "強制出力済"):
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
            "scenes_revised": sum(1 for s in vol.scenes if s.status == "修正済"),
            "scenes_force_exported": sum(
                1 for s in vol.scenes if s.status == "強制出力済"
            ),
        }

    # ── export helpers ────────────────────────────────────────────────

    def _assemble_manuscript(self, vol_num: int) -> str:
        export_dir = self._workdir / "exports"
        export_dir.mkdir(parents=True, exist_ok=True)
        chapters = []
        vol_dir = self._workdir / ".novel-forge" / "volumes" / f"vol{vol_num:02d}"
        for ch_path in sorted(vol_dir.glob("chapters/ch*.md")):
            chapters.append(ch_path.read_text(encoding="utf-8"))
        manuscript = "\n\n---\n\n".join(chapters)
        (export_dir / f"vol{vol_num:02d}_manuscript.md").write_text(
            manuscript, encoding="utf-8"
        )
        return manuscript

    def _generate_kdp_metadata(self, vol_num: int) -> dict[str, Any]:
        export_dir = self._workdir / "exports"
        export_dir.mkdir(parents=True, exist_ok=True)
        plan_path = self._workdir / ".novel-forge" / "series_plan.json"
        title = self._state.series_title
        if plan_path.exists():
            plan = json.loads(plan_path.read_text(encoding="utf-8"))
            title = plan.get("title", title)
        metadata = {
            "title": title,
            "volume": vol_num,
            "language": self._lang,
        }
        (export_dir / f"vol{vol_num:02d}_metadata.json").write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return metadata

    def _generate_readiness_report(self, vol_num: int) -> str:
        export_dir = self._workdir / "exports"
        export_dir.mkdir(parents=True, exist_ok=True)
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
                "以下のシーンは品質ゲート3回不合格のまま出力されています:",
            ])
            for s in vol.scenes:
                if s.status == "強制出力済":
                    lines.append(f"- シーン {s.scene_number}")

        # Unresolved foreshadowing
        unresolved = self._bible_mgr.get_unresolved_foreshadowing()
        if unresolved:
            lines.extend(["", "## ⚠️ 未回収伏線"])
            for fh in unresolved:
                lines.append(f"- {fh.description}")

        # Incomplete subplots
        incomplete_sp = self._bible_mgr.get_incomplete_subplots()
        if incomplete_sp:
            lines.extend(["", "## ⚠️ 未完了サブプロット"])
            for sp in incomplete_sp:
                lines.append(f"- [{sp.status}] {sp.name}: {sp.progress_note or '進捗なし'}")

        # Kanji check
        kanji_issues = self._bible_mgr.check_kanji()
        if kanji_issues:
            lines.extend(["", "## ⚠️ 簡体字混入の可能性"])
            lines.append("以下の項目に JIS 漢字セット外の漢字が含まれています:")
            lines.extend(kanji_issues)

        lines.extend(["", "## 提出前確認事項"])
        lines.append("- [ ] 表紙画像の準備")
        lines.append("- [ ] 商品説明文の最終確認")
        lines.append("- [ ] キーワード・カテゴリの確認")

        report = "\n".join(lines)
        (export_dir / f"vol{vol_num:02d}_kdp_readiness_report.md").write_text(
            report, encoding="utf-8"
        )
        return report
