# PNCA WriterView 改訂

## 目的

pre-render review の issue を解消した完全な replacement WriterView を返す。

## 応答方針

- `issues[].field` に関係しないフィールドは原則として元の値を保持する。整合性調整が必要な場合だけ、最小限変更する。明示的な指摘がない限り変更しない。issue が `required_beats[2]` ならその beat だけを修正し、`end_constraints`、他の beat、開始状況、物語目的を変更しない。issue が `end_constraints` なら end_constraints だけを単一の終点に直す。Canon、artifact ID、要約、audit、新しい plot fact を追加しない。

## 実行指示

- 固定した一人の限定 POV を維持する。他者の内面を要求する内容は、POV が観察できる台詞、表情、動き、距離、接触、物の変化に直す。
- 各 required beat は順序を持つ一つの具体的出来事にする。最後の beat と end_constraints は同じ直接観測可能な終了状態を記述する。
- presentation_constraints は限定 POV を要求できるが、POV 人物の即時の知覚・感情・解釈を禁止しない。
- 自然な日本語だけを使う。required beat 内で「または」「〜か」「など」による選択肢を作らない。

## 改訂対象

### WriterView
{writer_view}

### Review issues
{issues}

## 出力仕様

下記のスキーマに適合する JSON のみ出力すること。

{schema}
