# NovelForge Master Improvement Plan

作成日: 2026-07-05
対象: `/mnt/hdd/projects/novel-forge`

## 0. 目的

NovelForge を「実モデルでたまたま動くローカルLLM小説生成CLI」から、**仕様・ドキュメント・テスト・実装が同期した、保守可能な制作パイプライン**へ整理する。

この計画は以下を統合する。

- ドキュメント改善
- テスト再構築
- 実装リファクタリング
- プロンプト / スキーマ / モデル整合性
- 開発・運用ゲート
- リポジトリ衛生管理

関連計画:

- [`REFACTOR_PLAN.md`](REFACTOR_PLAN.md)
- [`TEST_REVIEW_AND_REBUILD_PLAN.md`](TEST_REVIEW_AND_REBUILD_PLAN.md)
- [`PROMPT_SCHEMA_QUALITY_REVIEW.md`](PROMPT_SCHEMA_QUALITY_REVIEW.md)
- [`PROGRESS.md`](PROGRESS.md)

---

## 1. 現状サマリー

### 1.1 検証済みの現状

| 項目 | 結果 |
|---|---:|
| `src/novel_forge` | 22 files / 4,059 LOC |
| `tests` | 11 files / 3,122 LOC / 222 tests |
| Markdown docs | README + docs配下14件 + report 2件 |
| `uv run pytest tests -q` | 221 passed / 1 failed |
| `uv run ruff check src/novel_forge tests` | 11 errors |
| `uv run mypy src/novel_forge` | 35 errors |
| `uv run python scripts/validate_prompts.py` | 37 issues |
| Markdown relative links | broken link 0件 |

### 1.2 作業前の注意

既存の未コミット差分がある。

```text
M novel_forge.log
M prompts/*.md
M schemas/volume_design.json
M src/novel_forge/engine/design.py
?? docs/dev/REFACTOR_PLAN.md
?? docs/dev/TEST_REVIEW_AND_REBUILD_PLAN.md
?? docs/dev/MASTER_IMPROVEMENT_PLAN.md
?? series_romance_fantasy2/
```

**必ず Phase 0 で既存差分を分離する。**

---

## 2. ドキュメント改善計画

## 2.1 現在のドキュメント構成評価

### 現在の主要ドキュメント

| ファイル | LOC | 役割 | 状態 |
|---|---:|---|---|
| `README.md` | 142 | 利用者向け入口 | 古いCLI例・内部設計が混在 |
| `docs/PIPELINE.md` | 467 | パイプライン説明 | 長い。仕様と実装詳細が混在 |
| `docs/PROMPTS.md` | 134 | プロンプト方針 | 概要として有効だが実装同期が弱い |
| `docs/PROMPT_SCHEMA_MAP.md` | 191 | prompt/schema/code対応 | 一部古い。`volume_design` required等が不一致 |
| `docs/GLOSSARY.md` | 96 | 用語集 | 有効。入口から参照あり |
| `docs/KEYWORD_SELECTION_GUIDE.md` | 84 | 入力ガイド | 利用者向けとして有効 |
| `docs/dev/ARCHITECTURE.md` | 335 | 開発者向け構成 | 現状追随は一部できているが古い説明あり |
| `docs/dev/SPECIFICATION.md` | 228 | 実装仕様 | 古いファイル構成・存在しないschema・存在しない `--strict` が含まれる |
| `docs/dev/TEMPLATE_SCHEMA_CONTRACT.md` | 141 | prompt/schema役割分担 | 方針文書として有効だが誤字あり |
| `docs/dev/raw_log_format.md` | 97 | raw log仕様 | 実装と再確認が必要 |
| `docs/dev/schema_maintenance.md` | 50 | schema修正チェック | `scripts/validate_schemas.py` が存在しない可能性あり。要確認 |
| `docs/dev/OLLAMA_API.md` | 115 | Ollama仕様 | 有効だが現payloadと同期確認が必要 |
| `consistency_report.md` | 163 | 過去の整合性レポート | stale化。docs/dev配下へ移すか削除候補 |
| `placeholder_consistency_report.md` | 534 | 過去のplaceholderレポート | stale化。現在は `validate_prompts.py` に置換すべき |

