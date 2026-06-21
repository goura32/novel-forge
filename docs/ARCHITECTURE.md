# NovelForge Architecture Design

## 1. 設計背景

NovelForge は、ローカルLLMを使って小説シリーズを企画・構成・執筆・レビュー・改稿・出力する Python CLI ツールです。

### 採用アーキテクチャ

4層アーキテクチャを採用します。

| Layer | 役割 | 主要コンポーネント |
|---|---|---|
| CLI Interface | ユーザーとの対話、排他制御 | `cli.py` (Typer) |
| Orchestration | 状態遷移、パイプライン制御 | `engine/` (NovelEngine) |
| Domain Logic | シーン執筆、コンテキスト構築、Bible管理 | `scene_writer.py`, `context_builder.py`, `bible_manager.py` |
| Infrastructure | LLM通信、永続化、ログ、スキーマ検証 | `llm_client.py`, `json_parser.py`, `storage.py`, `schemas.py`, `quality_gate.py` |

**用語の定義**: [GLOSSARY.md](GLOSSARY.md)

---

## 2. モジュール構成

```text
src/novel_forge/
├── cli.py              # CLI エントリポイント + 排他制御 (Typer)
├── engine/             # オーケストレーション層 (Mixin パターン)
│   ├── __init__.py     # NovelEngine クラス定義
│   ├── base.py         # NovelEngineBase (__init__, helpers, state, _review_and_revise)
│   ├── plan.py         # PlanMixin (plan, 3-phase: core → characters → volumes)
│   ├── design.py       # DesignMixin (design, 3-phase: volume → chapter → scene)
│   ├── write.py        # WriteMixin (write, progress)
│   └── export.py       # ExportMixin (export, _assemble_manuscript)
├── scene_writer.py      # SceneWriter (シーン執筆パイプライン)
├── context_builder.py   # ContextBuilder (context/continuity 構築)
├── bible_manager.py     # BibleManager (Bible 管理)
├── models.py            # Pydantic データモデル
├── llm_client.py        # LLM クライアント (Ollama /api/chat)
├── json_parser.py       # JSON パース・型変換ユーティリティ
├── prompts.py           # プロンプト管理 (PromptManager)
├── quality_gate.py      # QualityGate (シーン品質評価) + recalc_review_score
├── schemas.py           # JSON Schema 検証
├── storage.py           # 永続化 (StateStorage, BlackboardStorage, BibleStorage)
└── kanji_data.py        # 常用漢字データ
```

### 2.1 責務分割

| モジュール | 責務 | 依存先 |
|---|---|---|
| `NovelEngine` | plan/design/write/export のオーケストレーション | SceneWriter, ContextBuilder, BibleManager |
| `SceneWriter` | シーンの draft/review/revise/summarize/bible_update | LLMClient, QualityGate, BlackboardStorage, BibleStorage |
| `ContextBuilder` | context/continuity 構築、シリーズ要約、デザイン要約 | BlackboardStorage, BibleStorage |
| `BibleManager` | Bible の更新・照会・最終確定 | BibleStorage |
| `LLMClient` | LLM API 通信、リトライ、JSON Schema 検証 | json_parser, schemas |
| `json_parser` | JSON パース（フォールバック付き）、型変換 | — |
| `QualityGate` | シーン品質判定、レビュースコア再計算 | — |

### 2.2 Mixin パターン

`NovelEngine` は複数の Mixin クラスを組み合わせて機能を構成します。

```python
class NovelEngine(
    NovelEngineBase,    # __init__, helpers, state, _review_and_revise
    PlanMixin,          # plan() — 3-phase: core → characters → volumes
    DesignMixin,        # design() — 3-phase: volume → chapter → scene
    WriteMixin,         # write(), progress()
    ExportMixin,        # export(), _assemble_manuscript()
):
    pass
```

MRO (Method Resolution Order): `NovelEngineBase` → `PlanMixin` → `DesignMixin` → `WriteMixin` → `ExportMixin`

---

## 3. データフロー

### 3.1 制作パイプライン

```
キーワード → [plan] シリーズ企画 (core → characters → volumes) + 自己レビュー → 人間確認（暗黙承認）
           → [design] 巻デザイン (volume → chapter → scene) + 自己修正（最大3回）
           → [write] シーン執筆（sequential）→ レビュー → 改稿 → 品質ゲート → Blackboard更新
           → [export] 原稿組立 → 最終レビュー → kdp_readiness_report.md
           → [next-volume] 次巻のデザイン生成
```

- シーンは **sequential のみ**（前シーン全文を `{continuity}` として次シーンに注入）
- デザイン自己修正は **最大3回**
- シーン品質ゲート不合格 → 自動改稿 → 再評価（最大2回）。不合格 → `強制出力済`

### 3.2 状態遷移

**シリーズ**: `計画中 → デザイン済 → 執筆中 → 初稿済 → 強制出力済 → 出力済`

