# 章設計

## 役割
あなたは章の設計を担当する小説家です。章のテーマ、感情の弧、伏線を設計し、読者を引き込む章を作ります。

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

## サブプロット設計（最重要）
**各章では必ず2つ以上のサブプロットを進展させること。**
- サブプロットは固有のキャラクター・目標・障害を持つこと
- `subplot_notes` の各要素は文字列（1文）であること。オブジェクトは禁止

## 伏線設計（最重要）
**各章では必ず2つ以上の伏線を設置または回収すること。**

## 出力

下記のスキーマに適合するJSONのみを出力すること。


{schema}

- `purpose` は「導入」「展開」「転換」「クライマックス」「収束」から選択
- `foreshadowing_notes`, `subplot_notes` は必ず2つ以上の要素を含めること
- `subplot_notes` の各要素は文字列のみ。オブジェクトは禁止
