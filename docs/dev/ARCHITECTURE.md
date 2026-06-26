# NovelForge Architecture

## 1. 設計背景

NovelForge は、ロー�ルLLM で小説シリーズを企画・構成・執筆・出力する Python CLI ツール。

### 採用アーキテクチャ

4層アーキテクチャ:

| Layer | 役割 | 主要コンポーネント |
|---|---|---|
| CLI | ユーザー対話 | `cli.py` (Typer) |
| Orchestration | 状態遷移、パイプライン制御 | `engine/` (NovelEngine + Mixins) |
| Domain | シーン執筆、レビュー、改稿 | `scene_writer.py` |
| Infrastructure | LLM通信、永続化、スキーマ検証 | `llm_client.py`, `schemas.py`, `name_registry.py`, `logging_config.py` |

---

## 2. モジュール構成

```
src/novel_forge/
├── cli.py                  # CLI エントリポイント (Typer)
├── engine/
│   ├── __init__.py         # NovelEngine クラス定義
│   ├── infra.py            # make_engine(), ロック, status/doctor
│   ├── base.py             # NovelEngineBase — __init__, state, _generate_and_review()
│   ├── plan.py             # PlanMixin — plan() 3フェーズ
│   ├── design.py           # DesignMixin — design() 3フェーズ
│   ├── write.py            # WriteMixin — write()
│   └── export.py           # ExportMixin — export()
├── scene_writer.py         # SceneWriter — シーン draft → review → revise → summarize
├── models.py               # データモデル
├── llm_client.py           # LLM クライアント (Ollama streaming + {schema} 置換)
├── json_parser.py          # NDJSON パース・型変換
├── schemas.py              # JSON Schema スキーマローダ
├── name_registry.py        # キャラクター名重複排除
├── logging_config.py       # ログ出力（[YYYY-MM-DD HH:MM:SS] [PID] [LEVEL]）
├── quality_gate.py         # シーン品質ゲート（issues severity ベース）
├── prompts.py              # プロンプト管理
└── utils.py                # ユーティリティ
```

### 責務分割

| モジュール | 責務 |
|---|---|
| `NovelEngine` | plan/design/write/export のオーケストレーション |
| `SceneWriter` | シーンの draft/review/revise/summarize/bible_update |
| `LLMClient` | LLM 通信、`{schema}` → スキーマJSON 置換 |
| `json_parser` | NDJSON ストリームパース、型補正 |
| `name_registry` | キャラクター名の used_names.json 管理 |
| `quality_gate` | severity ベースのrevision_needed 判定 |

### Mixin パターン

```python
class NovelEngine(
    NovelEngineBase,    # __init__,, state, _generate_and_review
    PlanMixin,          # plan()
    DesignMixin,        # design()
    WriteMixin,         # write()
    ExportMixin,        # export()
):
    pass
```

---

## 3. LLM 通信仕様

### {schema} プレースホルダ

```python
# llm_client.py — complete_json()
if schema is not None:
    user_prompt = user_prompt.replace("{schema}", json.dumps(schema, ensure_ascii=False))
```

- **プロンプト**: `{schema}` のみ（構造はスキーマファイル参照）
- **スキーマ**: `schemas/*.json` に定義
- **コード**: `complete_json()` 実行時に置換

### リトライ戦略

- **バリデーションエラー**: seed 変えて再生成（プロンプト変更しない）
- **レビュー修正**: revision_fn で seed 変えて再生成
- **revision_needed**: コード側で機械判定（severity=致命的→true, 重大→true, 重要≥2→true）

### キャラクター名重複排除

`name_registry.py` が `workdir/used_names.json` を管理。

- `load_used_names()`: 既読名を set で返す
- `record_names()`: Plan完了時に新規名を記録
- `get_excluded_names()`: used_names.json から取得（バリデーション用）

---

## 4. データフロー

```
キーワード
  → plan()     → series_plan.json
  → design()   → vol01.json + ch*/sc*.json
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
│   ├── plan/
│   ├── design/
│   └── write/
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
_needed はコード判定**: LLM は boolean を推測せず、severity ベースでコード計算
3. **新規slug 生成時にキャラクター名重複排除**: `name_registry.py` で既存名チェック
4. **xxx_revision.json 不要**: 改訂も生成と同じスキーマを使用

---

## 8. ログ・RAWデータ

- ログ: `workdir/novel_forge.log`（追記モード、全シリーズ共通）
- RAW: `_raw_logs/{phase}/{pid}_{kind}/`（gzip）

---

*Last updated: 2026-06-26*
