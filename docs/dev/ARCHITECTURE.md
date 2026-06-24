# NovelForge Architecture Design

## 1. 設計背景

NovelForge は、ローカルLLMを使って小説シリーズを企画・構成・執筆・出力する Python CLI ツールです。

### 採用アーキテクチャ

4層アーキテクチャを採用します。

| Layer | 役割 | 主要コンポーネント |
|---|---|---|
| CLI Interface | ユーザーとの対話 | `cli.py` (Typer) |
| Orchestration | 状態遷移、パイプライン制御 | `engine/` (NovelEngine + Mixins) |
| Domain Logic | シーン執筆、コンテキスト構築、Bible管理 | `scene_writer.py`, `context_builder.py`, `bible_manager.py` |
| Infrastructure | LLM通信、永続化、ログ、スキーマ検証 | `llm_client.py`, `json_parser.py`, `storage.py`, `schemas.py`, `quality_gate.py` |

---

## 2. モジュール構成

```text
src/novel_forge/
├── cli.py              # CLI エントリポイント (Typer)
├── engine/             # オーケストレーション層
│   ├── __init__.py     # NovelEngine クラス定義
│   ├── infra.py        # ロック、エンジン生成、フェーズ解決、status/doctor
│   ├── base.py         # NovelEngineBase (__init__, helpers, state, _review_and_revise)
│   ├── plan.py         # PlanMixin (plan, 3-phase: core → characters → volumes)
│   ├── design.py       # DesignMixin (design, 3-phase: volume → chapter → scene)
│   ├── write.py        # WriteMixin (write)
│   └── export.py       # ExportMixin (export)
├── scene_writer.py     # SceneWriter (シーン執筆パイプライン)
├── context_builder.py  # ContextBuilder (context/continuity 構築)
├── bible_manager.py    # BibleManager (Bible 管理)
├── models.py           # Pydantic データモデル
├── llm_client.py       # LLM クライアント (Ollama /api/chat)
├── json_parser.py      # JSON パース・型変換ユーティリティ
├── prompts.py          # プロンプト管理 (PromptManager)
├── quality_gate.py     # QualityGate (シーン品質評価)
├── schemas.py          # JSON Schema 検証
├── storage.py          # 永続化 (StateStorage, BlackboardStorage, BibleStorage)
└── kanji_data.py       # 常用漢字データ
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

```python
class NovelEngine(
    NovelEngineBase,    # __init__, helpers, state, _review_and_revise
    PlanMixin,          # plan() — 3-phase: core → characters → volumes
    DesignMixin,        # design() — 3-phase: volume → chapter → scene
    WriteMixin,         # write()
    ExportMixin,        # export()
):
    pass
```

MRO: `NovelEngineBase` → `PlanMixin` → `DesignMixin` → `WriteMixin` → `ExportMixin`

---

## 3. データフロー

### 3.1 制作パイプライン

```
キーワード → [plan] シリーズ企画 (core → characters → volumes) + 自己レビュー → 人間確認（暗黙承認）
           → [design] 巻デザイン (volume → chapter → scene)
           → [write] シーン執筆（sequential）→ レビュー → 改稿 → 品質ゲート → Blackboard更新
           → [export] 原稿組立 → 最終レビュー → kdp_readiness_report.md
```

- シーンは **sequential のみ**（前シーン全文を `{continuity}` として次シーンに注入）
- デザイン自己修正は **最大3回**（`_generate_and_review` ループ）
- シーン品質ゲート不合格 → 自動改稿 → 再評価（最大2回）。不合格 → `強制出力済`

### 3.2 状態遷移

```
Volume status:
  計画中 → デザイン済 → 執筆中 → 初稿済 → 出力済

Scene status:
  計画中 → 初稿済 → 修正済
                │
                └→ 強制出力済 (2回不合格時)
