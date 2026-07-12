# CLIリファレンス

最終更新: 2026-07-12。実行環境では常にlive helpを正としてください。

```bash
uv run novel-forge --help
uv run novel-forge <command> --help
```

## 共通オプション

| オプション | 対象 | 内容 |
|---|---|---|
| `-w, --workdir PATH` | workdirを扱うcommand | 作業ディレクトリ。省略時はcanonical configの `workspace.root` |
| `-s, --series TEXT` | `design` / `write` / `export` / `resume` / `status` | 対象シリーズのslug |
| `-m, --model TEXT` | LLM関連command | モデル名を上書き |
| `--max-review-count INTEGER` | LLM関連command | review → reviseサイクルの上限 |
| `--max-summary-review-count INTEGER` | LLM関連command | summary review → reviseサイクルの上限 |
| `-v, --verbose` | LLM関連command | 詳細なコンソールログを表示。LLM evidenceは常時保存される |
| `--wait-lock` | 変更系command | run / series lockを待機し、即時失敗を避ける |

生成JSONやSchemaのcontract失敗は `quality.max_retry_count` の範囲で再試行されます。これはCLIオプションではなくcanonical configの設定です。transport errorは自動再試行せず、1件の失敗attemptとして記録されます。

## `plan`

```bash
uv run novel-forge plan -w <workdir> "keyword1 keyword2"
```

キーワードからシリーズ企画、Canon seed、series slug、初回selection snapshotを生成します。`KEYWORDS` は必須の位置引数です。

## `design`

```bash
uv run novel-forge design -w <workdir> -s <series-slug> -V 1
```

巻・章・scene設計を生成し、review済みのCanon eventをfrontierへ公開します。

| オプション | 既定値 | 内容 |
|---|---:|---|
| `-V, --volume INTEGER` | `1` | 対象巻。`0` は全巻 |

## `write`

```bash
uv run novel-forge write -w <workdir> -s <series-slug> -V 1
```

対象巻のscene draft、draft review / revise、continuity summaryとsummary review / reviseを生成します。

| オプション | 既定値 | 内容 |
|---|---:|---|
| `-V, --volume INTEGER` | `1` | 対象巻 |

## `export`

```bash
# immutable JSON artifact（既定）
uv run novel-forge export -w <workdir> -s <series-slug> -V 1
# 読者向けMarkdown原稿
uv run novel-forge export -w <workdir> -s <series-slug> -V 1 --format markdown
```

選択snapshotにpinされた設計・Canon・全sceneのdraft / summary / final reviewを検証して、immutable artifactを出力します。

| オプション | 既定値 | 内容 |
|---|---:|---|
| `-V, --volume INTEGER` | `1` | 対象巻 |
| `--format TEXT` | `json` | `json` はCanonとreview reportを含む監査用artifact、`markdown` は読者向け本文artifact |

出力は `<workdir>/.novel-forge/runs/<run>/attempts/<attempt>/artifacts/` に保存されます。Markdownのpayload名は `export.volNN.manuscript.md` です。DOCX / EPUBは出力しません。

## `complete`

```bash
uv run novel-forge complete -w <workdir> "keyword1 keyword2"
```

新規シリーズに対して `plan → design → write → export` を順に実行します。export形式はJSON既定です。

## `status` / `resume`

```bash
uv run novel-forge status -w <workdir> -s <series-slug>
uv run novel-forge resume -w <workdir> -s <series-slug>
```

`status` はシリーズと現在のselection状態を表示します。`resume` は選択済みartifactから次工程を再開します。

## 診断・読み取り専用監査

```bash
uv run novel-forge doctor -w <workdir>
uv run novel-forge list -w <workdir>
uv run novel-forge runs active -w <workdir>
uv run novel-forge run show -w <workdir> <run-id>
uv run novel-forge attempt show -w <workdir> <attempt-id>
uv run novel-forge llm diff -w <workdir> <attempt-a> <attempt-b>
uv run novel-forge artifact diff -w <workdir> <artifact-a> <artifact-b>
```

`doctor` はOllama接続とモデルを確認します。`llm diff` はcapture済みのrequest / response / parsed evidenceを比較し、`artifact diff` は検証済みartifact payloadを比較します。
