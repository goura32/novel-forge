# NovelForge Prompt Management

## プロンプトの管理方針

プロンプトは `prompts/` の Markdown ファイルで管理する。コードには直書きしない。

**用語の定義**: [GLOSSARY.md](GLOSSARY.md)

## プロンプト一覧

```text
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

## レビューと改稿は別プロンプト

**原則**: 同じプロンプトで書いて評価しない。自己評価バイアスを防ぐため、生成・レビュー・改稿はそれぞれ別のプロンプトファイルを使用する。

| 工程 | 生成 | レビュー | 改稿 |
|---|---|---|---|
| シリーズ企画 | `series_plan_core.md` + `characters.md` + `volumes.md` | `*_review.md` | `*_revision.md` |
| 巻デザイン | `volume_design.md` + `chapter_design.md` + `scene_design.md` | `*_review.md` | `*_revision.md` |
| シーン本文 | `scene_draft.md` | `scene_review.md` | `scene_revision.md` |
| 設定資料集 | `scene_summary_and_bible_update.md` | 該当なし | 該当なし |
| KDP メタデータ | `kdp_metadata.md` | 該当なし | 該当なし |

## プロンプトの構造

各プロンプトは `{variable}` プレースホルダーを使用する。

**プレースホルダーとコンテキスト注入の対応**:

| プレースホルダー | 内容 |
|---|---|
| `{series_plan}` | シリーズ企画の要約 |
| `{design}` | 巻デザイン |
| `{scene}` | デザイン内の当該シーン定義 |
| `{context}` | Bible + Blackboard |
| `{continuity}` | 前シーン全文 + 直近シーン要約 + 引き継ぎメモ |
| `{lang}` | 出力言語 |
| `{volume_number}` | 巻番号 |
| `{volume_title}` | 巻タイトル |
| `{volume_premise}` | 巻の前提 |
| `{chapter_number}` | 章番号 |
| `{chapter_title}` | 章タイトル |
| `{chapter_purpose}` | 章の役割 |
| `{scene_number}` | シーン番号 |
| `{chapter_scene_number}` | 章内シーンナンバー |
| `{scene_count}` | シーン総数 |
| `{current_design}` | 現在のデザイン（改稿時） |
| `{review}` | レビュー結果（改稿時） |
| `{plan_text}` | 企画テキスト（レビュー時） |
| `{characters}` | キャラクター設計（レビュー時） |
| `{volumes}` | 各巻設計（レビュー時） |

## レビュープロンプトの共通ルール

全レビュープロンプト（`*_review.md`）は以下の構造に従う:

1. **評価基準の提示**: 何を基準として評価するかを明示
2. **減点要素の明示**: 何があったら減点するかを具体的に列挙
3. **スコアリングガイド**: 3段階（不合格/合格/優秀）で評価
4. **出力形式**: JSON Schema に適合する構造化出力を指示
5. **改善提案**: 問題点だけでなく具体的な改善案を含める
6. **深刻度付け**: `critical` / `major` / `minor` / `blocker` の4段階
7. **制約**: 本文の新規生成は指示しない（scene_review.md のみ）

## スコアリングガイド（全レビュー共通）

| スコア | 意味 |
|---|---|
| 85-100 | 優秀。商業出版レベル |
| 70-84 | 合格。改善点はあるが出版可能 |
| 0-69 | 不合格。書き直しが必要 |

**甘つけ防止**: 80 点以上は本当に優れた場合のみ。70-84 点が合格ライン。減点要素が1つでもある場合は 80 点以上にしない。

**スコア再計算ルール**（Python 側で `recalc_review_score` が実行）:
- サブスコアの平均をベースに計算
- critical issue → score ≤ 50
- major issue 3つ以上 → score ≤ 65
- minor only → score ≥ 70

## 言語制約（最優先）

中国語の生成を禁止する。出力言語は `{lang}` で指定された言語に限定する。

この制約は `system.md` の最優先事項に記述し、全プロンプトで遵守される。

**簡体字・ハングル検出について:**
- ツールによる検出は行わない（混在チェックは LLM レビューに委ねる）
- プロンプトでの防止が主
- LLM が簡体字を出力した場合、レビューで `language_purity` カテゴリとして指摘する

## 品質基準（全工程共通）

1. **構造**: 目標→葛藤→結果の流れを遵守
2. **表現**: Show-don't-tell を徹底
3. **五感描写**: シーンに最低3つ以上の感覚描写を含める
4. **一貫性**: POV、キャラクター、世界観に矛盾がないこと
5. **重複防止**: シーン間で同じ情報が繰り返されないこと（continuity で防止）
6. **三人称維持**: 地の文は三人称で一貫させる（一人称に切り替わったら blocker）

## レビュー指摘修正ループ

### シーン単位
- デフォルト: 2回（`--max-retries 2`）
- 最大: 設定ファイル `quality.max_review_retries` で変更可能

### デザイン単位
- デフォルト: 3回（ハードコード）

### シリーズ企画単位
- デフォルト: 3回（ハードコード）

## summarize_and_update_bible

`scene_summary_and_bible_update.md` はシーン要約とBible更新を1回のLLM呼び出しで実行する統合プロンプト。

**出力スキーマ**: `scene_summary_and_bible_update.json`

**抽出項目**:
- シーン要約
- 事実記録 (facts)
- 引き継ぎメモ (continuity_notes)
- キャラクター更新（既存更新 or 新規追加）
- 伏線設置/回収
- キャラクター関係性変化
- サブプロット進捗
- 新規用語
- 世界観ルール追加

## ファイル名混入防止

LLM がシーンデザインのタイトルやファイル名をそのまま出力に含める場合がある。

**対策:**
- プロンプトで「本文のみを出力せよ」と明記（scene_draft.md に記載）
- レビューでファイル名混入を指摘
- 改稿で修正

---

*Last updated: 2026-06-21*
