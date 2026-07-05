# NovelForge Refactoring Plan

作成日: 2026-07-05
対象: `/mnt/hdd/projects/novel-forge`

関連する全体改善計画: [`MASTER_IMPROVEMENT_PLAN.md`](MASTER_IMPROVEMENT_PLAN.md)

## 0. 現状サマリー

### コード規模

| 領域 | ファイル数 | 行数 |
|---|---:|---:|
| `src/novel_forge` | 22 | 4,059 |
| `tests` | 11 | 3,122 |

大きめのファイル:

| ファイル | 行数 | 主な問題 |
|---|---:|---|
| `llm_client.py` | 468 | HTTP通信、payload構築、リトライ、raw log、schema検証が密結合 |
| `engine/plan.py` | 347 | 3段階生成の制御とprompt/review/revise定義が同居 |
| `scene_writer.py` | 302 | シーン生成、レビュー、改稿、Bible更新、保存処理が同居 |
| `engine/base.py` | 291 | DI、設定読込、ログ、ロック回収、storage初期化が集中 |
| `engine/design.py` | 288 | volume/chapter/scene design の3段階処理が1関数に集中 |

### 直近の検証結果

`uv run pytest tests/ -q` の結果:

```text
221 passed, 1 failed
FAILED tests/test_schemas_extended.py::TestValidate::test_valid_volume_design
原因: `schemas/volume_design.json` が `title` / `premise` 必須に変更済みだが、既存テストfixtureが追随していない。
```

### 作業前提

- 既存の uncommitted changes があるため、リファクタリング前に差分を分離する。
- プロンプト・スキーマ変更とコード構造変更を同一コミットに混ぜない。
- 実モデル検証は高コストなので、単体テスト → fake LLM smoke → 必要最小の実モデル smoke の順でゲートを置く。

---

## 1. リファクタリングの目的

1. **LLMタスク実行の統一**
   - plan/design/write/export で重複している `generate -> validate -> review -> revise` 定義を、タスク単位に整理する。

2. **巨大関数の分割**
   - `design()` と `plan()` を phase 単位の小さな workflow に分け、テスト対象を狭くする。

3. **I/O境界の明確化**
   - raw log、state保存、volume/chapter/scene artifact保存を repository 層に寄せる。

4. **Ollama/LLM通信の堅牢化**
   - payload構築、HTTP streaming、JSON parse、schema validation、raw logging を分離する。

5. **テストしやすさの向上**
   - 実LLMなしで plan/design/write の主要分岐を検証できる fake task runner を標準化する。

---

## 2. 目標アーキテクチャ

```text
cli.py
  -> engine/NovelEngine thin facade
      -> workflows/
          plan_workflow.py
          design_workflow.py
          write_workflow.py
          export_workflow.py
      -> task_runner.py
          LLMTaskRunner
          FakeLLMTaskRunner
      -> tasks/
          registry.py
          definitions.py
      -> repositories/
          project_repository.py
          raw_log_repository.py
  -> infra/
      ollama_client.py
      json_response_parser.py
      schema_validator.py
```

### 主要コンポーネント

| コンポーネント | 責務 |
|---|---|
| `Workflow` | phaseの順序制御のみ。promptやschemaの詳細を持たない |
| `TaskDefinition` | `task_name`, prompt template, schema, validate_fn, review task, revision task を定義 |
| `LLMTaskRunner` | TaskDefinitionを実行し、generate/review/revise loopを担当 |
| `ProjectRepository` | state, series_plan, volume/chapter/scene JSON, manuscript を保存・読込 |
| `RawLogRepository` | request/response gzip、summary markdown を保存 |
| `OllamaClient` | HTTP streamingのみ。schemaやpromptを知らない |
| `SchemaValidator` | JSON Schema validationとpath付きエラー生成 |

---

## 3. 実施フェーズ

## Phase 0 — 作業ベースライン固定

### 目的
既存変更とリファクタリング変更を混ぜない。

### タスク

- [ ] `git status --short` と `git diff --stat` を確認。
- [ ] 既存変更の扱いを決める。
  - prompt/schema/design.py の現差分を先にテスト修正してコミットする、または別ブランチ/一時退避する。
- [ ] 現在失敗している `test_valid_volume_design` を schema変更に合わせて修正。
- [ ] `uv run pytest tests/ -q` を green にする。
- [ ] `uv run ruff check .` を通す。

### 完了条件

- [ ] tests green
- [ ] ruff green
- [ ] `git status --short` でリファクタリング対象外の差分が分離されている

---

## Phase 1 — LLMタスク定義の導入

### 目的
prompt/schema/validator/reviewer/reviser の散在を止め、タスク名で扱えるようにする。

### 追加ファイル案

