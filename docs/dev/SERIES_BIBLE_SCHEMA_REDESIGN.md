# Series Bible スキーマ再設計 — 決定案

> 状態：**提案（実装前）**
>
> 対象：`bible.json`、Bible の Pydantic モデル、design 成果物の Bible 更新契約、旧 runtime 更新経路。
>
> 目的：Series Bible を「設計時の SSOT」として、参照可能・検証可能・冪等に更新可能な正規化モデルへ移行する。
>
> 互換性方針：**本番運用前のため旧 Bible データとの互換性・移行は提供しない。** 新規プロジェクトは v2 だけを生成・読み込む。

---

## 1. 結論

現在の増分拡張ではなく、**破壊的変更を伴う再設計を採用する**。

理由は、既存実装が「文字列を後から推測して Bible に反映する」構造であり、SSOT として必要な識別子・位置情報・更新意図を持たないためである。

具体的には以下を実施する。

1. `Bible` を `schema_version=2` の正規化された Canon モデルへ置換する。
2. Bible 内の全ての参照対象を stable ID で識別する。表示名・説明文をキーにしない。
3. `scene_design` にだけ、物語本文用フィールドとは分離した **`canon_patch`** を持たせる。`volume_design` / `chapter_design` の予定は既存 design artifact にのみ保存する。
4. `BibleManager.apply_design_update(stage, data, context)` の暗黙マッピングを廃止し、
   scene source event を置換して Canon を replay する `replace_scene_event(event)` だけで更新する。
5. `scene_summary_and_bible_update`、`bible_update.json`、`SceneWriter.summarize_and_update_bible()`、
   `BibleManager.apply_update()` を完全に撤去する。
6. JSON Schema、Pydantic モデル、プロンプト、テスト、保存データを同一世代で移行する。

これは大改修だが、今の `description` 部分一致や `notes` の一括 state 上書きを温存するより安全である。

---

## 2. 現行の問題（確認済み）

| 問題 | 現行の挙動 | なぜ壊れるか |
|---|---|---|
| 伏線に ID がない | `{description, resolved}` | 同名・類似伏線を区別できず、回収対象を正確に指定できない。 |
| 回収が部分一致 | `key in fh.description` | 意図しない伏線を回収し得る。文字列変更にも弱い。 |
| 人物状態が曖昧 | `scene_design.characters[]` 全員の `state` を同じ `notes` で上書く | 人物別の状態変化を表現できず、無関係な人物も壊す。 |
| 章メモがデータ本体 | `foreshadowing_notes[]` / `subplot_notes[]` が文字列 | setup / payoff / 状態遷移 / 参照先を区別できない。 |
| world rule が文字列 | `world_rules: string[]` | 名称・分類・例外・適用範囲を持てず、正確に参照できない。 |
| relationship に安定参照がない | 人物名ペアで照合 | 改名・別名・表記揺れ、ペアの方向性に弱い。 |
| 古い更新系が残存 | `bible_update.json`、`apply_update()`、scene writer の更新メソッド | runtime discovery を再導入しうる死んだ経路が残る。 |
| スナップショットがない | `BibleStorage` は `bible.json` のみ | 巻の再設計や修正時に、どの Canon が有効だったか復元できない。 |
| Schema / model の不一致 | `bible.json` と `models.Bible` は別管理 | JSON Schema は追加プロパティを許し、Pydantic も既定で余分な値を落とすため、契約逸脱を見逃す。 |

---

## 3. 設計原則

### 3.1 Canon・設計意図・更新 event を分離する

- **Canon (`series_bible`)**：scene 設計で確定した、その時点で真である系列横断の正規化状態。`bible.json` はこの materialized view。
- **Design Intent**：volume / chapter design に属する「この巻・章で扱う予定」の構想。既存の volume / chapter design artifact に保存し、Canon を更新しない。
- **Canon Patch (`canon_patch`)**：**review 合格済み scene design だけ**が出力する、Canon への型付き変更命令。
- **Canon Event**：`source`・完全な patch・生成 ID 対応・artifact digest を持つ、Canon を再構築するための永続イベント。
- **Narrative design**：シーンの目的・葛藤・出来事など、本文設計そのもの。

