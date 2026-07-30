---
name: review-pr
description: Review a pull request's code change against a CI/build/test gate and a seven-dimension rubric (correctness, standards, complexity, naming, comments, tests, security) plus spec alignment, then post a single structured GitHub review for the factory code-review agent. Use after factory-review identifies the target PR. Checks CI status and builds/tests the change with the target repo's validation gate (its validate_command from its target_repos entry), requires visual proof of testing (via factory-ui-verification) validated against the spec for user-facing changes and treats missing or spec-mismatched proof as a blocking REJECT, fetches the diff with gh, produces labeled inline comments and a final summary body with a clear verdict (accepted/rejected), posts the review, and notifies the task's record. Never merges the PR.
---

# review-pr

The code-review agent's core skill. `factory-review` routes here once the target
PR is known. **Goal:** review the code change and identify **all** issues that
must be addressed before it can be accepted. Output: **one** posted GitHub review
(a final summary body + verdict + inline comments) and a notification on the
task. You never merge — the verdict is advisory; a human merges.

The review has three parts, in order: (1) **gate on CI / build / tests**, (2)
**evaluate the change across the rubric dimensions**, and (3) **post inline
comments + a final summary with an accepted/rejected verdict**.

Keep the live status comment current and status posts terse per
`factory-progress-updates`. Use `factory-github-ops` for PR mechanics,
`factory-verification` for the build/test toolchain, and `factory-tracker-ops`
for posting to the task. The PR's repo is the task's target repo (the repo
recorded on the ticket); read its `validate_command` from its entry in
`target_repos` in `foreman/config.json`.

## Step 1 — Fetch the PR and its diff

```bash
gh pr view <pr> --repo <owner/repo> --json title,body,headRefOid,files
gh pr diff <pr> --repo <owner/repo>
```

Review only the files and lines this PR changes. Read the PR body for stated
scope and rationale before judging. If spec context is available for the PR, run
`check-impl-against-spec` and fold its findings into this same review.

## Step 2 — Check CI status, build, and run tests

Before judging the code, confirm the change is healthy. A headless or
purely-backend change is verified in code — build and run the tests, no UI needed
(see `factory-verification`). For a **user-facing** change (regardless of which
repo it targets), the PR must also carry **visual proof of testing** owned by
`factory-ui-verification` (screenshots or video in the PR body / task record),
and that proof must be **validated against the spec / acceptance criteria**
(proof-against-spec), not merely present. Confirm it in Step 3 — missing visual
proof, or proof that captures the wrong surface or omits a required acceptance
criterion, is a **blocking finding → REJECT (changes requested)** on a
user-facing change, not a soft nit. The review run is dispatched **with computer
use enabled**, so when the proof is absent or insufficient exercise the running
UI yourself with the **computer use** tool to confirm the behavior before
deciding the verdict. Consult `factory-verification` and `factory-ui-verification`
for whether `computer_use` applies to the target repo.

1. **Check CI status** on the PR head:
   ```bash
   gh pr checks <pr> --repo <owner/repo>
   ```
   Note any failing, pending, or missing required checks.