```text
src/novel_forge/tasks.py                  # TaskDefinition, TaskRegistry
src/novel_forge/llm_task_runner.py        # generate/review/revise loop
```

既に同名ファイルが存在する別系統プロジェクト（`novelpress-chatgpt`）の構成を参考にするが、NovelForge側の現行APIに合わせて最小移植する。

### タスク

- [ ] `TaskDefinition` dataclassを追加。
- [ ] `TaskRegistry` を追加し、まず `volume_design`, `chapter_design`, `scene_design` だけ登録。
- [ ] 現行 `generate_and_review()` を壊さず、内部から `LLMTaskRunner` に移せる形に薄くする。
- [ ] fake LLMで `volume_design -> review -> revise` を単体テスト。

### 完了条件

- [ ] 既存CLI挙動が変わらない
- [ ] design系タスク定義がregistryで参照可能
- [ ] tests/ruff green

---

## Phase 2 — `engine/design.py` の分割

### 目的
288行の `design()` を phase 単位に分け、バグ修正とprompt改善の影響範囲を狭める。

### 目標構成

```text
src/novel_forge/workflows/design_workflow.py
src/novel_forge/workflows/design_context.py
src/novel_forge/workflows/design_phases.py
```

### 分割案

| 現在 | 移動先 | 備考 |
|---|---|---|
| volume design生成 | `generate_volume_design()` | previous volume contextを引数化 |
| chapter design loop | `generate_chapter_designs()` | previous chapter outcomeを明示的に持つ |
| scene design loop | `generate_scene_designs()` | scene numberingを専用関数化 |
| result build/save | `ProjectRepository.save_volume_design()` | artifact保存をrepositoryへ |
| `_review_*` | task definition / runner | prompt名とschemaを宣言化 |

### タスク

- [ ] `DesignContext` を作る（series_plan, genre, vol_num, previous_design等）。
- [ ] volume/chapter/scene の各phase関数を抽出。
- [ ] `chapter_scene_number` が現在グローバル連番になっている点を検証し、必要なら章内連番へ修正。
- [ ] 保存処理を `ProjectRepository` へ移す前に、まず純粋な result build 関数をテストする。
- [ ] 現行 `NovelEngine.design()` は新workflow呼び出しだけにする。

### 完了条件

- [ ] `design()` が orchestration だけになる
- [ ] design workflowの単体テストがfake LLMで通る
- [ ] 既存fixture互換を維持

---

## Phase 3 — `llm_client.py` の分割

### 目的
LLM通信の障害調査を簡単にし、Ollama仕様変更・thinkingモデル対応を安全に変更できるようにする。

### 目標構成

```text
src/novel_forge/llm/
  __init__.py
  config.py              # load_config, _build_ollama_options
  ollama_client.py       # HTTP streaming
  payload.py             # build_payload
  raw_log.py             # raw log save + summary
  validation.py          # schema validation wrapper
```

### タスク

- [ ] `_build_ollama_options()` と `load_config()` を `llm/config.py` へ移動。
- [ ] `_build_payload()` を純粋関数化し、`think=False` の扱いをテストで固定。
- [ ] `_call_api()` を `OllamaClient` に分離。
- [ ] raw log保存を `RawLogRepository` に分離。
- [ ] 既存 `LLMClient` は互換 facade として残す。

### 完了条件

- [ ] `LLMClient.complete_json()` の外部API互換維持
- [ ] payloadテスト、raw logテスト、parse/validationテストが独立
- [ ] tests/ruff green

---

## Phase 4 — `scene_writer.py` の責務分割

### 目的
本文生成、レビュー、保存、Bible更新を分離し、シーン単位の再実行・差分検証を容易にする。

### 分割案

| 新コンポーネント | 責務 |
|---|---|
| `SceneDraftWorkflow` | draft/review/revise の制御 |
| `ScenePromptContextBuilder` | scene_draft/review/revision のtemplate変数生成 |
| `SceneArtifactRepository` | scene draft保存・読込 |
| `BibleUpdateService` | summarize_and_update_bible |

### タスク

- [ ] `write_scene()` から prompt context生成を抽出。
- [ ] `_call_review_api()` を LLMTaskRunner 経由へ寄せる。
- [ ] `_revise_scene()` を task definition 化。
- [ ] `save_scene_draft()` / `load_scene_draft()` を repository へ移す。
- [ ] Bible更新は scene draft保存後の明示ステップにする。

### 完了条件

- [ ] fake LLMで scene draft/review/revise の単体テストが可能
- [ ] write workflowが途中再開しやすい構造になる

---

## Phase 5 — `engine/base.py` と repository 層の整理

### 目的
NovelEngineBaseを「状態を持つ巨大オブジェクト」から「依存関係を束ねる薄いコンテナ」に寄せる。

### タスク

