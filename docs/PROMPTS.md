# NovelForge プロンプト管理

## プロンプトの管理方針

プロンプトは `src/novel_forge/resources/prompts/` の Markdown ファイルで一元管理する。コードには直書きしない。

**用語の定義**: [GLOSSARY.md](GLOSSARY.md)

## プロンプトとスキーマの対応

詳細な対応表は [PROMPT_SCHEMA_MAP.md](PROMPT_SCHEMA_MAP.md) を参照してください。

```
src/novel_forge/resources/prompts/
├── system.md                                # システムプロンプト
├── series_plan_concept.md                   # 生成: シリーズ構想
├── series_plan_concept_review.md            # レビュー: シリーズ構想
├── series_plan_concept_revision.md          # 修正: シリーズ構想
├── series_plan_characters.md                # 生成: キャラクター設計
├── series_plan_characters_review.md         # レビュー: キャラクター設計
├── series_plan_characters_revision.md       # 修正: キャラクター設計
├── series_plan_volumes.md                   # 生成: 各巻設計
├── series_plan_volumes_review.md            # レビュー: 各巻設計
├── series_plan_volumes_revision.md          # 修正: 各巻設計
├── volume_design.md                         # 生成: 巻設計
├── volume_design_review.md                  # レビュー: 巻設計
├── volume_design_revision.md                # 修正: 巻設計
├── chapter_design.md                        # 生成: 章設計
├── chapter_design_review.md                 # レビュー: 章設計
├── chapter_design_revision.md               # 修正: 章設計
├── scene_design.md                          # 生成: シーン設計
├── scene_design_review.md                   # レビュー: シーン設計
├── scene_design_revision.md                 # 修正: シーン設計
├── scene_draft.md                           # 生成: シーン本文
├── scene_review.md                          # レビュー: シーン本文
├── scene_revision.md                        # 修正: シーン本文
├── scene_summary_and_bible_update.md        # 要約・更新
├── kdp_metadata.md                          # KDP メタデータ生成
└── cover_prompt.md                          # 表紙画像生成プロンプト
```

## プロンプト戦略の概要

**生成・稿は別プロンプト**

自己評価バイアスを防ぐため、生成・レビュー・改稿はそれぞれ別のプロンプトファイルを使用する。

| 工程 | 生成 | レビュー | 改稿 |
|---|---|---|---|
| シリーズ企画 | `series_plan_concept.md` + `series_plan_characters.md` + `series_plan_volumes.md` | `*_review.md` | `*_revision.md` |
| 巻デザイン | `volume_design.md` + `chapter_design.md` + `scene_design.md` | `*_review.md` | `*_revision.md` |
| シーン本文 | `scene_draft.md` | `scene_review.md` | `scene_revision.md` |
| 設定資料集 | `scene_summary_and_bible_update.md` | 該当なし | 該当なし |
| 出版準備 | `kdp_metadata.md` | 該当なし | 該当なし |

### 各工程の役割定義

各プロンプトの先頭に `## 役割` セクションを記述し、LLMに期待する役割を明示する。

| プロンプト | 役割 |
|---|---|
| `series_plan_concept.md` | シリーズ全体を統括するプロデューサー |
| `series_plan_characters.md` | キャラクター設計の専門家 |
| `series_plan_volumes.md` | 物語の架構を設計する構成家 |
| `volume_design.md` | 巻の構造を設計する放送作家 |
| `chapter_design.md` | 章の設計を担当する小説家 |
| `scene_design.md` | シーンの設計を担当する小説家 |
| `scene_draft.md` | プロの小説家（本文執筆） |
| `scene_review.md` | 厳格な編集長（評価・改善指示） |
| `scene_revision.md` | 改稿を担当する作家（修正実行） |
| `scene_summary_and_bible_update.md` | 物語の記録係（要約・台帳更新） |
| `kdp_metadata.md` | 出版事務担当 |
| `cover_prompt.md` | 表紙デザイナー |

### スキーマ埋め込み方式

プロンプトには `{schema}` プレースホルダを記述する。
`complete_json()` 実行時に、対応する JSON スキーマファイルの内容に置換される。

- **プロンプト**: `{schema}` プレースホルダのみ（構造・制約の説明はスキーマに任せる）
- **スキーマファイル**: `schemas/*.json` に JSON Schema で構造を定義
- **コード**: `complete_json()` で `{schema}` → スキーマ全文に置換

### 改稿プロンプトのスキーマ

`*_revision.md` プロンプトは、**生成工程と同じスキーマ**を使用する。
（`*_revision.json` ファイルは不要。改訂も同じスキーマ構造で出力する。）

---

## slug の仕様

- 文字種: `a-z`, `0-9`, `_`（ハイフン不可）
- 区切り文字: `_`（アンダースコア）
- 最大長: 32文字
- 重複禁止: 既存シリーズの slug と重複不可
- 例: `novel_forge`, `monthly_closed_nonmagic_chef`

---

## 言語制約

**すべてのプロンプトに「言語純度」カテゴリを導入**

- 中国語（簡体字/繁体字）の生成を禁止
- 英語、ハングル等の混在を禁止
- 出力言語は日本語に限定する

この制約は各レビュープロンプトの「言語純度」レビュー観点で検証される。

---

## レビュー観点の共通化

すべてのレビュープロンプトで以下のカテゴリを含む：

- **言語純度**: 日本語以外の文字（英語、簡体字、繁体字、ハングル等）が混在していないか

各フェーズ固有の観点は PROMPT_SCHEMA_MAP.md を参照。

---

## ログフォーマット

```
[YYYY-MM-DD HH:MM:SS] [PID XXXX] [:X] [vol:Y] [LEVEL] message
```

- ログファイル: `workdir/novel_forge.log`（追記モード）
- stderr: WARNING 以上（verbose 時は DEBUG）

---

*Last updated: 2026-07-03*