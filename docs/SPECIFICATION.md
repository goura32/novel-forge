# NovelForge Implementation Specification

## 1. プロジェクト構造

```text
novel-forge/
├── pyproject.toml
├── README.md
├── docs/
│   ├── ARCHITECTURE.md
│   ├── SPECIFICATION.md
│   ├── PIPELINE.md
│   ├── PROMPTS.md
│   └── GLOSSARY.md
├── prompts/                    # プロンプトテンプレート（docs/PROMPTS.md を参照）
├── schemas/                    # JSON Schema 定義
│   ├── series_plan.json
│   ├── volume_outline.json
│   ├── volume_outline_review.json
│   ├── scene.json
│   ├── scene_design.json
│   ├── chapter_design.json
│   ├── volume_outline_revision_log.json
│   ├── scene_review.json
│   ├── scene_revision.json
│   ├── scene_summary.json
│   ├── scene_quality_gate.json
│   ├── blackboard.json
│   ├── bible.json
│   ├── kdp_metadata.json
│   └── cover_prompt.json
├── src/
│   └── novel_forge/
│       ├── __init__.py
│       ├── cli.py
│       ├── models.py            # Pydantic データモデル
│       ├── schemas.py           # SCHEMA_BY_NAME レジストリ
│       ├── storage.py           # StateStorage 永続化
│       ├── ollama_client.py     # LLMクライアント
│       ├── engine.py            # NovelEngine (状態機械)
│       ├── agents.py            # PlannerAgent, WriterAgent, CriticAgent
│       ├── orchestrator.py      # NovelOrchestrator
│       ├── scene_pipeline.py    # シーン単位パイプライン
│       ├── scene_workflow.py
│       ├── volume_workflow.py
│       ├── blackboard.py        # 事実記録
│       ├── bible.py             # 設定資料集
│       ├── quality.py           # QualityGate
│       ├── manuscript.py        # 原稿アセンブリ
│       ├── publisher.py         # KDP メタデータ
│       ├── prompts.py           # プロンプトテンプレート管理
│       ├── context_injection.py # コンテキスト注入
│       ├── revision.py          # 改稿優先ロジック
│       └── markdown_export.py   # Markdown エクスポート
├── tests/
│   ├── test_models.py
│   ├── test_ollama_client.py
│   ├── test_blackboard.py
│   ├── test_scene_workflow.py
│   ├── test_volume_workflow.py
│   └── test_end_to_end.py
└── scripts/
    └── make_smoke_workspace.py
```

### 1.1 設定ファイル

作業ディレクトリ直下に `.novel-forge.yaml` を置くことで CLI オプションを省略できる。

設定項目: `workdir`, `model`, `lang`, `volume`。コマンドライン指定が優先。

**パイプラインとコンポーネントの詳細**: [docs/PIPELINE.md](PIPELINE.md)

**プロンプト管理の詳細**: [docs/PROMPTS.md](PROMPTS.md)

**用語の定義**: [docs/GLOSSARY.md](GLOSSARY.md)

## 2. データモデル

すべてのデータモデルは `models.py` の Pydantic モデルとして定義し、対応する JSON Schema を `schemas/` に実装する。

### 2.1 主要モデル

| モデル | 用途 | 対応スキーマ |
|---|---|---|
| `SeriesPlan` | シリーズ企画 | `series_plan.json` |
| `VolumeOutline` | 巻アウトライン | `volume_outline.json` |
| `SceneRecord` | シーン生成状況 | `scene.json` (草稿) |
| `ProjectState` | シリーズ全体の状態 | — (state.json 直) |
| `SceneDesign` | シーン設計 | `scene_design.json` |
| `ChapterDesign` | 章設計 | `chapter_design.json` |
| `OutlineRevisionLog` | アウトライン修正履歴 | `volume_outline_revision_log.json` |

**事実記録（Blackboard）** と **設定資料集（Bible）** は `state.json` とは別ファイルとして永続化する。State Machine はメタデータ参照のみ保持し、物語の事実とメタデータは各ファイルの責務とする。

### 2.2 スキーマ定義

`schemas/` に JSON Schema (Draft 2020-12) として実装する。構造は §2.1 のデータモデル定義と PROMPTS.md のプレースホルダーに対応する。

実装するスキーマ: `scene_design.json`, `chapter_design.json`, `volume_outline_revision_log.json`

## 3. 作業フォルダ構造

**設計原則**:

