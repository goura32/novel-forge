# NovelForge

NovelForge はOllamaでシリーズ小説を **企画 → 設計 → 執筆 → 出力** する、PNCA-onlyのPython CLIです。すべての工程はimmutable run / attempt / artifact と selection snapshot を使い、入力・判断・出力を追跡可能にします。

> **出版品質は保証しません。** exportは読者向けMarkdown原稿を作ります。DOCX / EPUB / KDP提出用データは出力しないため、提出前に人が原稿を整形・確認してください。

## セットアップ

```bash
git clone https://github.com/goura32/novel-forge.git
cd novel-forge
uv venv --python 3.14 .venv
uv pip install -e .
mkdir -p ~/.config/novel-forge
cp config.example.yaml ~/.config/novel-forge/config.yaml
uv run novel-forge doctor
```

runtimeは `~/.config/novel-forge/config.yaml` だけを読みます。作業フォルダは `--workdir` または `workspace.root` で指定します。未知・廃止設定はエラーです。

## クイックスタート

```bash
uv run novel-forge plan -w <workdir> "近未来東京 記憶探偵"
uv run novel-forge design -w <workdir> -s <series-slug> -V 1
uv run novel-forge design -w <workdir> -s <series-slug> -V 1 -C 1
uv run novel-forge design -w <workdir> -s <series-slug> -V 1 -C 1 -S 1
uv run novel-forge write -w <workdir> -s <series-slug> -V 1
uv run novel-forge export -w <workdir> -s <series-slug> -V 1
```

`export`はMarkdown専用です。各工程は別runとして実行されるため、失敗した工程だけをevidenceから調査・再実行できます。

## 品質と進行

- JSON/schema contract failureは `quality.max_generation_attempts` の範囲で再生成します。初回も回数に含みます。
- transport/API failureは自動retryしません。
- hard finding（blockerまたは`constraint_kind != quality`）は停止します。
- `quality` の `major` / `minor` だけは、固定1回のpolish後に残れば`deferred`としてQualityDispositionへ記録できます。
- exportはfrozen DesignBundleを読むだけでなく、DraftAuditとQualityDispositionを再照合し、hard findingや不一致を拒否します。

## 主なコマンド

| コマンド | 役割 |
|---|---|
| `plan` | Series ContractとCanon rootをauthorしてaccept |
| `design` | Volume → Chapter → Scene Contractを一段ずつauthorしてaccept |
| `write` | Scene ContractからWriterView、draft、audit、disposition、DesignBundleを作成 |
| `export` | frozen DesignBundleからMarkdown manuscript artifactを出力 |
| `resume` | 指定巻のwriteとexportを再実行 |
| `status` / `runs` / `run` / `attempt` / `llm` / `artifact` | 読み取り専用の監査 |

## 成果物とLLM evidence

```text
<workdir>/.novel-forge/
  runs/<run-id>/attempts/<attempt-id>/
    attempt.json
    artifacts/
    llm/
      request.json
      response.ndjson
      response.content.json
      parsed.json
      validation.json
```

LLMを呼んだattemptにはevidenceが保存されます。schema/JSON failureのretryでは、各生成試行が別attemptとして残ります。

## ドキュメント

| 対象 | 読む文書 |
|---|---|
| 利用者 | [使い方](docs/USER_GUIDE.md) · [CLIリファレンス](docs/CLI_REFERENCE.md) · [運用runbook](docs/OPERATIONS.md) |
| 開発者 | [現行architecture](docs/dev/ARCHITECTURE.md) · [Prompt / Schema対応](docs/PROMPT_SCHEMA_MAP.md) · [品質disposition](docs/dev/QUALITY_DISPOSITION_POLICY.md) |
| 全体 | [ドキュメント索引](docs/INDEX.md) |

## 開発品質ゲート

```bash
uv run python scripts/check_dev_quality.py
uv run python scripts/check_dev_quality.py --full
```

## ライセンス

MIT
