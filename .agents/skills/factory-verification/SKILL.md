---
name: factory-verification
description: Shared reference and hard mandate for how the factory agents verify a change in the task's target repo — by exercising the affected code path, adding a failing-then-passing regression test (written per the target repo's test_guidance from its target_repos entry) when the change has meaningfully testable behavior (testing-exempt categories — config-only, dependency/version-bump, constant-or-flag-default, pure data/copy — skip the test but must name the category and rationale), and running the target repo's validation gate (its validate_command) unconditionally (no UI/computer_use for headless or purely-backend changes); and, for user-facing changes (any change a human could see rendered in a UI, regardless of which repo it targets), ADDITIONALLY by exercising the running UI with the computer use tool and capturing screenshot/visual proof attached to the task record and the PR. Use whenever a change alters behavior or any user-facing surface, to confirm the real defect is gone with deterministic checks (plus visual proof when user-facing) before claiming the fix works. This verification is mandatory and non-deferrable.
---

# factory-verification

Shared reference for verifying changes in the factory loop. Verification is done
with **deterministic code-level checks** against the task's target repo. Some
changes are also **user-facing** (they produce observable UI), and those
**additionally** require **visual proof** captured with the computer use tool.
Any factory skill that ships or reviews a change defers here for the mechanics —
and for the rule that this step is **not optional**.

The two knobs come from the task's target repo's entry in `target_repos` in
`foreman/config.json`:
- `validate_command` — that repo's full validation gate (formatting,
  linting, tests, build — exact tools vary by repo). Run it from the target repo
  root; it must pass before any PR is opened or marked ready.
- `test_guidance` — one line describing how regression tests are written and run
  in that repo. Follow it when adding the regression test below.

## Backend / headless changes: verify in code (no UI, no computer use)

Whether `computer_use` applies depends on the target repo **and** the change. A
**purely-backend change, or any change in a headless service** (no UI) — a
handler/response, business logic, a DB query, a migration, serialization, an
error path — has **nothing to click**, so do **not** reach for `computer_use`;
it does not apply. You verify by running the repo's own toolchain and tests in
the cloud Oz environment: exercise the affected code path, prove the defect with
a test, and gate on the target repo's `validate_command` (from its
`target_repos` entry).

## User-facing changes: ALSO capture visual proof

Some changes **are** user-facing — they produce observable UI (a web app or other
client surface in a UI-bearing repo, or any change a human could *see* rendered),
**regardless of which repo they target**. For any change with an observable
user-facing effect, the code-level checks above are **necessary but not
sufficient**: you must **also** capture visual proof of the new behavior.

The mechanics live in `factory-ui-verification`. Use that skill to decide when a
change is user-facing, exercise the running UI with `computer_use`, capture
screenshots or video, and attach the proof to the task record and the PR body.
`factory-ui-verification` also owns the rule that media never commits to the
branch and the explicit-exception path when the running UI cannot be exercised.

A user-facing change shipped **without** visual proof is **unverified** — do not
claim it works, and the code-review agent treats the missing proof as a
**blocking finding (REJECT)**, not a soft nit. The proof must also be **validated
against the spec / acceptance criteria** (proof-against-spec). Proof that shows
the wrong surface or omits a required acceptance criterion is treated the same as
missing proof.

## Rework path

When a review rejection bounces a user-facing change back with `blocked`, the
implementation agent must re-capture or update the visual proof **against the
spec** before re-marking the PR ready. The PR description and task record must
reflect the updated proof; the media itself is never committed to the branch.

## This verification is MANDATORY and non-deferrable

If the change alters observable behavior — a handler/response, business logic, a
DB query, a migration, serialization, an error path, or a user-facing surface —
you **must** prove the defect is gone with a deterministic check **before**
opening (or marking ready) the PR.

- It is **not** satisfied by the code compiling or by reasoning about the diff.
  Those are necessary but not sufficient.
