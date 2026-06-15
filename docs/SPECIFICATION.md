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
├── prompts/                    # プロンプトテンプレート（docs/PROMPTS.md を参照）
├── schemas/                    # JSON Schema 定義
│   ├── series_plan.json
│   ├── volume_outline.json
│   ├── volume_outline_review.json
│   ├── scene.json
│   ├── scene_design.json       # シーン設計（LLM設計出力）
│   ├── scene_review.json
│   ├── scene_revision.json
│   ├── scene_summary.json
│   ├── scene_quality_gate.json
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


**パイプラインとコンポーネントの詳細**: [docs/PIPELINE.md](PIPELINE.md)

**プロンプト管理の詳細**: [docs/PROMPTS.md](PROMPTS.md)

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
2. **原稿（Markdown）は `chapters/` + `scenes/` に保存**: 両ディレクトリともマークダウンだけ。JSON は一切混在しない
3. **LLM 設計出力（JSON）は `designs/` に保存**: シーン本文の元になった JSON 設計も保存し、後から設計意図を確認できる。`designs/` はマークダウン原稿の「設計」に対応する
4. **JSON（状態・メタデータ）はすべて `.novel-forge/` に隔離**: `.state.json`, `.series_plan.json`, `.blackboard.json`, `.bible.json` 等。人間は見ないし触らない
5. **RAWログ、レビュー、品質レポートも `.novel-forge/` 内**: 完全に機械用のデータ
6. **`exports/` の原稿だけが Git 管理対象**: 作品のバージョン管理は `exports/manuscript.md` に対して行う

```text
workspace/<slug>├── .novel-forge.yaml                 # CLI 設定（触ってもよい）
├── exports/                          # ← 人間が目にする唯一の場所
│   ├── manuscript.md                   # 完成原稿（全巻束ねたもの）
│   ├── vol01.md                       # 巻1 原稿（KDP 個別提出用）
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
    └── volumes/                      # 巻ごとの中間生成データ
        └── vol01/
            ├── vol01_outline.json      # 巻アウトライン
            ├── vol01_outline_review.json  # アウトライン自己レビュー
            ├── vol01_outline_revision_log.json  # アウトライン修正履歴
            ├── vol01_draft.md           # 巻1 ドラフト（全章束ねた作業用）
            ├── chapters/              # 章単位の Markdown（人間が読む用）
            │   ├── ch01.md             # 章1 原稿
            │   ├── ch02.md             # 章2 原稿
            │   └── ch03.md             # 章3 原稿
            ├── scenes/                # シーン単位の Markdown（人間が読む用）
            │   ├── ch01/
            │   │   ├── vol01_ch01_sc01.md
            │   │   └── vol01_ch01_sc02.md
            │   └── ch02/
            │       └── vol01_ch02_sc01.md
            ├── designs/              # LLM 設計出力（JSON、人間は見ない）
            │   ├── ch01_design.json           # 章1 設計（シーン構成・目的）
            │   ├── ch01/
            │   │   ├── vol01_ch01_sc01_design.json  # シーン1 設計（MVME goal等）
            │   │   └── vol01_ch01_sc02_design.json
            │   └── ch02/
            │       ├── vol01_ch02_design.json
            │       └── vol01_ch02_sc01_design.json
            └── quality_reports/       # シーン品質レポート
                └── vol01_ch01_sc01_quality.json
```

**階層構造の考え方**:

```
vol01/
├── vol01_outline.json       # 設計: 巻全体の章・シーン構成
├── vol01_draft.md          # 作業用: 全章束ねたドラフト
├── chapters/                # 出力: 章単位の Markdown（人間が確認・編集する単位）
│   ├── ch01.md
│   └── ch02.md
├── scenes/                  # 出力: シーン単位の Markdown（最小粒度）
│   ├── ch01/
│   │   ├── vol01_ch01_sc01.md
│   │   └── vol01_ch01_sc02.md
│   └── ch02/
│       └── vol01_ch02_sc01.md
├── designs/                # LLM 設計出力（JSON）
│   ├── ch01_design.json
│   ├── ch01/
│   │   ├── vol01_ch01_sc01_design.json
│   │   └── vol01_ch01_sc02_design.json
│   └── ch02/
│       ├── vol01_ch02_design.json
│       └── vol01_ch02_sc01_design.json
└── quality_reports/         # 管理: 品質ゲート結果
```

