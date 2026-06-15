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
│   ├── revision_priority.json
│   └── cover_prompt.json
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

### 2.1 設定ファイル

作業ディレクトリの直下に `.novel-forge.yaml` を置くことで、CLI オプションを省略できる。

```yaml
# .novel-forge.yaml
workdir: ./work/series1      # 作業ディレクトリ
model: qwen3.6:35b-a3b-mtp-q4_K_M  # LLM モデル
lang: ja                      # 出力言語
volume: 1                     # 現在処理中の巻番号
```

設定ファイルがある場合、`--workdir` と `--volume` を省略可能。コマンドライン指定が優先。

### 2.2 CLI コマンド

```bash
# セットアップ
uv run novel-forge --help

# モデル接続確認
uv run novel-forge probe-model

# 一括実行 (v1 → 全工程)
uv run novel-forge complete "近未来東京 記憶探偵 亲子の和解"

# 段階実行
uv run novel-forge plan          --keywords "..."
uv run novel-forge outline       # --volume 1 はデフォルト
uv run novel-forge write
**グローバルオプション**:

| オプション | 短縮 | デフォルト | 説明 |
|---|---|---|---|
| `--config` | `-c` | `./.novel-forge.yaml` | 設定ファイルパス |
| `--workdir` | `-w` | 設定ファイル or カレント | 作業ディレクトリ |
| `--volume` | `-V` | 設定ファイル or `1` | 処理対象の巻番号 |
| `--model` | `-m` | 設定ファイル or デフォルト | LLM モデル名 |
| `--timeout` | `-t` | 工程別デフォルト | LLM タイムアウト (秒) |

```bash
# 初回: plan で作業フォルダ自動作成
uv run novel-forge plan "近未来東京 記憶探偵"
# → ./20260615_近未来東京記憶探偵/ に作業フォルダ作成
# → series_plan.json 生成（LLM自己レビュー結果含む）
# → .novel-forge.yaml 作成（workdir 自動設定）
# → 人間が内容を確認。問題なければ自動的に次工程へ

# 一括実行
uv run novel-forge complete "..."   # plan → outline → write → export

# カスタム作業ディレクトリ
uv run novel-forge plan "..." --workdir ./my-custom-dir
# → ./my-custom-dir/ に作業フォルダ作成

# 既存シリーズで再開
uv run novel-forge complete --workdir ./20260615_近未来東京記憶探偵
# → plan をスキップして既存データで一括実行

# 巻2に切り替え
uv run novel-forge next-volume
uv run novel-forge outline -V 2
```

**段階実行コマンド**:

```bash
uv run novel-forge plan          --keywords "..."   # シリーズ企画（LLM自己レビュー→人間確認）
uv run novel-forge outline                        # 巻アウトライン（LLM自律）
uv run novel-forge write                          # シーン執筆（LLM自律）
uv run novel-forge export                         # KDP 向け出力（LLM自律）
uv run novel-forge bible         --action view    # メタデータ台帳
uv run novel-forge status                         # 進捗確認
uv run novel-forge resume                         # 中断した工程から再開
uv run novel-forge next-volume                    # 次巻へ
uv run novel-forge recover                        # 破損復旧
uv run novel-forge illustrate                     # 表紙画像プロンプト
uv run novel-forge complete                      # plan から一括実行
```

**削除されたコマンド**: `review`, `revise`, `quality` — これらは LLM 自律処理のため CLI コマンドとして不要。

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
    appearance: str | None = None

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
    quality_retries: int = 0          # 品質ゲート不合格からのリトライ回数 (最大3)
    draft_meta: dict | None = None      # LLM 出力メタ（scene.json スキーマ）
    review: dict | None = None           # scene_review.json スキーマ（人間には見せない）
    revision: dict | None = None         # scene_revision.json スキーマ（人間には見せない）
    quality_gate: dict | None = None     # scene_quality_gate.json スキーマ
    summary: dict | None = None          # scene_summary.json スキーマ

# ── 進捗 ──
class VolumeProgress(BaseModel):
    number: int; title: str
    status: Literal["planned","outlined","drafting","drafted",
                     "exported","finalized","force_exported"] = "planned"
    word_count: int = 0
    target_word_count: int = 80000

class ProjectState(BaseModel):
    series: SeriesPlan | None = None
    current_volume: int = 1
    volumes: list[VolumeProgress] = []
    scenes: dict[str, SceneRecord] = {}    # key "vol01_ch01_sc01"
    volume_outlines: dict[str, VolumeOutline] = {}  # key "vol01", "vol02", ...
    blackboard: BlackboardState | None = None
    bible: BibleState | None = None
    volume_reviews: dict[str, dict] = {}
    series_reviews: list[dict] = []
    schema_version: int = 1
```

