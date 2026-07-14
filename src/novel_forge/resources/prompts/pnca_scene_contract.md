# PNCA Scene Contract Proposal の生成

## 目的

入力された Chapter Contract、固定された Canon frontier と Canon projection、scene request だけを根拠に、指定された一つの slot の実行可能な Scene Contract proposal を作る。

## 応答方針

frontier artifact ID、frontier digest、snapshot ID、artifact ID は出力しない。これらは repository が入力 provenance から materialize する。writer に渡せる authority は `writer_view` の四フィールドだけであり、Canon payload や stable ID を混ぜない。

## 実行指示

- `slot_id` は repository が入力 scene request から固定して Scene Contract に materialize する authority であり、モデル出力には含めない。Chapter Contract に存在しない slot を作らない。
- この PNCA では全 scene が不可逆な前進を Canon に残す。`canon_effect` は必ず `mutates`、`canon_patch` は非空で、本文に観測可能な新しい事実（発見・決断・関係の転換・解決）として実装できる具体的な state change にする。`none`、導入の反復、既知事実の言い換えは不正である。
- `canon_effect` が `mutates` の場合だけ、frontier と slot authority に根拠を持つ non-empty `canon_patch` を返す。
- `requirement_dispositions` は parent requirement ledger が入力で明示された場合だけ、その各 requirement を一度ずつ扱う。この入力では parent ledger は提供されないため、必ず空配列 `[]` を返し、存在しない requirement を推測・作成しない。
- `admission_consumptions` は `admission_allowances` に列挙された allowance だけを消費できる。さらに、現在の `scene.request.slot_id` に対応する Chapter Contract `scene_slots[].allowed_admission_allowance_ids` の ID だけを消費できる。**入力 `### Admission allowances` が空配列 `[]` のとき、`admission_consumptions` は必ず空配列 `[]` にし、新規人物・場所・組織・artifact を `canon_patch` に作らない。過去巻・別slot・入力にない allowance IDを推測してはならない。** allowance 一覧は Volume 全体の候補であり、別 slot の候補は現在の scene では未承認である。各 item は `allowance_id` と `entity_id` だけを返す。`kind` は返さない。repository が入力の allowance 定義から `kind` を導出して materialize する。`allowance_id` と `entity_id` が allowance 定義と一致しない場合は拒否される。許可がなければ空配列 `[]` を返し、ID・上限を推測してはならない。
- **canon_seed または canon_projection に既に存在する entity（特に主人公や竜など系列初期からいる人物）は、新規 admission ではなく既存 Canon として参照する。** それらを `admission_consumptions` に入れてはならない。admission として消費するのは、この scene で**新たに**導入する人物・場所・組織・artifact だけである。例えば `{entity_id: "エルザ"}` や `{entity_id: "ルシオン"}` が canon_seed に定義済みなら、それらは admission 対象外であり `admission_consumptions` には含めない（slot の `allowed_admission_allowance_ids` が空でも正しい）。
- **同一 allowance_id は1つの scene 内で1回しか消費できない。** 例えば `org_1_vol1_faction`（faction 組織）の allowance が認可されていても、その scene では faction を**1つだけ**導入し、2つ目以降の派閥を新規 admission してはならない。`max_count` は巻全体の累積上限であり、1 scene で上限を使い切ってはならない。一度 admission した entity（faction 等）は、以降の scene では既存 Canon として参照し、再 admission しない。
- Chapter Contract の `volume_purpose` は親の Volume Contract から固定された巻の到達目的であり、`series_final_resolution` はシリーズ終端で必ず回収する具体的な解決契約である。この値を否定・開始段階へ巻き戻し・別の目的へ置換してはならない。scene は巻目的を前進させる本文上の出来事を一つ以上必ず含める。
- scene request の `is_terminal_scene` が true の場合だけ、ここはシリーズ最後の決着 scene である。`canon_effect` は必ず `mutates`、`canon_patch` は non-empty とし、`writer_view` の最後の required beat と end constraint に `series_final_resolution` を実現する可観測な解決を置く。花冠を完成し公爵の呪いを解除し、宮廷陰謀を公に打ち破り、互いの愛を言葉と行動で確認したうえで、冬の王都に幸福な生活が始まる到達状態まで本文で示す。手がかりの発見、初対面、契約開始、次巻への先送りだけで終えてはならない。
- `is_terminal_scene` が false の scene では、最終解決を先取りせず、現在の slot が担う一つの不可逆な前進だけを実現する。


- `writer_view` は object であり、`start_context`、`narrative_contract`、`end_constraints`、`presentation_constraints` はすべて object、`required_beats` は array にする。`writer_view` 自体やその object field を単一の文字列にしてはならない。
- `narrative_contract` は object で、少なくとも `{ "goal": "この scene で起こる具体的な変化", "progression": "Chapter の volume_purpose をどう前進させるか" }` のような key/value にする。抽象的な一文だけを `narrative_contract` に置かない。
- `start_context` は POV・場所・現在の観測可能な状態、`end_constraints` は scene end の観測可能な状態、`presentation_constraints` は POV・語調を、それぞれ key/value object で記述する。
- `writer_view` は一つの固定 POV だけで実行可能な本文指示にする。POV人物が直接知覚できない他者の感情・意図・確認・評価を、`end_constraints` や `required_beats` に置かない。相手の内面ではなく、POV人物に見える表情・姿勢・台詞・接触・距離・物の変化へ書き換える。
- 各 `required_beats` は単一の具体的な出来事として書く。配列の各要素は `description`（またはエイリアス `beat`）というキーで文字列を渡す：`{"description": "エリスが拉致された部屋で意識を取り戻す"}`。`beat_description` 等の別キーは使わない。選択肢・抽象的目的・複数到達状態を混ぜない。最後の beat は固定 POV で直接観測できる一つの scene-end 行為または反応にする。
- `end_constraints` は最後の beat と同じ、固定 POV が観測できる単一の到達状態だけを指定する。物語全体の読者効果、相手の内面、次 scene の準備を指定しない。
- `writer_view` を含む自然言語値はすべて自然な日本語で書く。簡体字・繁体字・ハングル・混在した外国語表記、および外国語の単語・フレーズ（台詞・独白を含む）を出力しない。中国語の字句を日本語の語として混ぜない。たとえば `安抚` は書かず、「慰める」「安心させる」と日本語で書く。

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
