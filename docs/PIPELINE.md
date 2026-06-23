# NovelForge Pipeline Design

## 1. CLI コマンド

### 1.1 グローバルオプション

| オプション | 短縮 | Default value | 説明 |
|---|---|---|---|
| `--workdir` | `-w` | `.` | 作業ディレクトリ |
| `--volume` | `-V` | `1` | 処理対象の巻番号 |
| `--model` | `-m` | 設定ファイル or デフォルト | LLM モデル名 |
|| `--lang` | | `ja` | 出力言語 |
|| `--max-retries` | | `2` | シーン品質ゲート最大リトライ回数 |
|| `--verbose` | `-v` | `false` | 詳細出力 |
| `--raw-log` | | `false` | LLM生データを `_raw_logs/` に gzip 保存 |
| | | | (`config.yaml` の `logging` セクションで既定値を設定可能) |

### 1.2 排他制御

`plan` / `design` / `write` / `export` / `resume` は同一シリーズ内で同時実行不可。

- `series_dir/.lock` ファイルで排他制御
- ロック保持プロセスが終了していたら自動回収
- `status` はロック不要（読み取り専用）

### 1.3 使用例

```bash
# 初回: plan で作業フォルダ自動作成
uv run novel-forge plan "近未来東京 記憶探偵" --workdir /mnt/hdd/novel

# 段階実行
uv run novel-forge plan          --workdir /mnt/hdd/novel --keywords "..."
uv run novel-forge design                         # 巻デザイン
uv run novel-forge write                           # シーン執筆
uv run novel-forge export                          # KDP 向け出力
uv run novel-forge status                          # 進捗確認
uv run novel-forge resume                          # 中断した工程から再開

# 次巻へ進む
uv run novel-forge design --volume 2
```

### 1.4 コマンド一覧

```bash
uv run novel-forge plan          --keywords "..."   # シリーズ企画
uv run novel-forge design                         # 巻デザイン
uv run novel-forge list                           # シリーズ一覧
uv run novel-forge show <slug>                    # シリーズ詳細
uv run novel-forge write                           # シーン執筆
uv run novel-forge export                          # KDP 向け出力
uv run novel-forge status                          # 進捗確認
uv run novel-forge resume                          # 中断した工程から再開
```

---

## 2. NovelEngine (engine/)

中核となるオーケストレーション層。全コマンドはこのエンジンを通る。

| コマンド | 役割 |
|---|---|
| `plan` | キーワードからシリーズ企画を生成。LLM自己レビュー後、人間が確認 |
| `design` | 巻デザイン（章・シーン構成）を生成。**前巻の design.json が必須（第2巻以降）** |
| `write` | シーン本文を生成し、レビュー・改稿・品質ゲートを実行。全工程LLM自律 |
| `export` | KDP 向け出力を生成 |
| `status` | 現在の進捗と文字数を表示 |
| `resume` | 中断した工程から再開 |

### ログ出力

全フェーズの開始・終了時に構造化ログが出力されます。
LLM呼び出し中は60秒ごとに進捗ログ（chunks, bytes, elapsed）が出力されます。

``` 2026-08-07 12:00:00 [PID 12345] [INFO] novel_forge.engine: Plan started: keywords='...'
2026-08-07 12:00:00 [PID 12345] [INFO] novel_forge.engine: Plan finished: slug='...'
2026-08-07 12:00:00 [PID 12346] [INFO] novel_forge.engine: Design started: volume=1 slug='...'
2026-08-07 12:00:00 [PID 12346] [INFO] novel_forge.engine: Design finished: volume=1 slug='...'
2026-08-07 12:05:00 [PID 12346] [INFO] novel_forge.llm:   [LLM PROGRESS] chunks=1234 bytes=567890 elapsed=00:05:00
```

- ログファイル: `series_dir/novel_forge.log`
- フォーマット: `%(asctime)s [PID %(process)d] [%(levelname)s] %(name)s: %(message)s`
- 各フェーズの開始・終了時に `info` ログ、レビュー失敗時に `warning` ログ
- LLM呼び出し中は60秒ごとに `[LLM PROGRESS]` ログ（経過時間は `HH:MM:SS` 形式）

