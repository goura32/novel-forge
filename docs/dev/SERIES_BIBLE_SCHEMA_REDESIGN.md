# Series Bible スキーマ再設計 — 決定案

> 状態：**提案（実装前）**
>
> 対象：`bible.json`、Bible の Pydantic モデル、design 成果物の Bible 更新契約、旧 runtime 更新経路。
>
> 目的：Series Bible を「設計時の SSOT」として、参照可能・検証可能・冪等に更新可能な正規化モデルへ移行する。

---

## 1. 結論

現在の増分拡張ではなく、**破壊的変更を伴う再設計を採用する**。

理由は、既存実装が「文字列を後から推測して Bible に反映する」構造であり、SSOT として必要な識別子・位置情報・更新意図を持たないためである。

具体的には以下を実施する。

1. `Bible` を `schema_version=2` の正規化された Canon モデルへ置換する。
2. Bible 内の全ての参照対象を stable ID で識別する。表示名・説明文をキーにしない。
3. `scene_design` / `chapter_design` / `volume_design` に、物語本文用フィールドとは分離した **`canon_patch`** を持たせる。
4. `BibleManager.apply_design_update(stage, data, context)` の暗黙マッピングを廃止し、
   `apply_patch(patch, source)` のみで更新する。
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

### 3.1 Canon と更新命令を分離する

- **Canon (`series_bible`)**：その時点で真である、系列横断の正規化された状態。
- **Canon Patch (`canon_patch`)**：設計成果物が「どの Canon を、なぜ、どう変えるか」を明示する命令。
- **Narrative design**：シーンの目的・葛藤・出来事など、本文設計そのもの。

`scene_design` の文言から manager が意味を推測して Canon を変えてはいけない。

### 3.2 ID は機械採番、LLM は既存 ID を参照する

- 新規 ID は manager が `fh_001` のように採番する。
- LLM は Bible slice に示された既存 ID を、回収・変更の対象として返す。
- LLM に UUID や連番を新規生成させない。
- 新規エンティティは `ref: null` / `create` 指示と内容を返し、manager が ID を付与する。

### 3.3 更新は明示・型付き・局所的にする

人物の state、関係、伏線、サブプロットを別の型付き操作にする。
任意 JSON Patch（RFC 6902）は LLM に不向きなので使わない。

### 3.4 現在値と履歴を混同しない

Bible は現在値を持つ。デバッグと巻き戻しのため、更新ごとの provenance を最小限記録する。
全文の変更履歴を Bible 本体に無制限に蓄積しない。

### 3.5 write は Canon を読まない

write は確定した `scene_design` を読むだけである。Canon の整合性保証は design の責務。
export は readiness report のために Canon を**読み取りのみ**許可するが、更新しない。

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
      "character_ids": ["char_001", "char_002"],
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
| world_rule | `rule_*` | constraint / patch | 説明文だけで参照すること |
| glossary | `term_*` | 任意 | 用語だけで更新対象を特定すること |
| relationship | `rel_*` | `character_ids` | `character_a/b` の文字列ペア |
| foreshadowing | `fh_*` | character / subplot | description の部分一致で回収すること |
| subplot | `sp_*` | character / foreshadowing | name を主キーにすること |

### 4.2 状態 enum

| 対象 | 値 |
|---|---|
| foreshadowing.status | `planned`, `planted`, `resolved`, `abandoned` |
| subplot.status | `planned`, `active`, `resolved`, `abandoned` |
| world_rule.scope | `series`, `world`, `region`, `faction` |
| constraint.scope | `series`, `volume` |

日本語の自然文は `current_state` / `statement` / `description` に置き、機械処理する状態だけを英字 enum に固定する。

---

## 5. 目標スキーマ：設計成果物の `canon_patch`

各 design 成果物には、物語の出力と分離した以下のフィールドを追加する。

```jsonc
{
  "canon_patch": {
    "character_state_updates": [
      {
        "character_id": "char_001",
        "current_state": "石の都へ到着し、妹の声を聞いた"
      }
    ],
    "relationship_updates": [
      {
        "relationship_id": "rel_001",
        "current_state": "妹の生存を確信し、捜索を決意した"
      }
    ],
    "foreshadowing": {
      "plant": [
        {
          "description": "石の中から妹の声がする",
          "intended_payoff": "妹の記憶が石に封じられた事実の判明",
          "related_character_ids": ["char_001", "char_002"],
          "related_subplot_ids": ["sp_001"]
        }
      ],
      "resolve_ids": ["fh_004"],
      "abandon_ids": []
    },
    "subplot_updates": [
      {
        "subplot_id": "sp_001",
        "status": "active",
        "current_state": "長老の関与が判明した"
      }
    ],
    "glossary_additions": [],
    "world_rule_additions": []
  }
}
```

### 5.1 ステージごとの許可操作

| 操作 | volume_design | chapter_design | scene_design |
|---|---:|---:|---:|
| character state 更新 | ✗ | ✓ | ✓ |
| relationship 更新 | ✗ | ✓ | ✓ |
| 伏線 plant / resolve / abandon | ✓（計画のみ） | ✓ | ✓ |
| subplot 更新 | ✓ | ✓ | ✓ |
| glossary / rule 追加 | ✓ | ✓ | ✓ |
| series 制約の変更 | ✗ | ✗ | ✗（明示的 `bible correct` のみ） |

`volume_design` の patch は「巻で扱う予定」の宣言に限定し、シーンで確定する状態を先取りしない。

### 5.2 manager の責務

`BibleManager.apply_patch(patch, source)` は次のみ行う。

