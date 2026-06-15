# NovelForge Pipeline Design

## 1. CLI コマンド

### 1.1 グローバルオプション

| オプション | 短縮 | デフォルト | 説明 |
|---|---|---|---|
| `--config` | `-c` | `./.novel-forge.yaml` | 設定ファイルパス |
| `--workdir` | `-w` | 設定ファイル or カレント | 作業ディレクトリ |
| `--volume` | `-V` | 設定ファイル or `1` | 処理対象の巻番号 |
| `--model` | `-m` | 設定ファイル or デフォルト | LLM モデル名 |
| `--timeout` | `-t` | 工程別デフォルト | LLM タイムアウト (秒) |

### 1.2 使用例

```bash
# 初回: plan で作業フォルダ自動作成
uv run novel-forge plan "近未来東京 記憶探偵"
# → ./20260615_近未来東京記憶探偵/ に作業フォルダ作成
# → series_plan.json 生成（LLM自己レビュー結果含む）
# → .novel-forge.yaml 作成（workdir 自動設定）
# → 人間が内容を確認。問題なければ自動的に次工程へ

# 一括実行
uv run novel-forge complete "..."   # plan → outline → write → export

# カスタム作業ディレクトリ
uv run novel-forge plan "..." --workdir ./my-custom-dir

# 既存シリーズで再開
uv run novel-forge complete --workdir ./20260615_近未来東京記憶探偵

# 巻2に切り替え
uv run novel-forge next-volume
uv run novel-forge outline -V 2
```

### 1.3 段階実行コマンド

```bash
uv run novel-forge plan          --keywords "..."   # シリーズ企画（LLM自己レビュー→人間確認）
uv run novel-forge outline                        # 巻アウトライン（LLM自律）
uv run novel-forge write                          # シーン執筆（LLM自律）
uv run novel-forge export                         # KDP 向け出力（LLM自律）
uv run novel-forge bible         --action view    # メタデータ台帳
uv run novel-forge status                         # 進捗確認
uv run novel-forge resume                         # 中断した工程から再開
uv run novel-forge next-volume                    # 次巻へ
uv run novel-forge recover                        # 破損復旧
uv run novel-forge illustrate                     # 表紙画像プロンプト
uv run novel-forge complete                      # plan から一括実行
```

**削除されたコマンド**: `review`, `revise`, `quality` — LLM 自律処理のため CLI コマンドとして不要。

---

## 2. NovelEngine (engine.py)

中核となる状態機械。全コマンドはこのエンジンを通ります。

| コマンド | 役割 |
|---|---|
| `plan` | キーワードからシリーズ企画を生成。**LLM自己レビュー後、人間が内容を確認して次工程へ** |
| `outline` | 巻アウトライン（章・シーン構成）を生成。**LLM自律レビュー（構造的妥当性・シーン間の一貫性）を含む** |
| `write` | シーン本文を生成し、レビュー・改稿・品質ゲートを実行（**全工程LLM自律**） |
| `export` | KDP 向け出力を生成。最終レビュー（LLM自律）結果を `kdp_readiness_report.md` に記録 |
| `bible` | メタデータ台帳を更新・参照 |
| `status` | 現在の進捗と文字数を表示 |
| `complete` | plan → outline → write → export を一括実行 |
| `next-volume` | 次巻のアウトラインを生成 |
| `recover` | 破損した状態ファイルを復旧 |
| `resume` | 中断した工程から再開 |
| `illustrate` | 表紙画像プロンプト |

---

## 3. VolumeOutlinePipeline (volume_outline.py)

巻アウトラインの生成から自己レビュー・自己修正までを担当する。

**重要性**: 巻アウトラインは作品の品質を握る。シーン本文はすべてアウトラインの枠組み内で書かれるため、アウトラインが破綻すると連鎖的にシーン品質が低下する。

### 3.1 生成（設計）

シリーズ企画をベースに、1巻の構造を以下の階層で設計する。

```python
class VolumeOutline(BaseModel):
    volume_number: int
    title: str
    premise: str                           # 巻の前提（1〜2文）
    chapters: list[ChapterPlan]

class ChapterPlan(BaseModel):
    number: int
    title: str
    purpose: str                           # 章の役割（物語機能）
    scenes: list[ScenePlan]

class ScenePlan(BaseModel):
    number: int
    title: str
    pov: str
    goal: str                              # MVME: "(State > Action | Result)"
    conflict: str
    outcome: str
    characters: list[str]
```

**章の役割（物語機能）:**

| 役割 | 説明 | 典型的な配置 |
|---|---|---|
| `introduction` | 導入。状況とキャラクターを提示 | 巻の最初の1〜2章 |
| `rising_action` | 展開。緊張感を高める | 巻の中盤 |
| `turning_point` | 転換。物語の方向性が変わる | 巻の中盤〜終盤の境 |
| `climax` | クライマックス。最大の緊張 | 巻の終盤1〜2章 |
| `resolution` | 収束。疑問の解決と次巻への伏線 | 巻の最後の1章 |

