# シリーズ聖典（Series Bible）仕様 — 理想形

> 対象：NovelForge の **設計時単一真実源（SSOT）** としての「聖典」。
> 方針：**著者向け出力レポート（export 時生成）は不要**。聖典は
> 企画（plan）で初版を作り、設計（design）で参照・更新する
> **生成パイプライン内の憲章** である。執筆・出力は聖典を直接読まず、
> 設計が投影した `scene_design` / 執筆された本文を読む。

---

## 1. 名称検討

| 候補 | 意味 | 評価 |
|---|---|---|
| `series_bible` | 業界用語（TV の「番組バイブル」）。設定・人物・世界観をまとめた聖典 | **推奨**。ユーザーが「聖典」と呼んでおり、業界でも定着。B（出力レポート）を廃したので混同の余地なし |
| `series_canon` | canon＝「公式に真である事実」。SSOT の意味論に最も忠実 | 意味は正確だが、日本語文脈で馴染み薄。 rename は 1 ファイル変更で済む |
| `series_charter` | charter＝憲章・規約。不変ルールを強調 | 良いが「人物・伏線も含む」広がりが表せない |
| `world_bible` | 世界観に特化 | 人物・伏線も含むので狭い |

**決定（提案）**：`series_bible`（ファイル：`bible.json` / `bible.vN.json`）。
 rename 希望があれば `series_canon` 等へ 1 行で変更可能。

---

## 2. 粒度の方針（再検討の核心）

### 2.1 原則：聖典は「不変事実 ＋ 設計者の意図的状態」のみ

| 入れるべき | 入れてはいけない |
|---|---|
| 一度決まったら揺らがない不変事実（世界ルール、人物の背景） | 実行時に draft から**発見・抽出**された状態 |
| 設計者が意図して決めた状態（伏線の plant/回収予定、サブプロット進行） | 執筆のたびに変動する transient な状態 |
| シリーズ横断で守るべき制約（トーン、禁忌） | シーン単位の詳細（それは `scene_design` の役割） |

**旧 bible の最大の誤り**：write 時に draft を LLM で要約し、
「その場で発見した事実」を聖典へ書き戻していた（runtime discovery）。
これは聖典を draft の**副産物**に堕落させる。理想形では
**聖典の更新は design のみ**、かつ**設計者の意図**によって行われる。

### 2.2 粒度の軸

1. **フィールド詳細度**：各エントリは「その事実を一意に特定・参照するのに十分」な属性を持つ。
2. **プロセス状態 vs 意図的状態**：`resolved` / `status` は**設計時に意図してセット**する（draft 走査で決めない）。
3. **履歴 vs 現在値**：聖典は**現在の正値**を持つ。どのシーンで変わったかは任意メタデータ（必須ではない）。

---

## 3. 理想構造

