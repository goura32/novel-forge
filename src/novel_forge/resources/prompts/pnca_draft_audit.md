# シーン草稿の審査（PNCA Draft Audit）

## 目的
生成されたシーン草稿 `content` を、対応する WriterView の制約に対して審査し、修正が必要な不備を `issues` に列挙する。不備がなければ空リストを返す。

## 応答方針
推測や好みで指摘しない。WriterView に明示された制約への違反のみを `issues` に挙げる。不備がなければ空リストを返す。

## 実行指示
- `severity` は `blocker`（出版不能）/ `major`（読者体験を損なう）/ `minor`（軽微）のいずれか。
- `detail` は違反箇所と根拠を具体的に記述する。
- 限定 POV 違反は、POV人物が知り得ない他者の未発話の感情・意図・記憶・画面外の事実を断定した箇所だけに限る。POV人物から見える表情・眉・姿勢・動作、聞こえる声や音、自身の身体反応・感情・場内の解釈は有効な限定 POV 表現であり、推測上の危険だけで issue にしない。
- issue ごとに `constraint_kind`、根拠となる `writer_view_field`、草稿本文からの完全一致 `draft_quote` を必ず出す。引用が草稿内に存在しない、または WriterView field を特定できない場合は issue を出さない。
- `blocker` は `required_beat`、`end_constraint`、限定 POV の明白な事実断定、または `language_contamination` の実際の違反だけに限る。`pov_fact` を blocker にするには、引用が POV人物の知り得ない他者の未発話の感情・意図・記憶・画面外事実を断定していなければならない。品質上の提案、解釈の揺れ、可視の表情や動作からの場内解釈は `major` 以下にする。
- `language_contamination` では、本文の日本語小説として不自然な簡体字・中国語の語法、混入したラテン文字、名前の文字種崩れを、実際の完全一致引用がある場合だけ指摘する。WriterView に個別の言語 field がなければ `presentation_constraints` を根拠 field とする。

- `issues` は必ず「各要素が完全な object」の配列にする。空文字列 `""`、空リスト `[]` の入れ子、重複した空エントリを要素に含めてはならない。指摘がない場合は `{"issues": []}` を返す（要素ゼロの配列）。指摘が1件でも各要素は `severity`・`constraint_kind`・`writer_view_field`・`draft_quote`・`detail` の5フィールドを持つ object でなければならない。

## 入力情報
### WriterView
{writer_view}

### 草稿
{draft}

## 出力仕様
下記のスキーマに適合する JSON のみ出力すること。

{schema}
