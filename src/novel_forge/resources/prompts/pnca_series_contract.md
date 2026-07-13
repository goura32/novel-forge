# PNCA シリーズ契約提案の生成

## 目的

入力 request artifact だけを根拠に、後続の Volume / Chapter / Scene が参照する初期 Canon seed を含む Series Contract proposal を作る。

## 応答方針

物語の開始状態、固有名、世界の制約を具体的かつ一貫して設計する。request にない章構成、scene 展開、将来の Canon event は書かない。

## 実行指示

- `contract_id` は最終 series slug として `[a-z0-9_]{1,40}` に完全一致する、request 内の既存 slug と重複しない stable ID を設計する。英字は ASCII 小文字 `a`〜`z` のみを使用し、アクセント記号・ダイアクリティカルマーク・日本語・ハイフン・空白を一文字も含めない。たとえば英語の借用語も `fiance` のように ASCII 化し、`fiancé` のような Unicode 文字は使わない。
- `canon_seed` は series ID、title、logline、初期 entity と state を含む JSON object にする。request の物語的キーワードは、単に title に残すのでなく、呪い・鍵となる artifact・政治的対立・関係性のそれぞれを seed の具体的な設定に反映する。固有名詞は自然な日本語表記（漢字・ひらがな・カタカナ）だけを使い、ラテン文字・簡体字・文字種を混ぜた名前を作らない。
- `final_resolution` は最終巻で解決すべき呪い、鍵となる artifact、宮廷対立、二人の関係の到達状態を、request の具体語を用いて一文で固定する。初対面・契約締結・関係の萌芽ではなく、解決後の幸福な状態まで書く。
- `volume_purposes` は各巻につき一つの短い目的を `ordinal` の昇順で列挙する。シリーズ全体の進行上その巻が果たす役割だけを書き、chapter、scene、具体的な beat、Canon patch は書かない。
- 不自然な英語、簡体字、ハングルを混在させず、自然な日本語で書く。
- 空の object や未定義の仮名を出力しない。

## 入力情報

### request

{request}

## 出力仕様

下記のスキーマに適合する JSON のみ出力すること。

{schema}
