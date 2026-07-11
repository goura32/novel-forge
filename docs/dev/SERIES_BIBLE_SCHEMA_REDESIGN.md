# Series Bible v2 — Canon Event Architecture

> **状態：未実装 target specification**
>
> **この文書が Series Bible v2 の唯一の仕様正本である。**
> 本仕様は新規 v2 プロジェクトだけを対象とする。既存方式からの移行・読込変換・バックアップ対応は、この設計の要件として定義しない。

---

## 1. 決定

Series Bible は、文字列照合で更新する現在の `bible.json` から、**event replay で再構築する正規化 Canon** へ破壊的に移行する。

```text
plan seed + Canon Event log  ──replay──>  bible.json
        正本                              materialized view
```

- `bible_seed.json` と `canon_events.jsonl` が Canon の正本である。
- `bible.json` はキャッシュであり、event replay の結果だけを保存する。
- Canon を変更できるのは、**review 合格済み `scene_design.canon_patch`** だけである。
- volume / chapter design は構造化された **Design Intent** を保存するが、Canon を変更しない。
- write は `scene_design` と執筆用の draft / scene summary だけを読む。Canon / event を読まない。
- export は readiness report のため Canon を read-only で読めるが、Canon / event を変更しない。
- draft 本文から事実を抽出して Canon に反映する runtime discovery は存在させない。

---

## 2. 用語と正本

| 用語 | 定義 | 正本性 |
|---|---|---|
| **Plan Seed** | plan が確定した時点の初期 Canon | 正本 |
| **Design Intent** | volume / chapter / scene の「扱う予定」。未発生の構想 | design artifact の正本。Canon ではない |
| **Canon Patch** | review 合格済み scene が明示した型付き Canon 変更 | Canon Event に格納 |
| **Canon Event** | patch、review 根拠、ID 割当、source を持つ不変レコード | 正本 |
| **Canon** | seed + active event replay の現在値 | `bible.json` は materialized view |
| **Writer context** | draft / scene summary の短期 prose context | Canon でも Design Intent でもない |

`Blackboard.facts` と `Blackboard.continuity_notes` は runtime で発見した状態を第二 Canon にするため、v2 で削除する。`scene_summaries` は write 用の短期コンテキストに限り残せるが、design / Canon 更新の根拠にはしない。

---

## 3. Identity・順序・再設計

### 3.1 source identity と表示順を分離する

scene の Canon source は `volume/chapter/scene` 番号では識別しない。番号は scene の追加・削除・並び替えで変わるためである。

```jsonc
{
  "scene_id": "scn_01J4T4C8R2K9", // 不変・不透明な source identity
  "location": {"volume": 1, "chapter": 2, "ordinal": 3}, // 表示と replay 順
  "revision": 2
}
```

- `scene_id` は chapter の構造が初めて確定したときにシステムが発行する。LLM は発行・変更しない。
- `location` は表示用・replay order 用であり、同一 source 判定には使わない。
- scene 設計を改訂しても `scene_id` は維持する。
- scene を追加すると新しい `scene_id` を発行する。削除した scene は明示的に `removed_scene_ids` へ列挙する。
- description、title、内容類似度、位置番号から source を自動対応させることは禁止する。

### 3.2 構造再設計は transaction として扱う

scene の挿入・削除・並べ替えを含む volume / chapter 再設計は、単一の `replace_scene_event()` では処理しない。

```text
replace_design_segment(segment, scene_mapping, removed_scene_ids, replacement_events)
```

この transaction は次を満たさなければならない。

1. 既存 `scene_id` の維持・削除・置換を明示する。
2. 削除 source が作成した entity を参照する後続 event を dependency graph で検出する。
3. dangling reference があれば transaction を拒否し、再設計が必要な依存 source を返す。
4. replacement event 群が揃った時だけ、seed から一度に replay する。

黙った event の付け替え、内容類似度による scene 対応、部分一致による entity 再接続は禁止する。

### 3.3 新規 entity の stable ID

既存 entity は Bible slice にある stable ID だけで参照する。LLM は stable ID、UUID、連番を新規発行しない。

新規 entity は source 内で一意な `creation_key` を返す。

```jsonc
{"creation_key": "sister_voice", "description": "石の中から妹の声がする"}
```

manager は最初の event 適用時に `scene_id + creation_key` に stable ID を割り当て、event の `created_entity_ids` に永続化する。同じ source の改訂では同じ `creation_key` に同じ ID を再利用する。

### 3.4 typed reference

ID と creation key は文字列で混在させない。

```jsonc
{"id": "fh_001"}
{"creation_key": "sister_voice"}
```

- 既存 entity 参照は `{ "id": "fh_001" }`。
- 同一 patch 内で作る entity の参照は `{ "creation_key": "sister_voice" }`。
- manager は create を先に解決し、型・存在・参照先の整合性を検証する。

---

## 4. Canon v2 の構造

すべての Pydantic model は `extra="forbid"` とする。JSON Schema は Pydantic model から生成する成果物であり、手書き二重管理をしない。

