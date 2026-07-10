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
| ユーザー設定 | `~/.config/novel-forge/config.yaml` のみ |
| 作業フォルダ | `--workdir` > `workspace.root`。未指定時はエラー |
| summary | 最終 draft から LLM が生成・レビュー・改訂する continuity handoff |
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
~/.config/novel-forge/config.yaml
```

`XDG_CONFIG_HOME` は参照しない。起動環境ごとに config path が変わる余地をなくし、同一OSユーザーにつき設定の所在を一意にする。リポジトリ直下、workspace、series directory、カレントディレクトリ、親ディレクトリの `config.yaml` は探索しない。`NOVEL_FORGE_CONFIG`、任意パスを受け取る `--config` も設けない。

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
  max_summary_review_count: 2
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
| `write.summary.review` | `write_summary_review.md` | `review_issues.json` |
| `write.summary.revise` | `write_summary_revise.md` | `write_summary.json` |

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
    "write.summary.generate": TaskSpec(
        prompt="write_summary_generate.md",
        schema="write_summary",
    ),
    "write.summary.review": TaskSpec(
        prompt="write_summary_review.md",
        schema="review_issues",
    ),
    "write.summary.revise": TaskSpec(
        prompt="write_summary_revise.md",
        schema="write_summary",
    ),
}
```

engine は prompt 名と schema 名を個別に指定せず task ID を指定する。これにより `scene_revision_v2.json` のような、推測実装を満たすためだけの schema コピーを不要にする。

LLM 出力 schema の正規配置は `src/novel_forge/resources/schemas/` のみとする。開発用 `schemas/` と package resource の二重管理は廃止する。

## High-quality LLM Summary

### Role and Boundary

summary は本文の先頭を切り出した文字列ではない。最終採用された draft を、次の scene の writer が安全かつ正確に引き継ぐための **continuity handoff** である。

summary の生成・レビュー・改訂はすべて LLM task とする。ただし reader ではなく writer-side artifact であり、Canon 原本、Canon event log、author-only truth、stable ID を渡してはならない。入力は次だけに限定する。

1. final selected `write.draft` artifact の本文（唯一の事実源）
2. 同一 scene の `SceneDesign.writer_context` と scene brief（POV-safe な名前・設定表現の補助）
3. summary revise 時は candidate summary と review issues

scene design と draft が食い違う場合、summary は draft に書かれた事実を優先する。summary task は design に合わせて本文の事実を補正・補完してはならない。design との乖離は別の draft review / semantic validation で扱う。

summary が前 scene の要約を入力として読む必要はない。現 scene の final draft を独立した唯一の事実源として要約し、連続性に必要な現在状態と未解決事項を出力する。これにより、過去 summary の誤りを次の summary へ連鎖させない。

### Task Flow

```text
final selected draft
  → write.summary.generate
  → write.summary.review
  → write.summary.revise（issues がある場合のみ）
  → final selected summary
```

- summary generate は final draft の確定後にのみ実行する。
- summary review は draft を根拠に、事実誤認、推測、重要な状態変化の脱落、次 scene への誤誘導だけを issue として返す。
- summary revise は draft、candidate summary、review issues のみを入力とし、本文にない事実を追加しない。
- summary review の retry 上限は `quality.max_summary_review_count` とする。上限に達した場合も、最後の summary と最後の review artifact を保存し、人間確認用に選択状態へ明示する。

### `write_summary.json` Contract

schema は以下の役割を持つ。各文字列の長さを機械的に縛るのではなく、field description で「本文から直接確認できる事実だけ」「次の writer が使える具体性」を要求する。

