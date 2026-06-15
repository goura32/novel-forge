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
│  │ Engine   │  │ Engine   │  │ Engine             │    │
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
  ▼
series_plan.json ──▶ Blackboard (facts)
  │                  Bible (meta)
  ▼
[Outline Phase]
  │ LLM: volume_outline schema
  ▼
volume_N/outline.json
  │
  ▼
[Writing Phase] (per chapter, per scene)
  │
  ├─▶ LLM: scene_draft → draft.json
  ├─▶ LLM: scene_review → review.json
  ├─▶ LLM: scene_revision → revised.json
  ├─▶ Quality Gate check → quality_gate.json
  └─▶ Blackboard.update(facts from scene)
  ▼
chapter_N/chapter.md (assembled scenes)
  │
  ▼
[Volume Review Phase]
  │ LLM: volume_review (chunked if long)
  ├─▶ LLM: volume_revision (if needed)
  ├─▶ Quality Gate: ready_for_publication + blocking issues
  └─▶ Bible.update(volume_revised)
  │
  ▼
[Export Phase]
  ├─▶ manuscript.md
  ├─▶ volumes/N/chapter_N.md
  ├─▶ book.epub (draft)
  ├─▶ metadata.json
  └─▶ kdp_readiness_report.md
```

### 2.2 状態遷移

```text
Volume status:
  planned → outlined → drafting → drafted → reviewed → revised → published
                                                              → force_exported

Scene status:
  planned → drafted → reviewed → revised
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

- **日本語能力**: 日本語の小説生成において、高い表現力と文法稳定性を確認済み
- **JSON 出力**: `/api/generate` + `format:"json"` + `think:false` の組み合わせで安定した JSON Schema 適合（2026-06-15 実測確認）
- **長文処理**: 131,072 トークンの context 長を備え、長大なプロンプトに対しても情報を保持
- **VRAM 効率**: Q4 量子化により、24GB VRAM  GPU での動作が可能
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
- エンドポイント: `http://ws1.local:11434/api/generate`

**`format` パラメータの比較（2026-06-15 実測, `think:false`）**:

| `format` | レスポーンスキー | 備考 |
|---|---|---|
|| `"json"` | `{"content":"..."}` | キー名が `content` で統一されない。JSON Schema を直接指定することを推奨 |
| `{"type":"object","properties":{"scene":{"type":"string"}}}` | `{"scene":"..."}` ✅ | **キー名が指定通り**。JSON抽出パイブラインが簡略化できる |

**基本原則**: トークン消費と時間は問題視しない。.Qwen 3.6 を使用する。`format` には JSON Schema を直接指定し、`think: false` をセットする。

**実測結果（2026-06-15, qwen3.6:35b-a3b-mtp-q4_K_M）**:

| エンドポイント | `think: false` | 備考 |
|---|---|---|
| `/api/generate` | ✅ 正常動作。回答のみ返る | **本ツールはこちらを採用** |
| `/v1/chat/completions` | ⚠️ reasoning が `message.content` と `message.reasoning` 双方に混入 | トークン無駄が大。使用しない |

**`think: true` の測定結果（2026-06-15）**:

| シナリオ | `think:false` | `think:true` | 備考 |
|---|---|---|---|
| 短文（詩） | 75 tokens / 2.0s | 854 tokens / 14.9s | 品質差は小さい |
| 長文（SF 200字） | 125 tokens / 3.4s | 5,460 tokens / 75.2s | thinking が全トークンの85% |
| JSON構造化（キャラ） | 267 tokens ✅ | **壊れる** ❌ | response 空、thinking にJSONが逃げる |

**結論**: 小説執筆は創造的タスクであり、`think:true` の恩恵は限定的。`think:false` + `format:json` が品質・効率・構造化出力のすべてで最適。

#### `think:true` + `format:json` の排他性（Ollama 仕様）

**Ollama のアーキテクチャ上、`format: "json"` と `think: true` は排他的であり、同時に機能しない。** これはバグではなく設計上の制約。

