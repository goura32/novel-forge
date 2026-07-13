# シーン本文の生成（PNCA WriterView 投影）

## 目的
WriterView の4つの入力だけから、現在進行の行動・違和感から始まる完成日本語小説本文を生成する。

## 応答方針
Canon、作者だけの真相、stable ID を推測しない。POV が観測できる事実だけを使い、WriterView に書かれた制約をこのシーン開始時点の確定事実として扱う。

## 実行指示
約500〜5000字の自然な日本語本文を `content` に書く。説明・見出し・メタ注釈を本文に混ぜない。

### WriterView 制約の厳守
- `start_context`：シーン開始時点の確定事実。それと反対の状態・位置・関係性を推測で足さない。
- `narrative_contract`：このシーンが満たすべき展開・転換・結末の契約。
- `end_constraints`：シーン終了時に確定していなければならない状態。
- `presentation_constraints`：視点・文体・禁止事項などの提示制約。

これらに反する描写（解消済み人物の未解消扱い、明示されない道具機能の創出、Canon未定義の固有名詞導入など）は後続工程で固定化されるため書かない。

## 入力情報
### start_context
{start_context}

### narrative_contract
{narrative_contract}

### end_constraints
{end_constraints}

### presentation_constraints
{presentation_constraints}

## 出力仕様
下記のスキーマに適合する JSON のみ出力すること。

{schema}
