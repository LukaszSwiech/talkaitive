<!-- IMPL-REVIEW-REPORT -->
# Implementation Review: AI code review agent in GitHub Actions

- **Plan**: context/changes/ci-ai-code-review/plan.md
- **Scope**: Phases 1-3 of 4 (Phase 4 is the real run and has not started)
- **Reviewed phases**: 1, 2, 3
- **Date**: 2026-10-31
- **Verdict**: APPROVED, after fixing F1 and F2 (NEEDS ATTENTION before them)
- **Findings**: 0 critical, 2 warnings (both fixed), 5 observations

## Verdicts

| Dimension | Verdict |
|-----------|---------|
| Plan Adherence | PASS |
| Scope Discipline | PASS |
| Safety & Quality | PASS (WARNING before the fixes) |
| Architecture | PASS |
| Pattern Consistency | PASS |
| Success Criteria | PASS |

Phase 4 rows in Progress are legitimately pending. Phases 1-3 hold no Manual rows.

## Findings

### F1 — Character references get around the mention and HTML sanitising

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Safety & Quality
- **Location**: scripts/review/run_review.py, `sanitize`
- **Detail**: `sanitize` only looked at the literal `@`, `![` and `<`. GitHub's own renderer (`POST /markdown`, `mode=gfm`, which publishes nothing) returned a real `<a class="user-mention">` for `&#64;octocat`, `&#x40;octocat` and `&commat;octocat`, so a prompt-injected model could still produce a mention. `&lt;img&gt;` and `&#60;img&#62;` render as text only, and `&#33;[x](url)` as a plain link, so HTML and images were not affected. Whether a rendered mention also sends a notification was not tested, because that needs a real comment.
- **Fix**: Replace `&` with `&amp;` before everything else. Confirmed on the same renderer: `&amp;#64;octocat` is plain text.
- **Decision**: FIXED

### F2 — The comment cap could cut off the scope note

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Safety & Quality
- **Location**: scripts/review/run_review.py, `render_comment`, `_scope_note`
- **Detail**: The scope and floor notes sat after the model's text, so the 60k cut removed them first, and an unclosed code fence in the summary would have swallowed them without any cut. The note itself was unbounded too: 20 dropped paths of 4,000 characters gave 76,285 characters, and 320,241 after sanitising.
- **Fix**: The fixed notes now come before the model's text, and each shown path is limited to `MAX_PATH_CHARS_SHOWN = 200`. The plan names the comment's parts without fixing an order, so this does not contradict it.
- **Decision**: FIXED

### F3 — `<` and `&` show as entities inside code spans

- **Severity**: OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Safety & Quality
- **Location**: scripts/review/run_review.py, `sanitize`
- **Detail**: Entities are not decoded in code, so `` `<style>` `` displays as `&lt;style>`, as the plan's `<` rule already implied. The `ui_contract` criterion makes this text likely. It is safe, only less readable. The zero-width character in a code span is invisible and harmless (rendered and checked).
- **Fix**: None now. Telling code from prose would need a Markdown parser, which is a new dependency.
- **Decision**: LEFT, cosmetic

### F4 — Links and issue references stay active

- **Severity**: OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Safety & Quality
- **Location**: scripts/review/run_review.py, `sanitize`
- **Detail**: `[text](http://...)` stays as the plan decided. Rendered: `rel="nofollow"` is added and `javascript:` URLs are stripped, so what remains is a phishing-style link a reader must click. `owner/repo#1` also becomes an issue link. The repo is private; whether such a link leaves a back-reference on a public target was not tested.
- **Fix**: None. Changing this would widen the plan's stated scope.
- **Decision**: LEFT, plan decision

### F5 — A PR's `.gitattributes` can hide a file's content from the review

- **Severity**: OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Safety & Quality
- **Location**: scripts/review/run_review.py, `read_diff`
- **Detail**: Observed in a throwaway repo: with `*.py -diff` added by the PR, `h.py` shows as `Binary files /dev/null and b/h.py differ`. The `.gitattributes` line itself stays visible in the diff. Only same-repo authors can do this, and the check is advisory. `--text` would close it, but would also send real binary bytes to the model, raising cost.
- **Fix**: None.
- **Decision**: LEFT, a fix would raise cost

### F6 — The 0.14 USD bound is an estimate, not a ceiling

- **Severity**: OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Plan Adherence
- **Location**: scripts/review/cost.py, `worst_case_usd`
- **Detail**: The bound assumes 3 characters per token and leaves out the schema sent with the call. Dense text at 1 token per character would cost about 0.24 USD (60,000 x 2.50 + 6,000 x 15.00, per million). The plan already calls it an estimate. The formula itself equals `turn_cost`, and the drift test ties them together.
- **Fix**: None. The CI key's monthly limit is the real ceiling.
- **Decision**: LEFT, informational

### F7 — Small additions beyond the plan

- **Severity**: OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Scope Discipline
- **Location**: scripts/review/run_review.py, .github/workflows/ai-review.yml
- **Detail**: Not in the plan and all benign: the prompt's note when the diff was cut, folding a rationale onto one line, and the post step re-checking the verdict. The `state == 'open'` job condition is the plan's recorded addition. If writing `$GITHUB_OUTPUT` itself fails, a comment file exists with no verdict, which is harmless because posting needs the verdict.
- **Fix**: None.
- **Decision**: LEFT, benign
