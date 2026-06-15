# NovelForge 用語集

> このドキュメントは、NovelForge の全ドキュメント・コード・プロンプトで使用される用語を定義し、用語の揺れを防ぐために作成しました。

---

## 1. 作品階層

| 用語 | 英語 | 説明 |
|---|---|---|
| シリーズ | series | 作品全体。1つ以上の巻で構成される |
| 巻 | volume | シリーズの分割単位。KDP 提出の単位 |
| 章 | chapter | 巻の分割単位。複数のシーンをまとめる |
| シーン | scene | 章の分割単位。最小の執筆粒度 |
| 章設計 | chapter design | 章のテーマ、全シーンの要約、章の感情アーク（`ch{NN}_design.json`） |
| シーン設計 | scene design | MVME goal、POV、conflict、outcome、キャラクター（`vol{NN}_ch{NN}_sc{NN}_design.json`） |
| アウトライン修正履歴 | outline revision log | 自己修正の履歴。修正箇所、理由、前後のスコア（`vol{NN}_outline_revision_log.json`） |

**補足**: 番号フォーマットは `vol01`, `ch01`, `sc01`（プレフィックス2文字 + ゼロ埋め2桁）。

---

## 2. 制作フェーズ

| 用語 | 説明 |
|---|---|
| 企画 (plan) | キーワードからシリーズ全体の企画案を生成する工程 |
| アウトライン (outline) | 巻ごとの章・シーン構成を設計する工程 |
| 執筆 (write) | シーン本文を生成し、レビュー・改稿・品質ゲートを実行する工程 |
| エクスポート (export) | 完成原稿を KDP 向けに出力する工程 |
| 一括実行 (complete) | plan → outline → write → export を連続実行するコマンド |
| 次巻 (next-volume) | 現在の巻が完了した次に、次の巻のアウトラインを生成する工程 |

---

## 3. データモデル

### 3.1 状態管理

| 用語 | 説明 |
|---|---|
| ProjectState | シリーズ全体の状態を保持する Pydantic モデル |
| VolumeProgress | 巻ごとの進捗（ステータス、文字数）を管理 |
| SceneRecord | シーンごとの生成状況（ステータス、リトライ回数、各工程の出力） |
| 状態遷移 | 各要素（巻・シーン）のステータスが時間とともに変化する様子 |

### 3.2 記憶モデル（3層ハイブリッド）

| 用語 | 説明 |
|---|---|
| State Machine | 制作進捗を管理する状態機械。`ProjectState` が担当 |
| 事実記録（Blackboard） | 物語の事実を格納する共有知識ベース。キャラクターの位置、状態、イベントの記録 |
| 設定資料集（Bible） | メタデータ台帳。キャラクター情報、用語、伏線、世界観ルールを管理 |

**事実記録のデータ構造**:
- `facts`: 物語の事実リスト。各 fact は `(subject, predicate, object, confidence)` の形式
- `scene_summaries`: シーンごとの要約
- `continuity_notes`: 次シーンへの引き継ぎメモ

**Bible のデータ構造**:
- `characters`: キャラクタープロファイル（名前、外見、性格、状態）
- `glossary`: 用語と定義
- `foreshadowing`: 伏線と回収状況
- `world_rules`: 世界観ルール

---

## 4. アーキテクチャ

### 4.1 レイヤー

| 用語 | 説明 |
|---|---|
| CLI Interface | ユーザーとの対話層。Typer で実装 |
| Orchestration Layer | 状態遷移管理、パイプライン順序制御、リトライを担当 |
| Intelligence Layer | LLM を使った生成・評価・改善。ロジックを持たない |
| State / Memory Layer | 進捗管理、物語の事実、メタデータ台帳 |
| Infrastructure Layer | LLM 通信、永続化、ログ記録 |

### 4.2 コンポーネント

| 用語 | 説明 |
|---|---|
| NovelEngine | 中核となる状態機械。全コマンドがこのエンジンを通る |
| VolumeOutlinePipeline | 巻アウトラインの生成から自己レビュー・自己修正までを担当 |
| ScenePipeline | シーン単位の処理パイプライン。全工程が LLM 自律 |
| Resume | 中断した制作を再開する機能 |
| Blackboard (モジュール) | 物語の事実を管理するモジュール |
| CoverPromptGenerator | 表紙画像を生成するためのプロンプトとメタデータを出力 |
| QualityGate | シーンの品質を評価し、合格/不合格を判定 |

### 4.3 エージェント

| 用語 | 説明 |
|---|---|
| Planner Agent | シリーズ企画・巻アウトラインを設計 |
| Writer Agent | シーン本文を執筆 |
| Critic Agent | 生成物を評価し、改善点を抽出 |

---

## 5. プロンプト

| 用語 | 説明 |
|---|---|
| プロンプトテンプレート | `prompts/` の Markdown ファイル。`{variable}` プレースホルダーを使用 |
| レンダリング | `prompts.py` の `render_prompt()` で変数を置換する処理 |
| 自己レビュー | LLM が自分で生成した内容を評価する工程 |
| 自己修正 | 自己レビュー結果に基づき、LLM が自分で内容を修正する工程 |
| 別プロンプト原則 | 生成・レビュー・改稿はそれぞれ別のプロンプトファイルを使用（自己評価バイアス防止） |
| Fact | 物語の事実。`(subject, predicate, object, confidence)` の4要素で構成 |

