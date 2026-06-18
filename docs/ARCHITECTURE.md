# NovelForge Architecture Design

## 1. 設計背景

NovelForge は、ローカルLLMを使って小説シリーズを企画・構成・執筆・レビュー・改稿・出力する Python CLI ツールです。

### 採用アーキテクチャ

4層アーキテクチャを採用します。

| Layer | 役割 | 主要コンポーネント |
|---|---|---|
| CLI Interface | ユーザーとの対話 | `cli.py` (Typer) |
| Orchestration | 状態遷移、パイプライン制御 | `engine.py` (NovelEngine) |
| Domain Logic | シーン執筆、コンテキスト構築、Bible管理 | `scene_writer.py`, `context_builder.py`, `bible_manager.py` |
| Infrastructure | LLM通信、永続化、ログ、スキーマ検証 | `ollama_client.py`, `storage.py`, `schemas.py`, `quality.py` |

**用語の定義**: [GLOSSARY.md](GLOSSARY.md)

---

## 2. モジュール構成

```
src/novel_forge/
├── cli.py              # CLI エントリポイント (Typer)
├── engine.py            # オーケストレーション層 (NovelEngine)
├── scene_writer.py      # シーン執筆パイプライン (SceneWriter)
├── context_builder.py   # コンテキスト構築 (ContextBuilder)
├── bible_manager.py     # Bible 管理 (BibleManager)
├── models.py            # Pydantic データモデル
├── ollama_client.py     # LLM クライアント
├── prompts.py           # プロンプト管理
├── quality.py           # 品質ゲート
├── schemas.py           # JSON Schema 検証
└── storage.py           # 永続化 (StateStorage, BlackboardStorage, BibleStorage)
```

### 2.1 責務分割

| モジュール | 責務 | 依存先 |
|---|---|---|
| `NovelEngine` | plan/outline/write/export のオーケストレーション | SceneWriter, ContextBuilder, BibleManager |
| `SceneWriter` | シーンの draft/review/revise/summarize/bible_update | LLMClient, QualityGate, BlackboardStorage, BibleStorage |
| `ContextBuilder` | context/continuity 構築、シリーズ要約、アウトライン要約 | BlackboardStorage, BibleStorage |
| `BibleManager` | Bible の更新・照会・最終確定 | BibleStorage |

### 2.2 SceneWriteContext (Parameter Object)

`SceneWriter.write_scene()` への引数を `SceneWriteContext` データクラスでまとめています。

```python
@dataclass
class SceneWriteContext:
    lang: str
    vol_num: int
    build_context_fn: Callable[[], str]
    build_continuity_fn: Callable[[int, int], str]
    get_series_plan_summary_fn: Callable[[], str]
    get_outline_summary_fn: Callable[[VolumeOutline], str]
    get_scene_summary_fn: Callable[[Scene], str]
    get_bible_text_fn: Callable[[], str]
    load_scene_draft_fn: Callable[..., str]
```

---

## 3. データフロー

### 3.1 制作パイプライン

```
キーワード → [plan] シリーズ企画 + 自己レビュー → 人間確認（暗黙承認）
           → [outline] 巻アウトライン → 自己修正（最大3回）
           → [write] シーン執筆（sequential）→ レビュー → 改稿 → 品質ゲート → Blackboard更新
           → [export] 原稿組立 → 最終レビュー → kdp_readiness_report.md
           → [next-volume] 次巻のアウトライン生成
```

- シーンは **sequential のみ**（前シーン要約を `{continuity}` として次シーンに注入）
- アウトライン自己修正は **最大3回**
- シーン品質ゲート不合格 → 自動改稿 → 再評価（最大1回、設定可能）。不合格 → `強制出力済`

### 3.2 状態遷移

**シリーズ**: `計画中 → アウトライン済 → 執筆中 → 初稿済 → 強制出力済 → 出力済`

**巻**: `計画中 → アウトライン済 → 執筆中 → 初稿済 → 強制出力済 → 出力済`

**シーン**: `計画中 → 初稿済 → 修正済`
                  └→ `強制出力済`

### 3.3 人間介入ポイント

