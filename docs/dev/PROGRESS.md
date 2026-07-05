# NovelForge Improvement Progress

最終更新: 2026-07-05
対象: `/mnt/hdd/projects/novel-forge`

## 0. 運用ルール

- このファイルを進捗の正とする。
- 作業は `MASTER_IMPROVEMENT_PLAN.md` → `PROGRESS.md` → 実装/テスト/ドキュメントで進む。

## 1. 現在の baseline

| 項目 | 状態 |
|---|---|
| pytest | 236 passed |
| ruff | All checks passed |
| prompt validator | All placeholders consistent |
| docs link check | broken link 0件 |

## 2. Phase 4 — ドキュメント再構成（完了）

| ID | Task | Status | メモ |
|---|---|---:|---|
| P4-01 | `docs/INDEX.md` を作る | Done | ユーザー/開発者/運用向け案内を作成 |
| P4-02 | README を利用者向け入口へ縮小 | Done | 80行→69行。CLI例の同期、アーキテクチャ詳細を dev docs へ分離 |
| P4-03 | `docs/USER_GUIDE.md` を作る | Done | セットアップ / クイックスタート / コマンド一覧付き (41行) |
| P4-04 | `docs/CLI_REFERENCE.md` を作る | Done | plan/design/write/export/complete/resume/status/doctor/list の8コマンド同期 (123行) |
| P4-05 | `docs/OPERATIONS.md` を作る | Done | Ollama/connectivity, lock, validation error, prompt placeholder mismatch 対応 (117行) |

## 3. Phase 5 — テスト・検証の同期（完了）

| ID | Task | Status | メモ |
|---|---|---:|---|
| P5-01 | pytest baseline の維持 | Done | `uv run pytest tests -q` → 236 passed |
| P5-02 | ruff green の維持 | Done | `uv run ruff check src/novel_forge tests scripts` → OK |
| P5-03 | prompt placeholder validator green | Done | `validate_prompts.py` → 0 issues |

## 4. Phase 6 — プロンプト/schema品質（完了）

| ID | Task | Status | メモ |
|---|---|---:|---|
| P6-01 | review.json の publication readiness 拡張 | Done | `ready_for_publication`, `strengths`, `overall_assessment` を追加 |
| P6-02 | scene_design.json の本文品質用フィールド追加 | Done | hook, turning_point, emotional_arc, ending_hook 等 |
| P6-03 | chapter_design.json の章機能用フィールド追加 | Done | chapter_turning_point, chapter_hook, foreshadowing_notes 等 |
| P6-04 | scene_draft.md に本文品質要件を追加 | Done | 冒頭hook/show dont tell/pov/台詞/感覚描写/メタ説明禁止 |
| P6-05 | validate_prompts.py の validator を AST ベースに更新 | Done | placeholder 検証が安定化 |

## 5. Phase 7 — リポジトリ衛生（完了）

| ID | Task | Status | メモ |
|---|---|---:|---|
| P7-01 | .gitignore に生成物/キャッシュ/log を追加 | Done | `.pytest_cache/`, `.ruff_cache/`, `*.log`, `series_*/` 等 |
| P7-02 | generated artifacts が Git管理外である確認 | Done | `git status --short` で意図した差分のみ |

## 6. Phase 8 — テスト再構築の土台（完了）

| ID | Task | Status | メモ |
|---|---|---:|---|
| P8-01 | `tests/fakes.py` を作成 | Done | MockLLMClient を抽出 |
| P8-02 | `tests/fixtures/factories.py` を作成 | Done | series/volume schema 用 valid fixture |
| P8-03 | `tests/contract/test_prompt_schema_contract.py` を新規追加 | Done | prompt/schema contract smoke test |
| P8-04 | `tests/unit/` テストディレクトリを作成 | Done | llm_task, repository, workflows の各単体テスト |
| P8-05 | schema 拡張 fixture と tests/test_schemas_extended.py を更新 | Done | review.chapter_scene_design schema 対応 |

...[truncated]