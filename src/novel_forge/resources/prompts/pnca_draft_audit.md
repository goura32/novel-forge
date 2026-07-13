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
- `blocker` は `required_beat`、`end_constraint`、`language_contamination` の明白な違反だけに使う。`quality` と `pov_fact` は blocker にしてはならない。

## 入力情報
### WriterView
{writer_view}

### 草稿
{draft}

## 出力仕様
下記のスキーマに適合する JSON のみ出力すること。

{schema}
