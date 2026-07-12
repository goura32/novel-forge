# Prompt / Schema Map

最終更新: 2026-07-12

この表は現行immutable runtimeが実行するLLM taskの契約です。TaskRegistry、prompt、schema、`RuntimeWorkflow._run_task()` の対応を変更時に同時に確認してください。

## 実行されるtask

| 成果物 | generate | review | revise | 出力schema |
|---|---|---|---|---|
| Series plan | `plan.series.generate` | `plan.series.review` | `plan.series.revise` | `plan_concept.json` |
| Volume design | `design.volume.generate` | `design.volume.review` | `design.volume.revise` | `design_volume.json` |
| Chapter design | `design.chapter.generate` | `design.chapter.review` | `design.chapter.revise` | `design_chapter.json` |
| Scene design | `design.scene.generate` | `design.scene.review` | `design.scene.revise` | `design_scene.json` |
| Scene draft | `write.draft.generate` | `write.draft.review` | `write.draft.revise` | `write_draft.json` |
| Scene summary | `write.summary.generate` | `write.summary.review` | `write.summary.revise` | `write_summary.json` |

review taskは共通の `review_issues.json` を使い、revision taskは対応するgenerate taskと同じschemaを返します。

## 品質ゲート

すべてのLLM候補は `generate → review → revise` のbounded cycleを通ります。review issuesが空ならその時点で候補を採用します。review上限に達した場合は、その時点の候補とfinal review evidenceを記録して後続へ進めます。上限は無限loopを防ぐ境界であり、未解決issueを自動拒否するquality gateではありません。

JSON parseまたはSchema validationの失敗はreview上限とは別に、`quality.max_retry_count` の範囲でgeneration attemptを作り直します。

## Scene Canon契約

LLMはCanon IDと表示名を含むauthor contextからscene designを作ります。`pov_character_id`、`character_ids`、`location_id`、`canon_updates.*.target_id` は許可されたIDとの完全一致でなければなりません。runtimeがsmall ID-only DSLをstrict CanonPatchへコンパイルし、整合性を検証します。

- 空patch、no-op更新、存在しない参照、前方参照は拒否する
- review済みのscene patchだけがCanon eventとしてfrontierへ公開される
- writerへはraw Canon frontierではなく、writer-safe contextと直近summaryだけを渡す

`{schema}` は `PromptManager.render_task()` が自動注入します。呼び出し側はtemplate variableとして渡しません。
