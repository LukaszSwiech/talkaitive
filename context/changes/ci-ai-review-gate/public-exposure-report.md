# Public exposure report: ci-ai-review-gate

- **Date:** 2026-11-01
- **Tool:** gitleaks 8.30.1 (Homebrew formula)
- **Command:** `gitleaks git --log-opts="--all" --redact --report-format json --report-path <scratch>/gitleaks.json`
- **Commits scanned:** 167 of 183 on all local refs (18 refs). The 16 not scanned have no added lines to inspect: 15 merge commits and 1 delete-only commit (`3d97f46`).
- **Findings:** 9, all `generic-api-key`. Real secrets: 0.
- **`.env` ever committed:** No. `git log --all --oneline -- .env` returns nothing.

Values were never printed. Triage used code context with string values masked to length and character classes, plus hash and count comparisons.

| Rule | File | Line | Short SHA | Verdict | Why |
| --- | --- | --- | --- | --- | --- |
| generic-api-key | context/foundation/test-plan.md | 193 | 834e476 | False positive | Polish prose quoting a `name=VALUE` code expression; no digits, and both parts occur in the project's Python code (10 and 8 files). |
| generic-api-key | tests/test_account_deletion.py | 14 | a58a433 | False positive | Test constant `PASSWORD`, used for test users. |
| generic-api-key | tests/test_login.py | 7 | 1c466da | False positive | Test constant `PASSWORD`, same value as the other test findings. |
| generic-api-key | tests/test_accounts.py | 14 | f7fd2e5 | False positive | Password of a superuser created inside the test, same value. |
| generic-api-key | tests/test_accounts.py | 46 | f7fd2e5 | False positive | Env var set through `monkeypatch` for the `createsuperuser` test, same value. |
| generic-api-key | tests/test_accounts.py | 63 | f7fd2e5 | False positive | Password field in a test signup form, same value. |
| generic-api-key | tests/test_accounts.py | 64 | f7fd2e5 | False positive | Password confirmation field in a test signup form, same value. |
| generic-api-key | tests/test_accounts.py | 81 | f7fd2e5 | False positive | Password field in a test signup form, same value. |
| generic-api-key | tests/test_accounts.py | 82 | f7fd2e5 | False positive | Password confirmation field in a test signup form, same value. |

## Conclusion

No real secret was found in the scanned history, and `.env` was never committed. No rotation or history rewrite is indicated by this scan.

Limits:

- gitleaks detects by pattern and entropy, so a clean result is strong evidence, not proof.
- The scan covers refs in this local clone. Commits that exist only on GitHub and were never fetched are not included.
- Untracked files are not in git history and were not scanned.
- The test password is treated as a dummy because of how it is used. This assumes it is not reused for a real account, which the scan cannot check.