### 3.2 作業フォルダ構造

**設計原則**:

1. **人間が目にするのは `exports/` のマークダウンだけ**: `manuscript.md` が完成原稿。`metadata.json` と `cover_prompt.json` は提出用手続き用
2. **原稿の実体は `volumes/` だが、マークダウンだけ**: `ch*.md`, `s*.md`。JSON は一切混在しない
3. **JSON はすべて `.novel-forge/` に隔離**: `.state.json`, `.series_plan.json`, `.blackboard.json`, `.bible.json` 等はすべて `.novel-forge/` 内。人間は見ないし触らない
4. **RAWログ、レビュー、品質レポートも `.novel-forge/` 内**: 完全に機械用のデータ
5. **`exports/` の原稿だけが Git 管理対象**: 作品のバージョン管理は `exports/manuscript.md` に対して行う

```text
workspace/<slug>/
├── .novel-forge.yaml                 # CLI 設定（触ってもよい）
├── exports/                          # ← 人間が目にする唯一の場所
│   ├── manuscript.md                   # 完成原稿（全巻束ねたもの）
│   ├── vol01.md                       # 巻1 原稿（個別提出用）
│   ├── metadata.json                 # KDP メタデータ
│   └── cover_prompt.json             # 表紙画像プロンプト
└── .novel-forge/                     # ← 人間は見ない（.gitignore 推奨）
    ├── state.json                    # メイン状態
    ├── state.json.bak                # 破損時退避
    ├── series_plan.json              # シリーズ企画
    ├── blackboard.json               # 物語の事実
    ├── bible.json                    # メタデータ台帳
    ├── raw_logs/                     # LLM 生ログ
    │   └── {timestamp}_{phase}.json
    └── volumes/                      # 中間生成データ
        └── vol01/
            ├── vol01_outline.json      # 巻アウトライン（vol01 プレフィックスでユニーク）
            ├── ch01/                  # 章1
            │   ├── vol01_ch01_sc01.md  # シーン1（シリーズ内ユニーク）
            │   └── vol01_ch01_sc02.md  # シーン2
            ├── ch02/                  # 章2
            │   └── vol01_ch02_sc01.md
            ├── vol01_review.json       # 巻レビュー（vol01 プレフィックスでユニーク）
            ├── vol01_revision.json     # 巻改稿中間データ
            └── quality_reports/
                └── vol01_ch01_sc01_quality.json  # vol01 プレフィックスでユニーク
```

**ファイル名ユニークルール**: 全ファイル名は `{vol}_{container}_{type}` の形式。`vol01` を必ず含めることで、シリーズディレクトリ内で一意を保証。

**ループ生成時の上書き戦略**:

| ファイル | 再実行時の挙動 | 根拠 |
|---|---|---|
| `vol01_outline.json` | 上書き | 再企画時に最新に更新 |
| `vol01_ch01_sc01.md` | 上書き | 再執筆時に最新に更新 |
| `vol01_review.json` | 上書き | 再レビュー時に最新に更新 |
| `vol01_revision.json` | 上書き | 再改稿時に最新に更新 |
| `vol01_ch01_sc01_quality.json` | 上書き | 再評価時に最新に更新 |
| `raw_logs/*.json` | **上書きしない**（タイムスタンプ付き） | 全 LLM やり取りの履歴を保持 |

