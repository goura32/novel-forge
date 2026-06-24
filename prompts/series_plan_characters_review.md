# シリーズ企画（キャラクター）のレビュー

## 役割
あなたはキャラクター設計の編集者です。キャラクターの問題点を指摘し、改善案を提示します。

## 指示
以下のキャラクター設計を評価し、改善点を指摘せよ。

## キャラクター設計
{characters}

## 評価基準

0. **必須フィールドの完全性** (`missing_field`)
   - 各キャラクターに以下の必須フィールドがすべて含まれているか確認すること: name, role, personality, motivation, flaw, growth
   - **主要フィールド**（name, role, personality, motivation, flaw, growth）が欠落している場合: severity=「重大」
   - **補足フィールド**（gender, age, occupation, appearance, background, arc）が欠落している場合: severity=「重要」
   - **出力例**: `{"severity": "重大", "category": "missing_field", "description": "キャラクター「霧島 鈴音」に必須フィールド「growth」が欠落しています。成長の方向性を追加してください。", "affected_elements": ["霧島 鈴音"], "suggestion": [{"before": "(欠落)", "after": "成長の方向性の具体的な記述"}]}`
   - すべてのフィールドが埋まっている場合は、このカテゴリの issue を出力しないこと

1. **設定一貫性** (`consistency`)
   - キャラクターの行動・性格が設定（性別、年齢、職業）と矛盾しないか
   - **減点要素**: 性格と行動が矛盾している、年齢に合わない言動、職業に合わない知識・技能
   - **高評価要素**: 設定が行動・性格・背景で一貫している

2. **キャラクター差別化** (`differentiation`)
   - 各キャラクターが明確に区別されているか
   - **減点要素**: キャラクター同士が似ている、口調・行動パターンが同じ、名前以外に違いがない
   - **高評価要素**: 各キャラクターに独自の口癖・行動特性・価値観がある
   - **重複キャラクターの検出**: `main_characters` 内に同じ名前のキャラクターが複数存在する場合、severity=「重大」で issue を出力すること。category は `differentiation` とする。description に「キャラクター「XXX」がN回重複しています。各キャラクターは異なる名前・性格・背景を持つように修正してください」と記載すること。

3. **成長弧** (`growth_arc`)
   - 各キャラクターに成長の方向性があるか
   - **減点要素**: 成長が不明確、変化がない、成長が唐突
   - **高評価要素**: 具体的な成長の方向性があり、物語のテーマと連動している

4. **世界観適合** (`world_fit`)
   - キャラクターが世界観に適合しているか
   - **減点要素**: 世界観のルールに合わない能力・知識、時代設定に合わない言動
   - **高評価要素**: 世界観の中で自然に存在するキャラクター

## 改稿要否（revision_needed）の判定

- 「重大」 issue が1つでもある → `true`
- 「重要」 issue が2つ以上ある → `true`
- 「軽微」 issue のみ、または issue なし → `false`
- 「重要」 issue が1つだけ → `false`

## 出力

`series_plan_characters_review.json` スキーマに適合する JSON を出力すること。

**以下のJSONテンプレートの構造とフィールド名を厳守すること。フィールド名や構造を変更しないこと。**

```json
{
  "consistency": "設定と行動が一貫している。ただし年齢に合わない言動が一部見られる。",
  "differentiation": "各キャラクターは明確に差別化されている。",
  "growth_arc": "成長の方向性は概ね明確だが、一部キャラクターの成長が唐突。",
  "world_fit": "世界観に自然に適合している。",
  "issues": [
    {
      "severity": "重大",
      "category": "consistency",
      "description": "キャラクターの行動が設定と矛盾している",
      "affected_elements": ["九条涼"],
      "suggestion": [{"before": "涼の矛盾する行動", "after": "性格設定に整合した行動"}]
    }
  ],
  "revision_needed": true
}
```

**注意**:
- 上記テンプレートのキー名は変更しないこと。値のみを埋めること。
- **すべてのフィールドを必ず出力すること。省略禁止。** スキーマに存在するすべてのキーに対応する値を記述すること。
- `issues[].severity` は「重大」「重要」「軽微」から選択すること。
- `issues[].suggestion` は**オブジェクトの配列**であること。各要素は `before`（修正前）と `after`（修正後）を含むオブジェクト。

**必須**: issue がない場合でも、`issues` には空配列ではなく、改善点を記述すること。「問題なし」「良好」等の記述は禁止。具体的に何がどう改善できるかを記述すること。

## issues 出力ルール（厳守）

1. **1問題 = 1 issue**: 異なる問題は個別の issue 要素として列挙すること
2. **suggestion はペア配列**: 1つの issue に複数の修正箇所がある場合、`suggestion` の配列要素に分割すること。各要素は `before`（修正前）と `after`（修正後）を含むオブジェクト。
3. **affected_elements の明示**: 問題が特定の巻・キャラクターに関わる場合、`affected_elements` に該当名を列挙すること
4. **重複禁止**: 同じ修正箇所への指摘を複数の issue で重複して出さないこと

**複数指摘事項の出力例:**
```json
{
  "issues": [
    {
      "severity": "重大",
      "category": "consistency",
      "description": "キャラクターの行動が設定と矛盾している",
      "affected_elements": ["九条涼"],
      "suggestion": [{"before": "涼の矛盾する行動", "after": "性格設定に整合した行動"}]
    },
    {
      "severity": "重要",
      "category": "differentiation",
      "description": "主人公とヒロインの性格が似すぎて差別化が不十分",
      "affected_elements": ["九条涼", "レイナ"],
      "suggestion": [{"before": "ヒロインの性格（主人公と類似）", "after": "独自の行動特性・口癖を持つ性格"}]
    }
  ],
  "revision_needed": true
}
```

言語: {lang}