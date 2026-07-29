# factory-agents template

A customer-ready "software factory": specialized Oz cloud agents that run an
autonomous or semi-autonomous change loop against **your** repo and **your**
Jira. A parent **foreman** owns workflow ordering and routes each incoming
request to one of four single-purpose step agents — **triage**, **spec**,
**implementation**, and **code-review** — each with its own skills and config.
The step agents are intentionally independent: each knows only its own gate,
work product, completion signals, and how to report back to the foreman.
Together they drive a change request — a bug to fix *or* a feature/enhancement
to build, at any size — from request to merged PR in the right target repo
(chosen from the `target_repos` map in `foreman/config.json`), keeping the
ticket updated at every step.

The factory uses **Jira** as the issue tracker, **GitHub** as the code forge,
and **Slack or Jira** as the conversation channel, depending on which door a
request came in through (see "The record vs. the conversation" below).

The loop is **task-driven, not chat-driven**, and **every actionable request
runs against a tracker ticket** — there is no ticketless mode. A request can
arrive from a Slack message, a Jira issue, or a direct prompt; **every** agent
(the foreman included) first ensures a ticket exists — adopting a provided or
found one, or creating it with the right description, pipeline gate label,
status, estimate, and artifacts for the step that agent is on — then reads and
updates it through the `scripts/tracker` CLI (default provider `jira`; auth via
the `$JIRA_BASE_URL` / `$JIRA_EMAIL` / `$JIRA_API_TOKEN` environment variables,
never stored in config). The ticket's **pipeline label + status/artifact/
estimate signals** are durable workflow signals; only the foreman interprets
them to decide ordering and auto-advance behavior. The only requests exempt are
non-requests (a bare greeting / no actionable ask).

This repo is a portable, public **template** derived from Warp's internal
factory. Adoption flow: create your copy with GitHub's "Use this template",
run `scripts/factory-init` to fill in the configs, connect the Slack and Jira
doors, and do one dry run — `SETUP.md` is the full checklist. It depends only
on **stable, released** platform features: dispatch is plain `run_agents`
payload composition, and there are no unreleased-integration hooks in any
script or skill. Extensibility lives behind two provider seams:
`scripts/tracker` (issue tracking; default `jira`) and `scripts/forge` (code
forge; default `github`) — to target a different tracker or forge, add a
provider script mirroring the existing command surface and select it via
`--provider` / the `FACTORY_*_PROVIDER` env vars.

## Layout

```
factory-agents-template/
  scripts/                       # shared deterministic mechanics (stdlib Python 3)
  .agents/skills/                # cross-agent shared skills
  foreman/          { AGENTS.md, config.json, .agents/skills/ }
  triage/           { AGENTS.md, config.json, .agents/skills/ }
  spec/             { AGENTS.md, config.json, .agents/skills/ }
  implementation/   { AGENTS.md, config.json, .agents/skills/ }
  code-review/      { AGENTS.md, config.json, .agents/skills/ }
  evals/            # eval harness docs + results (see evals/README.md)
  tests/            # unit tests for the deterministic scripts
```

Per agent:
- `AGENTS.md` — playbook pointer (where to start).
- `config.json` — per-track dispatch config for `scripts/factory-dispatch`:
  the base skill (`agent.entrypoint_skill` + `repos.self`) and a single plain
  `model` string.
- foreman's `config.json` holds the shared run-wide configuration: the tracker
  block (provider, project routing, status map, story-points field, issue
  type) plus the multi-repo target settings every step reads (`target_repos` —
  a map of `org/repo` → per-repo `description`, `base_branch`,
  `validate_command`, `test_guidance` — and `default_target_repo`), along with
  `spec_approval_required`, `self_repo`, and `self_project`. See
  "Configuration reference" below. The shared cloud environment id is **not**
  stored here — it comes from the agent environment variable
  `$FACTORY_FOREMAN_ENV` (like the Jira credentials), so a dispatched child
  inherits the foreman's environment by default.
- Skills resolve by name, so each agent sees its own `.agents/skills/` + the
  root `.agents/skills/`. Each step has exactly one main entry skill
  (`factory-triage`, `factory-spec`, `factory-implement`, or `factory-review`)
  plus any helper skills dedicated to that step; shared skills provide
  mechanics only and do not decide workflow ordering.

## Agents