**設計時の構造的制約:**

1. **物語の弧（Story Arc）**: 導入→展開→転換→クライマックス→収束の流れが明確であること
2. **キャラクターアーク**: メインキャラクターに変化（成長・堕落・気づき）があること。変化は巻アウトライン内で完結せず、複数巻にわたる弧（Series Arc）として設計されていること
3. **ペース配分**: 全シーンの約20%を導入、50%を展開・転換、30%をクライマックス・収束に割り当てる
4. **連続性**: 各シーンの `outcome` が次のシーンの `goal`（State部分）に繋がっていること。シーン間で事実・状態・ロケーションが矛盾しないこと
5. **サブプロット**: メイン物語に加えて1〜2つのサブプロットが存在し、少なくとも1つは巻内で解決すること
6. **伏線**: 次巻への伏線が1箇所以上含まれること。伏線は Bible に記録される

### 3.2 LLM自己レビュー

生成したアウトラインを LLM 自身で評価する。

```python
class OutlineReview(BaseModel):
    structural_validity: StructuralReview      # 構造的妥当性
    scene_coherence: CoherenceReview            # シーン間の論理一貫性
    pace_analysis: PaceReview                  # ペース配分
    character_arc_review: CharacterArcReview   # キャラクターアーク
    overall_score: float                       # 総合評価（0.0〜10.0）
    issues: list[Issue]                        # 問題点
    suggestions: list[str]                     # 改善提案

class StructuralReview(BaseModel):
    has_clear_arc: bool
    chapter_roles_valid: bool
    climax_placement_valid: bool
    score: float

class CoherenceReview(BaseModel):
    scene_transitions_valid: bool
    no_contradictions: bool
    state_continuity: bool
    score: float

class PaceReview(BaseModel):
    introduction_ratio: float
    development_ratio: float
    climax_ratio: float
    pacing_comment: str
    score: float

class CharacterArcReview(BaseModel):
    protagonist_has_arc: bool
    arc_believability: float
    supporting_chars_used: bool
    score: float

class Issue(BaseModel):
    severity: Literal["critical","major","minor"]
    category: str
    description: str
    affected_elements: list[str]
```

**深刻度の定義:**

| 深刻度 | 説明 | 対応 |
|---|---|---|
| `critical` | 物語の根幹に関わる（論理的破綻、致命的な矛盾） | 必ず修正 |
| `major` | 品質に大きく影響する（ペースの崩れ、キャラクターの不自然な行動） | 可能な限り修正 |
| `minor` | 改善点としては望ましいが必須ではない | 余力があれば修正 |

### 3.3 自己修正

**修正対象の判定:**
```
overall_score >= 7.0 かつ critical な issue が0件 → 合格
それ以外 → 不合格、自己修正を実行
```

**自己修正の手順:**
1. **critical** な issue を修正: 該当箇所を再生成
2. **major** な issue を修正: 該当箇所を改善
3. 修正後の再レビュー
4. **最大3回**まで繰り返す。3回不合格なら最も問題の少ないバージョンを採用

**修正時の注意:**
- 部分的修正（該当章・該当シーンのみ再生成）を基本とする
- 全体的な構造に問題がある場合のみ全体を再生成する
- 修正履歴を `vol01_outline_revision_log.json` に記録する

### 3.4 出力

| ファイル | 内容 |
|---|---|
| `vol01_outline.json` | 巻アウトライン（章・シーン構成） |
| `vol01_outline_review.json` | 自己レビュー結果 |
| `vol01_outline_revision_log.json` | 修正履歴 |

---

## 4. ScenePipeline (scene_pipeline.py)

シーン単位の処理パイプライン。**全工程が LLM 自律。人間は介入しない。**

**基本原則: LLMが生成したものはすべてLLMがレビューする。**

| 階層 | 設計 | レビュー | 無限ループ防止 |
|---|---|---|---|
| シリーズ企画 | LLM | LLM（自己レビュー） | 最大3回。人間が内容を確認（暗黙承認） |
| 巻アウトライン | LLM | LLM（構造的妥当性・シーン間の一貫性） | 最大3回 |
| シーン本文 | LLM | LLM（文章品質・物語の論理） | 最大3回。3回不合格→`force_exported` |

### 4.1 処理順序

1. **Draft** — アウトラインとコンテキストから初稿を生成
2. **Review** — 初稿を評価し、改善点を抽出（人間には見せない）
3. **Quality Gate** — レビュー結果に基づき合格/不合格を判定
4. **改稿** — 不合格の場合、レビュー結果に基づき自動改稿
5. **再評価** — 改稿後に再度 Quality Gate 判定
6. **Summarize** — 合格した本文から要約を生成し、Blackboard に事実を記録