**全履歴の保持**: `raw_logs/` にタイムスタンプ付きで保存されるため、再実行前の LLM レスポンスも失われない。作品ファイル（outline, scene, review 等）は上書きされるが、LLM の生ログは全履歴が残る。
```

**番号割り当て（統一フォーマット: プレフィックス2文字 + ゼロ埋め2桁）**:

| 要素 | フォーマット | 例 |
|---|---|---|
| 巻 | `vol{NN}` | `vol01`, `vol02` |
| 章 | `ch{NN}` | `ch01`, `ch02` |
| シーン | `sc{NN}` | `sc01`, `sc02` |

**設計原則**:

1. **人間が目にするのは `exports/` のマークダウンだけ**: `manuscript.md` が完成原稿
2. **原稿の実体は `.novel-forge/volumes/` だが、マークダウンだけ**: `ch{N}/vol{NN}_ch{NN}_sc{NN}.md`。JSON は一切混在しない
3. **JSON はすべて `.novel-forge/` に隔離**: `.state.json`, `.series_plan.json`, `vol{NN}_outline.json`, `vol{NN}_review.json` 等。人間は見ないし触らない
4. **RAWログ、レビュー、品質レポートも `.novel-forge/` 内**: 完全に機械用のデータ
5. **階層は2層まで**: `vol{N}/ch{N}/vol{NN}_ch{NN}_sc{NN}.md`。`chapters/`, `scenes/` は廃止
6. **プレフィックス2文字 + ゼロ埋め2桁で統一**: `vol01`, `ch01`, `sc01`

```
workspace/
├── mystery-series/          # シリーズ1
│   ├── .novel-forge.yaml    # workdir: ./, lang: ja, model: qwen3.6:35b
│   ├── exports/
│   └── .novel-forge/
│       ├── state.json       # シリーズ1 の状態
│       └── volumes/vol01/...
└── fantasy-series/          # シリーズ2（並行処理可）
    ├── .novel-forge.yaml
    ├── exports/
    └── .novel-forge/
        ├── state.json       # シリーズ2 の状態
        └── volumes/vol01/...
