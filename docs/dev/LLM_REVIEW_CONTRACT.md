# LLM Review Contract

## Goal

NovelForgeは、曖昧または検証不能なLLM出力を選択済みCanon・原稿へ進めません。各候補はimmutable attemptとして記録され、schema、review、deterministic contractを通過してからselection snapshotへ公開されます。

## Runtime task boundary

| Stage | 実行task | 受理条件 |
|---|---|---|
| Plan | `plan.series.generate → review → revise` | series schema、review cycle、Canon seed bootstrapが成立 |
| Design | `design.volume/chapter/scene.generate → review → revise` | sceneごとのID-only update DSL、deterministic Canon patch review、Canon event受理が成立 |
| Draft | `write.draft.generate → review → revise` | final review evidenceを記録 |
| Summary | `write.summary.generate → review → revise` | final summary review evidenceを記録 |

すべてのstageはbounded review cycleを実行し、reviewが空なら直ちに候補を採用します。review上限に達した場合は、その時点の候補とfinal review evidenceを記録して後続へ進みます。上限は無限loopを防ぐ境界であり、未解決issueを自動拒否する仕組みではありません。

## Retry boundary

JSON parse / Schema validationなどのcontract failureは `quality.max_retry_count` の範囲で別attemptとして再実行されます。transport failureは自動再試行せず、`error.json` を伴う失敗attemptとして終了します。

## Canon identity boundary

LLMはauthor context内で許可されたCanon IDをscene designへ直接返します。runtimeがID-only update DSLをstrict CanonPatchへコンパイルし、Canon patchの整合性を検証します。

- empty / no-op patchは拒否する
- 存在しないentity、前方参照、型不一致は拒否する
- review済みpatchだけがCanon eventとしてactive frontierに入る
- writerはraw Canon、event、stable IDではなくwriter-safe contextと直近summaryを受け取る

## Evidence

LLMを呼んだ各attemptは `llm/request.json`、`response.ndjson`、`response.content.json`、`validation.json` を保持します。parse・Schema validation成功時のみ `parsed.json` も保存されます。これにより、選択artifactからcandidate・review・revision・validationの追跡が可能です。

詳細は [Attempt-scoped LLM evidence形式](raw_log_format.md) を参照してください。
