# CLI_REFERENCE — コマンド一覧

> **Note**: 次のコマンドで最新情報を取得可能
> ```bash
> uv run novel-forge --help
> uv run novel-forge <command> --help
> ```

---

## 全般

| オプション | 説明 | デフォルト |
|---|---|---|
| `--workdir, -w` | 系列の出力先ディレクトリ | `.` |
| `--model, -m` | Ollama のモデル名 | `qwen3.6:35b-a3b-mtp-q4_K_M` |
| `--max-generation-count` | LLM API + validation リトライ最大数（同一工程内） | 3 |
| `--max-review-count` | レビュー→修正サイクルの最大回数（複数工程にわたる） | 7 |
| `-v, --verbose` | 詳細ログ出力 | false |
| `--raw-log` | LLM raw data を `_raw_logs/` に保存する | false |

---

## plan

```
uv run novel-forge plan -w <dir> "keyword1 keyword2 keyword3"
```

**役割**: キーワードからシリーズ企画（コンセプト、キャラクター、各巻構成）を生成。最終的に `series_plan.json` を作成。

| オプション | 説明 | デフォルト |
|---|---|---|
| `keywords` (必須) | スペース区切りのキーワード | — |

**補足**: `--strict` フラグは廃止済み。schema validation failure で即座に停止します。

---

## design

```
uv run novel-forge design -w <dir> [-V 0｜1｜2… ]
```

**役割**: シリーズ企画にもとづき巻のデザイン（章構成→章設計→シーン設計）を生成する。

| オプション | 説明 | デフォルト |
|---|---|---|
| `-V, --volume` | 対象の巻番号。`0` で全巻一括生成 | 1 |

**補足**: `series_plan.json` が存在しないとエラーになる。design は自動レビュー + リトライ付き。

---

## write

```
uv run novel-forge write -w <dir>
```

**役割**: シーン草稿を執筆。Blackboard / Bible による継続性（伏線、キャラクター変化）を保つ。

| オプション | 説明 | デフォルト |
|---|---|---|
| `-V, --volume` | 対象巻番号 | 1 |

**補足**: schema validation → review → revise ループ付き。最大回数に達すると停止します。

---

## export

```
uv run novel-forge export -w <dir>
```

**役割**: 完成原稿を markdown/KDP用パッケージとして出力する。

| オプション | 説明 | デフォルト |
|---|---|---|
| `-V, --volume` | 巻番号 | 1 |

**出力ファイル**:
- `exports/<slug>_volNN.md` — シーン本文を結合した原稿
- `exports/<slug>_volNN_metadata.json` — タイトル案、説明文、カテゴリ、キーワード
- `exports/<slug>_volNN_kdp_readiness_report.md` — KDP 出版準備度レポート

---

## complete

```
uv run novel-forge complete -w <dir> "keyword1 keyword2"
```

**役割**: `plan → design → write → export` を一度に実行する。各工程の中間状態を skip する場合や、一発で完走したい場合に便利。

---

## resume / status

```
uv run novel-forge resume -w <dir>    # 中断した工程から再開
uv run novel-forge status -w <dir>    # プロジェクトのステータスとロック状況を表示
```

| ステータス | 意味 |
|---|---|
| PlanCreated | 企画済み。次は design |
| DesignReady | 設計済。次は write |
| Writing | シーン執筆中 |
| DraftComplete | 初稿完了。次は export |
| Exported | エクスポート済み |

---

## doctor / list

```
uv run novel-forge doctor                         # Ollama 接続・モデルの確認
uv run novel-forge list -w <dir>                   # そのディレクトリ配下の一覧表示
```
