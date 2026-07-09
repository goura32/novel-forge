# NovelForge Architecture

## 状態の区別

このリポジトリには、現在稼働する v1 runtime と、未実装の Series Bible v2 設計があります。混同しないことが最重要です。

| 対象 | 現在の状態 | 正本 |
|---|---|---|
| 制作 runtime | 稼働中。`bible.json` / `blackboard.json` を使用 | 実装とテスト |
| Series Bible v2 | 承認済み、未実装の破壊的再設計 | [SERIES_BIBLE_SCHEMA_REDESIGN](SERIES_BIBLE_SCHEMA_REDESIGN.md) |

v2 が実装されるまでは、v1 artifact と prompt / schema が runtime の実態です。v2 を既存 CLI の機能として記述してはいけません。

## レイヤー

| レイヤー | 主なモジュール | 責務 |
|---|---|---|
| CLI | `cli.py` | Typer command、引数、表示 |
| Orchestration | `engine/` | plan / design / write / export / resume / status と lock、状態遷移 |
| Generation | `llm_task.py`、`scene_writer.py`、`engine/review.py` | LLM 生成、レビュー、改稿 |
| Domain | `models.py`、`bible_manager.py`、`context_builder.py` | project / volume / scene と v1 Bible の状態 |
| Infrastructure | `llm_client.py`、`prompts.py`、`schemas.py`、`storage.py`、`repository.py` | Ollama 通信、prompt 展開、schema 検証、永続化、raw log |

## 現行データフロー

```text
keywords
  → plan()       → <series>/series_plan.json
  → design()     → <series>/volNN/volNN.json と章・シーン設計
  → write()      → scene draft / v1 blackboard.json / v1 bible.json
  → export()     → exports/<slug>_volNN.{md,metadata.json,kdp_readiness_report.md}
```

- `plan` は concept、characters、volumes を生成し、series slug を確定します。
- `design` は volume、chapter、scene の順に設計します。
- `write` は scene draft、review、revision、要約・v1 Bible 更新を行います。
- `export` は scene artifact を preflight し、原稿と提出前レポートを出力します。現行 v1 runtime の readiness report は Bible の未回収伏線・未完サブプロットも参照します。

## Prompt と JSON Schema

`PromptManager.render()` は prompt 内の `{schema}` を対応する Schema の簡略化表現へ自動展開します。その後、変数を置換します。各 LLM 呼び出しは `LLMClient.complete_json()` を通り、JSON parse、Schema 検証、工程固有の semantic validation を受けます。

対応一覧は [PROMPT_SCHEMA_MAP](../PROMPT_SCHEMA_MAP.md)、変更時の手順は [schema_maintenance](schema_maintenance.md) を参照してください。

## 実行状態と回復

- `state.json` はシリーズ・巻・シーンの進捗を保存します。
- write は scene 単位で保存し、`resume` は保存状態から次工程を選びます。
- 同一シリーズの変更系 command は lock で排他します。
- `-v` を付けた実行では `_raw_logs/` に LLM 呼び出しの request / response を保存します。

## Series Bible v2 実装後の境界

v2 実装では、`canon_events.jsonl` を正本、`bible.json` を replay 生成物とし、review 合格済み `scene_design.canon_patch` だけが Canon を更新します。`CanonSliceBuilder` が stage / Context scope から projection を構築し、writer は `writer_context` と直近 summary だけを受け取ります。

この移行により、現行の runtime Bible update、`Blackboard.facts`、writer の Bible load は削除対象です。詳細な設計・移行順・受入条件は [Series Bible v2 決定書](SERIES_BIBLE_SCHEMA_REDESIGN.md) だけを参照してください。
