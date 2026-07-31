# Setup

Step-by-step onboarding for a team adopting the factory. Work through the
steps in order; each one is required unless marked optional. Placeholders you
must replace are written as `<LIKE-THIS>`.

Prerequisites on the machine you run these steps from: `git`, `gh`
(authenticated), `python3`, `curl`, and the `oz` CLI.

## 1. Create your copy from the template and configure it

This repo is a GitHub **template repository**. Create your own copy (rather
than a fork — a template copy starts with clean history) and clone it:

```bash
gh repo create <YOUR-ORG>/factory-agents \
  --template warpdotdev-demos/factory-agents-template --private --clone
cd factory-agents
```

Then fill in the configs. The fast path is the bootstrap script:

```bash
scripts/factory-init
```

It prompts for every value (or takes flags — see `--help`), and when the Jira
credentials from step 2 are already exported it **autodiscovers** your
projects' real workflow status names and the story-points field id — the two
most error-prone values below. It writes `foreman/config.json`, the four track
configs, and a `scripts/reviewer_overrides.json` skeleton, and
`scripts/factory-validate-config` (run as part of `scripts/check`) verifies
the result. Steps 3–7 below explain what each value means — work through them
manually instead if you prefer, or to double-check what factory-init wrote.

Either way, the self-references must point at your copy: `repos.self` in
**each** track config — `triage/config.json`, `spec/config.json`,
`implementation/config.json`, `code-review/config.json` — and `self_repo` in
`foreman/config.json` set to `<YOUR-ORG>/factory-agents`, plus `self_project`
naming the Jira project where the factory's own self-improvement tickets are
filed.

To pull future template improvements into your copy later:

```bash
git remote add template https://github.com/warpdotdev-demos/factory-agents-template.git
git fetch template && git merge template/main
```

## 2. Set up the Jira service account, its API token, and the Oz secrets

The factory acts in Jira as a real user account: every ticket it creates,
comment it posts, status transition, estimate, and PR link is attributed to
the account behind the API token. Use a **dedicated service account** rather
than a personal one — factory activity stays clearly attributed in ticket
history and audit logs, the token survives employee offboarding, and access
can be scoped and revoked without touching anyone's personal account.

### 2a. Create (or reuse) the service account

Two ways to get one:

- **Atlassian service account (recommended).** An organization admin creates
  it at admin.atlassian.com → **Directory → Service accounts** → *Create
  service account* (e.g. `factory-agent`); the email is auto-generated. Up to
  five service accounts are free per organization. Note that service
  accounts can only create **scoped** API tokens, which authenticate at the
  cloud-ID gateway rather than the site URL — see the scoped-token note at
  the end of this step.
- **A regular Atlassian account on a dedicated mailbox** (e.g.
  `factory-agent@yourcompany.com`). Use this when an org-level service
  account isn't available; it also supports plain unscoped API tokens that
  authenticate directly against the site URL.

Whichever you pick, the account needs:

- **Product access to Jira** on your site (grant the Jira app with the User
  role; it consumes a licensed seat, and project permissions alone are not
  enough without app access).
- **Project permissions in every routed project** — every key in
  `tracker.project_routing` plus `self_project`: *Browse Projects*, *Create
  Issues*, *Edit Issues*, *Add Comments*, *Transition Issues*, and *Link
  Issues* (the factory attaches PRs as remote links). Adding the account to
  each project's default member/developer role typically covers all of
  these; verify with Jira's Permission Helper. A dedicated group (e.g.
  `factory-agent-svc`) that carries these permissions keeps auditing and
  offboarding simple.

### 2b. Create the API token with the right scopes

Create the token as the service account: admin.atlassian.com → Directory →
Service accounts → your account → **Create credentials → API token**. (For a
regular dedicated account, sign in as it and create the token at
https://id.atlassian.com/manage-profile/security/api-tokens — with or without
scopes.)

When the token is **scoped** (mandatory for service accounts, recommended
otherwise), filter the scope picker to app **Jira**, scope type **Classic**,
and grant exactly these three scopes:

