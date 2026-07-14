# 用語集

| 用語 | 定義 |
|---|---|
| PNCA | Progressive Narrative Contract Architecture。契約を段階的にauthor・acceptするproduction path。 |
| artifact | attemptからcommitされるimmutable payloadとmanifest。 |
| run | 一つのCLI実行の監査単位。 |
| attempt | 一回のLLM呼出しまたはdeterministic処理の証跡単位。retryごとに新規作成される。 |
| Selection Snapshot | seriesの選択済みartifact slotをimmutableに記録する状態境界。 |
| acceptance | materialized contractをselection snapshotへ原子的にpublishする操作。 |
| FrontierBinding | Scene Contractが読むinput snapshot / Canon frontier / digestの組。 |
| WriterView | Scene Contractをprose writerへ必要最小限に投影したartifact。 |
| DraftAudit | scene draftに対するtyped issue集合。 |
| QualityDisposition | write phaseのaudit residualを`clean`または`deferred`としてimmutableに決定するartifact。 |
| clean | DraftAudit issueがゼロであるdisposition。残件を隠せない。 |
| deferred | `quality`の`major`/`minor` residualだけを、audit issueとの完全対応つきで記録するdisposition。 |
| non-waivable finding | blockerまたは`constraint_kind != quality`のissue。write / exportとも停止する。 |
| editorial debt | deferredに記録できるquality residual。release前の人間判断対象。 |
| DesignBundle | export対象のfrozen scene slot集合。contract、view、draft、audit、disposition、frontierをpinする。 |
| generation attempt | LLMに一回送信する試行。`quality.max_generation_attempts`は初回を含む上限。 |
| hard repair | blocker除去のためのrevision。最大2回。 |
| quality polish | editorial qualityのためのrevision。最大1回。 |
