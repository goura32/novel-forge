# NovelForge Pipeline Design

## 1. CLI コマンド

### 1.1 グローバルオプション

| オプション | 短縮 | Default value | 説明 |
|---|---|---|---|
| `--workdir` | `-w` | `.` | 作業ディレクトリ |
| `--volume` | `-V` | `1` | 処理対象の巻番号 |
| `--model` | `-m` | 設定ファイル or デフォルト | LLM モデル名 |
| `--lang` | | `ja` | 出力言語 |
| `--max-retries` | | `2` | シーン品質ゲート最大リトライ回数 |
| `--verbose` | `-v` | `false` | 詳細出力 |

### 1.2 排他制御

`plan` / `outline` / `write` / `export` / `resume` / `complete` は同一シリーズ内で同時実行不可。

- `series_dir/.lock` ファイルで排他制御
- ロック保持プロセスが終了していたら自動回収
- `status` はロック不要（読み取り専用）

### 1.3 使用例

```bash
# 初回: plan で作業フォルダ自動作成
uv run novel-forge plan "近未来東京 記憶探偵"

# 一括実行（plan → outline → write → export）
uv run novel-forge complete "近未来東京 記憶探偵" --workdir ./work/series1

# 段階実行
uv run novel-forge plan          --workdir ./work/series1 --keywords "..."
uv run novel-forge outline                        # 巻アウトライン
uv run novel-forge write                          # シーン執筆
uv run novel-forge export                         # KDP 向け出力
uv run novel-forge status                         # 進捗確認
uv run novel-forge resume                         # 中断した工程から再開

# 次巻へ進む
uv run novel-forge outline --volume 2
```

### 1.4 段階実行コマンド

```bash
uv run novel-forge plan          --keywords "..."   # シリーズ企画
uv run novel-forge outline                        # 巻アウトライン
uv run novel-forge write                          # シーン執筆
uv run novel-forge export                         # KDP 向け出力
uv run novel-forge status                         # 進捗確認
uv run novel-forge resume                         # 中断した工程から再開
```

---

## 2. NovelEngine (engine/)

中核となるオーケストレーション層。全コマンドはこのエンジンを通る。

| コマンド | 役割 |
|---|---|
| `plan` | キーワードからシリーズ企画を生成。LLM自己レビュー後、人間が確認 |
| `outline` | 巻アウトライン（章・シーン構成）を生成。**前巻の outline.json が必須（第2巻以降）** |
| `write` | シーン本文を生成し、レビュー・改稿・品質ゲートを実行。全工程LLM自律 |
| `export` | KDP 向け出力を生成 |
| `status` | 現在の進捗と文字数を表示 |
| `resume` | 中断した工程から再開 |

### 2.1 エンジン構成（Mixin パターン）

```python
class NovelEngine(
    NovelEngineBase,    # __init__, helpers, state, lock
    PlanMixin,          # plan(), _generate_plan(), _review_series_plan()
    OutlineMixin,       # outline(), _generate_outline() (3-phase)
    WriteMixin,         # write(), _progress()
    ExportMixin,       # export(), _assemble_manuscript()
):
    pass
```

---

## 3. シーン執筆パイプライン (SceneWriter)

シーン単位の処理パイプライン。**全工程が LLM 自律。**

### 3.1 処理順序（sequential）

シーンは**必ず順序通り**に処理。

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
- `scene`: シーン定義
- `context`: Bible + Blackboard
- `continuity`: 前シーン全文 + 直近シーン要約 + 引き継ぎメモ
- `subplots`: 進行中のサブプロット
- `relationships`: キャラクター関係性
- `foreshadowing_to_resolve`: 回収すべき伏線

### 3.3 Review → Quality Gate → Revise

1. **Review**: 初稿を評価し、改善点を抽出
2. **Quality Gate**: レビュー結果に基づき合格/不合格を判定
3. **Revise**: 不合格の場合、レビュー結果に基づき自動改稿
4. **最大2回**まで繰り返す。2回不合格 → `強制出力済`

### 3.4 Summarize + Bible Update

シーン合格後、`summarize_and_update_bible()` を1回のLLM呼び出しで実行:

- **Blackboard 更新**: シーン要約、事実記録、引き継ぎメモ
- **Bible 更新**: キャラクター、伏線、関係性、サブプロット、用語、世界観ルール

### 3.5 章の自動組立

全シーンが完了した時点で、章単位の Markdown を自動組立:

```
vol01/vol01_ch01/vol01_ch01_sc01.md
vol01/vol01_ch01/vol01_ch01_sc02.md
  → vol01/vol01_ch01/vol01_ch01.md (全シーン結合)
```

---

## 4. アウトライン生成（3フェーズ）

### 4.1 Phase 1: 章構成 (`chapter_outline.md`)

シリーズ企画とジャンルから、4〜6章の構成を生成。各章に役割（導入/展開/転換/クライマックス/収振）を割り当て。

### 4.2 Phase 2: 章設計 (`chapter_design.md`)

各章の詳細設計を生成: テーマ、感情弧、伏線メモ、サブプロットメモ。前章の感情弧の結果を引き継ぐ。

### 4.3 Phase 3: シーン設計 (`scene_outline.md`)

各章内のシーンを設計。前シーンの結果を `previous_outcome` として注入し、連続性を維持。

### 4.4 前巻参照

- `_get_previous_volume_outline()`: 前巻の `outline.json` を読み取り、プロンプトに含める
- 前巻の最後のシーンの `outcome` は、巻アウトラインの「前巻の主要な結果」として第1巻目の章設計に注入される

---

## 5. コンテキスト構築 (ContextBuilder)

`ContextBuilder` は以下の情報を構築する:

### 5.1 build_context()

Bible + Blackboard から現在の物語コンテキストを構築:

- キャラクター情報（名前、役割、性格、動機）
- キャラクター関係性
- サブプロット進捗
- 用語集
- 世界観ルール
- 事実記録

### 5.2 build_continuity()

前シーンからの連続性を構築:

- **前シーン全文**: 直前のシーンの本文全体
- **直近シーン要約**: 2〜3つ前のシーン要約（Blackboard.scene_summaries から）
- **引き継ぎメモ**: Blackboard.continuity_notes から最新5件

---

## 6. Bible 管理 (BibleManager)

### 6.1 更新タイミング

- **シーン完了時**: `summarize_and_update_bible()` で更新
- **export 時**: `finalize()` で未回収伏線の最終チェック

### 6.2 管理項目

| 項目 | 内容 |
|---|---|
| characters | キャラクタープロファイル |
| glossary | 用語集 |
| foreshadowing | 伏線と回収状況 |
| world_rules | 世界観ルール |
| relationships | キャラクター関係性 |
| subplots | サブプロット進捗 |

---

## 7. 状態遷移

```
Volume status:
  計画中 → アウトライン済 → 執筆中 → 初稿済 → 出力済
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
| アウトライン済 | outline から再開 |
| 執筆中 | write から再開（未完了のシーンのみ再生成） |
| 初稿済 | export から再開 |
| 強制出力済 | export から再開（強制出力済シーンは再生成しない） |

---

## 8. Export 処理フロー

1. **Bible 最終更新** — `BibleManager.finalize()` で未回収伏線をチェック
2. **原稿組立** — `manuscript.md` を chapters/ から組立
3. **KDP メタデータ生成** — `metadata.json`
4. **KDP 準備完了レポート生成** — `kdp_readiness_report.md`
   - レビュー結果サマリー
   - `強制出力済` シーンの警告
   - 未回収伏線のリスト
   - 未完了サブプロットのリスト

---

## 9. 人間介入ポイント

| 介入ポイント | タイミング | 内容 | 必須/任意 |
|---|---|---|---|
| シリーズ企画の確認 | plan 直後 | LLM自己レビュー結果を人間が確認 | **必須（暗黙承認）** |
| 最終レビュー | export 直後 | kdp_readiness_report.md の確認 | 任意 |

**それ以外の工程はすべて LLM 自律。**

---

## 10. 出力ファイル構成

```
<series_dir>/
├── state.json
├── series_plan.json
├── series_plan_review.json
├── blackboard.json
├── bible.json
├── raw_logs/
│   ├── 20260619_161231_series_plan.json
│   └── ...
├── vol01/
│   ├── outline.json
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

*Last updated: 2026-06-20*
