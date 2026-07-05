# NovelForge Prompt / Schema Quality Review

作成日: 2026-07-05
対象: `/mnt/hdd/projects/novel-forge/prompts`, `/mnt/hdd/projects/novel-forge/schemas`

## 0. 結論

現在のプロンプトテンプレートとスキーマは、**整合性以前に「品質の高い作品を作るための設計情報」が不足している箇所がある**。

特に問題が大きいのは以下。

1. **シーン本文プロンプトが薄い**
   - `scene_draft.md` は素材を渡すだけで、商業小説としての品質基準、文体、構成、心理描写、禁止事項が不足している。

2. **スキーマが品質上重要な情報を保持できない**
   - `scene_design.json` に `emotional_arc`, `sensory_focus`, `turning_point`, `hook`, `foreshadowing`, `subplot_progress` がない。
   - `chapter_design.json` も伏線・サブプロット・キャラクター変化を直接保持できない。

3. **レビューschemaが判定情報を保持できない**
   - `review.json` は `issues` だけで、`ready_for_publication`, `overall_assessment`, `strengths`, `risk_level` がない。
   - レビューの合否・品質傾向を後続工程やレポートに渡しにくい。

4. **章・シーン設計が「物語の機能」より「JSON項目埋め」に寄っている**
   - sceneの `goal/conflict/outcome` はあるが、読者感情・転換点・情報開示・伏線・余韻が弱い。

5. **プロンプトが品質基準を自然言語で持ちきれていない**
   - テンプレートとスキーマの役割分担方針はあるが、実際のテンプレートに品質基準が十分入っていない。

---

## 1. 評価基準

品質の高い商業小説を生成するため、prompt/schemaを以下の観点で評価した。

| 観点 | チェック内容 |
|---|---|
| 企画力 | 独自性、ターゲット、読者体験、ジャンル約束、差別化 |
| シリーズ構成 | 巻ごとの目的、変化、重複回避、シリーズ全体の上昇曲線 |
| キャラクター | 欲望、欠点、対立、関係性、行動特性、変化 |
| 章設計 | 章の役割、テーマ、感情の弧、伏線、サブプロット、転換点 |
| シーン設計 | goal/conflict/outcome, POV, hook, turning point, sensory focus, cliffhanger |
| 本文品質 | 冒頭フック、Show Don't Tell、台詞、地の文、視点一貫性、余韻 |
| 継続性 | Bible/Blackboard、前シーン、前巻、伏線回収、設定矛盾防止 |
| レビュー | severity, publication readiness, 指摘の具体性、過剰指摘防止 |
| スキーマ | 必須フィールド、後続工程で必要な情報の保持、semantic validation可能性 |
| ローカルLLM耐性 | JSON echo、未置換placeholder、曖昧な指示、過剰な自由度への耐性 |

---

## 2. フェーズ別レビュー

## 2.1 Series Concept

対象:

- `prompts/series_plan_concept.md`
- `schemas/series_plan_concept.json`

### 良い点

- 独自性、ターゲット、世界観、logline、売りポイントを要求している。
- slug重複回避を考慮している。
- loglineに「誰が、何に、どう立ち向かうか」を要求している。

### 不足

| 不足 | 影響 |
|---|---|
| 主人公の中心欲求 / 恐れ / 変化前後がない | 後続のキャラ・巻設計が薄くなりやすい |
| ジャンルの読者約束が明示されない | ミステリなら謎、ロマンスなら関係進展等の期待を外す可能性 |
| 競合作との差別化軸が構造化されていない | `selling_points` が抽象的になりやすい |
| 禁止パターンが弱い | 「真実を探る」等以外の曖昧表現が残る |
| シリーズ全体の最終到達点がない | 各巻が散漫になりやすい |

### 推奨スキーマ追加

`series_plan_concept.json` に以下を追加検討。

```json
{
  "protagonist_core_desire": "主人公が最も欲しているもの",
  "protagonist_core_fear": "主人公が最も恐れているもの",
  "series_end_state": "シリーズ最終巻で到達すべき状態",
  "genre_promises": ["読者に約束する体験"],
  "differentiation": "類似ジャンルとの差別化"
}
```

### 推奨プロンプト追加

- 「この作品で読者が繰り返し味わう快感」を具体的に書かせる。
- 「主人公が第1巻冒頭で信じている誤った信念」と「最終的に獲得する価値観」を書かせる。
- ジャンル別の読者約束を明示させる。