- `read:jira-work` — read and search issues, projects, workflow statuses,
  and fields (get-issue, search-issues, list-labels, and factory-init's
  status / story-points autodiscovery).
- `write:jira-work` — create issues, post comments, transition status, edit
  labels and estimates, and attach PR remote links.
- `read:jira-user` — look up users by name or email (find-user, @-mention
  and reviewer resolution).

Prefer these classic scopes over their granular equivalents: Atlassian
enforces an endpoint's granular scope list all-or-nothing, so a partial
granular set fails with `Unauthorized; scope does not match`. Scopes cap what
the token may do **in addition to** the account's project permissions — an
action must be allowed by both. Tokens expire (365 days maximum, 1 year by
default) and scopes can't be edited after creation — calendar the rotation.

### 2c. Store the Oz secrets

Store the Jira credentials as Oz team secrets so cloud runs can read them as
environment variables (each command prompts for the value; the token is never
committed or placed in config):

```bash
oz secret create --team JIRA_API_TOKEN
oz secret create --team JIRA_EMAIL       # the account email the token belongs to
oz secret create --team JIRA_BASE_URL    # e.g. https://<your-company>.atlassian.net
```

For local testing, export the same three variables in your shell.

**Scoped API tokens authenticate only at the cloud-ID gateway.** A scoped
token — which includes every service-account token — is rejected at the site
URL (401). If `GET $JIRA_BASE_URL/rest/api/3/myself` returns 401 with a
token you know is valid, find your cloudId
(`curl -s https://<your-company>.atlassian.net/_edge/tenant_info`), set
`JIRA_BASE_URL=https://api.atlassian.com/ex/jira/<cloudId>`, and set
`tracker.browse_url` in `foreman/config.json` to the human site URL
(`https://<your-company>.atlassian.net`) so issue links stay clickable.

## 3. Audit your Jira workflow and fill `tracker.status_map`

The factory drives six lifecycle states: `Triage`, `Todo`, `In Progress`,
`In Review`, `Done`, `Canceled`. Map each to a **real status name** in your
Jira workflow in `foreman/config.json` → `tracker.status_map`.

List the statuses your project's issue types actually use:

```bash
curl -s -u "$JIRA_EMAIL:$JIRA_API_TOKEN" \
  "$JIRA_BASE_URL/rest/api/3/project/<PROJECT-KEY>/statuses" | python3 -m json.tool
```

Rules of thumb:

- Every value in `status_map` must be an exact status name from that list
  (case-sensitive).
- Statuses must be **reachable via workflow transitions**: Jira only moves an
  issue along defined transitions, and the provider sets status by finding a
  transition whose target matches the mapped name. If your workflow has no
  path (e.g. no transition into `Canceled` from `In Review`), factory status
  updates will fail — add the transition or map to a reachable status.
- Two factory states may map to the same Jira status (the committed default
  maps both `Triage` and `Todo` to `To Do`).

## 4. Find your story-points field id

Story points live in a Jira **custom field** whose id varies per site. Find
it:

```bash
curl -s -u "$JIRA_EMAIL:$JIRA_API_TOKEN" "$JIRA_BASE_URL/rest/api/3/field" \
  | python3 -c "import json,sys; [print(f['id'], f['name']) for f in json.load(sys.stdin) if 'story point' in f['name'].lower()]"
```

Set the resulting id (e.g. `customfield_10016`) as
`tracker.story_points_field` in `foreman/config.json`. The factory records
estimates as story points: XS=1, S=2, M=3, L=5, XL=8.

