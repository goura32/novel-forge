# シーン設計生成

## 目的
親章の意図を満たし、物語に必要な Canon の追加・変更を **完全な `canon_patch`** として同時に設計する。

## 応答方針
物語上必要な Canon 追加・更新を明示するが、既存設定を推測で書き換えず、必要最小限の entity と patch だけを返す。

## Canon mutation の原則
- `pov_character_id`、`character_ids`、`location_id` には既存 Canon ID を完全一致で書く。
- この scene で初登場・以後の連続性管理が必要な entity は、`canon_patch` の対応 section の `create` に追加する。作成 payload の `id` は書かず、意味的で source 内一意な `creation_key` を書く。
- 同じ scene 内で新規 entity を POV / cast / setting / patch 内の他参照に使う場合は、final ID を推測せず `@created:<creation_key>` を書く。runtime が stable ID を発行する。
- 単なる情景の細部・一回限りの通行地点を無駄に Canon entity 化しない。後続 scene が固有状態・制約・関係・知識を参照するなら create する。
- 既存 entity の変化は create ではなく、対応する型付き update に書く。状態が変わらないなら update を捏造しない。
- Canon にない ID、表示名、推測 ID は既存参照欄に書かない。新しい概念は create + creation_key で表現する。

## `canon_patch` の構造
`canon_patch` は必要な section だけを返す object。各 section の操作は以下の strict CanonPatch に従う。

- `characters`: `create`、`state_updates`、`promote`、`identity_reveals`
- `collectives`: `create`、`state_updates`
- `locations`: `create`、`state_updates`
- `artifacts`: `create`、`custody_updates`、`condition_updates`
- `knowledge`: `create`、`holder_updates`、`visibility_updates`、`truth_status_transitions`
- `chronology`: `advance_to`、`deadline_updates`
- `relationships`: `create`、`updates`
- `foreshadowing`: `create`、`transitions`
- `subplots`: `create`、`updates`
- `glossary`: `create`

作成 payload は entity ごとの必須属性をすべて満たす。例: location は `creation_key` / `name` / `kind`、artifact は `creation_key` / `name` / `kind`、knowledge は `creation_key` / `proposition`、subplot は `creation_key` / `name` / `dramatic_question` / `stakes`。character create は identity・importance・tracking_level・narrative_function・continuity_card を必ず含める。relationship create は2人の participant と relationship state を持つ。

## 実行指示
`hook` は冒頭の読者関心、`turning_point` は場面の不可逆な転換、`ending_hook` は次場面を読む理由、`key_events` は実際の出来事を順に書く。新規 location をこの scene の舞台にする場合は `locations.create` と `location_id: "@created:<creation_key>"` を同時に返す。新規 character を登場させる場合は `characters.create` と `character_ids: ["@created:<creation_key>"]` を使う。

### Canon 制約の厳守
`canon_context` の world_rules / series_constraints / locations[].immutable_constraints / current_state は scene 開始時点の確定事実である。既存の人物・場所・物品・能力を表示名だけから推測しない。world rule で定義されない知覚・戦闘能力・道具の作用を追加しない。新規 entity を作ることは許されるが、既存設定と矛盾する能力・年代・関係・物理法則を作らない。

### 入力情報
### シリーズ企画
{series_plan}

### 巻と章
{volume_title}

### シーン種
{scene_seed}

### Canon
{canon_context}

**CanonPatch JSON Schema:** 以下は runtime が実際に検証する完全な JSON Schema である。`canon_patch` はこの schema に厳密に従い、独自 field を追加しない。

{canon_patch_schema}

## 出力仕様
下記のスキーマに適合する JSON のみ出力すること。

{schema}
