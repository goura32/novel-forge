# NovelForge Pipeline Design

## 1. CLI コマンド

### 1.1 グローバルオプション

| オプション | 短縮 | デフォルト | 説明 |
|---|---|---|---|
| `--config` | `-c` | `./.novel-forge.yaml` | 設定ファイルパス |
| `--workdir` | `-w` | 設定ファイル or カレント | 作業ディレクトリ |
| `--volume` | `-V` | 設定ファイル or `1` | 処理対象の巻番号 |
| `--model` | `-m` | 設定ファイル or デフォルト | LLM モデル名 |
| `--timeout` | `-t` | 工程別デフォルト | LLM タイムアウト (秒) |

### 1.2 使用例

```bash
# 初回: plan で作業フォルダ自動作成
uv run novel-forge plan "近未来東京 記憶探偵"
# → ./20260615_近未来東京記憶探偵/ に作業フォルダ作成
# → series_plan.json 生成（LLM自己レビュー結果含む）
# → .novel-forge.yaml 作成（workdir 自動設定）
# → 人間が内容を確認。問題なければ自動的に次工程へ

# 一括実行
uv run novel-forge complete "..."   # plan → outline → write → export

# カスタム作業ディレクトリ
uv run novel-forge plan "..." --workdir ./my-custom-dir

# 既存シリーズで再開
uv run novel-forge complete --workdir ./20260615_近未来東京記憶探偵

# 巻2に切り替え
uv run novel-forge next-volume
uv run novel-forge outline -V 2
```

### 1.3 段階実行コマンド

```bash
uv run novel-forge plan          --keywords "..."   # シリーズ企画（LLM自己レビュー→人間確認）
uv run novel-forge outline                        # 巻アウトライン（LLM自律）
uv run novel-forge write                          # シーン執筆（LLM自律）
uv run novel-forge export                         # KDP 向け出力（LLM自律）
uv run novel-forge bible         --action view    # メタデータ台帳参照（`view` / `export`）
uv run novel-forge status                         # 進捗確認
uv run novel-forge resume                         # 中断した工程から再開
uv run novel-forge next-volume                    # 次巻へ
uv run novel-forge recover                        # 破損復旧
uv run novel-forge probe-model                    # モデル接続確認
uv run novel-forge illustrate                     # 表紙画像プロンプト
uv run novel-forge complete                      # plan から一括実行
```

**削除されたコマンド**: `review`, `revise`, `quality` — LLM 自律処理のため CLI コマンドとして不要。

**用語の定義**: [GLOSSARY.md](GLOSSARY.md)

---

## 2. NovelEngine (engine.py)

中核となる状態機械。全コマンドはこのエンジンを通ります。

**タイムアウト**: 各工程のデフォルト値は `--timeout` フラグで上書き可能。工程別デフォルト: plan=300s, outline=600s, write=1800s, export=300s。

| コマンド | 役割 |
|---|---|
| `plan` | キーワードからシリーズ企画を生成。**LLM自己レビュー後、人間が内容を確認して次工程へ** |
| `outline` | 巻アウトライン（章・シーン構成）を生成。**LLM自律レビュー（構造的妥当性・シーン間の一貫性）を含む** |
| `write` | シーン本文を生成し、レビュー・改稿・品質ゲートを実行（**全工程LLM自律**） |
| `export` | KDP 向け出力を生成。最終レビュー（LLM自律）結果を `kdp_readiness_report.md` に記録 |
| `bible` | メタデータ台帳を更新・参照 |
| `status` | 現在の進捗と文字数を表示 |
| `complete` | plan → outline → write → export を一括実行 |
| `next-volume` | 次巻のアウトラインを生成 |
| `recover` | 破損した状態ファイルを復旧 |
| `resume` | 中断した工程から再開 |
| `probe-model` | モデル接続確認 |
| `illustrate` | 表紙画像プロンプト |

---

## 3. VolumeOutlinePipeline (volume_outline.py)

巻アウトラインの生成から自己レビュー・自己修正までを担当する。

**重要性**: 巻アウトラインは作品の品質を握る。シーン本文はすべてアウトラインの枠組み内で書かれるため、アウトラインが破綻すると連鎖的にシーン品質が低下する。

### 3.1 生成（設計）

シリーズ企画をベースに、1巻の構造を以下の階層で設計する。データモデル定義は [SPECIFICATION.md §2](../SPECIFICATION.md) を参照。

**章の役割（物語機能）:**

| 役割 | 説明 | 典型的な配置 |
|---|---|---|
| `introduction` | 導入。状況とキャラクターを提示 | 巻の最初の1〜2章 |
| `rising_action` | 展開。緊張感を高める | 巻の中盤 |
| `turning_point` | 転換。物語の方向性が変わる | 巻の中盤〜終盤の境 |
| `climax` | クライマックス。最大の緊張 | 巻の終盤1〜2章 |
| `resolution` | 収束。疑問の解決と次巻への伏線 | 巻の最後の1章 |

