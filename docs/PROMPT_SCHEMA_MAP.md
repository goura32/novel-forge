# NovelForge: コード・プロンプト・スキーマ対応表

このドキュメントは、コード（Python）、プロンプトテンプレート（.md）、JSONスキーマ（.json）の3層の整合性を記録します。

## 1. 生成フェーズ（Generate）

### 1.1 Plan フェーズ

| プロンプト | スキーマ | コード (validate_fn) | 出力先 |
|---|---|---|---|
| `series_plan_concept.md` | `series_plan_concept.json` | `_validate_plan_concept` | `series_plan.json` |
| `series_plan_characters.md` | `series_plan_characters.json` | `_validate_plan_characters` | `series_plan.json` |
| `series_plan_volumes.md` | `series_plan_volumes.json` | `_validate_plan_volumes` | `series_plan.json` |

### 1.2 Design フェーズ

| プロンプト | スキーマ | コード (validate_fn) | 出力先 |
|---|---|---|---|
| `volume_design.md` | `volume_design.json` | `_validate_volume_design` | `vol{NN}.json` |
| `chapter_design.md` | `chapter_design.json` | `_validate_chapter_design` | `vol{NN}.json` |
| `scene_design.md` | `scene_design.json` | `_validate_scene_design` | `vol{NN}.json` |

### 1.3 Write フェーズ

| プロンプト | スキーマ | コード (validate_fn) | 出力先 |
|---|---|---|---|
| `scene_draft.md` | `scene_draft.json` | `_validate_fn` (content length) | `scenes/vol{NN}/sc{NN}.json` |

---

## 2. レビューフェーズ（Review）

### 2.1 Plan レビュー

| プロンプト | スキーマ | コード (review_fn) | 備考 |
|---|---|---|---|
| `series_plan_concept_review.md` | `review.json` | `_review_plan_concept` | LLM が指摘事項を生成 |
| `series_plan_characters_review.md` | `review.json` | `_review_plan_characters` | LLM が指摘事項を生成 |
| `series_plan_volumes_review.md` | `review.json` | `_review_plan_volumes` | LLM が指摘事項を生成 |

### 2.2 Design レビュー

| プロンプト | スキーマ | コード (review_fn) | 備考 |
|---|---|---|---|
| `volume_design_review.md` | `review.json` | `_review_volume_design` | LLM が指摘事項を生成 |
| `chapter_design_review.md` | `review.json` | `_review_chapter_design` | LLM が指摘事項を生成 |
| `scene_design_review.md` | `review.json` | `_review_scene_design` | LLM が指摘事項を生成 |

### 2.3 Write レビュー

| プロンプト | スキーマ | コード (review_fn) | 備考 |
|---|---|---|---|
| `scene_review.md` | `review.json` | `_call_review_api` | LLM が指摘事項を生成 |

---

## 3. 修正フェーズ（Revise）

### 3.1 Plan 修正

| プロンプト | スキーマ | コード (revise_fn) | 備考 |
|---|---|---|---|
| `series_plan_concept_revision.md` | `series_plan_concept.json` | `complete_json` | 生成スキーマと同じ |
| `series_plan_characters_revision.md` | `series_plan_characters.json` | `complete_json` | 生成スキーマと同じ |
| `series_plan_volumes_revision.md` | `series_plan_volumes.json` | `complete_json` | 生成スキーマと同じ |

### 3.2 Design 修正

| プロンプト | スキーマ | コード (revise_fn) | 備考 |
|---|---|---|---|
| `volume_design_revision.md` | `volume_design.json` | `complete_json` | 生成スキーマと同じ |
| `chapter_design_revision.md` | `chapter_design.json` | `complete_json` | 生成スキーマと同じ |
| `scene_design_revision.md` | `scene_design.json` | `complete_json` | 生成スキーマと同じ |

### 3.3 Write 修正

| プロンプト | スキーマ | コード (revise_fn) | 備考 |
|---|---|---|---|
| `scene_revision.md` | `scene_draft.json` | `_revise_scene` | 生成スキーマと同じ |

---

## 4. その他のプロンプト

| プロンプト | スキーマ | 用途 | 備考 |
|---|---|---|---|
| `scene_summary_and_bible_update.md` | `scene_summary_and_bible_update.json` | シーン要約・更新 | レビューとは別 |
| `kdp_metadata.md` | `kdp_metadata.json` | KDPメタデータ生成 | 単体実行 |
| `system.md` | なし | システムプロンプト | 全フェーズで使用 |
| `cover_prompt.md` | なし | 表紙生成プロンプト | 未使用 |

---

## 5. スキーマとコードの対応詳細

### 5.1 必須フィールド検証（validate_fn）

