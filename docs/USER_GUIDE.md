# 使い方ガイド

NovelForge は Ollama を用いて、シリーズ小説を `plan → design → write → export` の順に制作します。工程間の入力はselection snapshotで固定され、成果物はimmutable artifactとして保存されます。

## 1. 導入と接続確認

```bash
git clone https://github.com/goura32/novel-forge.git
cd novel-forge
uv venv --python 3.14 .venv
uv pip install -e .

mkdir -p ~/.config/novel-forge
cp config.example.yaml ~/.config/novel-forge/config.yaml
uv run novel-forge doctor
```

設定の正規パスは `~/.config/novel-forge/config.yaml` です。既定モデルは `qwen3.6:35b-a3b-mtp-q4_K_M` です。`doctor` が失敗した場合は、Ollamaの起動、モデル名、`llm.ollama_host` を確認してください。

## 2. 新規シリーズを作る

```bash
uv run novel-forge plan -w <workdir> "近未来東京 記憶探偵"
```

`plan` はseries slug、`plan.series` artifact、Canon seed、最初のselection snapshotを作成します。表示されたslugを後続コマンドの `-s <series-slug>` に使います。

キーワードにはジャンル・主人公・舞台・対立・テーマを含めると設計が安定します。詳しくは [キーワード選定ガイド](KEYWORD_SELECTION_GUIDE.md) を参照してください。

## 3. 巻を設計・執筆・出力する

```bash
# Volume Contractを設計する
uv run novel-forge design -w <workdir> -s <series-slug> -V 1

# Chapter ContractとScene Contractまで設計する（例: 第1巻・第1章・scene 1）
uv run novel-forge design -w <workdir> -s <series-slug> -V 1 --chapter 1 --scene 1

# 本文を生成・監査し、選択snapshotに不変のDesignBundleをfreezeする
uv run novel-forge write -w <workdir> -s <series-slug> -V 1

# 既にfreeze済みのDesignBundleだけからMarkdown原稿を出力する（LLMは呼ばない）
uv run novel-forge export -w <workdir> -s <series-slug> -V 1 --format markdown
```

`write` と `export` は分離されています。`export` は草稿生成やauditを再実行せず、現在の選択snapshotの `pnca.design_bundle.<series>.<volume>` を検証して出力します。audit issueが一つでも未解決なら出力しません。

全巻を設計する場合は `design -V 0` を使います。初回から新規シリーズを一括実行する場合は次のとおりです。

```bash
uv run novel-forge complete -w <workdir> "近未来東京 記憶探偵"
```

`complete` は `plan → design → write → export` を順に実行し、Markdown原稿 artifact まで作成します。

## 4. 成果物と証跡を確認する

主な成果物は `<workdir>/.novel-forge/runs/<run>/attempts/<attempt>/artifacts/` に作成されます。

| payload名 | 内容 |
|---|---|
| `design_bundle.json` | 本文・WriterView・audit・output frontier をpinした不変のDesignBundle |
| `manuscript.md` | DesignBundleから再現された読者向けMarkdown本文 |

LLMを呼ぶattemptは同じattempt配下の `llm/` に、送信payload・生NDJSON・最終content・parse結果・validation結果を保存します。`--verbose` はコンソールログ量を変えるだけで、evidence保存の有無を変えません。

```bash
uv run novel-forge runs active -w <workdir>
uv run novel-forge run show -w <workdir> <run-id>
uv run novel-forge attempt show -w <workdir> <attempt-id>
```

`export` は選択snapshotにpinされたDesignBundleの Scene Contract・WriterView・draft・audit・output frontier を型・digest・provenanceで検証してから出力します。DOCX / EPUBやKDP提出用メタデータは出力しないため、提出前の人による整形・確認は別途必要です。

## 5. 中断から再開する

```bash
uv run novel-forge status -w <workdir> -s <series-slug>
uv run novel-forge resume -w <workdir> -s <series-slug>
```

同一シリーズに並行した変更系コマンドは実行できません。lock待機が必要な場合は `--wait-lock` を付けます。LLM contract errorやlockの対応は [OPERATIONS](OPERATIONS.md) を参照してください。

## 6. 設定の優先順位

1. 各コマンドのCLI引数（例: `--workdir`、`--model`）
2. `~/.config/novel-forge/config.yaml`
3. built-in既定値

`--workdir` を省略した場合は、設定の `workspace.root` が必要です。設定例は [`config.example.yaml`](../config.example.yaml) にあります。