volume / chapter の予定を「既に起きた Canon」に混ぜない。`scene_design` の本文フィールドを manager が解釈して Canon を変えることも禁止する。

### 3.2 ID は event で安定化し、LLM は既存 ID だけを参照する

- 既存 entity の更新・回収対象は Bible slice に示された stable ID だけを参照する。
- LLM に UUID・連番・既存 ID を新規生成させない。
- 新規 entity は `creation_key`（その source 内で一意の短い英数字キー）と内容を返す。例：`sister_voice`。
- manager は最初の適用時に `source + creation_key` に対応する stable ID を採番し、**Canon Event に永続化**する。
- source の再設計時も同じ `creation_key` の ID を再利用する。後続 scene が参照する ID は変化しない。
- `creation_key` の意味を description の類似度で推測してはならない。

### 3.3 更新は明示・型付き・局所的にする

人物の state、関係、伏線、サブプロットを別の型付き操作にする。
任意 JSON Patch（RFC 6902）は LLM に不向きなので使わない。

### 3.4 Canon の正本は event、Bible は再構築可能な現在値

`canon_events.jsonl` を正本とし、`bible.json` は event replay の結果を保存した materialized view とする。

- event には patch 全文、source、artifact digest、source 内の `creation_key → entity_id` 対応を残す。
- scene の再設計は、その source の event を置換し、plan seed から有効 event を設計順に replay して Canon を再構築する。
- 巻末 snapshot は高速化・監査用であり、特定 scene の巻き戻し根拠にはしない。
- Bible 本体に全文履歴を無制限に積まない。

### 3.5 write は Canon を読まず、Blackboard は Canon にならない

write は確定した `scene_design` と執筆用の直近 draft / scene summary を読むだけである。Canon の整合性保証は design の責務。
export は readiness report のために Canon を**読み取りのみ**許可するが、更新しない。

`Blackboard.facts` と `Blackboard.continuity_notes` は runtime で抽出された「事実」を Canon に昇格させる経路になるため v2 で削除する。`scene_summaries` は執筆用の短期コンテキストとして残してよいが、design / Canon 更新の根拠にしてはならない。

---

## 4. 目標スキーマ：`series_bible` v2

```jsonc
{
  "schema_version": 2,
  "series": {
    "id": "series",
    "title": "怪の街 記憶の礎",
    "logline": "…",
    "genres": ["ファンタジー"],
    "audience": "…",
    "themes": ["記憶", "喪失"],
    "tone": "叙情的で緊迫",
    "constraints": [
      {"id": "constraint_001", "statement": "死者は蘇生できない", "scope": "series"}
    ]
  },
  "characters": [
    {
      "id": "char_001",
      "name": "アリーン",
      "aliases": [],
      "role": "主人公／記憶彫刻師",
      "profile": {
        "personality": "寡黙で執念深い",
        "motivation": "失踪した妹を探す",
        "appearance": "…",
        "background": "…",
        "arc": "無力感から希望へ",
        "flaw": "他者を信じられない"
      },
      "current_state": "石の都へ到着し、妹の声を聞いた",
      "state_updated_at": "vol1/ch2/sc3"
    }
  ],
  "world_rules": [
    {
      "id": "rule_001",
      "name": "石媒律",
      "statement": "魔法は石を媒体としなければ発動しない",
      "scope": "world",
      "exceptions": []
    }
  ],
  "glossary": [
    {"id": "term_001", "term": "彫刻師", "definition": "記憶を石に刻む職能"}
  ],
  "relationships": [
    {
      "id": "rel_001",
      "source_character_id": "char_001",
      "target_character_id": "char_002",
      "directed": false,
      "kind": "姉妹",
      "current_state": "妹を捜索中",
      "updated_at": "vol1/ch2/sc3"
    }
  ],
  "foreshadowing": [
    {
      "id": "fh_001",
      "description": "石の中から妹の声がする",
      "status": "planted",
      "planted_at": "vol1/ch2/sc3",
      "resolved_at": null,
      "intended_payoff": "妹の記憶が石に封じられた事実の判明",
      "related_character_ids": ["char_001", "char_002"],
      "related_subplot_ids": ["sp_001"]
    }
  ],
  "subplots": [
    {
      "id": "sp_001",
      "name": "石都の陰謀",
      "status": "active",
      "current_state": "長老の関与が判明した",
      "related_character_ids": ["char_001"],
      "related_foreshadowing_ids": ["fh_001"],
      "updated_at": "vol1/ch2/sc3"
    }
  ]
}
```