### 構成上の問題

1. **利用者向け / 開発者向け / 監査レポートが混在**
   - README に内部アーキテクチャ詳細が入りすぎている。
   - `docs/dev/SPECIFICATION.md` は実装詳細であり、利用者仕様ではない。

2. **古い説明が残っている**
   - `docs/dev/SPECIFICATION.md` に `--strict` が記載されているが、現CLI helpには存在しない。
   - schema一覧に `scene_review.json`, `*_review.json` があるが、現schemasにはない。レビューは `review.json` 統一。
   - README の `plan --workdir ... --keywords` は現CLIと異なる。現CLIは `novel-forge plan [OPTIONS] KEYWORDS`。

3. **自動生成/検証結果のreportがrootに散らばっている**
   - `consistency_report.md`
   - `placeholder_consistency_report.md`
   - これらは最新版か不明で、読む人を迷わせる。

4. **ドキュメント間の責務境界が曖昧**
   - `PIPELINE.md` と `ARCHITECTURE.md` がどちらも構成説明を持つ。
   - `PROMPTS.md`, `PROMPT_SCHEMA_MAP.md`, `TEMPLATE_SCHEMA_CONTRACT.md` が重複している。

5. **ドキュメント検証がゲート化されていない**
   - link切れは現在0件だが、CLI例・schema名・prompt placeholderの実装同期は壊れている。

## 2.2 目標ドキュメント構成

```text
README.md                         # 利用者向け入口。短く、現CLIと一致

docs/
  INDEX.md                        # ドキュメント索引。対象読者別に案内
  USER_GUIDE.md                   # セットアップ、基本操作、成果物確認
  OPERATIONS.md                   # 実運用runbook、失敗時対応、再開、ログ調査
  CLI_REFERENCE.md                # `novel-forge --help` から同期するCLI仕様
  OUTPUT_LAYOUT.md                # series_dir配下の成果物構造
  KEYWORD_SELECTION_GUIDE.md      # 既存維持
  GLOSSARY.md                     # 既存維持

  design/
    PIPELINE.md                   # ユーザー可視の制作フローと状態遷移
    PROMPTS.md                    # prompt運用方針
    PROMPT_SCHEMA_MAP.md          # prompt/schema/task対応。自動検証対象
    TEMPLATE_SCHEMA_CONTRACT.md   # prompt/schemaの責務分担

  dev/
    ARCHITECTURE.md               # 実装構成。リファクタ後に更新
    TESTING.md                    # テスト方針・ゲート・fixture/fake
    REFACTOR_PLAN.md              # 既存
    TEST_REVIEW_AND_REBUILD_PLAN.md
    MASTER_IMPROVEMENT_PLAN.md
    OLLAMA_API.md
    RAW_LOG_FORMAT.md
    SCHEMA_MAINTENANCE.md
    DECISIONS/
      0001-review-schema-unification.md
      0002-template-schema-contract.md

  archive/
    consistency_report_YYYYMMDD.md
    placeholder_consistency_report_YYYYMMDD.md
```

### README の役割

README は以下に絞る。

- プロジェクト概要
- セットアップ
- 最短クイックスタート
- コマンド一覧へのリンク
- 出力先の概要
- 品質ゲート / 注意事項
- 詳細docsへの導線

内部クラス・mixin排除の説明は `docs/dev/ARCHITECTURE.md` へ移す。

### `docs/INDEX.md` の役割

対象読者別に案内する。

| 読者 | 読む順序 |
|---|---|
| 利用者 | README → USER_GUIDE → CLI_REFERENCE → OPERATIONS |
| プロンプト改善者 | PROMPTS → PROMPT_SCHEMA_MAP → TEMPLATE_SCHEMA_CONTRACT |
| 開発者 | ARCHITECTURE → TESTING → REFACTOR_PLAN |
| 運用・障害調査 | OPERATIONS → RAW_LOG_FORMAT → OLLAMA_API |

## 2.3 ドキュメント内容の改善項目

### README

- [ ] 現CLI helpと一致するよう修正
  - `plan` は `--keywords` ではなく positional `KEYWORDS`
  - `list` コマンドを追加
  - `--strict` は削除