| 介入ポイント | タイミング | 内容 | 必須/任意 |
|---|---|---|---|
| シリーズ企画の確認 | plan 直後 | LLM自己レビュー結果を人間が確認。問題なければ暗黙的に次工程へ | **必須（暗黙承認）** |
| 最終レビュー | export 直後 | kdp_readiness_report.md の確認 | 任意 |

**それ以外の工程はすべて LLM 自律。**

---

## 4. プロンプト戦略

### 4.1 MVME (Minimalist & Mathematical Edition)

MVME はシーン目標を因果関係で表す手法です。「どのような状態から、誰がどのような行動をとり、その結果どうなるか」を構造的に指定します。

全シーン目標に `(State > Action | Result)` パターンを強制します。詳細は [PROMPTS.md](PROMPTS.md) を参照。

### 4.2 JSON Schema 検証パイプライン

```
LLM Response
  │
  ├─▶ Step 1: Raw content parse (unwrap markdown fence, `{result:...}`)
  ├─▶ Step 2: Draft202012Validator 構造検証
  ├─▶ Step 3: Pydantic 型チェック (extra="forbid")
  └─▶ Step 4: 論理一貫性チェック (State Machine, Blackboard)
```

### 4.3 コンテキスト注入

各シーン生成時に注入する情報:

1. **system**: JSON 出力 + ジャンル/ペルソナ指示 (from `prompts/system.md`)
2. **context**: シリーズ企画 + 巻アウトライン + Blackboard.facts + Bible
3. **scene**: アウトライン内の当該シーン定義 (MVME goal 含む)
4. **continuity**: 前シーン要約 + revision履歴 (from Blackboard)

### 4.4 スキーマ設計原則

- **LLM呼び出し時と保存時でスキーマを分ける**
  - 章構成生成時: `chapter_outline.json`（`{chapters: [{title, purpose}]}`）
  - シーン設計生成時: `scene_outline.json`（`{title, goal, outcome, ...}`）
  - 保存時: `volume_outline.json`（`{chapters: [{title, purpose, scenes: [...]}]}`）
- **engine.py で機械採番するフィールド（number, chapter_number, volume_number）は LLM スキーマに含めない**

---

## 5. 記憶モデル (3層ハイブリッド)

### 5.1 State Machine (進捗管理)

`ProjectState` が制作進捗を管理。**事実記録と設定資料集は `state.json` とは別ファイル**として永続化します。

### 5.2 事実記録（Blackboard）— 物語の事実

`blackboard.json` として独立ファイルで管理。

- **facts**: `(subject, predicate, object, confidence)` の事実リスト
- **scene_summaries**: シーンごとの要約
- **continuity_notes**: 次シーンへの引き継ぎメモ
- **subplots**: サブプロット進捗
- **timeline**: 時系列イベント

**更新**: シーン完了時に `SceneWriter.summarize_and_update_bible()` が facts を追加。

### 5.3 設定資料集（Bible）— メタデータ台帳

`bible.json` として独立ファイルで管理。

- **characters**: キャラクタープロファイル（名前、役割、外見、性格、動機、状態）
- **glossary**: 用語と定義
- **foreshadowing**: 伏線と回収状況
- **world_rules**: 世界観ルール
- **relationships**: キャラクター関係性
- **subplots**: サブプロット

**更新**: シーン完了時に `SceneWriter.summarize_and_update_bible()` が Bible を更新。
**巻レベルの最終更新**: `BibleManager.finalize()` が export 時に未回収伏線をチェック。

---

## 6. LLM モデルの選定

### 6.1 推奨モデル

**`qwen3.6:35b-a3b-mtp-q4_K_M`** を推奨モデルとします。

選定理由:
- **日本語能力**: 日本語の小説生成において、高い表現力と文法穩定性
- **JSON 出力**: `/api/generate` + `format: schema` + `think: false` で **100% 成功率**（6プロンプト×5スケール=30テスト全成功）
- **長文処理**: 131,072 トークンの context 長
- **VRAM 効率**: Q4 量子化で 24GB VRAM GPU で動作可能
- **速度**: 平均4.7秒（simple〜complexプロンプト）

### 6.2 最適パラメータ（2026-06-28 ベンチマーク確定）

| パラメータ | 値 | 備考 |
|---|---|---|
| `think` | `false` | `true` は全スケールで0%（thinkingに逃げてcontent空） |
| `format` | `schema` | JSON Schemaオブジェクトをそのまま渡す |
| `num_predict` | `16384` | 1024〜16384全スケールで100%安定 |
| `num_ctx` | `65536` | ws1.local GPU の安定値 |