- **foreman** — parent **orchestrator** and entry point. Ensures a ticket
  exists (adopts a provided/found one, else creates a skeleton — triage seeds
  the first gate label), routes by the ticket's gate label, and dispatches
  **one child Oz run** for that step by calling the **`run_agents` tool** with
  the payload `scripts/factory-dispatch` resolves (the track's skill/model
  inline + a coordination footer, passing the ticket down). It then **waits**
  for the child to report completion, posts the **step result** (artifacts +
  the child's Oz run link), and **auto-advances to the next step by default**.
  It blocks on a human only at the final merge (the factory never merges), the
  spec-approval pause (when `spec_approval_required` is true), and incidental
  pauses (a clarifying question or an exhausted rework budget). It never does
  the downstream work itself. Skill: `factory-foreman`.
- **triage** — owns triage only. Reads the task + PR state, classifies the
  report, **chooses the target repo** (matching the request against the
  `target_repos` descriptions, falling back to `default_target_repo`, and
  recording the choice on the ticket), files/enriches the Jira ticket,
  reproduces **non-trivial** bugs,
  evaluates complexity, then applies triage's completion label (`spec-done` or
  `triage-done`), sets status **Todo**, records the story-point estimate,
  reports to the foreman, and ends.
  Skills: `factory-triage`, `evaluate-complexity`.
- **spec** — owns spec writing only. Gates on `triage-done`, reads state,
  takes ownership, writes the spec directly, scales the spec's depth to the
  work (a light fix spec for small changes, a fuller product + tech spec for
  larger ones), **commits it to a draft PR** (one markdown file under
  `agents/specs/` named `<ticket-key>: <very brief title>.md`, returning the
  PR link), records the spec PR link on the ticket, gets approval from the
  conversation (skipped when `spec_approval_required` is false), applies
  `spec-done`, reports to the foreman, and ends. GitHub is the source of truth
  for the committed spec, and the same PR/branch is reused by implementation.
  Skills: `factory-spec`.
- **implementation** — owns code artifacts only. Gates on `spec-done` or
  `blocked`, **reuses the spec's draft PR** (checking out its branch and
  reading the committed spec as the source of truth) or opens one when the
  spec was skipped, implements the ticket in the task's target repo, validates
  (that repo's `validate_command` + a regression test per its
  `test_guidance`), updates the shared PR's title + description (or opens the
  PR when spec-skipped), applies `impl-done`, records the PR link while
  keeping status **In Progress**, reports to the foreman, and keeps CI green;
  also ships self-skill changes.
  Skills: `factory-implement`, `fix-failing-ci`, `factory-self-update`.
- **code-review** — owns review only. Gates on `impl-done`, gates on
  CI/build/tests, reviews a PR across the rubric (correctness, standards,
  complexity, naming, comments, tests, security) + spec alignment, posts one
  structured GitHub review with inline comments + an accepted/rejected
  verdict, applies `review-done` (accepted) or `blocked` (rejected), records
  the PR/review links with status **In Review**, reports to the foreman, and
  can redirect the review.
  Skills: `factory-review`, `review-pr`, `check-impl-against-spec`,
  `manage-review-reassignment`.

See `SKILLS.md` for the full skills catalog.

## The loop

The **foreman orchestrates** the loop one gated step at a time: it routes by
the ticket's gate label, dispatches a child step, waits for that child to
report completion, posts the step result, then **auto-advances to the next
step by default** (`triage → spec`, `triage → implement` when triage skips the
spec, `spec → implement` after spec approval, `implement → review`, and
review-rejected rework up to **3** cycles). **Every inter-step hop
auto-advances — the move into implementation included**, whether a spec was
written and approved or triage judged the fix obvious and skipped it (no user
approval gate before implementation). The loop blocks on a human only at the
final merge, the spec approval (when required), and incidental pauses. With
**no** ticket it starts at triage; with one it picks up the step the gate
label dictates (label gating wins).