---

## 2.2 Series Characters

対象:

- `prompts/series_plan_characters.md`
- `schemas/series_plan_characters.json`

### 良い点

- 年齢、職業、性格、外見、背景、動機、欠点、成長方向を要求している。
- 役割重複、名前重複を避けようとしている。
- 対立軸・依存関係・行動特性に触れている。

### 不足

| 不足 | 影響 |
|---|---|
| `voice` / 口調 / 台詞傾向がschemaにない | 本文でキャラの台詞が均質になる |
| キャラクター同士の関係グラフがschema化されていない | 関係性の変化を追跡しづらい |
| `secret`, `misbelief`, `boundary`, `trigger` がない | ドラマを作る材料が弱い |
| 各キャラのscene上の行動原理が弱い | キャラが説明的な存在になりやすい |

### 推奨スキーマ追加

```json
{
  "voice": "口調・語彙・話し方の特徴",
  "behavioral_tics": ["行動上の癖"],
  "misbelief": "本人が信じている誤った前提",
  "secret": "物語上の秘密",
  "relationship_to_protagonist": "主人公との関係と対立",
  "scene_function": "登場時に物語へ与える機能"
}
```

### 推奨プロンプト追加

- 「台詞だけで誰かわかる特徴」を必須化。
- 「主人公と利害が一致する点 / 衝突する点」を分ける。
- 「初登場時に読者が受ける印象」と「終盤で反転する印象」を書かせる。

---

## 2.3 Series Volumes

対象:

- `prompts/series_plan_volumes.md`
- `schemas/series_plan_volumes.json`

### 良い点

- 各巻のテーマ・感情の弧・主要イベント・フックを要求している。
- 巻間の多様性を強調している。

### 不足

| 不足 | 影響 |
|---|---|
| 巻ごとの「読後感」がない | 巻ごとの差別化が弱くなる |
| 主人公/関係性の状態変化がない | シリーズ進行がイベント列になる |
| サブプロット/伏線の設置・回収計画がない | 後続で唐突な展開になりやすい |
| 最終巻以外のcliffhangerと最終巻のclosureのルールが曖昧 | 全巻が同じ引きになる可能性 |

### 推奨スキーマ追加

```json
{
  "reader_emotion": "この巻で読者に残す感情",
  "protagonist_change": "主人公の変化",
  "relationship_change": "主要関係性の変化",
  "foreshadowing_plan": ["設置/回収する伏線"],
  "subplot_plan": ["進行するサブプロット"],
  "volume_hook_type": "謎/関係/危機/決断/余韻など"
}
```

---

## 2.4 Volume Design

対象:

- `prompts/volume_design.md`
- `schemas/volume_design.json`

### 良い点

- 巻タイトルとpremiseを必須化したのは正しい。
- chapter purposeをenum化している。
- 起承転結を意識している。

### 不足

| 不足 | 影響 |
|---|---|
| 章単位の目的が `purpose` だけ | 章の具体的な物語機能が後続に渡りにくい |
| 各章の読者感情・情報開示・伏線機能がない | 章構成が表面的になる |
| `volume_number` に対応する planned volume の内容を選択していない | 指定巻の設計がシリーズ全体とズレる |
| 前巻からの継続課題の扱いが薄い | 巻をまたぐ連続性が弱い |

### 推奨スキーマ追加

`volume_design.chapters.items` に以下を追加検討。

```json
{
  "chapter_goal": "章で達成する物語上の目的",
  "reader_emotion": "章末で読者に残す感情",
  "information_reveal": "読者へ開示する新情報",
  "foreshadowing_setup": ["設置する伏線"],
  "foreshadowing_payoff": ["回収する伏線"],
  "subplot_movement": ["進行するサブプロット"]
}
```

### 過剰/注意点

- `purpose` の5語制約への説明が多く、品質指示よりもenum違反対策が目立つ。
- enum対策は必要だが、別途「良い章構成」の基準を足すべき。

---

## 2.5 Chapter Design

対象:

- `prompts/chapter_design.md`
- `schemas/chapter_design.json`

### 良い点

- `theme`, `emotional_arc`, `outcome`, `scenes` を持つ。
- 前章結果・前巻結果を渡す設計は良い。

### 不足

| 不足 | 影響 |
|---|---|
| schemaに `foreshadowing_notes`, `subplot_notes`, `characters` がない | promptの役割説明と保存情報が一致しない |
| 章内の転換点がない | シーンが並列になりやすい |
| 章末のhook/余韻がない | 次章への牽引力が弱い |
| 各sceneの役割分類がない | 本文時に単調なscene列になる |

