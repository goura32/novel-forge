# PNCA Scene Draft の改訂

## 目的

WriterViewを唯一の本文 authority とし、入力された草稿を audit issues の根拠に従って改訂する。指摘のない内容を壊さない。

## 応答方針

本文以外を出力せず、既存の語り・場面・設定の連続性を維持する。

## 実行指示

- `issues` の各指摘を本文で解消する。ただし、指摘された `required_beat` や `end_constraint` が実際の本文内にすでに完了として書かれている場合（audit の誤検出の可能性）、その beat/constraint に対する無理な書き直しは行わず、本文を維持する。`severity` が `blocker` で `constraint_kind` が `pov_fact` の場合は誤検出として維持してはならない。`draft_quote` の断定を削除または、POV人物が観測できる台詞・動作・表情・音・自身の推測へ改める。出力前に、そのissueの `draft_quote` が本文に残っていないことを確認する。
- `WriterView` は唯一の事実源である。`start_context` の場所・時刻・登場人物・現在状況、`end_constraints` の到達状態、`presentation_constraints` の視点・文体をすべて保持する。特に場所は `start_context` にある一つだけを使い、他の入力中の固有名詞から場所を推測・置換してはならない。
- issue が WriterView 内の複数箇所を引用していても、`start_context` と `end_constraints` を優先し、矛盾する語句は本文に持ち込まない。
- `issues[].field` に関係しないフィールドは原則として元の値を保持する。
- `Current draft.coverage.evidence[].draft_quote` はrender時点で検証済みの不変proofである。issue がその引用箇所を明示的に指摘していない限り、引用の本文上の文字列を一字も変更・削除・言い換えしてはならない。issue対応で周辺を改稿しても、coverage引用自体はそのまま残す。
- 整合性調整が必要な場合だけ、最小限変更する。
- 明示的な指摘がない限り変更しない。
- WriterViewにない設定・Canon・固有IDを追加しない。
- 本文は限定視点を守る。説明調・全知の断定・設定の要約を足さず、必要な脅威や背景は POV人物が知覚できる物、言動、行為、身体反応として書き直す。重要な展開を一文で処理せず、人物の選択と反応を場面内で描く。
- `required_beats` は順序どおりに本文で完了させる。未完の準備・試行・直前で終わらせない。beat が選択・発話・接触・到達状態を求めるときは、その状態が成立した直接の行為または台詞を本文に置く。
- `end_constraints` が「直後」「最後」「終わる」と指定する到達状態なら、その状態を本文最後の出来事にする。その後の受け取り、返答、視線移動、内省、時間経過を足さず、指定された動作が完了した文で本文を終了する。
- 日本語だけで自然な散文にする。簡体字・繁体字・ハングル・混在した外国語表記を使わない（例：「监护人」「后见人」「guardian」のような中国語・英語は絶対に書かない。「後見人」と日本語で書く）。また、入力のスキーマキー名（obligation・beat_index・end_constraint・required_beat 等）やスキーマ定義を `content` 本文に持ち込んではならない。
- 出力は JSON オブジェクトのみ。`content` は改訂後のシーン本文そのものを文字列として入れ、オブジェクトやスキーマを入れない。`"type"`・`"properties"` 等のスキーマ構造を output に含めない。

## 入力情報

### WriterView
{writer_view}

### Current draft
{draft}

### Protected render coverage (immutable)
{protected_coverage}

The quoted `draft_quote` strings in this coverage are protected verbatim text. Preserve every one in `content` unless an audit issue explicitly quotes that exact text.

### Audit issues
{issues}

## 出力仕様

下記のスキーマに適合する JSON のみ出力すること。

{schema}
