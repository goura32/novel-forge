# LLM Review Contract

## 現行のreview対象

| 対象 | task | 結果 |
|---|---|---|
| WriterView | `pnca.writer_view.review` / `pnca.writer_view.revise` | writer入力の構造的妥当性を確保 |
| Scene draft | `pnca.draft.audit` / `pnca.scene.revise` | draft issueをauditしrevision |
| Coverage | `pnca.scene.coverage` / `pnca.scene.rerender` | required beat / end constraint evidenceを検証 |

旧`generate → review → revise`共通task体系、summary review、review上限到達時のcandidate通過は現行PNCAにはありません。

## Bounded progression

- blockerは最大2回hard repairする。
- blockerまたは`constraint_kind != quality`が残れば停止する。
- `quality`のmajor/minorは最大1回polishし、残ればruntimeが`deferred`を作れる。
- `clean`はissueゼロ、`deferred`は全residualとの完全一致を要求する。

## Generation failure

JSON parse、schema validation、schema echoは`quality.max_generation_attempts`まで再生成する。初回を含む。transport failureはretryしない。各生成試行は独立したimmutable attempt evidenceとして保存する。
