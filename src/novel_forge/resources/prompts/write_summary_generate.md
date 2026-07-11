# Continuity handoff の生成

## 目的
次の writer が安全に引き継げる、POV-safe な scene summary を作る。

## 応答方針
final draft に直接書かれている事実だけを採用する。writer context は表示名・POV-safe な表現の補助に限り、draft と食い違う場合は draft を優先する。本文にない理由・真相・状態を補完しない。`evidence` には本文中の短い引用または出来事を記す。

## 実行指示
end_state、changed_threads、unresolved_threads、next_scene_handoff、evidence を具体的に出力する。

## 入力情報
### final draft（唯一の事実源）
{draft}

### writer context（表示名の補助のみ）
{writer_context}

## 出力仕様
下記のスキーマに適合する JSON のみ出力すること。

{schema}
