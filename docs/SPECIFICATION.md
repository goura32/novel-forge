# NovelForge Implementation Specification

## 1. プロジェクト構造

```text
novel-forge/
├── pyproject.toml
├── README.md
├── docs/
│   ├── ARCHITECTURE.md
│   ├── SPECIFICATION.md
│   └── SETUP_GUIDE.md
├── prompts/
│   ├── system.md              # LLM システムプロンプト共通部
│   ├── series_plan.md         # シリーズ企画
│   ├── volume_outline.md      # 巻アウトライン
│   ├── scene_draft.md         # シーン初稿 (MVME goal 使用)
│   ├── scene_review.md        # シーンレビュー
│   ├── scene_revision.md      # シーン改稿
│   ├── scene_summary.md       # シーン要約
│   ├── scene_quality_gate.md  # シーン品質ゲート
│   ├── chapter_review.md      # 章レビュー
│   ├── chapter_revision.md    # 章改稿
│   ├── volume_review.md       # 巻レビュー
│   ├── volume_revision.md     # 巻改稿
│   ├── series_review.md       # シリーズレビュー
│   ├── bible_update.md        # メタデータ台帳更新
│   └── kdp_metadata.md        # KDP メタデータ
├── schemas/
│   ├── series_plan.json
│   ├── volume_outline.json
│   ├── scene.json
│   ├── scene_review.json
│   ├── scene_revision.json
│   ├── scene_summary.json
│   ├── scene_quality_gate.json
│   ├── chapter_review.json
│   ├── chapter_revision.json
│   ├── volume_review.json
│   ├── volume_revision.json
│   ├── series_review.json
│   ├── blackboard.json
│   ├── bible.json
│   ├── kdp_metadata.json
│   └── revision_priority.json
├── src/
│   └── novel_forge/
│       ├── __init__.py
│       ├── cli.py              # typer CLI
│       ├── models.py            # Pydantic state/eventモデル
│       ├── schemas.py          # SCHEMA_BY_NAME レジストリ
│       ├── storage.py           # StateStorage 永続化
│       ├── ollama_client.py     # LLMクライアント
│       ├── engine.py           # NovelEngine (状態機械)
│       ├── agents.py           # PlannerAgent, WriterAgent, CriticAgent
│       ├── orchestrator.py     # NovelOrchestrator (Engine + Agents 統合)
│       ├── scene_pipeline.py   # シーン単位パイプライン
│       ├── scene_workflow.py   # シーン単体ワークフロー
│       ├── volume_workflow.py  # 巻単位ワークフロー
│       ├── blackboard.py       # Blackboard 実装
│       ├── bible.py           # Bible 実装
│       ├── quality.py           # QualityGate 実装
│       ├── manuscript.py       # 原稿アセンブリ
│       ├── publisher.py        # KDP メタデータ + 出版前チェック
│       ├── prompts.py          # プロンプトテンプレート管理
│       ├── context_injection.py# コンテキスト注入
│       ├── revision.py         # 改稿優先ロジック
│       └── markdown_export.py  # Markdown エクスポート
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

## 2. CLI コマンド

```bash
# セットアップ
uv run novel-forge --help

# モデル接続確認
uv run novel-forge probe-model

# 一括実行 (v1 → 全工程)
uv run novel-forge complete "近未来東京 記憶探偵 亲子の和解" --workdir ./work/series1 --volume 1

# 段階実行
uv run novel-forge plan          --workdir ./work/series1 --keywords "..."
uv run novel-forge outline       --workdir ./work/series1 --volume 1
uv run novel-forge write         --workdir ./work/series1 --volume 1
uv run novel-forge review        --workdir ./work/series1 --volume 1
uv run novel-forge revise        --workdir ./work/series1 --volume 1
uv run novel-forge quality       --workdir ./work/series1 --volume 1
uv run novel-forge export        --workdir ./work/series1 --volume 1
uv run novel-forge bible         --workdir ./work/series1 --action view
uv run novel-forge status        --workdir ./work/series1