If your project has **no editable story-points field** (common for Jira Work
Management / "business" projects — verify via the issue's `editmeta`), set
`tracker.story_points_field` to `null` to disable estimates: the provider
then skips estimate writes with a warning instead of failing the API call,
and agents record the estimate in the issue body instead.

## 5. Set project routing and the issue type

In `foreman/config.json`:

- `tracker.project_routing` — one entry per Jira project the factory may file
  tickets in: `"<PROJECT-KEY>": "<plain-language description of what that
  project owns>"`. The description is what the agent matches a request
  against, so make it concrete (components, services, product areas).
- `tracker.default_project` — the project key to fall back to when no routing
  entry clearly matches.
- `tracker.issue_type` — the issue type for factory-created tickets (e.g.
  `Task`). It must exist in every routed project.

**With more than one project, use the object form and declare the repos each
project owns** (see step 6 for the repos themselves). This is the single most
important setting for a multi-team factory, because it scopes repo routing to
the owning team and keeps the routing judgment over a handful of candidates:

```json
"project_routing": {
  "PAY": {
    "description": "payments and billing — checkout, subscriptions, invoicing",
    "repos": ["acme/payments-api", "acme/billing-worker", "acme/webapp"],
    "default_repo": "acme/payments-api"
  },
  "SEARCH": {
    "description": "search and discovery — query service, indexing, ranking",
    "repos": ["acme/search-service", "acme/webapp"],
    "default_repo": "acme/search-service",
    "status_map": { "In Review": "Code Review" },
    "story_points_field": "customfield_10032",
    "issue_type": "Bug"
  }
}
```

Notes for multi-project sites:

- A repo may be owned by several projects (a shared web app is the common
  case) — list it under each.
- A project with **no** `repos` list leaves every target repo a candidate; that
  is the single-project shape, and it is what a bare description string means.
- Projects rarely share one workflow. When a project's statuses, story-points
  field, or issue type differ, override them **in that project's entry** rather
  than bending the site-wide values; `scripts/tracker` resolves the right ones
  per issue. Team-managed (next-gen) projects in particular each get their own
  story-points custom field id — re-run the step-4 lookup per project.
- Check the result with `scripts/factory-config projects` (every project with
  its repos and effective settings) and
  `scripts/factory-config repos --key <PROJECT-KEY>` (what a ticket there can
  route to). `scripts/factory-validate-config` fails on a project that
  references an unknown repo and warns about a repo no project can reach.
- Deduplication searches every routed project by default, so the service
  account needs read access in all of them (step 2).
- `foreman/config.multi-project.example.json` is a full worked example.

## 6. Point the factory at your target repos

Still in `foreman/config.json`:

- `target_repos` — one entry per repo the factory may ship changes to, keyed
  by `org/repo`. This is a thin routing table, exactly like
  `tracker.project_routing`: triage matches each request against the entries'
  descriptions and picks the repo clearly responsible (recording the choice on
  the ticket), so make each description concrete (stack, components, product
  areas). Each entry has:
  - `description` — a plain-language description of what that repo owns.
  - `base_branch` — the branch PRs are opened against in that repo (e.g.
    `main`).
  - `validate_command` — the one command that validates a change in that repo
    (build + tests + lint, e.g. `make check` or `./scripts/ci`).
    Implementation and CI-fix gate on it.
  - `test_guidance` — one line telling the implementation agent how regression
    tests are written and run in that repo (framework, directory, invocation).
  - `app_start_command` (optional) — the command that boots the repo's app so
    UI verification can exercise it (e.g. `make init && uv run manage.py
    runserver 8000`); omit for headless repos.
  - `app_url` (optional) — the local URL the app serves once started (e.g.
    `http://localhost:8000`).
  - `environment_id` (optional) — the Oz cloud environment that clones this repo
    and has its toolchain (see step 8). Set this per repo once you have more
    than a couple of repos, so each child step runs where that repo's
    `validate_command` actually works.
  - `runner_id` (optional) — the Oz runner for this repo, when its build needs
    specific compute.
- `default_target_repo` — the `org/repo` to fall back to when no entry clearly
  matches a request and the ticket's project declares no `default_repo`.
- `spec_approval_required` — keep `true` to pause for a human spec approval
  before implementation; set `false` to let approved-by-default specs
  auto-advance. Start with `true` until you trust the loop.

A single-repo setup is simply a `target_repos` map with one entry, which is
also the `default_target_repo`. `foreman/config.example.json` is a complete
worked example — a single Django app (linkding) with a fast, self-contained
gate; its `target_repos` block:

```json
"target_repos": {
  "warpdotdev-demos/linkding": {
    "description": "linkding — self-hosted bookmark manager. Python/Django backend with server-rendered templates plus a small JS/Svelte frontend (bookmarks, tags, archive, REST API, importers, UI).",
    "base_branch": "master",
    "validate_command": "make lint && make test",
    "test_guidance": "pytest on Django with SQLite (no external services); tests live in bookmarks/tests/test_*.py — add a failing-then-passing test there and run 'uv run pytest bookmarks/tests/<file> -n auto' scoped, then the full gate.",
    "app_start_command": "make init && uv run manage.py runserver 8000",
    "app_url": "http://localhost:8000"
  }
},
"default_target_repo": "warpdotdev-demos/linkding"
```

A multi-repo setup adds one entry per repo, each with its own stack-specific
gate; triage routes each request to the candidate repo whose description
matches — the candidates being the repos the ticket's Jira project owns (step
5).

