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
| アウトライン (outline) | 巻ごとの章・シーン構成を設計する工程 |
| 執筆 (write) | シーン本文を生成し、レビュー・改稿・品質ゲートを実行する工程 |
| エクスポート (export) | 完成原稿を KDP 向けに出力する工程 |
| 一括実行 (complete) | plan → outline → write → export を連続実行 |
| 再開 (resume) | 中断した工程から再開 |

---

## 3. データモデル

### 3.1 状態管理

| 用語 | 説明 |
|---|---|
| ProjectState | シリーズ全体の状態を保持する Pydantic モデル |
| VolumeProgress | 巻ごとの進捗（ステータス、文字数）を管理 |
| SceneRecord | シーンごとの生成状況（ステータス、リトライ回数、品質ゲート結果） |
| SceneWriteContext | SceneWriter.write_scene() への引数をまとめたパラメータオブジェクト |

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
- `characters`: キャラクタープロファイル（名前、役割、外見、性格、動機、状態）
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
| CLI Interface | ユーザーとの対話層。Typer で実装 |
| Orchestration Layer | 状態遷移管理、パイプライン順序制御。`NovelEngine` が担当 |
| Domain Logic | シーン執筆、コンテキスト構築、Bible管理。各専用モジュールが担当 |
| Infrastructure Layer | LLM 通信、永続化、ログ記録、スキーマ検証 |

### 4.2 コンポーネント

| 用語 | 説明 |
|---|---|
| NovelEngine | 中核となるオーケストレーション層。全コマンドがこのエンジンを通る |
| SceneWriter | シーン単位の処理パイプライン。draft/review/revise/summarize/bible_update |
| ContextBuilder | context/continuity 構築、各種要約生成 |
| BibleManager | Bible の更新・照会・最終確定 |
| LLMClient | LLM API クライアント。リトライ・ログ・タイムアウト対応 |
| QualityGate | シーンの品質を評価し、合格/不合格を判定 |
| SceneWriteContext | write_scene() の引数をまとめたパラメータオブジェクト |

---

## 5. プロンプト

| 用語 | 説明 |
|---|---|
| プロンプトテンプレート | `prompts/` の Markdown ファイル。`{variable}` プレースホルダーを使用 |
| 自己レビュー | LLM が自分で生成した内容を評価する工程 |
| 別プロンプト原則 | 生成・レビュー・改稿はそれぞれ別のプロンプトファイルを使用（自己評価バイアス防止） |
| summarize_and_update_bible | シーン要約とBible更新を1回のLLM呼び出しで実行する統合メソッド |

**プロンプト一覧**:

| ファイル | 用途 |
|---|---|
| `system.md` | 共通システムプロンプト |
| `series_plan.md` | シリーズ企画 |
| `series_plan_review.md` | シリーズ企画の自己レビュー |
| `volume_outline.md` | 巻アウトライン生成 |
| `scene_draft.md` | シーン初稿 |
| `scene_review.md` | シーンレビュー |
| `scene_revision.md` | シーン改稿 |
| `scene_summary.md` | シーン要約 |
| `scene_summary_and_bible_update.md` | シーン要約 + Bible 更新（統合） |
| `bible_update.md` | Bible 更新 |

---

## 6. 評価・品質

| 用語 | 説明 |
|---|---|
| 品質ゲート (Quality Gate) | シーン単位の品質を評価し、合格/不合格を判定する工程。全レビュー共通で `score >= 70.0`（0-100スケール）かつ `critical`/`blocker` issue が0件で合格 |
| force_exported | 品質ゲート3回不合格でも続行するためのフラグ |
| 深刻度 | 問題の重要度。`critical` / `major` / `minor` の3段階 |
| 簡体字チェック | JIS漢字セット外の漢字を検出する品質チェック |

**レビューカテゴリ（8次元）**:
- `structural_validity`: 構造的妥当性
- `scene_coherence`: シーン間の論理一貫性
- `character_distinction`: キャラ立ち
- `foreshadowing_consistency`: 伏線の整合性
- `sensory_coverage`: 五感の網羅
- `page_turner`: ページターナー
- `tone_consistency`: 文体の一貫性
- `pov_consistency`: 視点の一貫性

---

## 7. LLM 関連

| 用語 | 説明 |
|---|---|
| MVME | Minimalist & Mathematical Edition。シーン目標を `(State > Action | Result)` で表す手法 |
| JSON Schema 検証パイプライン | LLM 応答を4段階で検証 |
| think: false | Ollama の思考モード無効化 |
| コンテキスト注入 | シーン生成時に Blackboard、Bible、前シーン要約をプロンプトに含める処理 |
| RAW ログ | 全 LLM リクエスト/レスポンスを `raw_logs/` に保存した記録 |

---

## 8. ファイル構造

| 用語 | 説明 |
|---|---|
| workdir | 作業ディレクトリ。1つのシリーズの全データが格納される |
| slug | シリーズの識別子。URL 安全な文字列 |
| `.novel-forge/` | 機械用データの隔離ディレクトリ |
| `exports/` | 人間が目にする唯一の出力ディレクトリ |
| `chapters/` | 章単位の Markdown 原稿 |
| `scenes/` | シーン単位の Markdown 原稿 |
| `raw_logs/` | LLM 生ログ |

---

## 9. 状態値

### 9.1 巻の状態

```
planned → outlined → drafting → drafted → exported → finalized
                                    │
                                    └→ force_exported
```

### 9.2 シーンの状態

```
planned → 初稿済 → 修正済
                │
                └→ 強制出力済 (3回不合格時)
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
| タイムアウト | LLM リクエストの最大待機時間。工程別に設定（60s〜3600s） |

---

*Last updated: 2026-06-25*
