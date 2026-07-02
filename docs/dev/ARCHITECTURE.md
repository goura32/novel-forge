# NovelForge Architecture

## 1. 設計背景

NovelForge は、ローカルLLM で小説シリーズを企画・構成・執筆・出力する Python CLI ツール。

### 採用アーキテクチャ

4層アーキテクチャ:

| Layer | 役割 | 主要コンポーネント |
|---|---|---|
| CLI | ユーザー対話 | `cli.py` (Typer) |
| Orchestration | 状態遷移、パイプライン制御 | `engine/` (NovelEngine + standalone functions) |
| Domain | シーン執筆、レビュー、改稿 | `scene_writer.py` |
| Infrastructure | LLM通信、永続化、スキーマ検証 | `llm_client.py`, `schemas.py`, `name_registry.py`, `logging_config.py` |

---

## 2. モジュール構成

```
src/novel_forge/
├── cli.py                  # CLI エントリポイント (Typer)
├── engine/
│   ├── __init__.py         # NovelEngine クラス定義 (thin facade)
│   ├── infra.py            # make_engine(), ロック, status/doctor
│   ├── base.py             # NovelEngineBase — __init__, state, DI
│   ├── plan.py             # plan() — 3フェーズ (core → characters → volumes)
│   ├── design.py           # design() — 3フェーズ (volume → chapter → scene)
│   ├── write.py            # write() — シーン執筆ループ
│   ├── export.py           # export(), resume(), status()
│   └── review.py           # generate_and_review(), format_review_text()
├── scene_writer.py         # SceneWriter — draft/review/revise/summarize/file-I/O
├── models.py               # データモデル (Pydantic)
├── llm_client.py           # LLM クライアント (Ollama streaming + {schema} 置換)
├── json_parser.py          # NDJSON パース・型変換
├── schemas.py              # JSON Schema スキーマローダ
├── name_registry.py        # キャラクター名重複排除
├── logging_config.py       # ログ出力
├── quality_gate.py         # シーン品質ゲート (issues severity ベース)
└── prompts.py              # プロンプト管理
```

### 責務分割

| モジュール | 責務 |
|---|---|
| `NovelEngine` | plan/design/write/export のオーケストレーション (thin facade) |
| `plan()` | シリーズ企画生成 (3フェーズ) |
| `design()` | 巻デザイン生成 (3フェーズ) |
| `write()` | シーン執筆ループ |
| `export()` | KDP 出力、レポート生成 |
| `review()` | generate_and_review — レビュー→改稿ループ |
| `SceneWriter` | シーンの draft/review/revise/summarize/file-I/O |
| `LLMClient` | LLM 通信、`{schema}` → スキーマJSON 置換 |
| `json_parser` | NDJSON ストリームパース、型補正 |
| `name_registry` | キャラクター名の used_names.json 管理 |
| `quality_gate` | severity ベースの revision_needed 判定 |

### Thin Facade パターン

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

### 依存性注入

```python
class NovelEngineBase:
    def __init__(
        self,
        workdir: Path,
        model: str | None = None,
        llm_client: LLMClient | None = None,      # 注入可能
        prompt_manager: PromptManager | None = None,
        storage: StateStorage | None = None,        # 注入可能
        bb_storage: BlackboardStorage | None = None, # 注入可能
        bible_storage: BibleStorage | None = None,   # 注入可能
        ctx_builder: ContextBuilder | None = None,   # 注入可能
        bible_mgr: BibleManager | None = None,        # 注入可能
        scene_writer: SceneWriter | None = None,    # 注入可能
        ...
    ):
```

テスト時にモックを注入可能:

```python
engine = NovelEngine(
    workdir=tmp_path,
    llm_client=MockLLMClient(),
    storage=MockStorage(),
    scene_writer=MockSceneWriter(),
)
```

---

## 3. LLM 通信仕様

### {schema} プレースホルダ