At fleet scale, do not hand-write this map. Generate it from whatever already
knows ownership (a service catalog, `CODEOWNERS`, a repo manifest) and feed it
in, then onboard later additions with `--merge`:

```bash
scripts/factory-init --projects-json @projects.json \
  --target-repos-json @repos.json \
  --self-repo <YOUR-ORG>/factory-agents --self-project <PLATFORM-KEY>

scripts/factory-init --merge --self-repo <YOUR-ORG>/factory-agents \
  --project "OPS=infrastructure and deploys" \
  --project-repos "OPS=acme/terraform" \
  --target-repo acme/terraform --target-description "infra as code" \
  --target-base-branch main --target-validate-command "terraform validate" \
  --target-test-guidance "terraform test under tests/"
```

Sanity-check the routing before the dry run:

```bash
scripts/factory-config projects                       # every project + its repos
scripts/factory-config repos --key <PROJECT-KEY>      # a ticket's candidates
scripts/factory-config repo --repo <org/repo>         # gate, branch, environment
scripts/factory-validate-config                       # references + placeholders
```

Commit the config changes to your copy of the repo.

## 7. Seed `scripts/reviewer_overrides.json`

The factory resolves one person across three platforms — Slack (requests),
Jira (tickets and @-mentions), and GitHub (PR reviewers) — with a shared
email as the join key. Jira Cloud **hides most users' email addresses** by
default (a privacy setting), so the automatic email-based lookups often have
nothing to go on — this manual identity map is the reliable path.

Find a teammate's Jira **accountId** (also visible in their profile URL,
`.../jira/people/<accountId>`) with:

```bash
scripts/tracker find-user "<name-or-email>"
```

Then add one entry per teammate to both maps:

```json
{
  "overrides": {
    "<jira-accountId>": { "github": "<github-handle>", "email": "<email>" }
  },
  "slack_users": {
    "<SLACK-USER-ID>": {
      "display_name": "<name>",
      "email": "<email>",
      "jira_account_id": "<jira-accountId>",
      "github": "<github-handle>"
    }
  }
}
```

`overrides` maps a Jira user to their GitHub reviewer handle
(`scripts/factory-resolve-reviewer`); `slack_users` lets the foreman convert
Slack `<@USERID>` tokens into real Jira mentions (`[~accountid:...]`) so the
person is actually tagged and notified on the ticket.

## 8. Create the Oz cloud environment(s)

For a **small setup (one or a few repos)**, one environment is enough. Create a
cloud environment for factory runs (Oz → Environments) that:

- clones **all** the repos: every repo in `target_repos` (each on its
  `base_branch`) and your copy of this template (on `main`);
- has `gh` authenticated with permission to open PRs and assign reviewers on
  every target repo;
- uses a Docker image with `git`, `gh`, `python3`, and `curl`, plus whatever
  each target repo's `validate_command` needs (compilers, package managers);
- exposes the Jira secrets from step 2 as environment variables
  (`JIRA_BASE_URL`, `JIRA_EMAIL`, `JIRA_API_TOKEN`);
