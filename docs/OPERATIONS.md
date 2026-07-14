# 運用 Runbook

## 標準フロー

```bash
novel-forge plan -w <workdir> "テーマ"
novel-forge design -w <workdir> -s <slug> -V 1
novel-forge design -w <workdir> -s <slug> -V 1 -C 1
novel-forge design -w <workdir> -s <slug> -V 1 -C 1 -S 1
novel-forge write -w <workdir> -s <slug> -V 1
novel-forge export -w <workdir> -s <slug> -V 1
```

Volume、Chapter、Sceneは別々のacceptance boundaryです。`design --chapters`は存在しません。`complete`も存在しません。

## 設定とretry

canonical configは `~/.config/novel-forge/config.yaml` です。

```yaml
quality:
  max_generation_attempts: 3
```

この値はJSON/schema contract failureに限る総生成試行数です。transport errorは1 attemptで停止します。hard repairは最大2回、quality polishは最大1回で、設定変更できません。

## 進捗とevidence

進捗eventは次にappendされます。

```text
<workdir>/.novel-forge/runs/<run-id>/events.jsonl
```

LLM呼出しごとに別attemptが作られます。retryした場合も各試行は独立した`attempt.json`、`error.json`または`completion.json`、`llm/` evidenceを持ちます。

```bash
novel-forge runs -w <workdir>
novel-forge run -w <workdir> <run-id>
novel-forge attempt -w <workdir> <attempt-id>
novel-forge llm -w <workdir> <attempt-id>
```

## failureの扱い

| 状態 | 対応 |
|---|---|
| JSON/schema contract failure | `max_generation_attempts`の範囲で自動retry。全失敗ならevidenceを調査 |
| transport failure | 自動retryしない。provider / networkを直して工程を再実行 |
| hard / non-quality audit finding | bundleを作らず停止。prompt、schema、contract、draft evidenceを調査 |
| deferred editorial debt | dispositionがbundleへpinされていればexport可能。release判断で確認 |
| export validation failure | bundleのaudit / disposition / provenance不整合。再生成ではなくartifact根拠を調査 |

## 復旧

immutable artifactは上書きしません。失敗runのattempt evidenceを確認し、原因を直して該当コマンドを新しいrunとして実行します。selected snapshotや既存artifactを手編集して回復してはいけません。
