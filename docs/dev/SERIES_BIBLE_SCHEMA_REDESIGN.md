# Series Bible v2 — Canon Event Architecture

> **状態：実装前の決定仕様**
>
> **この文書が Series Bible v2 の唯一の仕様正本である。**
> 旧 `SERIES_BIBLE_SPEC.md` は廃止済みであり、実装判断に用いてはならない。
>
> 互換性方針：本番運用前のため v1 との読込・変換・バックアップ互換は提供しない。新規プロジェクトは v2 だけを生成・読込する。

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
    "themes": ["記憶", "喪失"],
    "tone": "叙情的で緊迫",
    "constraints": [{"id": "constraint_001", "statement": "死者は蘇生できない", "scope": "series"}]
  },
  "characters": [{
    "id": "char_001",
    "name": "アリーン",
    "aliases": [],
    "role": "主人公／記憶彫刻師",
    "profile": {"personality": "寡黙", "motivation": "妹を探す", "appearance": "…", "background": "…", "arc": "…", "flaw": "…"},
    "current_state": "石の都へ到着した",
    "last_changed_by": {"scene_id": "scn_01J4T4C8R2K9", "event_digest": "sha256:…"}
  }],
  "world_rules": [{"id": "rule_001", "name": "石媒律", "statement": "魔法は石を媒体とする", "scope": "world", "exceptions": []}],
  "glossary": [{"id": "term_001", "term": "彫刻師", "definition": "記憶を石に刻む職能"}],
  "relationships": [{
    "id": "rel_001", "source_character_id": "char_001", "target_character_id": "char_002", "directed": false,
    "kind": "姉妹", "current_state": "妹を捜索中", "last_changed_by": {"scene_id": "scn_…", "event_digest": "sha256:…"}
  }],
  "foreshadowing": [{
    "id": "fh_001", "description": "石の中から妹の声がする", "status": "planted",
    "planted_by": {"scene_id": "scn_…", "event_digest": "sha256:…"}, "resolved_by": null,
    "intended_payoff": "妹の記憶が石に封じられた事実の判明",
    "related_character_ids": ["char_001"], "related_subplot_ids": ["sp_001"]
  }],
  "subplots": [{
    "id": "sp_001", "name": "石都の陰謀", "status": "active", "current_state": "長老の関与が判明した",
    "related_character_ids": ["char_001"], "related_foreshadowing_ids": ["fh_001"],
    "last_changed_by": {"scene_id": "scn_…", "event_digest": "sha256:…"}
  }]
}
```

### 4.1 正規化規則

| entity | ID | 参照 | 禁止 |
|---|---|---|---|
| character | `char_*` | relationship / subplot / foreshadowing | 人物名を外部キーにする |
| relationship | `rel_*` | source / target character | 対称性・方向性を推測する |
| foreshadowing | `fh_*` | character / subplot | description 部分一致で回収する |
| subplot | `sp_*` | character / foreshadowing | name を主キーにする |
| world rule | `rule_*` | plan seed / approved correction | scene patch で変更する |
| glossary | `term_*` | 任意 | term 文字列だけで更新対象を決める |

`directed=false` の relationship は source / target を ID 昇順で正規化する。非対称な感情・権力関係は `directed=true` の別 edge とする。

### 4.2 状態遷移

| entity | 通常 scene patch の許可遷移 |
|---|---|
| foreshadowing | `planted → resolved` / `planted → abandoned` |
| subplot | `active → resolved` / `active → abandoned` |
| character / relationship | 明示対象の `current_state` 更新 |

`resolved → planted`、`abandoned → active` などの逆遷移は通常 patch で禁止する。過去 event の置換後に replay した結果として状態が変わることだけを許可する。

world rule、series constraint、既存 character profile の訂正は、plan seed または人間承認済み `canon_correction` workflow だけが変更できる。

---

## 5. Design Intent

Design Intent は Canon ではなく、volume / chapter / scene artifact に保存する構造化された予定である。現行の `foreshadowing_notes[]` / `subplot_notes[]` だけに依存しない。

```jsonc
{
  "design_intent": {
    "foreshadowing": [{"intent_key": "sister_voice", "action": "plant", "target_scene_id": "scn_…"}],
    "subplots": [{"intent_key": "stone_city_conspiracy", "action": "advance", "target_scene_id": "scn_…"}]
  }
}
```

- Intent は Canon ID を発行せず、Canon の `planned` state を作らない。
- scene patch が実際に create / transition したときだけ Canon Event を作る。
- scene review は親 chapter / volume の Intent と scene patch の整合を検証する。
- 既存の自由文 notes は著者向け補助説明として残せても、Canon 更新・検証・参照の根拠にはしない。

---

## 6. scene design の `canon_patch`

`canon_patch` を持つのは review 合格済み `scene_design` だけである。

```jsonc
{
  "canon_patch": {
    "characters": {
      "create": [],
      "state_updates": [{"character": {"id": "char_001"}, "current_state": "妹の声を聞き捜索を決意した"}]
    },
    "relationships": {
      "create": [],
      "updates": [{"relationship": {"id": "rel_001"}, "current_state": "互いの生存を確信した"}]
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
- 新規 character / relationship / subplot / glossary / foreshadowing の create payload は、各 entity の必須プロパティを全て持つ。
- patch が参照できるのは Bible slice の ID または同一 patch の typed creation reference だけである。
- 本文の `notes`、`characters[]`、`key_events[]`、description の類似度から manager が patch を推測してはならない。
- `world_rules`、series constraint、profile 訂正は patch に含めない。

### 6.2 review evidence

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
- `SceneWriteContext.get_bible_text_fn`
- `Blackboard.facts` / `Blackboard.continuity_notes` と context builder の依存
- これらを前提とする schema、prompt、fixture、test

write / export から Bible / Canon Event の load / save を行う経路を残さない。

---

## 11. 実装順

### Phase 0 — 最小 real-model spike

1. `CanonPatch` の最小 subset（character state update、foreshadowing create、resolve）を Pydantic で定義する。
2. `model_json_schema()` を `complete_json` に直接渡す専用 harness を作る。
3. `qwen3.6:35b-a3b-mtp-q4_K_M` で生成・parse・Pydantic validation を通す。
4. 失敗時は prompt を増やさず、操作種・ネスト・required 項目を減らす。
5. 合格前に旧経路を削除しない。

### Phase 1 — schema / identity / pure validator

- Pydantic model、generated schema、registry を実装する。
- `SceneId`、`SourceRef`、typed reference、status transition、review evidence validator を実装する。
- source replacement、dependency rejection、replay の RED test を先に追加する。

### Phase 2 — Storage / seed / Event Store

- `BibleFactory` が plan 完了時に `bible_seed.json` を作る。
- `CanonEventStore`、atomic source replacement、replay、materialized view recovery を実装する。
- plan seed immutable policy と `reset_series_canon()` を実装する。

### Phase 3 — Design Intent / scene patch / review

- volume / chapter schema に構造化 `design_intent` を追加する。
- scene schema にだけ `canon_patch` を追加する。
- scene review に Bible slice、親 Intent、patch validator、review evidence を接続する。
- review 合格後だけ `replace_scene_event()` を呼ぶ。

### Phase 4 — 旧 runtime 経路削除

- §10 の対象を削除する。
- write / export の Canon Event 非接触 regression test を追加する。

### Phase 5 — E2E

- fake LLM で plan → volume/chapter intent → scene patch → write → export を検証する。
- scene 改訂、scene 挿入、scene 削除、依存削除拒否、segment replacement、materialized view 自動再生成を検証する。
- Phase 0 と同じ最小ケースを real model で再 smoke する。

---

## 12. 受け入れ基準

- [ ] `SERIES_BIBLE_SCHEMA_REDESIGN.md` 以外に有効な Series Bible 仕様正本がない。
- [ ] 新規 project は v2 seed だけを生成・読込し、旧 format は明示的に拒否する。
- [ ] Canon entity と scene source は stable ID を持ち、位置番号・表示名・説明文で identity を決めない。
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