```jsonc
{
  "schema_version": 2,
  "series": {
    "id": "series",
    "title": "怪の街 記憶の礎",
    "logline": "…",
    "genres": ["ファンタジー"],
    "target_audience": "大人向けの叙情的ファンタジー読者",
    "themes": ["記憶", "喪失"],
    "tone": "叙情的で緊迫",
    "selling_points": ["記憶を刻む魔法", "姉妹の秘密"],
    "constraints": [{"id": "constraint_001", "statement": "死者は蘇生できない", "scope": "series"}]
  },
  "characters": [{
    "id": "char_001",
    "identity": {"kind": "named", "display_name": "アリーン", "aliases": []},
    "importance": "core",
    "tracking_level": "full",
    "narrative_function": "主人公／記憶彫刻師",
    "profile": {"personality": "寡黙", "motivation": "妹を探す", "appearance": "…", "background": "…", "arc": "…", "flaw": "…"},
    "continuity_card": {"current_state": "石の都へ到着した", "current_location": {"id": "loc_stone_city"}, "distinguishing_traits": "石粉の残る指先", "known_constraints": []},
    "affiliations": [],
    "last_changed_by": {"scene_id": "scn_01J4T4C8R2K9", "event_digest": "sha256:…"}
  }, {
    "id": "char_014",
    "identity": {"kind": "role_anchored", "display_name": "北門の薬師", "aliases": []},
    "importance": "minor",
    "tracking_level": "continuity",
    "narrative_function": "主人公へ禁制薬の手がかりを渡す薬師",
    "profile": null,
    "continuity_card": {"current_state": "主人公の通行証を疑っている", "current_location": {"id": "loc_stone_city"}, "distinguishing_traits": "左手の青い染料痕", "known_constraints": ["王都の監察官に借りがある"]},
    "affiliations": [{"collective": {"id": "grp_north_gate"}, "role": "薬師", "status": "active"}],
    "last_changed_by": {"scene_id": "scn_…", "event_digest": "sha256:…"}
  }],
  "collectives": [{
    "id": "grp_north_gate", "kind": "organization", "name": "北門衛兵隊",
    "function": "北門の検問と治安維持", "current_state": "偽造通行証の流通を警戒している",
    "stance_toward_characters": [{"character": {"id": "char_001"}, "stance": "suspicious", "reason": "通行証に不審な印がある"}],
    "last_changed_by": {"scene_id": "scn_…", "event_digest": "sha256:…"}
  }],
  "world_rules": [{"id": "rule_001", "name": "石媒律", "statement": "魔法は石を媒体とする", "scope": "world", "exceptions": []}],
  "glossary": [{"id": "term_001", "term": "彫刻師", "definition": "記憶を石に刻む職能"}],
  "relationships": [{
    "id": "rel_001", "participant_ids": ["char_001", "char_002"],
    "structural_bonds": [{"kind": "kinship", "label": "姉妹", "direction": "symmetric"}],
    "shared_state": {"cooperation": "conditional", "openness": "guarded", "central_tension": "妹の行方を巡り互いに秘密を抱える", "current_arrangement": "石都を共同で調査する"},
    "perspectives": [
      {"character_id": "char_001", "attitude": "protective", "trust": "guarded", "desire_from_other": "真相を話してほしい", "boundary": "危険な単独行動は許さない"},
      {"character_id": "char_002", "attitude": "wary", "trust": "conditional", "desire_from_other": "対等に扱われたい", "boundary": "命令には従わない"}
    ],
    "arc_summary": "再会後の敵対は共同調査へ変わったが、不信は残っている。",
    "lifecycle": "active", "last_changed_by": {"scene_id": "scn_…", "event_digest": "sha256:…"}
  }],
  "foreshadowing": [{
    "id": "fh_001", "description": "石の中から妹の声がする", "status": "planted",
    "planted_by": {"scene_id": "scn_…", "event_digest": "sha256:…"}, "resolved_by": null,
    "intended_payoff": "妹の記憶が石に封じられた事実の判明",
    "related_character_ids": ["char_001"], "related_subplot_ids": ["sp_001"]
  }],
  "subplots": [{
    "id": "sp_001", "name": "石都の陰謀", "status": "active",
    "dramatic_question": "長老はなぜ記憶石を集めているのか", "stakes": "石都の住民の記憶と主人公の妹の手がかりが失われる",
    "current_state": "長老の関与が判明した",
    "related_character_ids": ["char_001"], "related_foreshadowing_ids": ["fh_001"],
    "last_changed_by": {"scene_id": "scn_…", "event_digest": "sha256:…"}
  }]
}
```

### 4.1 Character Tier と Cast

| 区分 | Canon entity | 管理粒度 | 用途 |
|---|---:|---|---|
| `core` | 必須 | `full` profile、関係 Arc、長期状態 | 主人公、主要対立者、恋愛相手 |
| `supporting` | 必須 | `continuity` または `full`、必要な関係 Arc | 相棒、師匠、繰返し登場する協力者・対立者 |
| `minor` | 条件付き | `continuity_card` のみ | 再登場する役職人物、将来の制約を残す端役 |
| `local_role` | 保存しない | scene artifact 限定 | 一度だけの店員、匿名の衛兵、通行人 |
| `collective` | 必要時に `grp_*` | 集団の立場・状態 | 組織、派閥、共同体、家 |

- `importance` は物語上の重み、`tracking_level` は Canon に保持する情報量であり、同義ではない。`continuity_card.current_location` は再訪する Location の typed ref とし、未確定時だけ `null` にする。
- `identity.kind=named` は固有名を持つ人物、`role_anchored` は「北門の衛兵」のように役割・所属で同一性を保つ再登場人物である。
- `local_role` は `Character` ではない。scene の表示 label・人数・scene function だけを持ち、Canon Patch、Relationship Arc、再登場同一視を行わない。
- 名前のない人物を再登場・関係・秘密・負債・所属・死亡/離脱などで後続が参照する必要が生じた時だけ、明示 `characters.create` で `role_anchored` entity にする。
- 群衆・組織・派閥を Character や Relationship Arc の participant として扱わない。個人との所属・権限は `affiliations`、集団の対人物 stance は `Collective` に持つ。

### 4.2 Relationship Arc

Relationship は単純な人物ペアや方向付き edge ではなく、**二者の継続的な物語 Arc** である。`participant_ids` は異なる `char_*` 2件を ID 昇順で正規化する。非対称性は別 edge を作らず、同じ Arc 内の `perspectives` で表す。

- `structural_bonds` は姉妹、師弟、主従、元恋人など、Arc の土台となる持続的事実である。
- `shared_state` は協力・開示・中心葛藤・現在の取決めを持つ。
- `perspectives` は participant ごとにちょうど1件あり、態度・信頼・相手に求めること・境界を分ける。
- `arc_summary` は現在までの変化を短く記録する。長い履歴は Canon Event replay に存在するため、別 history 配列を持たない。
- Relationship Arc は Core / Supporting 間で、継続する対立・協働・秘密・負債・約束が物語設計を制約する時に作る。Minor を participant に含めるのは再登場に加えて同じ条件または親 Design Intent がある場合だけとする。Local / Collective との Arc は作らない。

### 4.3 正規化規則

