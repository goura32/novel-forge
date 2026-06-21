# シーン要約 + Bible 更新

以下のシーン本文を分析し、**シーン要約**と**Bible 更新**を1回の出力で生成してください。

## シーン本文

{scene}

## 現在の Bible

{current_bible}

## 出力スキーマ

`scene_summary_and_bible_update.json` に適合する JSON を出力すること。

**以下のJSONテンプレートの構造とフィールド名を厳守すること。フィールド名や構造を変更しないこと。**

```json
{
  "summary": "シーンの要約（1000文字以内）",
  "facts": [
    {
      "subject": "主語",
      "predicate": "述語",
      "object": "目的語"
    }
  ],
  "continuity_notes": ["連続性メモ1", "連続性メモ2"],
  "characters": [
    {
      "name": "キャラクター名",
      "role": "役割（64文字以内）",
      "personality": "性格（200文字以内）",
      "appearance": "外見（200文字以内）",
      "motivation": "動機（200文字以内）",
      "arc": "成長・変化（200文字以内）",
      "state": "現在の状態（200文字以内）",
      "is_new": false
    }
  ],
  "foreshadowing": [
    {
      "description": "伏線の説明（200文字以内）",
      "type": "設置"
    }
  ],
  "relationships": [
    {
      "character_a": "キャラクターA",
      "character_b": "キャラクターB",
      "type": "関係の種類（64文字以内）",
      "change_direction": "改善",
      "trigger_event": "関係変化のきっかけ（200文字以内）"
    }
  ],
  "subplots": [
    {
      "id": "サブプロットID",
      "name": "サブプロット名（128文字以内）",
      "status": "進行中",
      "progress_note": "進捗メモ（200文字以内）"
    }
  ],
  "glossary": [
    {
      "term": "用語（64文字以内）",
      "definition": "定義（200文字以内）"
    }
  ],
  "world_rules": [
    {
      "rule": "世界観のルール（200文字以内）"
    }
  ]
}
```

**注意**:
- `foreshadowing[].type` は「設置」「回収」から選択すること。
- `relationships[].change_direction` は「改善」「悪化」「変化」「変化なし」から選択すること。
- `subplots[].status` は「未着手」「進行中」「完了」から選択すること。
- **サブプロット更新（最重要）**: シーンの内容に応じて、必ず1つ以上のサブプロットを更新または新規作成すること。「サブプロットなし」は禁止。サブプロットが存在しない場合は、シーン内で起こった出来事から新たなサブプロットを推測して作成すること。
- **伏線更新（最重要）**: シーンの内容に応じて、必ず1つ以上の伏線を設置または回収すること。「伏線なし」は禁止。

言語: {lang}
