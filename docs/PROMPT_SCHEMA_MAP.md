# NovelForge: コード・プロンプト・スキーマ対応表

このドキュメントは、コード（Python）、プロンプトテンプレート（.md）、JSONスキーマ（.json）の3層の整合性を記録します。

## 1. 生成フェーズ（Generate）

### 1.1 Plan フェーズ

| プロンプト | スキーマ | コード (validate_fn) | 出力先 |
|---|---|---|---|
| `series_plan_core.md` | `series_plan_core.json` | `_validate_plan_core` | `series_plan.json` |
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
| `series_plan_core_review.md` | `series_plan_core_review.json` | `_review_plan_core` | LLM が指摘事項を生成 |
| `series_plan_characters_review.md` | `series_plan_characters_review.json` | `_review_plan_characters` | LLM が指摘事項を生成 |
| `series_plan_volumes_review.md` | `series_plan_volumes_review.json` | `_review_plan_volumes` | LLM が指摘事項を生成 |

### 2.2 Design レビュー

| プロンプト | スキーマ | コード (review_fn) | 備考 |
|---|---|---|---|
| `volume_design_review.md` | `volume_design_review.json` | `_review_volume_design` | LLM が指摘事項を生成 |
| `chapter_design_review.md` | `chapter_design_review.json` | `_review_chapter_design` | LLM が指摘事項を生成 |
| `scene_design_review.md` | `scene_design_review.json` | `_review_scene_design` | LLM が指摘事項を生成 |

### 2.3 Write レビュー

| プロンプト | スキーマ | コード (review_fn) | 備考 |
|---|---|---|---|
| `scene_review.md` | `scene_review.json` | `_call_review_api` | LLM が指摘事項を生成 |

---

## 3. 修正フェーズ（Revise）

### 3.1 Plan 修正

| プロンプト | スキーマ | コード (revise_fn) | 備考 |
|---|---|---|---|
| `series_plan_core_revision.md` | `series_plan_core.json` | `complete_json` | 生成スキーマと同じ |
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
| `system.md` | なし | システムプロンプト | 全フェーズで使用 |

---

## 5. スキーマとコードの対応詳細

### 5.1 必須フィールド検証（validate_fn）

| スキーマ | 必須フィールド | コード |
|---|---|---|
| `series_plan_core.json` | title, slug, logline, genre, target_audience, themes, selling_points, world | `_validate_plan_core` |
| `series_plan_characters.json` | main_characters (各キャラ: name, role) | `_validate_plan_characters` |
| `series_plan_volumes.json` | planned_volumes (各巻: title) | `_validate_plan_volumes` |
| `volume_design.json` | chapters | `_validate_volume_design` |
| `chapter_design.json` | title, purpose, theme, emotional_arc | `_validate_chapter_design` |
| `scene_design.json` | title, goal, conflict, outcome | `_validate_scene_design` |
| `scene_draft.json` | content (minLength 3000) | `_validate_fn` |

### 5.2 レビュー出力スキーマ（category enum）

| スキーマ | category 一覧 |
|---|---|
| `series_plan_core_review.json` | あらすじ, ジャンル, 世界観, ターゲット, 言語 |
| `series_plan_characters_review.json` | 一貫性, 差別化, 成長弧, 世界観適合 |
| `series_plan_volumes_review.json` | 独自性, 流れ, フック, テーマ |
| `volume_design_review.json` | 構成, 一貫性, ペース |
| `chapter_design_review.json` | 章役割, テーマ, 感情弧, シーン配分 |
| `scene_design_review.json` | 目標結果, 葛藤, 舞台設定, 多様性 |
| `scene_review.json` | 冒頭フック, キャラ立ち, 感覚描写, 感情描写, シーン末尾, 台詞自然さ, 文体統一, シーン完結, シーン文字数, シー文字数, 言語純度, POV一貫性, 論理一貫性, その他 |

### 5.3 レビューの before/after

レビュースキーマ（`*_review.json`）の各 issue には `before`/`after` フィールドがあります。
- `before`: 修正前の該当部分（LLM が生成）
- `after`: 修正後の改善案（LLM が生成）

これらは **レビュー工程で LLM が生成する** もので、生成されたデータに含まれるものではありません。

---

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
├── series_plan_core.md               # 生成: シリーズ企画（核）
├── series_plan_core_review.md        # レビュー: シリーズ企画（核）
├── series_plan_core_revision.md      # 修正: シリーズ企画（核）
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
└── cover_prompt.md                   # カバー生成（未使用）

schemas/
├── series_plan_core.json             # シリーズ企画（核）スキーマ
├── series_plan_core_review.json      # シリーズ企画（核）レビュースキーマ
├── series_plan_characters.json       # キャラクター設計スキーマ
├── series_plan_characters_review.json # キャラクター設計レビュースキーマ
├── series_plan_volumes.json          # 各巻設計スキーマ
├── series_plan_volumes_review.json   # 各巻設計レビュースキーマ
├── volume_design.json                # 巻設計スキーマ
├── volume_design_review.json         # 巻設計レビュースキーマ
├── chapter_design.json               # 章設計スキーマ
├── chapter_design_review.json        # 章設計レビュースキーマ
├── scene_design.json                 # シーン設計スキーマ
├── scene_design_review.json          # シーン設計レビュースキーマ
├── scene_draft.json                  # シーン本文スキーマ
├── scene_review.json                 # シーン本文レビュースキーマ
├── scene_summary_and_bible_update.json # 要約スキーマ
└── cover_prompt.json                 # カバースキーマ（未使用）

src/novel_forge/engine/
├── plan.py                           # plan() — 3フェーズ
├── design.py                         # design() — 3フェーズ
└── scene_writer.py                   # write_scene() — シーン執筆
```