**`think: true` は不可**: `num_predict` を16倍にしても `done_reason=stop` で `response_len=0`。thinkingモードの構造的問題であり、トークン量では解決できない。

### 6.3 比較検証: gemma4:26b

| 設定 | 成功率 | 平均速度 | 備考 |
|---|---|---|---|
| **qwen3.6 + think:false** | **100%** | **4.7s** | 全スケール安定 |
| gemma4:26b + think:false | 67% | 9.5s | longプロンプトで `num_predict` 不足 |
| gemma4:26b + think:true | 40% | 不安定 | `done_reason=length` で切れる |

gemma4 は `think: false` でも長いプロンプトで `num_predict` 不足になり、`think: true` は壊れる。

### 6.4 モデルの切替

`--model` フラグで別のモデルを指定可能。

---

## 7. LLM API 設計

### 7.1 API Endpoint

`/api/generate` を採用。`format: JSON Schema` + `think: false` で安定した構造化出力。

### 7.2 リトライ戦略

- 最大リトライ回数: 2回（合計3回まで試行）
- リトライ時はエラーフィードバックをメッセージに追加

### 7.3 JSON抽出パイプライン

1. **直接 parse** — `message.content` を JSON としてパース
2. **Markdown fence フォールバック** — `` ```json ``` `` で囲まれた場合の中身を抽出
3. **ラッパーオブジェクトフォールバック** — `{result: ...}` 等のラッパーオブジェクトを抽出

---

## 8. セキュリティとデータ保全

| 項目 | 内容 |
|---|---|
| パストラバーサル防止 | `..` を含む slug を拒否 |
| 原子的書き込み | 一時ファイル作成 → `fsync` → `rename` (POSIX atomic)。既存 JSON は `.bak` 退避 |
| RAW ログ | 全 LLM リクエスト/レスポンスを `raw_logs/` に保存 |

---

## 9. 長文対応

1. **分割処理**: 各工程は scene または chapter 単位で LLM に投入
2. **集約の階層化**: scene → chapter → volume の順に段階的に集約
3. **Blackboard の巻ごとの要約**: 前巻の全データではなく、要約のみを次巻に引き継ぐ

---

## 10. ファイル構成

```
<workdir>/
├── .novel-forge/
│   ├── state.json              # プロジェクト状態
│   ├── series_plan.json        # シリーズ企画
│   ├── series_plan_review.json # シリーズ企画レビュー
│   ├── blackboard.json         # 事実記録
│   ├── bible.json              # 設定資料集
│   ├── raw_logs/               # LLM リクエスト/レスポンスログ
│   │   ├── 20260617_161613_series_plan.json
│   │   └── ...
│   └── volumes/
│       └── vol01/
│           ├── outline.json    # 巻アウトライン
│           ├── blackboard.json # 巻ごとの事実記録
│           ├── bible.json      # 巻ごとの設定資料集
│           ├── chapters/       # 章 Markdown
│           │   ├── ch01.md
│           │   └── ...
│           └── scenes/         # シーン Markdown
│               └── ch01/
│                   ├── vol01_ch01_sc01.md
│                   └── ...
└── exports/
    ├── vol01_manuscript.md
    ├── vol01_metadata.json
    └── vol01_kdp_readiness_report.md
```

---

## 11. 品質ゲート

### 11.1 合格基準

- `score >= 70`（0-100スケール）かつ `critical` / `blocker` issue が0件
- 不合格時は自動改稿 → 再評価（最大1回、`--max-retries` で設定可能）

### 11.2 レビュー指摘修正回数

| 工程 | デフォルト | 最大 | 設定方法 |
|---|---|---|---|
| シーン | 1回 | 3回 | `quality.max_review_retries` / `--max-retries` |
| アウトライン | 3回 | - | ハードコード |
| シリーズ企画 | 3回 | - | ハードコード |

### 11.3 簡体字チェック

- ツールによる検出は行わない（JIS 漢字セットベースの検出は誤検出が多いため）
- プロンプトでの防止が主
- LLM が簡体字を出力した場合、レビューで指摘する

---

*Last updated: 2026-06-28*
