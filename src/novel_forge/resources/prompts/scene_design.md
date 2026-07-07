# シーン設計

## 目的

指定されたシーンについて、目標、葛藤、結果、POV、舞台、キーイベントを詳細化する。章設計と前後の文脈に接続し、本文執筆でそのまま使えるシーン設計を作る。

## 応答方針

シーン設計を担当する小説家として、単なる説明ではなく、行動・対立・変化が明確な場面を設計する。章全体のテーマと感情の弧を、シーン単位の具体的な出来事へ落とし込む。

## 実行指示

- シーン種の素材と矛盾しないよう、goal、conflict、outcome、characters、key_events、setting を詳細化する。
- 前シーンの結果から自然につながる開始状況にする。
- 前巻の主要な結果がある場合は、設定・関係性・伏線の継続を反映する。
- POV人物を明確にし、本文執筆時に視点がぶれない設計にする。
- 冒頭フック、転換点、終わりの引きが分かるようにする。
- 感覚、サブテキスト、伏線が章のテーマと噛み合うようにする。
- `hook` は冒頭1〜2文で使える具体的な引き、`turning_point` は場面中の不可逆な変化、`ending_hook` は次シーンへの引きを書く。
- `pov` は視点人物名のみを明確に書き、`characters` には実際に登場・影響する人物だけを入れる。
- `key_events` は本文で順番に描ける行動・発見・対立を具体的に入れる。

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

### 章のテーマ

{chapter_theme}

### 章の感情の弧

{chapter_emotional_arc}

### 章の伏線メモ

{chapter_foreshadowing_notes}

### 章のサブプロットメモ

{chapter_subplot_notes}

### シーン番号

{scene_number}（全{scene_count}シーン中）

### 章内位置

{chapter_scene_number}/{chapter_scene_count}

### シーン種

{scene_seed}

### 前シーンの結果

{previous_outcome}

### 前巻の主要な結果

{previous_volume_summary}

## 出力仕様

下記のスキーマに適合する JSON のみ出力すること。

{schema}
