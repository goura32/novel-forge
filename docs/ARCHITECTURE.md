# NovelForge Architecture Design

## 1. 設計背景

NovelForge は、ローカルLLMを使って小説シリーズを企画・構成・執筆・レビュー・改稿・出力する Python CLI ツールです。

既存の複数ツールで実績のある設計パターンを調査・統合し、より堅牢で高品質な制作パイプラインを実現します。

### 設計パターンの採用

```text
┌─────────────────────────────────────────────────────────┐
│                    CLI Interface (typer)                  │
├─────────────────────────────────────────────────────────┤
│              Orchestration Layer (Engine)                 │
│  ┌──────────┐  ┌──────────┐  ┌────────────────────┐    │
│  │ Planning │  │ Writing  │  │ Quality / Review   │    │
│  │ Engine   │  │ Engine   │  │ (LLM自律)          │    │
│  └──────────┘  └──────────┘  └────────────────────┘    │
├─────────────────────────────────────────────────────────┤
│              Intelligence Layer (Agents)                  │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐              │
│  │ Planner  │  │ Writer   │  │ Critic   │              │
│  └──────────┘  └──────────┘  └──────────┘              │
├─────────────────────────────────────────────────────────┤
│              State / Memory Layer                        │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐              │
│  │ State    │  │Blackboard│  │ Bible    │              │
│  │ Machine  │  │ Facts    │  │ Meta     │              │
│  └──────────┘  └──────────┘  └──────────┘              │
├─────────────────────────────────────────────────────────┤
│              Infrastructure Layer                        │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐              │
│  │ LLM      │  │ Storage  │  │ Logger   │              │
│  │ Client   │  │ (atomic) │  │ (RAW)    │              │
│  └──────────┘  └──────────┘  └──────────┘              │
└─────────────────────────────────────────────────────────┘
```

**Layer 構成の考え方**:

| Layer | 役割 |
|---|---|
| Orchestration | 状態遷移管理、パイプライン順序制御、リトライ |
| Intelligence | LLM を使った生成・評価・改善（ロジックを持たない） |
| State / Memory | 進捗管理、物語の事実、メタデータ台帳 |
| Infrastructure | LLM 通信、永続化、ログ記録 |

---

## 2. データフロー

### 2.1 制作パイプライン

```text
Input: keywords (Japanese)
  │
  ▼
[Planning Phase]
  │ LLM: series_plan schema
  │ LLM: 自己レビュー（キャラクター整合性・世界観的一貫性）
  │ 不合格 → 自動修正 → 再評価 (最大3回)
  ▼
series_plan.json ──▶ Blackboard (facts)
  │                  Bible (meta)
  ▼
  │ ★ 人間確認: LLM自己レビュー結果を人間が確認。問題なければ暗黙的に次工程へ
  ▼
[Outline Phase]
  │ LLM: volume_outline schema
  │ LLM: 自己レビュー（構造的妥当性・シーン間の論理一貫性）
  │ 不合格 → 自動修正 → 再評価 (最大3回)
  ▼
volume_N/outline.json
  │
  ▼
[Writing Phase] (per chapter per scene = LLM自律)
  │
  ├─▶ LLM: scene_draft → designs/ch01/vol01_ch01_sc01_design.json (JSON設計)
  │          ↓ 設計をプロンプトに注入
  │          scenes/ch01/vol01_ch01_sc01.md (Markdown原稿)
  ├─▶ LLM: scene_review → review.json     ← 人間には見せない
  ├─▶ LLM: scene_revision → revised.json   ← 人間には見せない
  ├─▶ Quality Gate check → quality_reports/vol01_ch01_sc01_quality.json
  │   └─▶ 不合格 → 自動改稿 → 再評価 (最大3回)
  │       └─▶ 3回不合格 → force_exported フラグを立てて続行
  └─▶ Blackboard.update(facts from scene)
  │
  ├─▶ 全シーン完了 → chapters/ch01.md 自動組立
  └─▶ 全章完了 → vol01_draft.md 自動組立
  ▼
[Export Phase]
  ├─▶ chapters/*.md から manuscript.md を自動組立
  ├─▶ exports/vol01.md を生成（chapters/*.md の結合）
  ├─▶ metadata.json
  └─▶ kdp_readiness_report.md (最終レビュー結果含む)
  │
  ▼
  │ ★ 最終レビュー (1回だけ, LLM自律)
  │   → kdp_readiness_report.md に全巻通読結果を記録
  │   → 人間は確認してもよいが必須ではない
  ▼
[完了]
```

