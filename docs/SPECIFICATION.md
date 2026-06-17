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
│   ├── series_plan_revision.md
│   ├── volume_outline.md
│   ├── volume_outline_review.md
│   ├── volume_outline_revision.md
│   ├── chapter_design.md
│   ├── scene_outline.md
│   ├── scene_draft.md
│   ├── scene_review.md
│   ├── scene_revision.md
│   ├── scene_summary.md
│   ├── scene_summary_and_bible_update.md
│   ├── bible_update.md
│   ├── kdp_metadata.md
│   ├── kdp_final_review.md
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

**シリーズのステータス**: `計画中` / `アウトライン済` / `執筆中` / `初稿済` / `強制出力済` / `出力済`

**巻のステータス**: `計画中` / `アウトライン済` / `執筆中` / `初稿済` / `強制出力済` / `出力済`

**シーンのステータス**: `計画中` / `初稿済` / `修正済` / `強制出力済`

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

### 6.1 評価カテゴリ（10次元）

| カテゴリ | 説明 |
|---|---|
| `opening_hook` | 冒頭のフック |
| `character_distinction` | キャラ立ち |
| `foreshadowing_consistency` | 伏線の整合性 |
| `sensory_coverage` | 五感の網羅 |
| `page_turner` | ページターナー |
| `dialogue_naturalness` | 台詞の自然さ |
| `tone_consistency` | 文体の一貫性 |
| `scene_completeness` | シーン完結 |
| `language_purity` | 言語純度 |
| `pov_consistency` | 視点の一貫性 |

### 6.2 合格基準

- **全レビュー共通**: `score >= 70`（0-100スケール）かつ `critical` / `blocker` issue が0件
- 不合格時は自動改稿 → 再評価（最大3回）。3回不合格 → `強制出力済`

### 6.3 スコアリングガイド

- **90-100**: 商業出版レベル。ほぼ問題なし
- **80-89**: 良好。軽微な改善点があるが、そのまま出版可能
- **70-79**: 合格ライン。いくつかの改善点があるが、全体的に読者を引き込む品質
- **60-69**: 改善が必要。複数の major issue がある
- **50-59**: 大幅な改善が必要
- **0-49**: 書き直しが必要

### 6.4 簡体字チェック

JIS X 0208+0212+0213 セット（5976文字）で検出。

## 7. 言語制約

### 7.1 禁止事項

1. **英語**: 日本語として定着した語以外は日本語に翻訳
2. **中国語**: 簡体字・繁体字の混入禁止
3. **韓国語**: ハングル禁止

### 7.2 例外

- `slug` フィールドのみローマ字許可
- 技術用語（CPU, GPU, SSD, USB, URL, 等）は英語のまま許可
- 医療・科学分野の英語略語（ICU, DNA, RNA 等）は許可

## 8. 依存要件

### 8.1 前巻必須

**次巻のアウトライン生成には、前巻の `outline.json` が必須。**

- `outline -V N`（N >= 2）実行時、`volumes/vol{N-1:02d}/outline.json` が存在しない場合は `RuntimeError`
- エラーメッセージに「先に前巻のアウトラインを生成してください」と表示

### 8.2 アウトライン再生成時の再執筆

**アウトライン再生成後、既に本文執筆済みの章・シーンは再執筆が必要。**

- `outline` 再実行時、既存の `chapters/` ディレクトリを削除
- `write` 実行時、`修正済` または `強制出力済` のシーンは既存の原稿を再利用
- アウトライン変更によりシーン構成が変わった場合、該当シーンは `計画中` にリセット

## 9. テスト

### 9.1 テストファイル

| ファイル | 内容 |
|---|---|
| `test_models.py` | データモデルテスト |
| `test_storage.py` | 永続化テスト |
| `test_engine.py` | エンジンテスト |
| `test_quality.py` | 品質ゲートテスト |
| `test_schemas.py` | スキーマ検証テスト |
| `test_engine_integration.py` | エンジン統合テスト（モックLLM） |

### 9.2 実行

```bash
uv run pytest tests/ -x -q
```

### 9.3 テスト数

| ファイル | テスト数 |
|---|---|
| `test_models.py` | 47 |
| `test_quality.py` | 9 |
| `test_engine_integration.py` | 70 |
| `test_engine.py` | 11 |

**合計: 137 テスト**

---

*Last updated: 2026-06-28*
