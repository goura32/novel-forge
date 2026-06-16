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
    SceneDesign,
    ChapterDesign,
)
from novel_forge.storage import StateStorage, BlackboardStorage, BibleStorage
from novel_forge.ollama_client import LLMClient, load_config
from novel_forge.prompts import PromptManager, PromptLoader
from novel_forge.schemas import validate_or_raise
from novel_forge.quality import QualityGate, find_non_japanese_kanji


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
        self._blackboard_storage = BlackboardStorage(workdir)
        self._bible_storage = BibleStorage(workdir)
        # config.yaml の読み込み（明示引数 > 自動検出）
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

        # slug が 256 文字を超える場合は機械的に切り捨て
        if result.get("slug") and len(result["slug"]) > 256:
            result["slug"] = result["slug"][:256].rstrip("-")

        # planned_volumes に機械採番（LLMは title と premise のみ生成）
        for i, vol in enumerate(result.get("planned_volumes", []), 1):
            vol["number"] = i

        # LLM自己レビュー
        review = self._review_series_plan(result)

        self._state.series_title = result.get("title", "")
        self._state.status = "planned"
        self._save_path(0, "series_plan.json", result)
        self._save_path(0, "series_plan_review.json", review)
        self._save()
        return result

    def _review_series_plan(self, plan: dict[str, Any]) -> dict[str, Any]:
        system = self._prompts.render("system.md", {"lang": self._lang})
        import json as _json
        user = self._prompts.render(
            "series_plan_review.md",
            {"series_plan": _json.dumps(plan, ensure_ascii=False), "lang": self._lang},
        )
        schema = self._load_schema("series_plan_review")
        return self._llm.complete_json("series_plan_review", system, user, schema)

    # ── outline ───────────────────────────────────────────────────────

    def outline(self, volume_number: int | None = None) -> dict[str, Any]:
        vol_num = volume_number or self._state.current_volume
        self._state.current_volume = vol_num
        system = self._prompts.render("system.md", {"lang": self._lang})
        series_plan = self._get_series_plan_summary()
        genre = self._get_genre()
        user = self._prompts.render(
            "volume_outline.md",
            {
                "series_plan": series_plan,
                "volume_number": str(vol_num),
                "genre": genre,
                "lang": self._lang,
            },
        )
        schema = self._load_schema("volume_outline")
        result = self._llm.complete_json("volume_outline", system, user, schema)
        # Flatten nested chapters→scenes structure and assign sequential numbers
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
        vol.status = "outlined"
        self._state.status = "outlined"
        self._save_path(vol_num, "outline.json", result)
        self._save()
        return result

    # ── write ─────────────────────────────────────────────────────────

    def write(self, volume_number: int | None = None) -> list[dict[str, Any]]:
        vol_num = volume_number or self._state.current_volume
        self._state.current_volume = vol_num
        outline_data = self._load_path(vol_num, "outline.json")
        outline = VolumeOutline(**outline_data)
        # Deduplicate chapters by number (keep first occurrence)
        seen_chapters = {}
        for ch in outline.chapters:
            if ch.number not in seen_chapters:
                seen_chapters[ch.number] = ch
        outline.chapters = sorted(seen_chapters.values(), key=lambda c: c.number)
        vol = self._current_volume()
        vol.status = "drafting"
        results = []

        for chapter in outline.chapters:
            chapter_scenes: list[str] = []
            ch_scenes = [s for s in outline.scenes if s.chapter_number == chapter.number]
            for scene in ch_scenes:
                record = self._get_or_create_scene_record(vol, scene.number)
                if record.status in ("revised", "force_exported"):
                    chapter_scenes.append(self._load_scene_draft(vol_num, scene.number, chapter.number))
                    continue
                result = self._write_scene(outline, chapter, scene, record, vol_num)
                results.append(result)
                chapter_scenes.append(self._load_scene_draft(vol_num, scene.number, chapter.number))

            # 章自動組立
            self._assemble_chapter(vol_num, chapter, chapter_scenes)

        vol.status = "drafted"
        self._state.status = "drafted"
        self._save()
        return results

    def _write_scene(
        self,
        outline: VolumeOutline,
        chapter,
        scene,
        record: SceneRecord,
        vol_num: int,
    ) -> dict[str, Any]:
        system = self._prompts.render("system.md", {"lang": self._lang})
        context = self._build_context()
        continuity = self._build_continuity(record.scene_number)

        # Draft
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
        draft_text = self._llm.complete_text("scene_draft", system, user)
        draft_text = self._post_process_text(draft_text)
        record.status = "drafted"
        self._save_scene_draft(vol_num, record.scene_number, draft_text, chapter.number)

        # Review → Quality Gate → 改稿ループ（最大3回）
        for retry in range(QualityGate.MAX_RETRIES + 1):
            review = self._review_scene(draft_text, outline, scene)
            qg_result = self._quality.check_scene(review)
            record.quality_retries = retry + 1

            if qg_result.passed:
                # 品質ゲート通過後、簡体字チェック
                non_jp_kanji = self._quality.check_kanji(draft_text)
                if not non_jp_kanji:
                    record.status = "revised"
                    record.quality_gate = qg_result
                    break
                # 簡体字あり → revision で修正
                if retry < QualityGate.MAX_RETRIES:
                    review["kanji_issues"] = list(set(non_jp_kanji))
                    draft_text = self._revise_scene(draft_text, review)
                    draft_text = self._post_process_text(draft_text)
                    self._save_scene_draft(vol_num, record.scene_number, draft_text, chapter.number)
                    continue

            if retry < QualityGate.MAX_RETRIES:
                # 言語制約違反の情報を revision に追加
                lang_issues = self._extract_language_issues(review)
                if lang_issues:
                    review["language_issues"] = lang_issues
                draft_text = self._revise_scene(draft_text, review)
                draft_text = self._post_process_text(draft_text)
                self._save_scene_draft(vol_num, record.scene_number, draft_text, chapter.number)
            else:
                record.status = "force_exported"
                record.quality_gate = qg_result

        # Summarize → Blackboard更新
        self._summarize_scene(record.scene_number, draft_text)
        self._save()
        return {"scene_number": record.scene_number, "status": record.status}

    def _review_scene(self, draft_text: str, outline: VolumeOutline, scene) -> dict:
        system = self._prompts.render("system.md", {"lang": self._lang})
        user = self._prompts.render(
            "scene_review.md",
            {
                "scene": draft_text,
                "outline": outline.model_dump_json(),
                "context": self._build_context(),
                "lang": self._lang,
            },
        )
        schema = self._load_schema("scene_review")
        return self._llm.complete_json("scene_review", system, user, schema)

    def _extract_language_issues(self, review: dict) -> list[str]:
        """レビュー結果から言語制約違反の問題を抽出する。"""
        issues = review.get("issues", [])
        lang_issues = []
        for issue in issues:
            desc = issue.get("description", "")
            # 言語関連のキーワードを含む issue を抽出
            if any(kw in desc for kw in ["言語", "英語", "簡体字", "ハングル", "中国語", "language_purity", "langue"]):
                lang_issues.append(desc)
        return lang_issues

    def _post_process_text(self, text: str) -> str:
        """LLM出力の後処理: 簡体字の自動置換のみ。

        英語の置換は LLM レビュー・リビジョンに委ねる。
        簡体字は JIS漢字セット外の一般的な簡体字のみ置換。
        """
        # 簡体字→日本語漢字置換
        # JIS漢字セットに含まれないCJK漢字を対象とする
        # 注意: 一般的な簡体字のみ。作品固有の固有名詞には影響しない
        kanji_replacements = [
            ('标记', '標識'),
            ('诊所', '診療所'),
            ('搜索', '捜索'),
            ('调查', '調査'),
            ('转', '転'),
            ('间', '間'),
            ('门', '門'),
            ('东', '東'),
            ('车', '車'),
            ('马', '馬'),
            ('鱼', '魚'),
            ('鸟', '鳥'),
            ('龙', '龍'),
        ]
        for simp, jpn in kanji_replacements:
            text = text.replace(simp, jpn)

        return text

    def _revise_scene(self, draft_text: str, review: dict) -> str:
        system = self._prompts.render("system.md", {"lang": self._lang})
        user = self._prompts.render(
            "scene_revision.md",
            {
                "scene": draft_text,
                "review": json.dumps(review, ensure_ascii=False),
                "lang": self._lang,
            },
        )
        return self._llm.complete_text("scene_revision", system, user)

    def _summarize_scene(self, scene_number: int, draft_text: str) -> None:
        system = self._prompts.render("system.md", {"lang": self._lang})
        user = self._prompts.render(
            "scene_summary.md",
            {
                "scene": draft_text,
                "lang": self._lang,
            },
        )
        schema = self._load_schema("scene_summary")
        result = self._llm.complete_json("scene_summary", system, user, schema)
        bb = self._blackboard_storage.load()
        bb.scene_summaries[str(scene_number)] = result.get("summary", "")
        for fact_data in result.get("facts", []):
            from novel_forge.models import Fact
            bb.facts.append(Fact(**fact_data))
        bb.continuity_notes.extend(result.get("continuity_notes", []))
        self._blackboard_storage.save(bb)

    def _save_scene_draft(self, vol_num: int, scene_number: int, text: str, chapter_number: int = 1) -> None:
        path = (
            self._workdir
            / ".novel-forge"
            / "volumes"
            / f"vol{vol_num:02d}"
            / "scenes"
            / f"ch{chapter_number:02d}"
            / f"vol{vol_num:02d}_ch{chapter_number:02d}_sc{scene_number:02d}.md"
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def _load_scene_draft(self, vol_num: int, scene_number: int, chapter_number: int = 1) -> str:
        path = (
            self._workdir
            / ".novel-forge"
            / "volumes"
            / f"vol{vol_num:02d}"
            / "scenes"
            / f"ch{chapter_number:02d}"
            / f"vol{vol_num:02d}_ch{chapter_number:02d}_sc{scene_number:02d}.md"
        )
        if path.exists():
            return path.read_text(encoding="utf-8")
        return ""

    def _assemble_chapter(self, vol_num: int, chapter, scene_texts: list[str]) -> None:
        vol_dir = self._workdir / ".novel-forge" / "volumes" / f"vol{vol_num:02d}"
        ch_path = vol_dir / "chapters" / f"ch{chapter.number:02d}.md"
        ch_path.parent.mkdir(parents=True, exist_ok=True)
        content = f"# {chapter.title}\n\n" + "\n\n---\n\n".join(scene_texts)
        ch_path.write_text(content, encoding="utf-8")

    # ── export ────────────────────────────────────────────────────────

    def export(self, volume_number: int | None = None) -> dict[str, Any]:
        vol_num = volume_number or self._state.current_volume
        self._state.current_volume = vol_num
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
            "manuscript_path": str(self._workdir / "exports" / f"vol{vol_num:02d}_manuscript.md"),
            "metadata_path": str(self._workdir / "exports" / f"vol{vol_num:02d}_metadata.json"),
            "report_path": str(self._workdir / "exports" / f"vol{vol_num:02d}_kdp_readiness_report.md"),
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
        if not plan_path.exists():
            return "{}"
        data = json.loads(plan_path.read_text(encoding="utf-8"))
        # LLM に提示するのは必要な情報のみ。slug・enum値・schema関連フィールドは含めない（LLM混入の原因になる）
        filtered = {
            "title": data.get("title", ""),
            "logline": data.get("logline", ""),
            "genre": data.get("genre", ""),
            "target_audience": data.get("target_audience", ""),
            "main_characters": data.get("main_characters", []),
            "themes": data.get("themes", []),
        }
        return json.dumps(filtered, ensure_ascii=False)

    def _get_genre(self) -> str:
        plan_path = self._workdir / ".novel-forge" / "series_plan.json"
        if plan_path.exists():
            data = json.loads(plan_path.read_text(encoding="utf-8"))
            return data.get("genre", "fantasy")
        return "fantasy"

    def _build_context(self) -> str:
        bb = self._blackboard_storage.load()
        bible = self._bible_storage.load()
        parts = []
        if bb.facts:
            parts.append(
                "## 事実記録\n"
                + "\n".join(
                    f"- {f.subject} {f.predicate} {f.object}"
                    for f in bb.facts[-20:]
                )
            )
        if bible.characters:
            parts.append(
                "## キャラクター\n"
                + "\n".join(
                    f"- {c.name}: {c.personality}" for c in bible.characters
                )
            )
        if bible.glossary:
            parts.append(
                "## 用語\n"
                + "\n".join(f"- {g.term}: {g.definition}" for g in bible.glossary[-10:])
            )
        if bible.world_rules:
            parts.append(
                "## 世界観ルール\n" + "\n".join(f"- {r}" for r in bible.world_rules)
            )
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

    def _finalize_bible(self) -> None:
        """巻レベルの Bible 整合性を確認し、未反映の事実を更新する。"""
        bible = self._bible_storage.load()
        bb = self._blackboard_storage.load()

        # Blackboard の continuity_notes から伏線回収を検出
        for note in bb.continuity_notes:
            for fh in bible.foreshadowing:
                if not fh.resolved and fh.description in note:
                    fh.resolved = True

        self._bible_storage.save(bible)

    def _check_bible_kanji(self, vol_num: int) -> list[str]:
        """Bible 内のキャラクター名・用語・伏線テキストの簡体字をチェックする。"""
        bible = self._bible_storage.load()
        issues: list[str] = []

        def _scan(text: str, label: str) -> None:
            bad = find_non_japanese_kanji(text)
            if bad:
                unique = list(dict.fromkeys(bad))
                issues.append(f"  {label}: {', '.join(f'{c}(U+{ord(c):04X})' for c in unique)} in 「{text[:40]}」")

        for ch in bible.characters:
            _scan(ch.name, f"キャラクター名({ch.name})")
        for g in bible.glossary:
            _scan(g.term, f"用語({g.term})")
        for fh in bible.foreshadowing:
            _scan(fh.description, "伏線")

        return issues

    def _assemble_manuscript(self, vol_num: int) -> str:
        export_dir = self._workdir / "exports"
        export_dir.mkdir(parents=True, exist_ok=True)
        chapters = []
        vol_dir = self._workdir / ".novel-forge" / "volumes" / f"vol{vol_num:02d}"
        for ch_path in sorted(vol_dir.glob("chapters/ch*.md")):
            chapters.append(ch_path.read_text(encoding="utf-8"))
        manuscript = "\n\n---\n\n".join(chapters)
        (export_dir / f"vol{vol_num:02d}_manuscript.md").write_text(manuscript, encoding="utf-8")
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
        force_count = sum(1 for s in vol.scenes if s.status == "force_exported")
        revised_count = sum(1 for s in vol.scenes if s.status == "revised")
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
            lines.extend(
                [
                    "",
                    "## ⚠️ 警告",
                    "以下のシーンは品質ゲート3回不合格のまま出力されています:",
                ]
            )
            for s in vol.scenes:
                if s.status == "force_exported":
                    lines.append(f"- シーン {s.scene_number}")

        # 未回収伏線
        bible = self._bible_storage.load()
        unresolved = [fh for fh in bible.foreshadowing if not fh.resolved]
        if unresolved:
            lines.extend(["", "## ⚠️ 未回収伏線"])
            for fh in unresolved:
                lines.append(f"- {fh.description}")

        # 簡体字チェック（Bible）
        kanji_issues = self._check_bible_kanji(vol_num)
        if kanji_issues:
            lines.extend(["", "## ⚠️ 簡体字混入の可能性"])
            lines.append("以下の項目に JIS 漢字セット外の漢字が含まれています:")
            lines.extend(kanji_issues)

        lines.extend(["", "## 提出前確認事項"])
        lines.append("- [ ] 表紙画像の準備")
        lines.append("- [ ] 商品説明文の最終確認")
        lines.append("- [ ] キーワード・カテゴリの確認")

        report = "\n".join(lines)
        (export_dir / f"vol{vol_num:02d}_kdp_readiness_report.md").write_text(report, encoding="utf-8")
        return report
