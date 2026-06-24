# NovelForge Pipeline Design

## 1. CLI コマンド

### 1.1 グローバルオプション

| オプション | 短縮 | Default | 説明 |
|---|---|---|---|
| `--workdir` | `-w` | `.` | 作業ディレクトリ（config.yaml のある場所） |
| `--series` | `-s` | なし | 既存シリーズの slug |
| `--volume` | `-V` | `1` | 処理対象の巻番号 |
| `--model` | `-m` | 設定ファイル or デフォルト | LLM モデル名 |
| `--lang` | | `ja` | 出力言語（日本語固定） |
| `--max-retries` | | `2` | シーン品質ゲート最大リトライ回数 |
| `--verbose` | `-v` | `false` | 詳細出力 |
| `--raw-log` | | `false` | LLM生データを `_raw_logs/` に gzip 保存 |

### 1.2 排他制御

`plan` / `design` / `write` / `export` / `resume` は同一シリーズ内で同時実行不可。

- `series_dir/.lock` ファイルで排他制御
- ロック保持プロセスが終了していたら自動回収（stale lock 検出）
- `status` / `doctor` / `list` はロック不要（読み取り専用）

### 1.3 使用例

```bash
# 新規シリーズ企画
novel-forge plan "古文書修復師 司書 図書館" --workdir /mnt/hdd/novel

# 段階実行
novel-forge design --workdir /mnt/hdd/novel --series closed-stacks-return-box
novel-forge write   --workdir /mnt/hdd/novel --series closed-stacks-return-box
novel-forge export  --workdir /mnt/hdd/novel --series closed-stacks-return-box

# 一括実行
novel-forge complete "古文書修復師 司書 図書館" --workdir /mnt/hdd/novel

# 進捗確認
novel-forge status --workdir /mnt/hdd/novel --series closed-stacks-return-box
novel-forge doctor
```

### 1.4 コマンド一覧

| コマンド | 説明 |
|---|---|
| `plan` | キーワードからシリーズ企画を生成 |
| `design` | 巻デザイン（章・シーン構成）を生成 |
| `write` | シーン本文を生成 |
| `export` | KDP 向け出力を生成 |
| `complete` | plan → design → write → export を一括実行 |
| `status` | 現在の進捗を表示 |
| `resume` | 中断した工程から再開 |
| `list` | シリーズ一覧を表示 |
| `doctor` | Ollama 接続診断 |

---

## 2. エンジン構成

### 2.1 Mixin パターン

```python
class NovelEngine(
    NovelEngineBase,    # __init__, helpers, state, _review_and_revise
    PlanMixin,          # plan() — 3-phase: core → characters → volumes
    DesignMixin,        # design() — 3-phase: volume → chapter → scene
    WriteMixin,         # write()
    ExportMixin,        # export()
):
    pass
```

### 2.2 ファイル構成

```
engine/
├── base.py           # NovelEngineBase — __init__, ロック, 状態管理, _review_and_revise
├── infra.py          # ロック取得, エンジン生成, フェーズ解決, status/doctor
├── plan.py           # PlanMixin — plan() 3フェーズ
├── design.py         # DesignMixin — design() 3フェーズ
├── write.py          # WriteMixin — write()
├── export.py         # ExportMixin — export()
└── __init__.py       # NovelEngine クラス定義
```

---

## 3. シリーズ企画パイプライン (PlanMixin)

3フェーズでシリーズ企画を生成。各フェーズは `_generate_and_review()` で統一。

### Phase 1: Core
- 入力: キーワード
- 出力: タイトル、あらすじ、ジャンル、テーマ、世界観
- バリデーション: `title`, `slug`, `logline`, `genre`, `themes`, `selling_points`, `target_audience` 必須
- slug 重複チェック: 既存シリーズの slug 一覧をプロンプトに渡して回避

### Phase 2: Characters
- 入力: Phase 1 の世界観
- 出力: メインキャラクター（名前、役割、性格、背景、動機、欠陥、成長弧）

### Phase 3: Volumes
- 入力: Phase 1 + Phase 2
- 出力: 各巻のタイトル、前提、テーマ、感情弧、イベント、クリフハンガー

### `_generate_and_review()` ループ

```
for attempt in range(max_retries):
    result = generate(prompt, seed_offset=attempt)
    if validate(result) has errors: continue
    review = review(result, system)
    if no revision needed: return result
    result = revise(result, review, system, seed_offset)
    if validate(result) has errors: continue
    review = review(result, system)
    if no revision needed: return result
return result  # best effort after max_retries
```

- バリデーションエラー → seed を変えて再生成（プロンプトは変更しない）
- レビュー修正 → 修正後もバリデーション再チェック
- 合計 max_retries 回まで（デフォルト3回）

---

## 4. 巻デザインパイプライン (DesignMixin)

3フェーズで巻デザインを生成。

### Phase 1: Volume design (章構成)
- 入力: シリーズ企画、ジャンル
- 出力: 章のリスト（title, purpose）
- purpose: 導入 / 展開 / 転換 / クライマックス / 収束