- [ ] 内部アーキテクチャ詳細を削り、dev docsへ移動
- [ ] Mermaidで制作フローを追加
- [ ] 出力ファイル概要を追加
- [ ] 実行前提: Python 3.14 / uv / Ollama model / config.yaml
- [ ] 品質確認コマンドを現状に合わせる

### `docs/CLI_REFERENCE.md`

- [ ] `uv run novel-forge --help` と各subcommand helpから作成
- [ ] plan/design/write/export/status/resume/complete/doctor/list を網羅
- [ ] option default を明記
- [ ] CLI helpとの差分検出スクリプトを追加するか検討

### `docs/OPERATIONS.md`

- [ ] 通常運用手順: plan → design → write → export
- [ ] raw log有効化と確認方法
- [ ] ロックファイル対応
- [ ] 中断・resume手順
- [ ] Ollama接続失敗時
- [ ] schema validation failure時
- [ ] prompt placeholder不整合時
- [ ] 実モデル smoke の使い方

### `docs/design/PROMPT_SCHEMA_MAP.md`

- [ ] 現実装から再生成または手動同期
- [ ] `volume_design.required` を `title,premise,chapters` に修正
- [ ] `scene_review.json` 等の存在しないschemaを削除
- [ ] prompt placeholder一覧を追加
- [ ] `scripts/validate_prompts.py` の出力と一致させる

### `docs/dev/SPECIFICATION.md`

- [ ] `docs/dev/IMPLEMENTATION_SPEC.md` に改名を検討
- [ ] 古いschema一覧を修正
- [ ] 存在しない `--strict` 記述を削除
- [ ] ファイル構成を現状に更新
- [ ] 状態遷移の正を `PIPELINE.md` または `OUTPUT_LAYOUT.md` に集約

### root report類

- [ ] `consistency_report.md` と `placeholder_consistency_report.md` を `docs/archive/` に移動、または削除
- [ ] 最新の検証は `scripts/validate_prompts.py` と `contract tests` を正とする

---

## 3. テスト改善計画

詳細は [`TEST_REVIEW_AND_REBUILD_PLAN.md`](TEST_REVIEW_AND_REBUILD_PLAN.md) を正とする。

### 3.1 最優先修正

- [ ] `test_valid_volume_design` fixtureを現schemaへ追随
- [ ] unknown schemaを成功扱いするテストを廃止
- [ ] `scene_review` schema名問題を修正
- [ ] dict key重複を修正
- [ ] `test_fail_low_score` を実態に合う名前へ変更

### 3.2 テスト構成再編

```text
tests/
  fakes.py
  fixtures/factories.py
  unit/
  integration/
  contract/
```

### 3.3 必須contract tests

- [ ] 全schemaにvalid fixtureが存在し、通る
- [ ] invalid fixtureが期待エラーで落ちる
- [ ] 全prompt placeholderが実装側変数と一致
- [ ] `{schema}` prompt は対応schemaを持つ
- [ ] CLI docsとlive helpがズレていない

### 3.4 標準ゲート

```bash
uv run pytest tests -q
uv run ruff check src/novel_forge tests scripts
uv run python scripts/validate_prompts.py
```

mypyは当面baseline扱い。

```bash
uv run mypy src/novel_forge
```

---

## 4. 実装改善計画

詳細は [`REFACTOR_PLAN.md`](REFACTOR_PLAN.md) を正とする。

### 4.1 Phase 0: 破損・不整合の修正

- [ ] 現在のdirty差分を分離
- [ ] pytest failureを解消
- [ ] ruffエラーを解消
- [ ] prompt placeholder不整合を修正
- [ ] prompt/schemaの品質要件不足を修正（詳細: [`PROMPT_SCHEMA_QUALITY_REVIEW.md`](PROMPT_SCHEMA_QUALITY_REVIEW.md)）
- [ ] docsの明確な嘘を修正（CLI例、存在しないschema、`--strict`）

### 4.2 Phase 1: TaskDefinition / LLMTaskRunner

目的: LLM呼び出しを task 単位で宣言化し、fake runnerでテスト可能にする。