### 推奨スキーマ追加

```json
{
  "chapter_turning_point": "章内で不可逆に変わる出来事",
  "chapter_hook": "章末の引き/余韻",
  "foreshadowing_notes": ["伏線メモ"],
  "subplot_notes": ["サブプロット進行"],
  "characters": ["章で重要な人物"],
  "scenes[].scene_function": "setup/confrontation/reversal/payoff/aftermath 等",
  "scenes[].emotional_shift": "このシーンで変化する感情"
}
```

### 現raw logから見える問題

`raw_summary.md` では、`{volume_title}`, `{volume_premise}` が未置換でLLMへ渡っている。
これは整合性問題だが、品質面でも致命的。章設計時に巻の個性が欠落する。

---

## 2.6 Scene Design

対象:

- `prompts/scene_design.md`
- `schemas/scene_design.json`

### 良い点

- `goal`, `conflict`, `outcome`, `pov`, `characters`, `key_events`, `setting` を持つ。
- 前シーン結果を渡している。

### 不足

| 不足 | 影響 |
|---|---|
| `hook` がない | 冒頭が説明で始まりやすい |
| `turning_point` がない | シーン内に不可逆な変化が起きにくい |
| `emotional_arc` がschemaにない | 感情変化を本文に渡しにくい |
| `sensory_focus` がない | 感覚描写が場当たり的になる |
| `subtext` がない | 台詞が説明的になる |
| `foreshadowing` / `payoff` がない | 伏線設置・回収が偶然任せになる |
| `ending_hook` がない | シーン末尾が平板になりやすい |

### 推奨スキーマ追加

```json
{
  "hook": "冒頭1-2文で提示すべき具体的な異変/行動/対立",
  "turning_point": "シーン中盤〜終盤で不可逆に変わる事実/関係/決意",
  "emotional_arc": "開始感情 -> 終了感情",
  "sensory_focus": ["このシーンで重点的に使う感覚"],
  "subtext": "台詞の裏にある本音・隠し事",
  "foreshadowing": ["設置/回収する伏線"],
  "ending_hook": "次シーンへ読者を進ませる引き"
}
```

### 過剰/注意点

- あまり多くのフィールドを required にするとローカルLLMの失敗率が上がる。
- requiredは `hook`, `turning_point`, `emotional_arc`, `ending_hook` 程度から始め、他はoptionalでもよい。

---

## 2.7 Scene Draft

対象:

- `prompts/scene_draft.md`
- `schemas/scene_draft.json`

### 良い点

- series/outline/scene/context/continuity/subplots/relationships/foreshadowing を渡そうとしている。
- 出力を `title`, `content` に絞っているため本文生成は単純。

### 不足

`scene_draft.md` は現在48行で、本文品質の指示が不足している。

| 不足 | 影響 |
|---|---|
| 冒頭フックの明示がない | 説明から始まりやすい |
| Show Don't Tell がない | 設定・感情を説明しがち |
| 台詞の自然さ/短さ/サブテキスト指示がない | 説明台詞が増える |
| 地の文の文体制約がない | 文体が揺れる |
| POV制約がない | 他キャラ内面に侵入しやすい |
| 感覚描写の使い方がない | 感覚描写が少ない、または反復する |
| シーンの終わり方の指示がない | 余韻・引きが弱い |
| 禁止事項がない | 設定説明、箇条書き、メタ言及、英語混入が起きやすい |

### 推奨プロンプト追加

`scene_draft.md` に以下を追加する。

```md
## 本文品質要件

- 冒頭1-2文で、説明ではなく具体的な行動・異変・対立を提示する。
- 世界設定やルールは説明文で列挙せず、行動・環境・身体感覚・会話の結果として示す。
- POV人物が知覚できない他者の内面を書かない。
- 台詞は短く、説明ではなく欲望・隠し事・対立を含ませる。
- 感覚描写は最低3種類。ただし直近シーンと同じ感覚モチーフを繰り返さない。
- シーン末尾は結果を確定させつつ、次の疑問・緊張・余韻を残す。
- 本文中に「このシーンでは」「設定上」「伏線として」などのメタ説明を書かない。
```

### 推奨スキーマ追加

`scene_draft.json` はシンプルでよいが、品質監査のため以下をoptionalで持つ案がある。