```
request (Slack / Jira / direct prompt)
   ─▶ foreman ─(route by gate label; no ticket/label ─▶ triage)─▶ one step
   ◀─ step result + artifacts; auto-advances to the next step by default

triage ──┬─ unclear ──────────▶ ask in the conversation, END
         ├─ obvious & safe ────▶ label `spec-done`   (spec skipped; auto ─▶ implementation)
         ├─ self-skills ───────▶ label `spec-done`   (auto ─▶ implementation)
         └─ non-obvious ───────▶ label `triage-done` (auto ─▶ spec)
spec ─▶ commit spec to draft PR ─▶ approved ─▶ label `spec-done` (auto ─▶ implementation, reusing the same PR)
        (when `spec_approval_required` is false the approval pause is skipped:
         the committed spec advances straight into implementation)
implementation ─▶ code added to the spec PR (or a new PR if spec skipped) ─▶ label `impl-done` (In Progress)
              ─▶ CI red ─▶ fix-failing-ci (cap 3)
code-review ─▶ pass ─▶ label `review-done` (In Review)
            ─▶ fail ─▶ label `blocked` (In Review; auto ─▶ implementation rework, cap 3)
merge (by a human) ─▶ complete (Done + final message)

Gate labels (each describes the last completed step; exactly one active at a time):
  `triage-done` ▶ `spec-done` ▶ `impl-done` ▶ `review-done`
  (review fail ▶ `blocked` ▶ back to implementation rework)
Factory lifecycle states (mirrored to the Jira issue through the
`tracker.status_map` in `foreman/config.json`, which maps each state to your
workflow's real status name):
  Triage ─▶ Todo ─▶ In Progress ─▶ In Review ─▶ Done
       └─ Canceled (aborted / no real work)
Estimate: story points (XS=1, S=2, M=3, L=5, XL=8), written to the Jira
story-points field configured as `tracker.story_points_field`.
Step companion signals:
  triage: Todo + estimate
  spec: spec PR link + approval from the conversation
  implementation: PR linked + In Progress
  review: PR/review linked + In Review
```

The rework loop runs automatically up to a **maximum of 3** cycles, gated on
the PR's `review_rework_attempts` counter; past that the PR is handed to a
human. Each step records its artifacts on the ticket and messages the foreman
on completion; the gate label plus companion status/artifact/estimate signals
are the durable source of truth.

## The record vs. the conversation

The ticket is always the **durable record** (description, estimate, spec PR
link, progress, artifacts, status, gate labels). The **conversation** — where
the factory asks questions, requests approvals, and announces results — is
determined by which door the request came through:

- **Slack-triggered runs** converse in the Slack thread. Asks, approvals, and
  the merge request go to the thread; the Jira ticket stays **record-only**.
  Ticket comments never wake a Slack-originated run, so when an agent posts a
  record-keeping comment on the ticket it includes a one-line pointer to the
  live Slack thread where the conversation is actually happening. **Only the
  foreman run can post to the Slack thread** — child steps deliver any
  thread-bound ask (a clarifying question, spec approval) to the foreman as a
  `RELAY:` message; the foreman posts it verbatim and forwards the human's
  reply back to the paused child (see "Who can post where" in
  `factory-tracker-ops`).
- **Jira-triggered runs** treat the ticket **as** the conversation: asks are
  posted as Jira comments, and a reply on the ticket wakes (or cold-starts)
  the run.

Every gate ask is **written for a stranger**: it carries the ticket key,
enough context to act without the thread's history, and a description of what
a valid reply looks like. This matters because a reply may arrive long after
the original run ended and **cold-start a fresh run** that re-derives all
state from the durable ticket (gate label, status, artifacts) rather than from
conversation memory.

## Scripts (`scripts/`)

Python 3 stdlib-only helpers that own the deterministic mechanics so skills
call one command instead of hand-assembling API/`gh` calls. Every script is
executable, supports `--help`, emits facts as JSON to stdout, and fails loud
(nonzero exit + stderr).

- `tracker` — provider-agnostic issue-tracking CLI and the single seam every
  skill uses for ticket operations. It accepts `--provider` (default `jira`)
  and `FACTORY_TRACKER_PROVIDER`, then delegates all subcommands unchanged to
  the configured provider script (`jira` or `mock-issue-tracker`).
- `jira` — the default Jira provider, over the Jira Cloud REST API:
  `create-issue`, `comment`, `list-labels`, `search-issues`, `get-issue`,
  `update-issue`. Status changes go through the Jira **transitions** API using
  the status names from `tracker.status_map` (a status must be reachable via a
  workflow transition to be set); the story-point estimate is written to the
  custom field configured as `tracker.story_points_field`; markdown bodies are
  converted to ADF (Atlassian Document Format) for descriptions and comments;
  and PR links are attached to the issue as **remote links**. Auth is env-only:
  `$JIRA_BASE_URL`, `$JIRA_EMAIL`, `$JIRA_API_TOKEN`.
- `mock-issue-tracker` — an **in-memory mock provider** for the `tracker`
  seam, used by the eval harness (`scripts/factory-eval`) and for smoke tests.
  It mirrors the real provider's subcommands, flags, and JSON output shapes
  but needs no network and no Jira credentials, **always succeeds**, and keeps
  issues in a local JSON store so a `create-issue` is readable by a later
  `get-issue`/`update-issue`/`search-issues` within the same environment.
  Select it with `--provider mock-issue-tracker` or
  `FACTORY_TRACKER_PROVIDER=mock-issue-tracker`; the store path is
  `$FACTORY_MOCK_TRACKER_STORE` (else a file under the system temp dir). Not
  for real work.
