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
uv run novel-forge export -w <workdir> -s <series-slug> -V 1
```

設計上の全シーンに空でない草稿があることを preflight で検査してから、次を出力します。

- `exports/<slug>_volNN.md` — 結合済み原稿
- `exports/<slug>_volNN_metadata.json` — タイトル・巻番号・言語のメタデータ
- `exports/<slug>_volNN_kdp_readiness_report.md` — 草稿状態・未回収要素などの確認レポート

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