```jsonc
{
  "meta": {                      // ★ 追加：シリーズ最上位の不変クリエイティブ方向
    "title": "怪の街 記憶の礎",
    "logline": "記憶を石に刻む街で…（1文）",
    "themes": ["記憶", "喪失"],
    "tone": "叙情的／緊迫",
    "audience": "男性向けファンタジー",
    "global_constraints": [       // 全巻で守るべき絶対制約
      "魔法は『石』媒体のみ",
      "死者の蘇生は不可"
    ]
  },
  "characters": [                // 一意の人物定義（不変属性）
    {
      "name": "アリーン",
      "role": "主人公／記憶彫刻師",
      "personality": "寡黙で執念深い",
      "motivation": "失踪した妹を探す",
      "appearance": "…",
      "background": "…",
      "arc": "無力感→希望",
      "flaw": "他者を信じられない",
      "state": "第1巻末：石の都へ到着"   // 現在の正値（design が意図して更新）
    }
  ],
  "world_rules": [               // 不変の法則（1件1法則）
    { "name": "石媒律", "statement": "魔法は石を媒体としなければ発動しない" }
    // 文字列でも可（anyOf で許容）。構造化する場合は {name, statement}
  ],
  "glossary": [                  // 用語→定義（一意）
    { "term": "彫刻師", "definition": "記憶を石に刻む職能" }
  ],
  "relationships": [             // ペアの現在値（履歴は持たない）
    {
      "character_a": "アリーン",
      "character_b": "妹",
      "relationship_type": "姉妹",
      "status": "捜索中",
      "change_direction": "変化なし",
      "trigger_event": ""
    }
  ],
  "foreshadowing": [             // ★ 構造化：plant/payoff を設計時に意図
    {
      "id": "fh_001",
      "description": "石の中に妹の声",
      "type": "setup",            // setup=植え / payoff=回収
      "planted_in": "vol1/ch2",   // 設計時に意図して決定
      "resolved_in": "vol3/ch1",  // 設計時に意図（draft 走査では決めない）
      "status": "planted"         // planted / resolved
    }
  ],
  "subplots": [                  // サブプロットの正値
    {
      "id": "sp_001",
      "name": "石都の陰謀",
      "status": "進行中",          // 未着手／進行中／完了（design が意図して更新）
      "progress_note": "長老の正体が判明",
      "related_characters": ["アリーン", "長老"],
      "related_foreshadowing_ids": ["fh_003"]
    }
  ]
}

> **初期化ソース（重要）**：`meta` の大部分（`title` / `logline` / `themes` / `audience` / `world_rules`）は
> 既に `series_plan_concept.json` に存在する。plan 初版作成時は series_plan から**コピー**し、
> 聖典を独立ソースにする（以降の乖離を防ぐため、plan 以降は series_plan を参照しない）。
> よって `meta` は「新設」ではなく「series_plan からの引き継ぎ ＋ `global_constraints` 等の追加」である。
> `characters` も `series_plan_characters.main_characters` から seed する（§6.1 注記参照）。

### 粒度メモ（各フィールド）
- **meta**：★新設（実際は series_plan からの引き継ぎ）。系列全体の「憲章」。`global_constraints` は design が最も参照する（横断ルールのぶれ防止）。
- **characters**：旧来の rich profile を維持。`state` は「現在の正値」として design が更新。
- **world_rules**：1 法則 1 エントリ。名称付きオブジェクトを推奨（参照しやすい）が文字列でも可。
- **glossary**：term 一意。定義は簡潔に。
- **relationships**：ペアの「現在値」のみ。履歴（いつ変わったか）は任意。
- **foreshadowing**：★構造化。`type(setup/payoff)` + `planted_in` / `resolved_in` を design が**意図して**決める。runtime 抽出しない。
- **subplots**：`status` は design が意図して更新。

---

## 4. ライフサイクル（理想）

```
[plan]   キーワード → シリーズ企画
           └─→ bible.v0 を作成（meta ＋ 初期 characters/glossary/
                                    foreshadowing(setup)/world_rules/
                                    relationships/subplots）
[design] 各巻・各シーンの設計
   │ ① bible を「参照」（global_constraints・進行中伏線・人物・世界ルール）
   │ ② scene_design を生成（bible 情報をそのシーン用に投影・具体化）
   │    └─ 章末で chapter_design 結果を bible へ反映（§6.2）
   │    └─ 巻末で volume_design 結果を bible へ反映（§6.3）
   │ ③ シーン設計確定直後に新事実・変更を bible へ「意図的に書き戻し」（§6.1/§6.4/§6.6）
   │       └─ シーン末で即 commit、巻末で `bible.vN` 保存
[write]  各シーン執筆
   │ → scene_design のみ参照（bible は直接読まない）
   │ → 本文生成 → review → 品質ゲート
[export] 原稿出力
   │ → 執筆本文のみ参照（bible・scene_design は読まない）
   │ → KDP 原稿を生成（著者向け聖典レポートは作らない）
