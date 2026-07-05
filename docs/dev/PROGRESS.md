# NovelForge Improvement Progress

最終更新: 2026-07-05
対象: `/mnt/hdd/projects/novel-forge`

## 0. 運用ルール

- このファイルを進捗の正とする。
- 作業は `MASTER_IMPROVEMENT_PLAN.md` → `PROGRESS.md` → 実装/テスト/ドキュメントで進む。
- 変更後は `pytest` / `ruff` / prompt validator / 必要に応じて `uv build` を確認する。

## 1. 現在の baseline

| 項目 | 状態 |
|---|---|
| pytest | `uv run pytest tests -q` → 264 passed |
| ruff | `uv run ruff check src/novel_forge tests scripts` → All checks passed |
| prompt validator | `uv run python scripts/validate_prompts.py` → All placeholders consistent |
| wheel resources | `uv build` wheel に prompts 25件 / schemas 15件を同梱 |
| runtime wheel smoke | wheel install後 `validate_schemas()` / `PromptManager().render()` OK |

## 2. Phase 4 — ドキュメント再構成（完了）

| ID | Task | Status | メモ |
|---|---|---:|---|
| P4-01 | `docs/INDEX.md` を作る | Done | ユーザー/開発者/運用向け案内を作成 |
| P4-02 | README を利用者向け入口へ縮小 | Done | CLI例の同期、アーキテクチャ詳細を dev docs へ分離 |
| P4-03 | `docs/USER_GUIDE.md` を作る | Done | セットアップ / クイックスタート / コマンド一覧付き |
| P4-04 | `docs/CLI_REFERENCE.md` を作る | Done | plan/design/write/export/complete/resume/status/doctor/list を同期 |
| P4-05 | `docs/OPERATIONS.md` を作る | Done | Ollama/connectivity, lock, validation error, prompt placeholder mismatch 対応 |

## 3. Phase 5 — テスト・検証の同期（完了）

| ID | Task | Status | メモ |
|---|---|---:|---|
| P5-01 | pytest baseline の維持 | Done | 252 passed |
| P5-02 | ruff green の維持 | Done | All checks passed |
| P5-03 | prompt placeholder validator green | Done | 0 issues |

## 4. Phase 6 — プロンプト/schema品質（完了）

| ID | Task | Status | メモ |
|---|---|---:|---|
| P6-01 | review.json の publication readiness 拡張 | Done | `ready_for_publication`, `strengths`, `overall_assessment` を追加 |
| P6-02 | scene_design.json の本文品質用フィールド追加 | Done | hook, turning_point, emotional_arc, ending_hook 等 |
| P6-03 | chapter_design.json の章機能用フィールド追加 | Done | chapter_turning_point, chapter_hook, foreshadowing_notes 等 |
| P6-04 | scene_draft.md に本文品質要件を追加 | Done | 冒頭hook/show don't tell/pov/台詞/感覚描写/メタ説明禁止 |
| P6-05 | validate_prompts.py の validator を AST ベースに更新 | Done | placeholder 検証が安定化 |

## 5. Phase 7 — リポジトリ衛生（完了）

| ID | Task | Status | メモ |
|---|---|---:|---|
| P7-01 | .gitignore に生成物/キャッシュ/log を追加 | Done | `.pytest_cache/`, `.ruff_cache/`, `.mypy_cache/`, `*.log`, `series_*/` 等 |
| P7-02 | generated artifacts が Git管理外である確認 | Done | tracked generated artifacts を index から除外 |

## 6. Phase 8 — テスト再構築の土台（完了）

| ID | Task | Status | メモ |
|---|---|---:|---|
| P8-01 | `tests/fakes.py` を作成 | Done | MockLLMClient を抽出 |
| P8-02 | `tests/fixtures/factories.py` を作成 | Done | series/volume schema 用 valid fixture |
| P8-03 | `tests/contract/test_prompt_schema_contract.py` を追加 | Done | prompt/schema contract smoke test |
| P8-04 | `tests/unit/` テストディレクトリを作成 | Done | llm_task, repository, workflows の各単体テスト |
| P8-05 | schema 拡張 fixture と tests/test_schemas_extended.py を更新 | Done | review/chapter/scene design schema 対応 |

## 7. Phase 9 — 非同期レビュー結果のP0/P1修正（完了）

| ID | Task | Status | メモ |
|---|---|---:|---|
| P9-01 | wheel配布時の prompts/schemas 欠落を修正 | Done | package resources に prompts 25件 / schemas 15件を同梱、runtime smoke OK |
| P9-02 | `--series` と repository write の path traversal を拒否 | Done | `../` / absolute path escape を ValueError |
| P9-03 | `complete` 失敗時の AssertionError 上書きを修正 | Done | 元の phase error を保持し、成功時のみ Complete 表示 |
| P9-04 | `企画済` state の roundtrip と resume 判定を修正 | Done | `ProjectState.status` と resume action を同期 |
| P9-05 | revision prompt に対象schemaを注入 | Done | `*_revision.md` は review schema ではなく target schema を提示 |
| P9-06 | scene review kind を統一 review schema に合わせる | Done | `scene_review` kind ではなく `review` kind で検証 |
| P9-07 | Bible semantic alias を修正 | Done | subplot `完了`, foreshadowing `回収`, relationship `type` を正しく反映 |
| P9-08 | design の章番号0化と巻タイトル上書きを修正 | Done | chapter index fallback と LLM生成 title を保持 |
| P9-09 | CLI docs / operations docs の実CLI不整合を修正 | Done | `doctor --workdir` 削除、export出力名を実装に同期 |

