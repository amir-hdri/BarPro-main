# Publication candidate secret review — 2026-10-07

**No production credential was identified among the 68 scanner matches in 26 changed/new files reviewed for this publication. No changed-file candidate remains unresolved.** This is a scoped candidate review, not a claim that the entire repository or its history is free of secrets.

Input: `/tmp/barpro-resume-20261007/secrets-scan.json`, produced with `detect-secrets --no-verify`: 163 matches total. The remaining 95 matches are in unchanged baseline files and were not fully revalidated in this quick publication check. No credential validity checks or production access were performed.

## Dispositions and evidence

- **8 CI configuration matches:** `.github/workflows/ci-cd.yml` and `ci-test.yml`. JWT fields are explicitly labeled test credentials. PostgreSQL credentials configure the ephemeral test service and matching localhost test-database connection. The high-entropy Fernet value already exists in both workflows at HEAD; their adjacent comments label these deterministic non-production CI credentials. This same fixture value is used in the reproduction scripts, and an equality-only comparison found no match in local `.env` or `.env.example` key fields. Values are omitted from this report.
- **16 reproduction-script matches:** `frontend-contract-probes.py`, `otp-reproductions.py`, `reporting-reproductions.py`, `shipping-reproductions.py`, `security-reproductions.py`, and the two preserved copies of the latter under `security-baseline/artifacts/02_discovery/validation_artifacts/`. AST/source review shows synthetic test/audit credentials, test mode, local SQLite/Redis, `ALLOW_LIVE_SUBMIT=false`, and mocked or ASGI-local boundaries. The random-looking encryption value is the existing CI fixture described above. The three security reproduction copies carry the same fixture. These are test configuration examples, not discovered production credentials.
- **16 audit provenance matches:** three filesystem paths and one Git revision in `frontend-clean-environment.json`; three Git revisions in `repository-snapshot.json`; nine artifact-digest/revision matches in `security-baseline/scan-manifest.json`. All four inspected environment/repository revision values resolve to local Git commits. Recomputed SHA-256 values match all four manifest-listed final artifact files. The filesystem paths are local provenance and do not contain authentication tokens.
- **28 test matches:** 26 synthetic fixture passwords/encrypted-value placeholders used in local fixtures or mocked service calls; one digit-normalization sample in `tests/test_otp_forwarder.py:13`; one deterministic mobile protocol-header test vector in `tests/test_security_audit_gates.py:215`. Enclosing test functions and call boundaries were reviewed, including OTP, tenant isolation, dispatch, shipping and historical reporting fixtures. The protocol-vector test supplies a mocked HTTP client; the flagged value is its expected deterministic assertion output.

## Publication boundary

No repository files were modified by this review. The existing app code, sealed historical evidence, and test fixture values were left intact. AGENTS/reference/Gemini material is excluded from the parent's staging plan and was not added to this review's publication scope.

The defensible statement for the final report is: “Reviewed all 68 secret-scanner matches in changed/new flagged files: synthetic CI/test/reproduction data and non-secret provenance/test vectors; no production credential identified in that scope.” Do not report “163 confirmed false positives” or claim a complete historical/production secrets audit.

Machine-readable dispositions, without candidate values: `/tmp/barpro-resume-20261007-secret-review.json`.
