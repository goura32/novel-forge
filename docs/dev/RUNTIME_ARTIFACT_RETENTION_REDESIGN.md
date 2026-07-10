# Runtime Configuration, Artifact Retention, and LLM Trace Redesign

最終更新: 2026-07-11

## Status

この文書は未実装の破壊的再設計仕様である。現行 runtime の動作説明ではない。既存 run データおよび既存 `config.yaml` との互換性は持たせない。

目的は次の4点である。

1. 設定ファイルをシステム上の唯一の位置へ集約する。
2. 企画・設計・執筆の task、prompt、LLM出力 schema の命名を統一する。
3. 同一作業を二重起動できないようにし、run と PID を確実に追跡する。
4. retry・改訂・再実行で成果物と LLM 送受信記録を一切上書きせず、後から差分確認できるようにする。

## Decision Summary

| 項目 | 決定 |
|---|---|
| ユーザー設定 | `${XDG_CONFIG_HOME:-~/.config}/novel-forge/config.yaml` のみ |
| 作業フォルダ | `--workdir` > `workspace.root`。未指定時はエラー |
| 工程 ID | `plan` / `design` / `write` |
| 執筆の短縮 unit 名 | `draft` / `summary`。`scene_draft` / `scene_summary` は使わない |
| task ID | `<stage>.<unit>.<operation>` |
| prompt 名 | `<stage>_<unit>_<operation>.md` |
| schema 名 | 出力データ型を表す `<stage>_<unit>.json`。review は共通 `review_issues.json` |
| prompt/schema 対応 | 名前推測を廃止し、Task Registry を唯一の正本にする |
| LLM送受信保存 | `-v` / `--verbose` の場合だけ有効 |
| thinking | request/response/summary/manifest のすべてで保存しない |
| 圧縮 | gzip を使用しない |
| retry / 再実行 | run と attempt を新規作成。既存ファイルを上書きしない |
| 進行状態 | append-only ledger を正本とし、可変 state は再生成可能 cache とする |

## Configuration

### Canonical Location

runtime が読むユーザー設定は次の1ファイルだけである。

```text
${XDG_CONFIG_HOME:-~/.config}/novel-forge/config.yaml
```

リポジトリ直下、workspace、series directory、カレントディレクトリ、親ディレクトリの `config.yaml` は探索しない。`NOVEL_FORGE_CONFIG`、任意パスを受け取る `--config` も設けない。

設定の所在が一意でなければ、再現性・調査性・エージェントによる実行判断が崩れるためである。

### Workspace Resolution

```yaml
workspace:
  root: /mnt/hdd/projects/novel-forge/runs

llm:
  model: qwen3.6:35b-a3b-mtp-q4_K_M
  ollama_host: ws1.local:11434
  timeout_seconds: 3600
  ollama_options:
    think: false

quality:
  max_generation_count: 10
  max_review_count: 3
```

`--workdir` は `Path(".")` を既定値にしてはならない。未指定を `None` として扱い、次の順で解決する。

1. CLI の `--workdir`
2. `workspace.root`
3. どちらもなければエラー

```text
作業フォルダが未設定です。
config.yaml の workspace.root または --workdir を指定してください。
```

設定の値と CLI 値の優先順位は、model、retry 回数、verbose についても一貫して CLI 優先とする。

## Task Naming and Schema Ownership

### Naming Grammar

すべての LLM task は次の3要素で識別する。

```text
<stage>.<unit>.<operation>
```

- `stage`: `plan` / `design` / `write`
- `operation`: `generate` / `review` / `revise`
- `unit`: 工程内で扱う成果物

執筆はすべて scene を対象にするため、unit に `scene_` を重ねない。長い `scene_draft` と `scene_summary` は、それぞれ `draft` と `summary` に短縮する。

### Canonical Names

