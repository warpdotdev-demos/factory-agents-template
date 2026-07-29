---
name: check-impl-against-spec
description: Compare a PR's implementation against available spec context and fold any material mismatches into the factory code-review agent's review. Use during a factory review when a spec (e.g. one produced by factory-spec) or repository spec context is available for the PR. This is a supplement to review-pr, not a separate output.
---

# check-impl-against-spec

A supplement to `review-pr` for the code-review agent. Use it only when spec
context for the PR is available — for factory PRs that is the spec produced by
`factory-spec`, which is **committed as a file on the PR branch** (GitHub is the
source of truth). This never produces its own output; its findings fold into
the single review `review-pr` posts.

## Goal

Decide whether the implementation in the PR **materially** matches the spec.
Small, intent-preserving adjustments are fine; only material drift is a review
concern.

## Inputs

- The spec: read the **committed spec file on the PR branch** (under the
  repo's `agents/specs/` directory, named `<ticket-key>: <very brief title>.md`).
  GitHub is the source of truth — a human may have edited the committed spec
  directly — so read it from the branch, not from a ticket comment. The ticket
  records the spec PR link (via `factory-tracker-ops`) if you need to locate it.
- The PR diff and body (fetched in `review-pr` Step 1).
- The checked-out PR branch contents when deeper inspection is needed.

## Process

1. Extract the spec's concrete commitments:
   - required behaviors / acceptance criteria,
   - required files or subsystems to change,
   - stated constraints,
   - required validation, migrations, or follow-up steps.
2. Compare those commitments against the actual diff and checked-out files.
3. Accept small implementation-level differences (naming, structure, technique)
   when they preserve the spec's intent — don't flag harmless variation.
4. Flag a mismatch only when it is material, e.g.:
   - a required behavior is missing,
   - the implementation contradicts a spec decision,
   - the change introduces significant unplanned scope,
   - a required validation/migration/compatibility step is absent.

## Output

- Fold findings into the same review `review-pr` posts — no separate file.
- Put broad spec-drift concerns in the review overview body; add inline comments
  only when a mismatch ties to specific changed lines.
- Treat material spec drift as at least an `⚠️ [IMPORTANT]` concern.
- If the implementation matches the spec closely enough, add nothing.

## Boundaries

- Don't require literal one-to-one implementation when the PR achieves the same
  outcome safely.
- Don't speculate about spec details that aren't actually present.
- Don't merge the PR or act beyond informing the review.