### 4.1 必須の正規化ルール

| 要素 | 主キー | 外部参照 | 禁止 |
|---|---|---|---|
| character | `char_*` | relationship / subplot / foreshadowing | 人物名を外部キーにすること |
| world_rule | `rule_*` | series constraint / `canon_correction` | 説明文だけで参照すること |
| glossary | `term_*` | 任意 | 用語だけで更新対象を特定すること |
| relationship | `rel_*` | source / target character | 人物名を外部キーにすること。対称関係は `directed=false`、非対称関係は `source → target` を明示する。 |
| foreshadowing | `fh_*` | character / subplot | description の部分一致で回収すること |
| subplot | `sp_*` | character / foreshadowing | name を主キーにすること |

### 4.2 状態 enum

| 対象 | 値 |
|---|---|
| foreshadowing.status | `planted`, `resolved`, `abandoned` |
| subplot.status | `active`, `resolved`, `abandoned` |
| world_rule.scope | `series`, `world`, `region`, `faction` |
| constraint.scope | `series`, `volume` |

日本語の自然文は `current_state` / `statement` / `description` に置き、機械処理する状態だけを英字 enum に固定する。

---

## 5. 目標スキーマ：scene design の `canon_patch`

`canon_patch` を持つのは **review 合格済み `scene_design` だけ**である。volume / chapter design は既存の設計フィールドに予定を保存し、Canon を変更しない。

```jsonc
{
  "canon_patch": {
    "characters": {
      "create": [],
      "state_updates": [
        {
          "character_id": "char_001",
          "current_state": "石の都へ到着し、妹の声を聞いた"
        }
      ]
    },
    "relationships": {
      "create": [],
      "updates": [
        {
          "relationship_id": "rel_001",
          "current_state": "妹の生存を確信し、捜索を決意した"
        }
      ]
    },
    "foreshadowing": {
      "create": [
        {
          "creation_key": "sister_voice",
          "description": "石の中から妹の声がする",
          "intended_payoff": "妹の記憶が石に封じられた事実の判明",
          "related_character_ids": ["char_001", "char_002"],
          "related_subplot_ids": ["sp_001"]
        }
      ],
      "transitions": [
        {"foreshadowing_id": "fh_004", "status": "resolved"}
      ]
    },
    "subplots": {
      "create": [],
      "updates": [
        {
          "subplot_id": "sp_001",
          "status": "active",
          "current_state": "長老の関与が判明した"
        }
      ]
    },
    "glossary": {"create": []}
  }
}
```

- create 操作は必ず `creation_key` を持つ。foreign key は既存 ID または同一 patch の creation key を参照でき、manager が create を先に解決する。
- `world_rule` / series constraint の追加・変更は `canon_patch` に含めない。plan seed または人間承認済みの独立 `canon_correction` workflow だけが変更できる。
- 人物 profile の訂正も通常の scene patch では行わない。誤り訂正は `canon_correction` として明示する。

### 5.1 許可操作と確定タイミング

| 操作 | volume_design | chapter_design | review 合格済み scene_design |
|---|---:|---:|---:|
| Design Intent（予定） | ✓ | ✓ | ✓ |
| Canon の人物／関係／伏線／副筋更新 | ✗ | ✗ | ✓ |
| world rule / series constraint 変更 | ✗ | ✗ | ✗（`canon_correction` のみ） |

chapter / volume の「仕掛ける予定」「進める予定」は Canon の `planned` 状態を直接作らない。実際に設置・進展・回収される scene が review 合格したときだけ Canon Event を追加する。

### 5.2 manager の責務

`BibleManager.replace_scene_event(event)` と `BibleManager.rebuild()` は次のみ行う。

