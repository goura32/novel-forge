# プロンプト管理

## 正本と責務

runtimeが使用するpromptは `src/novel_forge/resources/prompts/` にあります。task ID、prompt、schema、runtime実行経路の対応は [PROMPT_SCHEMA_MAP](PROMPT_SCHEMA_MAP.md) を正とします。

| 層 | 責務 |
|---|---|
| Prompt (`.md`) | 各fieldに書く内容、品質基準、工程責務、出力上の注意 |
| JSON Schema (`.json`) | 型、必須field、有限enum、機械検証可能な構造 |
| Review prompt | 対象artifactと入力根拠に基づくissueの抽出 |
| Revision prompt | issueの反映と未指摘fieldの保全 |
| Python validator | Schemaだけでは表せない意味的整合性 |

`{schema}` は `PromptManager.render_task()` が自動注入します。呼び出し側は `schema` template variableを渡しません。

## 生成・レビュー・改稿

- `plan.series.generate` と `design.volume/chapter/scene.generate` はpublic runtimeではgenerate-only
- `write.draft.*` と `write.summary.*` はgenerate / review / reviseを実行
- reviewは実在する不整合だけを、下流工程への影響で判断して指摘する
- reviseはissueを反映しつつ、未指摘fieldと既存の正しい内容を壊さない

根拠のない好み、同内容の言い換え、対象に存在しない欠落はissueにしません。review上限に達しても未解決issueを持つ候補は選択されません。

## 日本語品質

各reviewは、日本語文脈で不自然な簡体字・中国語構文・英語混在・ハングル混在を確認します。ただし、自然なカタカナ語、固有名詞、一般的な英字略語、日本語として成立する漢語は問題として扱いません。

## Canonとwriter境界

scene designはnon-empty Canon patchを持ち、runtimeがauthor-facingな名前参照をstable typed referenceへ解決します。writerへ渡すのはwriter-safe contextと直近summaryであり、raw Canon frontier、event、stable ID、author-only情報は渡しません。

## 変更時の確認

```bash
uv run python scripts/validate_prompts.py
uv run pytest tests/contract -q
uv run python scripts/check_dev_quality.py
```
