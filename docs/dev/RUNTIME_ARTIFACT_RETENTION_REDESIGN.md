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
| `plan.series.generate` | `plan_concept_generate.md` | `plan_concept.json` |
| `design.volume.generate` | `design_volume_generate.md` | `design_volume.json` |
| `design.volume.review` | `design_volume_review.md` | `review_issues.json` |
| `design.volume.revise` | `design_volume_revise.md` | `design_volume.json` |
| `write.draft.generate` | `write_draft_generate.md` | `write_draft.json` |
| `write.draft.review` | `write_draft_review.md` | `review_issues.json` |
| `write.draft.revise` | `write_draft_revise.md` | `write_draft.json` |
| `write.summary.generate` | `write_summary_generate.md` | `write_summary.json` |
| `write.summary.review` | `write_summary_review.md` | `review_issues.json` |
| `write.summary.revise` | `write_summary_revise.md` | `write_summary.json` |

> **Note:** `plan` は単一の `plan.series.generate` に収束した（旧 `plan.concept/characters/volumes` の3分割は廃止）。plan は review/revise チェーンを持たない。現行 `RuntimeWorkflow` は `design.volume.generate` / `design.chapter.generate` / `design.scene.generate` の **generate のみ** を呼ぶ（`workflow_runtime.py` の `_run_task` 呼び出しを参照）。`design.*.review` / `design.*.revise` は registry に予約されているが runtime からは呼ばれない（design フェーズは generate-only）。`write.*` は generate/review/revise すべてを呼ぶ。
>
> **plan→design データフロー（意図的構造・誤検知防止）:** `RuntimeWorkflow` が `design.volume/chapter.generate` に渡す `"series_plan": plan` の `plan` は、`plan.series.generate` の出力（schema = `plan_concept.json`）から来た正しい plan オブジェクトである。`series_plan` というキー名は LLM 入力用のラベルであり、廃止された `series_plan.json` ファイルを指すものではない。したって「plan の schema が `series_plan.json` を参照している」とする静的解析の指摘は**誤検知**。`series_plan.json` というファイルは存在しない（設計上廃止済み）。
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
_TASK_ROWS = (
    ("plan.series", "plan_concept"),
    ("design.volume", "design_volume"),
    ("write.draft", "write_draft"),
    ("write.summary", "write_summary"),
)
_SINGLE_STEP_TASKS = frozenset({"plan.series"})
_OPERATIONS = ("generate", "review", "revise")

def _build_tasks() -> dict[str, TaskSpec]:
    tasks: dict[str, TaskSpec] = {}
    for stem, resource_stem in _TASK_ROWS:
        operations = ("generate",) if stem in _SINGLE_STEP_TASKS else _OPERATIONS
        for operation in operations:
            task_id = f"{stem}.{operation}"
            prompt = f"{resource_stem}_{operation}.md"
            tasks[task_id] = TaskSpec(
                task_id=task_id,
                prompt=prompt,
                schema="review_issues" if operation == "review" else resource_stem,
            )
    return tasks
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
- review issue がなければ、schema / semantic validation を通った candidate を `passed` として新しい selection snapshot へ自動採用する。
- review issue があり、`quality.max_summary_review_count` 未満なら revise → review を続ける。
- review issue が残ったまま上限に到達した場合も、最後に schema / semantic validation を通った candidate を `review_limit_reached` として新しい selection snapshot へ**自動採用**し、直ちに次工程へ進む。最後の review artifact と未解決 issue は summary manifest と export report に必ず残す。
- review API / parse / schema error は review 上限とは別の generation failure とし、`max_generation_count` の retry を使い切るまでは selection snapshot を作らない。

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

`review_error` は generation retry を使い切っても review artifact を得られなかった candidate の状態であり、selection snapshot に採用してはならない。selected summary の `summary_quality_status` は `passed` または `review_limit_reached` のどちらかだけである。

後続 scene の writer は、直前 scene の selected summary artifact をこの logical key で取得する。ファイル名の新旧や時刻順で選んではならない。

## Immutable Run and Attempt Model

### Terminology

| 用語 | 意味 |
|---|---|
| run | 1回の CLI 起動。`plan`、`write`、`complete` などが1 run |
| attempt | run 内の1つの task 実行。generation retry、review、revise、transport retry を含む |
| artifact | attempt が出力した plan/design/draft/summary/export などの不変成果物 |
| artifact manifest | `format_version`、artifact ID、logical key、content digest、入力 artifact IDs、schema/prompt digest を固定する不変メタデータ |
| ledger | artifact の採用関係と状態遷移を追記する append-only 記録 |
| selection snapshot | 後続工程が読む唯一の採用正本。複数 logical key の artifact を一つの入力集合として固定した immutable snapshot |