2. **Build and run the tests** for the change. Check out the PR branch and run
   the repo's gate per `factory-verification` (targeted package first for speed,
   then the full gate):
   ```bash
   gh pr checkout <pr> --repo <owner/repo>
   # Run targeted tests first for a fast inner loop
   <the target repo's validate_command from its target_repos entry>   # fmt, lint, full test suite, build
   ```
   Confirm the change **builds** and that the **tests pass** (especially any new
   regression test the change added). For **testing-exempt** changes, confirm
   the PR body names the testing-exempt category and states the rationale.
   **The validation gate (the target repo's `validate_command`) is mandatory
   for every change** (including testing-exempt ones); a PR where the
   validation gate was not run or failed is a blocking finding.

Treat CI/build/test health as a **blocking** input to the verdict: a change that
does not build, has failing tests, or has red required CI **cannot be accepted**
(`🚨 [CRITICAL]`). If the toolchain is genuinely unavailable in this
environment, do not claim it passed — say so explicitly in the review and lean on
CI status, per `factory-verification`.

## Step 3 — Evaluate the change across the rubric dimensions

Identify **all** issues that must be addressed before the change is accepted.
Evaluate every changed artifact across these dimensions:
- **Correctness** — bugs, broken logic, unhandled edge cases, error handling.
- **Standards** — adherence to the repo's and language's conventions, idioms,
  lint/format rules, and established patterns.
- **Complexity** — unnecessary complexity, dead code, over-long functions, and
  meaningful performance issues; simpler equivalents.
- **Naming** — clear, accurate, consistent identifiers for files, types,
  functions, and variables.
- **Comments** — necessary explanatory comments present; misleading or stale
  comments removed; no redundant noise.
- **Tests** — adequate coverage for the changed behavior, including a regression
  test for a fix; existing tests still pass (Step 2). Required for changes with
  meaningfully testable behavior. **Testing-exempt changes** (config-only,
  dependency/version bump, constant-or-flag-default, pure data/copy, or any
  other case where a test would be tautological): accept the skip when the PR
  body names the testing-exempt category and states the rationale; do **not**
  flag a missing test for a correctly-identified testing-exempt change. Flag an
  **unwarranted test** on a testing-exempt change as scope creep
  (`💡 [SUGGESTION]` if low-effort, `⚠️ [IMPORTANT]` if non-trivial
  maintenance burden). For a **user-facing** change, the PR must also include
  **visual proof of testing** owned by `factory-ui-verification` — screenshots
  or video of the validated behavior in the PR body (and/or the task record),
  **validated against the spec / acceptance criteria** (proof-against-spec), per
  `factory-verification` and `factory-ui-verification`. If a user-facing change
  ships **without** that visual proof, or the proof captures the wrong surface or
  omits a required acceptance criterion, that is a **blocking finding → REJECT
  (changes requested)**, not a soft nit — the change is unverified until
  spec-aligned proof is supplied.
- **Security** — injection, auth/authz, secret handling, unsafe input.

Also fold in **spec alignment** when spec context exists (material drift is a
concern — see `check-impl-against-spec`).

**PR description quality.** Flag the PR description as a finding
(`💡 [SUGGESTION]` at minimum, escalating to `⚠️ [IMPORTANT]` when it actively
misleads the reviewer) if it reads like an iteration/rework chronicle or commit
log instead of a clean current-state summary of the PR's net effect. Request
that the description be rewritten to describe what the PR does now. Raise this
finding in the final summary body, not as an inline comment.

Constraints:
- Treat **correctness**, **security**, a broken **build/tests/CI** (Step 2), and
  **missing or spec-mismatched visual proof on a user-facing change** (Step 2 /
  the Tests dimension) as blocking; the others are blocking only when they
  materially harm the change.
- Include style/nit comments only when you attach a concrete suggestion block.
- If a concern involves untouched code, **or cannot be tied to a specific changed
  line in the diff from Step 1**, raise it in the final summary body, not as an
  inline comment.
- Don't suggest tests that only vary inputs/fields when existing tests already
  cover the behavior; only propose tests that exercise a distinct path or edge
  case.
- For a clear V0 / initial implementation, frame robustness asks (timeouts,
  retries, lifecycle) as optional future work unless they risk correctness,
  security, or data loss.

## Step 4 — Comment labels

Every inline comment body must start with one of:
- `🚨 [CRITICAL]` — bugs, security issues, crashes, or data loss.
- `⚠️ [IMPORTANT]` — logic problems, edge cases, or missing error handling.
- `💡 [SUGGESTION]` — worthwhile improvements or better patterns.
- `🧹 [NIT]` — cleanup, only when the comment includes a suggestion block.
- `❓ [QUESTION]` — an open question about intent, rationale, or design that
  requires a decision before action can be taken. Use when you need clarification
  or when the point warrants product or technical discussion rather than a
  direct code change. The implementation agent will research and reply but will
  **not** resolve this thread automatically — only the human reviewer closes it.

Be concise, direct, and actionable. No compliments or hedging. Prefer
single-line comments; keep ranges to at most 10 lines. Only comment on files and
lines present in this PR's diff. Before finalizing each inline comment, verify
its `path` and `line` appear in the diff fetched in Step 1 — GitHub silently
drops comments whose line is not in the diff, so put those concerns in the body
instead.

## Step 5 — Suggestion blocks

When proposing a concrete change, use a GitHub suggestion block:

```suggestion
<replacement code here>
```

- Match the exact indentation of the original file.
- The block replaces **exactly** the commented line range — include only the
  replacement code for those lines, nothing above or below. Do not repeat lines
  that appear immediately above `start_line` or below `line`; they remain in the
  file and repeating them causes that content to appear twice after commit.
- Count brace/bracket/paren/block-delimiter depth (`{`, `[`, `(`, `end`, etc.)
  across the original replaced lines and ensure the replacement ends at the same
  depth — do not emit phantom closing tokens, and do not drop required ones.
- For multi-line suggestions, set `start_line` and `start_side` on the comment
  to the first line of the range and `line`/`side` to the last. `start_side`
  is required when `start_line` is present and must be `"LEFT"` or `"RIGHT"`.
- When unsure of the surrounding context, widen `start_line`/`line` to include
  enough real changed lines rather than guessing at surrounding tokens.

## Step 6 — Post inline comments + the final summary

Write the review body as **plain markdown** to a temp file:

```bash
cat > /tmp/review_body.md << 'EOF'
## Overview
<high-level summary as a single continuous paragraph>

## Concerns
<concerns as single continuous paragraphs>

## Verdict
Found: X critical, Y important, Z suggestions

**Approve** / **Request changes**
EOF
```

Write each paragraph as a single continuous line — do not manually wrap prose at 80 characters. GitHub PR review renders every newline within a paragraph as a visible line break, making the text look choppy. Use newlines only for `##` headings and blank lines between sections.

Build inline comments as a JSON file using `jq` — jq safely encodes all string
values (newlines, quotes, emojis, backticks) so no shell escaping is needed.
Use an empty array when there are no inline comments:

```bash
jq -n '[
  {
    "path": "pkg/foo.go",
    "line": 42,
    "side": "RIGHT",
    "body": "⚠️ [IMPORTANT] Short explanation"
  }
]' > /tmp/review_comments.json

# No inline comments:
jq -n '[]' > /tmp/review_comments.json
```

For multi-line ranges also include `start_line` and `start_side` in each object.

Map the recommendation to a GitHub review event:
- `Approve` / `Approve with nits` → `APPROVE` (**accepted**)
- `Request changes` → `REQUEST_CHANGES` (**rejected**)

Then post the review (markdown body + JSON comments file in one API call) per the
**"Post a review to GitHub"** step in `factory-github-ops`.

Do **not** post duplicate reviews — this skill is idempotent: if you already
reviewed this head SHA (per conversation history), don't repeat it.

## Step 7 — Notify the task

Post a notification on the task's record (tag the author) with the PR link,
verdict, one-line summary, and review link, per `factory-tracker-ops`. Your
verdict is the ticket's accepted/rejected review outcome and drives the
**terminal gate label** that `factory-review` Step 3 applies while setting status
**In Review**: an **accepted** verdict → `review-done`; a **rejected** verdict
(Request changes) → `blocked`. The code-review agent then **reports this verdict
back to the foreman** (per `factory-review` Step 3) and ends its turn. You never
merge the PR.
