# NovelForge プロンプト管理

## プロンプトの管理方針

プロンプトは `prompts/` の Markdown ファイルで管理する。コードには直書きしない。

**用語の定義**: [GLOSSARY.md](GLOSSARY.md)

## プロンプト一覧

```
prompts/
├── system.md                              # 共通システムプロンプト
├── series_plan_core.md                    # シリーズ企画（核）
├── series_plan_core_review.md             # シリーズ企画（核）のレビュー
├── series_plan_core_revision.md           # シリーズ企画（核）の改訂
├── series_plan_characters.md              # シリーズ企画（キャラクター）
├── series_plan_characters_review.md       # シリーズ企画（キャラクター）のレビュー
├── series_plan_characters_revision.md     # シリーズ企画（キャラクター）の改訂
├── series_plan_volumes.md                 # シリーズ企画（各巻）
├── series_plan_volumes_review.md          # シリーズ企画（各巻）のレビュー
├── series_plan_volumes_revision.md        # シリーズ企画（各巻）の改訂
├── volume_design.md                       # 巻デザイン Phase 1: 章構成
├── volume_design_review.md                # 巻デザインのレビュー
├── volume_design_revision.md              # 巻デザインの改訂
├── chapter_design.md                      # 巻デザイン Phase 2: 章設計
├── chapter_design_review.md               # 章デザインのレビュー
├── chapter_design_revision.md             # 章デザインの改訂
├── scene_design.md                        # 巻デザイン Phase 3: シーンデザイン
├── scene_design_review.md                 # シーンデザインのレビュー
├── scene_design_revision.md               # シーンデザインの改訂
├── scene_draft.md                         # シーン初稿
├── scene_review.md                        # シーンレビュー
├── scene_revision.md                      # シーン改稿
├── scene_summary_and_bible_update.md      # シーン要約 + Bible 更新（統合）
├── kdp_metadata.md                        # KDP メタデータ生成
└── cover_prompt.md                        # 表紙画像生成プロンプト
```

## プロンプト戦略の概要

**生成・レビュー・改稿は別プロンプト**

自己評価バイアスを防ぐため、生成・レビュー・改稿はそれぞれ別のプロンプトファイルを使用する。

| 工程 | 生成 | レビュー | 改稿 |
|---|---|---|---|
| シリーズ企画 | `series_plan_core.md` + `characters.md` + `volumes.md` | `*_review.md` | `*_revision.md` |
| 巻デザイン | `volume_design.md` + `chapter_design.md` + `scene_design.md` | `*_review.md` | `*_revision.md` |
| シーン本文 | `scene_draft.md` | `scene_review.md` | `scene_revision.md` |
| 設定資料集 | `scene_summary_and_bible_update.md` | 該当なし | 該当なし |

詳細なプロンプト設計原則は `docs/dev/PROMPTS_STRATEGY.md` を参照。

## 言語制約

中国語の生成を禁止する。出力言語は `{lang}` で指定された言語に限定する。この制約は `system.md` の最優先事項に記述し、全プロンプトで遵守される。

---

*Last updated: 2026-06-23*