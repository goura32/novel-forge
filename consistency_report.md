# novel-forge 整合性確認レポート

## 1. スキーマの項目とコードの整合性

### 問題1: `scene_draft.json` スキーマと `SceneDraft` モデル - 一致 ✓
- スキーマ: `title`, `content` (required)
- モデル: `title`, `content` - 一致

### 問題2: `scene_design.json` スキーマと `SceneDesign` モデル - 不一致
- **スキーマの required**: `title`, `goal`, `outcome` (3つ)
- **モデルの全フィールド**: `number`, `title`, `pov`, `goal`, `conflict`, `outcome`, `characters`, `emotional_arc`, `key_events`, `setting`, `notes` (11個)
- **スキーマの properties に欠落**: `number`, `pov` (requiredではないがpropertiesにはある), `emotional_arc`, `characters` (ある), `notes` (欠落)
- **影響**: LLMが生成する設計に `emotional_arc`, `notes` が含まれない。コード側で期待しても空になる

### 問題3: `chapter_design.json` スキーマと `ChapterDesign` モデル - 不一致
- **スキーマの required**: `title`, `purpose`, `theme`, `emotional_arc`
- **モデルの全フィールド**: `number`, `title`, `purpose`, `theme`, `emotional_arc`, `foreshadowing_notes`, `subplot_notes`, `scene_summaries`, `characters` (9個)
- **スキーマの properties に欠落**: `foreshadowing_notes`, `subplot_notes`, `scene_summaries`, `characters`, `number`

### 問題4: `volume_design.json` スキーマと `VolumeOutline`/`ChapterOutline`/`SceneOutline` モデル - 不一致
- **スキーマの required**: `chapters` のみ
- `VolumeOutline` モデル: `volume_number`, `title`, `premise`, `chapters`, `scenes`
- スキーマの `chapters` items には `number` がないがモデルにはある
- `SceneOutline` モデル: `number`, `chapter_number`, `title`, `pov`, `goal`, `conflict`, `outcome`, `characters`, `key_events`, `setting` - スキーマの scene properties に `pov`, `key_events`, `setting` しかなく、`chapter_number`, `conflict`, `outcome` 等がスキーマにあるがモデルと整合はとれているが `number` がスキーマにない

### 問題5: `bible.json` スキーマと `Bible` モデル - 基本一致だが Foreshadowing で差異
- **ForeshadowingItem スキーマ**: `description` (required), `resolved` (optional)
- **ForeshadowingItem モデル**: `description`, `resolved` - 一致
- **BibleUpdate スキーマの foreshadowing**: `id`, `description`, `type` (enum: 設置/回収), `resolved`, `scene_number` - モデルよりフィールド多い

### 問題6: `series_plan_concept.json` スキーマと `SeriesPlan` モデル - 不一致
- **スキーマの required**: `title`, `slug`, `logline`, `genre`, `target_audience`, `themes`, `selling_points`, `world` (8個)
- **モデルのフィールド**: `title`, `logline`, `genre`, `target_audience`, `themes`, `selling_points`, `world`, `main_characters`, `planned_volumes`, `keywords`, `catchphrase`, `differentiation` (12個) - `slug` がモデルにない！
- **影響**: slug は `plan()` 関数で機械生成されるが、SeriesPlan モデルに保存されない

### 問題7: `series_plan_characters.json` スキーマと `CharacterProfile` モデル - 不一致
- **スキーマの character properties**: `name`, `role`, `personality`, `motivation`, `flaw`, `arc`, `age`, `occupation`, `appearance`, `background` (10個)
- **モデル**: `name`, `role`, `arc`, `appearance`, `personality`, `motivation`, `state` (7個) - `flaw`, `age`, `occupation`, `background` がモデルにない
- **影響**: LLM生成データに含まれる `flaw`, `age`, `occupation`, `background` がモデルで保持されない

### 問題8: `series_plan_volumes.json` スキーマと `VolumePlanItem` モデル - 不一致
- **スキーマの volume properties**: `title`, `premise`, `theme`, `emotional_arc`, `key_events`, `cliffhanger` (6個)
- **モデル**: `title`, `premise` (2個) - `theme`, `emotional_arc`, `key_events`, `cliffhanger` がモデルにない

---

## 2. スキーマの項目とプロンプトの整合性

### 問題9: `scene_draft.md` プロンプトの `{design}` プレースホルダ - コードは `"outline"` を渡す
- **プロンプト**: `{design}` (line 12)
- **コード (scene_writer.py:108)**: `"outline": ctx.get_outline_summary_fn(design_obj)`
- **影響**: `{design}` が未置換のまま LLM に渡される → 設計情報が欠落

### 問題10: `scene_review.md` プロンプトの `{design}` プレースホルダ - コードは `"outline"` を渡す
- **プロンプト**: `{design}` (line 13)
- **コード (scene_writer.py:183)**: `"outline": ctx.get_outline_summary_fn(design_obj)`
- **影響**: レビュー時に巻設計が渡されない

### 問題11: `kdp_metadata.md` / `cover_prompt.md` - 使用されていないプロンプト
- どちらも `{design}` を使用だが、コードから呼び出されていない

### 問題12: `chapter_design.md` プロンプト - 渡されていない変数多数
- **プロンプトのプレースホルダ**: `{volume_title}`, `{volume_premise}`, `{chapter_title}`, `{chapter_purpose}`, `{previous_volume_summary}`, `{previous_chapter_outcome}`
- **コード (design.py:132-138)**: `series_plan`, `volume_number`, `chapter_number`, `chapter_title`, `chapter_purpose`, `previous_chapter_outcome`, `previous_volume_summary`, `lang`
- **不足**: `{volume_title}`, `{volume_premise}` - 渡されていない

