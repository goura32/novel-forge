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

**補足**: 番号フォーマットは `vol01`, `ch01`, `sc01`（プレフィックス2文字 + ゼロ埋め2桁）。

---

## 2. 制作フェーズ

| 用語 | 説明 |
|---|---|
| 企画 (plan) | キーワードからシリーズ全体の企画案を生成する工程 |
| デザイン (design) | 巻ごとの章・シーン構成を設計する工程（3フェーズ） |
| 執筆 (write) | シーン本文を生成し、レビュー・改稿・品質ゲートを実行する工程 |
| エクスポート (export) | 完成原稿を KDP 向けに出力する工程 |
| 再開 (resume) | 中断した工程から再開 |

---

## 3. データモデル

### 3.1 状態管理

| 用語 | 説明 |
|---|---|
| ProjectState | シリーズ全体の状態を保持する Pydantic モデル |
| VolumeProgress | 巻ごとの進捗（ステータス、文字数）を管理 |
| SceneRecord | シーンごとの生成状況（ステータス、リトライ回数、品質ゲート結果） |

### 3.2 記憶モデル（3層ハイブリッド）

| 用語 | 説明 |
|---|---|
| State Machine | 制作進捗を管理する状態機械。`ProjectState` が担当 |
| 事実記録（Blackboard） | 物語の事実を格納する共有知識ベース |
| 設定資料集（Bible） | メタデータ台帳。キャラクター、伏線、関係性、サブプロット等を管理 |

**事実記録のデータ構造**:
- `facts`: 物語の事実リスト。各 fact は `(subject, predicate, object, confidence)` の4-tuple
- `scene_summaries`: シーンごとの要約
- `continuity_notes`: 次シーンへの引き継ぎメモ
- `subplots`: サブプロット進捗
- `timeline`: 時系列イベント

**Bible のデータ構造**:
- `characters`: キャラクタープロファイル（名前、役弧、外見、性格、動機、状態）
- `glossary`: 用語と定義
- `foreshadowing`: 伏線と回収状況
- `world_rules`: 世界観ルール
- `relationships`: キャラクター関係性（関係種類、変化方向、トリガーイベント）
- `subplots`: サブプロット（ID、名前、ステータス、進捗メモ）

---

## 4. アーキテクチャ

### 4.1 レイヤー

| 用語 | 説明 |
|---|---|
| CLI Interface | ユーザーとの対話層。排他制御を担当。Typer で実装 |
| Orchestration Layer | 状態遷移管理、パイプライン順序制御。`NovelEngine` が担当 |
| Domain Logic | シーン執筆、コンテキスト構築、Bible管理。各専用モジュールが担当 |
| Infrastructure Layer | LLM 通信、永続化、ログ記録、スキーマ検証 |

### 4.2 コンポーネント

| 用語 | 説明 |
|---|---|
| NovelEngine | 中核となるオーケストレーション層。Mixin パターンで機能を組み立てる |
| SceneWriter | シーン単位の処理パイプライン。draft/review/revise/summarize/bible_update |
| ContextBuilder | context/continuity 構築、各種要約生成 |
| BibleManager | Bible の更新・照会・最終確定 |
| LLMClient | LLM API クライアント。リトライ・ログ・タイムアウト対応 |
| json_parser | JSON パース（フォールバック付き）、型変換 |
| QualityGate | シーンの品質を評価し、合格/不合格を判定。レビュースコア再計算 |

### 4.3 Mixin パターン

| 用語 | 説明 |
|---|---|
| NovelEngineBase | 基底クラス。__init__, helpers, state, _review_and_revise |
| PlanMixin | シリーズ企画（3-phase: core → characters → volumes） |
| DesignMixin | 巻デザイン（3-phase: volume → chapter → scene） |
| WriteMixin | シーン執筆 |
| ExportMixin | KDP 出力 |

### 4.4 排他制御

| 用語 | 説明 |
|---|---|
| .lock | シリーズディレクトリに作成されるロックファイル |
| stale lock | ロック保持プロセスが終了していた状態。自動回収される |
| _acquire_lock() | ロック取得関数。O_CREAT\|O_EXCL でアトミック取得 |
| _release_lock() | ロック解放関数 |

---

## 5. プロンプト

| 用語 | 説明 |
|---|---|
| プロンプトテンプレート | `prompts/` の Markdown ファイル。`{variable}` プレースホルダーを使用 |
| 自己レビュー | LLM が自分で生成した内容を評価する工程 |
| 別プロンプト原則 | 生成・レビュー・改稿はそれぞれ別のプロンプトファイルを使用（自己評価バイアス防止） |
| 3フェーズデザイン | Phase1(章構成) → Phase2(章設計) → Phase3(シーン設計) の分割生成 |
| summarize_and_update_bible | シーン要約とBible更新を1回のLLM呼び出しで実行する統合メソッド |

**プロンプト一覧**:

| ファイル | 用途 |
|---|---|
| `system.md` | 共通システムプロンプト（言語制約、出力形式） |
| `series_plan_core.md` | シリーズ企画（核） |
| `series_plan_core_review.md` | シリーズ企画（核）のレビュー |
| `series_plan_core_revision.md` | シリーズ企画（核）の改訂 |
| `series_plan_characters.md` | シリーズ企画（キャラクター） |
| `series_plan_characters_review.md` | シリーズ企画（キャラクター）のレビュー |
| `series_plan_characters_revision.md` | シリーズ企画（キャラクター）の改訂 |
| `series_plan_volumes.md` | シリーズ企画（各巻） |
| `series_plan_volumes_review.md` | シリーズ企画（各巻）のレビュー |
| `series_plan_volumes_revision.md` | シリーズ企画（各巻）の改訂 |
| `volume_design.md` | 巻デザイン Phase 1: 章構成 |
| `volume_design_review.md` | 巻デザインのレビュー |
| `volume_design_revision.md` | 巻デザインの改訂 |
| `chapter_design.md` | 巻デザイン Phase 2: 章設計 |
| `chapter_design_review.md` | 章デザインのレビュー |
| `chapter_design_revision.md` | 章デザインの改訂 |
| `scene_design.md` | 巻デザイン Phase 3: シーンデザイン |
| `scene_design_review.md` | シーンデザインのレビュー |
| `scene_design_revision.md` | シーンデザインの改訂 |
| `scene_draft.md` | シーン初稿 |
| `scene_review.md` | シーンレビュー |
| `scene_revision.md` | シーン改稿 |
| `scene_summary_and_bible_update.md` | シーン要約 + Bible 更新（統合） |
| `kdp_metadata.md` | KDP メタデータ生成 |
| `cover_prompt.md` | 表紙画像生成 |

---

## 6. 評価・品質

| 用語 | 説明 |
|---|---|
| 品質ゲート (Quality Gate) | シーン単位の品質を評価し、合格/不合格を判定する工程 |
| 強制出力済 (force_exported) | 品質ゲート不合格でも続行するためのフラグ |
| 深刻度 | 問題の重要度。`critical` / `major` / `minor` / `blocker` の4段階 |
| スコア | 0-100 の数値。70以上で合格 |
| recalc_review_score | Python 側でレビュースコアを再計算する関数 |

**評価カテゴリ（9次元）**:
- `opening_hook`: 冒頭のフック
- `character_distinction`: キャラ立ち
- `sensory_coverage`: 五感の網羅
- `scene_closure`: シーン末尾の引き
- `dialogue_naturalness`: 台詞の自然さ
- `tone_consistency`: 文体の一貫性
- `scene_completeness`: シーン完結
- `language_purity`: 言語純度
- `pov_consistency`: 視点の一貫性

**スコアリングガイド**:
- 85-100: 優秀。商業出版レベル
- 70-84: 合格。改善点はあるが出版可能
- 0-69: 不合格。書き直しが必要

**スコア再計算ルール**:
- サブスコアの平均をベースに計算
- critical issue → score ≤ 50
- major issue 3つ以上 → score ≤ 65
- minor only → score ≥ 70

---

## 7. LLM 関連

| 用語 | 説明 |
|---|---|
| think: true | Ollama の思考モード。NovelForge では `true` を採用 |
| JSON Schema 検証 | LLM 応答をスキーマで検証し、型変換で補正 |
| コンテキスト注入 | シーン生成時に Blackboard、Bible、前シーン全文をプロンプトに含める処理 |
| RAW ログ | 全 LLM リクエスト/レスポンスを `raw_logs/` に保存した記録 |
| num_predict | LLM 出力トークン数上限。`-1` = 無制限 |
| num_ctx | コンテキスト長。`262144` が qwen3.6:35b の最大値 |
| json_parser | JSON パース（8段階フォールバック）と型変換を行うモジュール |

---

## 8. ファイル構造

| 用語 | 説明 |
|---|---|
| workdir | 作業ディレクトリ。1つのシリーズの全データが格納される |
| series_dir | 実際のシリーズディレクトリ（`{timestamp}_{slug}` 形式） |
| slug | シリーズの識別子。URL 安全な文字列 |
| exports/ | 人間が目にする唯一の出力ディレクトリ |
| raw_logs/ | LLM 生ログ |

---

## 9. 状態値

### 9.1 巻の状態

```
計画中 → デザイン済 → 執筆中 → 初稿済 → 出力済
                                │
                                └→ 強制出力済
```

### 9.2 シーンの状態

```
計画中 → 初稿済 → 修正済
              │
              └→ 強制出力済 (2回不合格時)
```

---

## 10. セキュリティ

| 用語 | 説明 |
|---|---|
| パストラバーサル防止 | `..` を含む slug を拒否 |
| 原子的書き込み | 一時ファイル作成 → `fsync` → `rename` による POSIX 原子書き込み |
| .bak 退避 | 既存 JSON 更新時に `.bak` として退避 |

---

## 11. 運用

| 用語 | 説明 |
|---|---|
| 暗黙承認 | 人間が明示的に承認しなくても、問題なければ次工程に進む方式 |
| 人間介入ポイント | シリーズ企画の確認（暗黙承認）と最終レビュー（任意）の2箇所のみ |
| 順序実行 | ローカルLLMは1度に1プロンプトしか処理できないため、全工程は順次実行 |

---

*Last updated: 2026-06-21*