### 2.2 状態遷移

```text
Volume status:
  planned → outlined → drafting → drafted → exported → finalized
                                                        → force_exported

Scene status:
  planned → drafted → reviewed → reviewed_n (n=1,2,3) → revised

  ※ reviewed は最大3回まで自動改稿→再評価を繰り返す
  ※ 3回不合格でも force_exported フラグで続行可能

Resume (再開):
  任意の状態から再開可能。状態は .state.json から読み込まれる。
  planned → plan から再開
  outlined → outline から再開
  drafting → write から再開（未完了のシーンのみ再生成）
  drafted → export から再開
```

### 2.3 人間介入ポイント

**方針: 人間介入を最小限に。ツールが自律的にレビュー・改稿する。**

| 介入ポイント | タイミング | 内容 | 必須/任意 |
|---|---|---|---|
| シリーズ企画の確認 | plan 直後 | LLM自己レビュー結果を人間が確認。問題なければ暗黙的に次工程へ | **必須（暗黙承認）** |
| 最終レビュー | export 直後 | kdp_readiness_report.md の確認 | 任意 |

**それ以外の工程はすべて LLM 自律。人間には見せない。**

**レビューワークフロー（原則: LLMが生成したものはLLMがレビューする）**:

| 階層 | 設計 | レビュー | 無限ループ防止 |
|---|---|---|---|
| シリーズ企画 | LLM → `series_plan.json` | LLM → 自己レビュー結果を記録 | 最大3回。人間が内容を確認（暗黙承認） |
| 巻アウトライン | LLM → `outline.json` | LLM → 自己レビュー結果を記録 | 最大3回 |
| シーン本文 | LLM → 本文 | LLM → 改稿 → 品質ゲート | 最大3回（3回不合格→`force_exported`） |

```text
シリーズ企画(LLM設計) → LLMレビュー → [人間確認] → 巻アウトライン(LLM設計) → LLMレビュー → シーン本文(LLM設計) → LLMレビュー → 改稿 → 品質ゲート → export → [最終レビュー(任意)]
    │                                            │
    │                                    LLM自律レビュー
    │                                    LLM自律改稿
    │                                    品質ゲート (最大3回)
    │                                            │
    ▼                                            ▼
  確認 ◀─────────────────────────────── 全シーン完了
    │
    ▼
export ─▶ [最終レビュー(任意)] ─▶ 完了
```

---

## 3. プロンプト戦略

### 3.1 MVME (Minimalist & Mathematical Edition)

MVME はシーン目標を因果関係で表す手法です。「どのような状態から、誰がどのような行動をとり、その結果どうなるか」を構造的に指定することで、LLM が物語の論理を飛ばすのを防ぎます。

全シーン目標に `(State > Action | Result)` パターンを強制:

```json
{
  "goal": "(State > Action | Result)",
  "description": "街灯が揺れる > 主人公が駆け出す | 雨が全身を打つ"
}
```

### 3.2 JSON Schema 検証パイプライン

```text
LLM Response
  │
  ├─▶ Step 1: Raw content parse (unwrap markdown fence, `{result:...}`)
  ├─▶ Step 2: Draft202012Validator 構造検証
  ├─▶ Step 3: Pydantic 型チェック (extra="forbid")
  └─▶ Step 4: 論理一貫性チェック (State Machine, Blackboard)
```