**4層構造の役割**:

| 層 | ファイル | 形式 | 役割 | 人間が触るか |
|---|---|---|---|---|
| 巻 | `vol01_draft.md` | Markdown | write 工程中の作業用まとめ | いいえ |
| 章 | `chapters/ch01.md` | Markdown | 人間が確認・編集できる最小のまとまり | はい（必要なら） |
| シーン | `scenes/ch01/vol01_ch01_sc01.md` | Markdown | LLM が生成した完成原稿 | いいえ |
| 設計 | `designs/ch01/vol01_ch01_sc01_design.json` | JSON | LLM の設計出力（プロンプトの構造化結果） | いいえ |

**設計出力（`designs/`）の内容**:
- **章設計** (`ch01_design.json`): 章の目的、含まれるシーン一覧、章のテーマ
- **シーン設計** (`vol01_ch01_sc01_design.json`): MVME goal、POV、conflict、outcome、キャラクター、感情アーク
- これらは LLM が JSON Schema で出力した結果をそのまま保存する
- 人間は見ない。後から設計意図を確認したい場合に参照する

**設計と原稿の関係**:
- LLM が `design/` に JSON で設計を出力
- その設計に基づいて LLM が `scenes/` に Markdown で本文を執筆
- 本文執筆時、JSON 設計の内容をプロンプトに注入する
- 原稿（Markdown）は設計（JSON）から生成された成果物

**ファイル名ユニークルール**: 全ファイル名は `{vol}_{container}_{type}` の形式。`vol01` を必ず含めることで、シリーズディレクトリ内で一意を保証。

**ループ生成時の上書き戦略**:

| ファイル | 再実行時の挙動 | 根拠 |
|---|---|---|
| `vol01_outline.json` | 上書き | 再企画時に最新に更新 |
| `vol01_outline_review.json` | 上書き | 再レビュー時に最新に更新 |
| `vol01_draft.md` | 上書き | 再執筆時に最新に更新 |
| `chapters/ch01.md` | 上書き | 再執筆時に最新に更新 |
| `scenes/ch01/vol01_ch01_sc01.md` | 上書き | 再執筆時に最新に更新 |
| `designs/ch01_design.json` | 上書き | 再設計時に最新に更新 |
| `designs/ch01/vol01_ch01_sc01_design.json` | 上書き | 再設計時に最新に更新 |
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
5. **階層は4層まで**: `exports/`（人間閲覧）、`chapters/` + `scenes/`（Markdown原稿）、`designs/`（LLM設計JSON）
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
uv run novel-forge recover --workdir ./work/series1
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
- 各章に `purpose`（章の役割）が設定されていること
- 各シーンに MVME goal（`(State > Action | Result)`）が設定されていること
- 物語の弧（introduction → rising_action → turning_point → climax → resolution）が明確であること
- シーン間の連続性（前シーンの `outcome` が次シーンの `goal` に繋がる）が確保されていること
- 自己レビュー結果（`vol01_outline_review.json`）が生成されていること
- `overall_score` が 7.0 以上、または3回の自己修正内で最高スコアのバージョンが採用されていること
- 修正履歴（`vol01_outline_revision_log.json`）が生成されていること（修正が行われた場合）
- `vol01_outline_revision_log.json` には修正箇所・修正理由・修正前後の差分要約が記録されていること

### 8.3 write

- アウトラインに記載された全シーンについて、各シーンの Markdown 原稿（`scenes/`）、章の Markdown 原稿（`chapters/`）、LLM 設計 JSON（`designs/`）が生成されること
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
    "opencc-purepy>=1.3"
    "rich>=13.0",
    "jsonschema>=4.0",
]

[project.scripts]
novel-forge = "novel_forge.cli:app"
```

---

*Last updated: 2026-06-16*