| entity | ID | 参照 | 禁止 |
|---|---|---|---|
| character | `char_*` | relationship / subplot / foreshadowing / affiliation | 人物名を外部キーにする、本文から自動昇格する |
| collective | `grp_*` | affiliation / collective stance / knowledge holder | 個人の Relationship Arc participant にする |
| location | `loc_*` | character current location / artifact custody / Context scope | 場所名の部分一致で同一視する |
| artifact | `art_*` | knowledge / Context scope | 物品名の部分一致で同一視する |
| knowledge | `know_*` | Context scope / holder matrix | proposition 文字列を主キーにする、truth と holder state を混ぜる |
| deadline | `deadline_*` | Context scope / chronology | 自由文の期限説明で更新対象を決める |
| relationship | `rel_*` | 2 participant character | participant 順・方向から非対称感情を推測する |
| foreshadowing | `fh_*` | character / subplot | description 部分一致で回収する |
| subplot | `sp_*` | character / foreshadowing | name を主キーにする |
| world rule | `rule_*` | plan seed / approved correction | scene patch で変更する |
| glossary | `term_*` | 任意 | term 文字列だけで更新対象を決める |

### 4.4 状態遷移と昇格

| entity | 通常 scene patch の許可遷移 |
|---|---|
| foreshadowing | `planted → resolved` / `planted → abandoned` |
| subplot | `active → resolved` / `active → abandoned` |
| relationship | `shared_state` / `perspectives` / `arc_summary` の明示 update、`active → resolved` |
| character | `continuity_card.current_state` / `current_location` 更新、明示 `minor → supporting → core` 昇格 |
| collective / location | `current_state` / stance / membership の明示 update |
| artifact | custody / condition の明示 update |
| knowledge | holder state / visibility / `contested → confirmed / false_belief` の明示 update |
| chronology | marker の単調前進、deadline `active → resolved / missed` |

- `resolved → planted`、`abandoned → active`、`relationship.resolved → active` の逆遷移は通常 patch で禁止する。過去 event の置換後に replay した結果として状態が変わることだけを許可する。
- `characters.promote` は ID、alias、affiliation、既存 Canon state を保持する。`profile_additions` は空欄だった profile field の補完だけを許可する。既存 `profile=null` の Minor は、この操作で partial profile を初期化できるが、既存値の訂正は `canon_correction` に限る。
- `identity_reveal` は `role_anchored` の display name / alias を追加して `named` に変える明示操作であり、名前類似による merge ではない。
- world rule、series constraint、既存 character profile の訂正は、plan seed または人間承認済み `canon_correction` workflow だけが変更できる。

### 4.5 Canon item inventory

Canon は「後続の design / review / write の選択肢を制約する、再利用可能な確定情報」だけを持つ。各 scene の出来事全文や、作者の作業メモを蓄積する場所ではない。

| entity | Canon に置く情報 | 保存しない情報 | 保存条件 |
|---|---|---|---|
| `series` | logline、genre、target audience、theme、tone、series constraint | 巻ごとの予定、作者メモ | 常に seed |
| `world_rule` / `glossary` | 例外・代償を含む世界法則、再利用する用語の確定定義 | その場限りの比喩、未確定の噂 | 継続参照される時 |
| `character` | identity、現在状態、所属、継続する制約、人物 Arc に必要な profile | 一度きりの通行人、本文の一時感情 | §4.1 の tier 基準 |
| `collective` | 組織・派閥・共同体の権限、立場、継続状態 | 単発の群衆描写 | 後続 scene の制約になる時 |
| `location` | 再訪する場所の identity、アクセス/物理制約、現在状態 | 一度きりの背景描写 | 場所・破壊・封鎖・支配状態が後続に影響する時 |
| `artifact` | 固有の能力・制約・custody・状態を持つ重要物 | 汎用品、単発の小道具 | custody・能力・損壊が後続に影響する時 |
| `relationship` | 二者の durable bond、共有状態、非対称 perspective、Arc summary | 単発会話の印象 | §4.2 の Arc 基準 |
| `knowledge` | 真実・誤認・秘密と、人物/集団ごとの知識状態 | 全登場人物の自明な常識、本文の単なる回想 | 知識差が後続の選択・POV・伏線を制約する時 |
| `chronology` | 現在の物語時刻、進行中の期限、時刻依存の制約 | 全 scene の重複要約 | 時間経過・期限が意味を持つ時 |
| `foreshadowing` | 意図して設置した約束と回収状態 | 単なる雰囲気、偶然の細部 | 後続で回収/反転する設計意図がある時 |
| `subplot` | 独立して追跡する二次 Arc の問い・stakes・現在状態 | main plot の言い換え、chapter 内だけの小事件 | 複数 scene / chapter をまたぐ時 |

`facts`、`continuity_notes`、汎用 `story_events` は Canon entity にしない。技術的な変更履歴は `CanonEvent`、本文の近接文脈は writer-local `scene_summary`、永続的な事実は上表の domain entity にそれぞれ置く。これにより同じ出来事を複数の正本へ写すことを防ぐ。

### 4.6 Location / Artifact / Knowledge / Chronology

```jsonc
{
  "locations": [{
    "id": "loc_stone_city", "name": "石の都", "kind": "city",
    "parent_location": null,
    "immutable_constraints": ["夜間は城門が封鎖される"],
    "current_state": "北門は偽造通行証の検査を強化している",
    "last_changed_by": {"scene_id": "scn_…", "event_digest": "sha256:…"}
  }],
  "artifacts": [{
    "id": "art_memory_stone", "name": "記憶石", "kind": "magical_item",
    "properties": ["触れた者の記憶を一つだけ再生する", "再生後にひびが入る"],
    "custody": {"kind": "character", "id": "char_001"},
    "condition": "ひびが一本入っている", "narrative_significance": "妹の記憶の手がかり",
    "last_changed_by": {"scene_id": "scn_…", "event_digest": "sha256:…"}
  }],
  "knowledge": [{
    "id": "know_memory_stone_origin", "proposition": "妹の記憶は記憶石に封じられている",
    "truth_status": "confirmed", "visibility": "secret",
    "holders": [
      {"holder": {"kind": "character", "id": "char_001"}, "state": "suspects"},
      {"holder": {"kind": "character", "id": "char_002"}, "state": "knows"}
    ],
    "related_entity_refs": [{"kind": "artifact", "id": "art_memory_stone"}],
    "last_changed_by": {"scene_id": "scn_…", "event_digest": "sha256:…"}
  }],
  "chronology": {
    "current_marker": {"ordinal": 3, "label": "第3日・夜"},
    "active_deadlines": [{"id": "deadline_gate_close", "statement": "夜明けまでに北門を越えなければ追手に包囲される", "due_marker": {"ordinal": 4, "label": "第4日・夜明け"}, "status": "active"}]
  }
}
```