1. patch スキーマ検証。
2. 外部参照 ID の存在検証。
3. 新規 ID の機械採番。
4. allowed operation と source stage の検証。
5. 同一 `source` の再適用を no-op にする冪等性保証。
6. Canon 保存、巻末 snapshot 保存、provenance 記録。

**本文フィールドの文字列解釈、部分一致検索、暗黙的な state 更新は一切しない。**

---

## 6. 保存・バージョン・冪等性

### 6.1 保存物

```text
series/
  bible.json                    # 現行の v2 Canon
  bible.v0.json                 # plan 完了時
  bible.v01.json                # volume 1 design 完了時
  canon_events.jsonl            # 監査用（source / digest / patch summary）
```

`canon_events.jsonl` は全文差分でなく、以下の監査情報だけを保持する。

```json
{"source":"vol1/ch2/sc3","patch_digest":"sha256:...","applied_at":"...","counts":{"character_state_updates":1,"foreshadowing_plant":1}}
```

### 6.2 冪等キー

- source: `vol{v}/ch{c}/sc{s}`（または `vol{v}` / `vol{v}/ch{c}`）
- patch digest: 正規化 JSON の SHA-256
- 同じ source + 同じ digest: no-op
- 同じ source + 異なる digest: **replace**。当該 source が作成したエンティティと更新前値を、直前 snapshot / provenance から巻き戻してから適用する。

単純な「description が同じなら重複しない」では、再設計で内容が変わった時に古い Canon が残る。

---

## 7. 旧経路の削除範囲

以下は v2 移行で削除する。

- `schemas/bible_update.json`
- `schemas/scene_summary_and_bible_update.json`
- `resources/prompts/scene_summary_and_bible_update.md`
- `SceneWriter.summarize_and_update_bible()`
- `BibleManager.apply_update()`
- これらを前提にした schema / prompt contract / integration test fixture
- `SceneWriteContext.get_bible_text_fn`（既に未使用。モデル定義からも削除）
- Blackboard の `facts` / `continuity_notes` が旧 Bible 更新専用なら、用途を精査して削除または write 専用ログへ縮小する。

これにより「後で誰かが write 時更新を復活させる」経路をなくす。

---

## 8. 移行戦略

### Phase 0 — 契約テストを先に RED にする

- v2 JSON Schema の `additionalProperties: false` を全 object に設定する。
- Canon 内の ID 一意性、全参照の存在、status enum、source 許可操作を検証する純粋 validator を作る。
- `scene_design` の `canon_patch` が存在しない / 存在しない ID を参照する / source 禁止操作を行うケースを RED にする。

### Phase 1 — v2 モデル・Schema・Storage

- `Bible` と子モデルを v2 へ置換。
- Pydantic `extra="forbid"` を採用。
- `BibleStorage` に v1→v2 one-way migration を実装する。
- `bible.json` の旧データは read 時に migration し、成功後にバックアップを残す。

### Phase 2 — plan seed

- `series_plan` を v2 Bible 初期値に変換する専用 `BibleFactory` を作る。
- plan.py 内の inline 生成を廃止する。
- plan で生成できない ID は factory が採番する。

### Phase 3 — CanonPatch と design

- `canon_patch.json` を共通 schema として作成し、各 design schema から `$ref` する。
- volume / chapter / scene のプロンプトを、ID 参照・新規項目・禁止操作が明確な説明へ更新する。
- review prompt で `canon_patch` の参照・状態遷移も検査する。
- `apply_design_update` を `apply_patch` へ置換する。

### Phase 4 — 旧 runtime 経路の完全撤去

- §7 の対象を削除。
- SceneWriter / Blackboard / context builder / tests を整理。
- runtime で Bible が変更されない回帰テストを追加する。

### Phase 5 — snapshot / E2E

- 各 volume design 終了時に snapshot を保存する。
- plan → design → write → export の fake LLM E2E で以下を検証する。
  - write が Bible を read / write しない。
  - export が Bible を mutate しない。
  - scene patch で plant / resolve / character state / subplot state が正確に更新される。
  - scene 再設計で旧 patch の効果が残らない。

### Phase 6 — 最小 real-model smoke

`qwen3.6:35b-a3b-mtp-q4_K_M` を維持する。小規模な 1 巻・1 章・1 シーンで、`canon_patch` の構造出力を確認する。

もし nested patch が継続的に壊れる場合は、ルール文を増やすのではなく、`canon_patch` の操作種を削減して schema を単純化する。

---

## 9. 実装前の決定事項

この設計を採用する場合の決定は以下。

- Bible は互換維持しない。**v2 へ one-way migration**。
- stable ID は必須。
- `resolved: bool` は廃止し、`foreshadowing.status` と `resolved_at` へ置換。
- 文字列ベースの `foreshadowing_notes` / `subplot_notes` を Canon 更新の根拠にしない。
- `bible_update.json` は改修せず削除する。
- Canon 更新は `canon_patch` のみ。
- write / export は Canon を更新しない。

---

## 10. 受け入れ基準

- [ ] `bible.json` は `schema_version: 2` を持つ。
- [ ] Canon の entity ID は一意で、全 foreign key が解決する。
- [ ] 伏線回収は `fh_*` ID の完全一致だけで行われる。
- [ ] 人物状態は、対象 `char_*` が明示された時だけ更新される。
- [ ] 同一 patch の再適用は Canon を変更しない。
- [ ] 同一 source の再設計は古い patch の影響を残さない。
- [ ] `scene_summary_and_bible_update` / `bible_update` の schema・prompt・実装が存在しない。
- [ ] write 中に Bible の load / save が発生しない。
- [ ] export 中に Bible の save が発生しない。
- [ ] plan → design → write → export の E2E で Canon の整合性 validator が通る。