- You may **not** defer it to the PR reviewer ("the requester can check it"), to
  a follow-up, or to "if there's time." The whole point of the agent is that the
  reviewer trusts it was actually verified.
- **The validation gate (the target repo's `validate_command`) is
  unconditional** — it runs on every change, testing-exempt ones included.
- **Regression test: conditional.** Required for changes with meaningfully testable behavior; **skipped** for testing-exempt changes where a test would be tautological (it could only assert the new value, not detect a logic defect): config-only, dependency/version bump, constant-or-flag-default, pure data/copy, or any other such case. When skipping, **name the testing-exempt category and state the rationale** in the task update and PR body. An unwarranted test on a testing-exempt change is scope creep, not safety.
- For a **user-facing** change, the visual proof above is part of this mandate:
  shipping it without computer-use screenshots is the same as shipping a backend
  fix with no regression test.

## How to verify

1. **Reproduce the defect at the code level first.** Drive the affected path the
   way the bug describes: a focused test, a direct function/handler call, a
   local request against a locally-run server, or exercising the affected
   query/migration. Confirm you observe the reported wrong behavior before
   changing anything — a fix you can't first make fail is not understood.
   (Skip this step for testing-exempt changes — proceed directly to the
   validation gate.)
2. **Add a regression test that fails before the fix and passes after** — unless the change is testing-exempt (see *This verification is MANDATORY* above). Write it per the target repo's `test_guidance` (from its `target_repos` entry). This is the contract that proves the defect is gone and stays gone. Put it next to the code it covers, following the repo's existing test conventions. Name it so the failure clearly maps to the bug. If skipping, name the testing-exempt category and state the rationale in the task update and PR body.
3. **Run the full gate unconditionally** — every change, testing-exempt ones included. From the target repo root, run that repo's validation gate:
   ```bash
   <the target repo's validate_command from its target_repos entry in foreman/config.json>
   ```
   It runs formatting, linting, the test suite, and the build (exact tools vary
   by repo — consult the command's script or the repo's README). For a faster
   inner loop you may run the targeted package/module first, but the validation
   gate must pass before the PR is opened or marked ready.
4. **Confirm the original symptom is gone** on the real path — re-run the repro
   from step 1 (or the new regression test) and verify the corrected behavior
   matches the intended outcome. (Skip for testing-exempt changes with no
   testable behavior.)
5. **For a user-facing change, also capture visual proof.** Invoke
   `factory-ui-verification` to exercise the running UI and capture screenshots or
   video of the rendered surface. This is in addition to (not a replacement for) the
   code-level checks in steps 1–4.
6. **Record the evidence** you post to the task record (see `factory-tracker-ops`)
   and reference in the PR: the new test name (or skip category + rationale for
   testing-exempt changes), the relevant validation/test output, a one-line
   before/after of the observed behavior, and — for a user-facing change — the
   visual proof embedded in both the task record and the PR body.

If the toolchain is genuinely unavailable in this environment, do **not**
silently proceed and do **not** claim the fix was verified. Say so explicitly in
the task record and PR body, and treat the fix as unverified pending a human
check. The same applies when a user-facing change cannot be exercised in the
running UI: say so explicitly and treat the visual proof as outstanding.

## Writing verification criteria around this (for specs)

When `factory-spec` writes validation criteria for a fix, write them assuming
this verification *is* performed, and make them checkable **through it**:

- State the exact repro to re-run (test, request, or function call) and the
  **observable** expected result (e.g. "`GET /v1/foo` returns 200 with `bar`
  set, not 500").
- Name the regression test that must fail before and pass after the fix — or,
  for a testing-exempt change, state the testing-exempt category; the
  validation gate (the target repo's `validate_command`) is then the only
  required check.
- Require the validation gate to pass unconditionally, and call out any adjacent
  behavior that must still work (with the test that proves it).

A criterion that can't be confirmed by a deterministic check against the running
code isn't done — rewrite it until the validation gate or a named test can check
it. For testing-exempt changes, a passing validation gate is sufficient.