```json
{
  "summary": "scene の因果・転換・結果を、本文の事実だけで連続した日本語として記録する",
  "end_state": {
    "pov": "scene 終了時点で本文から確認できる POV 人物の位置・状態・当面の目的",
    "setting": "終了地点と時間的状況。本文に根拠がある場合のみ記録する"
  },
  "character_changes": [
    {
      "character": "本文に登場した表示名",
      "change": "scene 内で確認できる状態・認識・関係の変化",
      "evidence": "変化を裏付ける本文の短い引用または出来事"
    }
  ],
  "world_or_item_changes": [
    {
      "subject": "人物・場所・物品などの表示名",
      "change": "本文で確定した状態変化",
      "evidence": "根拠となる本文上の出来事"
    }
  ],
  "unresolved_threads": [
    {
      "thread": "本文で明示された未解決の疑問・脅威・約束・期限",
      "why_it_matters": "次 scene で保持すべき理由",
      "evidence": "根拠となる本文上の出来事"
    }
  ],
  "next_scene_handoff": [
    "次の writer が矛盾なく継続するために守るべき、本文に根拠のある状態・制約・直後の課題"
  ],
  "facts": [
    {
      "subject": "本文に登場する表示名",
      "predicate": "本文から直接読める行為または関係",
      "object": "対象または結果。対象がない事実では空文字を許可する",
      "evidence": "根拠となる本文上の出来事"
    }
  ]
}
```

`evidence` は summary review と人間確認に使う。次の draft prompt へ渡すのは、`summary`、`end_state`、`character_changes`、`world_or_item_changes`、`unresolved_threads`、`next_scene_handoff` のみであり、`evidence` と `facts` の全文は渡さない。これにより、writer の文脈を必要以上に肥大化させない。

### Summary Artifact References

summary artifact は少なくとも次を manifest に記録する。

```json
{
  "logical_key": "write.vol01.ch02.sc03.summary",
  "source_draft_artifact_id": "art_...",
  "scene_design_artifact_id": "art_...",
  "summary_review_artifact_id": "art_...",
  "summary_quality_status": "passed | review_limit_reached | review_error"
}
```

後続 scene の writer は、直前 scene の selected summary artifact をこの logical key で取得する。ファイル名の新旧や時刻順で選んではならない。

## Immutable Run and Attempt Model

### Terminology

| 用語 | 意味 |
|---|---|
| run | 1回の CLI 起動。`plan`、`write`、`complete` などが1 run |
| attempt | run 内の1つの task 実行。generation retry、review、revise、transport retry を含む |
| artifact | attempt が出力した plan/design/draft/summary/export などの不変成果物 |
| artifact manifest | artifact ID、logical key、content digest、入力 artifact IDs、schema/prompt digest を固定する不変メタデータ |
| ledger | artifact の採用関係と状態遷移を追記する append-only 記録 |
| selection snapshot | 複数 logical key の selected artifact を一つの入力集合として固定した immutable snapshot |

同じ CLI をもう一度実行する場合は別 run である。同じ task の generation retry、review/revise cycle、transport retry は別 attempt として記録する。

後続工程は単一 artifact の「最新時刻」を読まない。run 開始時に immutable `selection snapshot` を作り、その snapshot に記録された logical key → artifact ID の組だけを入力にする。たとえば export snapshot は plan、volume design、Canon revision、全 scene の draft、summary、final review artifact を同時に固定する。

```json
{
  "selection_snapshot_id": "sel_...",
  "base_snapshot_id": "sel_...",
  "slots": {
    "plan.series": "art_...",
    "design.vol01": "art_...",
    "write.vol01.ch02.sc03.draft": "art_...",
    "write.vol01.ch02.sc03.summary": "art_...",
    "write.vol01.ch02.sc03.final_review": "art_...",
    "canon.event_set": "art_..."
  },
  "slots_digest": "sha256:..."
}
```