## 8. Phase 10 — write リカバリ + export preflight（完了）

| ID | Task | Status | メモ |
|---|---|---:|---|
| P10-01 | write 中にシーン単位で `_save()` を呼ぶ | Done | crash recovery で未処理シーンから再開 |
| P10-02 | export 前に scene draft 存在/空チェック | Done | design上の全scene artifactを検証し、不完全/空原稿のKDP出力を拒否 |
| P10-03 | write resume / export preflight のテストを追加 | Done | `tests/test_write_resume_export_preflight.py` |
| P10-04 | plan後のfinal series dir再バインド | Done | temp dirに書き続ける不整合を修正 |

## 9. Phase 11 — schema strictness + semantic validators（完了）

| ID | Task | Status | メモ |
|---|---|---:|---|
| P11-01 | 全 object に `additionalProperties: false` を追加 | Done | 15 schema / packaged resourcesを同期し、未知fieldを拒否するcontract testを追加 |
| P11-02 | required fields に `minLength` / `minItems` を追加 | Done | 全stringの空文字を拒否し、重要arrayにminItemsを追加。空配列が意味を持つ更新系は例外化 |
| P11-03 | duplicate chapter/scene number などの semantic validator を追加 | Done | final volume design の重複番号・章/scene参照不整合を検出し、export preflightへ統合 |

## 10. Phase 12 — mypy burn-down（完了）

| ID | Task | Status | メモ |
|---|---|---:|---|
| P12-01 | `generate_and_review()` 戻り値の型を固定 | Done | `tuple[dict, dict]` を明示 unpack し、design path の型誤推論を解消 |
| P12-02 | mypy errors 49 → 0 を達成 | Done | `uv run mypy src/novel_forge tests --show-error-codes` → no issues |

## 11. Phase 13 — ローカル品質ゲート + config example（完了）

| ID | Task | Status | メモ |
|---|---|---:|---|
| P13-01 | 開発用ローカル品質ゲートを追加 | Done | `scripts/check_dev_quality.py` で pytest / ruff / mypy / prompt validator を一括実行、`--full` で `uv build` も実行 |
| P13-02 | `config.example.yaml` を追加 | Done | ローカル設定例を追加し README / OPERATIONS から案内 |
| P13-03 | pytest設定を明文化 | Done | `testpaths` と unit/integration/contract/real_model marker を `pyproject.toml` に追加 |

## 12. Phase 14 — 実モデル plan smoke / prompt hardening（完了）

| ID | Task | Status | メモ |
|---|---|---:|---|
| P14-01 | 実モデル `plan` smoke を実行 | Done | `uv run novel-forge plan -w smoke_workspace --raw-log --max-generation-count 2 --max-review-count 1 ...` |
| P14-02 | `series_plan_volumes.cliffhanger` 空文字対策 | Done | 最終巻も余韻・未来へのフックとして非空出力を要求 |
| P14-03 | `series_plan_characters_revision` の schema echo / 空配列対策 | Done | 既存人数維持、`main_characters` 配列、実データのみ出力、`arc`維持を明示 |
| P14-04 | 契約テスト追加 | Done | prompt品質契約で上記退行を固定 |
| P14-05 | smoke結果確認 | Done | `characters=3`, `volumes=4`, empty cliffhangersなし |

## 13. Phase 15 — raw log human summary 見直し（完了）

| ID | Task | Status | メモ |
|---|---|---:|---|
| P15-01 | 人間向けsummary仕様を点検 | Done | 旧 `raw_summary.md` は名称・重複・分割性が弱く、thinking除外も契約テストなし |
| P15-02 | summary構成を整理 | Done | `summary.md` を索引、`summary/request_*.md` / `summary/response_*.md` を詳細Markdown、`details/*.json.gz` を完全rawに分離 |
| P15-03 | response summaryからthinking/transport metadataを除外 | Done | Ollama NDJSON は `message.content` のみ連結しJSON整形。thinkingはgzip rawのみ |
| P15-04 | 重複rawを削除 | Done | 成功responseは `details/response_0_0.json.gz` に統一し、旧 `response.json.gz` を出さない |
| P15-05 | 実CLI smoke確認 | Done | `--raw-log` plan成功。missingなし、`response.json.gz`なし、summary内thinkingなし |

## 14. Phase 16 — config.yaml 省略時の既定値精査（完了）

| ID | Task | Status | メモ |
|---|---|---:|---|
| P16-01 | config探索順を明確化 | Done | `CLI > NOVEL_FORGE_CONFIG > --workdir/config.yaml > cwd親探索 > built-in` に統一 |
| P16-02 | CLI省略時のconfig上書きバグ修正 | Done | `--model`, `--verbose`, `--raw-log`, retry countが未指定なら `None` としてengine側で解決 |
| P16-03 | configなしbuilt-in既定値を精査 | Done | quality built-in を `max_generation_count=3`, `max_review_count=8` に調整 |
| P16-04 | doctorのconfig対応 | Done | `doctor -w <dir>` で `<dir>/config.yaml` の model/ollama_host を使用 |
| P16-05 | 契約テストとdocs同期 | Done | missing config / workdir config / CLI override / env precedence をテスト化 |
