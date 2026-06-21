# シーン設計のレビュー

## 指示
以下のシーン設計を評価し、改善点を指摘せよ。

## シリーズ企画
{series_plan}

## 巻情報
- 巻タイトル: {volume_title}
- 巻の前提: {volume_premise}

## 章情報
- 章タイトル: {chapter_title}
- 章の役割: {chapter_purpose}

## シーン設計
- シーンタイトル: {scene_title}
- 目標: {scene_goal}
- 結果: {scene_outcome}
- 葛藤: {scene_conflict}
- POV: {scene_pov}
- 登場人物: {scene_characters}
- 主要イベント: {scene_key_events}
- 舞台設定: {scene_setting}
- 感情の弧: {scene_emotional_arc}

## 前シーンの結果
{previous_outcome}

## 評価基準

1. **目標・結果の連貫性** (`goal_outcome_coherence`)
   - シーンの目標が明確か。結果が目標から自然に導かれるか。次のシーンの目標に繋がるか。
   - **減点要素**: 目標が曖昧、結果が目標と無関係、次シーンへの接続がない
   - **高評価要素**: 目標→結果→次シーン目標の流れが明確

2. **葛藤の質** (`conflict_quality`)
   - 葛藤が存在するか。葛藤が物語に意味を持つか。
   - **減点要素**: 葛藤がない、葛藤がシーンの目的と無関係
   - **高評価要素**: 葛藤がキャラクターに具体的な選択を迫る

3. **POV・キャラクター一貫性** (`pov_character_consistency`)
   - POVが明確か。キャラクターの行動が設定と矛盾しないか。
   - **減点要素**: POVが曖昧、キャラクター行動が設定と矛盾
   - **高評価要素**: POVが一貫し、キャラクター行動が設定に整合

4. **舞台・イベントの完全性** (`setting_event_completeness`)
   - 舞台設定が明確か。主要イベントが十分か。
   - **減点要素**: 舞台設定が曖昧、主要イベントが不足
   - **高評価要素**: 舞台設定が具体的で、主要イベントがシーンを推進する

## 改稿要否（revision_needed）の判定

- 「重大」 issue が1つでもある → `true`
- 「重要」 issue が2つ以上ある → `true`
- 「軽微」 issue のみ、または issue なし → `false`
- 「重要」 issue が1つだけ → `false`

## 出力

`scene_design_review.json` スキーマに適合する JSON を出力すること。

**以下のJSONテンプレートの構造とフィールド名を厳守すること。フィールド名や構造を変更しないこと。**

```json
{
  "goal_outcome_coherence": {
    "goal_clear": false,
    "outcome_follows": false,
    "connects_to_next": false,
  },
  "conflict_quality": {
    "conflict_exists": false,
    "conflict_meaningful": false,
  },
  "pov_character_consistency": {
    "pov_clear": false,
    "character_actions_consistent": false,
  },
  "setting_event_completeness": {
    "setting_clear": false,
    "key_events_sufficient": false,
  },
  "issues": [
    {
      "severity": "重大",
      "category": "カテゴリ名",
      "description": "問題の説明",
      "affected_elements": ["要素1"]
    }
  ],
  "suggestions": ["改善提案1"]
}
```

**注意**:
- 上記テンプレートのキー名は変更しないこと。値のみを埋めること。
- `issues[].severity` は「重大」「重要」「軽微」から選択すること。
- `issues[].category` は評価カテゴリ名から選択すること。
- `issues[].suggestion` は**オブジェクトの配列**であること。各要素は `before`（修正前）と `after`（修正後）を含むオブジェクト。

**suggestion 出力例:**
```json
{
  "severity": "重大",
  "category": "goal_outcome_coherence",
  "description": "シーンの結果が次のシーンの目標に繋がっていない",
  "affected_elements": ["シーン3"],
  "suggestion": [{"before": "シーン3の結果（次シーンと無関係）", "after": "シーン3の結果（次シーンの目標に繋がる内容）"}]
}
```

**必須**: スコアが 85 未満の場合、必ず `issues` に具体的な問題点を記述すること。問題点がない場合は、改善点を `suggestions` に記述すること。「問題なし」「良好」等の記述は禁止。

言語: {lang}
