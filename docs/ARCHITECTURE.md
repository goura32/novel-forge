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
- **JSON 出力**: `response_format = {"type": "json_object"}` + `thinking:false` の組み合わせで安定した JSON Schema 適合を確認
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

`/v1/chat/completions` を採用。

- `response_format = {"type": "json_object"}` は `thinking:false` 併用で安定
- role 構造 (system/user/assistant) で精密な制御が可能

### 6.2 リトライ戦略

LLM リクエストは失敗しやすいため、検証エラー時に自動リトライします。

- 最大リトライ回数: 2回（合計3回まで試行）
- リトライ時はエラーフィードバックをメッセージに追加し、LLM に自己修正を促す
- 最終試行でも失敗した場合は `ValidationError` を発生させる

### 6.3 JSON抽出パイプライン

LLM の応答から JSON を安定して抽出するため、4段階のフォールバックを使用します。

1. **Content 直接 parse** — message.content をそのまま JSON として解釈
2. **Markdown fence 除去** — `` ```json ``` `` で囲まれた中身を抽出
3. **Brace 検索** — 応答内の最初の `{...}` を候補として抽出
4. **Thinking fallback** — qwen3.6 系で content ではなく thinking 欄に出力が逃げる問題への対策

いずれの段階でもパースに失敗し、スキーマ検証でも不一致の場合は `ParseError` を発生させます。

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
