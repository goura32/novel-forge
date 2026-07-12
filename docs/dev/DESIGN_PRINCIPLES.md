# 設計原則：LLM出力の機械処理を最小に保つ

最終更新: 2026-07-12

この文書は novel-forge 全体（plan / design / write のすべての stage、generate / review / revise のすべての task）に適用する設計原則です。特定の工程（例: review）に限らず、LLM と runtime の境界で一貫して守るべきルールを定めます。

## 1. LLM出力は確率的である

同じ入力でも出力は毎回異なる。schema 違反や表現の揺れは起きうる前提で設計する。

## 2. 機械処理が必要な項目は ID/enum で選択肢を与える

runtime が後で機械的に照合・分岐・集計したい項目は、LLM に自由文で書かせるのではなく、次のいずれかで返させる:

- 既存の安定 ID（Canon entity ID、scene ID など）をそのまま返す
- `enum` で許可値を閉じた文字列を返す（例: `severity` を厳密な enum にする場合）
- 正規表現で機械照合できる形式（例: `slug` は `[a-z0-9_]+`）にする

この原則に従い、Canon 更新は「許可された Canon ID を直接返す ID-only DSL」とし、runtime が strict にコンパイル・検証する。これは本システムの模范的実装である。

## 3. それ以外の項目は機械処理しない

機械的に照合・置換・判定する必要がない項目（本文、説明、提案、レビュー指摘など）は:

- 次工程への入力としてそのまま渡す（revise は review 全体を `{review}` として LLM 入力に渡すだけ）
- または人間向けの出力として扱う

**やってはいけないこと**:

- 部分一致・あいまい一致・最寄り一致（fuzzy matching）による判定
- 生成テキストからの中途半端な抽出・編集・置換
- LLM 出力の文字列を runtime が書き換えて「正しい形」に矯正すること
- 「LLM が指示通りに返さなかった」ことをコード側の後処理で補う複雑な仕組み

## 4. LLMが指示通りに返さないことを許容する

プロンプト指示の逸脱（表現の揺れ、任意フィールドの省略/過剰、severity の表記揺れなど）は、ある程度許容する。schema で棄却されるものは `quality.max_retry_count` の範囲で再実行すればよく、runtime が個別に「直してやる」後処理を入れてはならない。

## 5. 複雑な仕組みは追加せず、プロンプト・スキーマで対応する

「LLM が X を守らない」と気づいたとき、コードで X を矯正する機構を足すのではなく、次の順で対応する:

1. プロンプトで X をより明確に指示する（具体例、禁止事項の明示）
2. JSON Schema で強制する（`additionalProperties: false`、必須キー、`enum`、`maxItems`、`pattern` など）
3. それでも不安定なら、スキーマ自体を単純化する、または入力へ渡す schema 表現を調整する

ただし `additionalProperties: false` は採用しない。後述の contract test（`test_schemas_avoid_strict_unknown_field_rejection`）が「local LLM は無害な余計なフィールドを出しがち」として棄却を禁じているため、余計なトップレベルフィールドは schema で弾くのではなく、プロンプト指示（`出版可否、総評、長所、スコアは書かない`）と retry で許容する。同様に `severity` は任意文字列（enum 化しない）、`issues` の切り詰めは `maxItems` ではなくプロンプトの「最大8件」指示で許容する。

## 禁止・許容の境界例

| 処理 | 扱い | 根拠 |
|---|---|---|
| `slug` の `[a-z0-9_]` 正規化 | 許容 | ID/enum 項目（§2）。正規表現で機械照合する形式をプロンプトで指示済み |
| Canon ID-only DSL の strict コンパイル | 許容 | ID 選択肢方式（§2）。模范的実装 |
| JSON 構文の修復（未エスケープ引用符、未引用値、閉じ括弧欠落） | 許容 | 「JSON を返させる」ための構文解析。部分一致・置換・曖昧一致ではない |
| review `before/after` の本文完全一致判定 | 禁止 | 部分一致・機械置換（§3）。任意の補足として扱う |
| review から `overall_assessment` 等を pop して捨てる | 禁止 | 「指示通りでないことをコードで矯正」(§3, §4)。`additionalProperties:false` は採用せず、プロンプト指示＋retryで許容 |
| review `issues` を `[:8]` で切り詰め | 禁止 | 中途半端な編集（§3）。`maxItems:8` は schema で強制せず、プロンプトの「最大8件」指示で許容 |
| `severity` の `.strip()` | 禁止 | 文字列の機械清掃（§3）。任意文字列として許容 |

## 関連文書

- [LLM_REVIEW_CONTRACT](LLM_REVIEW_CONTRACT.md): generation / review / revise の境界と retry 契約
- [PROMPTS](PROMPTS.md): プロンプト改善方針
- [schema_maintenance](schema_maintenance.md): JSON Schema の変更と検証