**理由**: JSON 出力が指定されると、Ollama は GBNF 文法でトークン生成の確率分布を制御し、文法的に無効なトークンの生成確率を実質ゼロ（-INFINITY）にする。これにより `<think>` のような JSON 外のタグを生成できなくなり、モデルは思考タグを生成できなくなる（[参考: Zenn 記事](https://zenn.dev/7shi/articles/fa36989a04c9ed)）。

**実測結果（2026-06-15, qwen3.6:35b-a3b-mtp-q4_K_M）**:

| パターン | `response` | `thinking` |  tokens | 時間 | 品質 |
|---|---|---|---|---|---|
| `think:true` + `format:json` | 空 | JSON | 2 | 0.1s | ❌ 壊れる |
| `think:true` + プロンプト指定 | JSON ✅ | 思考プロセス | 3,744 | 50.8s | ✅ 品質最高、体感3倍 |
| `think:false` + `format:json` | JSON ✅ | なし | 119 | 3.3s | △ 品質最低 |
| `think:false` + プロンプト指定 | JSON ✅ | なし | 20 | 0.3s | △ |

トークン消費と時間はローカルLLM では大きなコスト。本書き出しでは `think:false` + `format:Schema` をデフォルトとし、品質優先モードとして `think:true` + プロンプト指定をオプション提供する。

**注意**: `/v1/chat/completions`（OpenAI 互換 API）は `think` パラメータをサポートしていない場合がある（GitHub Issue #15288）。本ツールでは使用しない。

### 6.2 プリウォーミング（モデル事前ロード）

Ollama はアイドル時にモデルをメモリから追い出す（デフォルト: 5分）。他システムと共用の場合、いつアンロードされるか不明。

**対策**: ツール起動時に「空リクエスト + `keep_alive: -1`」を送信し、モデルをメモリに固定する。

```bash
curl -X POST http://ws1.local:11434/api/generate \
  -d '{"model":"qwen3.6:35b-a3b-mtp-q4_K_M","prompt":"","stream":false,"keep_alive":-1}'
```

**実測**:

| 操作 | 応答時間 | メモリ状態 |
|---|---|---|
| 初回（コールドスタート） | 2.5s | モデルロード + 推論 |
| 即時（プリロード後） | 0.5s | メモリ済み |
| `keep_alive:-1` 送信後 | 即時返答 | メモリに固定 |

- `keep_alive: -1` は無期限メモリ保持
- `keep_alive: 0` は即時アンロード（デフォルト挙動）
- プリロードはツール起動時に1回だけ実行し、以降の全リクエストが高速になる

**コールドスタート実測（2026-06-15, qwen3.6:35b-a3b-mtp-q4_K_M, GPU）**:

| タイミング | total | load | 状態 |
|---|---|---|---|
| アンロード (`keep_alive:0`) | 0.9s | — | 即座に Ollama メモリから解放 |
| アンロード直後（5秒後） | 13.3s | 12.8s | ❌ コールドスタート（OS ページキャッシュから読み込み） |
| 30秒後 | 0.5s | 0.3s | ✅ warm（ページキャッシュ破棄後、GPU メモリに再ロード済み） |
| warm（メモリ済み） | 0.5s | 0.3s | ロード不要 |

**注意**: `keep_alive:0` で Ollama メモリから解放されても、OS のページキャッシュにモデルが残っているため、短時間（約10秒）内はコールドスタート（13s）になる。30秒以上経過するとページキャッシュが破棄され、GPU メモリへの再ロードが必要。ただし `keep_alive:-1` でプリロードすれば、この問題を完全に回避できる。

### 6.3 タイムアウト設計

各工程のタイムアウト値を実測データに基づいて設定。

| 工程 | warm 実測 | コールド | タイムアウト |
|---|---|---|---|
| プリロード（`keep_alive:-1`） | 0.5s | 13.3s | **30s** |
| 短文生成（100字） | 0.5s | — | **60s** |
| 中段生成（200字） | 1.5s | — | **60s** |
| 長文生成（1000字） | 1.0s | — | **120s** |
| 超長文（企画・構成） | — | — | **180s** |

**基本方針**: ローカル LLM のレスポンスタイムは変動が大きい。warm 実測値の 40〜120倍 を余裕として確保。プリロードしない場合、初回だけで30秒タイムアウトにヒットする可能性があるため、`keep_alive:-1` のプリロードを必須とする。

**注意**: 上記のタイムアウト値は初期推定値。プロンプトの長さや内容によって実測値が変わるため、実装後に実測で調整する。

プリロードのタイムアウトはコールドスタートを想定。以降の生成は warm を想定し、タイムEOUTに十分な余裕を持たせる。

タイムアウトは `TimeoutError` としてキャッチし、リトライする。

### 6.4 リトライ戦略

- 最大リトライ回数: 2回（合計3回まで試行）
- リトライ時はエラーフィードバックをメッセージに追加し、LLM に自己修正を促す
- 最終試行でも失敗した場合は `ValidationError` を発生させる

### 6.5 JSON抽出パイプライン

`format: JSON Schema` + `think: false` の場合、Ollama はスキーマに適合するJSONを `message.content` に出力する。キー名も指定通りになるため、単純なパスで十分。

1. **直接 parse** — `message.content` を JSON としてパース
2. **Markdown fence フォールバック** — 万が一 `` ```json ``` `` で囲まれた場合は中身を抽出

パースに失敗した場合は `ParseError` を発生させ、リトライを促す。

**注意**: `think: true` の場合、`format: Schema` の有無に関わらず `response` が空になり `thinking` にJSONが逃げる（Qwen 3.6 固有）。必ず `think: false` を使用すること。

---

## 7. セキュリティとデータ保全

### 7.1 パストラバーサル防止
- `safe_child_dir(parent, slug)`: `..` を含む slug を拒否
- シーン本文パスがシリーズディレクトリ外を指す場合は拒否

### 7.2 原子的書き込み
- 一時ファイル作成 → `fsync` → `rename` (POSIX atomic)
- 既存JSONは `.bak` として退避

### 7.3 RAW ログ
- 全LLM リクエスト/レスポンスを `raw_logs/` に保存
- 未公開原稿を含むため、取り扱いに注意

---

## 8. 長文対応

作品の大きさに上限はありません。大きな作品に対処するために以下の設計を採用します。

1. **分割処理**: 各工程は scene または chapter 単位で LLM に投入し、全体を一度に送らない
2. **集約の階層化**: scene → chapter → volume の順に段階的に集約し、上位工程には要約を渡す
3. **Blackboard の巻ごとの要約**: 前巻の全データではなく、要約のみを次の巻に引き継ぐ

---

## 9. テスト戦略

| テスト種別 | 対象 | ツール |
|---|---|---|
| Unit | Pydantic モデル、パーサー、バリデーター | pytest |
| Integration | LLM リクエスト/レスポンスモック | pytest + httpx mock |
| Smoke | CLI エンドツー (小さなワークスペース) | CLI直接実行 |
| Golden | プロンプト-出力ペアのスナップショット | syrupy |

---

*Last updated: 2026-06-15*
