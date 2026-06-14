# NovelForge Implementation Specification

## 1. プロジェクト構造

```
novel-forge/
├── pyproject.toml
├── README.md
├── docs/
│   ├── ARCHITECTURE.md       # アーキテクチャ設計書
│   ├── SPECIFICATION.md      # このファイル
│   └── SETUP_GUIDE.md         # セットアップガイド
├── prompts/
│   ├── system.md             # LLM システムプロンプト共通部
│   ├── series_plan.md        # シリーズ企画
│   ├── volume_outline.md     # 巻アウトライン
│   ├── scene_draft.md        # シーン初稿 (MVME goal 使用)
│   ├── scene_review.md       # シーンレビュー
│   ├── scene_revision.md     # シーン改稿
│   ├── scene_summary.md      # シーン要約
│   ├── scene_quality_gate.md # シーン品質ゲート
│   ├── chapter_review.md     # 章レビュー
│   ├── chapter_revision.md   # 章改稿
│   ├── volume_review.md      # 巻レビュー
│   ├── volume_revision.md    # 巻改稿
│   ├── series_review.md      # シリーズレビュー
│   ├── bible_update.md       # メタデータ台帳更新
│   └── kdp_metadata.md       # KDP メタデータ
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
│       ├── cli.py               # typer CLI
│       ├── models.py             # Pydantic state/eventモデル (episode対応)
│       ├── schemas.py           # SCHEMA_BY_NAME レジストリ
│       ├── storage.py            # StateStorage 実装 (episode永続化、Markdown/JSON)
│       ├── ollama_client.py      # LLMクライアント
│       ├── engine.py            # NovelEngine (状態機械)
│       ├── agents.py            # PlannerAgent, WriterAgent, CriticAgent
│       ├── orchestrator.py      # NovelOrchestrator (Engine + Agents 統合)
│       ├── scene_pipeline.py    # SceneWritingPipeline 実装
│       ├── scene_workflow.py    # シーン単体 (> novel_forge の scene_workflow)
│       ├── volume_workflow.py   # 巻単位ワークフロー
│       ├── blackboard.py        # Blackboard 実装
│       ├── bible.py            # Bible 実装
│       ├── quality.py            # QualityGate 実装
│       ├── manuscript.py        # 原稿アセンブリ
│       ├── publisher.py         # KDP メタデータ + 出版前チェック
│       ├── prompts.py           # プロンプトテンプレート管理
│       ├── context_injection.py # コンテキスト注入 (Blackboard, Bible, RevisionHistory)
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

## 2. CLI コマンド

```bash
# セットアップ
uv run novel-forge --help

# モデル接続確認
uv run novel-forge probe-model \
  --ollama-url http://ws1.local:11434 \
  --model qwen3.6:35b-a3b-mtp-q4_K_M

# 一括実行 (v1 → 全工程)
uv run novel-forge complete "近未来東京 記憶探偵 親子の和解" \
  --workdir ./work/series1 --volume 1

# 段階実行
uv run novel-forge plan     --workdir ./work/series1 --keywords "..."
uv run novel-forge outline  --workdir ./work/series1 --volume 1
uv run novel-forge write    --workdir ./work/series1 --volume 1
uv run novel-forge review   --workdir ./work/series1 --volume 1
uv run novel-forge revise   --workdir ./work/series1 --volume 1
uv run novel-forge quality  --workdir ./work/series1 --volume 1
uv run novel-forge export   --workdir ./work/series1 --volume 1
uv run novel-forge bible    --workdir ./work/series1 --action view
uv run novel-forge status   --workdir ./work/series1

# 次巻へ進む
uv run novel-forge next-volume --workdir ./work/series1

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
    draft_meta: dict | None = None      # LLM 出力メタ
    review: dict | None = None
    revision: dict | None = None
    quality_gate: dict | None = None
    summary: dict | None = None

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

```
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

中核となる状態機械。全コマンドはこのエンジンを通る。

```python
class NovelEngine:
    def __init__(self, workdir: Path, client: OllamaClient):
        self.storage = StateStorage(workdir)
        self.client = client

    def plan_series(keywords: str) -> Result
    def outline_volume(volume: int) -> Result
    def write_volume(volume: int, max_scenes: int | None = None) -> Result
    def review_volume(volume: int) -> Result
    def revise_volume(volume: int) -> Result
    def check_quality(volume: int) -> Result
    def export_volume(volume: int, force: bool = False) -> Result
    def update_bible(volume: int) -> Result
    def generate_kdp_metadata(volume: int) -> Result
    def status() -> ProjectState
    def complete(keywords: str, volume: int) -> Result
```

### 4.2 ScenePipeline (scene_pipeline.py)

シーン単位の処理パイプライン。

```python
class ScenePipeline:
    def __init__(self, client, blackboard, bible, prompts):

    async def process(
        self, scene_plan: ScenePlan, context: SceneContext
    ) -> SceneRecord:
        # 1. Draft → draft.json
        draft = await self.write_draft(scene_plan, context)

        # 2. Review → review.json
        review = await self.review_draft(draft, context)

        # 3. Quality Gate check
        gate = await self.check_quality(draft, review, context)
        if not gate["passed"]:
            # auto-revise
            revision = await self.revise(draft, review, context)
            gate = await self.check_quality(revision, review, context)
        else:
            revision = draft

        # 4. Summarize → update Blackboard
        summary = await self.summarize(revision, context)
        self.blackboard.add_facts(summary.extract_facts())

        return SceneRecord(
            draft=draft, review=review,
            revision=revision, quality_gate=gate
        )
```

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

## 5. プロンプトバージョン管理

プロンプトは `prompts/` の Markdown ファイルで管理:

```
prompts/
├── system.md              # 共通システムプロンプト (JSON 出力 + ジャンル/ペルソナ)
├── series_plan.md         # シリーズ企画プロンプト
├── volume_outline.md      # 巻アウトライン
├── scene_draft.md         # シーン初稿 (MVME goal 使用)
├── scene_review.md        # シーンレビュー
├── scene_revision.md      # シーン改稿
├── scene_summary.md       # シーン要約 (Blackboard facts 抽出)
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
# 全テスト実行
uv run pytest -q

# カバレッジ
uv run pytest --cov=novel_forge --cov-report=term-missing

# Lint
uv run ruff check .

# 型チェック
uv run mypy src/

# スモーク検証 (LLMなし)
uv run python scripts/make_smoke_workspace.py --root /tmp/novel-forge-smoke
uv run novel-forge export --workdir /tmp/novel-forge-smoke --slug smoke-test
```

## 8. 依存関係 (pyproject.toml)

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
