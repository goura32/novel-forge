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
| Infrastructure | LLM通信、永続化、ログ、スキーマ検証 | `llm_client.py`, `storage.py`, `schemas.py`, `quality_gate.py` |

**用語の定義**: [GLOSSARY.md](GLOSSARY.md)

---

## 2. モジュール構成

```text
src/novel_forge/
├── cli.py              # CLI エントリポイント + 排他制御 (Typer)
├── engine/             # オーケストレーション層 (Mixin パターン)
│   ├── __init__.py     # NovelEngine クラス定義
│   ├── base.py         # NovelEngineBase (__init__, helpers, state)
│   ├── plan.py         # PlanMixin (plan, _generate_plan, _review_series_plan)
│   ├── outline.py      # OutlineMixin (outline, _generate_outline 3-phase)
│   ├── write.py         # WriteMixin (write, progress)
│   └── export.py       # ExportMixin (export, _assemble_manuscript)
├── scene_writer.py      # SceneWriter (シーン執筆パイプライン)
├── context_builder.py   # ContextBuilder (context/continuity 構築)
├── bible_manager.py     # BibleManager (Bible 管理)
├── models.py            # Pydantic データモデル
├── llm_client.py        # LLM クライアント (Ollama /api/generate)
├── prompts.py           # プロンプト管理 (PromptManager)
├── quality_gate.py      # QualityGate (シーン品質評価)
├── schemas.py           # JSON Schema 検証
├── storage.py           # 永続化 (StateStorage, BlackboardStorage, BibleStorage)
└── kanji_data.py        # 常用漢字データ
```

### 2.1 責務分割

| モジュール | 責務 | 依存先 |
|---|---|---|
| `NovelEngine` | plan/outline/write/export のオーケストレーション | SceneWriter, ContextBuilder, BibleManager |
| `SceneWriter` | シーンの draft/review/revise/summarize/bible_update | LLMClient, QualityGate, BlackboardStorage, BibleStorage |
| `ContextBuilder` | context/continuity 構築、シリーズ要約、アウトライン要約 | BlackboardStorage, BibleStorage |
| `BibleManager` | Bible の更新・照会・最終確定 | BibleStorage |

### 2.2 SceneWriteContext (Parameter Object)

`SceneWriter.write_scene()` への引数を `SceneWriteContext` データクラスでまとめています。

```python
class SceneWriteContext(BaseModel):
    lang: str
    vol_num: int
    build_context_fn: Any          # () -> str
    build_continuity_fn: Any       # (scene_number, vol_num) -> str
    get_series_plan_summary_fn: Any  # () -> str
    get_outline_summary_fn: Any    # (outline) -> str
    get_scene_summary_fn: Any      # (scene) -> str
    get_bible_text_fn: Any         # () -> str
    load_scene_draft_fn: Any       # (vol_num, scene_number, chapter_number) -> str
```

---

## 3. データフロー

### 3.1 制作パイプライン

```
キーワード → [plan] シリーズ企画 + 自己レビュー → 人間確認（暗黙承認）
           → [outline] 巻アウトライン（3フェーズ）→ 自己修正（最大3回）
           → [write] シーン執筆（sequential）→ レビュー → 改稿 → 品質ゲート → Blackboard更新
           → [export] 原稿組立 → 最終レビュー → kdp_readiness_report.md
           → [next-volume] 次巻のアウトライン生成
```

- シーンは **sequential のみ**（前シーン全文を `{continuity}` として次シーンに注入）
- アウトライン自己修正は **最大3回**
- シーン品質ゲート不合格 → 自動改稿 → 再評価（最大2回）。不合格 → `強制出力済`

### 3.2 状態遷移

**シリーズ**: `計画中 → アウトライン済 → 執筆中 → 初稿済 → 強制出力済 → 出力済`

**巻**: `計画中 → アウトライン済 → 執筆中 → 初稿済 → 強制出力済 → 出力済`

**シーン**: `計画中 → 初稿済 → 修正済`
                  └→ `強制出力済`

### 3.3 人間介入ポイント

| 介入ポイント | タイミング | 内容 | 必須/任意 |
|---|---|---|---|
| シリーズ企画の確認 | plan 直後 | LLM自己レビュー結果を人間が確認。問題なければ暗黙的に次工程へ | **必須（暗黙承認）** |
| 最終レビュー | export 直後 | kdp_readiness_report.md の確認 | 任意 |

**それ以外の工程はすべて LLM 自律。**

---

## 4. プロンプト戦略

### 4.1 アウトライン3フェーズ

巻アウトラインの生成は3フェーズに分かれています:

1. **Phase 1 (章構成)**: シリーズ企画から章のタイトルと役割を生成
2. **Phase 2 (章設計)**: 各章のテーマ、感情弧、伏線メモを生成
3. **Phase 3 (シーン設計)**: 各シーンの目標/結果/葛藤/視点を生成

詳細は [PROMPTS.md](PROMPTS.md) を参照。

### 4.2 JSON Schema 検証パイプライン

```text
LLM Response
  │
  ├─▶ Step 1: Raw content parse (unwrap markdown fence, `{result:...}`)
  ├─▶ Step 2: Draft202012Validator 構造検証
  ├─▶ Step 3: Pydantic 型チェック
  └─▶ Step 4: 論理一貫性チェック (continuity, Blackboard)
```

### 4.3 コンテキスト注入

各シーン生成時に注入する情報:

1. **system**: JSON 出力 + 言語制約 + ジャンル/ペルソナ指示 (from `prompts/system.md`)
2. **context**: シリーズ企画 + 巻アウトライン + Blackboard.facts + Bible
3. **scene**: アウトライン内の当該シーン定義
4. **continuity**: 前シーン全文 + 直近シーン要約 + 引き継ぎメモ

### 4.4 スキーマ設計原則

- **LLM呼び出し時と保存時でスキーマを分ける**
  - 章構成生成時: `chapter_outline.json`（`{chapters: [{title, purpose}]}`）
  - シーン設計生成時: `scene_outline.json`（`{title, goal, outcome, ...}`）
  - 保存時: `volume_outline.json`（`{chapters: [{title, purpose, scenes: [...]}]}`）
- **engine.py で機械採番するフィールド（number, chapter_number, volume_number）は LLM スキーマに含めない**

---

## 5. 記憶モデル (3層ハイブリッド)

### 5.1 State Machine (進捗管理)

`ProjectState` が制作進捗を管理。**事実記録と設定資料集は `state.json` とは別ファイル**として永続化。

### 5.2 事実記録（Blackboard）— 物語の事実

`blackboard.json` として独立ファイルで管理。

- **facts**: `(subject, predicate, object, confidence)` の事実リスト
- **scene_summaries**: シーンごとの要約
- **continuity_notes**: 次シーンへの引き継ぎメモ
- **subplots**: サブプロット進捗
- **timeline**: 時系列イベント

**更新**: シーン完了時に `SceneWriter.summarize_and_update_bible()` が facts を追加。

### 5.3 設定資料集（Bible）— メタデータ台帳

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

## 6. LLM モデルの選定

### 6.1 推奨モデル

**`qwen3.6:35b-a3b-mtp-q4_K_M`** を推奨モデルとします。

選定理由:
- **日本語能力**: 日本語の小説生成において、高い表現力と文法穩定性
- **JSON 出力**: `/api/generate` + `format: schema` + `think: false` で安定動作
- **長文処理**: 131,072 トークンの context 長
- **VRAM 効率**: Q4 量子化で 24GB VRAM GPU で動作可能

### 6.2 最適パラメータ

| パラメータ | 値 | 備考 |
|---|---|---|
| `think` | `false` | `true` は content 空になる |
| `format` | `schema` | JSON Schema をそのまま渡す |
| `num_predict` | `16384` | 1024〜16384 全スケールで安定 |
| `num_ctx` | `65536` | GPU 安定値 |

### 6.3 モデルの切替

`--model` フラグで別のモデルを指定可能。

---

## 7. LLM API 設計

### 7.1 API Endpoint

`/api/generate` を採用。`format: JSON Schema` + `think: false` で安定した構造化出力。

### 7.2 リトライ戦略

- 最大リトライ回数: 2回（合計3回まで試行）
- リトライ時はエラーフィードバックをメッセージに追加
- JSON パースエラー → フィードバック再プロンプト
- スキーマ検証エラー → 不足フィールドを明示して再プロンプト

### 7.3 JSON抽出パイプライン

1. **直接parse** — `message.content` を JSON としてパース
2. **Markdown fence フォールバック** — `` ```json ``` `` で囲まれた場合の中身を抽出
3. **ラッパーオブジェクトフォールバック** — `{result: ...}` 等のラッパーオブジェクトを抽出

---

## 8. セキュリティとデータ保全

| 項目 | 内容 |
|---|---|
| パストラバーサル防止 | `..` を含む slug を拒否 |
| 原子的書き込み | 一時ファイル作成 → `fsync` → `rename` (POSIX atomic)。既存 JSON は `.bak` 退避 |
| RAW ログ | 全 LLM リクエスト/レスポンスを `raw_logs/` に保存 |
| 排他制御 | `series_dir/.lock` ファイルで同一シリーズの同時実行防止 |

---

## 9. 長文対応

1. **分割処理**: 各工程は scene または chapter 単位で LLM に投入
2. **集約の階層化**: scene → chapter → volume の順に段階的に集約
3. **Blackboard の巻ごとの要約**: 前巻の全データではなく、要約のみを次巻に引き継ぐ

---

## 10. ファイル構成

```text
<series_dir>/
├── .lock                          # 排他ロックファイル
├── state.json                     # プロジェクト状態
├── series_plan.json               # シリーズ企画
├── series_plan_review.json        # シリーズ企画レビュー
├── blackboard.json                # 事実記録
├── bible.json                     # 設定資料集
├── raw_logs/                      # LLM リクエスト/レスポンスログ
│   ├── 20260619_161231_series_plan.json
│   └── ...
├── vol01/
│   ├── outline.json               # 巻アウトライン
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

## 11. 品質ゲート

### 11.1 合格基準

- `score >= 70`（0-100スケール）かつ `critical` / `blocker` issue が0件
- 不合格時は自動改稿 → 再評価（最大2回）。2回不合格 → `強制出力済`

### 11.2 レビュー指摘修正回数

| 工程 | デフォルト | 最大 | 設定方法 |
|---|---|---|---|
| シーン | 2回 | 設定可能 | `quality.max_review_retries` / `--max-retries` |
| アウトライン | 3回 | - | ハードコード |
| シリーズ企画 | 3回 | - | ハードコード |

### 11.3 言語純度チェック

- ツールによる検出は行わない（JIS 漢字セットベースの検出は誤検出が多いため）
- プロンプトでの防止が主
- LLM が簡体字を出力した場合、レビューで `language_purity` カテゴリとして指摘する

---

*Last updated: 2026-06-19*