**プロンプト一覧**:

| ファイル | 用途 |
|---|---|
| `system.md` | 共通システムプロンプト（JSON 出力指示、ジャンル/ペルソナ） |
| `series_plan.md` | シリーズ企画 |
| `series_plan_review.md` | シリーズ企画の自己レビュー |
| `volume_outline.md` | 巻アウトライン生成 |
| `volume_outline_review.md` | 巻アウトラインの自己レビュー |
| `volume_outline_revision.md` | 巻アウトラインの自己修正 |
| `scene_draft.md` | シーン初稿（MVME goal 使用） |
| `scene_review.md` | シーンレビュー |
| `scene_revision.md` | シーン改稿 |
| `scene_summary.md` | シーン要約 |
| `scene_quality_gate.md` | シーン品質ゲート |
| `bible_update.md` | メタデータ台帳更新 |
| `kdp_metadata.md` | KDP メタデータ |
| `kdp_final_review.md` | 最終レビュー（全巻通読） |
| `cover_prompt.md` | 表紙画像生成プロンプト |

---

## 6. 評価・品質

| 用語 | 説明 |
|---|---|
| 品質ゲート (Quality Gate) | シーンの品質を評価し、合格/不合格を判定する工程 |
| 構造的妥当性 | 物語の弧（導入→展開→転換→クライマックス→収束）が明確であるか |
| シーン間の一貫性 | シーン間の論理矛盾がないか、状態の連続性があるか |
| ペース配分 | 導入20%、展開・転換50%、クライマックス・収束30%の目安 |
| キャラクターアーク | メインキャラクターに変化（成長・堕落・気づき）があるか |
| 深刻度 | 問題の重要度。`critical` / `major` / `minor` の3段階 |
| force_exported | 品質ゲート3回不合格でも続行するためのフラグ |

**評価カテゴリ（レビュー）**:
- `structural_validity`: 構造的妥当性
- `scene_coherence`: シーン間の論理一貫性
- `pace_analysis`: ペース配分
- `character_arc_review`: キャラクターアーク

---

## 7. LLM 関連

| 用語 | 説明 |
|---|---|
| MVME | Minimalist & Mathematical Edition。シーン目標を `(State > Action | Result)` で表す手法 |
| JSON Schema 検証パイプライン | LLM 応答を4段階で検証（Raw parse → JSON Schema → Pydantic → 論理一貫性） |
| プリウォーミング | ツール起動時に `keep_alive: -1` でモデルを GPU メモリに固定する処理 |
| think: false | Ollama の思考モード無効化。`format: json` との同時使用が必須 |
| コンテキスト注入 | シーン生成時に Blackboard、Bible、前シーン要約をプロンプトに含める処理 |
| RAW ログ | 全 LLM リクエスト/レスポンスを `raw_logs/` に保存した記録 |

---

## 8. ファイル構造

| 用語 | 説明 |
|---|---|
| workdir | 作業ディレクトリ。1つのシリーズの全データが格納される |
| slug | シリーズの識別子。URL 安全な文字列（`my-series` 等） |
| `.novel-forge/` | 機械用データの隔離ディレクトリ。人間は見ない |
| `exports/` | 人間が目にする唯一の出力ディレクトリ |
| `designs/` | LLM 設計出力（JSON）の保存先 |
| `chapters/` | 章単位の Markdown 原稿 |
| `scenes/` | シーン単位の Markdown 原稿 |
| `quality_reports/` | シーン品質レポート |
| `raw_logs/` | LLM 生ログ |

---

## 9. 状態値

### 9.1 巻の状態

```
planned → outlined → drafting → drafted → exported → finalized
                                              → force_exported
```

### 9.2 シーンの状態

```
planned → drafted → reviewed → reviewed_n (n=1,2,3) → revised
```

---

## 10. セキュリティ

| 用語 | 説明 |
|---|---|
| パストラバーサル防止 | `..` を含む slug を拒否し、ディレクトリ外へのアクセスを防ぐ |
| 原子的書き込み | 一時ファイル作成 → `fsync` → `rename` による POSIX 原子書き込み |
| .bak 退避 | 既存 JSON 更新時に `.bak` として退避し、破損時に復旧可能にする |

---

## 11. 運用

| 用語 | 説明 |
|---|---|
| 暗黙承認 | 人間が明示的に承認しなくても、問題なければ次工程に進む方式 |
| 人間介入ポイント | シリーズ企画の確認（暗黙承認）と最終レビューの確認（任意）の2箇所のみ |
| スモーク検証 | LLM を使わずに、事前定義済みデータでパイプラインの動作を確認するテスト |
| タイムアウト | LLM リクエストの最大待機時間。工程別に設定（60s〜3600s） |

---

*Last updated: 2026-06-18*