### Phase 2: Chapter design
- 入力: Phase 1 の章構成
- 出力: 各章のテーマ、感情弧、伏線メモ、サブプロットメモ

### Phase 3: Scene design
- 入力: Phase 2 の章設計
- 出力: 各シーンの目標/結果/葛藤/視点/登場人物/主要イベント
- シーン数は purpose に基づいて自動推定（導入:2, 展開:3, 転換:3, クライマックス:4, 収束:2）

---

## 5. シーン執筆パイプライン (WriteMixin → SceneWriter)

### 5.1 処理順序

シーンは**必ず順序通り**に処理。

```
for chapter in chapters:
    for scene in chapter.scenes:
        if scene already done: skip
        Draft → Review → QualityGate → Revise → Summarize+BibleUpdate
```

### 5.2 Draft

SceneWriter.write_scene() で以下の情報を基に初稿生成:
- シリーズ企画、巻デザイン、シーン定義
- 前シーン全文 + 直近シーン要約 + 引き継ぎメモ
- Bible（キャラクター、伏線、関係性、用語、世界観ルール）

### 5.3 Review → Quality Gate → Revise

1. **Review**: 初稿を評価し、改善点を抽出
2. **Quality Gate**: レビュー結果に基づき合格/不合格を判定
3. **Revise**: 不合格の場合、レビュー結果に基づき自動改稿
4. **最大2回**まで繰り返す。2回不合格 → `強制出力済`

### 5.4 Summarize + Bible Update

シーン合格後、1回のLLM呼び出しで:
- **Blackboard 更新**: シーン要約、事実記録、引き継ぎメモ
- **Bible 更新**: キャラクター、伏線、関係性、サブプロット、用語、世界観ルール

---

## 6. ログ出力

### 6.1 フォーマット

```
[MM:SS] [LEVEL] message
```

- `MM:SS`: エンジン起動からの経過時間
- ログファイル: `workdir/novel_forge.log`（config.yaml と同じフォルダ）
- stderr: WARNING 以上（verbose 時は DEBUG）

### 6.2 フェーズログ

```
[00:00] [INFO] Plan started: keywords='...'
[00:00] [INFO]   [PHASE START] core
[00:09] [INFO]   [PHASE END] core
[00:09] [INFO]   [PHASE START] characters
...
[00:00] [INFO] Design started: volume=1
[00:00] [INFO]   [PHASE START] volume_design
[00:05] [INFO]   [PHASE END] volume_design: 4 chapters
```

### 6.3 LLM進捗ログ

```
[00:05] [DEBUG] [LLM PROGRESS] chunks=2500 bytes=394641 elapsed=00:03:24
[00:09] [DEBUG] [LLM DONE] kind=series_plan_core elapsed=435.0s
```

---

## 7. RAWデータ保存

LLM呼び出しの生データを `_raw_logs/{phase}/{pid}_{kind}/` に gzip 保存。

| イベント | ファイル名 | 内容 |
|---|---|---|
| LLM呼び出し前 | `request_N.json.gz` | リクエストペイロード |
| LLM呼び出し後 | `response_N.json.gz` | パース前の生データ |

- 各リトライで異なるファイル名（上書きしない）
- `raw_log: false` の場合は保存しない

---

## 8. 設定ファイル (config.yaml)

```yaml
llm:
  model: "qwen3.6:35b-a3b-mtp-q4_K_M"
  num_predict: -1
  num_ctx: 262144
  timeout_seconds: 3600
  max_retries: 5
  ollama_host: "192.168.1.31:11434"
  think: true

logging:
  verbose: true
  raw_log: true
  log_level: "DEBUG"

quality:
  max_review_retries: 3
```

優先順位: CLI引数 > config.yaml > デフォルト値

---

## 9. 状態遷移

```
Volume status:
  計画中 → デザイン済 → 執筆中 → 初稿済 → 出力済

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
| 執筆中 | write から再開（未完了シーンのみ） |
| 初稿済 | export から再開 |

---

## 10. 人間介入ポイント

| 介入ポイント | タイミング | 内容 |
|---|---|---|
| シリーズ企画の確認 | plan 直後 | LLM自己レビュー結果を人間が確認（暗黙承認） |
| 最終レビュー | export 直後 | kdp_readiness_report.md の確認（任意） |

**それ以外の工程はすべて LLM 自律。**

---

## 11. 出力ファイル構成

```
<series_dir>/
├── state.json
├── series_plan.json
├── series_core.json
├── series_characters.json
├── series_volumes.json
├── series_core_review.json
├── series_characters_review.json
├── series_volumes_review.json
├── blackboard.json
├── bible.json
├── _raw_logs/
│   └── {timestamp}_{kind}/
├── vol01/
│   ├── vol01.json
│   ├── vol01_ch01/
│   │   ├── vol01_ch01.json
│   │   ├── vol01_ch01_sc01/
│   │   │   ├── vol01_ch01_sc01.json
│   │   │   └── vol01_ch01_sc01.md
│   │   └── ...
│   └── ...
└── exports/
    ├── vol01_manuscript.md
    ├── vol01_metadata.json
    └── vol01_kdp_readiness_report.md
```

---

*Last updated: 2026-06-25*
