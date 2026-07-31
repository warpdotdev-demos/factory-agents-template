---
name: factory-implement
description: Resolve a ticket by producing one or more validated code artifacts against the task's target repo (its entry in config target_repos in foreman/config.json). Reuse the spec phase's existing draft PR when one exists — check out its branch and read the committed spec from it (GitHub is the source of truth) — adding the implementation to the same branch/PR rather than opening a new one and marking that reused spec PR ready for review; when there is no spec PR (an obvious spec-skipped fix or a bare prompt), open the PR yourself ready for review. Fetch the ticket plus any committed spec (spec'ing is optional), read the codebase for context, mark the ticket in progress, plan and orchestrate subtasks in parallel where appropriate, implement with incremental commits and tests, self-review, validate (regression test + the target repo's validation gate, plus computer-use screenshot proof for user-facing changes attached to the task and the PR), ensure the PR carries the PR↔task metadata block (updating the shared spec PR's title + description + marking it ready, or opening one ready for review when spec-skipped), assign the requester, link the PR on the ticket, keep status In Progress, and apply impl-done. Use when a ticket is marked ready for implementation (`spec-done`), marked for PR rework (`blocked`), or a user asks the implementation agent to write a PR. Never merges.
---

# factory-implement

The implementation agent's core skill. **Goal:** produce one or more code
artifacts that resolve a ticket. Use this skill when:
- a ticket is marked **ready for implementation** (`spec-done`),
- a ticket is marked `blocked` for PR rework, or
- a **user asks the implementation agent to write a PR** (a prompt, with or
  without a ticket).

How the task arrived here, and what happens after this step completes, belongs
to the foreman. Your job is to resolve the ticket with validated code artifacts
or record why implementation is incomplete.

**Input:** a ticket, with or without an associated product and technical spec —
spec'ing is optional. The ticket may include only a concrete fix direction, or it
may include a spec with validation criteria.

**Output:** one or more **ready-for-review** code artifacts (PRs) against the
target repo (except a reused spec PR you promote from draft to ready when adding
code), each validated and stamped with the PR↔task metadata block with the requester
assigned as reviewer, plus the implementation completion signals on the ticket:
the PR link, status **In Progress**, and `impl-done` label (or an incomplete
blocker). You never merge — a human does.

Keep the task's **live status comment** current and status posts terse per
`factory-progress-updates`. Read/post the task through `factory-tracker-ops`; use
`factory-github-ops` for PR mechanics and `factory-verification` for the
validation mandate. The task's target repo is the repo triage recorded on the
ticket (the `Target repo: <org/repo>` line, also usually in your brief); resolve
its `base_branch`, `validate_command`, `test_guidance`, and app-boot settings
with one call rather than reading the config by hand:

```bash
scripts/factory-config repo --repo <task's target repo>
```

Do **not** substitute a different repo, and do not reuse another repo's gate or
test conventions — with many repos configured, each one has its own.

## Step 0 — Locate the ticket, then gate on the label

A ticket is **required** at all times — never run ticketless. The foreman is the
sole ticket creator — you never create or search for tickets independently.
Establish the task_id in this order:
1. **Provided in the brief.** If the foreman included a `task_id` (the fast
   path), adopt it.
2. **Drain inbox (parallel-dispatch path).** If `task_id` was not in the brief,
   drain your inbox before any tracker operations: call `list_messages_from_agents`
   and `read_messages_from_agents` on any pending messages. The foreman sends
   `{"task_id":"<key>","task_url":"<url>"}` shortly after dispatch. If nothing
   yet, call `wait_for_events` once (up to 2 minutes) then drain again.
3. **Error if still none.** If the task_id still hasn't arrived, post a brief
   error in the conversation ("No task_id received from foreman — please resend
   the ticket link") and **end your turn**. Do **not** create a ticket.

Then trust your run's conversation history for what you've already done, and
re-derive externally-mutable facts:
- PR facts via `scripts/factory-state --task-id <task_id> --repo <task's target repo>` (the repo recorded on the ticket). When the ticket somehow records no target repo, pass `--issue <task_id>` so the probe covers only that project's repos plus `self_repo` instead of every configured repo.
- The linked issue's **labels** and newest comments via `factory-tracker-ops`.

**Gate on `spec-done` or `blocked`** (per the gating rule in
`factory-tracker-ops`):
- Issue linked **and** carries `spec-done` (fresh work) or `blocked` (review
  rework) → proceed.
- Issue linked but **lacks** both → post the canonical wrong-label message (from
  `factory-tracker-ops`) and **end your turn**, doing no work.
- A ticket adopted via inbox-drain (step 2) already carries `spec-done`, so it
  proceeds.

**Blocked / rework re-entry (`blocked`).** If the issue carries `blocked`
(in place of `spec-done`), a review requested changes. As soon as you confirm
you're in a `blocked` rework re-entry, **bump the durable rework counter exactly
once** so the ticket/PR metadata records this rework cycle:

```bash
scripts/factory-pr-meta bump-review-attempt --pr <pr> --repo <task's target repo>
```

It returns `{"review_rework_attempts": n}`. Then read **every** comment on
the failing review — the inline PR review comments (each labeled `🚨 [CRITICAL]`,
`⚠️ [IMPORTANT]`, `💡 [SUGGESTION]`, `🧹 [NIT]`, or `❓ [QUESTION]`), the review
summary body, and the task notification — and enumerate them into a checklist.
Fetch the PR feedback through the "Read ALL PR feedback surfaces" procedure in
`factory-github-ops`. **Keep two lists of GraphQL review thread node IDs**
(`PRRT_...`): one for **resolved threads** — action-oriented comments where you
actually make the requested code change (to pass to `factory-resolve-threads` in
Step 7) — and one for **keep-open threads** — declined requests,
discussion/question comments, and anything else requiring reviewer acknowledgment
— that you respond to but leave unresolved.

Address the review comments on the **existing** PR branch — do not open a second
PR. After pushing the rework commits, **capture the rework commit SHA** (`git
rev-parse HEAD`) — you will pass it as `--commit-sha` to `factory-resolve-threads`
in Step 7 so every resolved thread's reply links directly to that commit.
Resolve only the threads you addressed (see Step 7 and `factory-github-ops`). If
a PR already exists with no `blocked`, just reconcile state and notify (this
skill is idempotent) and do **not** bump the counter; a CI-failure signal
instead belongs to `fix-failing-ci` (which bumps the separate `ci_fix_attempts`
counter).

**Classify each comment before acting — every comment must receive a response.**
Review comments fall into two categories. **Human reviewers typically do not use
the factory agent's label format** (`🚨 [CRITICAL]`, `⚠️ [IMPORTANT]`, etc.) — when
no label is present, infer the category from the comment's content and intent.

1. **Action-oriented** — a concrete, implementable request: a bug to fix, a
   rename, code to add/remove/restructure, a missing test, a style or lint issue.
   Content signals when no label is present: direct instructions ("rename this",
   "move X to Y"), specific bug descriptions ("this will crash if …"), concrete
   code suggestions, or any comment whose natural reading is "please change the
   code in this specific way". Handle based on outcome:
   - **Implemented**: make the change, reply citing the commit SHA, and
     **resolve** the thread. This is the **only** case where the agent
     auto-resolves a thread.
   - **Declined**: reply with a clear, thorough justification for why the change
     was not made, and **keep the thread open** — the reviewer must explicitly
     acknowledge the decline; auto-resolving implies agreement.

2. **Discussion / question** — asks about intent, rationale, or design, or
   requires product or technical judgment before a course of action is clear.
   Content signals when no label is present: `❓ [QUESTION]`-labeled comments;
   open-ended questions ("why did you choose X?", "is this intentional?",
   "should this be a separate module?"); expressions of uncertainty; "what about
   Y edge case?" style prompts; or any comment whose primary purpose is to prompt
   a decision rather than request a specific code change.
   Handle with the **research → respond → keep open** cycle:
   - **Research**: investigate enough to give a well-grounded answer.
   - **Respond**: post a thorough reply on the thread directly addressing the
     question or discussion point.
   - **Keep open**: do **not** add this thread's node ID to the
     `factory-resolve-threads` call — leave the thread unresolved so the reviewer
     can read the answer and explicitly accept it or continue the discussion.
     A human must close discussion threads; never auto-resolve them.

**The rule for resolving is narrow: auto-resolve only when you made the requested
code change.** Declined requests, discussion threads, and anything the reviewer
must be made aware of and explicitly accept always stay open. When the category
is ambiguous, default to keeping the thread open.

**Every comment in both categories must receive a response.** Do **not** silently
skip any comment — not even praise (just say thanks) or a comment about untouched
code outside this PR's scope (acknowledge and note a follow-up where relevant).
The **exit criterion** before re-applying `impl-done` in Step 7 is: every
action-oriented comment that was implemented is resolved; every declined request
and every discussion/question comment received a thorough reply and is left open.
Re-walk the full checklist before completing.

## Step 1 — Locate the spec PR, fetch the spec, and read the codebase for context

Gather everything you need before writing code:
- **Find the spec PR and reuse it.** The spec phase commits the spec to a
  **draft PR**, and you build on that same PR/branch. Locate it with
  `scripts/factory-pr-meta find --task-id <task_id> --repo <task's target repo>`
  (see `factory-github-ops`); when it exists, **check out that branch** and add
  your code there — do **not** open a second PR. If none exists (triage spec-skipped an
  obvious fix, or a bare-prompt request), you'll create the branch and open the
  PR yourself (Step 3 / Step 6).
- **Fetch the spec (GitHub is the source of truth).** When a spec PR exists, read
  the **committed spec file on its branch** — a human may have edited it directly,
  so the committed file (not any ticket comment) is your exact contract and its
  validation criteria are your checklist. Also read the ticket's description and
  acceptance criteria via `factory-tracker-ops`. Spec'ing is optional: an
  obvious spec-skipped fix has no committed spec.
- **Read the codebase for context.** With the task's target repo checked out
  (the spec branch when present, else the repo's `base_branch` from its
  `target_repos` entry), read
  the relevant code paths, surrounding package conventions, and existing tests
  so your change fits the repo's patterns.

## Step 2 — Mark in progress, then plan (orchestrate in parallel where useful)

- **Update the ticket: in progress.** Set the lifecycle status to **In
  Progress** via `factory-tracker-ops`.
- **Plan the implementation.** Break the work into the minimal set of changes
  that resolve the ticket. **Orchestrate subtasks in parallel where
  appropriate** — for genuinely independent units of work, fan out parallel
  agents on isolated branches/worktrees and integrate their results; keep a
  single change serial when parallelism adds no value.
- **Stop early if the spec is underspecified.** If the spec or report leaves a
  genuine ambiguity you cannot resolve from the ticket or the codebase, **note
  the blocking issue on the ticket** (and surface the specific question to the
  requester in the task's conversation channel, written for a stranger — via a
  `RELAY:` message to the foreman on a Slack-door task since you cannot post
  to the Slack thread yourself, or a Jira comment you post on a Jira-door
  task, per **Who can post where** in `factory-tracker-ops`), set the ticket's
  terminal status to **incomplete** (see Step 7), and **stop** rather than
  guessing.

## Step 3 — Implement with incremental commits and tests

Implement the **minimal correct change** on the **spec PR's branch when one
exists** (checked out in Step 1) — otherwise on a new branch `factory/<short-slug>`
(see `factory-github-ops`):
- For an **obvious** fix: make the targeted change at the known root cause. Keep
  it localized; do not refactor adjacent code or expand scope.
- For a **spec'd change**: implement exactly what the spec describes. If you
  discover the spec is wrong or incomplete mid-implementation, stop, record the
  mismatch/blocker on the ticket, report it to the foreman, and do not silently
  diverge.

Push **incremental commits that include their tests** as you complete each unit
of work, and **update the ticket when a milestone is reached** (terse, per
`factory-progress-updates`) so progress stays visible. Follow the repo's existing
patterns and surrounding package conventions; default to one logical change per
PR, splitting into more than one PR only when the work is genuinely separable.

**Keep the committed diff to the change plus the spec — never commit testing or
verification artifacts.** The PR's diff contains the source and test code that
constitutes the fix **plus the committed spec file** the spec phase added (which
stays in the PR). The regression test from Step 4 *is* part of the change and
belongs in the diff; everything the test/verify steps produce as scaffolding does
**not**. Specifically, do **not** commit:
- **Testing artifacts** — validation/test output, logs, coverage reports, scratch
  repro scripts, throwaway fixtures, screenshots, or other temporary files created while
  verifying (as distinct from the regression test, which is committed).
- **Verification artifacts** — captured screenshots / visual proof. These are
  embedded in the **PR body and the task record** (Steps 4 & 6), not committed to
  the branch.

The **committed spec file is expected in the diff** — leave it in place (don't
delete it). If you discover mid-implementation that the spec is wrong or
incomplete, record the mismatch/blocker on the ticket, report it to the foreman,
and do not silently diverge. Before each commit, run `git status` / `git add -p`
and stage **only** the intended source, test, and spec files. If a
testing/verification artifact slipped into the working tree, delete it (or add it
to `.gitignore`) rather than committing it — and if one was already committed,
remove it from the branch before opening the PR or marking it ready.

## Step 4 — Validate (MANDATORY, per `factory-verification`)

Before opening or marking any PR ready, prove the defect is gone deterministically:
1. **Add a regression test** that fails before your change and passes after,
   written per the target repo's `test_guidance` (from its `target_repos`
   entry). Place it with the code it covers; name it
   so the failure maps to the bug. Follow the repo's existing test conventions
   for the language/framework.
2. **Run the gate** from the repo root — the target repo's validation gate:
   ```bash
   <the target repo's validate_command, from scripts/factory-config repo --repo <task's target repo>>
   ```
   It must pass (formatting, linting, tests, build — exact tools vary by repo;
   consult the command's script or the repo's README). For a faster inner loop
   run the targeted package/module first, but the validation gate gates the PR.
3. **Re-confirm the symptom is gone** on the real path and capture the evidence
   (new test name + relevant output) for the PR body and the task record.
4. **For a user-facing change, you MUST validate it visually with computer use —
   this is not optional.** If the change has an observable UI effect (per
   `factory-verification`), additionally exercise it through the running UI with
   the **computer use** tool
   and **capture before/after screenshots** of the rendered surface. Factory
   child runs are dispatched **with computer use enabled**, so "the tool wasn't
available" is not a valid reason to skip this.
  Follow the exact mechanics in `factory-ui-verification` (§ How to capture):
  **(1)** start the application server in the background before the session —
  run the target repo's `app_start_command` and use its `app_url` (both from
  the repo's `target_repos` entry in `foreman/config.json`; when unset, derive
  the startup command from the repo's README); **(2)** do **not** install or
  configure a browser manually —
  use the `computer_use` tool directly, which provides a pre-configured GUI
  desktop environment with a browser available; **(3)** inside the session, save
  each key UI state with `scrot -o /tmp/screenshot_<label>.png` — the tool lets
  the subagent see the screen but does **not** return files to the calling agent;
  if the session ends without screenshot files at the expected paths, the proof was
  not saved — re-run the session; **(4)** after the session, upload the saved files
  via `gh release create` on the target repo and embed the resulting GitHub release
  download URLs as markdown images (`![caption](url)`) in both the PR body and the
  task record. A textual description of what the subagent observed is **not**
  sufficient visual proof — the reviewer cannot see your description as an image.
  **Attach that proof to the
  task's record now** — embed the screenshots in your progress update via
  `factory-tracker-ops` so the record carries the visual evidence — and
  carry the same images forward to embed in the PR body in Step 6. These
  screenshots are **attached to the task record and PR body only — never
  committed to the branch** (see Step 3). A user-facing
   change with no visual proof is **unverified**: do **not** open the PR or report
   completion claiming it is done, and do **not** quietly report success on the
   code-level checks (type-check / lint / tests) alone as if that were the whole
   validation. In the rare case the running UI genuinely cannot be exercised,
   **say so explicitly** on the task record and in the PR body and treat the
   visual proof as outstanding — never imply a user-facing change was validated
   when it was not.

If you carried a spec, treat its validation criteria as the checklist —
every criterion must pass before you open the PR.

## Step 5 — Self-review for quality and correctness

Before opening the PR, **self-review your own diff** for quality and correctness:
re-read the full change end to end, confirm it resolves the ticket (every
acceptance / spec criterion met), and check for missed edge cases, leftover debug
code, scope creep, and adherence to package conventions. Fix what you find and
re-run Step 4 if you changed behavior.

As a **pre-flight checklist**, compare the final diff against the ticket, any
spec, and the target repo's local conventions. Resolve mismatches before
opening the PR; if the ticket/spec is ambiguous, record the blocker instead of
guessing.

## Step 6 — Open or update the PR with the metadata block

**Reuse the spec PR when one exists (the normal spec path).** Push your
implementation commits to the spec branch you checked out in Step 1 — the draft
PR already exists and already carries the PR↔task metadata block (stamped by the
spec phase), so **do not open a second PR**. The spec phase opened it with a
spec-marked title (e.g. `Spec: <title>`); now that the code is added you **must
update both the PR title and the PR description** to describe the shipped change:
- **Title** — rewrite it from the `Spec:` placeholder to a normal PR title for the
  implemented change (drop the `Spec:` prefix), via
  `gh pr edit <pr> --repo <task's target repo> --title "<new title>"`.
- **Description** — rewrite the body to describe the full change now that code is
  added — the bug, the root cause, the fix, and how it was verified (test name +
  the validation gate, or skip category + rationale + the validation gate for
  testing-exempt changes) — keeping the metadata block line and a visible
  **Originating thread** line linking back to where the request came from (the
  originating conversation/thread, e.g. the Slack thread) when one is available
  (see `factory-github-ops` PR body contents).
- **Ready** — mark the PR **ready for review**
  (`gh pr ready <pr> --repo <task's target repo>`) now that it carries the code. The
  spec phase kept it a draft only to hold the spec-approval gate, so promoting it
  is the spec→implement handoff (see `factory-github-ops`, Draft vs ready).

**Open the PR yourself only when there is no spec PR** (an obvious spec-skipped
fix, or a bare prompt). Build the metadata block and open the PR **ready for
review** (no `--draft`) with `gh`, against the target repo's `base_branch`
(from its `target_repos` entry), with a body covering the same points plus the
metadata block line. The `source` is always `factory-agent`:

```bash
scripts/factory-pr-meta build --task-id <key> --task-source <jira|github|prompt> \
  --task-url <url> --oz-run-id <run_id> --repo <task's target repo> --pr-url <url>
```

**For a user-facing change, embed the screenshots / visual proof** captured in
Step 4 in the PR body (the same proof posted to the task) by
uploading/referencing the images in the body — **not** by committing them to the
branch (see Step 3) — so the reviewer sees the validated behavior without
re-running anything — per `factory-verification`. Confirm the diff contains only
the source, test, and committed-spec files (no testing or verification
artifacts) before the PR goes ready for review. Include the co-author trailer
per `factory-github-ops`. Whether you reused or
opened the PR, run
`scripts/factory-pr-meta verify --pr <pr> --repo <task's target repo>`
to confirm exactly one valid block is present. Repeat per artifact when the work
produced more than one PR.

## Step 7 — Assign the reviewer, link the PR, and record completion signals

**Assign the requester as reviewer (non-optional, at PR-open).** Every PR the
factory opens carries the task requester as a reviewer, so the requester never
has to assign the PR to themselves. Resolve the requester to a GitHub handle and
assign them (see `factory-github-ops`):

```bash
scripts/factory-resolve-reviewer [--user <id>] [--email <email>] --repo <task's target repo>
gh pr edit <pr> --repo <task's target repo> --add-reviewer <handle>
```

If it resolves nothing (it never guesses), ask the requester for their GitHub
username **in the task's conversation channel** (per the door-dependent doctrine
and **Who can post where** in `factory-tracker-ops`, written for a stranger —
via a `RELAY:` message to the foreman on a Slack-door task, or a Jira comment
you post on a Jira-door task), then end your turn and assign on resume.

