# NovelForge Architecture Design

## 1. 設計背景

NovelForge は、3つの先行リポジトリ（`seriescraft-novel`, `novelpress`, `novel-craftsman`）の知見を統合した、次世代のローカルLLM小説制作パイプラインです。

### 先行リポジトリの分析サマリー

| 概念 | seriescraft-novel | novelpress | novel-craftsman |
|---|---|---|---|
| 制御構造 | State階層モデル（シリーズ>巻>章>シーン）+ 進捗管理パイプライン | Workflow統合パイプライン + 品質ゲート | RS-Arch 3層分離（Agent/Engine/WorldModel） |
| 記憶管理 | state.json 逐次保存 + 要約蓄積 | bible.json メタデータ蓄積 | Blackboard 事実ベース共有メモリ |
| プロンプト戦略 | 段階的コンテキスト注入 | JSON Schema 構造化検証 | MVME (State>Action|Result) 因果強制 |
| API方式 | `/api/generate` + `format:json` | `/v1/chat/completions` + `response_format` | `/api/chat` + `format` schema |
| JSON抽出 | パース + リペア + スキーマ検証 | フォン補正 + Draft202012Validator | 3段階フォールバック（直接>コードブロック>ブレース） |
| 品質管理 | シーン/巻ごとのレビュー + 品質ゲート + 出版前チェック | ready_for_publication + blocking issues チェック | CriticAgent + ConsistencyEngine |
| 中断再開 | state.json永続化 + 备份/復旧 | state.json + .bak + fsync | Blackboard永続化 |

### NovelForge 採用アプローチ

```
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
│  │ Ollama   │  │ Storage  │  │ Logger   │              │
│  │ Client   │  │ (atomic) │  │ (RAW)    │              │
│  └──────────┘  └──────────┘  └──────────┘              │
└─────────────────────────────────────────────────────────┘
```

**Layer採用の根拠**:

| Layer | 採用元 | 採用理由 |
|---|---|---|
| Orchestration | seriescraft-novel のエンジン + novelpress のWorkflow | 堅牢な状態遷移 + パイプライン統合 |
| Intelligence | novel-craftsman の Agent 分離 | LLM出力を隔離し、Engineが検証・制御 |
| State: State Machine | seriescraft-novel の `NovelState` + `ProgressState` | 中断再開・段階的進行管理 |
| State: Blackboard | novel-craftsman の `Blackboard` | Story facts の共有・矛盾防止 |
| State: Bible | novelpress の `bible.json` | キャラクター・用語・継続性のメタデータ管理 |
| Quality Gate | novelpress の `QualityGate` + seriescraft の品質ゲート | ready_for_publication + blocking issues による出版可否判定 |
| LLM Client | novelpress の `OllamaOpenAIClient` | `/v1/chat/completions` + `think:false` で verified |
| Storage | novelpress の atomic write + .bak | データ破壊防止 |

---

## 2. データフロー

### 2.1 制作パイプライン

```
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

```
Volume status:
  planned → outlined → drafting → drafted → reviewed → revised → published
                                                              → force_exported

Scene status:
  planned → drafted → reviewed → revised
```

---

## 3. プロンプト戦略

### 3.1 MVME (Minimalist & Mathematical Edition) の全シーン目標に適用

全シーン目標に構造的アンカー `(S > A | R)` を強制:

```json
{
  "goal": "(State > Action | Result)",
  "description": "雾が濃くなる > 主人公が踏み込む | 視界が完全に遮断される"
}
```

### 3.2 JSON Schema 検証パイプライン

```
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

Pydantic モデルの厳格な状態管理:

```python
class NovelState(BaseModel):
    id: str
    keywords: str
    series_plan: SeriesPlan | None
    volume_outlines: dict[str, VolumeOutline]
    scenes: dict[str, SceneRecord]       # key = "v01_c01_s01"
    blackboard: BlackboardState          # facts + relationships
    bible: BibleState                    # characters + terms + foreshadowing
```

### 4.2 Blackboard (物語の事実)

```python
class BlackboardState(BaseModel):
    facts: list[Fact]                    # (subject, predicate, object, confidence)
    scene_summaries: dict[str, str]    # key → summary
    continuity_notes: list[str]          # 次シーンへの引き継ぎメモ
```

- **Write**: シーン完了時に WriterAgent が facts を追加
- **Read**: WriterAgent 生成時に直近 facts をコンテキスト注入
- **Verify**: ConsistencyEngine が新 facts と既存 facts の矛盾を検出

### 4.3 Bible (メタデータ台帳)

```python
class BibleState(BaseModel):
    characters: list[CharacterProfile]    # 名前、外見、性格、状態
    glossary: list[Term]                 # 用語、定義
    foreshadowing: list[ForeshadowItem]  # 伏線、回収状況
    world_rules: list[str]               # 世界観ルール
```

---

## 5. LLM API 設計

### 5.1 API Endpoint

`/v1/chat/completions` を採用 (novelpress-olient で verified)

理由:
- `/api/generate` + `format:json` はティップシップな挙動がある
- `response_format = {"type": "json_object"}` は `thinking:false` 併用で安定
- `/v1/chat/completions` は role構造で制御可能

### 5.2 リトライ戦略

```python
async def chat_json_with_retry(messages, schema, max_retries=2):
    for attempt in range(max_retries + 1):
        raw = await client.post(chat_completions, ...)
        content = extract_content(raw)         # content 優先, thinking fallback
        parsed = unwrap_schema(content)          # schema適合オブジェクト取り出し
        errors = validate_schema(parsed, schema) # Draft202012Validator
        if not errors:
            return parsed
        if attempt < max_retries:
            messages = enrich_with_errors(messages, errors)
            continue
        raise ValidationError(errors)
```

### 5.3 JSON抽出パイプライン

```python
def extract_json(raw_response) -> dict:
    content = raw_response["choices"][0]["message"]["content"]
    thinking = raw_response["choices"][0]["message"].get("thinking", "")

    # 1. Content直接parse
    obj = try_parse(content)
    if obj: return obj

    # 2. Markdown fence除去
    obj = try_parse(strip_fence(content))
    if obj: return obj

    # 3. brute-force { } 検索
    obj = try_parse(extract_brace(content))
    if obj: return obj

    # 4. thinking fallback (qwen3.6 対策)
    obj = try_parse(thinking)
    if obj: return obj

    raise ParseError(content)
```

---

## 6. セキュリティとデータ保全

### 6.1 パストラバーサル防止
- `safe_child_dir(parent, slug)`: `..` を含むslug を拒否
- シーン本文パスがシリーズディレクトリ外を指す場合は拒否

### 6.2 原子的書き込み
- 一時ファイル作成 → `fsync` → `rename` (POSIX atomic)
- 既存JSONは `.bak` として退避

### 6.3 RAW ログ
- 全LLM リクエスト/レスポンスを `raw_logs/` に保存
- 未公開原稿を含むため、取り扱いに注意

---

## 7. テスト戦略

| テスト種別 | 対象 | ツール |
|---|---|---|
| Unit | Pydantic モデル、パーサー、バリデーター | pytest |
| Integration | LLM リクエスト/レスポンスモック | pytest + httpx mock |
| Smoke | CLI エンドツ南 (小さなワークスペース) | CLI直接実行 |
| Golden | プロンプト-出力ペアのスナップショット | syrupy |

---

*Last updated: 2026-06-15*
