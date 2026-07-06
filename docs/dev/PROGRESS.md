# NovelForge Improvement Progress

最終更新: 2026-07-06
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


## 14. Phase 16 — config.yaml 省略時の既定値精査（完了）

| ID | Task | Status | メモ |
|---|---|---:|---|
| P16-01 | config探索順を明確化 | Done | `CLI > NOVEL_FORGE_CONFIG > --workdir/config.yaml > cwd親探索 > built-in` に統一 |

| P16-03 | configなしbuilt-in既定値を精査 | Done | quality built-in を `max_generation_count=3`, `max_review_count=8` に調整 |
| P16-04 | doctorのconfig対応 | Done | `doctor -w <dir>` で `<dir>/config.yaml` の model/ollama_host を使用 |
| P16-05 | 契約テストとdocs同期 | Done | missing config / workdir config / CLI override / env precedence をテスト化 |

## 15. Phase 17 — retry責務分離（完了）

| ID | Task | Status | メモ |
|---|---|---:|---|
| P17-01 | LLM内retryをtransport限定化 | Done | `transport_retries` は timeout / HTTP error など一時的API失敗のみ再試行 |
| P17-02 | JSON/schema出力不備を工程retryへ移管 | Done | parse / schema / schema echo は `LLMError` として上位へ返し、`max_generation_count` が制御 |
| P17-03 | config互換性維持 | Done | `llm.transport_retries` を主名化。旧 `llm.max_retries` は alias として読める |
| P17-04 | 契約テスト追加 | Done | generation counter retry、transport retry、旧alias互換をテスト化 |

## 16. Phase 18 — prompt/schema/fallback hardening（進行中）

