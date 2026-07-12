# Prompt / Schema Map

最終更新: 2026-07-12

この表は現行immutable runtimeが実行するLLM taskの契約です。TaskRegistry、prompt、schema、`RuntimeWorkflow._run_task()` の対応を変更時に同時に確認してください。

## 実行されるtask

| 成果物 | generate | review | revise | 出力schema |
|---|---|---|---|---|
| Series plan | `plan.series.generate` | — | — | `plan_concept.json` |
| Volume design | `design.volume.generate` | — | — | `design_volume.json` |
| Chapter design | `design.chapter.generate` | — | — | `design_chapter.json` |
| Scene design | `design.scene.generate` | — | — | `design_scene.json` |
| Scene draft | `write.draft.generate` | `write.draft.review` | `write.draft.revise` | `write_draft.json` |
| Scene summary | `write.summary.generate` | `write.summary.review` | `write.summary.revise` | `write_summary.json` |

review taskは共通の `review_issues.json` を使い、revision taskは対応するgenerate taskと同じschemaを返します。

`design.*.review` / `design.*.revise` はregistry上の予約resourceですが、public runtimeは呼び出しません。planもsingle-step taskです。

## 品質ゲート

writeの各候補は `generate → review → revise` を通ります。review issuesが空になった候補だけが選択snapshotへ進みます。review上限に達しても未解決issueを持つ候補は選択されません。

JSON parseまたはSchema validationの失敗はreview上限とは別に、`quality.max_retry_count` の範囲でgeneration attemptを作り直します。

## Scene Canon契約

scene designには空でない `canon_patch` が必要です。LLMへ渡すauthor contextはIDを露出しない決定論的なnarrative contextで、runtimeがscene designの名前参照をstable `EntityRef` に解決します。

- 空patch、no-op更新、存在しない参照、前方参照は拒否する
- review済みのscene patchだけがCanon eventとしてfrontierへ公開される
- writerへはraw Canon frontierではなく、writer-safe contextと直近summaryだけを渡す

`{schema}` は `PromptManager.render_task()` が自動注入します。呼び出し側はtemplate variableとして渡しません。