- [ ] state/blackboard/bible/volume artifact保存を `ProjectRepository` に集約。
- [ ] lock回収処理を `engine/infra.py` または `locking.py` に移動。
- [ ] logging setupを `make_engine()` 側に寄せ、`NovelEngineBase.__init__` の副作用を減らす。
- [ ] `engine._save_path`, `_load_path`, `_current_volume` の直接利用箇所をrepository経由へ置換。

### 完了条件

- [ ] `NovelEngineBase.__init__` が設定・DI中心になる
- [ ] artifact保存場所の仕様が1箇所でテストされる

---

## Phase 6 — CLIとドキュメント更新

### 目的
内部構造変更後もCLIユーザー体験を維持し、開発者向け文書を最新化する。

### タスク

- [ ] `docs/dev/ARCHITECTURE.md` を新構成に更新。
- [ ] `docs/PIPELINE.md` の古い説明（例: severity名の不一致、schema置換説明など）を実装と同期。
- [ ] `README.md` のアーキテクチャ図を更新。
- [ ] `doctor`, `status`, `complete` のsmoke testを追加。

### 完了条件

- [ ] docsが実装と一致
- [ ] CLI smoke test green

---

## 4. 実行順序とコミット単位

| 順序 | コミット内容 | 検証 |
|---:|---|---|
| 1 | 現在のprompt/schema変更のテスト追随、または差分退避 | pytest, ruff |
| 2 | TaskDefinition/TaskRegistry/LLMTaskRunner導入（互換維持） | pytest, fake runner tests |
| 3 | design workflow分割 | pytest, design fake smoke |
| 4 | llm_client分割 | pytest, raw log/payload tests |
| 5 | scene_writer分割 | pytest, write fake smoke |
| 6 | repository層導入・engine/base縮小 | pytest, CLI smoke |
| 7 | docs更新 | link/path確認, pytest |

---

## 5. テスト戦略

詳細なテスト監査と再構築方針は [`docs/dev/TEST_REVIEW_AND_REBUILD_PLAN.md`](TEST_REVIEW_AND_REBUILD_PLAN.md) を参照。

### 常時実行

```bash
uv run pytest tests/ -q
uv run ruff check src/novel_forge tests scripts
uv run python scripts/validate_prompts.py
```

### 追加するテスト

| テスト | 目的 |
|---|---|
| `test_task_registry.py` | task名からprompt/schema/validatorを取得できる |
| `test_llm_task_runner.py` | generate/review/reviseの分岐をfake LLMで固定 |
| `test_design_workflow.py` | volume/chapter/scene designを実LLMなしで実行 |
| `test_llm_payload.py` | `think`, `format=json`, options, seedの構築を固定 |
| `test_raw_log_repository.py` | gzip保存とsummary追記を検証 |
| `test_project_repository.py` | vol/ch/sc artifact pathを固定 |
| `test_cli_smoke.py` | `doctor/status/list` 等の軽量CLIを検証 |

### 実モデル smoke

高コストなので各大フェーズの最後のみ実施。

```bash
uv run novel-forge plan "短編 SF 図書館 AI" --workdir /mnt/hdd/projects/novel-forge-smoke --max-generation-count 1 --max-review-count 1 --raw-log
uv run novel-forge design --workdir /mnt/hdd/projects/novel-forge-smoke --volume 1 --max-generation-count 1 --max-review-count 1 --raw-log
```

必要なら write は1シーンだけ実行できる smoke limiter を先に追加する。

---

## 6. リスクと対策

| リスク | 対策 |
|---|---|
| prompt/schema変更と構造変更が混ざる | Phase 0で必ず差分分離 |
| 実LLMの非決定性でリファクタリング検証が遅い | fake LLM runnerを先に作る |
| raw log形式が変わり過去調査しにくくなる | RawLogRepositoryで互換テストを書く |
| `NovelEngine` のprivate属性参照が多く移行漏れしやすい | repository導入は最後。先にworkflow分割だけ行う |
| schema更新で既存fixtureが壊れる | schemaごとのvalid fixtureを `tests/fixtures` に集約 |
| Ollama thinkingモデルでcontent空問題が再発 | payload testで `think=False` 設定を固定できるようにする |

---

## 7. 最初に着手する具体タスク

1. `tests/test_schemas_extended.py::TestValidate::test_valid_volume_design` を現schemaに合わせる。
2. `uv run pytest tests/ -q` を green にする。
3. `uv run ruff check .` を実行し、既存差分の品質を確認する。
4. `TaskDefinition` / `TaskRegistry` の最小実装を追加する。
5. `volume_design` のみ `LLMTaskRunner` 経由で実行できるようにしてテストする。

この順番なら、現在の破損を解消してから安全に構造変更へ入れる。