candidate artifact は validation 成功後も自動的に selected にならない。`artifact.selected` event が logical key、candidate artifact ID、previous artifact ID、base snapshot ID、選択理由を持って初めて後続入力へ採用される。export は自身の input snapshot ID を export manifest に必須記録する。

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
- series の `ledger/events.jsonl` は artifact、selection snapshot、Canon revision の正本である。各 event は UUID、UTC timestamp、event type、payload digest を持ち、`O_APPEND` と `fsync()` で一行ずつ追記する。
- `state-cache.json` は ledger から再構築できる高速化用 cache であり、履歴の正本ではない。
- `series_plan.json`、`vol01.json`、`scene_summaries.json`、`exports/<fixed-name>` のような固定成果物は廃止する。

Canon も artifact / ledger モデルの対象とする。plan seed は immutable `canon.seed` artifact、scene patch の承認済み集合は immutable `canon.event_set` artifact とし、Canon projection は両者の digest から再生成する cache とする。design artifact は `canon_seed_artifact_id` と `canon_event_set_digest` を必須参照し、Canon revision が異なる artifact を同じ selection snapshot に混在させてはならない。

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

### Artifact Commit Protocol and Recovery

attempt directory の存在だけでは artifact の完成を意味しない。次の順序で immutable commit を行う。

```text
attempt.created
  → request / response / parse / validation evidence を新規保存
  → artifact payload と artifact manifest を新規保存して fsync
  → artifact-ready.json を O_EXCL で作成
  → artifact.ready event を append + fsync
  → artifact.selected event または selection snapshot を append + fsync
```

`artifact-ready.json` は payload file の相対パスと SHA-256 を列挙する最後の commit marker とする。recovery は `artifact-ready.json` のない attempt を未完成として扱い、入力・比較・自動採用の対象から除外する。ready だが selected でない artifact は candidate として残し、明示的な selection event がある場合だけ後続工程の入力にする。

JSONL の最後にクラッシュ由来の不完全行があれば、その行だけを無視し、直前の完全かつ digest 検証済み event までを正本とする。途中の完全 event を黙って補正・削除してはならない。

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

後続工程は「最新ファイル名」でも「直近 successful attempt」でもなく、開始時に固定した selection snapshot を読む。再実行で良い結果が得られた場合も、以前の成果物を置き換えず、新しい candidate artifact と明示的な selection snapshot を追記するだけである。

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

### Thinking and Credential Redaction

response をディスクへ書く前に、NDJSON の各 JSON object から次を削除する。

```text
message.thinking
thinking
```

request、response、error、manifest を保存する前には共通 sanitizer を必ず通す。`Authorization`、`Proxy-Authorization`、`api_key`、`apiKey`、`token`、`password`、`secret`、`connection_string` と、URL query parameter に含まれる同等の credential は値を `[REDACTED]` に置換する。headers は allowlist を優先し、例外メッセージも同じ sanitizer を通す。

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
- plan が slug を確定した後は、workspace lock を保持したまま series lock を取得し、slug と初回 selection snapshot を ledger へ fsync した後に workspace lock を解放する。移管途中の無保護区間を作らない。
- `design`、`write`、`export`、`resume` は series lock を取得する。
- lock 保持中に同一 scope の2本目を起動した場合、既定では待機せず即時失敗する。
- `--wait-lock` を明示した場合だけ待機する。

lock は PID だけでなく、run ID、PPID、process start time、Linux boot ID、argv、phase、開始時刻、log path を JSON で保持する。PID再利用を検出できない単純な `.lock` は廃止する。

## Implementation Plan

### Phase 1: Contracts and Tests

1. `RuntimeConfig`、`TaskSpec`、`RunManifest`、`AttemptManifest`、`ArtifactManifest`、`SelectionSnapshot`、ledger event の Pydantic model を定義する。
2. Task Registry と schema resource の存在を検証する契約テストを追加する。
3. 非上書き保存用の `ImmutableWriter` と `artifact-ready.json` commit marker を追加し、既存パスが存在する場合は失敗するテストを追加する。
4. selection snapshot、Canon revision 整合、crash recovery、`-v` 有無、thinking / credential 除去、retry 保存、run 間差分の受入テストを先に追加する。

