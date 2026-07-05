# NovelForge Test Review and Rebuild Plan

作成日: 2026-07-05
対象: `/mnt/hdd/projects/novel-forge`

## 0. 結論

関連する全体改善計画: [`MASTER_IMPROVEMENT_PLAN.md`](MASTER_IMPROVEMENT_PLAN.md)

現在のテストは「数はあるが、品質ゲートとしては弱い」。

- **現在のテスト内容**: 一部は有効だが、古い仕様・private実装・存在確認レベルのテストが多く、LLMワークフローの本質的な失敗を十分に検出できていない。
- **テスト実施方法**: `pytest` だけでは不十分。`ruff`, `mypy`, prompt/schema contract, CLI smoke を標準ゲートに入れる必要がある。
- **テストしやすい実装か**: まだ十分ではない。`NovelEngineBase`, `design()`, `scene_writer`, `llm_client` が密結合で、fake LLM・repository・workflow単位のテストが書きにくい。
- **方針**: 既存テストを全面的に整理してよい。特に `test_engine_integration.py` は分割・再構築する。

---

## 1. 実測値

### テスト構成

| ファイル | LOC | tests | asserts | 特徴 |
|---|---:|---:|---:|---|
| `tests/test_engine_integration.py` | 1,012 | 41 | 52 | 巨大。MockLLMと多数fixtureが内包され、責務過多 |
| `tests/test_context_builder.py` | 471 | 29 | 72 | 比較的良い。formatting/limitsを細かく検証 |
| `tests/test_llm_client.py` | 349 | 22 | 40 | HTTP mock中心。payload/raw logは有効 |
| `tests/test_schemas_extended.py` | 333 | 31 | 33 | schema driftを検出するが、古いfixtureあり |
| `tests/test_models.py` | 285 | 32 | 38 | models/storage/prompts/engineが混在 |
| `tests/test_export.py` | 278 | 16 | 35 | MagicMock engineにprivate関数をbindしており脆い |
| `tests/test_json_parser.py` | 171 | 26 | 24 | `schemas.py` と重複する独自validator系が混在 |
| `tests/test_scene_writer.py` | 77 | 6 | 6 | loadのみ。write/review/revise本体をほぼ未検証 |
| `tests/test_storage.py` | 59 | 6 | 7 | atomic save/backupは有効 |
| `tests/test_prompts.py` | 52 | 9 | 8 | render単体のみ。template contractは未統合 |
| `tests/test_quality.py` | 35 | 4 | 4 | 古いscore前提名が残る |

合計: **222 tests / 3,122 LOC**

### 現在の実行結果

```text
uv run pytest tests/ -q
=> 221 passed, 1 failed

FAILED tests/test_schemas_extended.py::TestValidate::test_valid_volume_design
原因: schemas/volume_design.json は title/premise 必須だが、テストfixtureが chapters のみ。
```

### lint/type/prompt contract の結果

```text
uv run ruff check tests src/novel_forge
=> 11 errors
```

主なもの:

- `tests/test_schemas_extended.py`: dict key `field` の重複 (`F601`)
- `src/novel_forge/engine/design.py`: 未使用 `sc_data`
- `src/novel_forge/engine/review.py`: 未使用 `minor`
- `json_parser.py`, `prompts.py`: simplification系

```text
uv run mypy src/novel_forge
=> 35 errors in 10 files
```

主なもの:

- `engine/design.py` の tuple/dict 型混在
- `bible_manager.py` の同一変数に別型を再代入
- `write.py` の `VolumeOutline.chapters` 型不一致

```text
uv run python scripts/validate_prompts.py
=> 37 issues
```

`chapter_design.md`, `scene_design.md`, `series_plan_*`, `volume_design_review.md` などで、prompt placeholder と実装側の渡し値が一致していない。

---

## 2. 現在のテスト内容は適切か

### 良い点

- `ContextBuilder` は細かい表示・制限件数・空データを検証している。
- `LLMClient` は streaming NDJSON、retry、payload、raw log をmockで検証している。
- `Storage` は破損時backup fallbackを検証している。
- `QualityGate` は severity ベースの最低限の境界を持っている。

### 問題点

#### 2.1 存在確認・弱いassertが多い

例:

- `assert "properties" in schema`
- `assert len(errors) > 0`
- `assert "chapters" in schema["properties"]`

