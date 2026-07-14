# Prompt / Schema 対応表

この表は現行PNCA production taskの正本です。変更時は`pnca/defaults.py`、resource prompt、resource schema、`pnca/production.py`の入力変数、contract / writer / workflow testを同一変更で更新します。

| task ID | prompt | schema | 主な役割 |
|---|---|---|---|
| `pnca.series.contract` | `pnca_series_contract.md` | `pnca_series_contract.json` | Series Contract |
| `pnca.volume.contract` | `pnca_volume_contract.md` | `pnca_volume_contract.json` | Volume Contract |
| `pnca.chapter.contract` | `pnca_chapter_contract.md` | `pnca_chapter_contract.json` | Chapter Contract |
| `pnca.scene.contract` | `pnca_scene_contract.md` | `pnca_scene_contract.json` | Scene Contract |
| `pnca.writer_view.review` | `pnca_writer_view_review.md` | `review_issues.json` | WriterView audit |
| `pnca.writer_view.revise` | `pnca_writer_view_revise.md` | `pnca_writer_view_revise.json` | WriterView revision |
| `pnca.scene.render` | `pnca_scene_render.md` | `pnca_scene_render.json` | draft render |
| `pnca.scene.rerender` | `pnca_scene_rerender.md` | `pnca_scene_render.json` | structural rerender |
| `pnca.scene.coverage` | `pnca_scene_coverage.md` | `pnca_scene_coverage.json` | obligation coverage |
| `pnca.scene.revise` | `pnca_scene_revise.md` | `pnca_scene_revise.json` | draft revision |
| `pnca.draft.audit` | `pnca_draft_audit.md` | `pnca_draft_audit.json` | final draft audit |

JSON/schema contract failureは`quality.max_generation_attempts`まで再生成します。初回を含み、transport failureは自動retryしません。review上限でhard findingを後続へ通す規則はありません。

`QualityDisposition`はLLM taskではありません。runtimeが最終`DraftAudit`を決定論的に分類し、write phaseのbundle slotへpinします。
