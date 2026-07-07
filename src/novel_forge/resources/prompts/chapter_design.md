# 章設計の生成

## 目的

指定された章について、テーマ、感情の弧、結果、シーン構成を生成する。巻設計で与えられた章の役割を守り、後続のシーン設計に渡せる詳細な章設計を作る。

## 応答方針

章設計を担当する小説家として、章単体の読み応えと巻全体の流れを両立する。入力された章の役割は変更せず、シーンごとの因果と読者の感情変化を明確にする。

## 実行指示

- `purpose` フィールドには、入力の章の役割 `{chapter_purpose}` を1文字も変えずに出力する。
- `purpose` を「状況提示」「導入シーン」「冒頭」など別語へ言い換えない。
- 前章の結果から自然につながり、章の結果が次章へ接続できるようにする。
- 前巻の主要な結果がある場合は、関係性・伏線・状況の継続を反映する。
- シーン構成は章の目的を達成する順序にし、各シーンの設定・目標・葛藤・結果を具体化する。
- 各フィールドはスキーマの型・長さの制約を満たす具体的な日本語で書く。
- `theme` は章で扱う主題、`emotional_arc` は章全体の感情変化、`outcome` は章末で確定する状態を書く。
- `chapter_turning_point` は章全体の不可逆な転換点、`chapter_hook` は次章へ進ませる引きを書く。
- `foreshadowing_notes` と `subplot_notes` は空にせず、本文で使える具体的な伏線・副筋メモを1件以上入れる。
- `scenes[]` の各要素には `title`, `pov`, `goal`, `conflict`, `outcome`, `characters`, `key_events`, `setting` をすべて具体的に埋める。

## 入力情報

### シリーズ企画

{series_plan}

### 巻番号

{volume_number}

### 巻タイトル

{volume_title}

### 巻の前提

{volume_premise}

### 章番号

{chapter_number}

### 章タイトル

{chapter_title}

### 章の役割

{chapter_purpose}

### 前章の結果

{previous_chapter_outcome}

### 前巻の主要な結果

{previous_volume_summary}

## 出力仕様

下記のスキーマに適合する JSON のみ出力すること。

{schema}