### 4.2 無限ループ防止

```
Quality Gate 不合格 → 改稿 → 再評価 → 不合格 → 改稿 → 再評価 → ...
```

このループは **最大3回** まで。3回不合格でも `force_exported` フラグを立てて続行する（中断しない）。

| 試行 | 動作 |
|---|---|
| 1回目 | Draft → Review → Quality Gate |
| 2回目 | 不合格 → 改稿 → Quality Gate |
| 3回目 | 不合格 → 改稿 → Quality Gate |
| 3回不合格 | `force_exported` フラグを立てて続行 |

### 4.3 レビューと改稿は別プロンプト

- **scene_draft.md**: シーン執筆用（MVME goal 使用）
- **scene_review.md**: レビュー用（評価基準に特化。本文生成指示は含めない）
- **scene_revision.md**: 改稿用（レビュー結果を受けて改善。新規生成ではない）

---

## 5. Resume (resume.py)

中断した制作を再開する。

```python
class Resume:
    """現在の状態を読み込み、未完了のタスクから再開する"""

    def detect_state(self) -> dict:
        """state.json から現在状態を読み込む"""

    def next_tasks(self) -> list[str]:
        """未完了のタスク一覧を返す"""

    def run(self, phase: str | None = None):
        """指定 phase から再開。None は最初の未完了から"""
```

---

## 6. Blackboard (blackboard.py)

物語の事実を管理する。

```python
class Blackboard:
    facts: list[Fact]              # (subject, predicate, object, confidence)

    def add_fact(summary, details, characters)
    def query_recent(limit) -> str   # プロンプト注入用
    def check_consistency(new_fact) -> list[str] # 矛盾検出
    def scene_summary(key) -> str
    def to_prompt_context() -> str    # LLM 注入用フォーマット
```

---

## 7. CoverPromptGenerator (cover_prompt.py)

表紙画像を生成するためのプロンプトとメタデータを出力する。画像自体は生成しない（外部ツールを使用）。

```python
class CoverPromptGenerator:
    def __init__(self, prompts, bible, series_plan):

    def generate(self, volume_number: int) -> dict
        # cover_prompt.json スキーマに適合する dict を返す
```

---

## 8. QualityGate (quality.py)

```python
class QualityGate:
    def check_scene(record: SceneRecord) -> dict
        # Returns: {"passed": bool, "score": float, "issues": [...]}

    def check_volume(records: list[SceneRecord], review: dict) -> dict
        # Returns: {"ready_for_publication": bool, "issues": [...]}

    def ensure_export_allowed(review: dict, force: bool) -> None
        # Raises QualityGateError if not ready

    def check_simplified_chinese(text: str) -> list[str]
        # 簡体字検出: opencc-purepy で繁体字に変換できる文字を特定
        # 返り値: 検出された簡体字のリスト（空なら問題なし）
```

### 8.1 簡体字検出

LLM の応答に簡体字が混じった場合、品質ゲートで `critical` issue として記録する。

- **検出手法**: opencc-purepy（`s2t` 変換）を使用。テキスト中の各文字を繁体字に変換し、変換された文字を簡体字と判定
- **誤検知防止**: 日本語常用漢字（簡・体・学・国・会など）は繁体字と同一コードポイントのため変換されない。opencc の辞書ベース判定により、これらは誤検知されない
- **アクション**: リトライなし。`SceneRecord.quality_gate` に `simplified_chinese: [検出文字リスト]` を記録。`kdp_readiness_report.md` に集約
- **防止策**: システムプロンプト（`prompts/system.md`）に「简体中文・簡体字は使用しない」と明記

---

## 9. 状態遷移

```
Volume status:
  planned → outlined → drafting → drafted → exported → finalized
                                                        → force_exported

Scene status:
  planned → drafted → reviewed → reviewed_n (n=1,2,3) → revised

Resume (再開):
  任意の状態から再開可能。状態は .state.json から読み込まれる。
  planned → plan から再開
  outlined → outline から再開
  drafting → write から再開（未完了のシーンのみ再生成）
  drafted → export から再開
```

---

## 10. 人間介入ポイント

**方針: 人間介入を最小限に。ツールが自律的にレビュー・改稿する。**

| 介入ポイント | タイミング | 内容 | 必須/任意 |
|---|---|---|---|
| シリーズ企画の確認 | plan 直後 | LLM自己レビュー結果を人間が確認。問題なければ暗黙的に次工程へ | **必須（暗黙承認）** |
| 最終レビュー | export 直後 | kdp_readiness_report.md の確認 | 任意 |

**それ以外の工程はすべて LLM 自律。人間には見せない。**

---
