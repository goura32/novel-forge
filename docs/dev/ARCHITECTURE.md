# NovelForge Architecture

最終更新: 2026-07-12

## 正本と基本原則

現在のproduction pathは `RuntimeWorkflow` を中心とするimmutable runtimeです。固定の状態ファイル、時刻順の推測、live Canon storeは入力選択に使いません。

- **selection snapshot** が各後続runの唯一の入力正本
- **artifact** はappend-onlyで、ready markerとdigest検証を通過して初めて参照可能
- **Canon frontier** はseedと選択済みCanon eventからreplayされる
- LLMのgeneration、review、revisionはそれぞれ独立したattemptとevidenceを持つ

## レイヤー

| レイヤー | 主な実装 | 責務 |
|---|---|---|
| CLI | `cli.py` | Typer command、設定・workdir解決、run / lockの開始 |
| Workflow | `workflow_runtime.py` | snapshot入力、phase遷移、artifact公開、Canon frontier更新 |
| LLM boundary | `workflow_task_runner.py`、`llm_client.py` | task IDからprompt / schemaを解決し、Ollamaを1回呼び出す |
| Task resources | `task_registry.py`、`resources/prompts/`、`resources/schemas/` | task ID、prompt、JSON Schemaの対応を定義 |
| Immutable repository | `runtime.py` | run、attempt、artifact、ready marker、ledger、snapshot、lock |
| Canon | `canon/` | Canon seed、event、frontier replay、patch validation |

## データフロー

```text
keywords
  → plan.series generate → review → revise
  → plan.series + canon.seed + canon.frontier.root
  → selection snapshot
  → design.volume / design.chapter / design.scene の generate → review → revise
  → reviewed Canon event + updated frontier
  → selection snapshot
  → write.draft / write.summary の generate → review → revise
  → selection snapshot
  → export (json | markdown)
```

`plan`、`design.volume`、`design.chapter`、`design.scene`、`write.draft`、`write.summary` はそれぞれ `generate → review → revise` のbounded cycleを持ちます。reviewが空なら直ちに採用されます。上限到達時は、その時点の候補とfinal review evidenceを記録して後続へ進みます。scene designはdeterministic Canon patch reviewとCanon event公開も通ります。

## 永続化レイアウト

```text
<workdir>/.novel-forge/
  ledger/<series-slug>/
    events.jsonl
    snapshots/<snapshot-id>.json
  runs/<run-id>/
    run.json
    events.jsonl
    attempts/<attempt-id>/
      attempt.json
      artifacts/
      llm/
      error.json                 # failure attemptのみ
```

artifact payloadにはmanifestとready markerが対応します。選択snapshotはlogical keyからartifact IDを固定し、後続処理は「最新のファイル」ではなくその参照集合だけを読みます。

## LLM evidenceと失敗

LLMを呼んだattemptは `llm/request.json`、`response.ndjson`、`response.content.json`、`validation.json` を保存します。parseとSchema validationを通過した場合は `parsed.json` も保存します。

JSON parse / Schema validationのcontract failureは `quality.max_retry_count` の範囲で別attemptとして再試行します。transport failureは自動再試行せず、`error.json` を残して停止します。詳細は [LLM evidence形式](raw_log_format.md) と [Ollama API契約](OLLAMA_API.md) を参照してください。

## Canon境界

scene designはLLMがCanon IDだけを参照するsmall update DSLを返し、runtimeがstrict CanonPatchへコンパイルしてからdeterministic reviewを行います。空またはno-opのpatch、存在しないID、frontier replayの不整合は拒否されます。writerへ渡すのはwriter-safe contextと直近summaryであり、raw Canon frontierやstable IDを直接渡しません。

## 運用上の回復

`status` と `resume` はsnapshotとledgerを基に状態を判断します。変更系コマンドはworkspaceまたはseries lockで排他され、`--wait-lock` により待機できます。旧mutable状態ファイルや固定exportディレクトリは、現行runtimeの正本ではありません。