# 次巻へ進む
uv run novel-forge next-volume   --workdir ./work/series1

# 破損状態からの復旧
uv run novel-forge recover-state --workdir ./work/series1
```

## 3. データモデル

### 3.1 主要モデル (models.py)

```python
# ── シリーズ ──
class World(BaseModel):
    summary: str
    rules: list[str]

class Character(BaseModel):
    name: str
    role: str
    arc: str

class PlannedVolume(BaseModel):
    number: int
    title: str
    premise: str

class SeriesPlan(BaseModel):
    title: str; slug: str; logline: str; genre: str
    target_audience: str; themes: list[str]; selling_points: list[str]
    world: World; main_characters: list[Character]
    planned_volumes: list[PlannedVolume]

# ── 巻 ──
class ScenePlan(BaseModel):
    number: int; title: str; pov: str
    goal: str       # MVME: "(State > Action | Result)"
    conflict: str; outcome: str
    characters: list[str]

class ChapterPlan(BaseModel):
    number: int; title: str; purpose: str
    scenes: list[ScenePlan]

class VolumeOutline(BaseModel):
    volume_number: int; title: str; premise: str
    chapters: list[ChapterPlan]

# ── シーン ──
class SceneRecord(BaseModel):
    volume: int; chapter: int; scene: int
    title: str | None = None
    status: Literal["planned","drafted","reviewed","revised"] = "planned"
    content: str | None = None
    draft_meta: dict | None = None      # LLM 出力メタ（scene.json スキーマ）
    review: dict | None = None           # scene_review.json スキーマ
    revision: dict | None = None         # scene_revision.json スキーマ
    quality_gate: dict | None = None     # scene_quality_gate.json スキーマ
    summary: dict | None = None          # scene_summary.json スキーマ

# ── 進捗 ──
class VolumeProgress(BaseModel):
    number: int; title: str
    status: Literal["planned","outlined","drafting","drafted","reviewed",
                     "revised","published","force_exported"] = "planned"

class ProjectState(BaseModel):
    series: SeriesPlan | None = None
    current_volume: int = 1
    volumes: list[VolumeProgress] = []
    scenes: dict[str, SceneRecord] = {}    # key "v01_c01_s01"
    volume_outlines: dict[str, VolumeOutline] = {}  # key "1", "2", ...
    blackboard: BlackboardState | None = None
    bible: BibleState | None = None
    volume_reviews: dict[str, dict] = {}
    series_reviews: list[dict] = []
    schema_version: int = 1
```

### 3.2 作業フォルダ構造

```text
workspace/<slug>/
├── state.json                    # メイン状態ファイル
├── state.json.bak                # 破損時退避
├── series_plan.json
├── blackboard.json
├── bible.json
├── raw_logs/                     # LLM リクエスト/レスポンス
│   └── 20260615T120000.000Z_series_plan.json
└── volume_001/
    ├── outline.json
    ├── volume_review.json
    ├── volume_revision.json
    ├── volume_revised.md
    └── chapters/
        ├── chapter_001/
        │   ├── scene_001.md
        │   ├── scene_001_draft.json
        │   ├── scene_001_review.json
        │   ├── scene_001_revision.json
        │   └── scene_001_quality.json
        ├── chapter_001.md
        └── ...
