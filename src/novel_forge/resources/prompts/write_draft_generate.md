# シーン本文の生成

## 目的
投影済み writer context と直前 continuity handoff に忠実な完成日本語小説本文を生成する。

## 応答方針
Canon、作者だけの真相、stable ID を推測しない。POV が観測できる事実だけを使い、現在進行の行動・異変・欲求から始める。

## 実行指示
約500〜5000字の自然な日本語本文を `content` に書く。説明・見出し・メタ注釈を本文に混ぜない。

## 入力情報
### writer context
{writer_context}

### continuity handoff
{previous_summary}

## 出力仕様
下記のスキーマに適合する JSON のみ出力すること。

{schema}
