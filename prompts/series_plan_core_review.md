# シリーズ企画（核）のレビュー

## 役割
あなたはシリーズ企画の編集者です。企画の問題点を指摘し、改善案を提示します。

## 指示
以下のシリーズ企画の核を評価し、改善点を指摘せよ。

## シリーズ企画
{plan_text}

## 評価基準

0. **必須フィールドの完全性** (`missing_field`)
   - 以下の必須フィールドがすべて含まれているか確認すること: title, logline, genre, themes, selling_points, world (summary + rules), target_audience
   - **主要フィールド**（title, logline, genre, world）が欠落している場合: severity=「重大」
   - **補足フィールド**（themes, selling_points, target_audience）が欠落している場合: severity=「重要」
   - **欠落フィールドがある場合**: 該当する severity で issue を出力すること。category は `missing_field` とする
   - すべてのフィールドが埋まっている場合は、このカテゴリの issue を出力しないこと

1. **タイトルの力** (`title_power`)
   - 覚えやすいか、印象的か
   - **減点要素**: 直球的すぎる（「〜の物語」「〜と〜」）、長すぎる（10字以上）、何の作品かわからない
   - **高評価要素**: 好奇心を刺激する、書店で目を引く、検索しやすい

2. **あらすじの質** (`logline_quality`)
   - 明確か、読者の興味を引くか
   - **減点要素**: 曖昧な表現（「真実を探る」「自分を見つける」「絆を深める」）、主人公の具体的な危機・葛藤がない、何の作品かわからない
   - **高評価要素**: 「誰が、何に、どう立ち向かうか」が具体的に伝わる、読んでみたくなる

3. **ジャンル適合** (`genre_fit`)
   - ジャンル設定は内容と一致しているか
   - **減点要素**: ジャンルと内容が合っていない（例: 心理ミステリーなのにアクション主体）
   - **高評価要素**: ジャンルの特徴が反映されている

4. **世界観の一貫性** (`world_consistency`)
   - 世界観のルールに矛盾がないか
   - **減点要素**: ルール同士が矛盾している、ルールが不明確
   - **高評価要素**: ルールが明確で一貫している

## 改稿要否（revision_needed）の判定

- 「重大」 issue が1つでもある → `true`
- 「重要」 issue が2つ以上ある → `true`
- 「軽微」 issue のみ、または issue なし → `false`
- 「重要」 issue が1つだけ → `false`

## 出力

`series_plan_core_review.json` スキーマに適合する JSON を出力すること。

**以下のJSONテンプレートの構造とフィールド名を厳守すること。フィールド名や構造を変更しないこと。**

```json
{
  "title_power": {
    "memorable": false,
  },
  "logline_quality": {
    "clear": false,
    "compelling": false,
  },
  "genre_fit": {
    "appropriate": false,
  },
  "world_consistency": {
    "consistent": false,
  },
  "issues": [
    {
      "severity": "重大",
      "category": "カテゴリ名",
      "description": "問題の説明",
      "suggestion": [{"before": "修正前", "after": "修正後"}]
    }
  ],
  "revision_needed": false
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
      "category": "world_consistency",
      "description": "第3巻の前提がシリーズの世界観ルールと矛盾している",
      "affected_elements": ["第3巻"],
      "suggestion": [{"before": "第3巻の前提（矛盾する内容）", "after": "世界観ルールに整合した前提"}]
    },
    {
      "severity": "重要",
      "category": "logline_quality",
      "description": "タイトルが直球的で印象に残りにくい",
      "suggestion": [{"before": "現在のタイトル", "after": "具体的なイメージを喚起するタイトル"}]
    }
  ],
  "revision_needed": true
}
```

言語: {lang}