```

## 4. 主要コンポーネント

### 4.1 NovelEngine (engine.py)

中核となる状態機械。全コマンドはこのエンジンを通ります。

| コマンド | 役割 |
|---|---|
| `plan` | キーワードからシリーズ企画を生成 |
| `outline` | 巻アウトライン（章・シーン構成）を生成 |
| `write` | シーン本文を生成し、レビュー・改稿・品質ゲートを実行 |
| `review` | 巻全体をレビュー |
| `revise` | レビュー結果に基づき巻全体を改稿 |
| `quality` | シーン品質ゲートを再評価 |
| `export` | KDP 向け出力を生成 |
| `bible` | メタデータ台帳を更新・参照 |
| `status` | 現在の進捗を表示 |
| `complete` | 企画からレビューまでの全工程を一括実行 |
| `next-volume` | 次巻のアウトラインを生成 |
| `recover-state` | 破損した状態ファイルを復旧 |

### 4.2 ScenePipeline (scene_pipeline.py)

シーン単位の処理パイプライン。各シーンを以下の順序で処理します。

1. **Draft** — アウトラインとコンテキストから初稿を生成
2. **Review** — 初稿を評価し、改善点を抽出
3. **Quality Gate** — レビュー結果に基づき合格/不合格を判定。不合格の場合は自動改稿して再評価
4. **Summarize** — 改稿済み本文から要約を生成し、Blackboard に事実を記録

### 4.3 Blackboard (blackboard.py)

```python
class Blackboard:
    facts: list[Fact]              # (subject, predicate, object, confidence)

    def add_fact(summary, details, characters)
    def query_recent(limit) -> str   # プロンプト注入用
    def check_consistency(new_fact) -> list[str] # 矛盾検出
    def scene_summary(key) -> str
    def to_prompt_context() -> str    # LLM 注入用フォーマット
```

### 4.4 QualityGate (quality.py)

```python
class QualityGate:
    def check_scene(record: SceneRecord) -> dict
        # Returns: {"passed": bool, "score": float, "issues": [...]}

    def check_volume(records: list[SceneRecord], review: dict) -> dict
        # Returns: {"ready_for_publication": bool, "issues": [...]}

    def ensure_export_allowed(review: dict, force: bool) -> None
        # Raises QualityGateError if not ready
