# PNCA シリーズ契約提案の生成

## 目的

入力 request artifact だけを根拠に、後続の Volume / Chapter / Scene が参照する初期 Canon seed を含む Series Contract proposal を作る。

## 応答方針

物語の開始状態、固有名、世界の制約を具体的かつ一貫して設計する。request にない章構成、scene 展開、将来の Canon event は書かない。

## 実行指示

- `contract_id` は最終 series slug として `[a-z0-9_]{1,40}` に完全一致する、request 内の既存 slug と重複しない stable ID を設計する。
- `canon_seed` は series ID、title、logline、初期 entity と state を含む JSON object にする。
- 不自然な英語、簡体字、ハングルを混在させず、自然な日本語で書く。
- 空の object や未定義の仮名を出力しない。

## 入力情報

### request

{request}

## 出力仕様

下記のスキーマに適合する JSON のみ出力すること。

{schema}