```

### 3.3 人間介入ポイント

| 介入ポイント | タイミング | 内容 |
|---|---|---|
| シリーズ企画の確認 | plan 直後 | LLM自己レビュー結果を人間が確認（暗黙承認） |
| 最終レビュー | export 直後 | kdp_readiness_report.md の確認（任意） |

**それ以外の工程はすべて LLM 自律。**

---

## 4. レビュー・修正ループ

### 4.1 Plan フェーズ: `_generate_and_review()`

`PlanMixin._generate_and_review()` で統一。バリデーション + レビュー + リビジョンを1つのループに統合。

```python
while seed_offset < max_retries:
    result = generate(prompt, seed_offset)
    seed_offset += 1
    if validate(result) has errors: continue
    review = review(result, system)
    if no revision needed: return result
    if seed_offset >= max_retries: return result  # best effort
    result = revise(result, review, system, seed_offset)
    seed_offset += 1
    if validate(result) has errors: continue
    review = review(result, system)
    if no revision needed: return result
return result
```

- バリデーションエラー → seed を変えて再生成（プロンプトは変更しない）
- レビュー修正 → 修正後もバリデーション再チェック
- 合計 max_retries 回まで（デフォルト3回）

### 4.2 Design フェーズ: 各フェーズ独立

`DesignMixin` は3つの生成メソッドを順次実行:
1. `_generate_volume_design()` → 章構成
2. `_generate_chapter_designs()` → 章設計
3. `_generate_scene_designs()` → シーンデザイン

### 4.3 Write フェーズ: `SceneWriter._run_review_loop()`

品質ゲートと連動して自動改稿を実行。最大2回までリトライ。

---

## 5. プロンプト戦略

### 5.1 設計3フェーズ

1. **Phase 1 (巻構成)**: シリーズ企画から章のタイトルと役割を生成
2. **Phase 2 (章設計)**: 各章のテーマ、感情弧、伏線メモを生成
3. **Phase 3 (シーン設計)**: 各シーンの目標/結果/葛藤/視点を生成

### 5.2 各工程の役割定義

各プロンプトの先頭に `## 役割` セクションを記述し、LLMに期待する役割を明示する。

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

### 6.3 設定資料集（Bible）— メタデータ台帳

`bible.json` として独立ファイルで管理。

- **characters**: キャラクタープロファイル
- **glossary**: 用語と定義
- **foreshadowing**: 伏線と回収状況
- **world_rules**: 世界観ルール
- **relationships**: キャラクター関係性
- **subplots**: サブプロット

---

## 7. LLM モデルの選定

### 7.1 推奨モデル

**`qwen3.6:35b-a3b-mtp-q4_K_M`** を推奨モデルとします。

- **日本語能力**: 高い表現力と文法穩定性
- **JSON 出力**: `format: schema` + `think: true` で安定動作
- **長文処理**: 262,144 トークンの context 長
- **VRAM 効率**: Q4 量子化で 24GB VRAM GPU で動作可能

### 7.2 最適パラメータ

| パラメータ | 値 | 備考 |
|---|---|---|
| `think` | `true` | `false` は配列フィールドが空になる問題あり |
| `num_predict` | `-1` | 無制限 |
| `num_ctx` | `262144` | qwen3.6:35b の最大コンテキスト長 |
| `seed` | `42` | リトライ時にインクリメント |

---

## 8. セキュリティとデータ保全

| 項目 | 内容 |
|---|---|
| パストラバーサル防止 | `..` を含む slug を拒否 |
| 原子的書き込み | 一時ファイル作成 → `fsync` → `rename` (POSIX atomic) |
| RAW ログ | 全 LLM リクエスト/レスポンスを `raw_logs/` に保存 |
| 排他制御 | `series_dir/.lock` ファイルで同一シリーズの同時実行防止 |

---

## 9. ファイル構成

```text
<series_dir>/
├── .lock                          # 排他ロックファイル
├── state.json                     # プロジェクト状態
├── series_plan.json               # シリーズ企画
├── blackboard.json                # 事実記録
├── bible.json                     # 設定資料集
├── _raw_logs/                     # LLM リクエスト/レスポンスログ
├── vol01/
│   ├── vol01.json                 # 巻デザイン
│   ├── vol01_ch01/
│   │   ├── vol01_ch01.json        # 章設計
│   │   ├── vol01_ch01_sc01/
│   │   │   ├── vol01_ch01_sc01.json
│   │   │   └── vol01_ch01_sc01.md
│   │   └── ...
│   └── ...
└── exports/
    ├── vol01_manuscript.md
    ├── vol01_metadata.json
    └── vol01_kdp_readiness_report.md
```

---

*Last updated: 2026-06-25*
