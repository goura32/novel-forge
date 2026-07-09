# Bible ライフサイクル設計（あるべき姿）

> 対象：NovelForge の `bible`（設定資料集・単一真実源）の参照・更新タイミング。
> 方針：**執筆・出力は bible を直接見ない**。bible は企画で初版を作り、
> 設計（シーン設計）で参照・更新する。執筆は「設計結果」だけに従う。

---

## 1. 責務分離の原則（最重要）

| ステージ | bible との関係 | 参照ソース | 役割 |
|---|---|---|---|
| **plan** | 初版を**作成** | キーワード・企画案 | 世界観・人物・伏線のseedを決定 |
| **design** | bible を**参照・更新** | bible（＋企画） | シーン設計に bible を反映し、新事実を bible へ書き戻す |
| **write** | **無関係（直接参照しない）** | **scene_design のみ** | 設計結果（bible 已抽出済み）に従って本文を執筆 |
| **export** | **無関係（直接参照しない）** | **執筆本文のみ** | 本文から KDP 原稿・付録を生成 |

### 核心の鉄則
- **執筆工程は設定資料集を参照せず、シーン設計結果だけを参照する。**
- **export 工程も執筆された本文だけを参照する。**
- **設定資料集は plan で初版を作成し、design（シーン設計）で参照・更新する。**

bible は「企画→設計」の間だけ生きる **設計の補助台帳** であり、
執筆・出力の段階には **設計結果（scene_design）にその情報が既に具体化されている**
ので、bible を直接見る必要がない。

---

## 2. なぜ write / export が bible を見てはいけないか

### write が bible を見ると起きる問題
1. **ドミノ崩壊**：執筆中に bible を更新すると、未確定の試行錯誤（revision で破棄された草稿の内容）が bible に混入し、以降のすべての生成が汚染される。
2. **責務の重複**：scene_design が既に `characters` / `foreshadowing` / `setting` 等の bible 由来情報を内包している。write が改めて bible を見るのは二重管理。
3. **存在意義の喪失**：write が bible を直接参照・更新するなら、bible は scene_design の単なるコピーになり、SSOT としての意味が消える。

### export が bible を見ると起きる問題
1. **実際の本文との乖離**：bible には「意図した設定」があり、本文には「実際に書かれた結果」がある。export が bible を参照すると、本文に書かれていない設定が付録等に紛れ込む。
2. **出力の純粋性**：KDP 原稿は「書かれた本文」の整形であるべき。bible は設計時の補助であり、出力対象ではない。

---

## 3. ライフサイクル図

```
[plan]   keywords → シリーズ企画
            │
            └─→ bible.v0 を作成（characters/glossary/foreshadowing/world_rules/
                                  relationships/subplots の初版）
            │
[design] 各シーンの設計
   │  ① bible を参照（進行中伏線・人物・世界ルール）
   │  ② scene_design を生成（bible 情報を「そのシーン用に具体化」して内包）
   │  ③ 新事実を bible へ書き戻し（commit）
   │       └─ bible.v1, v2, ... へ更新（巻末スナップショット）
   │
[write]   各シーンの執筆
   │  → scene_design のみ参照（bible は見ない）
   │  → 本文生成 → review → 品質ゲート
   │
[export]  原稿出力
   │  → 執筆本文のみ参照（bible / scene_design は見ない）
   │  → KDP 原稿・巻末付録（用語集・人物一覧は本文から抽出）を生成
```

**bible が直接関わるのは plan → design の区間だけ。**

---

## 4. ステージ別 詳細

### 4.1 plan（初版作成）
- **操作**：Write（新規作成）
- **トリガー**：企画生成時
- **内容**：series_plan から `characters` / `glossary` / `foreshadowing`（初期 plant）/ `world_rules` / `relationships` / `subplots` を初期構築。
- **出力**：`bible.v0`
- **bible 以外の参照**：なし

### 4.2 design（参照・更新）
- **操作**：Read（参照）＋ Write（更新）
- **トリガー**：巻デザイン・シーン設計生成時
- **参照**：bible の進行中伏線・人物属性・世界ルールを読み、シーン設計がそれらと矛盾しないよう誘導。
- **更新**：シーン設計で決まった新事実（新人物登場・伏線 plant/回収・関係変化・サブプロット進行）を bible へ書き戻す。
- **重要**：**更新は design の責務**。write に任せてはいけない。
- **スナップショット**：巻末で `bible.vN` を保存。

