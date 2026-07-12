# Prompt / Schema Map

この表は現行の immutable runtime の唯一の LLM タスク契約です。旧 `engine/*` / v1 の prompt 名は参照しません。

## 全LLM工程の品質ゲート

すべての LLM 成果物は、必ず次の順序で処理されます。

1. `generate` — schema 準拠候補を作る
2. `review` — LLM レビューと deterministic contract review を行う
3. `revise` — issue があれば同じ schema の候補を改訂する
4. review issues が空になるまで繰り返す。上限到達時は **fail closed**（selection snapshot を進めない）

| 成果物 | generate | review | revise | 出力 schema |
|---|---|---|---|---|
| Series plan | `plan.series.generate` | `plan.series.review` | `plan.series.revise` | `plan_concept.json` |
| Volume design | `design.volume.generate` | `design.volume.review` | `design.volume.revise` | `design_volume.json` |
| Chapter design | `design.chapter.generate` | `design.chapter.review` | `design.chapter.revise` | `design_chapter.json` |
| Scene design | `design.scene.generate` | `design.scene.review` | `design.scene.revise` | `design_scene.json` |
| Scene draft | `write.draft.generate` | `write.draft.review` | `write.draft.revise` | `write_draft.json` |
| Scene summary | `write.summary.generate` | `write.summary.review` | `write.summary.revise` | `write_summary.json` |

レビューだけは共通の `review_issues.json` を使う。改訂は生成と同じ schema を返す。

## Scene の Canon 契約

`design_scene.json` は CanonPatch の内部構造を LLM に露出しない。LLM は `canon_context` に明示されたIDのみを、完全一致で返す。

- `pov_character_id`、`character_ids` は `canon_context.characters[].id` のみ。
- `location_id` は `canon_context.locations[].id` のみ。
- 表示名、alias、部分一致、推測したID、新規 entity は参照に使えない。
- `canon_updates` は既存 entity に対する小さい意図DSLである。Python の `_compile_scene_updates` が strict `CanonPatch` に変換し、schema/semantic preflight を通過した候補だけが Canon Event になる。
- ID不在、DSL不正、CanonPatch不正、semantic conflict は補正やデフォルト代入を行わない。review issue として `revise` に戻す。

この境界により、`artifacts.state_updates` のような LLM の近似的な CanonPatch を runtime が正規化して受け入れる経路は存在しない。