**設計時の構造的制約:**

1. **物語の弧（Story Arc）**: 導入→展開→転換→クライマックス→収束の流れが明確であること
2. **キャラクターアーク**: メインキャラクターに変化（成長・堕落・気づき）があること。変化は巻アウトライン内で完結せず、複数巻にわたる弧（Series Arc）として設計されていること
3. **ペース配分**: 全シーンの約20%を導入、50%を展開・転換、30%をクライマックス・収束に割り当てる
4. **連続性**: 各シーンの `outcome` が次のシーンの `goal`（State部分）に繋がっていること。シーン間で事実・状態・ロケーションが矛盾しないこと
5. **サブプロット**: メイン物語に加えて1〜2つのサブプロットが存在し、少なくとも1つは巻内で解決すること
6. **伏線**: 次巻への伏線が1箇所以上含まれること。伏線は設定資料集（Bible）に記録される

### 3.2 LLM自己レビュー

生成したアウトラインを LLM 自身で評価する。評価モデルは `volume_outline_review.json` スキーマに対応する。評価カテゴリの詳細は [GLOSSARY §6](GLOSSARY.md) を参照。

**深刻度の定義:**

| 深刻度 | 説明 | 対応 |
|---|---|---|
| `critical` | 物語の根幹に関わる（論理的破綻、致命的な矛盾） | 必ず修正 |
| `major` | 品質に大きく影響する（ペースの崩れ、キャラクターの不自然な行動） | 可能な限り修正 |
| `minor` | 改善点としては望ましいが必須ではない | 余力があれば修正 |

### 3.3 自己修正

**修正対象の判定:**
```
overall_score >= 7.0 かつ critical な issue が0件 → 合格
それ以外 → 不合格、自己修正を実行
```

**修正範囲の切り分け:**

| 修正範囲 | 条件 | 動作 |
|---|---|---|
| 全体再生成 | overall_score < 5.0、または critical issue が2件以上 | アウトライン全体を再生成 |
| 章再生成 | has_clear_arc == false、または chapter_roles_valid == false、または climax_placement_valid == false、または特定章に major issue が集中 | 該当章の全シーンを再生成 |
| シーン再生成 | scene_transitions_valid == false、または state_continuity == false、または pace_analysis で特定シーンに問題 | 該当シーンのみ再生成 |

**部分修正時のコンテキスト:**

| 修正範囲 | LLM に渡す情報 |
|---|---|
| 章再生成 | アウトライン全文 + 再生成対象章の前後2章の要約 |
| シーン再生成 | 所属章の全シーン定義 + 前後シーンの要約 |

**自己修正の手順:**
1. 修正範囲を判定（上記テーブルに基づく）
2. 該当箇所を再生成（部分修正時は前後のコンテキストを注入）
3. 修正後の再レビュー（§3.2 と同じ評価基準で再評価）
4. **最大3回**まで繰り返す。3回不合格なら最も問題の少ないバージョンを採用

**修正時の注意:**
- 部分修正を基本とする。全体再生成は最終手段
- 修正前後の差分を `vol01_outline_revision_log.json` に記録する
- 再生成された箇所の Blackboard 更新:
  - 該当シーンに関連する facts（`subject` または `object` が該当シーンのキャラクター・イベントに紐づくもの）を削除
  - 再生成後の内容から新規 facts を抽出して追加
  - `confidence` は再生成後は `0.8` にリセット（再生成で確度が変わるため）

### 3.4 出力

| ファイル | 内容 |
|---|---|
| `vol01_outline.json` | 巻アウトライン（章・シーン構成） |
| `vol01_outline_review.json` | 自己レビュー結果 |
| `vol01_outline_revision_log.json` | 修正履歴 |

---

## 4. ScenePipeline (scene_pipeline.py)

シーン単位の処理パイプライン。**全工程が LLM 自律。人間は介入しない。**

**基本原則: LLMが生成したものはすべてLLMがレビューする。**

| 階層 | 設計 | レビュー | 無限ループ防止 |
|---|---|---|---|
| シーン本文 | LLM | LLM（文章品質・物語の論理） | 最大3回。3回不合格→`force_exported` |

> シリーズ企画と巻アウトラインのレビューは VolumeOutlinePipeline §3.2〜3.3 を参照。人間介入ポイントは §11 を参照。

### 4.1 処理順序（sequential のみ）

シーンは**必ず順序通り**に処理する。各シーンの処理は以下の順序:

1. **Draft** — アウトラインとコンテキストから初稿を生成
2. **Review** — 初稿を評価し、改善点を抽出（人間には見せない）
3. **Quality Gate** — レビュー結果に基づき合格/不合格を判定
4. **改稿** — 不合格の場合、レビュー結果に基づき自動改稿
5. **再評価** — 改稿後に再度 Quality Gate 判定
6. **Summarize** — 合格した本文から要約を生成し、事実記録（Blackboard）に事実を記録

**前シーン要約の注入（必須）**:

シーンNの Draft 時、必ず前シーン（N-1）の要約をプロンプトに注入する。

```
シーン1: Draft(アウトライン, コンテキスト) → Review → QualityGate → Summarize
                                                                          ↓ 要約を注入
シーン2: Draft(アウトライン, コンテキスト, 前シーン要約) → Review → QualityGate → Summarize
                                                                          ↓ 要約を注入
シーン3: Draft(アウトライン, コンテキスト, 前シーン要約) → Review → QualityGate → Summarize
```

- 前シーン要約は事実記録（Blackboard）から取得する
- シーン1には前シーンがないため、要約注入なし
- 要約は `prompts/scene_draft.md` の `{continuity}` プレースホルダーに展開する

### 4.2 無限ループ防止

```
Quality Gate 不合格 → 改稿 → 再評価 → 不合格 → 改稿 → 再評価 → ...
```

このループは **最大3回** まで。3回不合格でも `force_exported` フラグを立てて続行する（中断しない）。

| 試行 | 動作 |
|---|---|
| 1回目 | Draft → Review → Quality Gate |
| 2回目 | 不合格 → 改稿 → Quality Gate |
| 3回目 | 不合格 → 改稿 → Quality Gate |
| 3回不合格 | `force_exported` フラグを立てて続行 |

### 4.3 レビューと改稿は別プロンプト

- **scene_draft.md**: シーン執筆用（MVME goal 使用）
- **scene_review.md**: レビュー用（評価基準に特化。本文生成指示は含めない）
- **scene_revision.md**: 改稿用（レビュー結果を受けて改善。新規生成ではない）

### 4.4 章の自動組立

全シーンが完了した時点で、章単位の Markdown を自動組立する。

```
出力タイミング:
- シーン1 → designs/ch01/vol01_ch01_sc01_design.json + scenes/ch01/vol01_ch01_sc01.md
- シーン2 → designs/ch01/vol01_ch01_sc02_design.json + scenes/ch01/vol01_ch01_sc02.md
- ...
- ch01 の全シーン完了 → designs/ch01/ch01_design.json（章設計）
- ch01 の全シーン完了 → chapters/ch01.md（章 Markdown、全シーン結合）
- ch01 の全シーン完了 → 設定資料集（Bible）更新（§6.1 参照）
```

**章設計** (`ch01_design.json`): 章のテーマ、全シーンの要約、章の感情アーク

**章 Markdown** (`ch01.md`): 章見出し + 各シーンの Markdown を結合。章末に章要約を追加

### 4.5 出力

| ファイル | 内容 |
|---|---|
| `designs/ch01/vol01_ch01_sc01_design.json` | シーン1 設計（LLM設計出力） |
| `scenes/ch01/vol01_ch01_sc01.md` | シーン1 本文（Markdown） |
| `designs/ch01/ch01_design.json` | 章1 設計（全シーン完了後） |
| `chapters/ch01.md` | 章1 原稿（全シーン完了後） |
| `.novel-forge/volumes/vol01/quality_reports/vol01_ch01_sc01_quality.json` | シーン1 品質レポート |

---

## 5. Resume (engine.py)

中断した制作を再開する。`Resume` は `state.json` から現在状態を読み込み、未完了のタスクから再開する。`Resume` は `NovelEngine` の一部として実装する。

データモデルは [SPECIFICATION.md §2](../SPECIFICATION.md) の `SceneRecord` を参照。

**未完了シーンの判定**:

| 状態 | 判定 |
|---|---|
| `status == "revised"` | 完了 |
| `status == "force_exported"` | 完了（品質ゲート3回不合格。再生成なし） |
| `quality_gate.passed == true` | 完了 |
| `status == "drafted"` かつ `quality_retries >= 3` | force_exported、完了扱い（再生成なし） |
| `status == "planned"` | 未生成、要生成 |
| `status == "drafted"` かつ `quality_gate.passed == false` かつ `quality_retries < 3` | 要再生成 |

**再開時の動作**:
- 未完了のシーンを sequential で再生成
- 既に完了したシーン（`revised` または `force_exported`）はそのまま使用
- 再生成時も前シーン要約を注入
- `force_exported` シーンは再生成しない（品質ゲート3回不合格のまま続行）

---

## 6. 事実記録（Blackboard）(blackboard.py)