```

**聖典が直接関わるのは plan → design の区間だけ。**

---

## 5. 各工程の責務

| ステージ | 聖典操作 | トリガー | 内容 |
|---|---|---|---|
| **plan** | 作成（Write） | 企画生成時 | `meta` ＋ 6 フィールドの初版を構築。`bible.v0` 保存 |
| **design（巻・章・シーン）** | 参照（Read）＋更新（Write） | 各設計生成時 | ① 聖典を読み設計を一致させる ② 生成結果から新事実を意図的に書き戻す ③ シーン末で即 commit、巻末で `bible.vN` 保存 |
| **write** | **なし** | — | `scene_design` のみ参照。聖典は読まない・書かない |
| **export** | **なし** | — | 執筆本文のみ参照。聖典は読まない |

> **更新の主体は design のみ**。シーン設計が確定（review 合格）した直後に聖典を更新する。
> これを「シーン末更新」と呼ぶ。write のシーン末（draft からの抽出）ではない。

---

## 6. マッピング（design 結果 → 聖典）

design が生成した各成果物から、どのフィールドを聖典のどの要素へ反映するか。
全て **設計者の意図**（この設計で何を plant するか）に基づく。runtime 抽出ではない。

### 6.1 scene_design → bible（シーン末更新の核心）

| scene_design のフィールド | bible の要素 | 操作 | 備考 |
|---|---|---|---|
| `characters[]` | `characters[]` | 新規名なら追加、既存なら `state` を上書き | 表記は series_plan の正式名と一致（表記揺れ禁止） |
| `foreshadowing[]`（文字列リスト） | `foreshadowing[]` | `type=setup` で追加。`id` 採番、`planted_in="vol{}/ch{}/sc{}"`、`status=planted` | 文字列→構造化（§6.4） |
| `key_events[]` | （参照用・直接マップしない） | — | 回収は下の `resolves_foreshadowing` で明示 |
| `resolves_foreshadowing[]`（**新設フィールド**） | `foreshadowing[].status` | 該当 `id` の `status=resolved`、`resolved_in="vol{v}/ch{c}/sc{s}"` をセット | **heuristic 抽出ではなく、設計が明示的に id を挙げる**（§6.6） |
| `setting` から派生する世界ルール言及 | `world_rules[]` | 新規ルールなら追加 | 通常は plan で初期化済み |

> **注意**：`scene_design` に `relationships` フィールドは存在しない（確認済み）。
> `bible.relationships` は plan 初版で `series_plan_characters.main_characters` から seed し、
> 以降は明示的な `bible correct` 操作（§9）または将来の design フィールド追加でのみ更新する。

### 6.2 chapter_design → bible（章末・design.py の章ループ終端で呼ぶ）

| chapter_design のフィールド | bible の要素 | 操作 |
|---|---|---|
| `characters[]` | `bible.characters[]` | 登場人物の `state` を上書き（§6.1 と同様） |
| `foreshadowing_notes[]` | `foreshadowing[]` | setup/payoff を反映 |
| `subplot_notes[]` | `subplots[]` | `status` / `progress_note` 更新。新規なら追加（`id` 採番） |

### 6.3 volume_design → bible（巻末・design.py の巻ループ終端で呼ぶ）

| volume_design のフィールド | bible の要素 | 操作 |
|---|---|---|
| `premise` | `meta.logline`（補強） | 必要に応じ上書き |
| 新規世界ルール・用語 | `world_rules[]` / `glossary[]` | 追加 |

### 6.4 構造化変換（foreshadowing の文字列→構造）

scene_design.foreshadowing は **文字列リスト**（`schemas/scene_design.json` より）。
これを bible.foreshadowing（構造化）へ変換：

```
"石の中に妹の声"  →  { "id":"fh_017", "description":"石の中に妹の声",
                        "type":"setup", "planted_in":"vol1/ch2/sc3",
                        "resolved_in":"", "status":"planted" }