```

**並行処理の仕組み**:

1. **作業ディレクトリが異なる**: 各シリーズは独立した `workdir` を持つ
2. **`.novel-forge/` も分離**: シリーズごとに独立した状態管理
3. **Ollama は共用**: LLM リクエストは Ollama 側で直列化されるため、シリーズ間で待ち時間が発生
4. **モデルは1つ**: `keep_alive:-1` で最初の起動時に1回ロードすれば、両シリーズで使い回せる

**Ollama 共用時の注意**: Ollama はリクエストを直列処理（memory で確認済み）。複数シリーズを同時に `complete` した場合、一方のリクエストが他方のレスポン待ちになる。これは許容範囲（ユーザーが待つだけ）であり、エラーにはならない。

**state.json は `.` プレフィックス付き**: `.novel-forge/state.json`。ユーザーファイルと区別し、管理ファイルであることを明示。

**state キーの衝突防止**: `.novel-forge/` はシリーズごとに完全分離されるため、`vol01_ch01_sc01` のような key でもシリーズ間で衝突しない。

## 4. 主要コンポーネント

### 4.1 NovelEngine (engine.py)

中核となる状態機械。全コマンドはこのエンジンを通ります。

| コマンド | 役割 |
|---|---|
| `plan` | キーワードからシリーズ企画を生成。**LLM自己レビュー後、人間が内容を確認して次工程へ** |
| `outline` | 巻アウトライン（章・シーン構成）を生成。**LLM自律レビュー（構造的妥当性・シーン間の一貫性）を含む** |
| `write` | シーン本文を生成し、レビュー・改稿・品質ゲートを実行（**全工程LLM自律**） |
| `export` | KDP 向け出力を生成。最終レビュー（LLM自律）結果を `kdp_readiness_report.md` に記録 |
| `bible` | メタデータ台帳を更新・参照 |
| `status` | 現在の進捗と文字数を表示 |
| `complete` | plan(承認含む) → outline → write → export を一括実行 |
| `next-volume` | 次巻のアウトラインを生成 |
| `recover` | 破損した状態ファイルを復旧 |
| `resume` | 中断した工程から再開 |
| `illustrate` | 表紙画像プロンプト |

### 4.2 ScenePipeline (scene_pipeline.py)

シーン単位の処理パイプライン。**全工程が LLM 自律。人間は介入しない。**

**基本原則: LLMが生成したものはすべてLLMがレビューする。**

この原則は全階層に適用される：

| 階層 | 設計 | レビュー | 無限ループ防止 |
|---|---|---|---|
| シリーズ企画 | LLM | LLM（自己レビュー） | 最大3回。人間が内容を確認（暗黙承認） |
| 巻アウトライン | LLM | LLM（構造的妥当性・シーン間の一貫性） | 最大3回 |
| シーン本文 | LLM | LLM（文章品質・物語の論理） | 最大3回。3回不合格→`force_exported` |

各シーンを以下の順序で処理します。

1. **Draft** — アウトラインとコンテキストから初稿を生成
2. **Review** — 初稿を評価し、改善点を抽出（人間には見せない）
3. **Quality Gate** — レビュー結果に基づき合格/不合格を判定
4. **改稿** — 不合格の場合、レビュー結果に基づき自動改稿
5. **再評価** — 改稿後に再度 Quality Gate 判定
6. **Summarize** — 合格した本文から要約を生成し、Blackboard に事実を記録

**無限ループ防止（最大試行回数）**:

```
Quality Gate 不合格 → 改稿 → 再評価 → 不合格 → 改稿 → 再評価 → ...
```

このループは **最大3回** まで。3回不合格でも `force_exported` フラグを立てて続行する。

| 試行 | 動作 |
|---|---|
| 1回目 | Draft → Review → Quality Gate |
| 2回目 | 不合格 → 改稿 → Quality Gate |
| 3回目 | 不合格 → 改稿 → Quality Gate |
| 3回不合格 | `force_exported` フラグを立てて続行 |

**レビューと改稿は別プロンプトを使用**: 執筆用プロンプトとレビュー用プロンプトは明確に分ける。同じプロンプトで書いて評価すると自己評価バイアスが増幅するため。

- **scene_draft.md**: シーン執筆用（MVME goal 使用）
- **scene_review.md**: レビュー用（評価基準に特化。本文生成指示は含めない）
- **scene_revision.md**: 改稿用（レビュー結果を受けて改善。新規生成ではない）

### 4.3 Resume (resume.py)

中断した制作を再開する。

```python
class Resume:
    """現在の状態を読み込み、未完了のタスクから再開する"""

    def detect_state(self) -> dict:
        """state.json から現在状態を読み込む"""

    def next_tasks(self) -> list[str]:
        """未完了のタスク一覧を返す"""

    def run(self, phase: str | None = None):
        """指定 phase から再開。None は最初の未完了から"""

### 4.7 Whiteboard (blackboard.py)

```python
class Blackboard:
    facts: list[Fact]              # (subject, predicate, object, confidence)

    def add_fact(summary, details, characters)
    def query_recent(limit) -> str   # プロンプト注入用
    def check_consistency(new_fact) -> list[str] # 矛盾検出
    def scene_summary(key) -> str
    def to_prompt_context() -> str    # LLM 注入用フォーマット
```

### 4.5 CoverPromptGenerator (cover_prompt.py)

表紙画像を生成するためのプロンプトとメタデータを出力します。画像自体は生成しません（外部の画像生成ツールを使用します）。

```python
class CoverPromptGenerator:
    def __init__(self, prompts, bible, series_plan):

    def generate(self, volume_number: int) -> dict
        # cover_prompt.json スキーマに適合する dict を返す
```

入力: シリーズ企画、Bible、黒板
出力: `exports/cover_prompt.json`

### 4.3 QualityGate (quality.py)

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
├── kdp_metadata.md        # KDP メタデータ
└── cover_prompt.md        # 表紙画像生成プロンプト
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

