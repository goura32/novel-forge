# Continuity handoff の生成

## 目的
次の writer が安全に引き継げる、POV-safe な scene summary を作る。

## 応答方針
final draft に直接書かれている事実だけを採用する。writer context は表示名・POV-safe な表現の補助に限り、draft と食い違う場合は draft を優先する。本文にない理由・真相・状態を補完しない。`evidence` には本文中の短い引用または出来事を記す。

## 実行指示
以下の全フィールドをスキーマ通りの正確な構造で出力する。

- `summary`: **文字列（プレーンテキスト）**。オブジェクト（`{"description": "..."}` 等）は禁止。scene の因果・転換・結果を本文の事実だけで連続した日本語として1つの文字列にまとめる。
- `end_state`: **オブジェクト**。必ず `pov`（文字列）と `setting`（文字列）の2キーを含める。`pov` = 本文から確認できる POV 人物の位置・状態・当面の目的。`setting` = 本文に根拠がある終了地点と時間的状況。
- `character_changes`: **配列**。各要素は `character`（文字列）、`change`（文字列）、`evidence`（文字列）の3キーを持つオブジェクト。本文で確認できる人物の状態または関係の変化。
- `world_or_item_changes`: **配列**。各要素は `subject`（文字列）、`change`（文字列）、`evidence`（文字列）の3キーを持つオブジェクト。本文で確認できる場所・物品・制度・環境の変化。
- `unresolved_threads`: **配列**。各要素は `thread`（文字列）、`why_it_matters`（文字列）、`evidence`（文字列）の3キーを持つオブジェクト。本文で未解決として残る問い・約束・危機・制約。
- `next_scene_handoff`: **文字列の配列**。次の writer が守る本文根拠のある状態・制約・直後の課題。
- `facts`: **配列**。各要素は `subject`（文字列）、`predicate`（文字列）、`object`（文字列）、`evidence`（文字列）の4キーを持つオブジェクト。本文に直接根拠を持つ一つの事実（`object` がない場合は空文字）。

## 入力情報
### final draft（唯一の事実源）
{draft}

### writer context（表示名の補助のみ）
{writer_context}

## 出力仕様
下記のスキーマに適合する JSON のみ出力すること。

{schema}
