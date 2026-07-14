# 現行設計原則

## Immutable provenance

run、attempt、artifact、selection snapshot、acceptanceをappend-onlyに扱う。失敗の回復に既存artifactを手編集せず、新しいrun / attemptを作る。

## Strict contracts

schema、stable ID、typed reference、digest、FrontierBinding、acceptance inputはfail-closedで検証する。runtimeはLLM outputの意味を推測して補完しない。

## Bounded generation and revision

JSON/schema contract failureは`quality.max_generation_attempts`まで再生成する。初回を含む。hard blocker repairは最大2回、editorial quality polishは最大1回である。transport failureは自動retryしない。

## Phase responsibility

- authoringはtyped contractを作る。
- auditはdraft evidenceに根ざしたissueを出す。
- revisionは指摘されたissueを直し、保護coverageを壊さない。
- dispositionはruntimeがfinal auditを分類する。
- exportはfrozen bundleのprovenanceとaudit / dispositionを再検証する。

## Editorial debtの限界

`deferred`はquality major/minorだけに限る。schema、Canon、frontier、provenance、required beat、end constraint、POV factなどのhard constraintを免除しない。