### 3.3 コンテキスト注入

各シーン生成時に注入する情報:

1. **system**: JSON 出力 + ジャンル/ペルソナ指示 (from `prompts/system.md`)
2. **context**: シリーズ企画 + 巻アウトライン + Blackboard.facts + Bible
3. **scene**: アウトライン内の当該シーン定義 (MVME goal 含む)
4. **continuity**: 前シーン要約 + revision履歴 (from Blackboard)

---

## 4. 記憶モデル (3層ハイブリッド)

### 4.1 State Machine (進捗管理)

Pydantic モデルの厳格な状態管理。Blackboard と Bible は `state.json` とは別ファイルとして永続化し、State はメタデータ参照のみ保持します。

```python
class NovelState(BaseModel):
    id: str
    keywords: str
    series_plan: SeriesPlan | None
    volume_outlines: dict[str, VolumeOutline]
    scenes: dict[str, SceneRecord]       # key = "v01_c01_s01"
```

Blackboard と Bible は `state.json` とは別ファイル（`blackboard.json`, `bible.json`）として永続化します。State は制作進捗の最小限の情報のみ保持し、物語の事実とメタデータは各ファイルの責務とします。

### 4.2 Blackboard (物語の事実)

`blackboard.json` として独立ファイルで管理。

```python
class BlackboardState(BaseModel):
    facts: list[Fact]                    # (subject, predicate, object, confidence)
    scene_summaries: dict[str, str]      # key → summary
    continuity_notes: list[str]          # 次シーンへの引き継ぎメモ
```

- **Write**: シーン完了時に WriterAgent が facts を追加
- **Read**: WriterAgent 生成時に直近 facts をコンテキスト注入
- **Verify**: ConsistencyEngine が新 facts と既存 facts の矛盾を検出

### 4.3 Bible (メタデータ台帳)

`bible.json` として独立ファイルで管理。

```python
class BibleState(BaseModel):
    characters: list[CharacterProfile]    # 名前、外見、性格、状態
    glossary: list[Term]                 # 用語、定義
    foreshadowing: list[ForeshadowItem]  # 伏線、回収状況
    world_rules: list[str]               # 世界観ルール
```

---

## 5. LLM モデルの選定

### 5.1 推奨モデル

**`qwen3.6:35b-a3b-mtp-q4_K_M`** を推奨モデルとします。

選定理由:

- **日本語能力**: 日本語の小説生成において、高い表現力と文法穩定性を確認済み
- **JSON 出力**: `/api/generate` + `format:"json"` + `think:false` の組み合わせで安定した JSON Schema 適合
- **長文処理**: 131,072 トークンの context 長を備え、長大なプロンプトに対しても情報を保持
- **VRAM 効率**: Q4 量子化により、24GB VRAM GPU での動作が可能
- **MTP (Multi-Token Prediction)**: 推論高速化により、長時間の生成でも実用的なレスポンスタイムを実現

### 5.2 モデルの切替

`--model` フラグで別のモデルを指定できますが、以下の条件を満たすモデルを推奨します。

- 日本語の商用小説を安定して生成できること
- JSON Schema に従った構造化出力ができること
- `thinking:false` または同等の思考モード無効化に対応していること
- 8B 以上のパラメータサイズがあること（故事的な一貫性を維持するため）

GPU VRAM が 24GB に満たない場合は、`qwen3.6:27b` 等の小さいモデルを検討してください。

---

## 6. LLM API 設計

### 6.1 API Endpoint

`/api/generate` を採用。

- `format: JSON Schema` + `think: false` で安定した構造化出力を確認

**基本原則**: `format` には JSON Schema を直接指定し、`think: false` をセットする。

**`think: true` + `format:json` の排他性（Ollama 仕様）**:

Ollama のアーキテクチャ上、`format: "json"` と `think: true` は排他的であり、同時に機能しない。JSON 出力が指定されると、Ollama は GBNF 文法でトークン生成の確率分布を制御し、文法的に無効なトークンの生成確率を実質ゼロ（-INFINITY）にする。これにより `<think>` のような JSON 外のタグを生成できなくなる。