1. Canon Patch schema と Pydantic model の検証。
2. source が review 合格済み scene artifact を指すことの検証。
3. foreign key と `creation_key` の解決、stable ID の割当・再利用。
4. source event の digest が同一なら no-op、異なればその event だけを置換。
5. plan seed と有効 event を設計順に replay して Canon を再構築。
6. `bible.json` materialized view と巻末 snapshot を保存。

**本文フィールドの文字列解釈、部分一致検索、暗黙的な state 更新は一切しない。**

---

## 6. 保存・バージョン・冪等性

### 6.1 保存物

```text
series/
  bible_seed.json               # plan が生成する v2 Canon の初期値
  canon_events.jsonl            # Canon の正本（scene event 全文、設計順）
  bible.json                    # event replay で得る現行 v2 Canon（materialized view）
  bible.v01.json                # 巻末 snapshot（高速化・監査用）
```

`canon_events.jsonl` の各行は、監査用の digest/count だけでなく、再構築可能な完全 event を保存する。

```jsonc
{
  "source": {"stage": "scene", "volume": 1, "chapter": 2, "scene": 3},
  "artifact_digest": "sha256:...",
  "patch": {"...": "CanonPatch 全文"},
  "created_entity_ids": {"foreshadowing:sister_voice": "fh_001"},
  "applied_at": "2026-07-10T12:34:56Z"
}
```

### 6.2 冪等性と再設計

- source は構造化 `SourceRef(stage, volume, chapter, scene)` とし、表示用文字列を解析してはならない。
- 同じ source + 同じ artifact digest: no-op。
- 同じ source + 異なる artifact digest: event を置換し、`bible_seed.json` から有効 event を設計順に replay する。
- source が作成した entity の ID は `created_entity_ids` によって維持する。description の一致・類似度によるマージは禁止する。
- replay 結果と `bible.json` の digest が一致しない場合は、壊れた materialized view としてエラーにする。

---

## 7. 旧経路の削除範囲

以下は v2 移行で削除する。

- `schemas/bible_update.json`
- `schemas/scene_summary_and_bible_update.json`
- `resources/prompts/scene_summary_and_bible_update.md`
- `SceneWriter.summarize_and_update_bible()`
- `BibleManager.apply_update()`
- `SceneWriteContext.get_bible_text_fn`（既に未使用。モデル定義からも削除）
- `Blackboard.facts` と `Blackboard.continuity_notes`、およびそれらを scene write context に注入する context builder の処理
- これらを前提にした schema / prompt contract / integration test fixture

`scene_summaries` は write の短期コンテキストとして残せるが、Bible / Design Intent / Canon Event のいずれも更新しない。ただし「後で write 時更新を復活させる」経路は残さない。

---

## 8. 移行戦略

### Phase 0 — 最小 CanonPatch spike と RED 契約テスト

- Pydantic `CanonPatch` / `CanonEvent` model を唯一の domain contract として先に定義する。JSON Schema は `model_json_schema()` から生成する成果物とし、手書き二重管理をしない。
- `canon_patch` の最小構成（既存人物の state 更新、伏線 create、伏線 resolve）だけで real-model smoke を実行する。対象モデルは `qwen3.6:35b-a3b-mtp-q4_K_M` を維持する。
- nested patch が崩れる場合は指示文を増やさず、操作種・ネスト・required 項目を削減する。smoke 合格前に旧経路を削除しない。
- Canon 内の ID 一意性、全参照の存在、status transition、event replay、同一 source 置換を検証する純粋 validator の RED test を追加する。
- `canon_patch` がない / 存在しない ID を参照する / scene 以外が Canon 更新を試みるケースを RED にする。

### Phase 1 — schema registry と v2 モデル

- v2 の Pydantic model を `extra="forbid"` で実装し、生成 JSON Schema に固定 `$id` を付与する。
- `_SCHEMA_DIR` の全 schema を `referencing.Registry` に登録し、`Draft202012Validator(schema, registry=registry)` で検証する。
- 外部 `$ref` の成功・未解決 ref の失敗を contract test にする。現行の `Draft202012Validator(schema)` 単独呼び出しは禁止する。
- `canon_patch.json` は共通 generated schema とし、**scene_design だけ**が `$ref` する。