- `forge` — provider-agnostic **code-forge** CLI. It accepts `--provider`
  (default `github`) and `FACTORY_FORGE_PROVIDER`, then delegates all
  subcommands to the configured provider script.
- `github` — the GitHub provider for the `forge` seam. Wraps
  `scripts/factory-pr-meta` (`build`, `find`, `verify`, `merged`,
  `bump-ci-attempt`, `bump-review-attempt`, `read`) and
  `scripts/factory-resolve-threads` (`resolve-threads`) unchanged, exposing a
  unified CLI surface.
- `mock-code-forge` — an **in-memory mock provider** for the `forge` seam
  (evals/smoke tests only). Mirrors the GitHub provider's command surface,
  needs no network and no `gh`, **always succeeds**, and keeps PR metadata in
  a local JSON store (`$FACTORY_MOCK_FORGE_STORE`, else a temp-dir file).
  Select it with `--provider mock-code-forge` or
  `FACTORY_FORGE_PROVIDER=mock-code-forge`. Not for real work.
- `factory-pr-meta` — PR↔task metadata block: `build`, `find`, `verify`,
  `merged`, `bump-ci-attempt`, `bump-review-attempt` (the durable
  `review_rework_attempts` counter the foreman uses to cap auto-rework at 3).
- `factory-resolve-reviewer` — task requester → GitHub handle (override map →
  email → search), with `scripts/reviewer_overrides.json` for manual
  fallbacks. Because Jira Cloud often hides user emails, seed the override map
  with your team's Jira accountId → GitHub handle entries during onboarding
  (see `SETUP.md`).
- `factory-resolve-threads` — resolve specific review threads on a PR after a
  rework; accepts `--thread-ids <id1,id2,...>`, `--rework-cycle N`, and
  `--commit-sha <sha>` / `--commit-url <url>`; posts a markdown reply linking
  the rework commit to each thread before resolving it, touching only the
  named threads; called before re-applying the `impl-done` label.
- `factory-state` — one JSON snapshot of a task's externally-mutable PR facts
  (linked PR state / merge status / reviewers); when `--repo` is omitted it
  probes every configured target repo plus `self_repo`. Tracker state is read
  through `scripts/tracker` instead.
- `factory-dispatch` — the foreman's dispatch **resolver**: resolve a track →
  its per-track config (skill derived from `agent.entrypoint_skill` +
  `repos.self`, plain `model`) + the shared environment (flag →
  `$FACTORY_FOREMAN_ENV`; unset ⇒ the child inherits the foreman's
  environment) and compose a ready-to-use **`run_agents` tool-call payload** —
  the foreman then dispatches the child by calling the `run_agents` tool with
  it (the script makes **no** API call). It prepends the track's
  `<track>/AGENTS.md` playbook as the shared `base_prompt` (missing/empty is a
  non-fatal warning), appends a coordination footer to the child prompt (the
  child messages the foreman on step completion, using the parent run id from
  `--parent-run-id` → `$CURRENT_RUN_ID` → `$OZ_RUN_ID`), names the run
  `FA_<track>_<UTC timestamp>`, enables computer use by default
  (`--no-computer-use` to opt out), and emits
  `{track, skill, model, name, environment_id, computer_use_enabled,
  parent_run_id, oz_web_origin, run_link_template, run_agents}` as JSON — the
  foreman substitutes the returned run id into `run_link_template` to build
  the child's Oz run link. Per-track overrides:
  `FACTORY_FOREMAN_<TRACK>_SKILL` / `FACTORY_FOREMAN_<TRACK>_MODEL`.
- `factory-eval` — curl-based eval harness that benchmarks a track by
  launching N Oz runs over a task list; see `evals/README.md`.
- `factory-init` — one-time bootstrap for a new copy of the template: prompts
  for every config value (or takes flags; see `--help`), autodiscovers your
  Jira workflow statuses and story-points field when the Jira env vars are
  exported (soft-failing to manual values), and writes `foreman/config.json`,
  the four track configs, and a `reviewer_overrides.json` skeleton. See
  `SETUP.md` step 1.
- `factory-validate-skills` — frontmatter lint + `git diff --check` + dangling
  cross-reference scan across every agent's skills, `AGENTS.md`, and this
  README.
- `factory-validate-config` — structural validation of `foreman/config.json`
  and the four track configs: required keys and types, cross-file
  `repos.self` / `self_repo` consistency, and the `REPLACE_ME` placeholder
  policy (a pristine template passes with warnings; a partially-configured
  repo fails).