**Don't duplicate the assignment on the shared spec PR.** When you reused the
spec phase's PR (Step 1), the spec phase already assigned the requester at
PR-open. Check the PR's reviewers via `scripts/factory-pr-meta find` and call
`gh pr edit --add-reviewer` only when the requester is absent, so the final PR
carries them exactly once. When you opened your own PR (the spec was skipped),
you are the sole assigner — assign at open.

**Parallel-mode exception.** If your brief contains **Parallel-mode instructions**
designating you as one of N parallel agents for this ticket: all agents share one
PR branch as specified in your brief. Implement only your assigned subtask scope
(your designated files). When your code is ready: (1) `git pull --rebase origin
factory/<slug>` to incorporate any prior commits from sibling agents, (2) commit
your changes with a descriptive message identifying your subtask, (3) `git push
origin factory/<slug>` (if the push is rejected because another agent pushed first,
pull --rebase and retry — since each agent owns different files, rebase conflicts
are not expected). If you are agent 1, create the branch on your first push and
open the draft PR. When done, message the foreman (per the coordination footer)
with: your commit SHA(s), the PR link (agent 1 only), what changed, and validation
results — then **end your turn**. Do NOT apply `impl-done`, do NOT attach the PR
to the ticket, and do NOT post a completion comment on the ticket; the foreman
applies unified completion signals after all parallel agents finish. If your subtask
is incomplete, message the foreman with the blocking reason instead and end. The
parallel-mode instructions override the coordination footer's instruction to apply
the pipeline gate label.

