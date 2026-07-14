# Prompt 編集方針

## Phase責務

| Phase | promptの責務 |
|---|---|
| Contract authoring | 親contract・request・frontierから次のtyped contractを作る |
| WriterView review / revise | proseへ渡す制約を完全・簡潔に保つ |
| render / rerender / coverage | required beatとend constraintの検証可能なdraft evidenceを作る |
| draft audit | 実際のdraft quoteに根ざしたtyped issueだけを報告する |
| draft revise | 指摘されたissueを直し、保護coverageを壊さない |

## 安全規約

- schema、prompt、production adapterの入力変数を別々に変更しない。
- promptはruntimeが推測して補うことを期待しない。必要な入力と出力を明示する。
- JSON/schema failureは`quality.max_generation_attempts`まで再生成する。各試行はevidenceとして保存される。
- hard findingをreview上限で選択・exportへ進めない。
- `quality` major/minorのdeferred判断はpromptではなく、最終DraftAuditとQualityDispositionのruntime規約で行う。

## 検証

prompt変更後は少なくともtask registry test、production adapter test、対応contract/writer testを実行する。real-model smokeではraw request、response、parsed payload、validation、audit issueをattempt単位で確認する。