| task ID | prompt | output schema |
|---|---|---|
| `plan.concept.generate` | `plan_concept_generate.md` | `plan_concept.json` |
| `plan.concept.review` | `plan_concept_review.md` | `review_issues.json` |
| `plan.concept.revise` | `plan_concept_revise.md` | `plan_concept.json` |
| `plan.characters.generate` | `plan_characters_generate.md` | `plan_characters.json` |
| `plan.characters.review` | `plan_characters_review.md` | `review_issues.json` |
| `plan.characters.revise` | `plan_characters_revise.md` | `plan_characters.json` |
| `plan.volumes.generate` | `plan_volumes_generate.md` | `plan_volumes.json` |
| `plan.volumes.review` | `plan_volumes_review.md` | `review_issues.json` |
| `plan.volumes.revise` | `plan_volumes_revise.md` | `plan_volumes.json` |
| `design.volume.generate` | `design_volume_generate.md` | `design_volume.json` |
| `design.volume.review` | `design_volume_review.md` | `review_issues.json` |
| `design.volume.revise` | `design_volume_revise.md` | `design_volume.json` |
| `design.chapter.generate` | `design_chapter_generate.md` | `design_chapter.json` |
| `design.chapter.review` | `design_chapter_review.md` | `review_issues.json` |
| `design.chapter.revise` | `design_chapter_revise.md` | `design_chapter.json` |
| `design.scene.generate` | `design_scene_generate.md` | `design_scene.json` |
| `design.scene.review` | `design_scene_review.md` | `review_issues.json` |
| `design.scene.revise` | `design_scene_revise.md` | `design_scene.json` |
| `write.draft.generate` | `write_draft_generate.md` | `write_draft.json` |
| `write.draft.review` | `write_draft_review.md` | `review_issues.json` |
| `write.draft.revise` | `write_draft_revise.md` | `write_draft.json` |
| `write.summary.generate` | `write_summary_generate.md` | `write_summary.json` |

`review_issues.json` はレビュー結果という同じデータ型を表す共通 schema である。生成と改訂は同じ完成データ型を返すため、改訂ごとの schema コピーは作らない。

### Registry

prompt 名から schema 名を推測する `_infer_schema_name()` を廃止する。task ID、prompt、schema の対応は `TaskRegistry` だけで管理する。

```python
TASKS = {
    "write.draft.generate": TaskSpec(
        prompt="write_draft_generate.md",
        schema="write_draft",
    ),
    "write.draft.revise": TaskSpec(
        prompt="write_draft_revise.md",
        schema="write_draft",
    ),
    "write.draft.review": TaskSpec(
        prompt="write_draft_review.md",
        schema="review_issues",
    ),
}
```

engine は prompt 名と schema 名を個別に指定せず task ID を指定する。これにより `scene_revision_v2.json` のような、推測実装を満たすためだけの schema コピーを不要にする。

LLM 出力 schema の正規配置は `src/novel_forge/resources/schemas/` のみとする。開発用 `schemas/` と package resource の二重管理は廃止する。

## Immutable Run and Attempt Model

### Terminology

| 用語 | 意味 |
|---|---|
| run | 1回の CLI 起動。`plan`、`write`、`complete` などが1 run |
| attempt | run 内の1つの task 実行。generation retry、review、revise、transport retry を含む |
| artifact | attempt が出力した plan/design/draft/summary/export などの不変成果物 |
| ledger | artifact の採用関係と状態遷移を追記する append-only 記録 |
| selected artifact | 後続工程が入力として採用する artifact。ledger の最新イベントで決定される |

同じ CLI をもう一度実行する場合は別 run である。同じ task の generation retry、review/revise cycle、transport retry は別 attempt として記録する。

### Layout

```text
<workspace>/
  .novel-forge/
    runs/
      run_20260711T103201Z_a42f9c/
        run.json
        events.jsonl
        logs/
          run.log
        attempts/
          att_000001_plan_concept_generate_g01_t01/
            attempt.json
            artifacts/
              plan_concept.json
            llm/
              request.json
              response.ndjson
              response.content.json
              parsed.json
              validation.json
          att_000002_plan_concept_review_r01_t01/
            attempt.json
            artifacts/
              review_issues.json
            llm/
              ...

  <series-slug>/
    .novel-forge/
      ledger/
        events.jsonl
      state-cache.json
```

- `run.json` と `attempt.json` は開始時に作成し、終了時には別の completion event を追記する。既存 JSON を更新しない。
- `events.jsonl` は run の出来事を順番に記録する。
- series の `ledger/events.jsonl` は「どの artifact を後続工程の入力に採用したか」を記録する正本である。
- `state-cache.json` は ledger から再構築できる高速化用 cache であり、履歴の正本ではない。
- `series_plan.json`、`vol01.json`、`scene_summaries.json`、`exports/<fixed-name>` のような固定成果物は廃止する。

plan 開始時は series slug が未確定である。そのため run は workspace 配下で開始し、plan 成功後に ledger へ slug と採用 artifact を記録する。run directory は移動しない。

### Non-overwrite Invariant