```

## 5. プロンプト管理

プロンプトは `prompts/` の Markdown ファイルで管理:

```text
prompts/
├── system.md              # 共通システムプロンプト
├── series_plan.md         # シリーズ企画
├── volume_outline.md      # 巻アウトライン
├── scene_draft.md         # シーン初稿
├── scene_review.md        # シーンレビュー
├── scene_revision.md      # シーン改稿
├── scene_summary.md       # シーン要約
├── scene_quality_gate.md  # シーン品質ゲート
├── chapter_review.md      # 章レビュー
├── chapter_revision.md    # 章改稿
├── volume_review.md       # 巻レビュー
├── volume_revision.md     # 巻改稿
├── series_review.md       # シリーズレビュー
├── bible_update.md        # メタデータ台帳更新
└── kdp_metadata.md        # KDP メタデータ
```

各プロンプトは `{variable}` プレースホルダーを使用。`prompts.py` の `render_prompt()` で置換。

## 6. エラーハンドリング

```python
class NovelForgeError(RuntimeError): pass
class LLMClientError(RuntimeError): pass
class QualityGateError(NovelForgeError): pass
class StateLoadError(NovelForgeError): pass
class PathSafetyError(NovelForgeError): pass
class SchemaValidationError(NovelForgeError): pass
```

### 6.1 破損状態復旧

```bash
uv run novel-forge recover-state --workdir ./work/series1
# state.json が破損 → .bak から復元
# 破損ファイルは .corrupt として保存
```

## 7. テスト要件

```bash
uv run pytest -q                              # 全テスト
uv run pytest --cov=novel_forge --cov-report=term-missing  # カバレッジ
uv run ruff check .                           # Lint
uv run mypy src/                              # 型チェック
uv run python scripts/make_smoke_workspace.py --root /tmp/novel-forge-smoke
uv run novel-forge export --workdir /tmp/novel-forge-smoke --slug smoke-test
```

## 8. 受け入れ基準

各コマンドが「完了」と見なすための基準です。

### 8.1 plan

- キーワードから `series_plan.json` が生成されること
- `series_plan.json` が `series_plan.json` スキーマに適合すること
- `state.json` が作成され、`series_plan` フィールドが設定されていること

### 8.2 outline

- `volume_N/outline.json` が生成されること
- `volume_N/outline.json` が `volume_outline.json` スキーマに適合すること
- 章が 1 件以上、各章にシーンが 1 件以上含まれること

### 8.3 write

- アウトラインに記載された全シーンについて、`scene_NNN.md` が生成されること
- 各シーンのレビュー結果（`scene_NNN_review.json`）が保存されていること
- 各シーンの品質ゲート結果（`scene_NNN_quality.json`）が保存されていること
- 章単位の Markdown（`chapter_NNN.md`）が全章分生成されていること

### 8.4 review

- `volume_N/volume_review.json` が生成されること
- 評価点、問題点、改善提案が構造化されていること

### 8.5 revise

- `volume_N/volume_revised.md` が生成されること
- 改稿後の章見出し数がアウトラインの章数と一致すること

### 8.6 quality

- 全シーンの品質ゲート結果が `state.json` に記録されていること
- 不合格シーンが存在する場合、その理由が `quality_gate.json` に記録されていること

### 8.7 export

- `exports/manuscript.md` が生成されること
- `exports/metadata.json` が生成されること
- 品質ゲート不合格が `--force` なしの場合、出力が停止すること

### 8.8 complete

- plan → outline → write → review の全工程がエラーなく完了すること
- `state.json` のステータスが `reviewed` 以降に更新されていること

### 8.9 next-volume

- 現在巻が完了状態の場合のみ、次巻のアウトラインが生成されること
- 計画巻数を超える場合、エラーで停止すること

### 8.10 recover-state

- 破損した `state.json` を検出できること
- 有効なバックアップ（`.bak`）から復元できること
- 復元後の `state.json` がパース可能なこと

### 8.11 bible

- `bible.json` が生成・更新されること
- キャラクター情報、用語、伏線が構造化されて保存されていること

### 8.12 status

- `state.json` の内容を人間が読める形式で表示すること
- 破損状態の場合はその旨と復旧手段を表示すること

## 9. 構造制約

### 9.1 技術的制約

以下の値は、ファイルシステムや LLM の技術的な上限に基づく必須の制約です。

| 項目 | 上限値 | 根拠 |
|---|---|---|
| slug の最大長 | 64 文字 | ファイルシステム制約 |
| 1 シーンの最大文字数 | 4,000 字 | LLM 1 回の出力トークン上限 |
| プロンプト最大トークン数 | 100,000 | LLM context 長の 80% を上限 |

### 9.2 作品の大きさ

**ツールは作品の大きさ（巻数、章数、シーン数、文字数）を制限しません。** これらは著者の判断と出版プラットフォームの仕様に委ねます。

実在するライトノベルシリーズには 15 巻を超える作品が多数あり、ツール側で巻数を制限するのは非現実的です。

ただし、参考値として以下を目安として記載します。

| 項目 | 参考値 | 目安 |
|---|---|---|
| 1 巻あたりの章数 | 10〜20 章 | ライトノベル 1 巻の一般的な章数 |
| 1 章あたりのシーン数 | 3〜8 シーン | 章内のまとまりと読みやすさ |
| 1 巻あたりの文字数 | 50,000〜120,000 字 | KDP ライトノベルの一般的な文字数 |

### 9.3 長文への対応

作品が大きくなる場合、LLM の context 長と出力トークンの壁に対処するために以下の設計を採用します。

1. **分割処理**: 各工程（特に write, review）は scene または chapter 単位で LLM に投入し、全体を一度に送らない
2. **集約の階層化**: scene → chapter → volume の順に段階的に集約し、上位工程には要約を渡す
3. **Blackboard の巻ごとの要約**: 前巻の全データではなく、要約のみを次の巻に引き継ぐ

番号の重複を避けるため、依存関係セクションの番号を 10 に変更します。

## 10. 依存関係 (pyproject.toml)

```toml
[project]
name = "novel-forge"
version = "0.1.0"
requires-python = ">=3.14"

dependencies = [
    "httpx>=0.28",
    "pydantic>=2.0",
    "typer>=0.12",
    "rich>=13.0",
    "jsonschema>=4.0",
]

[project.scripts]
novel-forge = "novel_forge.cli:app"
```

---

*Last updated: 2026-06-15*
