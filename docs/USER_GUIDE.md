# 使い方ガイド

NovelForge は Ollama を用いて、シリーズ小説を `plan → design → write → export` の順に制作します。

## 1. 導入と接続確認

```bash
git clone https://github.com/goura32/novel-forge.git
cd novel-forge
uv venv --python 3.14 .venv
uv pip install -e .

# 任意: 既定値を固定したい場合
cp config.example.yaml config.yaml
uv run novel-forge doctor
```

`doctor` が成功しない場合は、Ollama の起動、モデル名、ホストを確認してください。既定モデルは `qwen3.6:35b-a3b-mtp-q4_K_M` です。

## 2. 新規シリーズを作る

```bash
uv run novel-forge plan -w <workdir> "近未来東京 記憶探偵"
```

`plan` は `<workdir>/<series-slug>/series_plan.json` を作成します。表示された slug を以後のコマンドに使います。

キーワードは、ジャンル・主人公・舞台・対立・テーマを混ぜると設計が安定します。詳しくは [キーワード選定ガイド](KEYWORD_SELECTION_GUIDE.md) を参照してください。

## 3. 巻を設計・執筆・出力する

```bash
# 1巻を設計
uv run novel-forge design -w <workdir> -s <series-slug> -V 1

# 草稿を生成・レビュー・改稿
uv run novel-forge write -w <workdir> -s <series-slug> -V 1

# 原稿と準備完了レポートを出力
uv run novel-forge export -w <workdir> -s <series-slug> -V 1
```

全巻を設計する場合は `design -V 0` を使います。初回から一括実行したい場合は次のとおりです。

```bash
uv run novel-forge complete -w <workdir> "近未来東京 記憶探偵"
```

## 4. 成果物を確認する

主な成果物は `<workdir>/<series-slug>/` に作成されます。

| パス | 内容 |
|---|---|
| `series_plan.json` | シリーズ企画 |
| `volNN/volNN.json` | 巻・章・シーン設計 |
| `volNN/volNN_chNN/*_v*.md` | シーン草稿・改稿 |
| `exports/<slug>_volNN.md` | 結合済み原稿 |
| `exports/<slug>_volNN_metadata.json` | 最小メタデータ |
| `exports/<slug>_volNN_kdp_readiness_report.md` | 提出前の確認レポート |

`export` は設計上の全シーンに空でない草稿があることを確認してから出力します。準備完了レポートの警告を確認してから提出してください。

## 5. 中断から再開する

```bash
uv run novel-forge status -w <workdir> -s <series-slug>
uv run novel-forge resume -w <workdir> -s <series-slug>
```

`resume` は保存済み状態から次の工程を選びます。ロックや LLM エラーへの対応は [OPERATIONS](OPERATIONS.md) を参照してください。

## 6. 設定の優先順位

1. CLI 引数
2. `NOVEL_FORGE_CONFIG`
3. `--workdir` の `config.yaml`（series dir の場合は親も確認）
4. カレントディレクトリから親方向に探索した `config.yaml`
5. built-in 既定値

設定例は [`config.example.yaml`](../config.example.yaml) にあります。
