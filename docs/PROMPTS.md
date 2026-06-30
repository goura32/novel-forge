# NovelForge プロンプト管理

## プロンプトの管理方針

プロンプトは `prompts/` の Markdown ファイルで管理する。コードには直書きしない。

**用語の定義**: [GLOSSARY.md](GLOSSARY.md)

## プロンプトとスキーマの対応

詳細な対応表は [PROMPT_SCHEMA_MAP.md](PROMPT_SCHEMA_MAP.md) を参照してください。
├── scene_revision.md                      # シーン改稿
├── scene_summary_and_bible_update.md      # シーン要約 + Bible 更新（統合）
├── kdp_metadata.md                        # KDP メタデータ生成
└── cover_prompt.md                        # 表紙画像生成プロンプト
```

## プロンプト戦略の概要

**生成・稿は別プロンプト**

自己評価バイアスを防ぐため、生成・レビュー・改稿はそれぞれ別のプロンプトファイルを使用する。

| 工程 | 生成 | レビュー | 改稿 |
|---|---|---|---|
| シリーズ企画 | `series_plan_core.md` + `characters.md` + `volumes.md` | `*_review.md` | `*_revision.md` |
| 巻デザイン | `volume_design.md` + `chapter_design.md` + `scene_design.md` | `*_review.md` | `*_revision.md` |
| シーン本文 | `scene_draft.md` | `scene_review.md` | `scene_revision.md` |
| 設定資料集 | `scene_summary_and_bible_update.md` | 該当なし | 該当なし |

### 各工程の役割定義

各プロンプトの先頭に `## 役割` セクションを記述し、LLMに期待する役割を明示する。

| プロンプト | 役割 |
|---|---|
| `series_plan_core.md` | シリーズ全体を統括するプロデューサー |
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

中国語の生成を禁止する。出力言語は日本語に限定する。この制約は `system.md` に記述し、全プロンプトで遵守される。

---

## ログフォーマット

```
[YYYY-MM-DD HH:MM:SS] [PID XXXX] [:X] [vol:Y] [LEVEL] message
```

- ログファイル: `workdir/novel_forge.log`（追記モード）
- stderr: WARNING 以上（verbose 時は DEBUG）

---

*Last updated: 2026-06-30*