```json
{
  "author_notes": "生成意図。保存しない/監査用。通常は不要"
}
```

ただし本文生成の安定性を優先するなら、`title/content` のままにしてレビューを強化する方がよい。

---

## 2.8 Scene Review / Revision

対象:

- `prompts/scene_review.md`
- `prompts/scene_revision.md`
- `schemas/review.json`

### 良い点

- レビュー観点はある程度具体的。
- severity分類がある。
- 問題がなければ空issuesを返す指示がある。

### 不足

| 不足 | 影響 |
|---|---|
| review schemaに `ready_for_publication` がない | downstreamで品質状態を扱いにくい |
| strengthsがない | 良い点を壊さない改稿がしにくい |
| issueの修正優先度・publication blockingが曖昧 | 軽微な指摘で過修正しやすい |
| severityの定義がやや粗い | 重要/致命的の過剰判定が起きる |
| revision promptが短い | 指摘以外を壊さない保証が弱い |

### 推奨review schema

```json
{
  "ready_for_publication": true,
  "overall_assessment": "短い総評",
  "strengths": ["維持すべき良い点"],
  "issues": [
    {
      "severity": "致命的|重要|軽微",
      "field": "content",
      "description": "問題",
      "suggestion": "修正方針",
      "before": "該当箇所",
      "after": "置換案",
      "publication_blocking": true
    }
  ]
}
```

### severity再定義

- `致命的`: 出版不可。POV崩壊、設定矛盾、因果破綻、本文途中切断、言語制約違反、重大なキャラ矛盾。
- `重要`: 出版前に直すべき。説明過多、弱い冒頭、関係性の説得力不足、感情変化不足。
- `軽微`: 任意改善。言い回し、描写追加、リズム調整。

### readinessルール

- `ready_for_publication=true` の場合、`致命的` / `重要` issue は0件。
- `ready_for_publication=false` の場合、少なくとも1件の `致命的` または `重要` issue が必要。
- これをschemaだけでなく保存前正規化でも保証する。

---

## 2.9 Bible Update

対象:

- `prompts/scene_summary_and_bible_update.md`
- `schemas/scene_summary_and_bible_update.json`
- `schemas/bible_update.json`

### 良い点

- シーン要約とBible更新を一体化している。
- 伏線、関係性、サブプロット、world_rulesを扱う。

### 不足

| 不足 | 影響 |
|---|---|
| 既存項目の更新/新規追加/完了の区別が弱い | Bibleが重複・肥大化しやすい |
| timelineがschema化されていない | 長編の時系列追跡が弱い |
| contradiction checkがない | 設定矛盾の蓄積を検出しにくい |
| 関係性のbefore/afterがない | キャラ関係の変化を追いにくい |

### 推奨追加

```json
{
  "timeline_events": ["時系列イベント"],
  "contradiction_risks": ["既存Bibleと矛盾しそうな点"],
  "updated_existing_items": ["更新した既存項目ID/名称"],
  "relationship_changes": [
    {
      "character_a": "",
      "character_b": "",
      "before": "",
      "after": "",
      "trigger_event": ""
    }
  ]
}
```

---

## 3. 横断的な過不足

## 3.1 不足している品質制御

- [ ] ジャンル別品質基準
  - ミステリ: 謎・手がかり・誤誘導・解決
  - ロマンス: 距離変化・誤解・選択・親密さ
  - ファンタジー: ルール提示・代償・驚異・一貫性
  - SF: 仮説・社会的影響・技術制約

- [ ] 読者感情の設計
  - 各巻/章/シーンで読者に残す感情を明示する。

- [ ] シーン機能の分類
  - setup, confrontation, reversal, payoff, aftermath, reveal など。

- [ ] サブテキスト
  - 台詞の裏にある欲望・隠し事・対立を明示する。

- [ ] 伏線の設置/回収
  - 設置と回収を分けて管理する。

- [ ] 設定説明の抑制
  - 世界観ルールを本文で説明せず、行動・環境・結果で示す。

## 3.2 過剰または注意が必要な制御

- `purpose` enum対策の説明が多く、創作品質指示を圧迫している。
- スキーマdescriptionに文字数推奨が多いが、レビューで使うなら良い。ただし実装validatorと混同しないこと。
- schema requiredを増やしすぎると、ローカルLLMの失敗率が上がる。
- 本文生成schemaを複雑にしすぎると、本文よりメタ情報生成へ意識が逸れる。

