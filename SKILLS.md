# Skills catalog

Discoverability index of every skill in this repo: which agent owns it, its
primary use case, and a one-line description. Each agent sees its own
`.agents/skills/` plus the cross-cutting root `.agents/skills/`; skills
resolve each other by name.

Grouped by owner. Path is the skill's `SKILL.md`.

Note for readers porting from the internal Warp factory: there is **no**
`factory-linear-ops` here (tracker mechanics live in the provider-agnostic
`factory-tracker-ops`, default provider Jira) and **no**
`factory-slack-progress` (it depended on unreleased platform features; this
template is stable-only).

## Shared skills — `.agents/skills/` (every agent defers to these)

| Skill | Primary use case | Description |
| --- | --- | --- |
| `factory-tracker-ops` | Task tracking, comms, ticket mandate & pipeline labels | The ticket is mandatory: ensure-ticket (use a provided/found ticket, else create one), define the **pipeline gate labels + per-step gating mechanics + completion signals**, file a Jira issue (project routing + issue type + story-point estimate), read/update the record, comment (Slack-door only, never soliciting replies), set lifecycle status through the config `status_map`, resolve requester identity, and apply the **record-vs-conversation doctrine** (Slack-triggered runs converse in the thread with the ticket record-only; Jira-triggered runs converse via the Warp app mirroring the foreman's responses onto the ticket — no service-account comments there; every gate ask carries the ticket key and what a valid reply looks like) — all via the `scripts/tracker` CLI (default provider `jira`). This shared skill defines ticket mechanics only; the foreman decides workflow ordering. (`.agents/skills/factory-tracker-ops/SKILL.md`) |
| `factory-github-ops` | GitHub / PR mechanics | PR conventions per track, find a task's PR, detect merged state, assign/replace reviewers, map requester → GitHub handle, and resolve PR review threads after a rework — through the provider-agnostic `scripts/forge` seam (default `github`). (`.agents/skills/factory-github-ops/SKILL.md`) |
| `factory-progress-updates` | Progress reporting | Keep one live status comment for multi-step work on Slack-door tasks (no service-account comments on Jira-door tasks — progress flows through the foreman's conversation); keep plain updates terse while specs and PR notifications stay full-detail. (`.agents/skills/factory-progress-updates/SKILL.md`) |
| `factory-verification` | Fix verification (mandatory) | Verify changes against the task's target repo: a backend/headless change in code — reproduce, add a failing→passing regression test per the target repo's `test_guidance`, gate on its `validate_command` (both from its `target_repos` entry; no UI / `computer_use`); user-facing changes **also** require computer-use screenshot proof attached to the task and the PR. (`.agents/skills/factory-verification/SKILL.md`) |
| `factory-ui-verification` | UI proof | Capture screenshots or video for user-facing changes, validate the proof against the approved ticket spec / acceptance criteria, and attach it to the task record and PR body without committing media. (`.agents/skills/factory-ui-verification/SKILL.md`) |
| `complete` | Close the loop | On merge set the ticket Done + post the wrap-up; on close-without-merge set Canceled. (`.agents/skills/complete/SKILL.md`) |
| `factory-self-improvement` | In-conversation self-improvement dispatch | When a user, mid-conversation, asks a factory agent to change its own behaviour, classify conversation-only (apply just for this run, no edit) vs. structural/durable (a going-forward change), and for a structural change dispatch a background sub-agent that runs `factory-self-update` and reports back discreetly in the same thread — so the current task is never interrupted. (`.agents/skills/factory-self-improvement/SKILL.md`) |

## Foreman agent — `foreman/.agents/skills/`

| Skill | Primary use case | Description |
| --- | --- | --- |
| `factory-foreman` | Orchestrator entry | Run FIRST on every request the foreman receives: ensure a ticket exists, route by the ticket's pipeline gate label (label gating wins; `triage-done`→spec, `spec-done`→implementation, `impl-done`→code-review, merge→`complete`; no ticket or no label→triage), verify completion with the label plus status/artifact/estimate signals, dispatch one child Oz step via the `run_agents` tool (payload resolved by `scripts/factory-dispatch`), **wait** for the child's completion message, post the step result + artifacts, then **auto-advance to the next step by default** (triage→spec, triage→implement when triage skips the spec, spec→implement on approval — or immediately when `spec_approval_required` is false — implement→review, review rework up to 3 cycles). Blocks on a human only at the final merge (the factory never merges), the spec approval when required, and incidental pauses. Never does the downstream work itself. (`foreman/.agents/skills/factory-foreman/SKILL.md`) |

## Triage agent — `triage/.agents/skills/`

| Skill | Primary use case | Description |
| --- | --- | --- |
| `factory-triage` | Triage entry | Run FIRST on every triage task: derive state, classify, choose the target repo (matching the request against the config `target_repos` descriptions, falling back to `default_target_repo`, and recording the choice on the ticket), file/enrich a Jira issue (project routing + issue type), reproduce **non-trivial** bugs, assess complexity/size, then set status **Todo**, set the story-point estimate, apply triage's completion label (`spec-done` or `triage-done`), report to the foreman, and end. (`triage/.agents/skills/factory-triage/SKILL.md`) |
| `evaluate-complexity` | Triage complexity decision | Judge obvious-and-safe vs non-obvious by root-cause certainty, blast radius, ambiguity, and size; output the completion label triage should apply (`spec-done` or `triage-done`) plus the story-point estimate (XS=1, S=2, M=3, L=5, XL=8). (`triage/.agents/skills/evaluate-complexity/SKILL.md`) |

## Spec agent — `spec/.agents/skills/`

| Skill | Primary use case | Description |
| --- | --- | --- |
| `factory-spec` | Spec entry + writer | Run FIRST on every spec task: gate on `triage-done`, read the ticket's state + estimate, write the spec directly, scale it to the work (a light fix spec for small/obvious changes, a fuller product + tech spec for larger ones), commit it to a draft PR (one markdown file under `agents/specs/` named `<ticket-key>: <very brief title>.md`, returning the PR link), record the spec PR link on the ticket, drive approval from the conversation (skipped when the config `spec_approval_required` is false), apply `spec-done`, report to the foreman with the spec PR link, and end. GitHub is the source of truth for the committed spec, and the same PR/branch is reused for implementation. (`spec/.agents/skills/factory-spec/SKILL.md`) |

## Implementation agent — `implementation/.agents/skills/`

| Skill | Primary use case | Description |
| --- | --- | --- |
| `factory-implement` | Resolve a ticket with code artifacts | Establish the ticket, gate on `spec-done` or `blocked` (read review feedback when `blocked`); reuse the spec phase's draft PR — check out its branch and read the committed spec as the source of truth — or open a PR when the spec was skipped; read the task's target repo for context, mark **In Progress**, implement with incremental commits + tests, self-review, validate (a regression test per the target repo's `test_guidance` + its `validate_command`, both from its `target_repos` entry, plus computer-use screenshot proof for user-facing changes), update the shared PR's title + description (or open one when spec-skipped), assign the requester, link the PR on the ticket, keep status **In Progress**, and complete by applying `impl-done` or recording an incomplete blocker. (`implementation/.agents/skills/factory-implement/SKILL.md`) |
| `fix-failing-ci` | CI repair | Fix a red CI suite on an existing factory PR branch, re-run the target repo's `validate_command`, push, bump the per-PR attempt counter (cap 3). (`implementation/.agents/skills/fix-failing-ci/SKILL.md`) |
| `factory-self-update` | Self-skill changes | Ship a change to this factory playbook repo as its own PR: pre-confirm summary, `scripts/check`, draft PR, protected-script guardrails. (`implementation/.agents/skills/factory-self-update/SKILL.md`) |

## Code-review agent — `code-review/.agents/skills/`

| Skill | Primary use case | Description |
| --- | --- | --- |
| `factory-review` | Review entry | Run FIRST on every review task: gate on `impl-done` (ensure-ticket — search, ask the user, else create), review the PR (CI/build/tests + the rubric, folding in a spec check), then record the PR/review links, set status **In Review**, and set the ticket's review outcome via `review-done` (accepted) or `blocked` (rejected); also redirect the review or no-op. (`code-review/.agents/skills/factory-review/SKILL.md`) |
| `review-pr` | PR change review | Gate on CI/build/tests, then review the change across the rubric (correctness, standards, complexity, naming, comments, tests, security) + spec alignment, and post one structured GitHub review: inline comments + a final summary with an accepted/rejected verdict. Never merges. (`code-review/.agents/skills/review-pr/SKILL.md`) |
| `check-impl-against-spec` | Spec-alignment check | Supplement `review-pr` with material mismatches against an approved or repo spec context. (`code-review/.agents/skills/check-impl-against-spec/SKILL.md`) |
| `manage-review-reassignment` | Reassign reviewer | Redirect a factory PR's review to another person and notify the task's record. (`code-review/.agents/skills/manage-review-reassignment/SKILL.md`) |