### Phase 2: Configuration and Naming

1. 固定 config path を読む `RuntimeConfig.load()` を実装する。
2. 既存の config 探索、`NOVEL_FORGE_CONFIG`、workspace config 読み込みを削除する。
3. CLI の `--workdir` を nullable に変更し、CLI > config の解決テストを実装する。
4. prompt を新しい短縮名へ改名し、`scene_draft` / `scene_summary` を `draft` / `summary` へ置換する。
5. `write.summary.generate` / `review` / `revise` の prompt と `write_summary.json` を、final draft grounding・evidence・writer-safe handoff の契約で実装する。
6. `_infer_schema_name()` を削除し、Task Registry から prompt/schema を取得する。
7. LLM output schema を package resource だけへ集約し、トップレベル `schemas/` を削除する。

### Phase 3: Immutable Repository and Ledger

1. workspace run directory と series ledger directory を作る `RunRepository` を実装する。
2. run / attempt 開始、成功、失敗、artifact ready、artifact selection、selection snapshot、Canon revision の event を append-only で記録する。
3. `state.json` を正本として読むコードを、ledger と selection snapshot を読む `ArtifactRepository` へ置換する。
4. plan、design、write、export の固定パス保存を artifact reference 保存へ置換する。Canon seed / event set / projection cache も同じ参照モデルへ移す。
5. export は input selection snapshot に固定された draft / summary / final review / Canon revision を読み、出力自体も attempt artifact として保存する。
6. write は final draft → summary generate → review → revise を実行し、次 scene には selected summary の handoff fields だけを渡す。

### Phase 4: LLM Capture

1. `LLMClient` の raw logger を attempt-scoped writer へ置換する。
2. `-v` の場合だけ request / sanitized response / parsed / validation を保存する。
3. gzip、summary.md、summary directory、既存 `_raw_logs/` を廃止する。
4. すべての例外経路で `error.json` と partial response を残す。
5. response write 前の thinking redaction と request / response / error / manifest の credential sanitizer を共通関数化し、漏れをテストする。

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
| 高品質 summary | final draft から LLM generate → review → revise され、本文外の事実を含まず、次 writer に handoff fields だけを渡す |
| config | runtime が `~/.config/novel-forge/config.yaml` 以外を探索せず、`XDG_CONFIG_HOME` も参照しない |
| CLI優先 | `--workdir` が `workspace.root` より優先される |
| selection | 後続工程と export が logical key を持つ immutable selection snapshot だけを読み、時刻順で artifact を選ばない |
| Canon整合 | design / write / export の入力 artifact が同一 Canon seed と event-set revision を参照する |
| recovery | ready marker のない attempt は入力に使われず、壊れた JSONL 最終行は直前の検証済み event まで無視される |
| retry保全 | generation retry、review、revise、transport retry の各 artifact が別 attempt directory に残る |
| 再実行保全 | 同一 command を2回実行しても1回目の request、response、artifact の hash が変化しない |
| `-v` | request / sanitized response / parsed / validation が attempt ごとに保存される |
| 非verbose | request / response body が保存されない |
| thinking | 保存された全 JSON / NDJSON に `thinking` キーが存在しない |
| credentials | request / response / error / manifest に credential 値が残らない |
| gzip | run / attempt directory に `.gz` が存在しない |
| 比較 | 同一 task の2 attempt を `llm diff` で比較でき、元ファイルは更新されない |
| 二重起動 | 同一 scope の2本目が即時失敗し、既存 run ID / PID / log path を表示する |
| stale lock | PID再利用を process start time と boot ID で検出し、誤削除しない |

## Non-goals

- 過去 run の自動移行
- 過去 `state.json`、固定設計 JSON、`_raw_logs/` の読込互換
- LLM review の合否を自動的に正解化すること
- thinking の保存を許可する設定
