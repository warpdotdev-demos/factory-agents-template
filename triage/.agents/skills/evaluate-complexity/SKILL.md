---
name: evaluate-complexity
description: Decide whether a clear bug is obvious-and-safe enough for triage to mark `spec-done`, or non-obvious enough for triage to mark `triage-done` and require a written spec artifact, and choose the ticket's story-point estimate. Use this in the triage workflow after a bug report is understood. Trigger whenever triage needs to judge fix risk, blast radius, ambiguity, or size before applying its completion label and estimate.
---

# evaluate-complexity

Decide triage's local completion outputs for a **clear** bug report: which
**gate label** to apply and which **story-point estimate** to set on the ticket.

- **Obvious & safe** → apply `spec-done` (the spec phase is skipped). Record a
  clear fix direction in the issue's Solution.
- **Non-obvious** → apply `triage-done` (requires a written spec artifact).

Also choose the estimate using the story-point scale:
- **XS=1 / S=2** — localized, obvious, low-risk work with straightforward
  validation.
- **M=3** — moderate scope, multiple files, or some uncertainty that still has a
  bounded approach.
- **L=5 / XL=8** — cross-cutting, risky, ambiguous, or feature-sized work that
  needs deeper specification.

The cost of being wrong is asymmetric. Shipping a sloppy "obvious" fix that's
actually subtle wastes a review cycle and erodes trust in the agent; spec'ing a
truly trivial one-liner wastes time and annoys people. When genuinely on the
fence, **lean toward `triage-done`** — a written spec is cheap insurance and keeps a
human in the loop for anything non-trivial.

This step builds on the outcome of `factory-triage` Step 3 — a confirmed
hands-on repro, an environment-mismatch skip, a documented non-repro theory, or,
for a trivial/obvious fix, a deliberate "trivial — no repro needed" skip. For a
non-trivial issue, if you have not yet attempted to reproduce the bug, go back
and do that first; do not assess obviousness (or reach for a spec) from
code-reading alone. A non-repro (except an environment-mismatch skip) is a
strong signal for `triage-done`.

## What "obvious & safe" means

ALL of these should hold. If any is shaky, it's not obvious:

- **Root cause is known**, not guessed. You can point to the specific code and
  explain *why* it produces the bug — not "probably around here."
- **Localized.** The change is confined to a small number of files / a single
  component, with no API/contract/shared-state changes that ripple outward.
- **Low blast radius.** Hard to imagine it breaking unrelated surfaces. Not on
  a hot path, startup, auth, data persistence, or a business-critical (P0)
  flow.
- **Unambiguous desired behavior.** There's one reasonable correct outcome and
  the requester (and any sane reviewer) would agree on it. No product/design
  judgment call.
- **Verifiable.** You can validate the fix concretely with a deterministic check
  per `factory-verification` — a regression test (per the target repo's
  `test_guidance`) that fails before and passes after, plus that repo's
  validation gate (its `validate_command` from its `target_repos` entry). If
  you can't see how you'd actually verify the corrected behavior, it isn't
  obvious.

Typical obvious fixes: a wrong/missing field in a response, an off-by-one or
boundary error, an incorrect default or config value, a wrong status code, a
trivial nil/empty guard, a mis-parsed value, a clearly-inverted condition, or a
typo in a user-facing message or error string.

## What pushes it to non-obvious

Any one of these is enough:

- Root cause is uncertain or you'd need to dig to find it.
- Multiple plausible fixes with real tradeoffs, or the "right" behavior is a
  product/design decision.
- Touches shared code, public APIs, async/concurrency, state machines, data
  migration, or a business-critical / out-of-band-release-worthy flow.
- The reproduction itself is unclear, intermittent, or environment-specific.
- The fix is large, spans many files, or you can't cleanly enumerate how you'd
  verify it.

When in doubt about whether the fix could regress something you can't easily
see, treat it as non-obvious.

## Output

Decide, then record a one-line rationale on the task's record (it explains the
local triage output). The decision includes a gate label and estimate — apply
both via `factory-tracker-ops`; do not route into another step skill:
- Obvious → apply `spec-done` (spec skipped).
- Non-obvious → apply `triage-done` (written spec required).
- Estimate → set XS/S/M/L/XL as story points 1/2/3/5/8.

Do **not** ask the requester to choose the path — this judgment is your job.
