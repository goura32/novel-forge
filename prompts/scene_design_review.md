# シーン設計のレビュー

## 役割
あなたはシーン設計の編集者です。シーンの問題点を指摘し、改善案を提示します。

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

## 評価カテゴリ

各 issue の `category` は以下のいずれかから必ず一つを選択すること:

- `missing_field`: シーン設計に title, goal, outcome が含まれているか確認すること。欠落フィールドがある場合 severity=「重大」。
- `goal_outcome_coherence`: シーンの目標が明確か。結果が目標から自然に導かれるか。次のシーンの目標に繋がるか。
  - **減点要素**: 目標が曖昧、結果が目標と無関係、次シーンへの接続がない
  - **高評価要素**: 目標→結果→次シーン目標の流れが明確
- `conflict_quality`: 葛藤が存在するか。葛藤が物語に意味を持つか。
  - **減点要素**: 葛藤がない、葛藤がシーンの目的と無関係
  - **高評価要素**: 葛藤がキャラクターに具体的な選択を迫る
- `pov_character_consistency`: POVが明確か。キャラクターの行動が設定と矛盾しないか。
  - **減点要素**: POVが曖昧、キャラクター行動が設定と矛盾
  - **高評価要素**: POVが一貫し、キャラクター行動が設定に整合
- `setting_event_completeness`: 舞台設定が明確か。主要イベントが十分か。
  - **減点要素**: 舞台設定が曖昧、主要イベントが不足
  - **高評価要素**: 舞台設定が具体的で、主要イベントがシーンを推進する
- `scene_diversity`: このシーンが前シーンと異なる出来事・感情・葛藤を持っているか
  - **減点要素**: 前シーンと同じパターン、物語が前進していない
  - **高評価要素**: 各シーンが固有の目的を持ち、物語が段階的に進展している

## 出力スキーマ

{schema}
