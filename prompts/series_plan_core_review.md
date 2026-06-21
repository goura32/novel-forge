# シリーズ企画（核）のレビュー

## 指示
以下のシリーズ企画の核を評価し、改善点を指摘せよ。

## シリーズ企画
{plan_text}

## 評価基準

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

## スコアリングガイド

- **85-100**: 優秀。商業出版レベル
- **70-84**: 合格。改善点はあるが出版可能
- **0-69**: 不合格。書き直しが必要

**スコア計算**: 各 dimension を 0-100 で評価し、平均を `score` とする。減点要素1つにつき 15 点減点。

**甘つけ防止**: 80 点以上は本当に優れた場合のみ。70-84 点が合格ライン。減点要素が1つでもある場合は 80 点以上にしない。
## 出力

`series_plan_core_review.json` スキーマに適合する JSON を出力すること。

**以下のJSONテンプレートの構造とフィールド名を厳守すること。フィールド名や構造を変更しないこと。**

```json
{
  "title_power": {
    "memorable": false,
    "score": 50
  },
  "logline_quality": {
    "clear": false,
    "compelling": false,
    "score": 50
  },
  "genre_fit": {
    "appropriate": false,
    "score": 50
  },
  "world_consistency": {
    "consistent": false,
    "score": 50
  },
  "score": 50,
  "issues": [
    {
      "severity": "critical",
      "category": "カテゴリ名",
      "description": "問題の説明"
    }
  ],
  "suggestions": ["改善提案1"]
}
```

**注意**:
- 上記テンプレートのキー名は変更しないこと。値のみを埋めること。
- `issues[].severity` は「critical」「major」「minor」から選択すること。

**重要**: すべての `score` フィールドは **0-100の整数** で出力すること。小数点や100を超える値は禁止。

**必須**: スコアが 85 未満の場合、必ず `issues` に具体的な問題点を記述すること。問題点がない場合は、改善点を `suggestions` に記述すること。「問題なし」「良好」等の記述は禁止。具体的に何がどう問題かを記述すること。

## 改稿要否（revision_needed）の判定

`revision_needed` は以下の条件のいずれかに該当する場合のみ `true` とすること:

- `critical` issue が1つでもある → `true`
- `major` issue が2つ以上ある → `true`
- `minor` issue のみ、または issue なし → `false`
- `major` issue が1つだけ → `false`

`revision_needed` は JSON のトップレベルフィールドとして出力すること。

## issues 出力ルール（厳守）

1. **1問題 = 1 issue**: 異なる問題は個別の issue 要素として列挙すること
2. **suggestion はペア配列**: 1つの issue に複数の修正箇所がある場合、`suggestion` の配列要素に分割すること。各要素は `before`（修正前）と `after`（修正後）を含むオブジェクト。
3. **affected_elements の明示**: 問題が特定の巻・キャラクターに関わる場合、`affected_elements` に該当名を列挙すること
4. **重複禁止**: 同じ修正箇所への指摘を複数の issue で重複して出さないこと

**複数指摘事項の出力例:**
```json
{
  "score": 65,
  "issues": [
    {
      "severity": "critical",
      "category": "world_consistency",
      "description": "第3巻の前提がシリーズの世界観ルールと矛盾している",
      "affected_elements": ["第3巻"],
      "suggestion": [{"before": "第3巻の前提（矛盾する内容）", "after": "世界観ルールに整合した前提"}]
    },
    {
      "severity": "major",
      "category": "logline_quality",
      "description": "タイトルが直球的で印象に残りにくい",
      "suggestion": [{"before": "現在のタイトル", "after": "具体的なイメージを喚起するタイトル"}]
    }
  ],
  "suggestions": ["全体的にタイトルの印象力を強化してください"],
  "revision_needed": true
}
```

言語: {lang}