1. **人間が目にするのは `exports/` のマークダウンだけ**: `manuscript.md` が完成原稿
2. **原稿（Markdown）は `chapters/` + `scenes/` に保存**: 両ディレクトリともマークダウンだけ。JSON は一切混在しない
3. **LLM 設計出力（JSON）は `designs/` に保存**: 後から設計意図を確認できる
4. **JSON（状態・メタデータ）はすべて `.novel-forge/` に隔離**: 人間は見ないし触らない
5. **RAWログ、レビュー、品質レポートも `.novel-forge/` 内**: 完全に機械用のデータ
6. **階層は4層まで**: `exports/`（人間閲覧）、`chapters/` + `scenes/`（Markdown原稿）、`designs/`（LLM設計JSON）
7. **プレフィックス2文字 + ゼロ埋め2桁で統一**: `vol01`, `ch01`, `sc01`

```text
workspace/<slug>/
├── .novel-forge.yaml                 # CLI 設定（触ってもよい）
├── exports/                          # ← 人間が目にする唯一の場所
│   ├── manuscript.md                   # 完成原稿（全巻束ねたもの）
│   ├── vol01.md                       # 巻1 原稿（KDP 個別提出用）
│   ├── metadata.json                 # KDP メタデータ
│   └── cover_prompt.json             # 表紙画像プロンプト
└── .novel-forge/                     # ← 人間は見ない（.gitignore 推奨）
    ├── state.json                    # メイン状態
    ├── state.json.bak                # 破損時退避
    ├── series_plan.json              # シリーズ企画
    ├── blackboard.json               # 物語の事実（事実記録）
    ├── bible.json                    # メタデータ台帳（設定資料集）
    ├── raw_logs/                     # LLM 生ログ
    │   └── {timestamp}_{phase}.json
    └── volumes/
        └── vol{NN}/
            ├── vol{NN}_outline.json
            ├── vol{NN}_outline_review.json
            ├── vol{NN}_outline_revision_log.json
            ├── vol{NN}_draft.md
            ├── chapters/
            │   └── ch{NN}.md
            ├── scenes/
            │   └── ch{NN}/
            │       └── vol{NN}_ch{NN}_sc{NN}.md
            ├── designs/
            │   ├── ch{NN}_design.json
            │   └── ch{NN}/
            │       └── vol{NN}_ch{NN}_sc{NN}_design.json
            └── quality_reports/
                └── vol{NN}_ch{NN}_sc{NN}_quality.json
```

**4層構造の役割**:

| 層 | 保存先 | 形式 | 人間が触るか |
|---|---|---|---|
| 巻 | `.novel-forge/volumes/vol{NN}/` | — | いいえ |
| 章 Markdown | `chapters/ch{NN}.md` | Markdown | はい（必要なら） |
| シーン Markdown | `scenes/ch{NN}/vol{NN}_ch{NN}_sc{NN}.md` | Markdown | いいえ |
| 設計 JSON | `designs/` | JSON | いいえ |

**設計と原稿の関係**:
- LLM が `designs/` に JSON で設計を出力
- その設計に基づいて LLM が `scenes/` に Markdown で本文を執筆
- 本文執筆時、JSON 設計の内容をプロンプトに注入する

**上書き戦略**: `raw_logs/` 以外は再実行時に上書き。`raw_logs/` はタイムスタンプ付きで全履歴保持。

### 3.1 並行処理

各シリーズは独立した `workdir` を持ち、`.novel-forge/` も分離される。Ollama は共用だが、リクエストは Ollama 側で直列化される。`keep_alive: -1` で最初の起動時に1回ロードすれば両シリーズで使い回せる。

## 4. エラーハンドリング

カスタム例外階層: `NovelForgeError` → `LLMClientError`, `QualityGateError`, `StateLoadError`, `PathSafetyError`, `SchemaValidationError`

### 4.1 破損状態復旧

`recover` コマンドで `state.json` が破損した場合、`.bak` から復元。破損ファイルは `.corrupt` として保存。

## 5. テスト要件

```bash
uv run pytest -q                              # 全テスト
uv run pytest --cov=novel_forge --cov-report=term-missing  # カバレッジ
uv run ruff check .                           # Lint
uv run mypy src/                              # 型チェック
uv run python scripts/make_smoke_workspace.py --root /tmp/novel-forge-smoke
uv run novel-forge export --workdir /tmp/novel-forge-smoke --slug smoke-test
```

## 6. 受け入れ基準

### 6.1 plan

