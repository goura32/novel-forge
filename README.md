# NovelForge

**NovelForge** は、Ollama モデルを使って小説シリーズを企画・構成・執筆・レビュー・改稿・出力する Python CLI ツールです。

KDP での商用出版を視野に入れ、LLM の出力揺れや能力不足をツール側で補う設計にしています。**シリーズ > 巻 > 章 > シーン** の階層で制作を管理します。

> **注意**: NovelForge は「出版保証ツール」ではありません。KDP 出版可能品質の最終判断は人間が行う前提です。

## ドキュメント

| ファイル | 内容 |
|---|---|
| [docs/PIPELINE.md](docs/PIPELINE.md) | パイプライン設計（CLI コマンド、エンジン、状態遷移） |
| [docs/PROMPTS.md](docs/PROMPTS.md) | プロンプト管理（一覧、役割定義、言語制約） |
| [docs/dev/ARCHITECTURE.md](docs/dev/ARCHITECTURE.md) | アーキテクチャ（レイヤー構成、データフロー、LLM通信） |
| [docs/GLOSSARY.md](docs/GLOSSARY.md) | 用語集 |

---

## セットアップ

```bash
git clone https://github.com/goura32/novel-forge.git
cd novel-forge
uv venv --python 3.14 .venv
source .venv/bin/activate
uv pip install -e .
```

Ollama に `qwen3.6:35b-a3b-mtp-q4_K_M` が存在することを確認してください。

## モデル接続確認

```bash
uv run novel-forge doctor
```

## クイックスタート

```bash
# 段階的に進める
uv run novel-forge plan    --workdir /mnt/hdd/novel --keywords "近未来東京 記憶探偵"
uv run novel-forge design  --workdir /mnt/hdd/novel
uv run novel-forge write   --workdir /mnt/hdd/novel
uv run novel-forge export  --workdir /mnt/hdd/novel

# 次巻へ進む
uv run novel-forge design  --workdir /mnt/hdd/novel --volume 2

# 中断・再開
uv run novel-forge status  --workdir /mnt/hdd/novel
uv run novel-forge resume  --workdir /mnt/hdd/novel
```

## 主要機能

| 機能 | 説明 | 人間介入 |
|---|---|---|
| シリーズ企画 | キーワードから世界観・キャラクター・構成案を生成 | 確認（暗黙承認） |
| 巻デザイン | 3フェーズ（章構成→章設計→シーン設計）で生成 | なし（LLM自律） |
| シーン執筆 | Blackboard + Bible による継続性維持 | なし（LLM自律） |
| 自律レビュー | 全工程 LLM が自己レビュー・改稿・品質ゲート | なし（LLM自律） |
| Bible 管理 | キャラクター、伏線、関係性、サブプロットの自動追跡 | なし（LLM自律） |
| KDP メタデータ | タイトル案、内容紹介、カテゴリ、キーワード | なし（LLM自律） |
| Markdown エクスポート | 完成原稿の KDP 確認用出力 | なし |
| 最終レビュー | 全巻通読結果を kdp_readiness_report.md に記録 | 任意で確認 |

## 排他制御

同一シリーズ内では `plan` / `design` / `write` / `export` / `resume` は同時に実行できません。

- `series_dir/.lock` ファイルで排他制御
- ロック保持プロセスが終了していたら自動回収（stale lock detection）
- `status` はロック不要（読み取り専用）

```bash
# 同時実行しようとすると即座にエラー
$ novel-forge write --workdir /mnt/hdd/novel
✗ Lock held by PID=12345 (active, 120s ago). Another process is running on this series.
  Wait for it to finish, or remove the lock file manually:
  rm /mnt/hdd/novel/.lock
```

## アーキテクチャ

```
cli.py → engine/ → scene_writer.py
        → llm_client.py → json_parser.py
        → schemas.py
        → name_registry.py
        → quality_gate.py
```

- **CLI Interface** (`cli.py`): ユーザー対話、排他制御
- **NovelEngine** (`engine/`): オーケストレーション層（thin facade + standalone functions）
- **SceneWriter** (`scene_writer.py`): シーン執筆パイプライン（draft/review/revise/summarize）
- **LLMClient** (`llm_client.py`): LLM API 通信（`{schema}` 置換、リトライ、ログ）
- **json_parser** (`json_parser.py`): NDJSON ストリームパース、型変換
- **name_registry** (`name_registry.py`): キャラクター名重複排除
- **QualityGate** (`quality_gate.py`): シーン品質評価（severity ベース）

### Mixin 排除

従来の Mixin パターンを排除し、スタンドアロン関数 + thin facade パターンを採用:

```python
# 従来（Mixin パターン）
class NovelEngine(NovelEngineBase, PlanMixin, DesignMixin, WriteMixin, ExportMixin):
    pass

# 最新（thin facade + standalone functions）
class NovelEngine(NovelEngineBase):
    def plan(self, keywords: str) -> dict:
        return plan(self, keywords)
    def design(self, volume_number: int | None = None) -> dict:
        return design(self, volume_number)
    ...
```

### 依存性注入

テスト時にモックを注入可能:

```python
engine = NovelEngine(
    workdir=tmp_path,
    llm_client=MockLLMClient(),
    storage=MockStorage(),
    scene_writer=MockSceneWriter(),
)
```

## テスト

```bash
uv run pytest tests/ -x -q   # 全テスト
uv run ruff check .          # lint
```

## ライセンス

MIT