同じ CLI をもう一度実行する場合は別 run である。同じ task の generation retry、review/revise cycle、transport retry は別 attempt として記録する。

後続工程は単一 artifact の「最新時刻」を読まない。`plan` 以外の run は開始時に immutable `selection snapshot` を固定し、その snapshot に記録された logical key → artifact ID の組だけを入力にする。初回 plan は artifact がまだないため `input_snapshot_id: null` と `input_kind: bootstrap` を持つ唯一の例外とする。plan 成功後には、`plan.series`、`canon.seed`、空の event set を表す `canon.frontier` を含む最初の通常 snapshot を作る。export snapshot は plan、volume design、Canon frontier、全 scene の draft、summary、final review artifact を同時に固定する。

```json
{
  "format_version": 1,
  "record_type": "selection_snapshot",
  "selection_snapshot_id": "sel_...",
  "base_snapshot_id": "sel_...",
  "slots": {
    "plan.series": "art_...",
    "design.vol01": "art_...",
    "write.vol01.ch02.sc03.draft": "art_...",
    "write.vol01.ch02.sc03.summary": "art_...",
    "write.vol01.ch02.sc03.final_review": "art_...",
    "canon.seed": "art_...",
    "canon.frontier": "art_..."
  },
  "slots_digest": "sha256:..."
}
```

`write.<volume>.<chapter>.<scene>.final_review` は task ID ではない。final selected draft を対象にした最後の `write.draft.review` attempt が出力する `review_issues` artifact の logical key である。draft の中間 candidate に対する review artifact はこの slot に入れない。

candidate artifact は `artifact-ready.json` が作られても、selection snapshot に入るまで後続入力に使用しない。採用状態を変更できる ledger event は `selection.snapshot.created` **だけ**であり、event は完全な slots map、base snapshot ID、slots digest、採用理由を持つ。単独 artifact の採用を表す `artifact.selected` event は作らない。

review loop を持つ task の snapshot 作成規則は共通である。

1. schema / semantic validation に成功し、review issue がなければ candidate を `passed` として自動採用する。
2. issue があり review 回数が上限未満なら revise → review を続ける。
3. issue が残ったまま review 上限に達した場合は、最後に validation を通った candidate を `review_limit_reached` として自動採用し、次工程へ進む。
4. review の generation failure は上限到達とは扱わず、generation retry を使い切るまで candidate のままとする。retry 枯渇後は candidate を `review_error` と記録し、selection snapshot を作らず task / run を `failed`（`resume` 可能）として終了する。次工程へは進まない。

export は自身の input snapshot ID と、`review_limit_reached` の artifact に紐付く最後の review artifact IDs を export manifest に必須記録する。

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
              plan_concept.manifest.json
            artifact-ready.json
            llm/                     # `-v` の場合だけ作成
              request.json
              response.ndjson
              response.content.json
              parsed.json
              validation.json
            error.json                # verbose: 詳細 / 非verbose: safe metadata
          att_000002_plan_concept_review_r01_t01/
            attempt.json
            artifacts/
              review_issues.json
              review_issues.manifest.json
            artifact-ready.json

  <series-slug>/
    .novel-forge/
      ledger/
        events.jsonl
        snapshots/
          sel_20260711T103244Z_91f.json
      state-cache.json