- `Location.immutable_constraints` は地理・法・物理の変わりにくい制約であり、通常 patch では訂正しない。`current_state` は封鎖、損壊、支配、天候などの後続制約を明示 update できる。
- `Artifact.properties` は能力・代償などの確定仕様で、通常 patch では訂正しない。動的所在は `custody: EntityRef(kind=character|collective|location, id)` の一点だけで表し、scene patch は custody と condition だけを更新できる。Character が保持する Artifact の場所は Character の `current_location` から導出し、holder と location の二重保存をしない。
- `Knowledge.proposition` は作者視点の命題であり、`truth_status` は `confirmed` / `contested` / `false_belief`、holder state は `knows` / `suspects` / `believes` / `unaware` とする。holder は Character または Collective の `EntityRef(kind, id)`、`related_entity_refs` は mixed entity 用の `EntityRef(kind, id)` とし、真実そのものと人物の認識を混ぜない。通常 patch は scene outcome の明示根拠がある `contested → confirmed` または `contested → false_belief` だけを許可し、確定済み status や proposition の訂正は `canon_correction` に限る。Knowledge は「誰が何を知るか」、Foreshadowing は「何を約束して後で回収するか」であり、必要なら typed ref でリンクしても同一 entity に統合しない。
- Subplot は `dramatic_question`、`stakes`、`current_state` を必須とする。`name` だけで main plot を言い換えたり、問いと stakes がない chapter 内小事件を永続 subplot にしない。
- `Chronology` は singleton である。時刻・期限が物語上意味を持つ場合だけ seed / scene patch で更新し、scene ごとの重複要約や技術的 event order を保存しない。`current_marker.ordinal` と `due_marker.ordinal` は validator が比較する非負整数、`label` は読者向け表示文字列である。

---

## 5. Design Intent

Design Intent は Canon ではなく、volume / chapter / scene artifact に保存する構造化された予定である。現行の `foreshadowing_notes[]` / `subplot_notes[]` だけに依存しない。

```jsonc
{
  "design_intent": {
    "foreshadowing": [{"intent_key": "sister_voice", "action": "plant", "target_scene_id": "scn_…"}],
    "subplots": [{"intent_key": "stone_city_conspiracy", "action": "advance", "target_scene_id": "scn_…"}],
    "relationship_arcs": [{
      "relationship": {"id": "rel_001"},
      "action": "shift",
      "target_scene_id": "scn_…",
      "expected_effect": "師弟の敵対を限定的な共同調査へ移す"
    }],
    "cast": [{
      "target_scene_id": "scn_…",
      "entries": [
        {"kind": "character", "character": {"id": "char_001"}},
        {"kind": "local_role", "label": "港の検問兵", "count": "one", "scene_function": "偽造通行証への疑念を示す"}
      ]
    }]
  }
}
```

- Intent は Canon ID を発行せず、Canon の `planned` state を作らない。
- `relationship_arcs.action` は `introduce` / `pressure` / `reveal` / `shift` / `rupture` / `repair` / `commit` / `resolve` のみとする。
- `cast` の `local_role` は scene artifact にだけ存在する。一度きりの label を Character entity や Relationship Arc に変換しない。
- scene patch が実際に create / transition したときだけ Canon Event を作る。
- scene review は親 chapter / volume の Intent と scene patch の整合を検証する。
- 既存の自由文 notes は著者向け補助説明として残せても、Canon 更新・検証・参照の根拠にはしない。

### 5.1 Context scope

Design Intent は、予定だけでなく **どの Canon entity がその設計の前提か**を typed reference で宣言する。

```jsonc
{
  "context_scope": {
    "pov_character": {"id": "char_001"},
    "setting": {"id": "loc_stone_city"},
    "required_refs": [
      {"kind": "relationship", "id": "rel_001"},
      {"kind": "artifact", "id": "art_memory_stone"},
      {"kind": "knowledge", "id": "know_memory_stone_origin"},
      {"kind": "deadline", "id": "deadline_gate_close"}
    ]
  }
}
```

- `required_refs` は LLM が選んだ曖昧な検索語ではなく、`kind + id` を持つ前段確定の typed reference である。homogeneous slot の `{id}` と混用しない。
- slice builder は `context_scope`、scene cast、setting、POV、parent Intent を起点に、必要な関係・所属・場所・未解決 thread を決定的に閉包する。
- 必須 world rule / series constraint / scope に関係する POV knowledge / scope に関係する active deadline は token budget によって脱落させない。
- context scope に存在しない新規 Minor / Local role は scene design の `canon_patch.create` または local cast で明示し、名前類似から既存 entity を推測しない。

### 5.2 更新権限と参照先

| entity | 初期作成 | 通常更新 | 訂正/破壊的変更 | 主な reader |
|---|---|---|---|---|
| series / constraint / world rule | Plan Seed | 不可 | 人間承認 `canon_correction` / reset | volume, chapter, scene design, review |
| glossary | Plan Seed または scene patch create | 新規 create のみ | 定義変更は `canon_correction` | scope 内の design / review / writer projection |
| core / known supporting / initial collective | Plan Seed | state、所属、明示昇格 | profile / identity 訂正は correction | scope 内の design / review |
| minor / role-anchored character | review 合格 scene patch create | state、identity reveal、昇格 | correction | scene design / review |
| location | Plan Seed または scene patch create | current state | immutable constraint の訂正は correction | setting を使う design / review / writer projection |
| artifact | Plan Seed または scene patch create | custody、condition | property の訂正は correction | scope 内の design / review / writer projection |
| collective | Plan Seed または scene patch create | state、stance、membership | immutable identity の訂正は correction | scope 内の design / review |
| relationship Arc | Plan Seed または scene patch create | shared state、perspective、summary、resolve | structural bond の訂正は correction | participant を含む design / review / writer projection |
| knowledge | Plan Seed または scene patch create | holder knowledge state、visibility、`contested` の確定 | proposition / 確定済み truth status の訂正は correction | author-context design / review、POV-filtered writer projection |
| chronology | Plan Seed または scene patch | marker、deadline state | past marker の訂正は correction | time-sensitive design / review / writer projection |
| foreshadowing / subplot | Plan Seed または scene patch create | 明示 transition / current state | 過去事実の訂正は correction または source replacement | relevant design / review / export readiness |

