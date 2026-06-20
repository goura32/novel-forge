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
│   ├── chapter_outline.md
│   ├── chapter_design.md
│   ├── scene_outline.md
│   ├── scene_draft.md
│   ├── scene_review.md
│   ├── scene_revision.md
│   ├── scene_summary.md
│   ├── scene_summary_and_bible_update.md
│   ├── bible_update.md
│   ├── kdp_metadata.md
│   └── cover_prompt.md
├── schemas/                      # JSON Schema 定義
│   ├── series_plan.json
│   ├── series_plan_review.json
│   ├── series_plan_revision.json
│   ├── volume_outline.json
│   ├── volume_outline_review.json
│   ├── volume_outline_revision.json
│   ├── chapter_outline.json
│   ├── chapter_design.json
│   ├── scene_outline.json
│   ├── scene_draft.json
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
│       ├── cli.py               # CLI エントリポイント + 排他制御
│       ├── engine/              # NovelEngine (オーケストレーション)
│       │   ├── __init__.py
│       │   ├── base.py          # NovelEngineBase (初期化, state, lock)
│       │   ├── plan.py          # シリーズ企画
│       │   ├── outline.py       # 巻アウトライン
│       │   ├── write.py          # シーン執筆
│       │   └── export.py        # KDP出力
│       ├── scene_writer.py      # SceneWriter (シーン執筆パイプライン)
│       ├── context_builder.py   # ContextBuilder (コンテキスト構築)
│       ├── bible_manager.py     # BibleManager (Bible 管理)
│       ├── models.py            # Pydantic データモデル
│       ├── llm_client.py        # LLM クライアント
│       ├── prompts.py           # プロンプト管理
│       ├── quality_gate.py      # QualityGate
│       ├── schemas.py           # スキーマレジストリ
│       ├── storage.py           # 永続化
│       └── kanji_data.py        # 常用漢字データ
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
| `ChapterOutline` | `models.py` | 章アウトライン |

### 2.2 ステータス値

**シリーズのステータス**: `計画中` / `アウトライン済` / `執筆中` / `初稿済` / `強制出力済` / `出力済`

**巻のステータス**: `計画中` / `アウトライン済` / `執筆中` / `初稿済` / `強制出力済` / `出力済`

**シーンのステータス**: `計画中` / `初稿済` / `修正済` / `強制出力済`

## 3. 設定ファイル (config.yaml)

```yaml
llm:
  model: "qwen3.6:35b-a3b-mtp-q4_K_M"
  num_predict: -1
  num_ctx: 262144
  timeout_seconds: 3600
  max_retries: 2
  ollama_host: "ws1.local:11434"
  ollama_options:
    think: true
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
| `.lock` | 排他ロック | 全 engineering コマンド実行中 |

### 4.2 原子的書き込み

全 JSON ファイルは原子的書き込み（一時ファイル → fsync → rename）で保存。既存ファイルは `.bak` に退避。

## 5. LLM クライアント

### 5.1 エンドポイント

`/api/chat` を使用。`format: schema` + `think: true`。

### 5.2 リトライ

- 最大リトライ: 2回（合計3回試行）
- JSON パースエラーやスキーマ検証エラーはフィードバック付きでリトライ

### 5.3 JSON 抽出パイプライン

1. 直接 parse (`message.content` を JSON パース)
2. Markdown fence フォールバック (`` ```json ``` ``)
3. `{...}` 範囲抽出フォールバック

## 6. アウトライン生成（3フェーズパイプライン）

### 6.1 Phase 1: 章構成

`chapter_outline.md` + `chapter_outline.json` — 章のタイトルと役割（導入/展開/転換/クライマックス/収束）

### 6.2 Phase 2: 章設計

`chapter_design.md` + `chapter_design.json` — 各章のテーマ、感情弧、伏線メモ、サブプロットメモ

### 6.3 Phase 3: シーン設計

`scene_outline.md` + `scene_outline.json` — 各シーンの目標/結果/葛藤/視点/登場人物

## 7. 品質ゲート

### 7.1 評価カテゴリ（10次元）

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

### 7.2 合格基準

- `score >= 70`（0-100スケール）かつ `critical` / `blocker` issue が0件
- 不合格時は自動改稿 → 再評価（最大2回）。2回不合格 → `強制出力済`

## 8. 言語制約

### 8.1 禁止事項

1. **英語**: 日本語として定着した語以外は日本語に翻訳
2. **中国語**: 簡体字・繁体字の混入禁止
3. **韓国語**: ハングル禁止

### 8.2 例外

- `slug` フィールドのみローマ字許可
- 技術用語（CPU, GPU, SSD, USB, URL, 等22語）は英語のまま許可
- 医療・科学分野の英語略語（ICU, DNA, RNA 等）は許可

## 9. 依存要件

### 9.1 前巻必須

**次巻のアウトライン生成には、前巻の `outline.json` が必須。**

- `outline -V N`（N >= 2）実行時、`vol{N-1:02d}/outline.json` が存在しない場合は `RuntimeError`

### 9.2 前巻シーン参照（continuity）

各シーンの執筆時、`build_continuity()` が前シーンの全文を注入。これによりシーン間の連続性を維持。

- 巻内の連続性: 前シーン全文 + 直近3シーン要摘要 + 引き継ぎメモ
- 巻間の連続性: 前巻の `scene_summaries` が Blackboard に蓄積され、 continuity に含まれる

## 10. テスト

### 10.1 テストファイル

| ファイル | 内容 |
|---|---|
| `test_models.py` | データモデルテスト |
| `test_storage.py` | 永続化テスト |
| `test_prompts.py` | プロンプトテスト |
| `test_quality.py` | 品質ゲートテスト |
| `test_engine_integration.py` | エンジン統合テスト |

### 10.2 実行

```bash
uv run pytest tests/ -x -q
```

---

*Last updated: 2026-06-20*