```

- `run.json`、`attempt.json`、artifact manifest、`artifact-ready.json`、ledger event、selection snapshot はすべて `format_version` と `record_type` を持つ。未知の version は fail-fast で拒否する。
- `run.json` と `attempt.json` は開始時に作成し、終了時には別の completion event を追記する。既存 JSON を更新しない。
- `events.jsonl` は run の出来事を順番に記録する。
- series の `ledger/events.jsonl` は artifact、selection snapshot、Canon revision の正本である。各 event は UUID、UTC timestamp、event type、payload digest を持ち、`O_APPEND` と `fsync()` で一行ずつ追記する。selection snapshot 本体は `ledger/snapshots/<id>.json` を `O_EXCL` で新規保存し、`selection.snapshot.created` event はその path と SHA-256 を参照する。
- `state-cache.json` は ledger から再構築できる高速化用 cache であり、履歴の正本ではない。
- `series_plan.json`、`vol01.json`、`scene_summaries.json`、`exports/<fixed-name>` のような固定成果物は廃止する。

Canon も artifact / ledger モデルの対象とする。plan seed は immutable `canon.seed` artifact、承認済み scene patch の集合は immutable `canon.event_set` artifact とし、selection snapshot は現在採用する event set を `canon.frontier` slot として指す。Canon projection は snapshot の `canon.seed` と `canon.frontier` から再生成する cache とする。

Canon を消費する artifact manifest は `canon_lineage_root_digest` と `input_canon_frontier_digest` を持つ。bootstrap plan と `canon.seed` 自体は input frontier を持たない。`canon.event_set` artifact は `parent_frontier_artifact_id`、`parent_frontier_digest`、順序付き `source_patch_artifact_ids` を持つ。空の root event set だけは parent を `null` にする。Canon patch を出力する artifact は、さらに `output_canon_frontier_artifact_id` を持つ。snapshot は、Canon を消費する artifact が同じ lineage root を共有し、event-set の parent chain で各 input frontier が snapshot の `canon.frontier` の祖先または同一である場合だけ有効である。過去 scene の artifact と、その後の patch を含む frontier を同じ snapshot に置くことは許可する。一方、互いに祖先関係を持たない branch の frontier を混在させてはならない。

export は live series store を入力として読まない。input selection snapshot の `canon.seed` と `canon.frontier` artifact を replay し、その結果だけを Canon report / manuscript metadata に使う。projection cache はこの2つの digest が一致する時だけ使用できる。

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

`-v` の request / response には原稿本文が含まれるため、`.novel-forge/`、run directory、attempt directory は作成時に mode `0700`、その配下の JSON / NDJSON / log file は mode `0600` とする。共有 workspace の umask に依存しない。

### Artifact Commit Protocol and Recovery

attempt directory の存在だけでは artifact の完成を意味しない。`attempt.json` は開始 record であり、終了情報を書き戻さない。成功と失敗は次の分岐で immutable commit する。

```text
attempt start
  → attempt.json を O_EXCL で新規保存して file fsync
  → attempt directory fsync
  → attempt.created event を append + fsync
  → `-v` の場合だけ request / response / parsed / validation evidence を新規保存

success
  → artifact payload と artifact manifest を新規保存して file fsync
  → attempt directory fsync
  → artifact-ready.json を O_EXCL で作成して file fsync
  → attempt directory fsync
  → artifact.ready event を append + fsync
  → attempt.succeeded event を append + fsync
  → 採用する場合だけ selection snapshot file を O_EXCL で新規保存して file + snapshot directory fsync
  → 採用する場合だけ selection.snapshot.created event を append + fsync
  → ledger directory fsync

failure
  → safe `error.json`（`-v` 時は sanitized detail を追加）を新規保存して file fsync
  → attempt directory fsync
  → attempt.failed event を append + fsync
  → artifact-ready.json と selection snapshot は作成しない