通常更新はすべて review 合格済み `scene_design.canon_patch` からの Canon Event に限る。volume / chapter は Context scope と Intent を作るが Canon を更新しない。export は全 entity を read-only で検査し、write は §6.2 の projection 以外を読まない。

---

## 6. scene design の `canon_patch`

`canon_patch` を持つのは review 合格済み `scene_design` だけである。

```jsonc
{
  "canon_patch": {
    "characters": {
      "create": [{
        "creation_key": "north_gate_guard",
        "identity": {"kind": "role_anchored", "display_name": "北門の衛兵", "aliases": []},
        "importance": "minor", "tracking_level": "continuity",
        "narrative_function": "主人公の通行証を疑う検問担当者",
        "profile": null,
        "continuity_card": {"current_state": "主人公を監視している", "current_location": {"id": "loc_stone_city"}, "distinguishing_traits": "右頬の古傷", "known_constraints": []},
        "affiliations": [{"collective": {"id": "grp_north_gate"}, "role": "衛兵", "status": "active"}]
      }],
      "state_updates": [{"character": {"id": "char_001"}, "current_state": "妹の声を聞き捜索を決意した"}],
      "promote": [{
        "character": {"id": "char_014"}, "to_importance": "supporting",
        "profile_additions": {"motivation": "北門を守るため違法通行者を見逃せない"},
        "reason": "主人公を追う準対立者として継続登場する"
      }],
      "identity_reveals": [{"character": {"id": "char_014"}, "display_name": "ガルド", "add_aliases": ["北門の衛兵"]}]
    },
    "collectives": {"create": [], "state_updates": []},
    "locations": {"create": [], "state_updates": []},
    "artifacts": {"create": [], "custody_updates": [], "condition_updates": []},
    "knowledge": {"create": [], "holder_updates": [], "visibility_updates": [], "truth_status_transitions": []},
    "chronology": {"advance_to": null, "deadline_updates": []},
    "relationships": {
      "create": [],
      "updates": [{
        "relationship": {"id": "rel_001"},
        "shared_state": {"cooperation": "conditional", "openness": "guarded", "central_tension": "真相の秘匿", "current_arrangement": "共同で石都を調査する"},
        "perspective_updates": [{"character": {"id": "char_001"}, "attitude": "protective", "trust": "conditional", "desire_from_other": "真相を話してほしい", "boundary": "危険な単独行動は許さない"}],
        "arc_summary": "救出を契機に、敵対は限定的な共同調査へ移った。"
      }]
    },
    "foreshadowing": {
      "create": [{"creation_key": "sister_voice", "description": "石の中から妹の声がする", "intended_payoff": "…", "related_character_refs": [{"id": "char_001"}]}],
      "transitions": [{"foreshadowing": {"id": "fh_004"}, "status": "resolved"}]
    },
    "subplots": {"create": [], "updates": []},
    "glossary": {"create": []}
  }
}
```

### 6.1 patch の制約

- create は必ず `creation_key` を持つ。
- 新規 character / collective / location / artifact / knowledge / relationship / subplot / glossary / foreshadowing の create payload は、各 entity の必須プロパティを全て持つ。
- Core と plan 時点で既知の Supporting、Collective、Relationship Arc は plan seed にだけ作る。scene patch は Minor を通常 create し、Supporting を create するには親 Design Intent を必須とする。Core の scene create は禁止する。
- patch が参照できるのは Bible slice の ID または同一 patch の typed creation reference だけである。
- Relationship Arc create は異なる2 participant、participant ごとにちょうど1 perspective、participant に属する structural bond direction を必須とする。
- Relationship Arc update は少なくとも片方の participant が scene cast に含まれる時だけ許可する。offstage 人物への影響は Intent と scene outcome の明示根拠を要する。
- Character state update は `current_state` と `current_location` を独立更新する。`current_location` は既存または同一 patch 作成の Location ref だけを受け付ける。
- Location state update は setting または scene outcome に根拠を要する。Artifact update は custody / condition のうち実際に変化した field だけを持ち、custody kind と参照先 entity の整合性を検証する。
- Knowledge holder update は、holder が scene cast であるか、明示的な伝達・観察・推論の scene outcome を根拠に持つ。author truth を holder の `knows` へ自動昇格してはならない。`truth_status_transitions` は `contested → confirmed / false_belief` のみで、同じ明示根拠を必須とする。
- Chronology は `advance_to.ordinal > current_marker.ordinal` の単調前進と deadline の `active → resolved / missed` だけを通常 patch で許可する。等しい ordinal で label だけを変える更新、過去 ordinal への巻戻しは source replacement または correction に限る。
- `characters.promote` と `identity_reveal` は明示操作だけを許可する。本文の出現回数、名前・役職・description の類似度から manager が昇格・同一人物化・merge を推測してはならない。
- 本文の `notes`、`characters[]`、`key_events[]`、description の類似度から manager が patch を推測してはならない。
- `world_rules`、series constraint、Location の immutable constraint、Artifact の properties、Knowledge の proposition と確定済み `truth_status`、既存 profile 訂正は patch に含めない。

### 6.2 LLM projection contract

LLM に raw `bible.json`、Canon Event log、または文字列検索で拾った任意の Canon を渡してはならない。`CanonSliceBuilder` が、指定 stage と typed Context scope から **決定的な projection** を生成する。