- `check` — the validation gate: `py_compile` + `--help` smoke test over every
  script, then `factory-validate-skills` and `factory-validate-config`. Run
  it before opening a PR.

## Configuration reference

### `foreman/config.json` (shared, run-wide)

- `tracker.provider` — the issue-tracker provider for `scripts/tracker`
  (`"jira"`).
- `tracker.project_routing` — map of Jira **project key** → a plain-language
  description of the area that project owns (e.g. `"PROJ": "backend services,
  APIs, and data pipelines"`). The agent creating a ticket picks the
  best-matching project for the change.
- `tracker.default_project` — the fallback project key used when routing
  finds no clear match.
- `tracker.status_map` — maps each factory lifecycle state (`Triage`, `Todo`,
  `In Progress`, `In Review`, `Done`, `Canceled`) to the **real status name**
  in your Jira workflow. Every mapped status must exist and be reachable via
  workflow transitions (see `SETUP.md`).
- `tracker.story_points_field` — the Jira custom field id that stores story
  points (commonly `customfield_10016`; find yours per `SETUP.md`).
- `tracker.issue_type` — the Jira issue type used for factory-created tickets
  (e.g. `Task`).
- `target_repos` — a map of `org/repo` → that target repo's settings. Like
  `tracker.project_routing`, this is a thin routing table: the agent (triage)
  matches the request against each entry's `description`, picks the repo
  clearly responsible, and records the choice on the ticket; downstream steps
  use the chosen repo's entry. One task normally targets **one** repo (at most
  one PR per repo); a request spanning several repos becomes several tickets.
  Each entry has:
  - `description` — a plain-language description of what that repo owns; the
    text the routing judgment matches a request against.
  - `base_branch` — the branch PRs are opened against in that repo.
  - `validate_command` — the command implementation (and CI-fix) runs to
    validate a change in that repo (e.g. `make test`, `./scripts/ci`).
  - `test_guidance` — one line telling the implementation agent how regression
    tests are written and run in that repo (framework, location, invocation).
  - `app_start_command` (optional) — the command that boots the repo's app so
    UI verification can exercise it (used by `factory-ui-verification`); omit
    for headless repos.
  - `app_url` (optional) — the local URL the running app serves during UI
    verification (e.g. `http://localhost:8000`).
- `default_target_repo` — the fallback `org/repo` used when no `target_repos`
  entry clearly matches a request.
- `spec_approval_required` — when `true` (the default), the spec step pauses
  for a human approval in the conversation before the loop advances to
  implementation; when `false`, the committed spec auto-advances with no
  pause.
- `self_repo` — the `org/repo` of **your copy of this template**; used by
  dispatch to attach skills and by `factory-self-update` to ship changes to
  the factory itself.
- `self_project` — the Jira project key where the factory's own
  self-improvement tickets are filed.

### `<track>/config.json` (per track: triage, spec, implementation, code-review)

- `agent.entrypoint_skill` — the track's entry skill name; dispatch derives
  the repo-qualified skill spec
  `<repos.self>:<track>/.agents/skills/<entrypoint_skill>/SKILL.md`.
- `model` — a single plain model-id string for the track's child runs (e.g.
  `"auto"`); emitted as the `run_agents` `model_id`.
- `repos.self` — the `org/repo` of your copy of this template (same value in
  every track config).

## Environment prerequisites

- `$JIRA_BASE_URL` (e.g. `https://yourcompany.atlassian.net`), `$JIRA_EMAIL`,
  and `$JIRA_API_TOKEN` set so the default `scripts/tracker` Jira provider can
  read/create issues, comment, transition status, and set the estimate. A
  ticket is required at all times. Credentials live **only** in the
  environment, never in config.
- `gh` authenticated against every configured target repo and your template
  copy, with permission to open PRs and assign reviewers.
- Python 3 on PATH for `scripts/`.
- `$FACTORY_FOREMAN_ENV` optionally set to the shared cloud environment id for
  child dispatch; when unset, dispatched children inherit the foreman's
  environment.
- The foreman's child dispatch needs no API key or `curl` — it calls the
  `run_agents` tool. `curl` on PATH and `$WARP_API_KEY` set are required only
  for the curl-based eval harness (`scripts/factory-eval`).
- Every repo in `target_repos` (each at its `base_branch`) and this repo
  cloneable in the environment.

See `SETUP.md` for the full onboarding checklist.

## Validation

```bash
scripts/check
python3 -m unittest discover -s tests
```

CI (`.github/workflows/check.yml`) runs both on every push to `main` and every
pull request.

## License

A license has not been chosen yet — this template currently ships without
one; licensing is pending.
