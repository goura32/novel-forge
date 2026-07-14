# PNCA シリーズ契約提案の生成

## 目的

入力requestだけを根拠に、後続のVolume / Chapter / Sceneが最初から二人の主役を個人として参照できる初期Canon seedを含むSeries Contract proposalを作る。

## 応答方針

物語の開始状態、固有名、二人の関係、世界の制約を具体的かつ一貫して設計する。requestにない章構成、scene展開、将来のCanon eventは書かない。

## 実行指示

- `contract_id`は最終series slugとして`[a-z0-9_]{1,40}`に完全一致し、request内のexisting_slugsと重複しないstable IDを設計する。英字はASCII小文字`a`〜`z`のみを使用し、アクセント記号・ダイアクリティカルマーク・日本語・ハイフン・空白を一文字も含めない。
- `canon_seed.protagonists`には、最初のsceneから登場・会話・内面描写できる主役を**ちょうど二人**入れる。各人に異なる`character_id`、自然な日本語の固有名、社会的role、開始時の制約または目的、書き分け可能なvoiceを与える。「主人公」「王子」「彼女」のような役名だけをnameにしてはならない。
- `canon_seed.relationship`は、上記二人の`character_id`だけをparticipant_idsに入れる。政略結婚・偽の婚約・身分差など開始時の力関係と、互いに隠していることをinitial_stateへ具体的に書く。
- `canon_seed.world_state`には、requestの呪い・鍵となるartifact・宮廷対立を、後続sceneで不変の制約として参照できる具体的なkey/valueで入れる。
- requestの物語的キーワードはtitleだけに残さず、二人のinitial_state / relationship / world_stateへそれぞれ具体的に反映する。固有名詞は自然な日本語表記（漢字・ひらがな・カタカナ）だけを使い、ラテン文字・簡体字・文字種を混ぜた名前を作らない。
- `final_resolution`は最終巻で解決すべき呪い、鍵となるartifact、宮廷対立、二人の関係の到達状態を、requestの具体語を用いて一文で固定する。初対面・契約締結・関係の萌芽ではなく、解決後の幸福な状態まで書く。
- requestに`volume_count`がある場合、`volume_purposes`はordinal 1から`volume_count`まで連番で**ちょうどその件数**にする。指定件数より少なくして結末を省略したり、多くして最終解決を後ろへ先送りしてはならない。
- `volume_purposes`は各巻につき一つの短い目的をordinalの昇順で列挙する。シリーズ全体の進行上その巻が果たす役割だけを書き、chapter、scene、具体的なbeat、Canon patchは書かない。
- 不自然な英語、簡体字、ハングルを混在させず、自然な日本語で書く。

## 入力情報

### request

{request}

## 出力仕様

下記のスキーマに適合する JSON のみ出力すること。

{schema}
