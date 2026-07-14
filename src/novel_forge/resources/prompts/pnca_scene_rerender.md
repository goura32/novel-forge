# ブロッカー付きシーンの再render（PNCA Scene Rerender）

## 目的
既存草稿のcoverage引用にblockerが重なり、部分改稿では不変proofと品質修正を両立できない。既存草稿・audit・coverageを変更せず、新しい独立草稿を生成する。

## 応答方針
既存artifactを修正・上書きせず、auditで示された違反を解消する新しい草稿だけを返す。

## 実行指示
- `WriterView` を唯一の事実源として、場所、時間、登場人物、視点、required beats、end constraintsを満たす完成したscene本文を `content` に出力する。
- `Audit issues` の各blockerを必ず解消する。`draft_quote` をそのまま残さず、限定POVではPOV人物が観察できる台詞・動作・表情・音・自身の推測だけを書く。
- `Previous draft` は編集対象でも事実源でもない。そこにだけある設定・文・coverageを新しい本文へ持ち込まない。
- 新しい本文のcoverageは別taskが本文から選び直す。coverageオブジェクトや引用を出力してはならない。
- 日本語だけで自然な小説本文を書く。簡体字・繁体字・中国語の語法、不自然なラテン文字を混入させない。出力直前に `content` 全体を読み直し、台詞・独白・地の文のいずれにも日本語以外の単語・語法・文字種が一つも残っていないことを自分で確認してから返す。

## 入力情報
### WriterView
{writer_view}

### Previous draft
{draft}

### Audit issues
{issues}

## 出力仕様
下記のスキーマに適合する JSON のみ出力すること。

{schema}
