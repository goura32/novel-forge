# NovelForge Pipeline Design

## 1. CLI コマンド

### 1.1 グローバルオプション

| オプション | 短縮 | Default | 説明 |
|---|---|---|---|
| `--workdir` | `-w` | `.` | 作業ディレクトリ（config.yaml のある場所） |
| `--series` | `-s` | なし | 既存シリーズの slug |
| `--volume` | `-V` | `1` | 処理対象の巻番号 |
| `--model` | `-m` | 設定ファイル or デフォルト | LLM モデル名 |
| `--max-generation-count` | | `3` | 生成API（APIエラー＋バリデーション）の最大リトライ回数（同一工程内） |
| `--max-review-count` | | `3` | レビュー→修正サイクルの最大回数（複数工程にまたがる） |
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
novel-forge design --workdir /mnt/hdd/novel --series monthly_closed_nonmagic_chef
novel-forge write   --workdir /mnt/hdd/novel --series monthly_closed_nonmagic_chef
novel-forge export  --workdir /mnt/hdd/novel --series monthly_closed_nonmagic_chef

# 一括実行
novel-forge complete "古文書修復師 司書 図書館" --workdir /mnt/hdd/novel

# 進捗確認
novel-forge status --workdir /mnt/hdd/novel --series monthly_closed_nonmagic_chef
novel-forge doctor
```

### 1.4 コマンド一覧

| コマンド | 説明 |
|---|---|
| `plan` | キーワードからシリーズ企画を生成 |
| `design` | 巻デザイン（章・シーン構成）を生成。`--volume 0` で全巻一括生成 |
| `write` | シーン本文を生成 |
| `export` | KDP 向け出力を生成 |
| `complete` | plan → design → write → export を一括実行 |
| `status` | 現在の進捗を表示 |
| `resume` | 中断した工程から再開 |
| `list` | シリーズ一覧を表示 |
| `doctor` | Ollama 接続診断 |

---

## 2. エンジン構成

### 2.1 Thin Facade パターン

```python
class NovelEngine(NovelEngineBase):
    """NovelEngine — all phase methods defined directly.

    No mixins. Each method delegates to a standalone function.
    """

    def plan(self, keywords: str) -> dict:
        return plan(self, keywords)

    def design(self, volume_number: int | None = None) -> dict:
        return design(self, volume_number)

    def write(self, volume_number: int | None = None) -> list:
        return write(self, volume_number)

    def export(self, volume_number: int | None = None) -> dict:
        return export(self, volume_number)

    def resume(self) -> dict:
        return resume(self)

    def status(self) -> dict:
        return status(self)
```

### 2.2 ファイル構成

```
engine/
├── __init__.py         # NovelEngine クラス定義 (thin facade)
├── infra.py            # ロック取得, エンジン生成, status/doctor
├── base.py             # NovelEngineBase — __init__, state, DI
├── plan.py             # plan() — 3-phase: core → characters → volumes
├── design.py           # design() — 3-phase: volume → chapter → scene
├── write.py            # write() — シーン執筆ループ
├── export.py           # export(), resume(), status()
└── review.py           # generate_and_review(), format_review_text()
```

### 2.3 外部モジュール

```
├── cli.py                # CLI コマンド定義（typer）
├── llm_client.py         # Ollama API クライアント（ストリーミング + JSON パース）
├── schemas.py            # JSON スキーマローダー（get_schema, validate）
├── name_registry.py      # キャラクター名重複排除
├── bible_manager.py      # 設定資料集（伏線・関係性・用語）
├── json_parser.py        # パース・型補正ユーティリティ
├── logging_config.py     # ロギング設定（ファイル追記 + コンソール）
├── models.py             # データモデル（SceneRecord等）
└── scene_writer.py       # シーン本文生成エンジン
```

---

## 3. シリーズ企画パイプライン (plan())

3フェーズでシリーズ企画を生成。各フェーズが `generate_and_review()` で生成→レビュー→改稿ループ。

### Phase 1: Core
- **入力**: キーワード
- **出力**: タイトル、あらすじ、ジャンル、テーマ、世界観、キャラクター一覧
- **スキーマ**: `series_plan_core.json`
- **バリデーション**: `title`, `slug`, `logline`, `genre`, `themes`, `selling_points`, `world`, `target_audience`, `main_characters` 必須
- **slug 重複チェック**: 既存シリーズの slug 一覧をプロンプトに渡す
- **キャラクター名重複バリデーション**: 名前レジストリで重複排除

### Phase 2: Characters
- **入力**: Phase 1 の世界観・キャラクター
- **出力**: 全キャラクターの詳細プロフィール（personality, motivation, flaw, arc, skills）
- **スキーマ**: `series_plan_characters.json`

### Phase 3: Volumes
- **入力**: Phase 1 + Phase 2
- **出力**: 各巻の構造（タイトル、前提、テーマ、感情弧、主要イベント）
- **スキーマ**: `series_plan_volumes.json`
- **制約**: 3巻固定、クリフハンガー必須（最終巻除く）

### generate_and_review() ループ

```python
# generation_cycles: 生成API＋バリデーション（同一工程内）
# review_cycles: レビュー→修正サイクル（複数工程にまたがる）