- キーワードから `series_plan.json` が生成されること
- `series_plan.json` が `series_plan.json` スキーマに適合すること
- `state.json` が作成され、`series` フィールドが設定されていること
- `--workdir` 省略時、`yyyymmdd_{slugified_keywords}` のフォルダが自動生成されること
- `--workdir` 指定時、指定されたフォルダを使用すること
- `.novel-forge.yaml` が自動作成され、`workdir` が設定されていること
- LLM自己レビュー結果が `.novel-forge/` に記録されること
- 人間が内容を確認後、問題なければ自動的に次工程（outline）へ進むこと

### 6.2 outline

- `vol01_outline.json` が生成されること
- 上記が `volume_outline.json` スキーマに適合すること
- 章が 1 件以上、各章にシーンが 1 件以上含まれること
- 各章に `purpose` が設定されていること
- 各シーンに MVME goal（`(State > Action | Result)`）が設定されていること
- 物語の弧（introduction → rising_action → turning_point → climax → resolution）が明確であること
- シーン間の連続性が確保されていること
- 自己レビュー結果（`vol01_outline_review.json`）が生成されていること
- `overall_score` が 7.0 以上、または3回の自己修正内で最高スコアのバージョンが採用されていること
- 修正履歴（`vol01_outline_revision_log.json`）が生成されていること（修正が行われた場合）

### 6.3 write

- 全シーンについて、Markdown 原稿（`scenes/`）、章 Markdown（`chapters/`）、LLM 設計 JSON（`designs/`）が生成されること
- 各シーンのレビュー結果が `.novel-forge/` 内に保存されていること（人間には見せない）
- 各シーンの品質ゲート結果が保存されていること
- 品質ゲート不合格のシーンは最大3回まで自動改稿→再評価されること
- 3回不合格のシーンは `force_exported` フラグが立つこと
- `SceneRecord.quality_retries` が実際のリトライ回数を記録すること

### 6.4 export

- `exports/manuscript.md` が生成されること
- `exports/metadata.json` が生成されること
- `exports/kdp_readiness_report.md` が生成されること（最終レビュー結果を含む）
- 最終レビューは LLM 自律で実行されること

### 6.5 complete

- plan(承認含む) → outline → write → export の全工程がエラーなく完了すること
- `state.json` のステータスが `finalized` または `exported` に更新されていること

### 6.6 next-volume

- 現在巻が完了状態の場合のみ、次巻のアウトラインが生成されること
- 計画巻数を超える場合、エラーで停止すること

### 6.7 recover

- 破損した `state.json` を検出できること
- 有効なバックアップ（`.bak`）から復元できること
- 復元後の `state.json` がパース可能なこと

### 6.8 設定資料集（bible）

- `bible.json` が生成・更新されること
- キャラクター情報、用語、伏線が構造化されて保存されていること

### 6.9 status

- `state.json` の内容を人間が読める形式で表示すること
- 破損状態の場合はその旨と復旧手段を表示すること

## 7. 構造制約

### 7.1 技術的制約

| 項目 | 上限値 | 根拠 |
|---|---|---|
| slug の最大長 | 64 文字 | ファイルシステム制約 |
| 1 シーンの最大文字数 | 4,000 字 | LLM 1 回の出力トークン上限 |
| プロンプト最大トークン数 | 100,000 | LLM context 長の 80% を上限 |

### 7.2 作品の大きさ

ツールは作品の大きさ（巻数、章数、シーン数、文字数）を制限しない。参考値:

| 項目 | 参考値 |
|---|---|
| 1 巻あたりの章数 | 10〜20 章 |
| 1 章あたりのシーン数 | 3〜8 シーン |
| 1 巻あたりの文字数 | 50,000〜120,000 字 |

### 7.3 全体文字数・目標管理

KDP では 1 巻あたり 50,000〜120,000 文字が標準。ツールは全体の文字数を追跡し、目標との乖離をフィードバックする。

**文字数カウント**: 日本語は文字数 × 0.4 で近似。コードブロック・JSONスキーマ部分は除外。

**目標管理**: `target_word_count` を設定可能（デフォルト: 80,000文字）。`status` 時に目標対比を表示。

### 7.4 長文への対応

1. **分割処理**: 各工程は scene または chapter 単位で LLM に投入
2. **集約の階層化**: scene → chapter → volume の順に段階的に集約
3. **事実記録の巻ごとの要約**: 前巻の全データではなく、要約のみを次の巻に引き継ぐ

## 8. 依存関係 (pyproject.toml)

`httpx>=0.28`, `pydantic>=2.0`, `typer>=0.12`, `rich>=13.0`, `jsonschema>=4.0`

エントリポイント: `novel-forge = "novel_forge.cli:app"`

---

*Last updated: 2026-06-18*
