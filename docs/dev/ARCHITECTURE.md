# 現行 PNCA Architecture

## 状態

この文書は現行production pathの正本です。production rootは`PNCAWorkflow`、`PNCAContractAuthor`、`PNCATaskExecutor`、`PNCAExporter`です。旧`RuntimeWorkflow`、`workflow_runtime.py`、`workflow_task_runner.py`は現行pathではありません。

## 境界

| 層 | 実装 | 責務 |
|---|---|---|
| CLI | `cli.py` | run、lock、selected snapshotの取得、公開コマンド |
| Contract authoring | `pnca/workflow.py` / `pnca/production.py` | Series / Volume / Chapter / Scene Contractのauthorとaccept |
| Task registry | `pnca/defaults.py` / `pnca/registry.py` | task ID、prompt、schema、入力projection、出力境界 |
| Writer | `pnca/writer.py` | WriterView、render、coverage、audit、revision |
| Quality gate | `pnca/workflow.py` / `pnca/contracts.py` | hard failureとdeferred editorial debtの決定 |
| Export | `pnca/export.py` | frozen bundleのprovenance・audit・dispositionを最終検証 |
| Runtime | `runtime.py` | append-only run / attempt / artifact / snapshot / acceptance |

## Phase flow

```text
plan:   Series Contract → accept Series root
 design: Volume Contract → accept
         Chapter Contract → accept
         Scene Contract + FrontierBinding → atomic scene acceptance
 write:  Scene Contract → WriterView → Draft → DraftAudit → QualityDisposition → DesignBundle
export:  frozen DesignBundle → Markdown manuscript artifact
```

Volume / Chapter / Sceneは別々のCLI invocationとacceptance boundaryです。Scene Contractは正確なbase snapshotとFrontierBindingをpinします。

## LLM taskとretry

PNCA taskはregistryでallow-listされます。JSON/schema contract failureは`quality.max_generation_attempts`の範囲で再生成し、各試行を別attemptとして保存します。初回も回数に含みます。transport failureはretryしません。

## Reviewと進行

- blockerは最大2回のhard repair後も残れば停止します。
- `constraint_kind != quality`はseverityに関係なく停止します。
- `quality`のmajor/minorだけは最大1回polish後、残れば`deferred`にできます。
- `QualityDisposition`はwrite phaseでのみ作成され、DesignBundle slotにpinされます。
- exportはDraftAuditとQualityDispositionを再照合します。hard finding、`clean`に隠れたissue、deferred findingの不一致は拒否します。

## Export

export形式はMarkdownのみです。payload名は`manuscript.md`です。exportはselected/latest mutable Canon stateを読まず、bundle slotにpinされたcontract、view、draft、assessment、disposition、frontierだけを読む設計です。