```jsonc
{
  "projection_version": 1,
  "canon_digest": "sha256:…",
  "stage": "scene_design",
  "scope_manifest": {
    "roots": [{"kind": "character", "id": "char_001"}],
    "included": [{"kind": "relationship", "id": "rel_001"}],
    "omitted_optional_count": 3
  },
  "author_context": {"…": "設計・review が読める Canon slice"},
  "pov_safe_context": {"…": "writer に投影可能な制約"}
}
```

`canon_digest`、projection version、root / included ID は scene design と review evidence に保存する。revision / retry は同じ digest の projection を再利用し、Canon が変わった場合は slice を再構築して review をやり直す。

#### Selection and budget

| priority | 必ず含める情報 | 除外規則 |
|---|---|---|
| **P0: invariant** | series constraint、scope に関係する world rule、POV / cast の identity と current state、setting の制約、scope に関係する active deadline、scope に関係する POV knowledge | token budget で除外しない |
| **P1: causal** | cast 間 Relationship Arc、所属 Collective、scope 指定 Artifact / Knowledge、関連する active subplot / unresolved foreshadowing、直近 scene outcome | 必要な compact form を保って含める |
| **P2: optional** | 関連の薄い Minor、親 location、過去 Arc summary、補助 glossary | budget 超過時に deterministic rank（explicit ref → direct relation → recency → ID）でのみ除外 |

- core の full profile をそのまま全 scene へ複製しない。scene の goal / conflict / POV / cast に関係する profile field だけを projection する。
- `current_state`、`condition`、`custody`、期限、relationship perspective は要約で落としてはならない。長文の `arc_summary`、background、過去履歴だけを compact 化できる。
- slice builder は LLM に関連性判定を委ねない。ID graph と Context scope で選択し、prose 化は選択後に行う。
- 同じ entity を `Character.current_state` と generic fact の両方で送らない。Canon item inventory の各 field を一箇所だけから投影する。

#### Stage matrix

| stage | LLM が読む Canon | LLM が書くもの | Canon への書込 |
|---|---|---|---|
| plan | ユーザー入力のみ（既存シリーズを reset する場合は人間承認情報） | Plan Seed | event がない段階だけ seed を作成 |
| volume design | series、world rule、Core / relevant Supporting の長期 Arc、active subplot / foreshadowing、長期 deadline | volume Intent / Context scope | 不可 |
| chapter design | volume Intent、chapter focus、関連 Character / Collective / Location / Relationship / Knowledge、active thread | chapter Intent、scene seed、typed Context scope | 不可 |
| scene design | P0 + P1 Canon slice、parent Intent、直前 scene outcome | cast、relationship context、Canon Patch 候補 | review 合格後だけ Event |
| scene patch review | scene design、同じ author-context slice、patch 前の対象 entity、親 Intent | review evidence | 不可 |
| writer | `scene_design.writer_context`、POV-safe context、直近 scene summary | draft | 不可 |
| draft review / revision | draft、scene design、writer projection | review / revised draft | 不可 |
| export readiness | Canon 全体を read-only で検査 | readiness report | 不可 |

#### Author context and writer projection

Design / patch review は author-context として scope 内の `Knowledge.proposition` と holder matrix を読める。ただし prompt に「作者情報であり、POV が知らない事実を本文上の知識・発話・地の文の断定にしてはならない」と明記する。

Writer は Bible を読まない。scene design が以下だけを `writer_context` として投影する。

```jsonc
{
  "pov": {"character": "アリーン", "known_information": ["記憶石は一度だけ再生できる"]},
  "cast_constraints": [{"character": "ガルド", "observable_state": "右腕を負傷している", "behavioral_constraint": "アリーンの提案には証拠を求め、即答しない"}],
  "setting_constraints": ["夜間は城門が封鎖される"],
  "setting_state": ["北門は偽造通行証の検査を強化している"],
  "artifact_constraints": ["記憶石は一度再生するとひびが入る"],
  "artifact_state": ["記憶石はアリーンが携行し、ひびが一本入っている"],
  "time_constraints": ["夜明けまでに北門を越える必要がある"],
  "required_story_beats": ["検問を突破する", "薬師への不信を強める"],
  "unrevealed_guardrails": ["POVが観測・推論していない原因、他者の非公開動機、未開示の真相を断定しない"]
}
```

- writer projection は stable ID / event digest / author-only truth を本文 prompt に露出しない。ID は validator 用 artifact 内には保持してよい。
- `unrevealed_guardrails` は secret proposition の全文を writer に渡さず、「POVが根拠を持たない原因・動機・真相を断定しない」という非 spoiler の制約だけを投影する。
- writer は scene design が投影した関係・知識・場所・物品・期限だけを参照する。全 Character、全 Relationship Arc、全 Subplot、全 unresolved foreshadowing の load は禁止する。
- review は author-context を使い、POV leak、knowledge state 違反、artifact/location/chronology/relationship の連続性違反を検出する。

### 6.3 review evidence

Canon Event を作る前に、scene design は内容 review と patch review の両方に合格しなければならない。

```jsonc
{
  "review_evidence": {
    "status": "approved",
    "reviewed_artifact_digest": "sha256:…",
    "review_digest": "sha256:…",
    "review_contract_version": 1
  }
}
```

`reviewed_artifact_digest` と event の `artifact_digest` が一致しない event は拒否する。review 後に scene 本文・patch のどちらかを変更した場合、再 review を必須にする。

---

## 7. Canon Event・dependency・replay

### 7.1 Canon Event

```jsonc
{
  "event_id": "cev_scn_01J4T4C8R2K9_r2",
  "source": {"scene_id": "scn_01J4T4C8R2K9", "location": {"volume": 1, "chapter": 2, "ordinal": 3}, "revision": 2},
  "artifact_digest": "sha256:…",
  "review_evidence": {"status": "approved", "reviewed_artifact_digest": "sha256:…", "review_digest": "sha256:…", "review_contract_version": 1},
  "patch": {"…": "CanonPatch 全文"},
  "created_entity_ids": {"foreshadowing:sister_voice": "fh_001"},
  "created_at": "2026-07-10T12:34:56Z"
}
```

