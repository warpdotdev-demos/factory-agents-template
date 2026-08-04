---
name: evaluate-complexity
description: After understanding a bug or feature, judge whether a spec would add real value and choose the ticket's story-point estimate. The default is no spec - apply `spec-done` and go straight to implementation; only apply `triage-done` when BOTH significant product ambiguity AND material technical complexity are present. Use this in the triage workflow after a report is understood. Trigger whenever triage needs to judge fix risk, blast radius, ambiguity, or size before applying its completion label and estimate.
---

# evaluate-complexity

Decide triage's local completion outputs for a **clear** report: which **gate
label** to apply and which **story-point estimate** to set on the ticket.

- **No spec (the common path)** → apply `spec-done`; the spec phase is skipped
  and the work goes straight to implementation.
- **Spec (the uncommon path)** → apply `triage-done`; a written spec artifact is
  required first.

Also choose the estimate using the story-point scale:
- **XS=1 / S=2** — localized, obvious, low-risk work with straightforward
  validation.
- **M=3** — moderate scope, multiple files, or some uncertainty that still has a
  bounded approach.
- **L=5 / XL=8** — cross-cutting, risky, ambiguous, or feature-sized work.

**The default is no spec.** Don't require one unless it would materially
reduce the risk of shipping the wrong thing. When on the fence, lean toward
no spec — implementation agents handle reasonable judgment calls well, and
code-review catches architectural missteps.

This step builds on the outcome of `factory-triage` Step 3 — a confirmed
hands-on repro, an environment-mismatch skip, a documented non-repro theory, or,
for a trivial/obvious fix, a deliberate "trivial — no repro needed" skip.

## When to apply NO spec (the common path)

No spec is the right default for:

- **Clear bugs with a known or diagnosable fix.** Root cause is identifiable;
  the correct behavior is unambiguous; the fix is localized.
- **Self-skills / factory-agent changes.** Almost always go directly to
  implementation.
- **Features with clear, well-scoped requirements.** The desired behavior is
  specified well enough that an agent can implement without guessing.
- **Localized changes** confined to a small number of files or a single
  component with no API/contract/shared-state changes that ripple outward.
- **Low blast radius.** Not on a hot path, startup, auth, data persistence, or
  a P0 flow.
- **Verifiable.** You can validate the fix concretely with a deterministic check
  per `factory-verification` — a regression test (per the target repo's
  `test_guidance`) that fails before and passes after, plus that repo's
  validation gate (its `validate_command`, both from its `target_repos` entry).
  If you can't see how you'd actually verify the corrected behavior, it isn't
  obvious.

Record a concrete fix/build direction in the issue's **Solution** section so
the implementation agent inherits clear direction.

## When to apply a spec (the uncommon path)

Require a spec **only** when BOTH of the following are true:

1. **Significant product ambiguity** — there are multiple reasonable product
   behaviors and the "right" answer requires a deliberate product decision that
   shouldn't be left to the implementor (competing UX flows, behavioral tradeoffs
   between stakeholders, or an under-specified request where a spec + approval
   cycle would catch the disagreement).

2. **Material technical risk or complexity** — the change is large, cross-cutting,
   architecturally significant, touches shared APIs/state machines/auth, or is
   risky enough that writing the approach down and getting human sign-off is
   worth the delay.

Examples that warrant a spec: a new multi-step user flow with unclear edge-case
behavior, a change to a shared authentication or billing path, a feature that
requires design choices among competing valid approaches, or a large refactor
with unclear scope.

Examples that do **not** warrant a spec: a well-specified feature request where
requirements are clear (even if the change is large), a bug with a known root
cause that affects many files, or a self-skills change to agent behavior.

**A non-repro is NOT by itself enough to require a spec** — if the bug is
still clear from the report and codebase, no spec is needed.

## Output

Apply the gate label and the estimate via `factory-tracker-ops`; do not route
into another step skill. Record a one-line rationale on the task's record:
- No spec → apply `spec-done` (the spec phase is skipped) and record the fix
  direction in the issue's **Solution**.
- Spec → apply `triage-done`, naming **both** the product ambiguity and the
  material technical risk. If you can only name one, it's `spec-done`.

Set the estimate: XS/S/M/L/XL as story points 1/2/3/5/8.

Do **not** ask the requester to choose the path — this judgment is your job.
