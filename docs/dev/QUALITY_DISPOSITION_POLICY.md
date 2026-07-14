# Quality Disposition Policy

## 適用範囲

このpolicyは**write phaseのfinal DraftAudit**に適用されます。plan / designはQualityDispositionを作りません。exportは新たにdispositionを決めず、bundleにpin済みのdispositionを再検証します。

## 分類

| final audit issue | 結果 |
|---|---|
| `severity == blocker` | non-waivable。停止 |
| `constraint_kind != quality` | non-waivable。停止 |
| `constraint_kind == quality` かつseverityがmajor/minor | 最大1回polish後、残ればdeferred候補 |

## Disposition

| status | 要件 |
|---|---|
| `clean` | issueがゼロ |
| `deferred` | 全residualがquality major/minorであり、assessment artifact ID、issue index、severity、kind、field、quote、detailがauditと完全一致 |

writeはnon-waivable findingが残る場合、DesignBundleを作りません。`deferred`はhuman narrative waiverではありません。構造、provenance、Canon、frontier、schema、required beat、end constraintを免除しません。

## Export defense in depth

exportはbundle slotのcontract、WriterView、draft、DraftAudit、QualityDisposition、frontierを検証します。さらにfinal auditとdispositionを再照合し、次を拒否します。

- hard / non-quality finding
- issueを持つ`clean`
- auditに対応しない、またはauditを取りこぼす`deferred`
- dispositionのsubject / review / input provenance不一致