```

- `id`：通番（`fh_{:03d}`）。既存と description 完全一致なら再利用（重複排除）。
- `type`：`setup`（plant）固定。回収（payoff）は §6.6 の `resolves_foreshadowing` 経由で `status=resolved` に（heuristic 不使用）。
- `planted_in`：設計コンテキストから `"vol{v}/ch{c}/sc{s}"` を補完。

### 6.5 冪等性（再実行時の挙動）

design の再実行（巻の再設計・シーンの再設計）を想定し、聖典更新は冪等でなければならない。

- **foreshadowing**：キーは `(planted_in, description)` のペア。同じキーの entry が既にあれば上書き（新しい `id` は採番しない）。
  シーン番号がずれて再 plant された場合、古い `planted_in` の entry は「そのシーンがもう生成されない」ことが確定してから削除（または `status=abandoned` に）。単純な再実行では重複を作らない。
- **characters.state / subplots.status**：値の上書きのみ（履歴は残さない）。
- **新規追加**：description / name の完全一致で既存を検索し、あれば更新・なければ追加。

### 6.6 回収検出は heuristic にしない（明示フィールド方式）

§6.1 の `resolves_foreshadowing[]` は **scene_design スキーマへの新設フィールド**。
design が「このシーンでどの伏線を回収するか」を **id で明示** して出力する。

- これにより「key_events を文字列マッチ / LLM で読んで回収を当てる」という脆い heuristic を排除。
- 設計者の**意図**がそのまま構造化される（runtime discovery の防止とも整合）。
- `bible_update.json` の `foreshadowing[].resolved` フラグは廃し、代わりに `resolves_foreshadowing` 経由で `status=resolved` をセット。

---

## 7. プロンプト注入の具体化

design の全ステージ（volume / chapter / scene）のプロンプトに **`{bible}` プレースホルダ** を追加し、
聖典の「関連スライス」を注入する。これにより設計が聖典と矛盾しないよう誘導する。

### 7.1 注入するスライス（ステージ別）

| ステージ | 注入する bible スライス |
|---|---|
| **volume_design** | `meta`（logline/themes/tone/`global_constraints`）＋ `world_rules` 全文 |
| **chapter_design** | `meta.global_constraints` ＋ 進行中 `subplots`（status≠完了）＋ 未回収 `foreshadowing` |
| **scene_design** | `meta.global_constraints` ＋ そのシーンに登場する `characters`（state 付き）＋ 未回収 `foreshadowing` ＋ 関連 `relationships` |

### 7.2 プロンプトへの記述パターン（例：scene_design.md）

入力情報セクションに以下を追加：

```
### シリーズ聖典（series bible）
{bible}

上記聖典と矛盾しないよう設計すること。特に：
- `global_constraints` に違反する設定・能力は作らない。
- `characters` の state と食い違う人物の行動・状態変化を書かない。
- `foreshadowing`（未回収）は、このシーンで plant する場合は `foreshadowing` フィールドに追加（文字列で十分）。
  過去に plant 済の伏線をこのシーンで回収する場合は `resolves_foreshadowing` にその `id` を列挙する（heuristic ではなく明示）。
```

### 7.3 実装での注入フック（design.py）

既存の `engine._prompts.render("scene_design.md", {...})` 呼び出し（design.py 約 L288）の
引数 dict に `"bible": engine._bible_mgr.to_text_slice(scene_context)` を追加。
`to_text_slice` は §7.1 のスライスを生成する新メソッド（既存 `to_text` は全文なので用途別に分割）。

volume / chapter も同様に render 引数へ `"bible": ...` を追加。

### 7.4 シーン末更新の実装フック（design.py）

scene_design 生成・review 合格後（design.py 約 L333 `prev_outcome = ...` の直後）に：

```python
if isinstance(scene_obj, dict):
    # ... 既存の number/scene セット ...
    prev_outcome = scene_obj.get("outcome", "")
    # ★ シーン末：聖典へ意図的に反映
    engine._bible_mgr.apply_design_update(scene_obj, vol_num, ch_num, scene_counter)
