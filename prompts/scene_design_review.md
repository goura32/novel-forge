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

## レビュー観点

以下の観点を順に評価し、問題があれば `issues` に指摘すること。各 issue の `category` は以下のいずれかから選択すること:

- `必須フィールド欠落`: 必須フィールドの完全性
- `目標結果の整合性`: 目標が明確か、結果が目標から自然に導かれるか
- `葛藤の質`: 葛藤が存在するか、物語に意味を持つか
- `舞台設定完了性`: 舞台設定が明確か
- `シーン多様性`: このシーンが前シーンと異なる出来事・感情・葛藤を持っているか

## 出力構造

下記のスキーマに適合するJSONのみを出力すること。

{schema}
