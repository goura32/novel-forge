# NovelForge Implementation Specification

## 1. プロジェクト構造

```text
novel-forge/
├── pyproject.toml
├── README.md
├── config.yaml                   # 設定ファイル
├── docs/
│   ├── ARCHITECTURE.md
│   ├── SPECIFICATION.md
│   ├── PIPELINE.md
│   ├── PROMPTS.md
│   └── GLOSSARY.md
├── prompts/                      # プロンプトテンプレート
│   ├── system.md
│   ├── series_plan.md
│   ├── series_plan_review.md
│   ├── volume_outline.md
│   ├── scene_draft.md
│   ├── scene_review.md
│   ├── scene_revision.md
│   ├── scene_summary.md
│   ├── scene_summary_and_bible_update.md
│   ├── bible_update.md
│   └── cover_prompt.md
├── schemas/                      # JSON Schema 定義
│   ├── series_plan.json
│   ├── series_plan_review.json
│   ├── volume_outline.json
│   ├── scene.json
│   ├── scene_design.json
│   ├── chapter_design.json
│   ├── scene_review.json
│   ├── scene_revision.json
│   ├── scene_summary.json
│   ├── scene_summary_and_bible_update.json
│   ├── bible.json
│   ├── bible_update.json
│   ├── blackboard.json
│   └── cover_prompt.json
├── src/
│   └── novel_forge/
│       ├── __init__.py
│       ├── cli.py               # CLI エントリポイント
│       ├── models.py            # Pydantic データモデル
│       ├── schemas.py           # スキーマレジストリ
│       ├── storage.py           # 永続化
│       ├── ollama_client.py     # LLM クライアント
│       ├── engine.py            # NovelEngine (オーケストレーション)
│       ├── scene_writer.py      # SceneWriter (シーン執筆)
│       ├── context_builder.py   # ContextBuilder (コンテキスト構築)
│       ├── bible_manager.py     # BibleManager (Bible 管理)
│       ├── prompts.py           # プロンプト管理
│       └── quality.py           # QualityGate
└── tests/
    └── test_*.py
```

## 2. データモデル

### 2.1 主要モデル

| モデル | ファイル | 説明 |
|---|---|---|
| `ProjectState` | `models.py` | シリーズ全体の状態 |
| `VolumeProgress` | `models.py` | 巻ごとの進捗 |
| `SceneRecord` | `models.py` | シーンごとの生成状況 |
| `SceneWriteContext` | `models.py` | write_scene() のパラメータオブジェクト |
| `Blackboard` | `models.py` | 事実記録 |
| `Bible` | `models.py` | 設定資料集 |
| `CharacterProfile` | `models.py` | キャラクタープロファイル |
| `ForeshadowingItem` | `models.py` | 伏線 |
| `RelationshipItem` | `models.py` | キャラクター関係性 |
| `SubplotItem` | `models.py` | サブプロット |
| `GlossaryItem` | `models.py` | 用語 |
| `VolumeOutline` | `models.py` | 巻アウトライン |
| `SceneOutline` | `models.py` | シーンアウトライン |

### 2.2 ステータス値

**巻のステータス**: `planned` / `outlined` / `drafting` / `drafted` / `exported` / `finalized` / `force_exported`

**シーンのステータス**: `planned` / `drafted` / `reviewed` / `revised` / `force_exported` / `エラー`

## 3. 設定ファイル (config.yaml)

```yaml
llm:
  model: "qwen3.6:35b-a3b-mtp-q4_K_M"
  num_predict: 8192
  num_ctx: null
  timeout_seconds: 3600
  max_retries: 2
  ollama_host: null
  ollama_options:
    temperature: 1.0
    top_k: 20
    top_p: 0.95
    repeat_penalty: 1.0
    presence_penalty: 1.5
```

## 4. 永続化

### 4.1 ファイル配置

| ファイル | 内容 | 更新タイミング |
|---|---|---|
| `state.json` | プロジェクト状態 | 各工程完了時 |
| `blackboard.json` | 事実記録 | シーン完了時 |
| `bible.json` | 設定資料集 | シーン完了時 |
| `series_plan.json` | シリーズ企画 | plan 完了時 |
| `outline.json` | 巻アウトライン | outline 完了時 |

### 4.2 原子的書き込み

全 JSON ファイルは原子的書き込み（一時ファイル → fsync → rename）で保存。既存ファイルは `.bak` に退避。

## 5. LLM クライアント

### 5.1 エンドポイント

`/api/generate` を使用。`format: JSON Schema` + `think: false`。

### 5.2 リトライ

- 最大リトライ: 2回
- タイムアウト: 設定ファイルで指定（デフォルト 3600s）

### 5.3 JSON 抽出

1. 直接 parse
2. Markdown fence フォールバック
3. ラッパーオブジェクトフォールバック

## 6. 品質ゲート

### 6.1 評価カテゴリ（8次元）

| カテゴリ | 説明 |
|---|---|
| `opening_hook` | 冒頭のフック |
| `character_distinction` | キャラ立ち |
| `foreshadowing_consistency` | 伏線の整合性 |
| `sensory_coverage` | 五感の網羅 |
| `page_turner` | ページターナー |
| `tone_consistency` | 文体の一貫性 |
| `pov_consistency` | 視点の一貫性 |
| `structural_validity` | 構造的妥当性 |

### 6.2 合格基準

- `score >= 7.0` かつ `critical` issue が0件

### 6.3 簡体字チェック

JIS X 0208+0212+0213 セット（5976文字）で検出。

## 7. 言語制約

### 7.1 中国語禁止

簡体字の混入は「かなり重要」品質扱い。プロンプトで中国語禁止を明示。

### 7.2 検出方法

- プロンプトによる防止が主
- ツールによる検出は補助的（JIS 漢字セット外の漢字を検出）

## 8. テスト

### 8.1 テストファイル

| ファイル | 内容 |
|---|---|
| `test_models.py` | データモデルテスト |
| `test_storage.py` | 永続化テスト |
| `test_engine.py` | エンジンテスト |
| `test_quality.py` | 品質ゲートテスト |
| `test_schemas.py` | スキーマ検証テスト |

### 8.2 実行

```bash
uv run pytest tests/ -x -q
```

---

*Last updated: 2026-06-25*