### LLM出力のJSONパース方針

Ollamaの `format: json` モードを使用し、LLMは有効なJSONのみを出力する。

**原則: 機械的補正ではなくリトライ**

- 不正なJSONが返った場合、`_fix_*` 関数で機械的に修正しない
- `llm_client.py` のリトライロジック（最大 `max_retries` 回）で再生成させる
- JSONパースエラーは `JsonParseError` としてリトライ判定される

**パース処理 (`parse_json_response`)**

1. **Direct parse** — `json.loads()` を試行
2. **Fallback** — `{...}` 境界を抽出して再パース
3. **失敗** — `JsonParseError` を投げ、`llm_client.py` がリトライ

**廃止されたフォールバック (2026-06-24)**

以下の関数は `format: json` では不要のため `parse_json_response` から削除済み:
- `_escape_json_string_values` — 文字列内改行エスケープ
- `_fix_bracket_quoted_values` — `「...」` → `"..."` 変換
- `_fix_single_quoted_values` — `'...'` → `"..."` 変換
- `_fix_unquoted_values` — クォートなし値の補正
- `_fix_trailing_comma` — trailing comma 除去
- `_fix_missing_colons` — colon 補正

これらが必要になった場合は、リトライ回数を増やすか、プロンプトを改善することで対応する。

### RAWデータ保存

LLM呼び出しの生データを `_raw_logs/{phase}/{pid}_{kind}/` に gzip 保存する。
リトライ時に上書きしない仕様で、全試行の生データを保持する。

| イベント | ファイル名 | 内容 |
|---|---|---|
| LLM呼び出し前 (attempt N) | `request_N.json.gz` | リクエストペイロード |
| 成功時 (attempt N) | `response_N.json.gz` | 成功したLLM出力 |
| JSONパースエラー時 (attempt N) | `_json_err_N.json.gz` | 不正なJSONの出力 |
| スキーマエラー時 (attempt N) | `_schema_err_N.json.gz` | スキーマ不一致の出力 |
| LLM通信エラー時 (attempt N) | `_llm_err_N.json.gz` | 通信エラー時の出力（空の場合あり） |
| その他のエラー時 (attempt N) | `_err_N.json.gz` | 予期しないエラー時の出力 |
| 全リトライ失敗時 | `_failed.json.gz` | 最後の試行の出力 |

- 各リトライで異なるファイル名が使われるため、全試行のRAWデータが保持される
- `raw_log: false` の場合は保存しない

### 設定ファイル (config.yaml)

```yaml
llm:
  model: "qwen3.6:35b-a3b-mtp-q4_K_M"
  num_predict: -1             # トークン上限（-1=無制限）
  num_ctx: 262144            # コンテキスト長（null=Ollama自動検出）
  timeout_seconds: 3600      # LLM応答待ちタイムアウト（秒）
  max_retries: 5             # LLM呼び出し最大リトライ回数
  ollama_host: "ws1.local:11434"
  think: true                # 思考モード（qwen3.6で有効）
  # 以下は省略可能（Ollamaデフォルト値が使用される）
  # temperature: 0.85
  # top_k: 20
  # top_p: 0.80
  # repeat_penalty: 1.0
  # presence_penalty: 0.0
  # frequency_penalty: 0.0
  # seed: 42
  # stop: []
  # tfs_z: 1.0
  # typical_p: 1.0
  # mirostat: 0
  # mirostat_tau: 5.0
  # mirostat_eta: 0.1
  # penalize_newline: true
  # num_threads: 0
  # ollama_options:  # 個別パラメータの上書き（個別パラメータより優先）
  #   temperature: 0.85
  #   top_k: 20
```
logging:
  verbose: true       # stderr に DEBUG レベルで出力
  raw_log: true       # _raw_logs/ に LLM 生データを gzip 保存
  log_level: "DEBUG"   # ログファイルのレベル

quality:
  max_review_retries: 2
