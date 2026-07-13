# PNCA Scene Contract Proposal の生成

## 目的

入力された Chapter Contract、固定された Canon frontier と Canon projection、scene request だけを根拠に、指定された一つの slot の実行可能な Scene Contract proposal を作る。

## 応答方針

frontier artifact ID、frontier digest、snapshot ID、artifact ID は出力しない。これらは repository が入力 provenance から materialize する。writer に渡せる authority は `writer_view` の四フィールドだけであり、Canon payload や stable ID を混ぜない。

## 実行指示

- `slot_id` は入力 scene request の `slot_id` と完全一致させる。
- Chapter Contract に存在しない slot を作らない。
- `canon_effect` が `none` の場合、`canon_patch` は省略する。
- `canon_effect` が `mutates` の場合だけ、frontier と slot authority に根拠を持つ non-empty `canon_patch` を返す。
- `requirement_dispositions` は parent requirement ledger が入力で明示された場合だけ、その各 requirement を一度ずつ扱う。この入力では parent ledger は提供されないため、必ず空配列 `[]` を返し、存在しない requirement を推測・作成しない。
- `admission_consumptions` は `admission_allowances` に列挙された allowance だけを消費できる。さらに、現在の `scene.request.slot_id` に対応する Chapter Contract `scene_slots[].allowed_admission_allowance_ids` の ID だけを消費できる。allowance 一覧は Volume 全体の候補であり、別 slot の候補は現在の scene では未承認である。各 item の `allowance_id` と `kind` はその定義に完全一致させる。許可がなければ空配列 `[]` を返し、ID・kind・上限を推測してはならない。
- Chapter Contract の `volume_purpose` は親の Volume Contract から固定された巻の到達目的であり、`series_final_resolution` はシリーズ終端で必ず回収する具体的な解決契約である。この値を否定・開始段階へ巻き戻し・別の目的へ置換してはならない。scene は巻目的を前進させる本文上の出来事を一つ以上必ず含める。
- `is_terminal_volume` が true の場合、ここはシリーズ最後の決着 scene である。`canon_effect` は必ず `mutates`、`canon_patch` は non-empty とし、`writer_view` の最後の required beat と end constraint に `series_final_resolution` を実現する可観測な解決（呪い解除、花冠、宮廷陰謀の打破、相互の愛情、王都の幸福）を置く。手がかりの発見、初対面、契約開始、次巻への先送りだけで終えてはならない。


- `writer_view` は一つの固定 POV だけで実行可能な本文指示にする。POV人物が直接知覚できない他者の感情・意図・確認・評価を、`end_constraints` や `required_beats` に置かない。相手の内面ではなく、POV人物に見える表情・姿勢・台詞・接触・距離・物の変化へ書き換える。
- 各 `required_beats` は単一の具体的な出来事として書く。「AまたはB」「〜するか」「〜など」の選択肢、抽象的な目的、複数の到達状態を混ぜない。最後の beat は固定 POV で直接観測できる一つの scene-end 行為または反応にする。
- `end_constraints` は最後の beat と同じ、固定 POV が観測できる単一の到達状態だけを指定する。物語全体の読者効果、相手の内面、次 scene の準備を指定しない。
- `writer_view` を含む自然言語値はすべて自然な日本語で書く。簡体字・繁体字・ハングル・混在した外国語表記を出力しない。

## 入力情報

### Chapter Contract
{parent}

### Canon frontier
{frontier}

### Canon projection
{canon_projection}

`seed` は不変の系列設定、`events` はこの frontier までに確定した時系列事実である。新規人物・場所・組織・artifact は許可済み admission を消費して `canon_patch` に明示登録し、既存 Canon と矛盾させない。

### Admission allowances
{admission_allowances}

### Scene request
{request}

## 出力仕様

下記のスキーマに適合する JSON のみ出力すること。

{schema}
