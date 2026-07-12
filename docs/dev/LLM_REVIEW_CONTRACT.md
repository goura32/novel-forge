# LLM Review Contract

## Goal

NovelForgeは、曖昧または検証不能なLLM出力を選択済みCanon・原稿へ進めません。各候補はimmutable attemptとして記録され、schema、review、deterministic contractを通過してからselection snapshotへ公開されます。

## Runtime task boundary

| Stage | 実行task | 受理条件 |
|---|---|---|
| Plan | `plan.series.generate` | series schemaとCanon seed bootstrapが成立 |
| Design | `design.volume/chapter/scene.generate` | sceneごとのnon-empty Canon patchとdeterministic patch reviewが成立 |
| Draft | `write.draft.generate → review → revise` | final review issuesが空 |
| Summary | `write.summary.generate → review → revise` | final summary review issuesが空 |

planとdesignはpublic runtimeではgenerate-onlyです。writeのreview上限は未解決欠陥を許容する仕組みではなく、上限到達時は選択snapshotを進めず停止します。

## Retry boundary

JSON parse / Schema validationなどのcontract failureは `quality.max_retry_count` の範囲で別attemptとして再実行されます。transport failureは自動再試行せず、`error.json` を伴う失敗attemptとして終了します。

## Canon identity boundary

LLMはauthor-facingな名称と文脈からscene designを作ります。runtimeが名前参照をstable typed referenceへ解決し、Canon patchの整合性を検証します。

- empty / no-op patchは拒否する
- 存在しないentity、前方参照、型不一致は拒否する
- review済みpatchだけがCanon eventとしてactive frontierに入る
- writerはraw Canon、event、stable IDではなくwriter-safe contextと直近summaryを受け取る

## Evidence

LLMを呼んだ各attemptは `llm/request.json`、`response.ndjson`、`response.content.json`、`validation.json` を保持します。parse・Schema validation成功時のみ `parsed.json` も保存されます。これにより、選択artifactからcandidate・review・revision・validationの追跡が可能です。

詳細は [Attempt-scoped LLM evidence形式](raw_log_format.md) を参照してください。
