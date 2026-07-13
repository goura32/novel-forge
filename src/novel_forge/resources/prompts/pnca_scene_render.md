# シーン本文の生成（PNCA WriterView 投影）

## 目的
WriterView の4つの入力だけから、現在進行の行動・違和感から始まる完成日本語小説本文を生成する。

## 応答方針
Canon、作者だけの真相、stable ID を推測しない。POV が観測できる事実だけを使い、WriterView に書かれた制約をこのシーン開始時点の確定事実として扱う。

## 実行指示
約500〜5000字の自然な日本語本文を `content` に書く。説明・見出し・メタ注釈を本文に混ぜない。簡体字・繁体字・ハングル・混在した外国語表記を使わない。

限定視点では、POV人物が今この場で知覚・記憶・推論できることだけを書く。第三者の感情・意図・評価・関係性を事実として断定しない。見える表情や動作も、内面の証明にはしない。相手について書くときは、台詞・物理的動作・外見・音・POV人物自身の身体反応に留める。社会状況、陰謀、呪い、過去の経緯、脅威は、感覚、具体的な物、相手の言動、行為、その場で生じる身体反応として場面内に現し、作者の解説や全知の断定で要約しない。WriterView が求める展開・状態変化も、一文の説明で飛ばさず、POV人物の選択と反応の連鎖として本文に置く。

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

### required_beats
{required_beats}

`required_beats` は、この scene の本文内で順番に観測できなければならない不可欠な行動・反応・到達点である。各 beat を説明文で済ませず、POV人物が知覚する具体的な行為・台詞・反応として実現する。準備・試行・直前で止めず、beat が要求する選択・発話・接触・到達状態を本文内で完了させてから、最後の beat の後で scene を閉じる。

`coverage.evidence` は本文ではない。各 required beat と end constraint について、完了を直接示す `content` 内の完全一致文を一つずつ引用する。要件が完了していないなら引用を捏造せず、先に本文を完成させる。

## 出力仕様
下記のスキーマに適合する JSON のみ出力すること。

{schema}
