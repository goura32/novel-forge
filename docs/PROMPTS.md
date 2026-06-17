# NovelForge Prompt Management

## プロンプトの管理方針

プロンプトは `prompts/` の Markdown ファイルで管理する。コードには直書きしない。

**用語の定義**: [GLOSSARY.md](GLOSSARY.md)

## プロンプト一覧

```text
prompts/
├── system.md                              # 共通システムプロンプト
├── series_plan.md                         # シリーズ企画
├── series_plan_review.md                  # シリーズ企画の自己レビュー
├── series_plan_revision.md                # シリーズ企画の改訂
├── volume_outline.md                      # 巻アウトライン生成
├── volume_outline_review.md               # 巻アウトラインの自己レビュー
├── volume_outline_revision.md             # 巻アウトラインの改訂
├── chapter_design.md                      # 章設計
├── scene_outline.md                       # シーン設計
├── scene_draft.md                         # シーン初稿
├── scene_review.md                        # シーンレビュー
├── scene_revision.md                      # シーン改稿
├── scene_summary.md                       # シーン要約
├── scene_summary_and_bible_update.md      # シーン要約 + Bible 更新（統合）
├── scene_quality_gate.md                  # シーン品質ゲート
├── bible_update.md                        # Bible 更新
├── kdp_metadata.md                        # KDP メタデータ生成
├── kdp_final_review.md                    # KDP 最終レビュー
└── cover_prompt.md                        # 表紙画像生成プロンプト
```

## レビューと改稿は別プロンプト

**原則**: 同じプロンプトで書いて評価しない。自己評価バイアスを防ぐため、生成・レビュー・改稿はそれぞれ別のプロンプトファイルを使用する。

| 工程 | 生成 | レビュー | 改稿 |
|---|---|---|---|
| シリーズ企画 | `series_plan.md` | `series_plan_review.md` | `series_plan_revision.md` |
| 巻アウトライン | `volume_outline.md` | `volume_outline_review.md` | `volume_outline_revision.md` |
| シーン本文 | `scene_draft.md` | `scene_review.md` | `scene_revision.md` |
| 設定資料集 | `bible_update.md` | 該当なし | 該当なし |
| KDP メタデータ | `kdp_metadata.md` | 該当なし | 該当なし |
| KDP 最終レビュー | `kdp_final_review.md` | 該当なし | 該当なし |

## プロンプトの構造

各プロンプトは `{variable}` プレースホルダーを使用する。

**プレースホルダーとコンテキスト注入の対応**:

| プレースホルダー | 内容 |
|---|---|
| `{series_plan}` | シリーズ企画の要約 |
| `{outline}` | 巻アウトライン |
| `{scene}` | アウトライン内の当該シーン定義 |
| `{context}` | Bible + Blackboard |
| `{continuity}` | 前シーン要約 + 引き継ぎメモ |
| `{current_bible}` | 現在の Bible テキスト |
| `{lang}` | 出力言語 |

## レビュープロンプトの共通ルール

全レビュープロンプト（`*_review.md`）は以下の構造に従う:

1. **評価基準の提示**: 何を基準として評価するかを明示
2. **出力形式**: JSON Schema に適合する構造化出力を指示
3. **改善提案**: 問題点だけでなく具体的な改善案を含める
4. **深刻度付け**: `critical` / `major` / `minor` の3段階
5. **制約**: 本文の新規生成は指示しない

## 言語制約（最優先）

中国語の生成を禁止する。出力言語は `{lang}` で指定された言語に限定する。

この制約は `system.md` の最上位に記述し、全プロンプトで最優先する。

**簡体字・ハングル検出について:**
- ツールによる検出は行わない（JIS 漢字セットベースの検出は誤検出が多いため）
- プロンプトでの防止が主
- LLM が簡体字を出力した場合、レビューで指摘する

## 品質基準（全工程共通）

1. **構造**: 目標→障害→災害→反応→ジレンマ→決断のビートを遵守
2. **表現**: Show-don't-tell を徹底
3. **五感描写**: シーンに最低3つ以上の感覚描写を含める
4. **一貫性**: POV、キャラクター、世界観に矛盾がないこと
5. **重複防止**: シーン内で同一段落や情報が繰り返されないこと

## スコアリングガイド

### シーン評価（scene_review.md）

- **90-100**: 商業出版レベル。ほぼ問題なし
- **80-89**: 良好。軽微な改善点があるが、そのまま出版可能
- **70-79**: 合格ライン。いくつかの改善点があるが、全体的に読者を引き込む品質
- **60-69**: 改善が必要。複数の major issue がある
- **50-59**: 大幅な改善が必要
- **0-49**: 書き直しが必要

**重要**: 商業出版レベルの小説は 70-85 点の範囲で評価するのが適切。完璧を求めて 60 点以下をつけないこと。

### アウトライン評価（volume_outline_review.md）

- `score` = (`structural_validity.score` + `scene_coherence.score` + `pace_analysis.score` + `character_arc_review.score`) / 4
- `critical` issue がある場合: `score` 最大 50
- `major` issue が 3 つ以上ある場合: `score` 最大 65
- `minor` issue のみの場合: `score` 最低 70

## レビュー指摘修正ループ

### シーン単位

- デフォルト: 1回のレビュー指摘修正（`--max-retries 1`）
- 最大: 3回（品質ゲート不合格時）
- 設定ファイル: `quality.max_review_retries`
- CLI オプション: `--max-retries`

### アウトライン単位

- デフォルト: 3回のレビュー指摘修正
- シリーズ企画、巻アウトラインとも同じ

## summarize_and_bible_update

`scene_summary_and_bible_update.md` はシーン要約とBible更新を1回のLLM呼び出しで実行する統合プロンプト。

**出力スキーマ**: `scene_summary_and_bible_update.json`

**抽出項目**:
- シーン要約
- 事実記録 (facts)
- 引き継ぎメモ (continuity_notes)
- キャラクター更新
- 伏線設置/回収
- キャラクター関係性変化
- サブプロット進捗
- 新規用語
- 世界観ルール追加

## ファイル名混入防止

LLM がシーンアウトラインのタイトルやファイル名をそのまま出力に含める場合がある。

**対策:**
- プロンプトで「本文のみを出力せよ」と明示
- レビューでファイル名混入を指摘
- 改稿で修正

---

*Last updated: 2026-06-28*
