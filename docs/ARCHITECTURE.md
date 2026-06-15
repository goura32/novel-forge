# NovelForge Architecture Design

## 1. 設計背景

NovelForge は、ローカルLLMを使って小説シリーズを企画・構成・執筆・レビュー・改稿・出力する Python CLI ツールです。

既存の複数ツールで実績のある設計パターンを調査・統合し、より堅牢で高品質な制作パイプラインを実現します。

### 設計パターンの採用

5層アーキテクチャを採用します。各層の詳細な構成図とコンポーネント一覧は [PIPELINE.md](PIPELINE.md) を参照してください。

| Layer | 役割 | 主要コンポーネント |
|---|---|---|
| CLI Interface | ユーザーとの対話 | Typer |
| Orchestration | 状態遷移、パイプライン制御、リトライ | NovelEngine, ScenePipeline, VolumeOutlinePipeline |
| Intelligence | LLM による生成・評価・改善 | PlannerAgent, WriterAgent, CriticAgent |
| State / Memory | 進捗管理、物語の事実、メタデータ | State Machine, Blackboard, Bible |
| Infrastructure | LLM 通信、永続化、ログ | llm_client, storage, raw_logger |

---

## 2. データフロー

### 2.1 制作パイクライン

各フェーズの詳細な処理フロー・評価基準・出力ファイルは [PIPELINE.md](PIPELINE.md) を参照してください。

**概要**:

```
キーワード → [plan] シリーズ企画 + 自己レビュー → 人間確認（暗黙承認）
           → [outline] 巻アウトライン + 自己レビュー → 自己修正（最大3回）
           → [write] シーン執筆（sequential）→ レビュー → 改稿 → 品質ゲート → Blackboard更新
           → [export] 原稿組立 → 最終レビュー → kdp_readiness_report.md
```

- シーンは **sequential のみ**（前シーン要約を `{continuity}` として次シーンに注入）
- アウトライン自己修正は **3段階切り分け**（全体/章/シーン）。部分修正時は前後コンテキストを注入
- シーン品質ゲート不合格 → 自動改稿 → 再評価（最大3回）。3回不合格 → `force_exported` フラグで続行

### 2.2 状態遷移

詳細な状態遷移図と Resume の判定ロジックは [PIPELINE.md §9](PIPELINE.md) を参照してください。

**巻**: `planned → outlined → drafting → drafted → exported → finalized`（`force_exported` は例外パス）
**シーン**: `planned → drafted → reviewed → revised`（最大3回の自動改稿→再評価を経て `revised` へ）

### 2.3 人間介入ポイント

**方針: 人間介入を最小限に。ツールが自律的にレビュー・改稿する。**

| 介入ポイント | タイミング | 内容 | 必須/任意 |
|---|---|---|---|
| シリーズ企画の確認 | plan 直後 | LLM自己レビュー結果を人間が確認。問題なければ暗黙的に次工程へ | **必須（暗黙承認）** |
| 最終レビュー | export 直後 | kdp_readiness_report.md の確認 | 任意 |

**それ以外の工程はすべて LLM 自律。人間には見せない。**

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

詳細なデータモデル定義は [SPECIFICATION.md §3](SPECIFICATION.md) を参照してください。

### 4.1 State Machine (進捗管理)

`ProjectState` が制作進捗を管理。**Blackboard と Bible は `state.json` とは別ファイル**として永続化し、State はメタデータ参照のみ保持します。

### 4.2 Blackboard (物語の事実)

`blackboard.json` として独立ファイルで管理。

- **facts**: `(subject, predicate, object, confidence)` の事実リスト
- **scene_summaries**: シーンごとの要約
- **continuity_notes**: 次シーンへの引き継ぎメモ

**更新**: シーン完了時に WriterAgent が facts を追加。生成時に直近 facts をコンテキスト注入。

### 4.3 Bible (メタデータ台帳)

`bible.json` として独立ファイルで管理。

- **characters**: キャラクタープロファイル（名前、外見、性格、状態）
- **glossary**: 用語と定義
- **foreshadowing**: 伏線と回収状況
- **world_rules**: 世界観ルール

**更新**: 章完了時に、当該章の全シーンから抽出した情報を Bible に反映。

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

`/api/generate` を採用。`format: JSON Schema` + `think: false` で安定した構造化出力。

**`think: true` + `format:json` の排他性（Ollama 仕様）**: 同時に機能しない。JSON 出力指定時は GBNF 文法制御により思考タグを生成できない。**必ず `think: false` を使用すること**。

### 6.2 プリウォーミング

ツール起動時に `keep_alive: -1` でモデルを GPU メモリに固定。Ollama はアイドル時にモデルを追い出す（デフォルト5分）ため、プリロードで防止。

### 6.3 リトライ戦略

- 最大リトライ回数: 2回（合計3回まで試行）
- リトライ時はエラーフィードバックをメッセージに追加
- 最終試行失敗時は `ValidationError` を発生

### 6.4 JSON抽出パイプライン

1. **直接 parse** — `message.content` を JSON としてパース
2. **Markdown fence フォールバック** — `` ```json ``` `` で囲まれた場合の中身を抽出

パース失敗時は `ParseError` を発生させ、リトライを促す。

---

## 7. セキュリティとデータ保全

| 項目 | 内容 |
|---|---|
| パストラバーサル防止 | `..` を含む slug を拒否。シーン本文パスがシリーズ外を指す場合も拒否 |
| 原子的書き込み | 一時ファイル作成 → `fsync` → `rename` (POSIX atomic)。既存 JSON は `.bak` 退避 |
| RAW ログ | 全 LLM リクエスト/レスポンスを `raw_logs/` に保存。未公開原稿を含むため共有禁止 |
| RAW ログローテーション | デフォルト全量保持。`--max-raw-logs N` で最新 N 件のみ |

---

## 8. 長文対応

作品の大きさに上限はありません。大きな作品に対処するために以下の設計を採用します。

1. **分割処理**: 各工程は scene または chapter 単位で LLM に投入し、全体を一度に送らない
2. **集約の階層化**: scene → chapter → volume の順に段階的に集約し、上位工程には要約を渡す
3. **Blackboard の巻ごとの要約**: 前巻の全データではなく、要約のみを次の巻に引き継ぐ

---

*Last updated: 2026-06-16*