### 6.2 プリウォーミング（モデル事前ロード）

Ollama はアイドル時にモデルをメモリから追い出す（デフォルト: 5分）。他システムと共用の場合、いつアンロードされるか不明。

**対策**: ツール起動時に「空リクエスト + `keep_alive: -1`」を送信し、モデルをメモリに固定する。

- `keep_alive: -1` は無期限メモリ保持
- `keep_alive: 0` は即時アンロード（デフォルト挙動）
- プリロードはツール起動時に1回だけ実行し、以降の全リクエストが高速になる

### 6.3 リトライ戦略

- 最大リトライ回数: 2回（合計3回まで試行）
- リトライ時はエラーフィードバックをメッセージに追加し、LLM に自己修正を促す
- 最終試行でも失敗した場合は `ValidationError` を発生させる

### 6.4 JSON抽出パイプライン

`format: JSON Schema` + `think: false` の場合、Ollama はスキーマに適合する JSON を `message.content` に出力する。キー名も指定通りになるため、単純なパスで十分。

1. **直接 parse** — `message.content` を JSON としてパース
2. **Markdown fence フォールバック** — 万が一 `` ```json ``` `` で囲まれた場合は中身を抽出

パースに失敗した場合は `ParseError` を発生させ、リトライを促す。

---

## 7. セキュリティとデータ保全

### 7.1 パストラバーサル防止
- `safe_child_dir(parent, slug)`: `..` を含む slug を拒否
- シーン本文パスがシリーズディレクトリ外を指す場合は拒否

### 7.2 原子的書き込み
- 一時ファイル作成 → `fsync` → `rename` (POSIX atomic)
- 既存 JSON は `.bak` として退避

### 7.3 RAW ログ

全 LLM リクエスト/レスポンスを `raw_logs/` に保存し、動作確認・デバッグ時に確認できるようにする。

**保存形式**: JSON ファイル、1リクエスト1ファイル。

**ファイル名**: `{timestamp}_{phase}_{model}.json`
- 例: `20260615_001_scene_draft_qwen3.6-35b.json`

**記録内容**:

```json
{
  "timestamp": "2026-06-15T00:00:00+09:00",
  "phase": "scene_draft",
  "model": "qwen3.6:35b-a3b-mtp-q4_K_M",
  "request": {
    "prompt": "...(完全なプロンプト)",
    "format": { "type": "object", "properties": {...} },
    "think": false,
    "options": { "num_tokens": 512 }
  },
  "response": {
    "content": "...(LLM の生応答)",
    "thinking": null,
    "raw": "...(API レスポンス全体)"
  },
  "metrics": {
    "total_duration_ms": 1500,
    "load_duration_ms": 300,
    "eval_count": 125,
    "prompt_eval_count": 50
  },
  "status": "success"
}
```

**エラー時も記録**:

```json
{
  "status": "error",
  "error_type": "TimeoutError",
  "error_message": "LLM request timed out after 60s",
  "request": { "prompt": "...", "phase": "..." },
  "partial_response": null
}
```

**保存先**: `{workdir}/raw_logs/`

**注意**: 未公開原稿を含むため、`raw_logs/` を共有しないこと。

**ローテーション**: デフォルトは全量保持。`--max-raw-logs N` で最新 N 件のみ保持（古いものは削除）。

---

## 8. 長文対応

作品の大きさに上限はありません。大きな作品に対処するために以下の設計を採用します。

1. **分割処理**: 各工程は scene または chapter 単位で LLM に投入し、全体を一度に送らない
2. **集約の階層化**: scene → chapter → volume の順に段階的に集約し、上位工程には要約を渡す
3. **Blackboard の巻ごとの要約**: 前巻の全データではなく、要約のみを次の巻に引き継ぐ

---

*Last updated: 2026-06-16*
