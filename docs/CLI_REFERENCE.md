# CLI リファレンス

## 共通事項

- runtime設定は `~/.config/novel-forge/config.yaml` のみを読みます。
- `--workdir` は設定の`workspace.root`より優先されます。
- `--model`はそのrunだけのLLM model overrideです。
- `--wait-lock`は既存run lockの解放を待ちます。
- JSON/schema contract failureだけは`quality.max_generation_attempts`まで再試行します。初回を含みます。transport errorはretryしません。

## 変更するコマンド

| コマンド | 主要引数 | 結果 |
|---|---|---|
| `plan KEYWORDS` | `-w`, `-m`, `--volumes` | Series Contract / Canon rootをaccept |
| `design` | `-V`, `-C`, `-S`, `-w`, `-s`, `-m` | Volume / Chapter / Scene Contractを一段ずつaccept |
| `write` | `-V`, `-w`, `-s`, `-m` | scene draft、audit、QualityDisposition、DesignBundleを作成 |
| `export` | `-V`, `-w`, `-s`, `--format markdown` | frozen bundleからMarkdown原稿artifactを作成 |
| `resume` | `-V`, `-w`, `-s`, `-m` | 指定巻のwriteとexportを実行 |

`design -S`には`-V >= 1`と`-C >= 1`、およびselected Chapter Contractが必要です。

## Export

利用可能なformatは`markdown`だけです。payload名は`manuscript.md`です。

```bash
novel-forge export -w <workdir> -s <slug> -V 1
```

exportはnew auditやdispositionを生成しません。bundleにpin済みのdraft、audit、disposition、frontierを検証してから原稿を出力します。

## 読み取り専用コマンド

| コマンド | 用途 |
|---|---|
| `status` | selected snapshotとslotを表示 |
| `list` | workdir内のseriesを列挙 |
| `runs` / `run` / `attempt` | immutable run / attemptの調査 |
| `llm` | attempt-scoped LLM evidenceの調査・比較 |
| `artifact` | artifactの表示・比較 |
| `doctor` | Ollama接続・model readinessの診断 |

## 固定されたreview budget

hard blockerのrepairは最大2回、editorial quality polishは最大1回です。これらを上書きするCLI optionやconfig keyはありません。
