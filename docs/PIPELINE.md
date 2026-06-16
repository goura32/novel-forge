# NovelForge Pipeline Design

## 1. CLI コマンド

### 1.1 グローバルオプション

| オプション | 短縮 | Default value | 説明 |
|---|---|---|---|
| `--config` | `-c` | `./.novel-forge.yaml` | 設定ファイルパス |
| `--workdir` | `-w` | 設定ファイル or カレント | 作業ディレクトリ |
| `--volume` | `-V` | 設定ファイル or `1` | 処理対象の巻番号 |
| `--model` | `-m` | 設定ファイル or デフォルト | LLM モデル名 |
| `--timeout` | `-t` | 工程別デフォルト | LLM タイムアウト (秒) |

### 1.2 使用例

```bash
# 初回: plan で作業フォルダ自動作成
uv run novel-forge plan "近未来東京 記憶探偵"

# 一括実行
uv run novel-forge complete "..."

# 既存シリーズで再開
uv run novel-forge resume --workdir ./my-project

# 巻2に切り替え
uv run novel-forge outline -V 2
```

### 1.3 段階実行コマンド

```bash
uv run novel-forge plan          --keywords "..."   # シリーズ企画
uv run novel-forge outline                        # 巻アウトライン
uv run novel-forge write                          # シーン執筆
uv run novel-forge export                         # KDP 向け出力
uv run novel-forge status                         # 進捗確認
uv run novel-forge resume                         # 中断した工程から再開
```

---

## 2. NovelEngine (engine.py)

中核となるオーケストレーション層。全コマンドはこのエンジンを通ります。

| コマンド | 役割 |
|---|---|
| `plan` | キーワードからシリーズ企画を生成。LLM自己レビュー後、人間が確認 |
| `outline` | 巻アウトライン（章・シーン構成）を生成。LLM自律 |
| `write` | シーン本文を生成し、レビュー・改稿・品質ゲートを実行。全工程LLM自律 |
| `export` | KDP 向け出力を生成 |
| `status` | 現在の進捗と文字数を表示 |
| `resume` | 中断した工程から再開 |

---

## 3. シーン執筆パイプライン (SceneWriter)

シーン単位の処理パイプライン。**全工程が LLM 自律。**

### 3.1 処理順序（sequential）

シーンは**必ず順序通り**に処理します。

```
シーン1: Draft → Review → QualityGate → Summarize+BibleUpdate
                                                    ↓ continuity として注入
シーン2: Draft → Review → QualityGate → Summarize+BibleUpdate
                                                    ↓
シーン3: Draft → Review → QualityGate → Summarize+BibleUpdate
```

### 3.2 Draft

`SceneWriteContext` に含まれる以下の情報を使用して初稿を生成:

- `series_plan`: シリーズ企画サマリー
- `outline`: 巻アウトラインサマリー
- `scene`: シーン定義 (MVME goal 含む)
- `context`: Bible + Blackboard
- `continuity`: 前シーン要約 + 引き継ぎメモ

### 3.3 Review → Quality Gate → Revise

1. **Review**: 初稿を評価し、改善点を抽出
2. **Quality Gate**: レビュー結果に基づき合格/不合格を判定
3. **Revise**: 不合格の場合、レビュー結果に基づき自動改稿
4. **最大3回**まで繰り返す。3回不合格 → `force_exported`

### 3.4 Summarize + Bible Update

シーン合格後、`summarize_and_update_bible()` を1回のLLM呼び出しで実行:

- **Blackboard 更新**: シーン要約、事実記録、引き継ぎメモ
- **Bible 更新**: キャラクター、伏線、関係性、サブプロット、用語、世界観ルール

### 3.5 章の自動組立

全シーンが完了した時点で、章単位の Markdown を自動組立:

```
scenes/ch01/vol01_ch01_sc01.md
scenes/ch01/vol01_ch01_sc02.md
  → chapters/ch01.md (全シーン結合)
```

---

## 4. コンテキスト構築 (ContextBuilder)

`ContextBuilder` は以下の情報を構築します:

### 4.1 build_context()

Bible + Blackboard から現在の物語コンテキストを構築:

- キャラクター情報（名前、役割、性格、動機）
- キャラクター関係性
- サブプロット進捗
- 用語集
- 世界観ルール
- 事実記録

### 4.2 build_continuity()

前シーンからの連続性を構築:

- 前シーン全文
- 前々シーンまでの要約（直近3件）
- 引き継ぎメモ

---

## 5. Bible 管理 (BibleManager)

### 5.1 更新タイミング

- **シーン完了時**: `summarize_and_update_bible()` で更新
- **export 時**: `finalize()` で未回収伏線の最終チェック

### 5.2 管理項目

| 項目 | 内容 |
|---|---|
| characters | キャラクタープロファイル |
| glossary | 用語集 |
| foreshadowing | 伏線と回収状況 |
| world_rules | 世界観ルール |
| relationships | キャラクター関係性 |
| subplots | サブプロット進捗 |

---

## 6. 状態遷移

```
Volume status:
  planned → outlined → drafting → drafted → exported → finalized
                                    │
                                    └→ force_exported

Scene status:
  planned → drafted → reviewed → revised
                         │
                         └→ force_exported (3回不合格時)
```

### Resume (再開)

任意の状態から再開可能。状態は `state.json` から読み込まれる。

| 状態 | 再開動作 |
|---|---|
| planned | plan から再開 |
| outlined | outline から再開 |
| drafting | write から再開（未完了のシーンのみ再生成） |
| drafted | export から再開 |
| force_exported | export から再開（force_exported シーンは再生成しない） |

---

## 7. Export 処理フロー

1. **Bible 最終更新** — `BibleManager.finalize()` で未回収伏線をチェック
2. **原稿組立** — `manuscript.md` を chapters/ から組立
3. **KDP メタデータ生成** — `metadata.json`
4. **KDP 準備完了レポート生成** — `kdp_readiness_report.md`
   - レビュー結果サマリー
   - `force_exported` シーンの警告
   - 未回収伏線のリスト
   - 未完了サブプロットのリスト
   - 簡体字混入の可能性

---

## 8. 人間介入ポイント

| 介入ポイント | タイミング | 内容 | 必須/任意 |
|---|---|---|---|
| シリーズ企画の確認 | plan 直後 | LLM自己レビュー結果を人間が確認 | **必須（暗黙承認）** |
| 最終レビュー | export 直後 | kdp_readiness_report.md の確認 | 任意 |

**それ以外の工程はすべて LLM 自律。**

---

## 9. 出力ファイル構成

```
<workdir>/
├── .novel-forge/
│   ├── state.json
│   ├── series_plan.json
│   ├── series_plan_review.json
│   ├── blackboard.json
│   ├── bible.json
│   └── volumes/
│       └── vol01/
│           ├── outline.json
│           ├── blackboard.json
│           ├── bible.json
│           ├── chapters/
│           │   ├── ch01.md
│           │   └── ...
│           └── scenes/
│               └── ch01/
│                   ├── vol01_ch01_sc01.md
│                   └── ...
└── exports/
    ├── vol01_manuscript.md
    ├── vol01_metadata.json
    └── vol01_kdp_readiness_report.md
```

---

*Last updated: 2026-06-25*
