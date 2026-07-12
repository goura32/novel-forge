# NovelForge用語集

最終更新: 2026-07-12

## A〜Z

| 用語 | 説明 |
|---|---|
| Artifact | immutable payload、manifest、ready markerからなる成果物。ready検証前のpayloadは参照しない |
| Artifact manifest | artifact ID、logical key、payload path、digest、入力artifact、prompt/schema digestを記録するメタデータ |
| Attempt | 1回のLLM呼び出しまたは決定論的処理の不変記録。`attempt.json` とeventで状態を追跡する |
| Canon | Canon seedとactive Canon eventのreplayで得られる現在の設定・事実 |
| Canon frontier | sceneごとの選択済みCanon eventを表すimmutable artifact。後続snapshotが参照する |
| LLM evidence | LLM attempt配下のrequest、NDJSON response、content、parsed、validation記録 |
| Selection snapshot | 後続runが読むlogical key → artifact IDの不変な入力集合 |

## あ行

| 用語 | 説明 |
|---|---|
| あらすじ (logline) | シリーズの核心を1〜2文で表す説明 |
| 暗黙承認 | CLI上の人手承認ステップではなく、選択snapshotへ公開されたartifactだけが後続工程へ進むこと |

## か行

| 用語 | 説明 |
|---|---|
| 作業ディレクトリ (workdir) | `.novel-forge/` runtimeデータを置くルート。`--workdir` またはcanonical configの `workspace.root` で指定 |
| 生成contract failure | JSON parse、Schema validation、task contractに失敗したLLM応答。retry上限内で別attemptとして再実行する |
| シリーズ (series) | 複数巻からなる小説シリーズ。slugでledgerとsnapshotを区別する |
| シリーズ企画 (`plan.series`) | title、logline、世界観、人物、各巻の前提を含む選択済みplan artifact |
| スラグ (slug) | シリーズ識別子。英小文字・数字・アンダースコアで表す |

## さ行

| 用語 | 説明 |
|---|---|
| scene summary | 次sceneへ渡すcontinuity handoff。writer-safeな状態変化・未解決thread・次sceneへの引き継ぎを含む |
| スキーマ (schema) | LLM出力の型・必須field・構造を検証するJSON Schema |

## は行

| 用語 | 説明 |
|---|---|
| 品質ゲート | review issue、Schema、deterministic contractを用い、未解決候補の選択を止める仕組み |
| パイプライン | `plan → design → write → export` の一連の工程 |
| 非LLM attempt | Canon適用、artifact commit、scene受理など、LLM requestを発行しない決定論的attempt |

## ら行

| 用語 | 説明 |
|---|---|
| リトライ (retry) | contract failure時に新しいattemptを作って生成を再実行すること。transport errorは自動retryしない |
| ロック (lock) | workspaceまたはseries単位で変更系commandを排他する仕組み。`--wait-lock` で待機できる |