## 3.3 追加すべきsemantic validators

JSON Schemaではなくコード側で検証する。

- [ ] requested volume_number と出力対象の整合
- [ ] chapter/scene番号の重複禁止
- [ ] `purpose` の順序・最低構成
- [ ] scene `pov` が登場人物に含まれるか
- [ ] scene `outcome` が次sceneのcontextに渡るか
- [ ] review readiness と issue severity の矛盾禁止
- [ ] unresolved foreshadowing の最終巻残存チェック
- [ ] generated textに未置換placeholder `{xxx}` が残っていないか

---

## 4. 改善順序

### Phase A: まず壊れている品質入力を直す

- [ ] 未置換placeholderを全解消
- [ ] `chapter_design` に `volume_title`, `volume_premise` を実際に渡す
- [ ] `scene_design` に章テーマ・章感情弧・伏線・サブプロット情報を渡す
- [ ] `scene_review` / `scene_revision` の `concept_json` 問題を解消

### Phase B: レビューschemaを強化する

- [ ] `review.json` に `ready_for_publication`, `overall_assessment`, `strengths` を追加
- [ ] readiness/severity矛盾を正規化するコードを追加
- [ ] review promptにseverity基準を再定義

### Phase C: 設計schemaを品質重視に拡張する

優先順:

1. `scene_design.json`
   - `hook`, `turning_point`, `emotional_arc`, `ending_hook`
2. `chapter_design.json`
   - `chapter_turning_point`, `chapter_hook`, `foreshadowing_notes`, `subplot_notes`
3. `volume_design.json`
   - `reader_emotion`, `information_reveal`, `foreshadowing_setup/payoff`
4. `series_plan_*`
   - protagonist desire/fear, genre promises, relationship arc

### Phase D: scene_draft promptを強化する

- [ ] 冒頭フック
- [ ] Show Don't Tell
- [ ] POV制約
- [ ] 台詞サブテキスト
- [ ] 感覚描写3種類 + 反復禁止
- [ ] 設定説明禁止
- [ ] 末尾の引き/余韻

### Phase E: 実モデル検証

- [ ] ジャンル違いの2〜3作品で `plan -> design -> write` を実行
- [ ] raw logを比較
- [ ] 汎用的な問題だけをprompt/schemaへ戻す
- [ ] 作品固有最適化はしない

---

## 5. テスト追加計画

### Contract tests

- [ ] promptが要求する品質フィールドがschemaに存在する
- [ ] schema required fixtureがすべて通る
- [ ] review readiness/severity矛盾がfailする
- [ ] 未置換placeholderが残らない

### Fake LLM semantic tests

- [ ] scene_designが `hook/turning_point/ending_hook` を保存する
- [ ] scene_draft promptに品質要件が含まれる
- [ ] review promptが軽微issueだけでpublish不可にしない
- [ ] revision promptが指摘外の本文を大きく壊さない

### Raw log audit tests / scripts

- [ ] 連続シーンで同じ感覚描写が反復していないか
- [ ] 冒頭が説明文だけで始まっていないか
- [ ] POV外の内面描写が混入していないか
- [ ] 世界観ルールを直接説明しすぎていないか

---

## 6. 完了条件

- [ ] `scripts/validate_prompts.py` がgreen
- [ ] prompt/schema/model対応表が現実装と一致
- [ ] `review.json` がpublication readinessを表現できる
- [ ] `scene_design` が本文品質に必要な設計情報を保持できる
- [ ] `scene_draft.md` に商業小説品質要件が明記されている
- [ ] fake LLMで拡張フィールドが保存・利用される
- [ ] 実モデルraw logで、冒頭/描写/POV/末尾/レビュー矛盾を確認済み

---

## 7. 最初に着手する具体タスク

1. `scene_draft.md` に本文品質要件を追加する。
2. `review.json` と `scene_review.md` に `ready_for_publication` / `strengths` / `overall_assessment` を追加する。
3. `scene_design.json` に `hook`, `turning_point`, `emotional_arc`, `ending_hook` を追加する。
4. `chapter_design.json` に `chapter_turning_point`, `chapter_hook`, `foreshadowing_notes`, `subplot_notes` を追加する。
5. 追加フィールドを `models.py` と保存・組み立て処理に通す。
6. fake LLMテストで追加フィールドが本文promptへ渡ることを確認する。

この順なら、整合性修正だけで終わらず、本文品質を上げるための情報経路を先に作れる。
