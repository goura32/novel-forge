# Progressive Narrative Contract Architecture — Future Proposal

> **Future proposal / not implemented。現行production specificationとして使用しないでください。**

この文書が以前提案したCandidatePlan、candidate branch、3 ContractAudit、ReviewSynthesis、DecisionRecord、human waiver、slotごとのinput/output frontier chain、volume-end checkpointは、現在のproduction PNCAには実装されていません。

現行実装は、Series / Volume / Chapter / Scene Contractを段階的にauthorしてacceptし、write phaseでDraftAuditとQualityDispositionを作り、frozen DesignBundleをMarkdown exportします。

現行の安全契約は次です。

- blockerまたは`constraint_kind != quality`は停止する。
- quality major/minorのみ、最大1回polish後にdeferredとして記録できる。
- exportはbundleのauditとdispositionを再照合する。
- human waiver artifactやCandidatePlanは存在しない。

実装作業の正本は[ARCHITECTURE.md](ARCHITECTURE.md)と[QUALITY_DISPOSITION_POLICY.md](QUALITY_DISPOSITION_POLICY.md)です。
