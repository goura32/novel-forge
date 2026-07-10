# NovelForge 用語集

## A〜Z

| 用語 | 説明 |
|---|---|
| Bible (bible.json) | **現行 v1 runtime** の設定資料集。キャラクター、用語、伏線、世界観ルール、関係性、サブプロットを管理する台帳。Series Bible v2 では `canon_events.jsonl` が正本となり、本ファイルは replay 生成物に降格する |
| Blackboard (blackboard.json) | **現行 v1 runtime** の事実記録。facts、シーン要約、引き継ぎメモ、サブプロット進捗、タイムラインを管理。Series Bible v2 では runtime discovery を禁止するため削除対象 |

## あ行

| 用語 | 説明 |
|---|---|
| あらすじ (logline) | シリーズの核心を1〜2文で表現。「誰が、何に、どう立ち向かうか」が伝わるもの |
| 暗黙承認 (implicit approval) | plan フェーズ完了後の人間確認。明示的な YES/NO ではなく、次工程へ進むこと自体が承認 |

## か行

| 用語 | 説明 |
|---|---|
| 会話の自然さ (dialogue_naturalness) | レビューカテゴリ。キャラクター口調が一貫し、説明的でないか |
| 環境変数 (environment variable) | `OLLAMA_HOST`, `NOVEL_FORGE_CONFIG` 等の設定 |
| 強制出力済 (forced output) | 品質ゲート不合格が規定回数繰り返されたシーン。最終手段として出力される |
| 共通システムプロンプト (system.md) | 全プロンプト共通の前提条件・制約（言語制約、JSON出力、共通役割） |
| 言語純度 (language_purity) | レビューカテゴリ。日本語文脈で不自然な簡体字、中国語構文、英語混在、ハングル混在がないか。自然なカタカナ語、英語表記、英字略語、一般的なジャンル語、固有名詞、日本語として成立する漢語は問題にしない |

## さ行

| 用語 | 説明 |
|---|---|
| 作業ディレクトリ (workdir) | シリーズデータのルートディレクトリ。`--workdir` で指定 |
| 系列 (series) | 複数巻からなる小説シリーズ全体 |
| シリーズ企画 (series_plan.json) | タイトル、あらすじ、ジャンル、世界観、キャラクター、各巻設計 |
| 衝突 (conflict) | シーン内で主人公が直面する障害・対立 |
| 構造化ログ (structured log) | `novel_forge.log` に出力されるログ。[YYYY-MM-DD HH:MM:SS] [PID] [LEVEL] フォーマット |
| スキーマ (schema) | JSON Schema。LLM出力の検証に使用 |
| スラグ (slug) | シリーズ識別子。ディレクトリ名に使用。英数字アンダースコア区切り（例: `novel_forge`） |
| 設定ファイル (config.yaml) | LLM、ログ、品質ゲート等の設定 |

## た行

| 用語 | 説明 |
|---|---|
| 多様性 (diversity) | リトライ時の seed 変更やプロンプト変更による出力の多様性確保 |
| 対話的コマンド (interactive command) | 実行中にプロンプトを表示する CLI（NovelForge にはない） |
| 単体テスト (unit test) | pytest で実装されるコードレベルのテスト |

## な行

| 用語 | 説明 |
|---|---|
| 内部対話 (inner monologue) | 視点人物の内心描写。POV が視点人物の場合のみ許可 |

## は行

| 用語 | 説明 |
|---|---|
| 品質ゲート (quality gate) | レビュー結果に基づき code側で revision_needed を判定する機構（severity=致命的/重要→true, 重要≥2→true） |
| revision_needed | 改稿が必要か。コード側が severity ベースで機械判定（LLMは出力しない） |
| 非決定的 (non-deterministic) | LLM 出力の非決定的な性質。リトライで多様性を確保 |
| パイプライン (pipeline) | plan → design → write → export の一連の工程 |
| 非同期 (asynchronous) | 非同期処理。NovelForge は同期実行のみ |
| 伏線 (foreshadowing) | 後で回収されるための事前配置。Bible で管理 |
| ブラックボード (Blackboard) | 事実記録の別名。bible.json とは別ファイル |

## ま行

| 用語 | 説明 |
|---|---|
| 前処理 (preprocessing) | JSON パース前の正規化処理（Markdown除去、クォート修正等） |
| 未回収伏線 (unresolved foreshadowing) | 回収されていない伏線。export 時に警告 |

## や行

| 用語 | 説明 |
|---|---|
| 役割 (purpose) | 章の役割（導入/展開/転換/クライマックス/収束） |
| 約束 (promise) | 伏線の一種。「いつか〜する」というキャラクターの約束 |

## ら行

| 用語 | 説明 |
|---|---|
| リトライ (retry) | 失敗時の再試行。seed をインクリメントして多様性を確保 |
| ロック (lock) | `.lock` ファイルによる同一シリーズの同時実行防止 |
| ログレベル (log level) | DEBUG / INFO / WARNING / ERROR / CRITICAL |

## わ行

| 用語 | 説明 |
|---|---|
| 輪郭 (outline) | 巻デザインの章・シーン構成 |

---

*Last updated: 2026-07-10*