これは「壊れていること」は多少検出できるが、「仕様通りか」は保証しない。

改善:

- error内容を具体的に検証する。
- valid fixture / invalid fixture を分ける。
- schema-valid だが意味的に不正な出力も検証する。

#### 2.2 存在しない schema 名でも成功するテストがある

`tests/test_schemas_extended.py::test_valid_scene_review` は `validate("scene_review", data)` を呼んでいるが、`schemas/scene_review.json` は存在しない。

現在の `schemas.validate()` は unknown schema で `[]` を返すため、このテストは **schemaを検証していないのに成功する**。

これは危険。unknown schema は原則 fail-fast にすべき。

推奨:

- production path: unknown schema は `FileNotFoundError` / `SchemaNotFoundError`
- test path: `assert_schema_exists(name)` をfixture化
- 互換が必要なら `validate(..., allow_unknown=True)` のように明示する

#### 2.3 schemaとfixtureが同期していない

現在の失敗がその例。

`volume_design.json` は `title`, `premise`, `chapters` 必須だが、valid fixture が `chapters` のみ。

推奨:

```text
tests/fixtures/schemas/valid/volume_design.json
tests/fixtures/schemas/invalid/volume_design_missing_title.json
tests/fixtures/schemas/invalid/volume_design_invalid_purpose.json
```

schema変更時は fixture を更新する運用にする。

#### 2.4 `test_engine_integration.py` が巨大すぎる

1ファイル 1,012行で、以下が混在している。

- MockLLMClient
- plan tests
- design/outline tests
- write tests
- export/resume/status tests
- context/bible/quality tests
- prompt completeness tests

問題:

- 変更影響が読みづらい。
- helper/fakeがファイル内に閉じていて再利用できない。
- テスト名はintegrationだが、実際はunit/characterization/mock integrationが混ざっている。

推奨:

```text
tests/fakes.py
tests/fixtures/factories.py
tests/unit/engine/test_plan_workflow.py
tests/unit/engine/test_design_workflow.py
tests/unit/engine/test_write_workflow.py
tests/integration/test_engine_pipeline_fake_llm.py
```

#### 2.5 private実装への依存が強い

例:

- `mock_engine._assemble_manuscript = _assemble_manuscript.__get__(engine)`
- `engine._series_dir`
- `engine._state`
- `engine._current_volume`

private関数を直接bindするテストは、リファクタリング時に壊れやすい。behaviorではなく構造を固定してしまう。

推奨:

- public workflow / repository API を作ってそこをテストする。
- private helper は「抽出後のpublic component」としてテストする。
- `NovelEngine` は thin facade delegation test に留める。

#### 2.6 LLMワークフロー特有の失敗が薄い

現状で不足している代表例:

- JSON Schemaは通るが、要求volume番号と出力volume番号が違う
- chapter番号・scene番号が重複し、ファイル上書き/脱落する
- `ready_for_publication=true` なのに critical/major issue がある
- reviewがschema-validだが revision対象 field が存在しない
- prompt placeholder が未置換のままLLMに渡る
- raw logが request/response の対応関係を失う
- resume時に既存artifactを壊す

---

## 3. テスト実施方法は適切か

### 現在の標準コマンド

README上は以下のみ。

```bash
uv run pytest tests/ -x -q
uv run ruff check .
```

### 問題

- `pytest -x` は最初の失敗で止まるため、全体像把握には不向き。
- `ruff` が現在失敗しているが、CI相当の必須ゲートとして扱われていない。
- `mypy` が pyproject にあるのに運用ゲート化されていない。
- `scripts/validate_prompts.py` があるが、テスト/CIゲートに入っていない。
- CLI smoke がない。
- 実LLM smoke と fake LLM integration の役割が分かれていない。

### 推奨ゲート

#### fast gate: 変更ごとに実行

```bash
uv run pytest tests/unit -q
uv run ruff check src/novel_forge tests
```

#### full local gate: コミット前

```bash
uv run pytest tests -q
uv run ruff check src/novel_forge tests scripts
uv run mypy src/novel_forge
uv run python scripts/validate_prompts.py
uv run python -m novel_forge.cli --help
```

#### integration gate: workflow変更時

```bash
uv run pytest tests/integration -q
```

内容:

- fake LLMで `plan -> design -> write -> export`
- artifact生成確認
- resume確認
- raw log確認

#### real-model smoke: 大きなprompt/schema変更時のみ

```bash
uv run novel-forge plan "短編 SF 図書館 AI" --workdir /mnt/hdd/projects/novel-forge-smoke --max-generation-count 1 --max-review-count 1
uv run novel-forge design --workdir /mnt/hdd/projects/novel-forge-smoke --volume 1 --max-generation-count 1 --max-review-count 1
```

`write` は1シーンだけ実行できる `--max-scenes 1` を追加してからsmoke対象にする。

---

## 4. テストしやすい実装になっているか

### 現状評価

| 領域 | 評価 | 理由 |
|---|---|---|
| `ContextBuilder` | 良い | storage注入ができ、テストが軽い |
| `Storage` | 良い | filesystem境界が明確 |
| `QualityGate` | 良い | pureに近い |
| `LLMClient` | 普通 | HTTP mock可能だが、payload/raw log/parseが1クラスに集中 |
| `SceneWriter` | 弱い | prompt生成、LLM、保存、Bible更新が密結合 |
| `engine/design.py` | 弱い | 1関数に3phase + save + review/revise が集中 |
| `NovelEngineBase` | 弱い | init副作用が多く、log/config/storage/LLM初期化が密結合 |
| CLI | 弱い | Typer commandのsmoke/runner testsがない |

### 実装修正方針

テストしやすくするには、以下の順で抽出する。

1. **TaskDefinition / LLMTaskRunner**
   - prompt/schema/validator/reviewer/reviser を宣言化
   - fake runnerでLLMなし検証

2. **ProjectRepository**
   - state/series_plan/volume/chapter/scene/export のpathとI/Oを集約
   - private `_save_path`, `_load_path` を段階的に置換

3. **Workflow classes**
   - `PlanWorkflow`, `DesignWorkflow`, `WriteWorkflow`, `ExportWorkflow`
   - `NovelEngine` は delegationのみ

4. **LLM infra分割**
   - `PayloadBuilder`, `OllamaClient`, `RawLogRepository`, `SchemaValidator`

5. **CLI runner tests**
   - Typer CliRunner または subprocess smoke を導入

---

## 5. 作り直す場合の新テスト構成

```text
tests/
  conftest.py
  fakes.py
  fixtures/
    factories.py
    schemas/
      valid/
      invalid/
    prompts/
  unit/
    test_quality_gate.py
    test_schema_validator.py
    test_json_parser.py
    test_prompt_manager.py
    test_project_repository.py
    test_raw_log_repository.py
    test_llm_payload.py
    test_llm_task_runner.py
    workflows/
      test_plan_workflow.py
      test_design_workflow.py
      test_write_workflow.py
      test_export_workflow.py
  integration/
    test_engine_facade_delegation.py
    test_pipeline_fake_llm.py
    test_resume_fake_llm.py
    test_cli_smoke.py
  contract/
    test_prompt_schema_contract.py
    test_schema_fixtures.py
    test_artifact_layout_contract.py
```

### 共通fixture/fake

`tests/fakes.py`:

- `FakeLLMClient`
- `FakeTaskRunner`
- `RecordingPromptManager`
- `InMemoryProjectRepository`

`tests/fixtures/factories.py`:

- `make_series_plan()`
- `make_volume_design()`
- `make_chapter_design()`
- `make_scene_design()`
- `make_review()`
- `make_scene_draft()`

---

## 6. 必須で追加すべきテスト

### 6.1 schema validator

- [ ] unknown schema は原則エラーになる
- [ ] valid fixture は全schemaで通る
- [ ] invalid fixture は期待エラーを返す
- [ ] `volume_design` は `title`, `premise`, `chapters` 必須
- [ ] review severity は `致命的|重要|軽微` のみ

### 6.2 prompt/schema contract

- [ ] 全promptのplaceholderが実装側で渡される
- [ ] 実装側の余分なkeyをwarning/failで検出
- [ ] `{schema}` を持つpromptは対応schemaが存在する
- [ ] raw promptに未置換 `{xxx}` が残らない

### 6.3 LLMTaskRunner

- [ ] generation schema validation failure は seedを変えてretry
- [ ] schema echo はretry
- [ ] critical issue はrevisionへ進む
- [ ] 重要issue 1件ならpass、2件ならrevision
- [ ] review schema failure はfail-fastまたは指定retry
- [ ] max_generation/max_review 到達で明確なRuntimeError

