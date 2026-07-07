# NovelForge Implementation Specification

## 1. プロジェクト構造

```text
novel-forge/
├── pyproject.toml
├── README.md
├── config.yaml                   # 設定ファイル
├── docs/
│   ├── ARCHITECTURE.md
│   ├── SPECIFICATION.md
│   ├── PIPELINE.md
│   ├── PROMPTS.md
│   └── GLOSSARY.md
├── prompts/                      # プロンプトテンプレート
│   ├── system.md                 # 共通システムプロンプト
│   ├── series_plan_concept.md    # シリーズ企画（構想）
│   ├── series_plan_concept_review.md
│   ├── series_plan_concept_revision.md
│   ├── series_plan_characters.md # シリーズ企画（キャラクター）
│   ├── series_plan_characters_review.md
│   ├── series_plan_characters_revision.md
│   ├── series_plan_volumes.md    # シリーズ企画（各巻）
│   ├── series_plan_volumes_review.md
│   ├── series_plan_volumes_revision.md
│   ├── volume_design.md          # 巻デザイン（Phase 1: 章構成）
│   ├── volume_design_review.md
│   ├── volume_design_revision.md
│   ├── chapter_design.md         # 章デザイン（Phase 2）
│   ├── chapter_design_review.md
│   ├── chapter_design_revision.md
│   ├── scene_design.md           # シーンデザイン（Phase 3）
│   ├── scene_design_review.md
│   ├── scene_design_revision.md
│   ├── scene_draft.md            # シーン初稿
│   ├── scene_review.md           # シーンレビュー
│   ├── scene_revision.md         # シーン改稿
│   ├── scene_summary_and_bible_update.md
│   ├── kdp_metadata.md
│   └── cover_prompt.md
├── schemas/                      # JSON Schema 定義
│   ├── series_plan_concept.json
│   ├── series_plan_characters.json
│   ├── series_plan_volumes.json
│   ├── volume_design.json
│   ├── chapter_design.json
│   ├── scene_design.json
│   ├── scene_draft.json
│   ├── review.json
│   ├── scene_summary_and_bible_update.json
│   ├── scene_summary.json
│   ├── blackboard.json
│   ├── bible.json
│   ├── bible_update.json
│   ├── cover_prompt.json
│   └── kdp_metadata.json
├── src/
│   └── novel_forge/
│       ├── __init__.py
│       ├── cli.py               # CLI エントリポイント + 排他制御
│       ├── engine/              # NovelEngine (オーケストレーション)
│       │   ├── __init__.py      # NovelEngine クラス定義 (thin facade)
│       │   ├── base.py          # NovelEngineBase (初期化, state, DI)
│       │   ├── plan.py          # plan() — 3フェーズ
│       │   ├── design.py        # design() — 3フェーズ
│       │   ├── write.py         # write() — シーン執筆ループ
│       │   ├── export.py        # export(), resume(), status()
│       │   ├── review.py        # generate_and_review(), format_review_text()
│       │   └── infra.py         # make_engine(), ロック, status/doctor
│       ├── scene_writer.py      # SceneWriter (シーン執筆パイプライン)
│       ├── context_builder.py   # ContextBuilder (コンテキスト構築)
│       ├── bible_manager.py     # BibleManager (Bible 管理)
│       ├── models.py            # Pydantic データモデル
│       ├── llm_client.py        # LLM クライアント
│       ├── json_parser.py       # JSON パース・型変換
│       ├── prompts.py           # プロンプト管理
│       ├── quality_gate.py      # QualityGate
│       ├── schemas.py           # スキーマレジストリ
│       ├── storage.py           # 永続化
│       └── name_registry.py     # キャラクター名重複排除
└── tests/
    └── test_*.py
```

## 2. データモデル

### 2.1 主要モデル

| モデル | ファイル | 説明 |
|---|---|---|
| `ProjectState` | `models.py` | シリーズ全体の状態 |
| `VolumeProgress` | `models.py` | 巻ごとの進捗 |
| `SceneRecord` | `models.py` | シーンごとの生成状況 |
| `Blackboard` | `models.py` | 事実記録 |
| `Bible` | `models.py` | 設定資料集 |
| `CharacterProfile` | `models.py` | キャラクタープロファイル |
| `ForeshadowingItem` | `models.py` | 伏線 |
| `RelationshipItem` | `models.py` | キャラクター関係性 |
| `SubplotItem` | `models.py` | サブプロット |
| `GlossaryItem` | `models.py` | 用語 |
| `VolumeOutline` | `models.py` | 巻アウトライン |
| `SceneWriteContext` | `models.py` | シーン生成用コンテキスト |
| `QualityGateResult` | `quality_gate.py` | 品質ゲート結果 |