max_generation = quality.generation_max_retries
max_review = quality.review_max_retries
generation_cycles = 0
review_cycles = 0

while generation_cycles < max_generation:
    if review_cycles >= max_review and generation_cycles > 0:
        raise RuntimeError("max review cycles reached")

    try:
        result = generate(prompt, seed_offset=generation_cycles)
    except SchemaValidationError as e:
        generation_cycles += 1
        continue

    if llm._is_schema_echo(result):
        generation_cycles += 1
        continue

    try:
        errors = validate_fn(result)
    except SchemaValidationError as e:
        errors = [f"path={...} msg={e.message}"]
    if errors:
        generation_cycles += 1
        continue

    # First review (after initial generation)
    review = review_fn(result, system)
    review_cycles += 1

    blocker = [i for i in review['issues'] if i['severity'] == '致命的']
    critical = [i for i in review['issues'] if i['severity'] == '重大']
    major = [i for i in review['issues'] if i['severity'] == '重要']
    fatal_count = len(blocker) + len(critical)
    revision_needed = fatal_count > 0 or len(major) >= 2

    if not revision_needed:
        return result, review

    if review_cycles >= max_review:
        raise RuntimeError("max review cycles reached")

    result = revise_fn(result, review, system, generation_cycles)
    generation_cycles += 1

    # Post-revision validation
    errors = validate_fn(result)
    if errors:
        if generation_cycles >= max_generation - 1:
            raise RuntimeError("post-revision validation failed")
        continue

    # Re-review
    review = review_fn(result, system)
    review_cycles += 1

    # Check issues after re-review
    blocker = [...]
    critical = [...]
    major = [...]
    fatal_count = len(blocker) + len(critical) + len(major)

    if fatal_count > 0 and review_cycles >= max_review:
        raise RuntimeError("issues remain after max review cycles")

    if not fatal_count:
        return result, review

    # Another revise cycle
    result = revise_fn(result, review, system, generation_cycles)
    generation_cycles += 1
    # Loop back for another validation + review cycle
```

---

## 4. 巻デザイン�イプライン (design())

3フェーズで。

### Phase 1: Volume Design (章構成)
- **入力**: シリーズ企画、ジャンル
- **出力**: 各章の title, purpose, theme
- **スキーマ**: `volume_design.json`
- **制約**: ストーリーに必要な章数を自律的に判断すること（最低2章）。必ず「収束」の章を含めること

### Phase 2: Chapter Design
- **入力**: Phase 1 の章構成
- **出力**: 各章のサブプロット・伏線メモ・感情の弧
- **スキーマ**: `chapter_design.json`

### Phase 3: Scene Design
- **入力**: Phase 2 の章設計
- **出力**: 全シーンの構造（goal, outcome, conflict, pov, characters, events, setting, emotional_arc）
- **スキーマ**: `scene_design.json`
- **シーン数**: purpose に基づいて自動推定（導入:2, 展開:3, 転換:3, クライマックス:4, 収束:2）

---

## 5. シーン執筆パイプライン (write() → SceneWriter)

### 5.1 処理順序

シーンは**必ず順に処理。

```
for chapter in chapters:
    for scene in chapter.scenes:
        if scene already done: skip
        Draft → Review → QualityGate → Revise → Summarize+BibleUpdate
