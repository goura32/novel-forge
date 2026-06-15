# NovelForge Prompt Management

## プロンプトの管理方針

プロンプトは `prompts/` の Markdown ファイルで管理する。コードには直書きしない。

## プロンプト一覧

```text
prompts/
├── system.md                    # 共通システムプロンプト（JSON 出力指示、ジャンル/ペルソナ）
├── series_plan.md               # シリーズ企画（人間が方向性を確認）
├── series_plan_review.md        # シリーズ企画の自己レビュー
├── volume_outline.md            # 巻アウトライン生成
├── volume_outline_review.md     # 巻アウトラインの自己レビュー
├── volume_outline_revision.md   # 卷五トラインの自己修正
├── scene_draft.md               # シーン初稿（MVME goal 使用）
├── scene_review.md              # シーンレビュー（評価基準に特化）
├── scene_revision.md            # シーン改稿（レビュー結果を受けて改善）
├── scene_summary.md             # シーン要約
├── scene_quality_gate.md        # シーン品質ゲート（合格/不合格判定）
├── bible_update.md              # メタデータ台帳更新
├── kdp_metadata.md              # KDP メタデータ
├── kdp_final_review.md         # 最終レビュー（全巻通読）
└── cover_prompt.md              # 表紙画像生成プロンプト
```

## レビューと改稿は別プロンプト

**原則**: 同じプロンプトで書いて評価しない。自己評価バイアスを防ぐため、生成・レビュー・改稿はそれぞれ別のプロンプトファイルを使用する。

| 工程 | 生成 | レビュー | 改稿 |
|---|---|---|---|
| シリーズ企画 | `series_plan.md` | `series_plan_review.md` | 該当なし（人間が確認） |
| 巻アウトライン | `volume_outline.md` | `volume_outline_review.md` | `volume_outline_revision.md` |
| シーン本文 | `scene_draft.md` | `scene_review.md` | `scene_revision.md` |
| 最終レビュー | 該当なし | `kdp_final_review.md` | 該当なし |

## プロンプトの構造

各プロンプトは `{variable}` プレースホルダーを使用する。`prompts.py` の `render_prompt()` で置換。

必須プレースホルダー:

| 工程 | 必須変数 |
|---|---|
| シリーズ企画 | `{keywords}`, `{lang}` |
| 巻アウタライン | `{series_plan}`, `{volume_number}`, `{genre}`, `{lang}` |
| シーン執筆 | `{series_plan}`, `{outline}`, `{scene}`, `{context}`, `{continuity}`, `{lang}` |
| シーンレビュー | `{scene}`, `{outline}`, `{context}`, `{lang}` |
| シーン改稿 | `{scene}`, `{review}`, `{lang}` |
| 品質ゲート | `{scene}`, `{review}`, `{lang}` |

## レビュープロンプトの共通ルール

全レビュープロンプト（`*_review.md`）は以下の構造に従う:

1. **評価基準の提示**: 何を基准として評価するかを明示
2. **出力形式**: JSON Schema に適合する構造化出力を指示
3. **改善提案**: 問題点だけでなく具体的な改善案を含める
4. **深刻度付け**: `critical` / `major` / `minor` の3段階で深刻度を付与
5. **制約**: 本文の新規生成は指示しない（レビュー・評価のみ）

## 品質基準（全工程共通）

全レビューと品質ゲートは以下の商業レベル基準を適用する。

1. **構造**: 目標→障害→災害→反応→ジレンマ→決断のビートを遵守
2. **表現**: Show-don't-tell を徹底し、フィルター単語を排除
3. **網羅性**: 7感覚（視覚・聴覚・嗅覚・触覚・味覚・固有感覚・内臓感覚）を網羅
4. **一貫性**: POV、キャラクター、世界観に矛盾がないこと
5. **重複防止**: シーン内で同一段落や情報が繰り返されないこと

---
