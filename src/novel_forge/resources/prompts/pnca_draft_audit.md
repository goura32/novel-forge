# シーン草稿の審査（PNCA Draft Audit）

## 目的
生成されたシーン草稿 `content` を、対応する WriterView の制約に対して審査し、修正が必要な不備を `issues` に列挙する。不備がなければ空リストを返す。

## 応答方針
推測や好みで指摘しない。WriterView に明示された制約への違反のみを `issues` に挙げる。不備がなければ空リストを返す。

## 実行指示
- `severity` は `blocker`（出版不能）/ `major`（読者体験を損なう）/ `minor`（軽微）のいずれか。
- `detail` は違反箇所と根拠を具体的に記述する。
- 本文長が約500〜5000文字の範囲外、または説明・メタ注釈が混じる場合は `blocker` とする。

## 入力情報
### WriterView
{writer_view}

### 草稿
{draft}

## 出力仕様
下記のスキーマに適合する JSON のみ出力すること。

{schema}