| ID | Task | Status | メモ |
|---|---|---:|---|
| P18-01 | prompt template を `system.md` 以外で統一構成へ整理 | Done | `目的/応答方針/実行指示/入力情報/出力仕様` に統一。editable prompts と packaged resources を同期 |
| P18-02 | review prompt と `review.json` の publication readiness を同期 | Done | `ready_for_publication`, `overall_assessment`, `strengths`, `publication_blocking` の判断規則を明示 |
| P18-03 | scene draft の本文品質制約を強化 | Done | 完成本文のみ、2000〜5000字、常体、Show Don't Tell、POV、感覚描写、メタ説明禁止を契約化 |
| P18-04 | 生成系 prompt の必須フィールド説明を補強 | Done | `chapter_turning_point`, `hook`, `world_rules`, `main_characters[]`, `planned_volumes[]`, `chapters[]`, KDP metadata, cover prompt を補強 |
| P18-05 | `scene_summary_and_bible_update` schema を簡素化 | Done | `world_rules` を `string[]` に統一。`facts[].object` は任意化。legacy `{rule: ...}` は reader 側で後方互換維持 |
| P18-06 | fallback/logging を監査し不適切な無言fallbackを修正 | Done | unknown schema は fail-fast。破損state/config/registry復旧は warning。schema補正ログも warning 化 |
| P18-07 | 契約テスト・回帰テストを追加/更新 | Done | prompt品質契約、schema契約、bible manager、json parser、storage、name registry 等を更新 |
| P18-08 | ローカル品質ゲートを通す | Done | `uv run pytest` → 288 passed。`git diff --check` OK。`uv run ruff check src tests` → All checks passed |
| P18-09 | hardening 差分を commit/push | Done | commit `7867b9e` を `origin/main` へ push 済み。remote SHA `7867b9eb7174f2241393f7c5adf931506b2f2e66` |
| P18-10 | 実LLM smoke を1シリーズで実行 | Blocked | 1回目 `workspace/phase18_real_smoke_20260706_110407`: JSON parse retry 後、review要修正で `max-review-count=1` 到達。2回目 `workspace/phase18_real_smoke_20260706_110924`: revision後も `publication_blocking=false` の重要issueだけで `ready_for_publication=false` になり停止。原因は review readiness が severity と blocking を混同していたこと |
| P18-11 | smoke結果から schema簡素化/ prompt微修正の要否を判断 | Done | 実LLMログから、schema複雑度ではなく review readiness 判定の設計不整合と判断。P18-12で修正 |
| P18-12 | review readiness を publication_blocking ベースへ修正 | Done | `ready_for_publication=false` は `publication_blocking=true` issue がある場合のみ。`severity=重要` でも非ブロッキングなら ready=true を許可。prompt/schema/validator/tests/docs/resources を同期済み。`uv run pytest` → 289 passed、resource sync OK、ruff OK |
| P18-13 | 実LLM smoke を再実行 | Blocked | `workspace/phase18_real_smoke_20260706_112546`: 1回目 review の `intent` 英語混入 blocking は妥当。revision後、2回目 review が「サイバーパンク読者と静謐トーンのミスマッチ」という主観的ターゲット指摘を `publication_blocking=true` にして停止 |
| P18-14 | review blocking 基準を狭める | Done | blocking は必須フィールド欠落、後続工程が使えない矛盾、不自然な言語混入、明確な設定破綻などに限定。ジャンル整理/ターゲット精度/比較作品の好み/売り文句の磨き込みは原則 non-blocking。`uv run pytest` → 289 passed、resource sync OK、ruff OK |
| P18-15 | 実LLM smoke を再々実行 | Blocked | `workspace/phase18_real_smoke_20260706_112948`: review JSON は `ready_for_publication=true` + non-blocking issue の状態まで到達したが、engine review loop 本体がまだ severity ベースで `重要` issue を revision対象にして停止 |
| P18-16 | engine review loop を `publication_blocking` ベースへ修正 | Done | `_blocking_issues()` を追加し、初回/post-revision review とも `publication_blocking=true` のみ revision対象に変更。review validation error 注入issueにも `publication_blocking=true` を付与。回帰テスト追加。`uv run pytest` → 291 passed、ruff OK |
| P18-17 | 実LLM smoke を再々々実行 | Blocked | `workspace/phase18_real_smoke_20260706_113505`: Plan完了、Design `volume_design` 完了、`chapter_design` review で `ready_for_publication=false` だが `publication_blocking=true` issueなしの schema validation error で停止 |
| P18-18 | LLM client の invalid generation retry と schema validation を修正 | Done | JSON parse/schema echo/schema validation を generation retry 対象に変更。`complete_json(..., schema)` が渡された schema ではなく kind名schemaを読み直していた不整合も `validate_data_or_raise` 追加で修正。`uv run pytest` → 292 passed、ruff OK |
| P18-19 | 実LLM smoke を5回目実行 | Blocked | `workspace/phase18_real_smoke_20260706_114505`: Plan完了、invalid generation retry は実動確認済み。Design `volume_design` が6章→8章まで改訂後、2回目reviewで「10章程度へ拡張」が blocking となり `--max-review-count 2` 到達。クラッシュではなく通常品質ループ未収束 |
| P18-20 | 実LLM smoke を max-review-count 4 で実行 | Blocked | `workspace/phase18_real_smoke_20260706_115144`: Plan完了、Design `chapter_design` まで到達。review retryは効いたが、2回目reviewが `ready_for_publication=true` + `publication_blocking=true` issue で schema contradiction となり停止 |
| P18-21 | review 出力の readiness 正規化 | Done | LLM review出力で各issueの `publication_blocking` 欠落をfalse補完し、`ready_for_publication = not any(publication_blocking)` に再計算。contradictionだけで落ちず、実際のblocking issueは改訂ループへ流す。`uv run pytest` → 294 passed、ruff OK |
| P18-22 | 実LLM smoke を6回目実行 | Blocked | `workspace/phase18_real_smoke_20260706_120430`: Design `chapter_design` で `purpose` enum に `導入：...` のような説明文が付いて schema validation error。retry後も同種で停止 |
| P18-23 | enum prefix 正規化を追加 | Done | `purpose` 等の enum 値が `導入：説明` のように許容enum+区切り文字で始まる場合、先頭enumへ丸める。`uv run pytest` → 295 passed、ruff OK |
| P18-24 | 実LLM smoke を7回目実行 | Blocked | `workspace/phase18_real_smoke_20260706_121701`: Plan完了、Design `volume_design` で4回改訂後、最終reviewが既に修正済みの `齿轮`→`歯車` を stale blocking issue として返し停止 |
| P18-25 | stale resolved review issue 除外 | Done | `before` が現在JSONになく `after` が現在JSONにある issue は解決済みとして除外し、残issueから readiness を再計算。`uv run pytest` → 296 passed、ruff OK |
| P18-26 | 実LLM smoke を8回目実行 | Blocked | `workspace/phase18_real_smoke_20260706_122949`: Plan突破、Design `chapter_design` まで到達。`purpose` が enum ではなく詳細文のみになり schema validation error。enum prefixでは回復不能 |
| P18-27 | chapter_design purpose を入力章のpurposeで上書き | Reverted | 不適切修正と判定。P18-28で、LLM改訂が `purpose=展開` に直した後、engineが `volume_design.chapters[].purpose=クライマックス` へ戻し、reviewが同じblocking issueを出し続けた |
| P18-28 | 実LLM smoke を9回目実行 | Blocked | `workspace/phase18_real_smoke_20260706_124753`: Design `chapter_design` reviewで4回改訂後も停止。最終raw outputは `purpose=展開` だったが、review requestには `purpose=クライマックス` と渡っていた |
| P18-29 | chapter_design final raw/review確認 | Done | `_raw_logs/.../0028_chapter_design/summary/response_0_2.md` と `0029_review` を確認。schema違反でもenum prefix問題でもなく、engine-side purpose上書きによる判定ループと確定 |
| P18-30 | P18-27の不適切修正を復帰 | Done | `src/novel_forge/engine/design.py` から chapter purpose 強制上書きを削除。LLM/改訂結果の valid enum を保持する回帰テスト `test_chapter_design_keeps_revised_purpose` を追加。`uv run pytest` → 297 passed、`git diff --check` OK、ruff OK |
| P18-31 | 実LLM smoke を10回目実行 | Blocked | `workspace/phase18_real_smoke_20260706_143122`: P18-30復帰後、Plan完了→Design `chapter_design` まで進行。P18-28のpurpose上書きループは解消したが、review issue の欠落差分で `before=""` が出て schema validation error で停止 |
| P18-32 | review.before 空文字許可 | Done | review prompts は「欠落フィールドの `before` は空文字列」と指示していたが schema が `minLength=1` で拒否していた。`before` のみ空文字を許可し、`after` 非空は維持。`uv run pytest` → 299 passed、`git diff --check` OK、ruff OK |
| P18-33 | 実LLM smoke を11回目実行 | Blocked | `workspace/phase18_real_smoke_20260706_144911`: Plan完了→Design `chapter_design`。P18-31のreview.before schema issueは解消。別章で `purpose` が enum ではなく説明文になり、2回retry後も schema validation error で停止 |
| P18-34 | invalid chapter purpose のみ入力章purposeへ補正 | Done | P18-27の常時上書きは再導入せず、`chapter_design.purpose` が schema enum 外のときだけ `volume_design.chapters[].purpose` のvalid enumで補正。valid enum改訂結果は保持。`uv run pytest` → 300 passed、`git diff --check` OK、ruff OK |
| P18-35 | 実LLM smoke を12回目実行 | Blocked | `workspace/phase18_real_smoke_20260706_150209`: P18-34のinvalid purpose修正後に再実行。Plan完了→Design `volume_design` で停止。`volume_design.title` が上流series_planの「無音の刻鐘と錆びた鍵」から「時計台の鍵と記憶の欠片」へ逸れ、reviewがタイトル不一致をblockingとして出し続けた |
| P18-36 | volume_design title を上流planned volume titleへ固定 | Done | `series_plan.planned_volumes[vol-1].title` を source of truth とし、volume_design生成/改訂後に `title` を固定。reviewへ渡る前に正規化するためタイトル不一致ループを防止。`uv run pytest` → 301 passed、`git diff --check` OK、ruff OK |
| P18-37 | 実LLM smoke を13回目実行 | Todo | P18-36 commit/push後、同条件で再実行してDesign通過/Write到達を確認する |

### Phase 18 復帰メモ

- 現在の正: この `PROGRESS.md`。中断復帰時は P18-37 以降から再開する。
- 直近検証済みコマンド:
  - `uv run pytest tests/test_engine_integration.py::TestOutline::test_outline_creates_outline tests/test_engine_integration.py::TestOutline::test_volume_design_title_uses_series_plan_title tests/test_engine_integration.py::TestOutline::test_chapter_design_keeps_revised_purpose tests/test_engine_integration.py::TestOutline::test_chapter_design_repairs_invalid_purpose_from_volume_design -q` → 4 passed
  - `uv run pytest tests/test_engine_integration.py -q` → 45 passed
  - `uv run pytest` → 301 passed
  - `git diff --check` → OK
  - `uv run ruff check src tests` → OK

- 次に迷わず実行すること:
  1. P18-36を commit/push
  2. P18-37 smokeを `--max-generation-count 3 --max-review-count 4 --verbose` で実行
  3. Design通過とWrite到達を確認。失敗時は raw log の `review` と `revision` を読み、schema簡素化/判定ルール修正/プロンプト微修正/engine判定修正のどれかに分類
