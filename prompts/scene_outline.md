# シーン設計

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

## 設計原則

1. **シーンの目標 (goal)**: シーン開始時の状況と主人公の行動。`State: ... | Action: ...` 形式。
2. **シーンの結果 (outcome)**: シーン終了時の実際の結果。次のシーンの goal（State部分）に繋がること。
3. **葛藤 (conflict)**: シーン内の障害・対立。
4. **視点 (pov)**: このシーンの視点人物。
5. **登場人物**: このシーンに登場するキャラクター。
6. **主要イベント**: シーン内で起こる重要な出来事。
7. **舞台設定**: シーンが行われる場所・状況。

## 出力スキーマ

`scene_outline.json` に適合する JSON を出力すること。JSON Schema の各フィールド定義・required・maxLength に従うこと。

**以下のJSONテンプレートの構造とフィールド名を厳守すること。フィールド名や構造を変更しないこと。**

```json
{
  "title": "シーンタイトル（128文字以内）",
  "goal": "State: シーン開始時の状況 | Action: 主人公の行動（400文字以内）",
  "outcome": "シーン終了時の実際の結果。次のシーンのgoalに繋がること（400文字以内）",
  "conflict": "シーン内の障害・対立（300文字以内）",
  "pov": "視点人物（64文字以内）",
  "characters": ["登場人物1", "登場人物2"],
  "key_events": ["主要イベント1", "主要イベント2"],
  "setting": "舞台設定（200文字以内）"
}
```

**注意**:
- 上記テンプレートのキー名は変更しないこと。値のみを埋めること。
- `goal` は `State: ... | Action: ...` 形式で記述すること。
- `outcome` は次のシーンの `goal`（State部分）に繋がる内容にすること。

言語: {lang}