- [ ] `TaskDefinition`
- [ ] `TaskRegistry`
- [ ] `LLMTaskRunner`
- [ ] generate/review/revise loopの単体テスト

### 4.3 Phase 2: DesignWorkflow抽出

- [ ] `DesignContext`
- [ ] volume/chapter/scene phaseの分割
- [ ] scene番号・chapter内scene番号のテスト
- [ ] artifact build/saveの分離

### 4.4 Phase 3: LLMClient分割

- [ ] payload builder
- [ ] Ollama HTTP client
- [ ] raw log repository
- [ ] schema validator
- [ ] `think=False` payload test

### 4.5 Phase 4: SceneWriter分割

- [ ] SceneDraftWorkflow
- [ ] ScenePromptContextBuilder
- [ ] SceneArtifactRepository
- [ ] BibleUpdateService
- [ ] `--max-scenes` smoke limiterを追加検討

### 4.6 Phase 5: ProjectRepository導入

- [ ] state / blackboard / bible / volume / scene / export pathを集約
- [ ] `_save_path`, `_load_path` の直接利用を段階的に置換
- [ ] artifact layout contract testを追加

---

## 5. プロンプト・スキーマ・モデル整合性改善

### 5.1 現在の主な問題

`scripts/validate_prompts.py` で37件のplaceholder不一致が出ている。

代表例:

- `chapter_design.md`: `{volume_title}`, `{volume_premise}` が実装から渡されていない
- `scene_design.md`: 章/巻context系placeholderが多数不足
- `scene_review.md` / `scene_revision.md`: `{concept_json}` が渡されていない
- `series_plan_*`: prompt側placeholder名と実装側keyが不一致
- `volume_design_review.md`: `{concept_text}` が渡されていない

### 5.2 改善方針

- [ ] prompt側を直すのか、実装側keyを直すのかをタスク単位で決める
- [ ] placeholder名を `series_plan`, `volume_title`, `volume_premise`, `chapter_*`, `scene_*` に統一
- [ ] prompt/schema mapを手動文書ではなく contract test で検証する
- [ ] schemaには構造、promptには品質指示、review promptには品質基準、という責務を徹底

### 5.3 schema方針

- [ ] unknown schemaはfail-fastへ変更
- [ ] `review.json` 統一を文書・テスト・実装で固定
- [ ] `volume_design` の `title/premise` 必須化にfixture・docsを追随
- [ ] schema-valid but semantically-invalid な出力を追加検証

---

## 6. 開発・運用ゲート改善

### 6.1 `scripts/check_quality.py` または `scripts/check.sh`

以下をまとめて実行する。

```bash
uv run pytest tests -q
uv run ruff check src/novel_forge tests scripts
uv run python scripts/validate_prompts.py
uv run python -m novel_forge.cli --help
```

mypyは初期段階ではwarning扱いにする。

### 6.2 pyproject整備

- [ ] pytest設定を追加
  - `testpaths = ["tests"]`
  - markers: `unit`, `integration`, `contract`, `real_model`
- [ ] ruff対象を明確化
- [ ] mypy baseline strategyを明記

### 6.3 CI相当のローカル手順

- [ ] fast gate
- [ ] full gate
- [ ] real model smoke
- [ ] release/readiness checklist

---

## 7. リポジトリ衛生管理

### 7.1 `.gitignore` / generated artifacts

現在 `search_files` で以下が見えている。

- `.mypy_cache/`
- `.ruff_cache/`
- `.pytest_cache/`
- `.venv/`
- `novel_forge.log`
- `series_romance_fantasy2/`
- raw logs
- `__pycache__/`

対応:

- [ ] `.gitignore` を確認・更新
- [ ] 生成物はGit管理外へ
- [ ] sampleとして残す必要がある場合は `examples/` に最小化して配置
- [ ] root直下のreport類を `docs/archive/` へ移動または削除

### 7.2 config管理

- [ ] `config.example.yaml` を作る
- [ ] 実運用configはGit管理外
- [ ] README/OPERATIONSからexampleへ誘導

---

## 8. 推奨実施順序

## Phase 0 — 現状固定と破損修正

