# CLI リファレンス

この文書は 2026-07-10 に取得した `novel-forge --help` と各 command help を基準にしています。実行環境では常に次を正としてください。

```bash
uv run novel-forge --help
uv run novel-forge <command> --help
```

## 共通オプション

| オプション | 対象 | 内容 |
|---|---|---|
| `-w, --workdir PATH` | 全 command | 作業ディレクトリ。既定値は `.` |
| `-s, --series TEXT` | plan 以外のシリーズ操作 | 対象シリーズの slug |
| `-m, --model TEXT` | LLM を使う command | モデル名を上書き |
| `--max-generation-count INTEGER` | plan / design / write / complete | API・JSON・検証失敗を含む生成試行の上限 |
| `--max-review-count INTEGER` | plan / design / write / complete | レビュー→改稿サイクルの上限 |
| `-v, --verbose` | LLM を使う command | 詳細ログと raw LLM log を有効化 |

`--strict` は存在しません。schema / semantic validation に失敗した生成は、生成上限まで再試行します。

## `plan`

```bash
uv run novel-forge plan -w <workdir> "keyword1 keyword2"
```

キーワードからシリーズ企画と slug を生成します。`KEYWORDS` は必須の位置引数です。

## `design`

```bash
uv run novel-forge design -w <workdir> -s <series-slug> -V 1
```

巻・章・シーン設計を生成します。

| オプション | 既定値 | 内容 |
|---|---:|---|
| `-V, --volume INTEGER` | `1` | 対象巻。`0` は全巻 |

## `write`

```bash
uv run novel-forge write -w <workdir> -s <series-slug> -V 1
```

対象巻のシーン草稿を生成し、レビューと改稿を行います。

| オプション | 既定値 | 内容 |
|---|---:|---|
| `-V, --volume INTEGER` | `1` | 対象巻 |

## `export`

```bash
# immutable JSON artifact（既定）
uv run novel-forge export -w <workdir> -s <series-slug> -V 1
# 人が読むためのMarkdown原稿
uv run novel-forge export -w <workdir> -s <series-slug> -V 1 --format markdown
```

選択snapshotにpinされた設計・Canon・全sceneのdraft / summary / final reviewを検証して、runtime run配下のimmutable artifactを出力します。

| オプション | 既定値 | 内容 |
|---|---:|---|
| `--format TEXT` | `json` | `json` はCanonとreview reportを含む監査用artifact、`markdown` は巻・章・scene見出しを持つ読者向け本文artifact |

出力は `*.novel-forge/runs/<run>/attempts/<attempt>/artifacts/` に保存されます。`markdown` のpayload名は `export.volNN.manuscript.md` です。DOCX / EPUBは出力しません。

## `complete`

```bash
uv run novel-forge complete -w <workdir> "keyword1 keyword2"
```

`plan → design → write → export` を順に実行します。必要に応じて `-V`、モデル、生成/レビュー上限、verbose を指定できます。

## `status` / `resume`

```bash
uv run novel-forge status -w <workdir> -s <series-slug>
uv run novel-forge resume -w <workdir> -s <series-slug>
```

`status` はシリーズと現在巻の進捗を表示します。`resume` は保存済み状態から次に実行すべき工程を再開します。

## `doctor` / `list`

```bash
uv run novel-forge doctor -w <workdir>
uv run novel-forge doctor --ollama-host localhost:11434
uv run novel-forge list -w <workdir>
```

`doctor` は Ollama 接続と指定モデルを確認します。`list` は workdir 内のシリーズを表示します。
