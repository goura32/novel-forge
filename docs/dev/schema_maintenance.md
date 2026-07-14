# Schema 保守

## 変更単位

PNCA schemaを変えるときは、次を一つの変更として扱います。

1. `src/novel_forge/resources/schemas/<schema>.json`
2. 対応prompt `src/novel_forge/resources/prompts/<prompt>.md`
3. `pnca/defaults.py` のtask registry
4. `pnca/production.py` のprompt variable projection
5. Pydantic contract / validation / workflow
6. task registry、production、contract、writer、exportの回帰テスト

## 原則

- output schemaはstrict contractとして扱う。未宣言fieldや必須field欠落をruntimeが推測・補完しない。
- promptに`{schema}`を渡すことはproduction adapterの明示責務である。
- schema mismatchは`quality.max_generation_attempts`まで別attemptで再生成する。初回を含む。
- retryで救えない構造不整合、provenance不整合、Canon / frontier violationをdeferredにしない。

## 検証

```bash
uv run pytest -q tests/test_pnca_contracts.py tests/test_pnca_production.py tests/test_pnca_export.py
uv run python scripts/check_dev_quality.py
```

schemaだけ、promptだけ、adapterだけを単独で変更してはいけません。