```python
# llm_client.py — complete_json()
if schema is not None:
    schema_data = {k: v for k, v in schema.items() if k not in ("$schema", "title", "description")}
    schema_text = json.dumps(schema_data, ensure_ascii=False)
    replacement = (
        f"以下のスキーマに従って、実際のデータ値を埋めた JSON のみを出力すること。"
        f"スキーマ構造そのものを返さないこと。\n\n{schema_text}"
    )
    user_prompt = user_prompt.replace("{schema}", replacement)
```

- **プロンプト**: `{schema}` のみ（構造はスキーマファイル参照）
- **スキーマ**: `schemas/*.json` に定義
- **コード**: `complete_json()` 実行時に置換

### リトライ戦略

- **バリデーションエラー**: seed 変えて再生成（プロンプト変更しない）
- **レビュー修正**: revise_fn で seed 変えて再生成
- **revision_needed**: コード側で機械判定（致命的→true, 重大→true, 重要≥2→true）

### レビュースキーマ (統一)

全レビューで同じ構造。`category` enum のみ各スキーマで異なる:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "required": ["issues"],
  "properties": {
    "issues": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["severity", "category", "description", "suggestion", "before", "after"],
        "properties": {
          "severity": { "type": "string", "enum": ["致命的", "重大", "重要", "軽微"] },
          "category": { "type": "string", "enum": ["<各スキーマ固有>"] },
          "description": { "type": "string" },
          "suggestion": { "type": "string" },
          "before": { "type": "string" },
          "after": { "type": "string" }
        }
      }
    }
  }
}
```

### generate_and_review パターン

```python
from novel_forge.engine.review import generate_and_review

result = generate_and_review(
    generate_fn=lambda p, s: engine._llm.complete_json("volume_design", system, p, schema, seed_offset=s),
    validate_fn=_validate_volume_design,
    review_fn=lambda r, sys: _review_volume_design(engine, r, sys),
    revise_fn=lambda r, rv, sys, so=0: engine._llm.complete_json("volume_design", sys, revise_prompt, schema, seed_offset=so),
    system=system,
    user_prompt=prompt,
    kind="volume_design",
    llm=engine._llm,
    quality=engine._quality,
    strict=engine._strict,
)
```

### キャラクター名重複排除

`name_registry.py` が `workdir/used_names.json` を管理。

- `load_used_names()`: 既読名を set で返す
- `record_names()`: Plan完了時に新規名を記録
- `plan()` の `_generate_plan_characters` で既存名をプロンプトに含める

---

## 4. データフロー

```
キーワード
  → plan()     → series_plan.json
  → design()   → vol01.json + ch*/sc*..json (全巻)
  → write()    → sc*.md (初稿 + 改稿) + blackboard/bible 更新
  → export()   → series_dir/exports/slug_vol01.md + metadata + kdp_report
```

### 状態管理

```
Volume: 計画中 → デザイン済 → 初稿済 → 執筆中 → 出力済
Scene:  計画中 → 初稿済 → 修正済 / 強制出力済
```

---

## 5. 出力ファイル構成

```
<series_dir>/
├── state.json                     # プロジェクト状態
├── series_plan.json               # シリーズ企画
├── used_names.json                # 使用済みキャラクター名
├── blackboard.json                # 事実記録（サマリー、連続性）
├── _raw_logs/                     # LLM 生データ
│   ├── plan/                      # plan_{attempt}_{seed}/
│   ├── design/                    # design_{attempt}_{seed}/
│   └── write/                     # write_{attempt}_{seed}/
├── vol01/
│   ├── vol01.json                 # 巻デザイン
│   ├── vol01_ch01/
│   │   ├── vol01_ch01.json        # 章設計
│   │   ├── vol01_ch01_sc01.json   # シーンデザイン
│   │   └── ...
│   └── ...
└── exports/
    ├── <slug>_vol01.md
    ├── <slug>_vol01_metadata.json
    └── <slug>_vol01_kdp_readiness_report.md
```

### RAWデータ構造

```
_raw_logs/plan/20260629_064606_series_plan_core/
├── raw_summary.md              # 人が読める形式（追記）
│                               # - request: messagesのcontentを出力
│                               # - response: contentを出力（thinking除外）
│                               # - タイムスタンプ付きで追記
└── details/                    # 元データ（gzip）
    ├── request_0_0.json.gz     # attempt=0, seed_offset=0
    ├── response_0_0.json.gz    # LLM 生出力
    ├── request_0_1.json.gz     # attempt=0, seed_offset=1 (revision)
    └── response_0_1.json.gz