```

優先順位: CLI引数 (`--verbose`, `--raw-log`) > config.yaml > デフォルト値

### 2.1 エンジン構成（Mixin パターン）

```python
class NovelEngine(
    NovelEngineBase,    # __init__, helpers, state, _review_and_revise
    PlanMixin,          # plan() — 3-phase: core → characters → volumes
    DesignMixin,        # design() — 3-phase: volume → chapter → scene
    WriteMixin,         # write(), progress()
    ExportMixin,        # export(), _assemble_manuscript()
):
    pass
```

---

## 3. シリーズ企画パイーン (PlanMixin)

3フェーズでシリーズ企画を生成:

### Phase 1: Core
- 入力: キーワード
- 出力: タイトル、あらすじ、ジャンル、テーマ、世界観
- レビュー: `series_plan_core_review.md`
- 修正: `series_plan_core_revision.md`
- ループ: 最大3回

### Phase 2: Characters
- 入力: Phase 1 の世界観
- 出力: メインキャラクター、サブキャラクター
- レビュー: `series_plan_characters_review.md`
- 修正: `series_plan_characters_revision.md`
- ループ: 最大3回

### Phase 3: Volumes
- 入力: Phase 1 + Phase 2
- 出力: 各巻のタイトル、前提、テーマ
- レビュー: `series_plan_volumes_review.md`
- 修正: `series_plan_volumes_revision.md`
- ループ: 最大3回

---

## 4. 巻デザインパイプライン (DesignMixin)

3フェーズで巻デザインを生成:

### Phase 1: 章構成 (volume_design)
- 入力: シリーズ企画、ジャンル
- 出力: 章のタイトルと役割（導入/展開/転換/クライマックス/収束）
- 前巻参照: 前巻の design.json を要約して注入

### Phase 2: 章設計 (chapter_design)
- 入力: Phase 1 の章構成
- 出力: 各章のテーマ、感情弧、伏線メモ、サブプロットメモ
- レビュー: `chapter_design_review.md`
- 修正: `chapter_design_revision.md`
- ループ: 最大2回/章

### Phase 3: シーンデザイン (scene_design)
- 入力: Phase 2 の章設計
- 出力: 各シーンの目標/結果/葛藤/視点/登場人物
- 前シーン参照: 前シーンの結果を `previous_outcome` として注入
- レビュー: `scene_design_review.md`
- 修正: `scene_design_revision.md`
- ループ: 最大2回/シーン

### 巻レビュー
- Phase 1 完了後、巻全体をレビュー
- レビュー: `volume_design_review.md`
- 修正: `volume_design_revision.md`
- ループ: 最大3回

---

## 5. シーン執筆パイプライン (SceneWriter)

シーン単位の処理パイプライン。**全工程が LLM 自律。**

### 5.1 処理順序（sequential）

シーンは**必ず順序通り**に処理。

```
シーン1: Draft → Review → QualityGate → Revise → Summarize+BibleUpdate
                                                    ↓ continuity として注入
シーン2: Draft → Review → QualityGate → Revise → Summarize+BibleUpdate
                                                    ↓
シーン3: Draft → Review → QualityGate → Revise → Summarize+BibleUpdate
```

### 5.2 Draft

以下の情報を使用して初稿を生成:

- `series_plan`: シリーズ企画サマリー
- `design`: 巻デザインママリー
- `scene`: デザイン内の当該シーン定義
- `context`: Bible + Blackboard
- `continuity`: 前シーン全文 + 直近シーン要約 + 引き継ぎメモ
- `subplots`: 進行中のサブプロット
- `relationships`: キャラクター関係性

### 5.3 Review → Quality Gate → Revise

1. **Review**: 初稿を評価し、改善点を抽出
2. **Quality Gate**: レビュー結果に基づき合格/不合格を判定
3. **Revise**: 不合格の場合、レビュー結果に基づき自動改稿
4. **最大2回**まで繰り返す。2回不合格 → `強制出力済`

### 5.4 Summarize + Bible Update

シーン合格後、`summarize_and_update_bible()` を1回のLLM呼び出しで実行:

- **Blackboard 更新**: シーン要約、事実記録、引き継ぎメモ
- **Bible 更新**: キャラクター、伏線、関係性、サブプロット、用語、世界観ルール

### 5.5 章の自動組立

全シーンが完了した時点で、章単位の Markdown を自動組立:

```
vol01/vol01_ch01/vol01_ch01_sc01.md
vol01/vol01_ch01/vol01_ch01_sc02.md
  → vol01/vol01_ch01/vol01_ch01.md (全シーン結合)
