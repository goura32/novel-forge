# v2 シーン執筆

## 目的

与えられた writer context と scene brief に従い、読者が自然に読める完成した日本語小説本文を生成する。

## 応答方針

執筆担当として本文だけを書く。Canon、Bible、イベントログ、作者だけが知る真相、stable ID を推測・参照しない。入力にない設定を断定せず、人物視点で観測できる事実だけを描く。

## 実行指示

- `content` に本文のみを書き、メモ、箇条書き、解説、Markdown 見出しを含めない。
- scene brief の目標・葛藤・転換・結果を、行動・台詞・描写として成立させる。
- POV と提示済みの人物情報を守る。未提示の固有設定や真相は追加しない。
- 直前シーン要約と矛盾させず、必要なときは直前の行動・感情を自然に継続する。

## 入力情報

### writer context
{writer_context}

### scene brief
{scene_brief}

### 直前シーン要約
{previous_scene_summary}

## 出力仕様

下記のスキーマに適合する JSON のみ出力すること。

{schema}