**巻**: `計画中 → デザイン済 → 執筆中 → 初稿済 → 強制出力済 → 出力済`

**シーン**: `計画中 → 初稿済 → 修正済`
                  └→ `強制出力済`

### 3.3 人間介入ポイント

| 介入ポイント | タイミング | 内容 | 必須/任意 |
|---|---|---|---|
| シリーズ企画の確認 | plan 直後 | LLM自己レビュー結果を人間が確認。問題なければ暗黙的に次工程へ | **必須（暗黙承認）** |
| 最終レビュー | export 直後 | kdp_readiness_report.md の確認 | 任意 |

**それ以外の工程はすべて LLM 自律。**

---

## 4. レビュー・修正ループ

全工程のレビュー・修正ループは `NovelEngineBase._review_and_revise()` に共通化されています。

```python
def _review_and_revise(
    self,
    item: dict,
    review_fn,    # (item, system) -> review dict
    revise_fn,    # (item, review, system) -> revised item dict
    system: str,
    max_retries: int = 3,
    label: str = "",
) -> dict:
```

**フロー:**
1. `review_fn(item, system)` でレビュー実行
2. `recalc_review_score(review)` でスコア再計算
3. `score >= 70` かつ `critical` issue が0なら合格
4. 不合格なら `revise_fn(item, review, system)` で修正 → 再レビュー
5. 最大 `max_retries` 回繰り返し

**レビュースコア再計算ルール (`quality_gate.recalc_review_score`):**
- サブスコアの平均をベーススコアとする
- `critical` issue があれば score ≤ 50
- `major` issue が3つ以上あれば score ≤ 65
- `minor` only なら score ≥ 70

---

## 5. プロンプト戦略

### 5.1 デザイン3フェーズ

巻デザインの生成は3フェーズに分かれています:

1. **Phase 1 (巻構成)**: シリーズ企画から章のタイトルと役割を生成
2. **Phase 2 (章設計)**: 各章のテーマ、感情弧、伏線メモを生成
3. **Phase 3 (シーン設計)**: 各シーンの目標/結果/葛藤/視点を生成

詳細は [PROMPTS.md](PROMPTS.md) を参照。

### 5.2 コンテキスト注入

各シーン生成時に注入する情報:

1. **system**: JSON 出力 + 言語制約 (from `prompts/system.md`)
2. **context**: シリーズ企画 + 巻デザイン + Blackboard.facts + Bible
3. **scene**: デザイン内の当該シーン定義
4. **continuity**: 前シーン全文 + 直近シーン要約 + 引き継ぎメモ

### 5.3 スキーマ設計原則

- **LLM呼び出し時と保存時でスキーマを分ける**
- **engine で機械採番するフィールド（number, chapter_number, volume_number）は LLM スキーマに含めない**
- **IDs/numbers は LLM に入力せず、engine が機械的に割り当てる**

---

## 6. 記憶モデル (3層ハイブリッド)

### 6.1 State Machine (進捗管理)

`ProjectState` が制作進捗を管理。**事実記録と設定資料集は `state.json` とは別ファイル**として永続化。

### 6.2 事実記録（Blackboard）— 物語の事実

`blackboard.json` として独立ファイルで管理。

- **facts**: `(subject, predicate, object, confidence)` の事実リスト
- **scene_summaries**: シーンごとの要約
- **continuity_notes**: 次シーンへの引き継ぎメモ
- **subplots**: サブプロット進捗
- **timeline**: 時系列イベント

**更新**: シーン完了時に `SceneWriter.summarize_and_update_bible()` が facts を追加。

### 6.3 設定資料集（Bible）— メタデータ台帳

`bible.json` として独立ファイルで管理。

- **characters**: キャラクタープロファイル（名前、役割、外見、性格、動機、状態）
- **glossary**: 用語と定義
- **foreshadowing**: 伏線と回収状況
- **world_rules**: 世界観ルール
- **relationships**: キャラクター関係性
- **subplots**: サブプロット

**更新**: シーン完了時に `SceneWriter.summarize_and_update_bible()` が Bible を更新。
**巻レベルの最終更新**: `BibleManager.finalize()` が export 時に未回収伏線をチェック。

---

## 7. LLM モデルの選定

### 7.1 推奨モデル

**`qwen3.6:35b-a3b-mtp-q4_K_M`** を推奨モデルとします。

選定理由:
- **日本語能力**: 日本語の小説生成において、高い表現力と文法穩定性
- **JSON 出力**: `/api/chat` + `format: schema` + `think: true` で安定動作
- **長文処理**: 262,144 トークンの context 長
- **VRAM 効率**: Q4 量子化で 24GB VRAM GPU で動作可能

### 7.2 最適パラメータ