### Phase 2 — v2 Storage・plan seed・event replay

- `BibleStorage` は v2 だけを受理する。`schema_version != 2` は migration せず明確に停止する。
- `BibleFactory` が plan の `series_plan` から `bible_seed.json` を生成する。plan.py の inline 初期化を廃止する。
- `CanonEventStore` を実装し、`replace_scene_event()` と `rebuild()` を plan seed + event replay で実現する。
- `bible.json` を replay 結果の materialized view として保存し、整合 digest を検証する。
- 旧 format の fixture・テスト・互換コードは残さない。

### Phase 3 — scene CanonPatch と design review

- `scene_design` にだけ `canon_patch` を追加する。volume / chapter design は Design Intent を直接保存し、Canon を mutate しない。
- scene prompt には ID を含む Bible slice、`creation_key`、許可された操作だけを具体的に説明する。
- scene review は本文の整合性に加え、patch の存在 ID・状態遷移・creation key 一意性を検査する。
- 現行 `apply_design_update()` は `replace_scene_event()` に置換する。

### Phase 4 — 旧 runtime 経路の完全撤去

- §7 の対象を削除する。
- Blackboard から `facts` / `continuity_notes` と context builder の依存を削除する。
- runtime で Bible / event store が変更されない回帰テストを追加する。

### Phase 5 — snapshot・fake E2E・最終 smoke

- 各 volume 終了時に snapshot を保存する。
- plan → design → write → export の fake LLM E2E で以下を検証する。
  - write が Bible / Canon Event を read / write しない。
  - export が Bible / Canon Event を mutate しない。
  - scene patch で create / transition / character state / relationship / subplot state が正確に更新される。
  - scene 再設計で source event が置換され、旧 patch の効果が残らない。
  - event replay と `bible.json` が完全一致する。
- Phase 0 と同じ最小ケースで final real-model smoke を再実行する。

---

## 9. 実装前の決定事項

この設計を採用する場合の決定は以下。

- Bible は旧 format と互換維持しない。**v2 専用で開始し、migration は実装しない。**
- stable ID は必須。既存 entity は ID で参照し、新規 entity は `creation_key` を event 内の stable ID 対応へ固定する。
- `resolved: bool` は廃止し、`foreshadowing.status` と `resolved_at` へ置換。
- volume / chapter の文字列ベースの `foreshadowing_notes` / `subplot_notes` は Design Intent とし、Canon 更新の根拠にしない。
- Canon 更新は、review 合格済み `scene_design.canon_patch` を含む Canon Event のみ。
- `bible.json` は Canon Event replay の materialized view とする。
- `bible_update.json` は改修せず削除する。
- `world_rule` / series constraint / profile 訂正は通常 scene patch で変更せず、plan seed または人間承認済み `canon_correction` だけが変更する。
- write / export は Canon / Canon Event を更新しない。

---

## 10. 受け入れ基準

- [ ] `bible_seed.json` は `schema_version: 2` を持ち、`bible.json` は event replay の結果としてだけ保存される。
- [ ] Canon の entity ID は一意で、全 foreign key と同一 patch 内 creation key が解決する。
- [ ] relationship の対称性／方向性は `directed` と source / target ID で検証される。
- [ ] 伏線回収は `fh_*` ID の完全一致だけで行われる。
- [ ] 人物状態は、対象 `char_*` が明示された時だけ更新される。
- [ ] 同一 source + digest の再適用は Canon を変更しない。
- [ ] 同一 source の再設計は event を置換し、replay 後に旧 patch の影響を残さない。
- [ ] 外部 `$ref` は schema registry を通じて解決し、未解決 ref は明確に失敗する。
- [ ] `scene_summary_and_bible_update` / `bible_update` の schema・prompt・実装が存在しない。
- [ ] `Blackboard.facts` / `Blackboard.continuity_notes` と、それらの context builder 依存が存在しない。
- [ ] write 中に Bible / Canon Event の load / save が発生しない。
- [ ] export 中に Bible / Canon Event の save が発生しない。
- [ ] 最小 CanonPatch の real-model smoke が成功し、plan → design → write → export の fake E2E で Canon の整合性 validator と replay digest が通る。