**Set the ticket's implementation completion signals — complete or incomplete:**
- **Complete** — the change is implemented and one or more PRs are open and
  linked. Record the PR link(s) on the ticket, set/keep the lifecycle status
  **In Progress**, apply `impl-done`, and **remove** `spec-done` and `blocked`
  (if present). Post a substantive PR-ready notification (full detail, not terse)
  tagging the requester: the PR link(s), what changed, and how it was verified.
  Complete all label/status/artifact/report requirements:
  - **If this is a `blocked` rework re-entry**: before applying the label,
    resolve the PR review threads you addressed in this cycle (see
    `factory-github-ops`). Pass only the thread IDs for action-oriented comments
    where the requested code change was **actually implemented** — do **not** pass
    threads for declined requests, discussion/question threads, or threads you did
    not address (all stay open for the reviewer to close):
    ```bash
    REWORK_SHA=$(git rev-parse HEAD)
    scripts/factory-resolve-threads --repo <owner/repo> --pr <number> \\
      --thread-ids <id1,id2,...> --rework-cycle <N> --commit-sha "$REWORK_SHA"
    ```
    where `--thread-ids` is the comma-separated list of GraphQL thread node IDs
    collected in Step 0, `--rework-cycle` is the `review_rework_attempts` count
    returned by `bump-review-attempt` at the start of this step, and
    `--commit-sha` is the HEAD SHA of the rework push (use `--commit-url` instead
    if you already have the full URL). Each resolved thread receives a reply
    `[addressed on rework # N](https://github.com/<owner>/<repo>/commit/<sha>)`
    so reviewers can jump directly to the commit.
  1. **Link the PR and apply `impl-done`** (removing `spec-done` / `blocked`)
     while the ticket status is **In Progress**. These are the durable
     implementation completion signals. Never leave the step "done" without the
     PR link, status, and label.
  2. **Report completion to the foreman** (per the coordination footer): send it
     a brief completion message — the PR link(s) + status **In Progress** + what
     changed + how it was verified, and the applied label (`impl-done`). **On a
     `blocked` rework re-entry, state in that report which action-oriented
     comments were implemented (resolved), which were declined (replied to, left
     open), and which discussion/question comments received a researched reply
     (left open)** (per Step 0). If
     agent-to-agent messaging is unavailable, just end; the ticket signals remain
     the durable completion record.
- **Incomplete** — you could not finish (underspecified/ambiguous spec, an
  unresolved reviewer, an unavailable toolchain, or another blocker). Note the
  blocking issue on the ticket tagging the requester, report the blocker to the
  foreman, keep the ticket out of review (leave `spec-done` so it remains
  implementation-owned; do not add `blocked`, which is reserved for review-rework
  state), and leave the lifecycle status at **In Progress**. Do not claim
  completion.

**End your turn.** Future follow-ups are foreman-owned. If this same
implementation run is resumed, re-read the ticket/PR state from Step 0 and act
only when it is still implementation-owned.