### 4.3 write（参照しない）
- **操作**：Read（scene_design のみ）
- **トリガー**：各シーン草稿生成時
- **参照**：そのシーンの `scene_design`（bible 情報は既に具体化済みで内包されている）。
- **bible へのアクセス**：**なし**。bible を参照・更新しない。
- **矛盾が見つかったら**：bible を直すのではなく、**scene_design を修正** する（design へ差し戻し）。bible は「設計時点の正当な事実」として守る。

### 4.4 export（参照しない）
- **操作**：Read（執筆本文のみ）
- **トリガー**：出力時
- **参照**：各シーンの `draft`（執筆された本文）。
- **bible へのアクセス**：**なし**。
- **付録生成（用語集・人物一覧等）**：bible からではなく、**本文から抽出** する。本文に書かれていない設定は出力しない。

---

## 5. スキーマ上の表現（bible.json 各フィールドの役割）

| フィールド | plan で初版 | design で参照 | design で更新 |
|---|---|---|---|
| `characters` | ✓ | ✓ | 新規追加・属性確定 |
| `glossary` | ✓ | ✓ | 新用語追加 |
| `foreshadowing` | ✓（初期 plant） | ✓（進行中を参照） | 新規 plant・回収 status 更新 |
| `world_rules` | ✓ | ✓ | 新ルール発見・追加 |
| `relationships` | ✓ | ✓ | `change_direction` 変化追跡 |
| `subplots` | ✓ | ✓ | `status` 遷移 |

※ write / export では一切参照・更新しない。

---

## 6. 矛盾の解決ルール

| ケース | 解決 |
|---|---|
| シーン設計が bible と矛盾 | design 段階で bible に合わせる（または bible を正して design を再生成） |
| 執筆中に bible との乖離発見 | **scene_design を修正**（design へ差し戻し）。bible は直接触らない |
| export 時に本文と bible が乖離 | bible は無視。本文を正とする（bible は設計補助に過ぎない） |
| bible 自体が誤っていた（初期設定ミス） | 明示的な `bible correct` 操作（理由記録）。自動では行わない |

---

## 7. バージョニング・スナップショット

- bible は `bible.v{volume}.json` として巻単位で保存（v0 = plan 初版、v1 = vol1 の design 終了後 …）。
- 現在世代用は `bible.json`（常に最新）。
- design の巻末ごとにスナップショットを取り、巻間の差分確認・巻き戻しに利用。

---

## 8. 現行実装との乖離（覚書・要修正）

現行コードは以下のようになっており、**設計と逆**。修正が必要。

| ステージ | 現行 | あるべき姿 |
|---|---|---|
| plan | bible 作成なし（どこかで初期化される） | **bible 初版を作成** |
| design | bible 参照・更新なし | **bible 参照・更新（責務）** |
| write | `get_bible_text_fn` で bible 参照・`summarize_and_update_bible` で更新 | **bible 参照・更新を削除。scene_design のみ参照** |
| export | `finalize` / `get_unresolved_foreshadowing` / `get_incomplete_subplots` で bible 参照 | **bible 参照を削除。本文から抽出** |

### 修正の優先順位
1. **write.py**：bible 参照・更新を削除（line 95, 107-108）。scene_design のみ渡すよう変更。
2. **export.py**：bible 参照を削除（line 26, 231, 237）。本文から付録を抽出するよう変更。
3. **design.py**：bible 参照・更新ロジックを追加（現行は 0 件）。
4. **plan.py**：bible 初版作成ロジックを追加（現行は 0 件）。

---

## 9. 受け入れ基準（チェックリスト）

- [ ] plan 完了時に `bible.v0` が存在する
- [ ] design が bible を参照し、新事実を書き戻している
- [ ] **write 実行中に bible ファイルが変更されていない**（read-only を遵守）
- [ ] **export 実行中に bible ファイルを読み込んでいない**
- [ ] export 出力（付録含む）が「本文に書かれた事実」のみから構成されている
- [ ] 巻末に `bible.vN` スナップショットが保存されている
