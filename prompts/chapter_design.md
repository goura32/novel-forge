# 章設計

## 指示
以下の情報に基づいて、この章の詳細設計を生成せよ。

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

## 前章の結果
{previous_chapter_outcome}

## 前巻の主要な結果
{previous_volume_summary}

## 設計原則

1. **章のテーマ (theme)**: この章が描く核心的なテーマや問い。例: 「信頼の崩壊」「選択の代償」
2. **感情の弧 (emotional_arc)**: 読者がこの章で辿る感情的な変化。例: 「不安→緊張→絶望→希望」
3. **伏線メモ (foreshadowing_notes)**: この章で設置する伏線、回収する伏線、次章への引き継ぎ事項
4. **サブプロットメモ (subplot_notes)**: この章で進展させるサブプロット、関わるキャラクター

## 出力スキーマ

`chapter_design.json` に適合する JSON を出力すること。JSON Schema の各フィールド定義・required・maxLength に従うこと。

**以下のJSONテンプレートの構造とフィールド名を厳守すること。フィールド名や構造を変更しないこと。**

```json
{
  "title": "",
  "purpose": "",
  "theme": "",
  "emotional_arc": "",
  "foreshadowing_notes": [],
  "subplot_notes": []
}
```

**注意**:
- 上記テンプレートのキー名は変更しないこと。値のみを埋めること。
- **すべてのフィールドを必ず出力すること。省略禁止。** スキーマに存在するすべてのキーに対応する値を記述すること。
- `purpose` は「導入」「展開」「転換」「クライマックス」「収束」から選択すること。
- **配列フィールド（`foreshadowing_notes`, `subplot_notes`）は必ず2つ以上の要素を含めること。空配列にしないこと。**

言語: {lang}
