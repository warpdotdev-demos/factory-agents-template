# evals

Local harness to benchmark a factory track's agent (skill + model) by
launching N Oz runs over a per-track task list and recording normalized
performance/cost results to CSV.

The recommended way to run evals is against the **mock providers**
(`mock-issue-tracker` for the tracker seam, `mock-code-forge` for the forge
seam), so the full pipeline can be exercised **without touching real Jira or
GitHub state** — no real tickets, no real PRs. See "Mock providers" below.

## Layout

```
evals/
  tasks/     <track>.jsonl   # starter task lists (generic examples)
  results/   <track>.csv     # written by scripts/factory-eval (rows appended per run)
  results/viewer.html        # open locally to browse the results CSVs
```

Starter task files are committed at `evals/tasks/<track>.jsonl` as **generic
examples** — replace them with tasks written for your own repos (the
code-review examples need a real PR URL, or a mock-forge PR id, substituted
in). You can also supply tasks per run via `--prompt` (inline) or
`--tasks-file <path>` pointing at a local JSONL file you author. Each line is
a JSON object: `{"id": ..., "prompt": ...}`.

Tracks: `triage`, `spec`, `implementation`, `code-review`. Each track's task
list is authored to that track's entry gate:

- **triage** — a raw bug/feature request. Expected artifact: a **tracker
  issue** (no PR). With several Jira projects and many repos configured,
  **routing accuracy is the main quality risk**, so include tasks that should
  land in a specific `(project, repo)` pair — especially near-miss wording that
  could plausibly match a neighbouring team's repo description — and grade the
  run on the ticket's project and its recorded `Target repo` line. Compare a
  task's expected repo against
  `scripts/factory-config repos --key <PROJECT-KEY>`; a routing miss usually
  means two `description` fields overlap and need sharpening, not that the agent
  misbehaved.
- **spec** — a change that needs a written spec.
- **implementation** — an obvious fix or an approved spec. Expected artifact:
  a **PR** (with a metadata-linked tracker issue).
- **code-review** — an **open PR** to review. Provide open PR URLs in your
  task file or via `--prompt` (mock-forge PR ids when running against the
  mocks).

## Running

```bash
# Run with an inline prompt (no task file needed):
scripts/factory-eval --track spec --runs 1 --prompt "Your task prompt here"

# Run round-robin over a local task file, overriding the model:
scripts/factory-eval --track spec --runs 6 --tasks-file my-tasks.jsonl --model <model-id>
```

`--runs N` is the **total** number of runs; tasks are cycled round-robin, so N
may be larger or smaller than the task count.

### Compare models (fan one request across models)

Use `--models` to send the **same** request to one run per model — handy for
A/B/n-ing models on a single task. Pick the request with `--task-id` (from the
track's task file), `--prompt` (inline), or let it default to the file's sole
task. `--reps` sets repetitions **per model** (default 1); `--model` and
`--runs` are not allowed in this mode.

```bash
# One task, three models, one run each:
scripts/factory-eval --track spec --task-id spec-bulk-cancel \
    --models <model-a>,<model-b>,<model-c>

# Inline prompt, two models, 3 reps each (= 6 runs):
scripts/factory-eval --track spec --prompt "Design a bulk-cancel endpoint" \
    --models <model-a>,<model-b> --reps 3
```

Every run records its own `model` in the CSV, so results can be grouped by
model to compare them directly.

## Authentication (`$WARP_API_KEY`)

Runs are launched via `curl` against the host in `--api-url` (default
`$FACTORY_FOREMAN_API_URL`, else the platform default) using an **Oz Cloud API
key** (Settings → Cloud platform → Oz Cloud API Keys; keys start with `wk-`).

The key is read **only** from `$WARP_API_KEY` in the local environment —
export it in your shell before running. If it is unset the script exits with
an error; it is never prompted for, echoed, or logged (curl reads it from a
stdin config, never argv).

## Mock providers (no real tickets, no real PRs)

By default an eval run drives the **real** providers through the
`scripts/tracker` and `scripts/forge` seams, so the agents create/update real
Jira tickets and real GitHub PRs. To exercise the full pipeline against
neither, point both seams at their in-memory mocks:

```bash
FACTORY_TRACKER_PROVIDER=mock-issue-tracker \
FACTORY_FORGE_PROVIDER=mock-code-forge \
scripts/factory-eval --track spec --runs 3 --prompt "Your task prompt here"
```

- `mock-issue-tracker` mirrors the real tracker provider's command surface,
  needs no network and no Jira credentials, **always succeeds**, and keeps
  issues in a local JSON store (`$FACTORY_MOCK_TRACKER_STORE`, else a file
  under the system temp dir) so a `create-issue` is readable by a later
  `get-issue`/`update-issue`/`search-issues` within the same run — letting
  each agent advance to its next step.
- `mock-code-forge` does the same for the forge seam: no network, no `gh`, PR
  metadata in a local JSON store (`$FACTORY_MOCK_FORGE_STORE`).

No real tickets or PRs are created, so cleanup (below) is a no-op. For the
launched **cloud** runs to use the mocks, both `FACTORY_TRACKER_PROVIDER` and
`FACTORY_FORGE_PROVIDER` must be set in the run environment (e.g. the eval
environment's variables) — exporting them only in your local shell affects
only the harness itself. Delete the store files to reset the mocks.

## Cleanup (`--apply-cleanup`)

Only relevant when running against the **real** providers: eval runs then
create real artifacts (PRs in the target repo, and the tracker issues linked
from those PRs). Cleanup prefixes their titles with `[Test]` and closes them
(PRs closed via `gh`; tracker issues set to `Canceled`).

- Cleanup is **preview-only by default** — it prints what it *would* change.
- Pass `--apply-cleanup` to actually mutate (retitle + close). This is a
  destructive action against shared state, hence the explicit opt-in.
- Tracker discovery is deterministic via the PR metadata block
  (`<!-- factory-agent: {...} -->`), read with `scripts/factory-pr-meta read`.
- **Triage limitation:** a standalone triage run produces a tracker issue but
  no PR, so there is no metadata to trace. Its issue is recorded in the CSV as
  the expected artifact but is **not** auto-closed — clean it up manually.

Requires `gh` (authenticated against the target repo) and the Jira
credentials in the environment; if either is missing, that side of cleanup is
skipped with a warning and the CSV is still written.

## Output

`scripts/factory-eval` appends one CSV row per run to
`evals/results/<track>.csv` (creating it with a header if absent), tagging
every row with a `batch_timestamp` shared by all runs in the same invocation,
and prints a batch-summary JSON object to stdout. Open
`evals/results/viewer.html` in a browser to inspect results.