- キーワードから `.series_plan.json` が生成されること
- `.series_plan.json` が `series_plan.json` スキーマに適合すること
- `.state.json` が作成され、`series_plan` フィールドが設定されていること
- `--workdir` 省略時、`yyyymmdd_{slugified_keywords}` のフォルダが自動生成されること
- `--workdir` 指定時、指定されたフォルダを使用すること
- `.novel-forge.yaml` が自動作成され、`workdir` が設定されていること
- LLM自己レビュー結果が `.novel-forge/` に記録されること
- 人間が内容を確認後、問題なければ自動的に次工程（outline）へ進むこと

### 8.2 outline

- `.novel-forge/volumes/vol01/vol01_outline.json` が生成されること
- 上記が `volume_outline.json` スキーマに適合すること
- 章が 1 件以上、各章にシーンが 1 件以上含まれること

### 8.3 write

- アウトラインに記載された全シーンについて、`.novel-forge/volumes/vol01/ch01/vol01_ch01_sc01.md` のような形式で生成されること
- 各シーンのレビュー結果が `.novel-forge/` 内に保存されていること（人間には見せない）
- LLM が生成した全階層（シリーズ企画・巻アウトライン・シーン本文）のレビュー結果がそれぞれ `.novel-forge/` に記録されていること
- 各シーンの品質ゲート結果（`.novel-forge/volumes/vol01/quality_reports/`）が保存されていること
- 品質ゲート不合格のシーンは最大3回まで自動改稿→再評価されること
- 3回不合格のシーンは `force_exported` フラグが立つこと
- `SceneRecord.quality_retries` が実際のリトライ回数を記録すること
- 章単位の Markdown は各章ディレクトリ直下に生成されること

### 8.4 export

- `exports/manuscript.md` が生成されること
- `exports/metadata.json` が生成されること
- `exports/kdp_readiness_report.md` が生成されること（最終レビュー結果を含む）
- 最終レビューは LLM 自律で実行されること

### 8.5 complete

- plan(承認含む) → outline → write → export の全工程がエラーなく完了すること
- `.state.json` のステータスが `finalized` または `exported` に更新されていること

### 8.6 next-volume

- 現在巻が完了状態の場合のみ、次巻のアウトラインが生成されること
- 計画巻数を超える場合、エラーで停止すること

### 8.10 recover

- 破損した `.state.json` を検出できること
- 有効なバックアップ（`.bak`）から復元できること
- 復元後の `.state.json` がパース可能なこと

### 8.11 bible

- `.bible.json` が生成・更新されること
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
|| 1 巻あたりの文字数 | 50,000〜120,000 字 | KDP ライトノベルの一般的な文字数 |

### 9.3 全体文字数・目標管理

KDP では 1 巻あたり 50,000〜120,000 文字が標準的なライトノベルの文字数。ツールは全体の文字数を追跡し、目標との乖離をフィードバックする。

**文字数カウント**:

```python
def count_words(text: str) -> int:
    """KDP向けの語数カウント"""
    # 日本語: 文字数 × 0.4 で近似
    # 英語: スペース区切り
    # コードブロック・JSONスキーマ部分は除外
```

* 日本語: 文字数 × 0.4 で近似（例: 10,000文字 → 4,000語）
* 英語: スペース区切り

**目標管理**:
* `series_plan.json` に `target_word_count` を設定可能（デフォルト: 80,000文字）
* `state.json` に `current_word_count` を更新
* `status` 時に目標対比を表示: 「vol01: 52,000文字 / 目標80,000文字 (65%)]」

### 9.4 長文への対応

作品が大きくなる場合、LLM の context 長と出力トークンの壁に対処するために以下の設計を採用します。

1. **分割処理**: 各工程は scene または chapter 単位で LLM に投入し、全体を一度に送らない
2. **集約の階層化**: scene → chapter → volume の順に段階的に集約し、上位工程には要約を渡す
3. **Blackboard の巻ごとの要約**: 前巻の全データではなく、要約のみを次の巻に引き継ぐ

## 11. 依存関係 (pyproject.toml)

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

*Last updated: 2026-06-16*