| パラメータ | 値 | 備考 |
|---|---|---|
| `think` | `true` | `false` は配列フィールドが空になる問題あり |
| `format` | `schema` | JSON Schema をそのまま渡す |
| `num_predict` | `-1` | 無制限。32768 も安定値 |
| `num_ctx` | `262144` | qwen3.6:35b の最大コンテキスト長 |
| `seed` | `42` | リトライ時にインクリメント |

### 7.3 モデルの切替

`--model` フラグで別のモデルを指定可能。

---

## 8. LLM API 設計

### 8.1 API Endpoint

`/api/chat` を採用。`format: schema` + `think: true` で安定した構造化出力。

### 8.2 リトライ戦略

- 最大リトライ回数: 2回（合計3回まで試行）
- リトライ時はエラーフィードバックをメッセージに追加
- JSON パースエラー → フィードバック再プロンプト
- スキーマ検証エラー → 不足フィールドを明示して再プロンプト
- リトライ時に seed をインクリメント（42 → 43 → 44）

### 8.3 JSON パースパイプライン (`json_parser.py`)

1. **直接 parse** — `message.content` を JSON としてパース
2. **Markdown fence 除去** — `` ```json ``` `` で囲まれた場合の中身を抽出
3. **改行エスケープ** — 文字列値内の改行を `\n` に変換
4. **括弧修正** — `「...」` → `"..."`
5. **シングルクォート修正** — `'...'` → `"..."`
6. **クォートなし値修正** — `key: value` → `key: "value"`
7. **コロン修正** — `"key", "value"` → `"key": "value"`
8. **範囲抽出** — `{...}` を抽出して再パース

### 8.4 型変換パイプライン (`json_parser.coerce_types`)

LLM の出力をスキーマに合わせて型変換:
- `dict` → `string` (例: `{age: "20代"}` → `"age: 20代"`)
- `list` → `string` (例: `["a", "b"]` → `"a、b"`)
- `string` → `array` (例: `"a, b, c"` → `["a", "b", "c"]`)
- `float` → `integer` (score フィールドは 0-100 範囲チェック)
- `string` → `integer` (数値文字列をパース)
- `object` → 再帰的に型変換、不足フィールドを補完

---

## 9. セキュリティとデータ保全

| 項目 | 内容 |
|---|---|
| パストラバーサル防止 | `..` を含む slug を拒否 |
| 原子的書き込み | 一時ファイル作成 → `fsync` → `rename` (POSIX atomic)。既存 JSON は `.bak` 退避 |
| RAW ログ | 全 LLM リクエスト/レスポンスを `raw_logs/` に保存 |
| 排他制御 | `series_dir/.lock` ファイルで同一シリーズの同時実行防止 |

---

## 10. 長文対応

1. **分割処理**: 各工程は scene または chapter 単位で LLM に投入
2. **集約の階層化**: scene → chapter → volume の順に段階的に集約
3. **Blackboard の巻ごとの要約**: 前巻の全データではなく、要約のみを次巻に引き継ぐ

---

## 11. ファイル構成

```text
<series_dir>/
├── .lock                          # 排他ロックファイル
├── state.json                     # プロジェクト状態
├── series_plan.json               # シリーズ企画
├── blackboard.json                # 事実記録
├── bible.json                     # 設定資料集
├── raw_logs/                      # LLM リクエスト/レスポンスログ
│   ├── 20260619_161231_series_plan.json
│   └── ...
├── vol01/
│   ├── design.json                # 巻デザイン（章＋シーン構成）
│   ├── vol01_ch01/
│   │   ├── vol01_ch01.md          # 章組立Markdown
│   │   ├── vol01_ch01_sc01.md     # シーン初稿
│   │   └── ...
│   └── vol01_ch02/
│       └── ...
├── vol02/
│   └── ...
└── exports/
    ├── vol01_manuscript.md
    ├── vol01_metadata.json
    └── vol01_kdp_readiness_report.md
```

---

## 12. 品質ゲート

### 12.1 合格基準

- `score >= 70`（0-100スケール）かつ `critical` / `blocker` issue が0件
- 不合格時は自動改稿 → 再評価（最大2回）。2回不合格 → `強制出力済`

### 12.2 レビュー指摘修正回数

| 工程 | デフォルト | 最大 | 設定方法 |
|---|---|---|---|
| シーン | 2回 | 設定可能 | `quality.max_review_retries` / `--max-retries` |
| デザイン | 3回 | — | ハードコード |
| シリーズ企画 | 3回 | — | ハードコード |

### 12.3 スコアリングガイド

| スコア | 意味 |
|---|---|
| 85-100 | 優秀。商業出版レベル |
| 70-84 | 合格。改善点はあるが出版可能 |
| 0-69 | 不合格。書き直しが必要 |

### 12.4 言語純度チェック

- ツールによる検出は行わない（JIS 漢字セットベースの検出は誤検出が多いため）
- プロンプトでの防止が主
- LLM が簡体字を出力した場合、レビューで `language_purity` カテゴリとして指摘する

---

*Last updated: 2026-06-21*