`canon_events.jsonl` は Canon Event の active set を source ごとに一つだけ持つ。実装では source replacement により論理的に event を置換してもよいが、replay は必ず有効 event set を決定的な scene order で処理する。

### 7.2 dependency policy

manager は event の create / reference から dependency graph を構築する。

- ある source が作成した entity を改訂で削除する場合、後続 source がその entity を参照していれば replacement を拒否する。
- 返却値には再設計が必要な `scene_id` 群を含める。
- 依存 source を含む `replace_design_segment()` transaction が全 replacement event を揃えたときだけ実行できる。
- dangling reference を tombstone・description 類似・自動付け替えで隠さない。

### 7.3 replay と障害回復

`bible.json` はキャッシュであり、digest 不一致は致命エラーではない。

1. `CanonEventStore` は更新済み event set を一時ファイルへ書き、atomic rename する。
2. event set を seed から replay して Canon と digest を生成する。
3. `bible.json` を atomic write する。
4. 起動時に `bible.json` の digest が replay digest と異なれば、`bible.json` を自動再生成する。
5. event JSON の破損、schema 違反、参照不整合、review evidence 不一致だけは停止エラーにする。

単一ファイル atomic write だけでは event と materialized view の transaction にならないため、常に **event を正本、Bible を再生成可能なキャッシュ**として扱う。

### 7.4 plan seed の変更

`bible_seed.json` は最初の Canon Event を追加した後は immutable である。

- event が存在しない段階では plan 再生成で seed を置換できる。
- event がある状態で plan を再設計するには、全 event を明示的に破棄する `reset_series_canon()` を実行し、design を最初から生成する。
- plan 内容の類似度で既存 event を移植しない。

---

## 8. 保存物

```text
series/
  bible_seed.json                 # v2 Plan Seed（正本）
  canon_events.jsonl              # active Canon Event set（正本）
  bible.json                      # materialized Canon view（キャッシュ）
  bible.v01.json                  # 任意の巻末キャッシュ snapshot
```

`bible.vNN.json` は高速化・監査用であり、scene 単位の巻き戻し根拠ではない。

---

## 9. Schema registry と生成

- Pydantic v2 model を Canon / Patch / Event の唯一の domain contract とする。
- LLM 用 JSON Schema は `model_json_schema()` から生成し、生成物を commit する。
- 全 schema に固定 `$id` を付け、`referencing.Registry` に登録する。
- `Draft202012Validator(schema, registry=registry)` だけを使用する。
- sibling schema の `$ref` を `Draft202012Validator(schema)` 単独で解決しようとしてはならない。
- `canon_patch.json` は共通 generated schema とし、`scene_design` だけが `$ref` する。
  - **実装状態（2026-07-12 時点）:** `canon_patch.json` は**未生成**。代わりに `design_scene.json` の `properties` に `canon_patch`（object, required）を直接定義し、`RuntimeWorkflow._scene_from_generated_payload` が必須チェックしている。これは意図的な暫定構造であり、静的解析による「`canon_patch.json` が存在しない」「`canon_patch` が scene にのみ必須」は**設計どおりの正しい挙動**であってバグではない。volume/chapter には `canon_patch` は不要（runtime も要求しない）。

contract test は、有効 external `$ref` の成功と未解決 `$ref` の失敗を必須とする。

---

## 10. 旧経路の削除

v2 実装時に次を削除する。

- `schemas/bible_update.json`
- `schemas/scene_summary_and_bible_update.json`
- `resources/prompts/scene_summary_and_bible_update.md`
- `SceneWriter.summarize_and_update_bible()`
- `BibleManager.apply_update()`
- `BibleManager.apply_design_update()`
- `SceneWriteContext.get_bible_text_fn`、`ContextBuilder` の Bible load / `build_context()` Bible section、`SceneWriter._get_bible()`、`_get_subplots_text()`、`_get_relationships_text()`、`_get_foreshadowing_to_resolve_text()`
- `scene_draft.md` の `{subplots}` / `{relationships}` / `{foreshadowing_to_resolve}` と、Bible / Blackboard 全体を本文 prompt に注入する placeholder
- `Blackboard.facts` / `Blackboard.continuity_notes` と context builder の依存
- これらを前提とする schema、prompt、fixture、test

write から Bible / Canon Event の load / save を行う経路を残さない。export readiness は materialized `bible.json` を read-only で検査できるが、`canon_events.jsonl` を直接読まず、Canon を変更・保存しない。writer の input は `writer_context` と直近 scene summary のみであり、旧 prompt placeholder を経由した全 Canon 注入も残さない。

---

## 11. 実装順

### Phase 0 — 最小 real-model spike

1. `CanonPatch` の最小 subset（Minor Character create、character state update、Relationship Arc の1 perspective update、foreshadowing create / resolve）を Pydantic で定義する。
2. `model_json_schema()` を `complete_json` に直接渡す専用 harness を作る。
3. `qwen3.6:35b-a3b-mtp-q4_K_M` で生成・parse・Pydantic validation を通す。
4. 失敗時は prompt を増やさず、操作種・ネスト・required 項目を減らす。Relationship Arc が失敗するなら、まず `perspective_updates` を単一 participant update に限定する。
5. 合格前に旧経路を削除しない。

### Phase 1 — schema / identity / pure validator

- Pydantic model、generated schema、registry を実装する。
- `SceneId`、`SourceRef`、`EntityRef(kind, id)`、Character Tier、Collective、Location、Artifact、Knowledge、Chronology、Relationship Arc、status transition、review evidence validator を実装する。
- Character identity、promotion、identity reveal、2 participant / 2 perspective、affiliation、cast relevancy、knowledge/POV 分離、Knowledge `contested` 確定、artifact custody、chronology ordinal/deadline transition の RED test を先に追加する。
- `CanonSliceBuilder` の scope closure、P0 non-drop、P2 deterministic omission、projection manifest / digest の RED test を先に追加する。
- source replacement、dependency rejection、replay の RED test を先に追加する。

### Phase 2 — Storage / seed / Event Store