### 2.2 ステータス値

**プロジェクトのステータス**: `計画中` / `デザイン済` / `執筆中` / `初稿済` / `出力済` / `強制出力済`

**巻のステータス**: `計画中` / `デザイン済` / `執筆中` / `初稿済` / `出力済` / `強制出力済`

**シーンのステータス**: `計画中` / `初稿済` / `修正済` / `強制出力済`

## 3. 設定ファイル (config.yaml)

`config.yaml` は作業ディレクトリに自動検索されます。存在しない場合はコード内のデフォルト値が使用されます。

```yaml
llm:
  model: "qwen3.6:35b-a3b-mtp-q4_K_M"
  num_predict: -1
  num_ctx: 262144
  timeout_seconds: 3600
  transport_retries: 2    # 一時的な LLM API/通信エラー時のみ。旧 max_retries も互換aliasとして読める
  ollama_host: "ws1.local:11434"
  think: false

quality:
  max_generation_count: 4  # 生成API＋バリデーション最大リトライ（同一工程内）
  max_review_count: 4      # レビュー→修正サイクル最大回数（複数工程にまたがる）
```

優先順位: CLI引数 > config.yaml > デフォルト値

## 4. 永続化

### 4.1 ファイル配置

| ファイル | 内容 | 更新タイミング |
|---|---|---|
| `state.json` | プロジェクト状態 | 各工程完了時 |
| `blackboard.json` | 事実記録 | シーン完了時 |
| `bible.json` | 設定資料集 | シーン完了時 |
| `series_plan.json` | シリーズ企画 | plan 完了時 |
| `vol01.json` | 巻デザイン | design 完了時 |
| `vol01_ch01.json` | 章設計 | design 完了時 |
| `vol01_ch01_sc01.json` | シーンデザイン | design 完了時 |
| `vol01_ch01_sc01.md` | シーン本文 | write 完了時 |
| `used_names.json` | 使用済みキャラクター名 | plan 完了時 |

### 4.2 アトミック書き込み

`storage.py` の全クラスが `tempfile.mkstemp` + `os.rename` でアトミック書き込みを実装。

## 5. 依存性注入

`NovelEngineBase.__init__` で依存性を注入可能:

```python
class NovelEngineBase:
    def __init__(
        self,
        workdir: Path,
        llm_client: LLMClient | None = None,
        storage: StateStorage | None = None,
        bb_storage: BlackboardStorage | None = None,
        bible_storage: BibleStorage | None = None,
        ctx_builder: ContextBuilder | None = None,
        bible_mgr: BibleManager | None = None,
        scene_writer: SceneWriter | None = None,
        ...
    ):
```

テスト時の使用例:

```python
engine = NovelEngine(
    workdir=tmp_path,
    llm_client=MockLLMClient(),
    storage=MockStateStorage(),
    bb_storage=MockBlackboardStorage(),
    bible_storage=MockBibleStorage(),
    scene_writer=MockSceneWriter(),
)
```

### 6. 生成・レビュー回数の制御

`plan` / `design` / `write` / `resume` / `complete` は、生成・レビュー回数をCLIオプションで制御できる。

```bash
novel-forge plan --workdir /mnt/hdd/novel --max-generation-count 5 --max-review-count 5 "キーワード"
novel-forge design --workdir /mnt/hdd/novel --max-generation-count 5 --max-review-count 5
novel-forge write --workdir /mnt/hdd/novel --max-generation-count 5 --max-review-count 5
```

動作:
- **`--max-generation-count`**: LLM API呼び出しとスキーマ/semantic validationの最大リトライ回数。
- **`--max-review-count`**: レビュー→修正サイクルの最大回数。
- 最大回数到達後も重大なvalidation/review問題が残る場合、該当工程は例外で停止する。

現CLIには `--strict` フラグは存在しない。

### 7. 統一レビュースキーマ (review.json)

全レビューで単一の `review.json` スキーマを使用。

```json
{
  "issues": [{
    "severity": "致命的|重要|軽微",
    "field": "対象フィールド名",
    "description": "問題の説明",
    "suggestion": "修正提案",
    "before": "修正前テキスト",
    "after": "修正後テキスト"
  }]
}
```

機械的修正には `field` + `before` + `after` のみで十分。

---

*Last updated: 2026-07-03*
