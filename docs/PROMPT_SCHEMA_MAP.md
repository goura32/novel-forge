# Prompt / Schema / Runtime 対応

最終更新: 2026-07-10

この表は、現在実装されている v1 runtime の対応です。Series Bible v2 の未実装 Schema は含めません。

## 生成・レビュー・改稿

| 工程 | 生成 prompt / schema | review prompt / schema | revision prompt / schema | 主な実行箇所 |
|---|---|---|---|---|
| Series concept | `series_plan_concept.md` / `series_plan_concept.json` | `series_plan_concept_review.md` / `review.json` | `series_plan_concept_revision.md` / `series_plan_concept.json` | `engine/plan.py` |
| Characters | `series_plan_characters.md` / `series_plan_characters.json` | `series_plan_characters_review.md` / `review.json` | `series_plan_characters_revision.md` / `series_plan_characters.json` | `engine/plan.py` |
| Volumes | `series_plan_volumes.md` / `series_plan_volumes.json` | `series_plan_volumes_review.md` / `review.json` | `series_plan_volumes_revision.md` / `series_plan_volumes.json` | `engine/plan.py` |
| Volume design | `volume_design.md` / `volume_design.json` | `volume_design_review.md` / `review.json` | `volume_design_revision.md` / `volume_design.json` | `engine/design.py` |
| Chapter design | `chapter_design.md` / `chapter_design.json` | `chapter_design_review.md` / `review.json` | `chapter_design_revision.md` / `chapter_design.json` | `engine/design.py` |
| Scene design | `scene_design.md` / `scene_design.json` | `scene_design_review.md` / `review.json` | `scene_design_revision.md` / `scene_design.json` | `engine/design.py` |
| Scene draft | `scene_draft.md` / `scene_draft.json` | `scene_review.md` / `review.json` | `scene_revision.md` / `scene_draft.json` | `scene_writer.py` |
| Scene summary + v1 Bible update | `scene_summary_and_bible_update.md` / `scene_summary_and_bible_update.json` | — | — | `scene_writer.py` |

`system.md` は全 LLM task で共通に使われます。

## 例外・未使用のリソース

| リソース | 現状 |
|---|---|
| `kdp_metadata.md` / `kdp_metadata.json` | export のメタデータは `engine/export.py` が Python で生成するため、現行 runtime は template を render しない |
| `cover_prompt.md` / `cover_prompt.json` | runtime から呼ばれない |

これらは package resource として残っていますが、現行 runtime contract ではありません。削除・再導入は、実装とテストを同じ変更で扱ってください。

## Schema 展開と検証

1. `PromptManager.render()` が `{schema}` を対応 Schema の簡略化表現へ展開する。
2. prompt variables を置換する。
3. `LLMClient.complete_json()` が Ollama 呼び出し、JSON parse、Schema validation を行う。
4. plan / design / export などが工程固有の semantic validation を追加する。

Review の共通 Schema は `review.json` です。`publication_blocking` は severity と独立した、次工程へ進めない問題の印です。

## v2 への注意

`scene_summary_and_bible_update` と `bible*.json` は現行 v1 runtime の契約です。Canon Event ベースの v2 では Pydantic domain model と `CanonPatch` / `CanonEvent` を使用し、現行の update 経路を廃止します。v2 の設計判断は [SERIES_BIBLE_SCHEMA_REDESIGN](dev/SERIES_BIBLE_SCHEMA_REDESIGN.md) を参照してください。
