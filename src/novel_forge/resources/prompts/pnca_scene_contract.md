# PNCA Scene Contract Proposal の生成

## 目的

入力 Chapter Contract、Canon frontier/projection、scene request のみから、指定 slot の実行可能な proposal を返す。

## 応答方針

入力で固定された ChapterPlan と slot mandate を変更せず、本文 writer へ余分な Canon authority を渡さない。

## 実行指示
 `scene.request.slot_mandate` は Chapter が不変に割り当てた責務である。`start_state` から `required_transition` を経て `end_state` に到達し、`relationship_contribution` を果たし、`prohibited_repetition` を繰り返さない。
- 全 scene は `canon_effect: "mutates"` と、単一の typed `canon_patch` を返す。patch は `entity_id`、`state_key`、`prior_value`、`new_value`、`cause_beat_index`、`observable_consequence` を全て持つ。`cause_beat_index` はゼロ始まりで `required_beats` の既存要素を必ず指す。
- `writer_view` は唯一の本文入力であり、Canon、artifact ID、summary を含めない。`start_context` は `pov`、`location`、`observable_start_state`、`narrative_contract` は `goal`、`progression`、`obstacle`、`remaining_uncertainty`、`end_constraints` は `pov`、`final_state`、`presentation_constraints` は `pov`、`tone` を必ず持つ。三つの `pov` は一致する。
- `required_beats` は文字列でなく `{"description": "..."}` の構造化配列にする。各 beat は POV が観測でき、最後の beat は final_state を実現する。
- `writer_view` は object であり、`narrative_contract` は object である。各 field を単一の文字列にしてはならない。`安抚` は書かず、「慰める」「安心させる」と書く。
- `### Admission allowances` が空配列 `[]` の場合、過去巻・別slot・入力にない allowance IDを推測してはならない。
- terminal scene 以外は series final resolution を writer_view に含めず先取りしない。terminal scene だけは request の終端責務を最後の beat/final_state で可観測に解決する。
- admission は入力 allowance と当該 slot の許可だけを使い、未承認 entity を作らない。

## 入力情報

### Chapter Contract
{parent}

### Canon frontier
{frontier}

### Canon projection
{canon_projection}

### Admission allowances
{admission_allowances}

### Scene request
{request}

## 出力仕様

下記のスキーマに適合する JSON のみ出力すること。

{schema}