```

`apply_design_update` は §6.1/§6.4 のマッピングを適用（既存 `apply_update` を
runtime 抽出から design 意図ベースへ書き換え）。write.py の `summarize_and_update_bible` は削除。

---

## 8. 更新の境界（鉄則）

- **聖典を書き換えられるのは plan と design のみ。**
- write / export は聖典に**一切触らない**（read も write も不可）。
- 聖典の更新は **runtime discovery ではなく、設計者の意図** によって行われる。
  - よって `foreshadowing.resolved` は「design が回収を設計したとき」にセットし、
    「write が draft を走査して回収を発見したとき」にはセットしない。
- 執筆中に聖典との乖離を見つけたら：**聖典を直すのではなく `scene_design` を修正**（design へ差し戻し）。聖典は「設計時点の正当な事実」として守る。

---

## 9. 整合性ルール

| ケース | 解決 |
|---|---|
| シーン設計が聖典と矛盾 | design 段階で聖典に合わせる（または聖典を正して再設計） |
| 執筆中に聖典との乖離発見 | `scene_design` を修正（design へ差し戻し）。聖典は直接触らない |
| 聖典自体が誤っていた（初期設定ミス） | 明示的な `bible correct` 操作（理由・巻番号記録）。自動では行わない |
| 巻末 reconcile | 聖典全体の整合性検証：未回収伏線の整理、サブプロット status 見直し、スナップショット保存 |

---

## 10. バージョニング

- `bible.v{volume}.json` として巻単位保存（v0 = plan 初版、v1 = vol1 の design 終了後 …）。
- 現在世代用は `bible.json`（常に最新）。
- design の**シーン末で即 commit**、巻末ごとにスナップショット。巻間差分確認・巻き戻しに利用。

---

## 11. 現行実装との乖離（覚書・要修正）

| 項目 | 現行 | 理想形 |
|---|---|---|
| 名称 | `bible` | `series_bible`（据え置き可） |
| plan で作成 | なし | **初版作成（meta 含む）** |
| design で参照・更新 | なし（grep 0 件） | **参照・更新（責務）** |
| write で参照・更新 | `SceneWriter.__init__` の `get_bible_text_fn=engine._bible_mgr.to_text` 注入 ＋ `scene_writer.summarize_and_update_bible(...)` 呼び出し | **削除。scene_design のみ** |
| export で参照 | `BibleManager.finalize(...)` / `get_unresolved_foreshadowing()` / `get_incomplete_subplots()` 呼び出し | **削除。本文のみ** |
| 更新の性質 | draft からの runtime 抽出 | **design による意図的更新** |
| meta フィールド | なし（series_plan にのみ存在） | **聖典に格納** |
| foreshadowing 構造 | `{description, resolved:bool}` | **`{id, type, planted_in, resolved_in, status}`** |

### 修正優先順位
1. **write.py**：聖典参照・更新を削除（line 95, 107-108）。scene_design のみ渡す。
2. **export.py**：聖典参照を削除（line 26, 231, 237）。本文から出力。
3. **plan.py**：聖典初版作成（meta 含む）を追加（現行 0 件）。
4. **design.py**：
   - 全ステージ（volume/chapter/scene）の render に `"bible": to_text_slice(...)` を注入（§7.3）。
   - scene_design 確定直後に `apply_design_update`（§6.1/§6.4 マッピング）を呼ぶ（§7.4）。
   - 既存 `apply_update`（runtime 抽出）を design 意図ベースへ書き換え。
5. **スキーマ変更**：
   - `bible.json`：`meta` 追加（series_plan_concept から初期化）、`foreshadowing` 構造化（§3）。
   - `scene_design.json`：`resolves_foreshadowing: string[]` を新設（§6.6）。
   - `bible_update.json`：`foreshadowing[].resolved` フラグを廃し `resolves_foreshadowing` 経由に（§6.6）。
6. **bible_manager.py**：`to_text_slice(scene_context)` 新メソッド追加（§7.1）。`apply_design_update` を冪等に（§6.5）。

---

## 12. 受け入れ基準（チェックリスト）

- [ ] plan 完了時に `bible.v0`（meta 含む）が存在する
- [ ] design の全ステージプロンプトに `{bible}` スライスが注入されている
- [ ] シーン設計確定直後に聖典が意図的に更新されている（シーン末 commit）
- [ ] **write 実行中に聖典ファイルが変更されていない**（read/write とも不可）
- [ ] **export 実行中に聖典ファイルを読み込んでいない**
- [ ] 聖典の `resolved` / `status` が runtime 抽出ではなく design の意図でセットされている
- [ ] 巻末に `bible.vN` スナップショットが保存されている