- `BibleFactory` が plan 完了時に `bible_seed.json` を作る。Core、初期 Supporting、初期 Collective、初期 Location / Artifact / Knowledge / Chronology、初期 Relationship Arc は plan seed に含める。
- Minor、後から確定した Location / Artifact / Knowledge / Collective は、review 合格済み scene patch でだけ create する。Local role は seed / Canon のどちらにも保存しない。
- `CanonEventStore`、atomic source replacement、replay、materialized view recovery を実装する。
- plan seed immutable policy と `reset_series_canon()` を実装する。

### Phase 3 — Design Intent / scene patch / review

- volume / chapter schema に構造化 `design_intent`、relationship arc intent、cast intent、typed `context_scope` を追加する。
- scene schema にだけ `cast`、`relationship_context`、`writer_context`、projection manifest、`canon_patch` を追加する。
- `CanonSliceBuilder` を volume / chapter / scene design と scene patch review に接続し、同一 `canon_digest` の author-context を design / review が共有することを検証する。
- scene review に cast-relevant Bible slice、親 Intent、Character Tier / Relationship Arc / Location / Artifact / Knowledge / Chronology patch validator、POV leak validator、review evidence を接続する。
- review 合格後だけ `replace_scene_event()` を呼ぶ。

### Phase 4 — 旧 runtime 経路削除

- §10 の対象を削除する。
- write の Bible / Canon Event 非接触、export readiness の Canon Event 非接触・materialized Bible read-only を regression test で追加する。
- writer が `scene_design.writer_context` と直近 summary だけを使い、Bible、Canon Event、全人物 / 関係性 / thread を load しないことを regression test で固定する。

### Phase 5 — E2E

- fake LLM で plan → volume/chapter intent → scene patch → write → export を検証する。
- Minor create、role-anchored identity reveal、Minor → Supporting promotion、Collective affiliation、Location 封鎖、Artifact custody 移送 / 損壊、Knowledge `contested` 確定と POV leak 拒否、Chronology ordinal/deadline、Relationship Arc の非対称 perspective update を検証する。
- scope closure、P0 non-drop、P2 deterministic omission、design/review digest 一致、writer の author-secret 非露出を検証する。
- scene 改訂、scene 挿入、scene 削除、依存削除拒否、segment replacement、materialized view 自動再生成を検証する。
- Phase 0 と同じ最小ケースを real model で再 smoke する。

---

## 12. 受け入れ基準

- [ ] `SERIES_BIBLE_SCHEMA_REDESIGN.md` 以外に有効な Series Bible 仕様正本がない。
- [ ] 新規 project は v2 seed だけを生成・読込する。旧 format の読込・変換・移行は実装しない。
- [ ] Canon entity と scene source は stable ID を持ち、位置番号・表示名・説明文で identity を決めない。
- [ ] Character は `core` / `supporting` / `minor`、scene-local cast は `local_role`、組織・派閥・共同体は `collective` として責務分離される。
- [ ] Local role は seed / Canon / Relationship Arc に保存されず、出現回数や名称類似で Character に自動昇格・同一視されない。
- [ ] role-anchored Character の identity reveal と Minor → Supporting → Core promotion は stable ID と既存 Canon state を保持し、明示 patch だけで実行される。
- [ ] Relationship Arc は異なる2 participant と participant ごとに1 perspective を持ち、固定 bond、共有状態、非対称 perspective、短い Arc summary を分離する。
- [ ] Character ↔ Collective は affiliation / collective stance で扱い、Collective / Local role を Relationship Arc participant にしない。
- [ ] Location は不変制約と現在状態を、Artifact は不変 properties と単一 `custody` / condition を分離し、通常 patch が不変 field を書換えない。Character が custody の場合、Artifact の場所は Character の `current_location` から導出される。
- [ ] Knowledge は authorial proposition / truth status と holder ごとの認識状態を分離し、holder を author truth から自動的に `knows` へ昇格しない。通常 patch の truth status は根拠付き `contested → confirmed / false_belief` だけを許可する。
- [ ] Foreshadowing は setup/payoff、Knowledge は知識分布、Subplot は `dramatic_question` / `stakes` / `current_state` を持つ独立 Arc として責務分離される。
- [ ] Chronology は `ordinal` と表示用 `label` を分離し、通常 patch の時刻 ordinal は厳密に単調前進する。
- [ ] 汎用 `facts` / `continuity_notes` / `story_events` の第二 Canon を持たず、永続情報は domain entity、技術履歴は Canon Event、近接本文文脈は scene summary にだけ置く。
- [ ] `ContextScope.required_refs` は `kind + id` の typed reference であり、scope closure は文字列検索・名前類似に依存しない。
- [ ] `CanonSliceBuilder` は P0 invariant を必ず含め、P2 optional だけを deterministic rank で除外し、projection manifest と Canon digest を残す。
- [ ] scene design と patch review は同一 Canon digest の author-context を使い、Canon が変われば slice 再構築と再 review を要求する。
- [ ] writer は投影済み `writer_context` と直近 summary だけを読み、Bible / Canon Event / author-only truth / stable ID を本文 prompt に受け取らない。
- [ ] review は POV leak、knowledge state、Location / Artifact / Chronology / Relationship の連続性違反を検出する。
- [ ] Canon Event は完全 patch、review evidence、created entity ID 対応を永続化する。
- [ ] 同一 source + 同一 digest は no-op、異なる digest は event replacement + replay になる。
- [ ] scene 挿入・削除・並べ替えは segment transaction を通り、暗黙対応しない。
- [ ] 依存 entity を削除する event replacement は、依存 source が未更新なら拒否される。
- [ ] Canon 内 provenance は構造化 `EventRef` であり、`vol1/ch2/sc3` のような位置文字列を保存しない。
- [ ] ID と creation key の参照は typed reference であり、裸の文字列を推測しない。
- [ ] Design Intent は Canon と分離され、構造化されている。
- [ ] status transition と review evidence が validator で強制される。
- [ ] event store を正本として `bible.json` を自動再生成できる。
- [ ] event / seed の破損・参照不整合だけは停止エラーになる。
- [ ] 外部 `$ref` が registry で解決され、未解決 `$ref` は contract test で失敗する。
- [ ] `bible_update` / runtime discovery / Blackboard の第二 Canon 経路が存在しない。
- [ ] 最小 CanonPatch の real-model smoke と fake E2E が通る。