```

`attempt.succeeded` / `attempt.failed` event は attempt ID、終了時刻、終了理由、validation outcome、retryable を持つ。非verboseでは本文・provider message・provider error body を event payload に入れない。

`artifact-ready.json` は artifact manifest と payload file の相対パスおよび SHA-256 を列挙する最後の commit marker である。marker がない attempt は未完成として、入力・比較・自動採用の対象から除外する。marker がある場合でも、selection snapshot を解決する前に ledger event が参照する snapshot file の SHA-256 を再検証し、次に marker が列挙する manifest / payload の SHA-256 を再検証する。いずれかが不一致なら fail-fast とし、自動差し替えしない。run 中に破損を検出した場合は `artifact.corrupt` event を追記して失敗し、既存 snapshot を別 candidate へ自動差し替えしない。read-only command は event を追記せず、検出結果だけを返す。ready かつ hash 検証済みでも selection snapshot に含まれない artifact は candidate として残し、`selection.snapshot.created` event が参照する場合だけ後続工程の入力にする。

JSONL の最後にクラッシュ由来の不完全行があれば、その行だけを無視し、直前の完全かつ digest 検証済み event までを正本とする。途中の完全 event を黙って補正・削除してはならない。

### Retry Recording

すべての失敗経路でも attempt を残す。

| 事象 | `-v` で保存するもの | 非verboseで保存するもの |
|---|---|---|
| transport timeout | request、受信済み partial response、詳細 `error.json` | safe `error.json`、attempt event。partial response body は保存しない |
| HTTP error | request、error response / error detail、詳細 `error.json` | HTTP status / retryable / body保存有無だけを持つ safe `error.json`、attempt event |
| JSON parse error | request、response.ndjson、response.content.json、parse error | parser result本文を含まない failure code、attempt event |
| schema / semantic validation error | request、response、parsed.json、validation.json | validation outcome / error code / artifact ID だけを持つ safe metadata、attempt event |
| generation retry | retry ごとの新しい attempt directory | retry ごとの新しい attempt directory |
| review → revise | review attempt と revise attempt を別々に保存 | review attempt と revise attempt を別々に保存 |
| CLI 再実行 | 新しい run directory と新しい attempt tree | 新しい run directory と新しい attempt tree |

後続工程は「最新ファイル名」でも「直近 successful attempt」でもなく、開始時に固定した selection snapshot を読む。再実行で良い結果が得られた場合も、以前の成果物を置き換えず、新しい candidate artifact と明示的な selection snapshot を追記するだけである。

## LLM Request / Response Capture

### Activation

LLM送受信の保存は現状どおり `-v` / `--verbose` を指定した run だけで有効にする。

```bash
novel-forge write --workdir /path/to/workspace --series example --volume 1 -v
```

`-v` なしの場合、run metadata、attempt metadata、append-only event、通常ログ、最終成果物は残すが、request / response / partial response / parsed JSON / validation detail の本文を保存しない。非verboseの `error.json` は exception class、error code、HTTP status、retryable、body保存有無だけを allowlist で持つ safe metadata とし、provider message や error response body は持たない。

### Per-attempt Files

`-v` の各 LLM attempt は次のファイルを保存する。gzip 圧縮は行わない。

| ファイル | 内容 |
|---|---|
| `attempt.json` | run ID、task ID、phase、model、seed、retry番号、開始時刻。終了時刻・終了理由・validation outcome は immutable `attempt.succeeded` / `attempt.failed` event にだけ記録する |
| `llm/request.json` | Ollama に送信した payload |
| `llm/response.ndjson` | thinking を除去した受信 NDJSON。受信順を維持 |
| `llm/response.content.json` | `message.content` を結合した応答本文 |
| `llm/parsed.json` | parser が得た JSON 値。parse失敗時は作らない |
| `llm/validation.json` | schema / semantic validation の結果 |
| `error.json` | 例外種別、sanitized message、HTTP情報、partial response の有無。非verboseでは allowlist safe metadata のみ |

`response.ndjson` は「thinking 除去済み transport record」であり、受信バイト列の完全コピーとは呼ばない。thinking を保存しないという要件を優先する。

### Ollama Thinking and Credential Redaction

当面の provider は Ollama のみである。Ollama 以外の reasoning / thought envelope への対応は本仕様の対象外とし、必要になった時点で provider contract として別途追加する。

response をディスクへ書く前に、NDJSON の各 JSON object から次を削除する。

```text
message.thinking
thinking
```

request、response、error、manifest、**通常ログ** を保存する前には共通 sanitizer を必ず通す。`Authorization`、`Proxy-Authorization`、`api_key`、`apiKey`、`token`、`password`、`secret`、`connection_string` と、URL query parameter に含まれる同等の credential は値を `[REDACTED]` に置換する。headers は allowlist を優先し、例外メッセージも同じ sanitizer を通す。`run.log` を含む通常ログは、verbose の有無にかかわらず request / response / partial response / parsed JSON / provider error body を出力してはならない。raw LLM本文を保存できるのは `-v` の attempt `llm/` file だけである。

この処理は成功、timeout、HTTP error、parse error、schema validation error のすべての保存経路で必ず通る。human-readable summary を別に作らず、`response.content.json` を人間確認用の本文とする。

## Later Comparison

履歴を残す目的は「最新だけを見る」ことではなく、retry や再実行による LLM 応答の変化を検証することである。次の read-only command を提供する。

```bash
novel-forge run show <run-id>
novel-forge attempt show <attempt-id>
novel-forge llm diff <attempt-a> <attempt-b>
novel-forge llm diff --metadata-only <attempt-a> <attempt-b>
novel-forge artifact diff <artifact-a> <artifact-b>
```

`llm diff` は、両方の attempt に `-v` capture が完備している場合だけ実行できる。request / response / parsed のいずれかがない場合は元ファイルを読んで補完せず、non-zero exit と不足 attempt ID を返す。非verbose attempt の task ID、model、seed、prompt hash、schema hash、attempt reason、validation outcome だけを比較する場合は `llm diff --metadata-only` を明示する。

完全 capture がある `llm diff` は次を出力する。

- task ID、model、seed、prompt hash、schema hash、attempt reason
- request payload の構造差分
- `response.content.json` の unified diff
- parsed JSON の構造差分
- validation 結果の変化

差分コマンドは原本を更新しない。比較結果を保存したい場合だけ `--output <new-path>` を指定し、その出力も既存ファイルがあれば失敗する。

## Run Ownership and Duplicate Start Prevention

副作用を持つ `plan`、`design`、`write`、`export`、`resume`、`complete` は Run Manager を通す。

- 単独の `plan` は workspace lock を取得する。plan が slug を確定した後は、workspace lock を保持したまま series lock を取得する。series ledger がすでに存在する場合は `SERIES_SLUG_EXISTS` で失敗し、candidate run を残すが既存 series の Canon / ledger / selection snapshot は変更しない。ledger がない場合だけ slug と最初の通常 selection snapshot を ledger へ fsync した後に workspace lock を解放する。移管途中の無保護区間を作らない。
- `complete` は workspace lock を取得して plan を実行する。slug 確定後は同じ collision check と series lock 移管を行う。既存 series slug なら `SERIES_SLUG_EXISTS` で停止する。新規 series の場合だけ、**design → write → export が成功・失敗・中断のいずれで終了するまで series lock を保持する**。phase ごとに lock を取り直さない。
- `design`、`write`、`export`、`resume` は series lock を取得する。
- lock 保持中に同一 scope の2本目を起動した場合、既定では待機せず即時失敗する。
- `--wait-lock` を明示した場合だけ待機する。

lock は PID だけでなく、run ID、PPID、process start time、Linux boot ID、argv、phase、開始時刻、log path を JSON で保持する。PID再利用を検出できない単純な `.lock` は廃止する。

## Implementation Plan

### Phase 1: Contracts and Tests

1. `RuntimeConfig`、`TaskSpec`、`RunManifest`、`AttemptManifest`、`ArtifactManifest`、`SelectionSnapshot`、ledger event の Pydantic model を定義する。
2. Task Registry と schema resource の存在を検証する契約テストを追加する。
3. 非上書き保存用の `ImmutableWriter` と `artifact-ready.json` commit marker を追加し、既存パスが存在する場合は失敗するテストを追加する。
4. selection snapshot の唯一性、bootstrap plan、Canon lineage / frontier 整合と parent chain、snapshot 固定 export、ready marker の SHA-256 再検証、成功 / failure attempt の immutable 時系列、review 上限到達時の自動進行、review generation retry 枯渇時の failed/resume、`complete` の全工程 lock、slug collision、verbose / 非verbose 保存境界、通常ログの raw body 禁止、Ollama thinking / credential 除去、`llm diff` capture 要件、retry 保存、run 間差分の受入テストを先に追加する。

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
2. run / attempt 開始、成功、失敗、artifact ready、**selection.snapshot.created**、Canon frontier の event を append-only で記録する。単独 `artifact.selected` event は実装しない。
3. `state.json` を正本として読むコードを、ledger と selection snapshot を読む `ArtifactRepository` へ置換する。
4. plan、design、write、export の固定パス保存を artifact reference 保存へ置換する。Canon seed / event set / frontier / projection cache も同じ参照モデルへ移す。
5. export は input selection snapshot に固定された draft / summary / final review / `canon.seed` / `canon.frontier` を読み、live series store を読まずに Canon projection を replay する。出力自体も attempt artifact として保存する。
6. write は final draft → summary generate → review → revise を実行し、review 上限到達時は最後の validation 済み summary を自動採用して、次 scene にはその handoff fields だけを渡す。

### Phase 4: LLM Capture

1. `LLMClient` の raw logger を attempt-scoped writer へ置換する。
2. `-v` の場合だけ request / sanitized response / parsed / validation を保存する。
3. gzip、summary.md、summary directory、既存 `_raw_logs/` を廃止する。
4. すべての例外経路で safe `error.json` と attempt failure event を残し、partial response 本文は `-v` の場合だけ保存する。
5. Ollama response write 前の thinking redaction、request / response / error / manifest / 通常ログの credential sanitizer、通常ログの raw body 禁止を共通経路で実装し、漏れをテストする。

### Phase 5: Run Manager and CLI

1. JSON lock、PID identity 検証、stale lock recovery を実装する。
2. 全副作用コマンドを Run Manager でラップし、`complete` は slug 確定後から export 終了まで同じ series lock を保持する。
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
| review上限 | review issue が残っても上限到達時は最後の validation 済み candidate を `review_limit_reached` として自動採用し、次工程へ進む。最後の review artifact / issues は export report に残る |
| review generation failure | generation retry 枯渇後は candidate を `review_error` と記録し、selection snapshot を作らず task / run を failed（`resume`可能）で終了する |
| config | runtime が `~/.config/novel-forge/config.yaml` 以外を探索せず、`XDG_CONFIG_HOME` も参照しない |
| CLI優先 | `--workdir` が `workspace.root` より優先される |
| selection | `selection.snapshot.created` が唯一の採用正本であり、後続工程と export は logical key を持つ immutable selection snapshot だけを読む。単独 `artifact.selected` event は存在しない |
| bootstrap | 初回 plan は `input_kind: bootstrap` と `input_snapshot_id: null` で開始し、成功時に plan / Canon seed / 空の Canon frontier を含む最初の通常 snapshot を作る |
| Canon整合 | Canon を消費する snapshot artifact は同一 Canon lineage root を共有し、`canon.event_set` の parent chain で各 input frontier が snapshot の `canon.frontier` の祖先または同一である。branch が異なる Canon frontier は混在しない |
| Canon export | export は snapshot の `canon.seed` / `canon.frontier` だけを replay し、live series store の変化で結果を変えない |
| format | immutable record が `format_version` と `record_type` を持ち、未知 version は fail-fast で拒否される |
| final review slot | `write.*.final_review` は final selected draft を対象にした最後の `write.draft.review` artifact だけを指し、中間 candidate の review を指さない |
| attempt時系列 | `attempt.json` は開始 record のみで更新されず、成功は ready marker → `artifact.ready` → `attempt.succeeded`、失敗は `attempt.failed` で終わる。failure attempt は ready marker / selection snapshot を持たない |
| recovery | ready marker のない attempt は入力に使われない。input selection snapshot、marker が列挙する manifest / payload の SHA-256 を入力解決前に再検証する。hash 不一致は fail-fast とし自動差し替えしない。壊れた JSONL 最終行は直前の検証済み event まで無視され、file と directory の fsync 順序を守る |
| retry保全 | generation retry、review、revise、transport retry の各 artifact が別 attempt directory に残る |
| 再実行保全 | 同一 command を2回実行しても1回目の artifact と、`-v` で保存済み request / response の hash が変化しない |
| `-v` | request / sanitized response / parsed / validation が attempt ごとに保存される |
| 非verbose | request / response / partial response / parsed JSON / validation detail の本文を保存しない。`error.json` は allowlist safe metadata のみ |
| thinking | Ollama response の保存済み JSON / NDJSON に `thinking` キーが存在しない。Ollama 以外の reasoning envelope は本仕様の対象外 |
| logs | `run.log` を含む通常ログは verbose の有無にかかわらず raw request / response / partial response / parsed JSON / provider error body を含まない |
| credentials | request / response / error / manifest / 通常ログに credential 値が残らない |
| permissions | `.novel-forge/` / run / attempt directory は `0700`、配下の JSON / NDJSON / log file は `0600` で作成される |
| gzip | run / attempt directory に `.gz` が存在しない |
| 比較 | `llm diff` は両 attempt の verbose capture が完備している場合だけ request / response / parsed diff を出力する。非verbose比較は `--metadata-only` が必須で、元ファイルを更新しない |
| 二重起動 | 同一 scope の2本目が即時失敗し、既存 run ID / PID / log path を表示する |
| complete lock | `complete` は slug 確定後から export 終了まで同じ series lock を保持し、別の design / write / export / resume を開始させない |
| slug collision | `plan` / `complete` が既存 series slug を得た場合は `SERIES_SLUG_EXISTS` で失敗し、candidate run 以外の既存 series data を変更しない |
| stale lock | PID再利用を process start time と boot ID で検出し、誤削除しない |

## Non-goals

- 過去 run の自動移行
- 過去 `state.json`、固定設計 JSON、`_raw_logs/` の読込互換
- LLM review の合否を自動的に正解化すること
- thinking の保存を許可する設定