| 項目 | 内容 | 検証 |
|---|---|---|
| 0.1 | dirty差分を分類 | `git status --short`, `git diff --stat` |
| 0.2 | pytest failure修正 | `uv run pytest tests -q` |
| 0.3 | ruff修正 | `uv run ruff check src/novel_forge tests scripts` |
| 0.4 | 明確に古いdocs修正 | CLI help smoke |
| 0.5 | `.gitignore` / generated artifacts整理 | `git status --short` |

## Phase 1 — ドキュメント再構成の土台

| 項目 | 内容 | 検証 |
|---|---|---|
| 1.1 | `docs/INDEX.md` 作成 | link check |
| 1.2 | READMEを利用者向けに縮小 | live CLI helpと照合 |
| 1.3 | CLI_REFERENCE作成 | `novel-forge --help` と照合 |
| 1.4 | OPERATIONS作成 | 実行手順・障害対応確認 |
| 1.5 | root reportをarchiveへ | link check |

## Phase 2 — テスト再構築

| 項目 | 内容 | 検証 |
|---|---|---|
| 2.1 | `tests/fakes.py` / factories作成 | unit tests |
| 2.2 | schema fixtures作成 | contract tests |
| 2.3 | prompt/schema contract pytest化 | contract tests |
| 2.4 | engine integration分割 | fake pipeline green |
| 2.5 | CLI smoke追加 | integration green |

## Phase 3 — prompt/schema/model整合性修正

| 項目 | 内容 | 検証 |
|---|---|---|
| 3.1 | placeholder不一致修正 | `validate_prompts.py` green |
| 3.2 | schema requiredとfixtures同期 | schema contract green |
| 3.3 | model/schema drift修正 | unit + mypy改善 |
| 3.4 | raw log仕様を実装に同期 | raw log tests |

## Phase 4 — 実装リファクタリング

| 項目 | 内容 | 検証 |
|---|---|---|
| 4.1 | LLMTaskRunner導入 | runner tests |
| 4.2 | DesignWorkflow抽出 | design workflow tests |
| 4.3 | LLMClient分割 | payload/raw log tests |
| 4.4 | SceneWriter分割 | write workflow tests |
| 4.5 | ProjectRepository導入 | artifact layout tests |

## Phase 5 — 実モデル検証と最終docs同期

| 項目 | 内容 | 検証 |
|---|---|---|
| 5.1 | fake LLM full pipeline | integration green |
| 5.2 | minimal real model smoke | raw log確認 |
| 5.3 | docs final sync | docs contract green |
| 5.4 | release checklist | full gate green |

---

## 9. 完了条件

### Documentation Done

- [ ] READMEが現CLIと一致
- [ ] docs/INDEX.md がある
- [ ] user/dev/operation/design docsが分離されている
- [ ] 古い `--strict`, 存在しないschema記述がない
- [ ] rootに古いreportが残っていない
- [ ] link check green

### Testing Done

- [ ] pytest green
- [ ] ruff green
- [ ] prompt/schema contract green
- [ ] fake LLM full pipeline green
- [ ] CLI smoke green
- [ ] unknown schema成功テストがない

### Implementation Done

- [ ] workflow/task/repository境界が明確
- [ ] private helper bind型テストが不要
- [ ] prompt/schema/model不整合が解消
- [ ] raw logとresumeがテストされている
- [ ] 実モデルsmokeが最小手順で再現可能

### Repository Hygiene Done

- [ ] generated artifactsがGit管理外
- [ ] `.gitignore` が現実に合っている
- [ ] `config.example.yaml` がある
- [ ] `git status --short` が意図した差分のみ

---

## 10. 最初に実行する具体タスク

1. `test_valid_volume_design` を直して pytest を green にする。
2. `ruff` の11件を直す。
3. READMEのCLI例を現helpに合わせる。
4. `docs/dev/SPECIFICATION.md` の `--strict` と存在しないschema一覧を修正する。
5. `docs/INDEX.md` を作る。
6. `tests/fakes.py` / factories を作る。
7. prompt placeholder不整合を1カテゴリずつ直す。

この順番なら、ユーザー向けの嘘を減らしつつ、リファクタリング前に検出力を高められる。
