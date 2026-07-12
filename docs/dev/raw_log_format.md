# Attempt-scoped LLM evidence形式

最終更新: 2026-07-12

LLM evidenceは `--verbose` の有無にかかわらず、LLMを実行した各attemptへ保存されます。旧raw-logディレクトリ、gzip、summary directoryは現行runtimeでは使用しません。

```text
<workdir>/.novel-forge/runs/
  <run-id>/
    attempts/
      <attempt-id>/
        attempt.json
        llm/
          request.json
          response.ndjson
          response.content.json
          parsed.json
          validation.json
        error.json                 # failure attemptのみ
```

`attempt-id` は `att_<6桁連番>_<task-idのドットをアンダースコア化>_<6桁hex>` の形式です。例: `att_000001_write_draft_generate_041a4f`。

## ファイルの意味

| ファイル | 保存条件 | 内容 |
|---|---|---|
| `attempt.json` | 全attempt | run ID、task ID、phase、model、seed、retry番号、開始時刻 |
| `llm/request.json` | LLM呼び出し | Ollamaへ送るrequest payload |
| `llm/response.ndjson` | 応答を受信 | 受信したNDJSON response records |
| `llm/response.content.json` | 非空contentを受信 | 結合済み `message.content` |
| `llm/parsed.json` | parse・Schema validation成功 | 検証済みの構造化出力 |
| `llm/validation.json` | LLM呼び出し | `passed` またはJSON parse / Schema validation失敗の結果 |
| `error.json` | failure attempt | transportまたはruntime failureの分類情報 |

`parsed.json` がないことだけではraw evidence欠損を意味しません。JSON parseまたはSchema validationに失敗したattemptでは、request・response・validationは残りますが、検証済みparsed objectは存在しません。

Canon適用、artifact commit、scene受理などの決定論的attemptはLLMを呼ばないため、`llm/` を持ちません。

## 調査コマンド

```bash
uv run novel-forge run show -w <workdir> <run-id>
uv run novel-forge attempt show -w <workdir> <attempt-id>
uv run novel-forge llm diff -w <workdir> <attempt-a> <attempt-b>
uv run novel-forge llm diff -w <workdir> --metadata-only <attempt-a> <attempt-b>
```

`llm diff` は両attemptに `request.json`、`response.content.json`、`parsed.json` がある場合に内容比較を行います。validation失敗attemptは、個別の `validation.json` とraw responseを確認してください。

## 取り扱い

requestにはprompt・入力context、responseには生成本文やthinkingを含み得ます。workdir全体を機密成果物として扱い、Gitへの追加や外部共有を行う前に内容を確認してください。