```

- ディレクトリ名: `{YYYYMMDD_HHMMSS}_{kind}`（実行単位の識別）
- `raw_summary.md` は追記モード。新しいLLM呼び出しのたびに追記される
- `thinking` は長いため `raw_summary.md` では除外される

---

## 6. LLM モデル

**推奨**: `qwen3.6:35b-a3b-mtp-q4_K_M`

- 262K コンテキスト
- JSON + think: true で安定
- VRAM 効率: Q4 量子化

**パラメータ**: num_predict=-1, think=true, seed=42+N(リトライ毎インクリメント)

---

## 7. 設計原則

1. **プロンプト/スキーマ分離**: プロンプトに構造を埋め込まない。`{schema}` プレースホルダ + コードで置換
2. **revision_needed はコード判定**: LLM は boolean を推測せず、severity ベースでコード計算
3. **既存slug 重複排除**: 新規slug 生成時に `_get_existing_slugs` で既存ディレクトリからslugを収集
4. **既存キャラクター名重複排除**: `name_registry.py` で管理、プロンプトに含める
7. **Mixin 排除**: 多重継承を避け、スタンドアロン関数 + thin facade パターンを採用
8. **依存性注入**: テスト時にモックを注入可能
9. **レビュースキーマ統一**: 全フェーズで同じスキーマ構造、`category` enum のみ異なる
10. **strict mode既定**: `generate_and_review` デフォルトで strict=True（最大回数到達→`RuntimeError`→パイプライン停止）。非strict時はbest-effort

---

## 8. ログ・RAWデータ

- ログ: `workdir/novel_forge.log`（追記モード、全シリーズ共通）
- RAW: `_raw_logs/{phase}/{YYYYMMDD_HHMMSS}_{kind}/`
  - `raw_summary.md`: 人が読める形式（追記、`--raw-log` 時のみ）
  - `details/`: gzip 元データ（リクエスト・レスポンス）

## 9. プロンプトテンプレート一覧

| テンプレート | フェーズ | `{schema}` | `{keywords}` | `{core_text}` | `{characters_text}` | `{series_plan}` | `{used_names}` | `{existing_slugs}` |
|---|---|---|---|---|---|---|---|---|
| system.md | 全共通 | - | - | - | - | - | - | - |
| series_plan_core.md | Plan (1) | ✓ | ✓ | - | - | - | - | ✓ |
| series_plan_core_revision.md | Plan (1) 修正 | ✓ | - | ✓ | - | - | - | - |
| series_plan_characters.md | Plan (2) | ✓ | - | ✓ | - | - | ✓ | - |
| series_plan_characters_revision.md | Plan (2) 修正 | ✓ | - | ✓ | ✓ | - | - | - |
| series_plan_volumes.md | Plan (3) | ✓ | - | ✓ | ✓ | - | - | - |
| series_plan_volumes_revision.md | Plan (3) 修正 | ✓ | - | ✓ | ✓ | - | - | - |
| volume_design.md | Design (1) | ✓ | - | - | - | ✓ | - | - |
| volume_design_revision.md | Design (1) 修正 | ✓ | - | - | - | ✓ | - | - |
| chapter_design.md | Design (2) | ✓ | - | - | ✓ | - | - | - |
| chapter_design_revision.md | Design (2) 修正 | ✓ | - | - | ✓ | - | - | - |
| scene_design.md | Design (3) | ✓ | - | - | - | - | - | - |
| scene_design_revision.md | Design (3) 修正 | ✓ | - | - | - | - | - | - |
| scene_draft.md | Write | ✓ | - | - | - | - | - | - |
| scene_revision.md | Write 修正 | ✓ | - | - | ✓ | - | - | - |
| scene_summary_and_bible_update.md | Write 後処理 | ✓ | - | - | - | - | - | - |
| *_review (共通) | レビュー | ✓ | - | - | - | - | - | - |

---

*Last updated: 2026-06-29*
