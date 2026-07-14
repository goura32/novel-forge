# 2026-07-14 PNCA運用監査と是正記録

## 対象

2026-07-14 07:30 以降に加えられた PNCA writer、LLM client、prompt/schema と運用コマンドの変更を、現在の immutable runtime / PNCA contract の仕様に照らして再監査した記録です。

## 正しい不変条件

1. LLMの返答は入力ではなく候補である。未検証の値を runtime が推測・補完してはならない。
2. evidence は LLM 呼出し前から attempt に紐付き、成功・失敗とも後から読める。
3. render は obligation coverage を唯一生成する工程であり、revision は coverage を自己申告しない。
4. revision 後の本文も、render から継承した quotation evidence と照合して初めて publish候補になる。
5. CLI は一工程・一snapshot を単位にし、合成コマンドで provenance を混ぜない。

## 発見した不適切な対応と是正

| 旧対応 | なぜ不適切か | 是正 |
|---|---|---|
| null `beat_index` を evidence 配列の位置から補完 | 並び順は obligation の証拠ではない。誤った index が通ると coverage検証が無意味になる | 補完を削除。Pydantic validation failure として停止・記録する |
| null `draft_quote` を空文字にする | 空文字は任意の本文に含まれるため、引用証拠を偽造する | 補完を削除。verbatim quote が必須 |
| field-schema echo を空文字へcoerce | LLMの schema辞書を正常な空本文・空reviewに偽装し、下流の品質低下を招く | `SchemaEchoError` として停止し `validation.json` に `SCHEMA_ECHO` を残す |
| reviseで旧coverageを無条件継承 | 改訂で quotation が消えても、旧draftの証拠が残る | 改訂本文に対して inherited coverage の全 quote を再照合する |
| `AttemptCapture` があるだけで本番呼出しへ未接続 | RAW出力「常時保存」という文書と実態が不一致。障害時の根拠を失う | provider呼出し前に evidence attempt を作り、request/response/parse/validation/終端状態を保存する |
| `complete` 合成CLI | run・lock・snapshotの境界が曖昧で、失敗工程だけの監査／再実行ができない | CLIから削除。個別の plan/design/write/export を標準にする |
| malformed audit issue をschema検証前にdrop | blockerを含む evidence が「問題なし」へ変わり、監査根拠が失われる | 配列・issueの破損を補正しない。元payloadのままschema validation failureにする |
| 2回改訂後も残る blocker をbundle化 | hard contract failure をexportへ通す | 未解決 blocker は `RuntimeContractError` で停止しbundle snapshotを作らない |
| evidence-only attempt の `completion.json` を終端扱いしない | 完了後にartifact追加・failure化でき、attempt不変性が壊れる | completionもterminal markerとして全write経路で拒否する |
| capture非対応clientの検査がattempt作成後 | terminal recordのない孤児attemptが残る | capabilityを作成前に検査し、capture setup失敗は `error.json` で終端化する |

## あえて採用しなかった対応

### 簡体字のコード側ブラックリスト

`监护人` のような文字列を個別にrejectするのは、言語品質を網羅できず、保守対象を無限に増やします。本文が日本語であることは prompt の具体的な制約と review / revision の品質責務で扱います。Unicode blockだけで日本語漢字と簡体字を確実に区別することはできません。

### LLM client内部での隠れたschema-echo再試行

同一 attempt 内で複数 provider request を行うと、どの request が最終応答を生んだかが曖昧になり、固定名のRAWファイルを上書きし得ます。1 evidence attempt = 1 provider request を守り、再試行が必要なら orchestration が新しい attempt を明示的に作成します。

## 既存runへの影響

過去のrun artifactは不変であり書き換えません。以前の直接 `manuscript.md` 編集は provenance を損なう操作で、今後の修正方法として採用しません。再生成が必要な場合は新しい run / attempt を作り、選択snapshotから正規経路で export します。

## 追跡項目

- quality retry policy は evidence attempt を増やす orchestration の責務として別途実装する。LLM client内の隠れた再試行は追加しない。
- 日本語本文の品質はブラックリストでなく、render/revise/review prompt と人間による artifact review で評価する。