### 6.4 design workflow

- [ ] volume designの `title/premise` が最終 `vol01.json` に保存される
- [ ] chapter数とscene数が一致する
- [ ] scene番号が重複しない
- [ ] `chapter_scene_number` が章内番号として渡される
- [ ] 前章outcome / 前巻summary が次phaseに渡る
- [ ] 既存volumeの再実行でartifactを意図せず破壊しない

### 6.5 write workflow

- [ ] 既に `修正済` / `強制出力済` のsceneはskip
- [ ] draft保存後にBible更新が実行される
- [ ] review critical issue でrevisionが発生する
- [ ] scene本文が最低長未満ならretry/error
- [ ] 1シーンだけのsmoke limiterが機能する

### 6.6 export/resume

- [ ] manuscript本文の章順・scene順が正しい
- [ ] metadata title/volume/slug が state と一致する
- [ ] 強制出力sceneがreadiness reportに出る
- [ ] resumeが status/volume status を正しく解釈する
- [ ] export再実行が冪等

### 6.7 CLI

- [ ] `novel-forge --help`
- [ ] `novel-forge doctor --help`
- [ ] `novel-forge status --workdir <tmp>`
- [ ] `plan/design/write/export` がfake engineで呼び出し可能
- [ ] lock中のコマンドが適切に失敗する

---

## 7. 移行順序

### Step 1: 現在の壊れたテストを直す

- [ ] `test_valid_volume_design` fixtureに `title`, `premise` を追加
- [ ] `scene_review` という存在しないschema名を `review` に修正、または `scene_review.json` を作るか判断
- [ ] 重複dict keyを修正
- [ ] `test_fail_low_score` を `test_score_is_ignored_when_no_severity_issues` に改名

### Step 2: テスト実行ゲートを整備

- [ ] `pyproject.toml` に pytest config を追加
- [ ] `scripts/check.sh` または `uv run python scripts/check_quality.py` を作る
- [ ] gate: pytest + ruff + prompt validator を通す
- [ ] mypyは当面 `allow-fail` 扱いでbaseline化、段階的に0へ

### Step 3: fixture/fakeを共通化

- [ ] `tests/fakes.py` に MockLLMClient を移動
- [ ] `tests/fixtures/factories.py` を作る
- [ ] `test_engine_integration.py` からhelperを撤去

### Step 4: unit / integration / contract へ分割

- [ ] context/storage/parser/schema/prompt/quality は unit
- [ ] fake LLM pipeline は integration
- [ ] prompt/schema/artifact layout は contract

### Step 5: 実装をテストしやすくする

- [ ] LLMTaskRunner導入
- [ ] ProjectRepository導入
- [ ] DesignWorkflow抽出
- [ ] SceneDraftWorkflow抽出
- [ ] NovelEngineはfacade delegation testへ縮小

### Step 6: 古いテストを削除

- [ ] private関数bind型テストを削除
- [ ] schema存在確認だけのテストを削除/contract testへ統合
- [ ] 重複テストを削除

---

## 8. 判定基準

テスト再構築後、以下を満たすこと。

- [ ] `uv run pytest tests -q` がgreen
- [ ] `uv run ruff check src/novel_forge tests scripts` がgreen
- [ ] `uv run python scripts/validate_prompts.py` がgreen、またはpytest contractに統合済み
- [ ] unknown schemaを使ったテストが存在しない
- [ ] `test_engine_integration.py` が300行未満、または廃止されている
- [ ] fake LLMで `plan -> design -> write -> export` が通る
- [ ] 実LLMなしでリファクタリングの主要回帰を検出できる
- [ ] 実モデルsmokeは「最後の確認」であり、通常テストの代替ではない

---

## 9. 推奨する最初の作業

最初にやるべき順序:

1. 現在の赤テストを直す。
2. `scene_review` unknown schema問題を修正する。
3. `tests/fakes.py` と `tests/fixtures/factories.py` を作る。
4. `test_engine_integration.py` を分割する。
5. prompt/schema contract を pytest に入れる。
6. その後、実装リファクタリングに入る。

この順序なら、リファクタリング前に「壊れたら検出できる土台」を作れる。