```

### 5.2 Draft

SceneWriter._draft_scene() で以下の情報を基に初稿生成:
- シリーズ企画、巻デザイン、シーン定義
- 前シーン全文 + 直近シーン要約 + 引き継ぎメモ
- Bible（キャラクター、伏線、関係性、用語、世界観ルール）

### 5.3 Review → Quality Gate → Revise

1. **Review**: 初稿を評価し、改善点を抽出（`scene_review.json`）
2. **Quality Gate**: レビュー結果に基づき code側で 合格/不合格 を機械判定
3. **Revise**: 不合格の場合、レビュー結果に基づき自動改稿（`scene_draft` スキーマ使用）
4. **最大2回**まで繰り返す。2回不合格 → `強制出力済`

### 5.4 Summarize + Bible Update

シーン合格後、1回のLLM呼び出しで:
- **Blackboard 更新**: シーン要約、事実記録、引き継ぎメモ
- **Bible 更新**: キャラクター、伏線、関係性、サブプロット、用語、世界観ルール
- **スキーマ**: `scene_summary_and_bible_update.json`

---

## 6. レビュー指摘カテゴリ

### シリーズ企画（核）
`missing_field`, `title_power`, `logline_quality`, `genre_fit`, `world_consistency`, `language_purity`

### シリーズ企画（キャラクター）
`missing_field`, `consistency`, `differentiation`, `growth_arc`, `world_fit`

### シリーズ企画（各巻）
`missing_field`, `volume_uniqueness`, `series_flow`, `cliffhanger`, `theme_consistency`

### 巻デザイン
`missing_field`, `structural_validity`, `scene_coherence`, `pace_analysis`, `character_arc_review`

### 章デザイン
`missing_field`, `role_validity`, `theme_coherence`, `emotional_arc_quality`, `scene_distribution`

### シーン
`opening_hook`, `character_distinction`, `sensory_coverage`, `scene_closure`, `dialogue_naturalness`, `tone_consistency`, `scene_completeness`, `scene_length`, `language_purity`, `pov_consistency`

---

## 7. キャラクター名重複排除

`name_registry.py` が `workdir/used_names.json` を管理。

- **Plan 完了時**: キャラクター名を `record_names()` で記録
- **新規 Plan**: `load_used_names()` で既読名を取得し、プロンプトに「使用不可名」として渡す

---

## 8. ログ出力

### 8.1 フォーマット

```
[YYYY-MM-DD HH:MM:SS] [series:X] [PID XXXXX] [LEVEL] message
```

- `PID`: プロセスID（マルチプロセス時の区別）
- `series`: シリーズslug（Design/Write/Export フェーズ）
- ログファイル: `workdir/novel_forge.log`（追記モード）
- stderr: WARNING 以上（verbose 時は DEBUG）

### 8.2 フェーズログ

```
[2026-06-26 10:30:00] [PID 45567] [INFO] ▶ Plan: keywords='...'
[2026-06-26 10:30:00] [PID 45567] [INFO]   ▶ core — [1/3]
[2026-06-26 10:35:19] [PID 45567] [INFO]   ✓ core — title='...' slug='...'
```

### 8.3 LLM進捗ログ

```
[2026-06-26 10:30:00] [PID 45567] [INFO]  [LLM PROGRESS] chunks=2500 bytes=394641 elapsed=110.0s series=X vol=Y
[2026-06-26 10:40:00] [PID 45567] [DEBUG]  [LLM DONE] kind=series_plan_core chunks=5081 bytes=795439 elapsed=124.4s done=
```

---

## 9. RAWデータ保存

LLM呼び出しの生データを `_raw_logs/{phase}/{timestamp}_{kind}/` に保存。

```
_raw_logs/plan/20260629_064606_series_plan_core/
├── raw_summary.md              # 人が読める形式（追記）
└── details/                    # 元データ（gzip）
    ├── request_0_0.json.gz
    └── response_0_0.json.gz
```

| ファイル | 内容 |
|---|---|
| `raw_summary.md` | request/response を人が読める形式で追記。`--raw-log` 時のみ保存 |
| `details/*.json.gz` | 元のリクエストペイロード・レスポンス（gzip） |

- ディレクトリ名: `{YYYYMMDD_HHMMSS}_{kind}`（実行単位の識別）
- `raw_summary.md` は追記モード。新しいLLM呼び出しのたびに追記される
- request: `messages` の `content` を出力。エスケープされた改行は復元
- response: `content` を出力。`thinking` は長いため除外
- `raw_log: false` の場合は保存しない

---

## 10. 設定ファイル (config.yaml)

```yaml
llm:
  model: "qwen3.6:35b-a3b-mtp-q4_K_M"
  num_predict: -1
  num_ctx: 262144
  timeout_seconds: 3600
  max_retries: 2          # LLM API 呼び出しエラー時のリトライ
  ollama_host: "192.168.1.31:11434"
  think: true

quality:
  max_generation_count: 3  # 生成API＋バリデーション最大リトライ（同一工程内）
  max_review_count: 3      # レビュー→修正サイクル最大回数（複数工程にまたがる）
```

優先順位: CLI引数 > config.yaml > デフォルト値

---

## 11. 状態遷移

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

## 12. 人間介入ポイント

| 介入ポイント | タイミング | 内容 |
|---|---|---|
| シリーズ企画の確認 | plan 直後 | LLM自己レビュー結果を人間が確認（暗黙承認） |
| 最終レビュー | export 直後 | kdp_readiness_report.md の確認（任意） |

**それ以外の工程はすべて LLM 自律。**

---

## 13. 出力ファイル構成

```
<series_dir>/
├── state.json
├── series_plan.json
├── _raw_logs/plan/20260629_064606_series_plan_core/
│   ├── raw_summary.md
│   └── details/
├── _raw_logs/design/20260629_094252_volume_design/
│   ├── raw_summary.md
│   └── details/
├── _raw_logs/write/20260629_120000_scene_draft/
│   ├── raw_summary.md
│   └── details/
├── vol01/
│   ├── vol01.json
│   ├── vol01_ch01/
│   │   ├── vol01_ch01.json
│   │   ├── vol01_ch01_sc01.json
│   │   └── ...
│   └── ...
├── used_names.json
└── exports/
    ├── <slug>_vol01.md
    ├── <slug>_vol01_metadata.json
    └── <slug>_vol01_kdp_readiness_report.md
```

---

## 14. {lang} の廃止

`{lang}` プレースホルダは全プロンプトから削除済み。
出力言語は `system.md` の「日本語固定」に従う。

---

*Last updated: 2026-06-29*
