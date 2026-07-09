# プロンプト管理

## 正本と責務

runtime が使用する prompt は `src/novel_forge/resources/prompts/` にあります。prompt、Schema、Python 呼び出しの対応は [PROMPT_SCHEMA_MAP](PROMPT_SCHEMA_MAP.md) を正とします。

| 層 | 責務 |
|---|---|
| Prompt (`.md`) | 各 field に何を書くか、品質基準、工程の責務、出力上の注意 |
| JSON Schema (`.json`) | 型、必要 field、有限 enum、機械検証可能な構造 |
| Review prompt | 対象 artifact と入力根拠に基づく issue の抽出 |
| Revision prompt | issue の反映と未指摘 field の保全 |
| Python validator | Schema だけでは表せない意味的整合性 |

`{schema}` は `PromptManager.render()` が自動展開します。呼び出し側は `schema` という template variable を渡しません。

## 生成・レビュー・改稿

各 artifact は、生成・レビュー・改稿を別 prompt として扱います。改善の優先順位は次のとおりです。

1. **生成**: 後工程で使える、根拠ある自然な日本語の artifact を最初から出す。
2. **レビュー**: 実在する不整合だけを、下流工程への影響で判断して指摘する。
3. **改稿**: 指摘を反映しつつ、未指摘 field と既存の正しい内容を壊さない。

根拠のない好み、同じ内容を言い換えただけの提案、対象に存在しない欠落の指摘は issue にしません。

## 日本語品質

各 review は、日本語文脈で不自然な簡体字・中国語構文・英語混在・ハングル混在を確認します。ただし、自然なカタカナ語、固有名詞、一般的な英字略語、日本語として成立する漢語は問題として扱いません。

## Series Bible v2 と writer 境界

現在の runtime は v1 Bible prompt context を使用します。一方、v2 実装後は raw Bible、Canon Event、stable ID、author-only secret を writer に渡しません。writer は `scene_design.writer_context` と直近 summary だけを受け取り、秘密の全文ではなく spoiler-free な guardrail だけを使います。

この将来契約の唯一の正本は [SERIES_BIBLE_SCHEMA_REDESIGN](dev/SERIES_BIBLE_SCHEMA_REDESIGN.md) です。v2 実装前に、現行 prompt の動作を v2 前提へ誤って書き換えないでください。

## 変更時の確認

```bash
uv run python scripts/validate_prompts.py
uv run pytest tests/contract -q
uv run python scripts/check_dev_quality.py
```
