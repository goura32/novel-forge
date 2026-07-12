# シーン設計レビュー

## 目的
シーンの物語設計と、追加・更新を含む `canon_patch` を厳格に検査する。

## 応答方針
レビュー対象に根拠があり、改訂工程で具体的に修正できる問題に限定する。severity は後続工程への影響度で決める。軽微に見える表記・用語でも、後続工程で固定化・拡散する場合は指摘する。修正可能な差分に限定し、出版可否、総評、長所、スコアは出力しない。`issues` が空配列なら改訂不要、1件以上なら改訂を継続する。問題がない場合は、無理に指摘を作らず `issues` を空配列にする。`issues` は最大8件に限定。各 issue は `severity`、`field`、`description`、`suggestion` を含め、`description` と `suggestion` は短文にする。二重引用符を書かない。入力キーワードまたは前工程JSONに明示された期間、職業、役割、性別、タイトル、ジャンル、固有名は正として扱い、後続工程で具体化できる未定義要素だけを指摘する。日本語文脈で不自然な簡体字、中国語構文、英語混在、ハングル混在を指摘する。指摘時は問題文字列を引用する。自然なカタカナ語、英語表記、英字略語、一般的なジャンル語、固有名詞、日本語として成立する漢語は言語純度の問題にしない。自然なカタカナ語、英語表記、英字略語、一般的なジャンル語、固有名詞、日本語として成立する漢語は問題にしない。

## CanonPatch のレビュー規則
- 既存 entity 参照は「有効な Canon ID」白リストの完全一致だけを許可する。表示名・alias・推測 ID は issue にする。
- 新規 entity は `canon_patch.<section>.create` に `creation_key` を持つ payload として宣言する。final ID を推測して書かない。
- 同一 candidate 内の新規 entity を参照する唯一の表記は `@created:<creation_key>`。その key が対応する create にない、kind が違う、曖昧なら issue にする。
- 新規場所・人物・物品・知識・関係・伏線・subplot・用語が物語上必要なら、既存 ID へ無理に置換させない。create payload が不十分・既存 Canon と矛盾・連続性管理不要な過剰作成の場合だけ issue にする。
- `canon_patch` は section ごとの full CanonPatch である。旧 `canon_updates` DSL、`operation/target_id/value` の独自形式、未定義 operation を要求・提案してはならない。
- create は entity の必須属性を満たすこと。update は対応 entity kind と型付き operation を一致させること。現在値と同一の update は no-op として issue にし、その update を削除するよう提案する。
- Canon に存在しない ID を `before` / `after` に新規 final ID として書かない。必要な新規 entity は `creation_key` を示し、create payload を追加するよう提案する。

## 実行指示
### 指摘対象
{design}

### 企画
{series_plan}

### シーン種
{scene_seed}

### Canon
{canon_context}

### 有効なCanon ID（完全白リスト）
{valid_canon_ids}

「有効な Canon ID」リストに含まれる ID はすべて存在する。このリストの ID を「存在しない」と指摘したり、新規作成させたりしてはならない。Canonにある関係、伏線、世界ルール、人物、場所が候補に登場しないことだけを issue にしない。起こり得る・不自然かもしれないという可能性だけで issue にしない。Canon の world_rules / series_constraints / immutable_constraints / current_state に反する key_events、outcome、patch は issue にする。新規 entity を作る場合も、既存の能力・年代・関係・物理法則を矛盾させない。

## 出力仕様
下記のスキーマに適合する JSON のみ出力すること。

{schema}
