# シーン設計

## 役割
あなたはシーンの設計を担当する小説家です。目標・結果・葛藤・視点を明確にし、臨場感のあるシーンを設計します。

## 指示
以下の情報に基づいて、このシーンの詳細設計を生成せよ。

## シリーズ企画
{series_plan}

## 巻情報
- 巻番号: {volume_number}
- 巻タイトル: {volume_title}
- 巻の前提: {volume_premise}

## 章情報
- 章番号: {chapter_number}
- 章タイトル: {chapter_title}
- 章の役割: {chapter_purpose}
- 章のテーマ: {chapter_theme}
- 章の感情の弧: {chapter_emotional_arc}
- 章の伏線メモ: {chapter_foreshadowing_notes}
- 章のサブプロットメモ: {chapter_subplot_notes}

## このシーンの位置
- シーン番号: {scene_number}（全{scene_count}シーン中）
- 章内位置: {chapter_scene_number}/{chapter_scene_count}

## 前シーンの結果
{previous_outcome}

## 前巻の主要な結果
{previous_volume_summary}

## シーン間の多様性（最重要）
**各シーンは固有の目的・イベント・感情の変化を持つこと。同じパターンを繰り返さないこと。**
- 前シーンとの差別化: 異なる出来事・異なる感情・異なる葛藤
- 感情の弧の多様化: 各シーンで異なる感情の断面
- イベントの進行: 各シーンで新しい情報・変化・対立を導入
- POVの活用: 章内でPOVを切り替える
- 舞台設定の変化: 場所や時間帯を変える

## 出力

下記のスキーマに適合するJSONのみを出力すること。


{schema}

- `goal` は `State: ... | Action: ...` 形式
- `outcome` は次のシーンの goal（State部分）に繋がる内容
- `title` には「シーンX:」等のプレフィックスを付けない
- `pov` にはキャラクター名をスペースなしで（例: 「九条涼」）
- `characters`, `key_events` は必ず2つ以上