以下はすべて新規作成のみを許可する。

- run directory
- attempt directory
- request payload
- response transport record
- parse / validation result
- plan、design、draft、summary、review、revision、export の成果物
- error record
- ledger event

ファイル名の空き番号探索ではなく、run ID / attempt ID と `O_CREAT | O_EXCL` により競合を防ぐ。衝突した場合は別名に黙って置き換えず、ID生成の異常として失敗させる。

既存ファイルに対する `write_text()`、`replace()`、`os.rename()` での成果物置換は禁止する。原子的な一時ファイル置換が必要なのは、再生成可能な `state-cache.json` だけである。

### Retry Recording

すべての失敗経路でも attempt を残す。

| 事象 | 保存するもの |
|---|---|
| transport timeout | request、受信済み partial response、error、attempt event |
| HTTP error | request、error response / error detail、attempt event |
| JSON parse error | request、response.ndjson、response.content.json、parse error |
| schema / semantic validation error | request、response、parsed.json、validation.json |
| generation retry | retry ごとの新しい attempt directory |
| review → revise | review attempt と revise attempt を別々に保存 |
| CLI 再実行 | 新しい run directory と新しい attempt tree |

後続工程は「最新ファイル名」ではなく、ledger で selected とされた artifact reference を読む。再実行で良い結果が得られた場合も、以前の成果物を置き換えず、新しい artifact を selected とするイベントを追記するだけである。

## LLM Request / Response Capture

### Activation

LLM送受信の保存は現状どおり `-v` / `--verbose` を指定した run だけで有効にする。

```bash
novel-forge write --workdir /path/to/workspace --series example --volume 1 -v
```

`-v` なしの場合、run metadata、イベント、通常ログ、成果物は残すが、request / response body を保存しない。

### Per-attempt Files

`-v` の各 LLM attempt は次のファイルを保存する。gzip 圧縮は行わない。

| ファイル | 内容 |
|---|---|
| `attempt.json` | run ID、task ID、phase、model、seed、retry番号、開始/終了時刻、終了理由 |
| `llm/request.json` | Ollama に送信した payload |
| `llm/response.ndjson` | thinking を除去した受信 NDJSON。受信順を維持 |
| `llm/response.content.json` | `message.content` を結合した応答本文 |
| `llm/parsed.json` | parser が得た JSON 値。parse失敗時は作らない |
| `llm/validation.json` | schema / semantic validation の結果 |
| `error.json` | 例外種別、メッセージ、HTTP情報、partial response の有無 |

`response.ndjson` は「thinking 除去済み transport record」であり、受信バイト列の完全コピーとは呼ばない。thinking を保存しないという要件を優先する。

### Thinking Redaction

response をディスクへ書く前に、NDJSON の各 JSON object から次を削除する。

```text
message.thinking
thinking
```

この処理は成功、timeout、HTTP error、parse error、schema validation error のすべての保存経路で必ず通る。human-readable summary を別に作らず、`response.content.json` を人間確認用の本文とする。

## Later Comparison

履歴を残す目的は「最新だけを見る」ことではなく、retry や再実行による LLM 応答の変化を検証することである。次の read-only command を提供する。

```bash
novel-forge run show <run-id>
novel-forge attempt show <attempt-id>
novel-forge llm diff <attempt-a> <attempt-b>
novel-forge artifact diff <artifact-a> <artifact-b>
```

`llm diff` は次を出力する。

- task ID、model、seed、prompt hash、schema hash、attempt reason
- request payload の構造差分
- `response.content.json` の unified diff
- parsed JSON の構造差分
- validation 結果の変化

差分コマンドは原本を更新しない。比較結果を保存したい場合だけ `--output <new-path>` を指定し、その出力も既存ファイルがあれば失敗する。

## Run Ownership and Duplicate Start Prevention

副作用を持つ `plan`、`design`、`write`、`export`、`resume`、`complete` は Run Manager を通す。

- `plan` は workspace lock を取得する。
- plan が slug を確定した後、series lock へ移管する。
- `design`、`write`、`export`、`resume` は series lock を取得する。
- lock 保持中に同一 scope の2本目を起動した場合、既定では待機せず即時失敗する。
- `--wait-lock` を明示した場合だけ待機する。

lock は PID だけでなく、run ID、PPID、process start time、Linux boot ID、argv、phase、開始時刻、log path を JSON で保持する。PID再利用を検出できない単純な `.lock` は廃止する。

