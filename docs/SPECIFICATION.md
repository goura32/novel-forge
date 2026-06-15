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
# → series_plan.json 生成
# → .novel-forge.yaml 作成（workdir 自動設定）

# 以後は workdir 省略可
uv run novel-forge complete "..."   # 一括実行
uv run novel-forge write
uv run novel-forge review

# カスタム作業ディレクトリ
uv run novel-forge plan "..." --workdir ./my-custom-dir
# → ./my-custom-dir/ に作業フォルダ作成

# 既存シリーズで再開
uv run novel-forge complete --workdir ./20260615_近未来東京記憶探偵
# → plan をスキスクして既存データで一括実行

# 巻2に切り替え
uv run novel-forge next-volume
uv run novel-forge outline -V 2
```

**段階実行コマンド**:

```bash
uv run novel-forge plan          --keywords "..."   # シリーズ企画
uv run novel-forge outline                        # 巻アウトライン
uv run novel-forge write                          # シーン執筆
uv run novel-forge review                         # 巻レビュー
uv run novel-forge revise                         # 巻改稿
uv run novel-forge quality                        # シーン品質ゲート再評価
uv run novel-forge export                         # KDP 向け出力
uv run novel-forge bible         --action view    # メタデータ台帳
uv run novel-forge status                         # 進捗確認
uv run novel-forge next-volume                    # 次巻へ
uv run novel-forge recover                        # 破損復旧
uv run novel-forge illustrate                     # 表紙画像プロンプト
uv run novel-forge complete                      # plan から一括実行
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
| `illustrate` | 表紙画像生成用のプロンプトとメタデータを出力 |

### 4.2 ScenePipeline (scene_pipeline.py)

シーン単位の処理パイプライン。各シーンを以下の順序で処理します。

1. **Draft** — アウトラインとコンテキストから初稿を生成
2. **Review** — 初稿を評価し、改善点を抽出
3. **Quality Gate** — レビュー結果に基づき合格/不合格を判定。不合格の場合は自動改稿して再評価
4. **Summarize** — 改稿済み本文から要約を生成し、Blackboard に事実を記録

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

### 8.2 outline

- `.novel-forge/volumes/vol01/vol01_outline.json` が生成されること
- 上記が `volume_outline.json` スキーマに適合すること
- 章が 1 件以上、各章にシーンが 1 件以上含まれること

### 8.3 write

- アウトラインに記載された全シーンについて、`.novel-forge/volumes/vol01/ch01/vol01_ch01_sc01.md` のような形式で生成されること
- 各シーンのレビュー結果（`.novel-forge/volumes/vol01/vol01_review.json`）が保存されていること
- 各シーンの品質ゲート結果（`.novel-forge/volumes/vol01/quality_reports/`）が保存されていること
- 章単位の Markdown は各章ディレクトリ直下に生成されること

### 8.4 review

- `.novel-forge/volumes/vol01/vol01_review.json` が生成されること
- 評価点、問題点、改善提案が構造化されていること

### 8.5 revise

- `.novel-forge/volumes/vol01/vol01_revision.json` が生成されること
- 改稿後の章見出し数がアウトラインの章数と一致すること

### 8.6 quality

- 全シーンの品質ゲート結果が `.state.json` に記録されていること
- 不合格シーンが存在する場合、その理由が quality_reports に記録されていること

### 8.7 export

- `exports/manuscript.md` が生成されること
- `exports/metadata.json` が生成されること
- 品質ゲート不合格が `--force` なしの場合、出力が停止すること

### 8.8 complete

- plan → outline → write → review の全工程がエラーなく完了すること
- `.state.json` のステータスが `reviewed` 以降に更新されていること

### 8.9 next-volume

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