### 問題13: `scene_design.md` プロンプト - 渡されていない変数多数
- **プロンプトのプレースホルダ**: `{volume_title}`, `{volume_premise}`, `{chapter_title}`, `{chapter_purpose}`, `{chapter_theme}`, `{chapter_emotional_arc}`, `{chapter_foreshadowing_notes}`, `{chapter_subplot_notes}`, `{previous_volume_summary}`, `{previous_outcome}`, `{scene_number}`, `{scene_count}`, `{chapter_scene_number}`, `{chapter_scene_count}`
- **コード (design.py:175-182)**: `series_plan`, `volume_number`, `chapter_number`, `scene_number`, `scene_count`, `chapter_scene_number`, `chapter_scene_count`, `previous_outcome`, `lang`
- **不足**: `{volume_title}`, `{volume_premise}`, `{chapter_title}`, `{chapter_purpose}`, `{chapter_theme}`, `{chapter_emotional_arc}`, `{chapter_foreshadowing_notes}`, `{chapter_subplot_notes}`, `{previous_volume_summary}`

### 問題14: `chapter_design_review.md` / `scene_design_review.md` - `{lang}` 渡されているがプロンプトにない
- コード: `"lang": engine._lang` を渡しているが、プロンプトに `{lang}` は存在しない（無害だが無駄）

---

## 3. プロンプトテンプレートのプレースホルダーとコードの整合性

### 問題15: `scene_draft.md` - `{design}` vs コードの `"outline"` (問題9と同じ)

### 問題16: `scene_review.md` - `{design}` vs コードの `"outline"` (問題10と同じ)

### 問題17: `system.md` - `{schema}` は自動置換されるが、`{lang}` はプロンプトになくコードで渡している
- **現状**: `system.md` には `{schema}` のみ（自動置換対象）、`{lang}` なし
- **コード**: `{"lang": ctx.lang}` を渡す → 無害だが無駄

### 問題18: `scene_revision.md` - `{lang}` 渡されているがプロンプトにない
- コード: `"lang": lang` を渡しているがプロンプトに `{lang}` なし

### 問題19: `volume_design_revision.md` - `{series_plan}`, `{previous_design}` 含め正しく渡されている ✓

### 問題20: `series_plan_concept_revision.md` / `series_plan_characters_revision.md` / `series_plan_volumes_revision.md` - 正しく渡されている ✓

---

## 重要度順まとめ

### 🔴 Critical (データ欠落・エラーの原因)
1. **問題9, 15**: `scene_draft.md` の `{design}` が `"outline"` として渡される → シーン執筆時に設計情報欠落
2. **問題10, 16**: `scene_review.md` の `{design}` が `"outline"` として渡される → レビュー時に設計情報欠落
3. **問題6**: `SeriesPlan` モデルに `slug` フィールドなし → スラッグが永続化されない
4. **問題7**: `CharacterProfile` モデルに `flaw`, `age`, `occupation`, `background` なし → キャラ詳細が失われる
5. **問題8**: `VolumePlanItem` モデルに `theme`, `emotional_arc`, `key_events`, `cliffhanger` なし → 巻設計詳細が失われる

### 🟠 High (機能低下・品質低下)
6. **問題2**: `SceneDesign` スキーマに `emotional_arc`, `notes` なし → シーン設計の品質低下
7. **問題3**: `ChapterDesign` スキーマに `foreshadowing_notes`, `subplot_notes` 等なし → 章設計の品質低下
8. **問題12**: `chapter_design.md` に `{volume_title}`, `{volume_premise}` 渡されない → 章設計時の文脈不足
9. **問題13**: `scene_design.md` に 9個の変数渡されない → シーン設計時の文脈不足

### 🟡 Medium (無駄・軽微)
10. **問題14, 17, 18**: `{lang}` を渡しているがプロンプトで使われていない
11. **問題11**: 未使用プロンプト (`kdp_metadata.md`, `cover_prompt.md`)

### 🟢 Low (整合性の問題)
12. **問題4, 5**: スキーマとモデルの細かな不一致（実用上問題になりにくい）

---

## 修正提案

### 修正1: scene_draft.md / scene_review.md のプレースホルダ名を統一
**選択肢A**: プロンプト側を `{outline}` に変更（推奨：コード変更不要）
**選択肢B**: コード側を `"design": ...` に変更

### 修正2: SeriesPlan モデルに `slug` フィールド追加
```python
class SeriesPlan(BaseModel):
    slug: str = ""  # 追加
    ...
```

### 修正3: CharacterProfile モデルに不足フィールド追加
```python
class CharacterProfile(BaseModel):
    flaw: str = ""
    age: str = ""
    occupation: str = ""
    background: str = ""
    ...
```

### 修正4: VolumePlanItem モデルに不足フィールド追加
```python
class VolumePlanItem(BaseModel):
    theme: str = ""
    emotional_arc: str = ""
    key_events: list[str] = Field(default_factory=list)
    cliffhanger: str = ""
    ...
```

### 修正5: scene_design.json / chapter_design.json スキーマに不足フィールド追加
- `scene_design.json` に `emotional_arc`, `notes` を properties に追加
- `chapter_design.json` に `foreshadowing_notes`, `subplot_notes`, `scene_summaries`, `characters` を properties に追加

### 修正6: design.py で chapter_design.md / scene_design.md に必要な変数を渡す
- 章設計生成時に `volume_title`, `volume_premise` を取得して渡す
- シーン設計生成時に章情報（theme, emotional_arc, foreshadowing_notes, subplot_notes）を渡す

### 修正7: 不要な `"lang"` 渡しを削除（system.md, scene_revision.md 等）

### 修正8: 未使用プロンプトの削除または実装