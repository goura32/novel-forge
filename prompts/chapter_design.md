# 章設計の生成

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
- 章の役割: {chapter_purpose}  （この値をそのまま `purpose` フィールドに使用。必ず `導入` `展開` `転換` `クライマックス` `収束` のいずれか）

## 前章の結果

{previous_chapter_outcome}

## 前巻の主要な結果

{previous_volume_summary}

## 重要（必須）
- `purpose` フィールドは **必ず `導入` か `展開` か `転換` か `クライマックス` か `収束` のいずれか1単語のみ**。説明文・修飾子付きの文言は不可。
- シーン構成における各フィールド（特に `setting`）はスキーマの minLength を絶対超過しないこと。`setting` が minLength=6 なら最低でも「部屋」「窓辺」などの6文字以上で出力。

## 出力構造

下記のスキーマに適合する JSON のみ出力すること。
{schema}