- (optional) sets `FACTORY_FOREMAN_ENV` to this environment's id, so child
  steps are always dispatched into it explicitly rather than inheriting the
  foreman's environment.

**With many repos, split it up.** One image carrying every stack becomes slow to
build, expensive to boot, and prone to toolchain conflicts. Instead:

- create **one environment per repo (or per repo family that shares a
  toolchain)**, each cloning just those repos plus your template copy, with only
  that stack's tooling and the same Jira secrets and `gh` auth;
- record each one as `environment_id` on the matching `target_repos` entry (step
  6), or as a per-project `environment_id` when a whole project shares one;
- keep a lightweight **shared** environment as `FACTORY_FOREMAN_ENV` for the
  foreman and for any step dispatched before a repo is chosen (the first triage
  dispatch);
- add `runner_id` where a repo's build needs more memory or a different OS.

The foreman passes `--repo` / `--issue` to `scripts/factory-dispatch`, which
resolves the repo's environment first, then the project's, then
`$FACTORY_FOREMAN_ENV`. Verify a repo resolves the way you expect:

```bash
scripts/factory-dispatch --track implementation --prompt probe \
  --parent-run-id probe --repo <org/repo> \
  | python3 -c "import json,sys; d=json.load(sys.stdin); print(d['environment_id'], d['environment_source'])"
```

## 9. Connect the Slack door

Connect the Slack integration in your Oz workspace settings and create the
factory's Slack-facing agent with the **foreman skill as the integration's
base prompt**, referencing it repo-qualified:

```
<YOUR-ORG>/factory-agents-template:foreman/.agents/skills/factory-foreman/SKILL.md
```

Point the integration at the **shared** environment from step 8 (the foreman's
own environment; child steps move themselves into each repo's environment).
Requests that arrive via Slack converse in the Slack thread; the Jira ticket
stays record-only (see "The record vs. the conversation" in `README.md`).

## 10. Connect the Jira door

Connect the Jira integration as the second door, using the same foreman base
prompt and environment. Runs triggered from Jira treat the ticket as the
conversation: the factory posts asks as Jira comments and a reply on the
ticket wakes (or cold-starts) a run that picks up from the ticket's durable
state.

## 11. Smoke-test with the mock providers

Verify the mechanics without touching real Jira or GitHub. The mock providers
mirror the real command surfaces, always succeed, and keep state in local
JSON stores:

```bash
# Validate the repo itself:
scripts/check

# Exercise the tracker seam against the mock:
FACTORY_TRACKER_PROVIDER=mock-issue-tracker scripts/tracker get-issue --help

# Drive a full eval run against both mocks (needs $WARP_API_KEY; see evals/README.md):
FACTORY_TRACKER_PROVIDER=mock-issue-tracker \
FACTORY_FORGE_PROVIDER=mock-code-forge \
scripts/factory-eval --track triage --runs 1 --prompt "Users report the settings page 500s when the profile has no avatar."
```

For the launched cloud runs to use the mocks, set both `FACTORY_*_PROVIDER`
variables in the run environment (e.g. the eval environment's variables).

## 12. Real dry run

Finally, run one low-stakes request end to end against real providers:

1. Pick (or file) a small, well-understood ticket in a routed Jira project. With
   several projects configured, do this once per project — each one exercises
   its own status map, story-points field, and repo subset.
2. Trigger the factory through one door — mention it in Slack with the ticket
   key, or comment on the Jira ticket.
3. Watch the loop: triage → (spec) → implementation → review. Confirm the
   ticket's gate labels, status transitions, story-point estimate, recorded
   target repo (the `Target repo: <org/repo>` line), and PR remote link all
   appear in Jira, and that the PR opens in the recorded target repo against
   that repo's `base_branch`. On a multi-project setup, also confirm the
   recorded target repo is one that ticket's project **owns** (compare against
   `scripts/factory-config repos --issue <TICKET-KEY>`) — a repo from another
   project's list means the project descriptions overlap and need sharpening.
4. Approve the spec if asked, and merge the PR yourself — the factory never
   merges. On merge, the ticket should move to Done with a closing comment.