物語の事実を管理する。`Fact` モデルは `(subject, predicate, object, confidence)` の4-tuple。スキーマは `blackboard.json` を参照。

**更新タイミング**: シーン完了時（ScenePipeline §4.1 の Summarize ステップ）に WriterAgent が facts を追加。

---

## 6.1 設定資料集（Bible）(bible.py)

メタデータ台帳。キャラクター情報、用語、伏線、世界観ルールを管理する。スキーマは `bible.json` を参照。

**更新タイミング**: 章完了時（全シーン完了 → 章 Markdown 組立の直後）に、当該章の全シーンから抽出した情報を Bible に反映。詳細は §4.4 を参照。
- 新キャラクターの登場 → `characters` に追加
- 新用語の使用 → `glossary` に追加
- 伏線の設置/回収 → `foreshadowing` に追加・更新
- 世界観ルールの明示 → `world_rules` に追加

**巻レベルの最終更新**: export 処理の開始時（§8 の原稿組立前）に、巻全体の Bible 整合性を確認し、未反映の事実・伏線があれば最終更新する。

---

## 7. CoverPromptGenerator (cover_prompt.py)

表紙画像を生成するためのプロンプトとメタデータを出力する。画像自体は生成しない（外部ツールを使用）。`cover_prompt.json` スキーマに適合する dict を出力する。

**CLI コマンド**: `novel-forge illustrate` が呼び出し、`exports/cover_prompt.json` を出力する。KDP 提出前の補助機能。

---

## 8. QualityGate (quality.py)

シーンの品質を評価し、合格/不合格を判定する。`QualityGate` はシーン単位と巻単位の両方でチェックを行う。

- `check_scene`: シーン品質を判定 → `{"passed": bool, "score": float, "issues": [...]}`
  - 評価カテゴリ: `opening_hook`, `character_distinction`, `foreshadowing_consistency`, `sensory_coverage`, `page_turner`
  - 合格判定: `score >= 7.0` かつ `critical` issue が0件

- `check_volume`: 巻全体の品質を判定 → `{"passed": bool, "score": float, "issues": [...]}`
  - 評価カテゴリ: `structural_validity`, `scene_coherence`, `pace_analysis`, `character_arc`
  - 全シーンの `check_scene` スコアの平均値と、巻レベルトポロジー（章の役割配置、物語の弧）を総合評価
  - `force_exported` シーンが1件以上存在する場合、スコア上限は 5.0 とする

## 9. Export 処理フロー

`export` コマンドの処理順序:

1. **Bible 最終更新** — §6.1 の巻レベル最終更新を実行
2. **原稿組立** — `manuscript.md` を chapters/ から組立
3. **KDP メタデータ生成** — `metadata.json`, `cover_prompt.json`
4. **最終レビュー（LLM自律）** — `kdp_final_review.md` プロンプトで巻全体を評価
5. **KDP 準備完了レポート生成** — `kdp_readiness_report.md` を exports/ に出力
   - レビュー結果サマリー
   - `force_exported` シーンの警告（該当する場合）
   - 未回収伏線のリスト（該当する場合）
   - KDP 提出前の人間確認事項

---

## 10. 状態遷移

```
Volume status:
  planned → outlined → drafting → drafted → exported → finalized
                                    │
                                    └→ force_exported (export時に
                                       force_exportedシーンが1件以上)

Scene status:
  planned → drafted → reviewed → revised
                         │
                         └→ force_exported (3回不合格時)

巻の drafted への遷移条件:
  全シーンが revised または force_exported になった時点で drafted に遷移。
  force_exported シーンが含まれていても巻は drafted に遷移可能。

巻の force_exported への遷移条件:
  export 処理開始時に force_exported シーンが1件以上存在する場合、
  巻ステータスは exported ではなく force_exported に遷移する。
  force_exported 巻も export コマンドの対象となる（kdp_readiness_report.md に警告記載）。

Resume (再開):
  任意の状態から再開可能。状態は state.json から読み込まれる。
  planned → plan から再開
  outlined → outline から再開
  drafting → write から再開（未完了のシーンのみ再生成）
  drafted → export から再開
  force_exported → export から再開（force_exported シーンは再生成しない）
```

---

## 11. 人間介入ポイント

**方針: 人間介入を最小限に。ツールが自律的にレビュー・改稿する。**

| 介入ポイント | タイミング | 内容 | 必須/任意 |
|---|---|---|---|
| シリーズ企画の確認 | plan 直後 | LLM自己レビュー結果を人間が確認。問題なければ暗黙的に次工程へ | **必須（暗黙承認）** |
| 最終レビュー | export 直後 | kdp_readiness_report.md の確認 | 任意 |

**それ以外の工程はすべて LLM 自律。人間には見せない。**

---