## Implementation Plan

### Phase 1: Contracts and Tests

1. `RuntimeConfig`、`TaskSpec`、`RunManifest`、`AttemptManifest`、ledger event の Pydantic model を定義する。
2. Task Registry と schema resource の存在を検証する契約テストを追加する。
3. 非上書き保存用の `ImmutableWriter` を追加し、既存パスが存在する場合は失敗するテストを追加する。
4. `-v` 有無、thinking 除去、retry 保存、run 間差分の受入テストを先に追加する。

### Phase 2: Configuration and Naming

1. 固定 config path を読む `RuntimeConfig.load()` を実装する。
2. 既存の config 探索、`NOVEL_FORGE_CONFIG`、workspace config 読み込みを削除する。
3. CLI の `--workdir` を nullable に変更し、CLI > config の解決テストを実装する。
4. prompt を新しい短縮名へ改名し、`scene_draft` / `scene_summary` を `draft` / `summary` へ置換する。
5. `_infer_schema_name()` を削除し、Task Registry から prompt/schema を取得する。
6. LLM output schema を package resource だけへ集約し、トップレベル `schemas/` を削除する。

### Phase 3: Immutable Repository and Ledger

1. workspace run directory と series ledger directory を作る `RunRepository` を実装する。
2. run / attempt 開始、成功、失敗、artifact selection の event を append-only で記録する。
3. `state.json` を正本として読むコードを、ledger を読む `ArtifactRepository` へ置換する。
4. plan、design、write、export の固定パス保存を artifact reference 保存へ置換する。
5. export は selected draft artifact を読み、出力自体も attempt artifact として保存する。

### Phase 4: LLM Capture

1. `LLMClient` の raw logger を attempt-scoped writer へ置換する。
2. `-v` の場合だけ request / sanitized response / parsed / validation を保存する。
3. gzip、summary.md、summary directory、既存 `_raw_logs/` を廃止する。
4. すべての例外経路で `error.json` と partial response を残す。
5. response write 前の thinking redaction を共通関数化し、漏れをテストする。

### Phase 5: Run Manager and CLI

1. JSON lock、PID identity 検証、stale lock recovery を実装する。
2. 全副作用コマンドを Run Manager でラップし、`complete` と `plan` を含める。
3. `runs active`、`run show`、`attempt show`、`llm diff`、`artifact diff` を追加する。
4. lock が競合した場合の fail-fast 出力と `--wait-lock` を実装する。

### Phase 6: Documentation and Removal

1. `USER_GUIDE.md`、`CLI_REFERENCE.md`、`OPERATIONS.md`、`RAW_LOG_FORMAT.md`、`PROMPT_SCHEMA_MAP.md` を新仕様へ更新する。
2. `PROMPT_SCHEMA_MAP.md` は Task Registry から生成する。
3. 旧 config、旧 schema directory、旧 `_raw_logs/`、旧 `.lock`、固定成果物パス前提の文書とテストを削除する。
4. 互換レイヤー・自動移行・旧 run の読み込みは実装しない。旧 run は Git または filesystem のアーカイブとして残すだけとする。

## Acceptance Criteria

| 条件 | 合格基準 |
|---|---|
| 命名 | `write_scene_draft_*` / `write_scene_summary_*` / `*_v2` が正規 task resource に存在しない |
| config | runtime が固定 config path 以外を探索しない |
| CLI優先 | `--workdir` が `workspace.root` より優先される |
| retry保全 | generation retry、review、revise、transport retry の各 artifact が別 attempt directory に残る |
| 再実行保全 | 同一 command を2回実行しても1回目の request、response、artifact の hash が変化しない |
| `-v` | request / sanitized response / parsed / validation が attempt ごとに保存される |
| 非verbose | request / response body が保存されない |
| thinking | 保存された全 JSON / NDJSON に `thinking` キーが存在しない |
| gzip | run / attempt directory に `.gz` が存在しない |
| 比較 | 同一 task の2 attempt を `llm diff` で比較でき、元ファイルは更新されない |
| 二重起動 | 同一 scope の2本目が即時失敗し、既存 run ID / PID / log path を表示する |
| stale lock | PID再利用を process start time と boot ID で検出し、誤削除しない |

## Non-goals

- 過去 run の自動移行
- 過去 `state.json`、固定設計 JSON、`_raw_logs/` の読込互換
- LLM review の合否を自動的に正解化すること
- thinking の保存を許可する設定