```

---

## 6. コンテキスト構築 (ContextBuilder)

`ContextBuilder` は以下の情報を構築する:

### 6.1 build_context()

Bible + Blackboard から現在の物語コンテキストを構築:

- キャラクター情報（名前、役割、性格、動機）
- キャラクター関係性
- サブプロット進捗
- 用語集
- 世界観ルール
- 事実記録

### 6.2 build_continuity()

前シーンからの連続性を構築:

- **前シーン全文**: 直前のシーンの本文全体
- **直近シーン要約**: 2〜3つ前のシーン要約（Blackboard.scene_summaries から）
- **引き継ぎメモ**: Blackboard.continuity_notes から最新5件

---

## 7. Bible 管理 (BibleManager)

### 7.1 更新タイミング

- **シーン完了時**: `summarize_and_update_bible()` で更新
- **export 時**: `finalize()` で未回収伏線の最終チェック

### 7.2 管理項目

| 項目 | 内容 |
|---|---|
| characters | キャラクタープロファイル |
| glossary | 用語集 |
| foreshadowing | 伏線と回収状況 |
| world_rules | 世界観ルール |
| relationships | キャラクター関係性 |
| subplots | サブプロット進捗 |

---

## 8. 状態遷移

```
Volume status:
  計画中 → デザイン済 → 執筆中 → 初稿済 → 出力済
                                    │
                                    └→ 強制出力済

Scene status:
  計画中 → 初稿済 → 修正済
                │
                └→ 強制出力済 (2回不合格時)
```

### Resume (再開)

任意の状態から再開可能。状態は `state.json` から読み込まれる。

| 状態 | 再開動作 |
|---|---|
| 計画中 | plan から再開 |
| デザイン済 | design から再開 |
| 執筆中 | write から再開（未完了のシーンのみ再生成） |
| 初稿済 | export から再開 |
| 強制出力済 | export から再開（強制出力済シーンは再生成しない） |

---

## 9. Export 処理フロー

1. **Bible 最終更新** — `BibleManager.finalize()` で未回収伏線をチェック
2. **原稿組立** — `manuscript.md` を chapters/ から組立
3. **KDP メタデータ生成** — `metadata.json`
4. **KDP 準備完了レポート生成** — `kdp_readiness_report.md`
   - レビュー結果サマリー
   - `強制出力済` シーンの警告
   - 未回収伏線のリスト
   - 未完了サブプロットのリスト

---

## 10. 人間介入ポイント

| 介入ポイント | タイミング | 内容 | 必須/任意 |
|---|---|---|---|
| シリーズ企画の確認 | plan 直後 | LLM自己レビュー結果を人間が確認 | **必須（暗黙承認）** |
| 最終レビュー | export 直後 | kdp_readiness_report.md の確認 | 任意 |

**それ以外の工程はすべて LLM 自律。**

---

## 11. 出力ファイル構成

```
<series_dir>/
├── state.json
├── series_plan.json
├── blackboard.json
├── bible.json
├── raw_logs/
│   ├── 20260619_161231_series_plan.json
│   └── ...
├── vol01/
│   ├── design.json
│   ├── vol01_ch01/
│   │   ├── vol01_ch01.md
│   │   ├── vol01_ch01_sc01.md
│   │   └── ...
│   ├── vol01_ch02/
│   │   └── ...
│   └── ...
├── vol02/
│   └── ...
└── exports/
    ├── vol01_manuscript.md
    ├── vol01_metadata.json
    └── vol01_kdp_readiness_report.md
```

---

*Last updated: 2026-06-24*