| スキーマ | 必須フィールド | コード |
|---|---|---|
| `series_plan_concept.json` | title, slug, logline, genre, target_audience, themes, selling_points, world_summary, world_rules | `_validate_plan_concept` |
| `series_plan_characters.json` | main_characters (各キャラ: name, role, personality, background, arc, relationships) | `_validate_plan_characters` |
| `series_plan_volumes.json` | planned_volumes (各巻: title, premise) | `_validate_plan_volumes` |
| `volume_design.json` | chapters | `_validate_volume_design` |
| `chapter_design.json` | title, purpose, theme, emotional_arc, outcome, scenes | `_validate_chapter_design` |
| `scene_design.json` | title, goal, conflict, outcome, pov, characters, key_events, setting | `_validate_scene_design` |
| `scene_draft.json` | title, content (minLength 3000) | `_validate_fn` |
| `kdp_metadata.json` | title, description, keywords, categories | なし |

### 5.2 統一レビュースキーマ（review.json）

すべてのレビューで単一の `review.json` スキーマを使用。フィールドは以下のみ:

| フィールド | 必須 | 説明 |
|---|---|---|
| `severity` | ✓ | 修正の緊急性: `致命的` / `重要` / `軽微` |
| `field` | ✓ | 修正対象のフィールド名（各フェーズ固有） |
| `description` | ✓ | 問題の説明。何がどう問題かを具体的に記述。 |
| `suggestion` | ✓ | 修正の提案。どう改善すべきかの方向性を示す。 |
| `before` | ✓ | 修正前のテキスト（当該フィールド内の該当箇所を引用） |
| `after` | ✓ | 修正後のテキスト。beforeを置き換える完成形。プレースホルダー禁止、即採用可能な品質。 |

## 6. プレースホルダ自動置換

`prompts.py` の `render()` メソッドは `{schema}` を自動的にスキーマJSONに置換します。

```python
# prompts.py
def render(self, name: str, variables: dict[str, str]) -> str:
    ...
    if "{schema}" in result:
        schema_json = json.dumps(get_schema(schema_name), ensure_ascii=False, indent=2)
        result = result.replace("{schema}", schema_json)
    return render_prompt(result, variables)
```

そのため、コードで `schema` キーを渡す必要はありません。

---

## 7. ファイル構成

```
prompts/
├── system.md                         # システムプロンプト
├── series_plan_concept.md               # 生成: シリーズ構想
├── series_plan_concept_review.md        # レビュー: シリーズ構想
├── series_plan_concept_revision.md      # 修正: シリーズ構想
├── series_plan_characters.md         # 生成: キャラクター設計
├── series_plan_characters_review.md  # レビュー: キャラクター設計
├── series_plan_characters_revision.md # 修正: キャラクター設計
├── series_plan_volumes.md            # 生成: 各巻設計
├── series_plan_volumes_review.md     # レビュー: 各巻設計
├── series_plan_volumes_revision.md   # 修正: 各巻設計
├── volume_design.md                  # 生成: 巻設計
├── volume_design_review.md           # レビュー: 巻設計
├── volume_design_revision.md         # 修正: 巻設計
├── chapter_design.md                 # 生成: 章設計
├── chapter_design_review.md          # レビュー: 章設計
├── chapter_design_revision.md        # 修正: 章設計
├── scene_design.md                   # 生成: シーン設計
├── scene_design_review.md            # レビュー: シーン設計
├── scene_design_revision.md          # 修正: シーン設計
├── scene_draft.md                    # 生成: シーン本文
├── scene_review.md                   # レビュー: シーン本文
├── scene_revision.md                 # 修正: シーン本文
├── scene_summary_and_bible_update.md # 要約・更新
├── kdp_metadata.md                   # KDPメタデータ生成
└── cover_prompt.md                   # カバー生成（未使用）

schemas/
├── series_plan_concept.json             # シリーズ構想スキーマ
├── series_plan_characters.json       # キャラクター設計スキーマ
├── series_plan_volumes.json          # 各巻設計スキーマ
├── volume_design.json                # 巻設計スキーマ
├── chapter_design.json               # 章設計スキーマ
├── scene_design.json                 # シーン設計スキーマ
├── scene_draft.json                  # シーン本文スキーマ
├── review.json                       # 統一レビュースキーマ（全フェーズ共通）
├── scene_summary_and_bible_update.json # 要約スキーマ
├── kdp_metadata.json                 # KDPメタデータスキーマ
└── cover_prompt.json                 # カバースキーマ（未使用）

src/novel_forge/engine/
├── plan.py                           # plan() — 3フェーズ
├── design.py                         # design() — 3フェーズ
└── scene_writer.py                   # write_scene() — シーン執筆
```

---

*Last updated: 2026-07-03* (review.json スキーマから category フィールドを削除しました（レビュー指摘では severity、field、description, suggestion, before, after のみを使用）。config.yaml の品質ゲート設定も併せて更新しています（max_generation_count: 4、max_review_count: 7、max_retries: 1）。