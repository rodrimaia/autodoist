# Autodoist

[![CI](https://github.com/rodrimaia/autodoist/actions/workflows/ci.yaml/badge.svg)](https://github.com/rodrimaia/autodoist/actions/workflows/ci.yaml) ![Python](https://img.shields.io/badge/python-%3E%3D3.11-blue) [![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE) [![ko-fi](https://ko-fi.com/img/githubbutton_sm.svg)](https://ko-fi.com/C3Y026MKBX)

Autodoist is a long-running [Todoist](https://todoist.com/) automation service. It keeps a trustworthy `next_action` label up to date for GTD-style workflows and can also maintain task headers, shift the effective end of day, remove labels from selected projects, and report its health to a monitoring service.

This repository is an actively maintained fork of [Hoffelhas/autodoist](https://github.com/Hoffelhas/autodoist). It preserves Autodoist's established behavior while updating its Todoist integration, packaging, tests, and operations. See [Project history](#project-history) for the full lineage.

## What it does

| Capability | Status | How to enable it |
| --- | --- | --- |
| Automatic next-action labels | Active | `--label next_action` |
| Sequential and parallel task selection | Active | Add `-` or `=` strategies to Todoist names |
| Actionable dates and future-task filtering | Active | Add a `start=...` marker or use `--hide_future` |
| Shifted end of day | Active | `--end HOUR` |
| Bulk header/unheader commands | Active | Prefix a project, section, or task with `** ` or `-* ` during an enabled run |
| Project-wide label cleanup | Active | `--remove_all_labels_from_project PROJECT` |
| Monitoring callbacks and JSON logs | Active | `--status_url URL` and `--debug` |
| Recurring-subtask regeneration | **Disabled** | Todoist's REST API does not expose the completed-task data this implementation requires |

## Quick start with Docker

The rolling `master` image is published to GHCR after the test suite passes. This fork does not currently publish versioned releases. The image currently targets `linux/amd64`; Docker can run it through emulation on ARM hosts, where it will display a platform warning.

### 1. Create an environment file

Get your token from Todoist's [Integrations settings](https://app.todoist.com/app/settings/integrations/developer), then place it in a local `.env` file:

```dotenv
TODOIST_API_KEY=replace_with_your_token
```

Do not commit this file. The repository's `.gitignore` already excludes `.env`.

### 2. Run one sync interactively

The first run verifies your token and offers to create the configured label if it does not exist:

```bash
docker run --rm -it \
  --env-file .env \
  ghcr.io/rodrimaia/autodoist:master \
  --label next_action \
  --onetime
```

Nothing will be selected until you configure a [label strategy](#label-strategies), unless you add `--all_projects`.

### 3. Keep Autodoist running

Once the initial sync behaves as expected, run it as a service:

```bash
docker run -d \
  --name autodoist \
  --restart unless-stopped \
  --env-file .env \
  ghcr.io/rodrimaia/autodoist:master \
  --label next_action
```

Follow its structured logs with:

```bash
docker logs -f autodoist
```

### Persist planner metadata

Autodoist stores planner metadata in `/app/metadata.sqlite`. Docker preserves that file across container restarts, but not when the container is removed and recreated. For deployments that recreate containers, bind-mount the database:

```bash
mkdir -p autodoist-data
touch autodoist-data/metadata.sqlite

docker run -d \
  --name autodoist \
  --restart unless-stopped \
  --env-file .env \
  --mount type=bind,src="$PWD/autodoist-data/metadata.sqlite",dst=/app/metadata.sqlite \
  ghcr.io/rodrimaia/autodoist:master \
  --label next_action
```

Autodoist also writes `debug.log` inside the container, but the same JSON log stream is available through `docker logs`.

## Run from source

Requirements:

- Python 3.11 or newer
- [uv](https://docs.astral.sh/uv/)
- A Todoist API token

Install the locked dependencies:

```bash
uv sync --frozen
```

Export your token and perform one sync:

```bash
export TODOIST_API_KEY=replace_with_your_token
uv run --frozen python autodoist.py --label next_action --onetime
```

Remove `--onetime` to enter the continuous sync loop. You may also pass the token with `--api_key`, but an environment variable avoids placing it in your shell history.

## Configuration reference

At least one functional mode—next-action labeling, shifted end of day, or project label cleanup—must be enabled.

| Option | Purpose | Default |
| --- | --- | --- |
| `-a`, `--api_key TOKEN` | Todoist API token; `TODOIST_API_KEY` is used when omitted | Environment |
| `-l`, `--label NAME` | Enable next-action labeling with this Todoist label | Disabled |
| `-e`, `--end HOUR` | Treat an hour from `1` through `24` as the end of day | Disabled |
| `-d`, `--delay SECONDS` | Delay between sync-loop starts | `5` |
| `-p`, `--p_suffix TEXT` | Parallel label-strategy suffix | `=` |
| `-s`, `--s_suffix TEXT` | Sequential label-strategy suffix | `-` |
| `-hf`, `--hide_future DAYS` | Do not label tasks due at least this many days in the future | `0` |
| `--onetime` | Run one sync and exit | Disabled |
| `--debug` | Include debug-level events in the JSON logs | Disabled |
| `--inbox parallel\|sequential` | Select the strategy used for Inbox tasks | Unconfigured |
| `--all_projects` | Apply next-action labeling to projects without strategy suffixes | Disabled |
| `--ignore_suffix` | With `--all_projects`, skip projects ending in `_ignore` | Disabled |
| `--remove_all_labels_from_project PROJECT` | Remove all labels from active tasks in a project; repeatable | Disabled |
| `--status_url URL` | Send a GET request to a monitoring endpoint during sync loops | Disabled |
| `-r`, `--regeneration` | Recurring-subtask regeneration | **Currently disabled** |
| `-df`, `--dateformat FORMAT` | Date format for the disabled regeneration feature | **Currently disabled** |

Avoid `/` as a custom strategy suffix: Todoist normalizes it to `_` in section names, so Autodoist cannot detect the original character there.

See the CLI itself for the authoritative short reference:

```bash
uv run --frozen python autodoist.py --help
```

Options can be combined. For example, this labels every project except names ending in `_ignore`, uses a 30-second delay, and pings a health-check URL:

```bash
uv run --frozen python autodoist.py \
  --label next_action \
  --all_projects \
  --ignore_suffix \
  --delay 30 \
  --status_url https://example.com/healthcheck
```

## Next-action labeling

Autodoist adds and removes the label supplied with `--label` so that only currently actionable tasks carry it. Label strategies can be defined in the names of projects, sections, or tasks. A more specific strategy overrides one inherited from a higher level.

A Todoist filter such as the following then becomes a live view of the actionable work in a project:

```text
@next_action & #PROJECT_NAME
```

### Label strategies

| Suffix | Strategy | Behavior |
| --- | --- | --- |
| `-` | Sequential | Label only the first actionable task in order, descending to the lowest available subtask |
| `=` | Parallel | Label every actionable leaf task at that level |

![A sequential project labels only the first available action](https://i.imgur.com/ZUKbA8E.gif)

![A parallel project labels all available leaf actions](https://i.imgur.com/xZZ0kEM.gif)

The suffix position describes increasingly deeper levels:

| Name being configured | Maximum suffix length | Positions control |
| --- | --- | --- |
| Project | 3 | Sections → root tasks → subtasks |
| Section | 2 | Root tasks → subtasks |
| Task | 1 | Child tasks |

If a suffix is shorter than the maximum, its last strategy repeats. A project ending in `=` therefore behaves like `===`, while `=-` behaves like `=--`. The same rule makes a section ending in `=` equivalent to `==`.

Project examples:

| Suffix | Result |
| --- | --- |
| `---` | Select the first section, first root-task path, and first actionable leaf |
| `=--` | Process all sections, then select tasks and descendants sequentially |
| `-=-` | Select one section, process its root tasks in parallel, and descend sequentially |
| `--=` | Select one section and root-task path, then process its subtasks in parallel |
| `==-` | Process all sections and root tasks, descending into subtasks sequentially |
| `=-=` | Process all sections, root tasks sequentially, and subtasks in parallel |
| `-==` | Select one section, then process its root tasks and subtasks in parallel |
| `===` | Process all eligible tasks in parallel |

Section examples:

| Suffix | Result |
| --- | --- |
| `--` | Select the first root-task path and descend sequentially |
| `=-` | Process every root task, descending sequentially |
| `-=` | Select the first root task, then process its subtasks in parallel |
| `==` | Process root tasks and subtasks in parallel |

A task ending in `-` processes its children sequentially; a task ending in `=` processes them in parallel.

To disable next-action labeling for a section, place `*` at the beginning or end of its name.

### Kanban example

For a board that should expose one action per column and none in a final Done column:

1. End the project name with `=--`.
2. Add `*` to the beginning or end of the Done section name.

Alternatively, end every section that should expose one action with `--`.

### Label every project

Use `--all_projects` when suffixes should be optional:

```bash
uv run --frozen python autodoist.py --label next_action --all_projects
```

Add `--ignore_suffix` to exclude projects whose names end in `_ignore`:

```bash
uv run --frozen python autodoist.py \
  --label next_action \
  --all_projects \
  --ignore_suffix
```

Explicit suffix strategies still take precedence over the all-project default.

### Actionable dates

Place an actionable date marker anywhere in a task's content to delay its `next_action` label:

| Marker | Meaning |
| --- | --- |
| `start=31-12-2026` | Actionable on or after this absolute date (`DD-MM-YYYY`) |
| `start=due-3d` | Actionable three days before its Todoist due date |
| `start=due-2w` | Actionable two weeks before its Todoist due date |

![A task using an absolute actionable date marker](https://i.imgur.com/WJRoJzW.png)

If a relative marker is used on a task without a Todoist due date, Autodoist leaves its label behavior unchanged and adds a warning to the task description so the incomplete configuration is visible.

`--hide_future DAYS` provides an account-wide boundary in addition to per-task markers. For example, `--hide_future 14` prevents labeling tasks due 14 or more days in the future.

![Tasks hidden using the future due-date boundary](https://i.imgur.com/LzSoRUm.png)

## Other automations

### Shift the end of day

Use `--end HOUR` for daily recurring tasks completed after midnight. Before the configured hour, Autodoist corrects an eligible recurring task that Todoist has already advanced to tomorrow so it can still be completed for the current day.

```bash
uv run --frozen python autodoist.py --end 3
```

![A daily recurring task corrected after midnight](https://i.imgur.com/tvnTMOJ.gif)

### Make task trees uncheckable or checkable

Todoist treats task content beginning with `* ` as an uncheckable header. Prefix a project, section, or root task with one of these one-time commands:

| Prefix | Effect |
| --- | --- |
| `** ` | Convert the included task tree to headers |
| `-* ` | Convert the included task tree back to checkable tasks |

Autodoist removes the command prefix after processing it. Header commands are scanned as part of an otherwise enabled Autodoist run.

### Remove every label from selected projects

`--remove_all_labels_from_project` continuously enforces an empty label set on active tasks in the selected project. Pass an exact, case-sensitive project name or a project ID, and repeat the option for multiple projects:

```bash
uv run --frozen python autodoist.py \
  --remove_all_labels_from_project "Someday" \
  --remove_all_labels_from_project 123456789
```

Important behavior:

- Project IDs take precedence when a value could match both an ID and a name.
- An unknown or ambiguous name aborts the sync before label changes are written.
- Active root tasks, subtasks, and header tasks directly in the project are included, including Inbox tasks when Inbox is selected.
- Completed tasks and tasks in nested projects are not changed; select nested projects separately.
- New labels and tasks moved into a selected project are cleaned during the next sync.
- Cleanup wins if the same task is also considered by next-action labeling.

This option is destructive. Use `--onetime` for a one-off cleanup before enabling continuous enforcement.

## Operations

Autodoist emits one JSON object per line to stderr and `debug.log`. Every event includes `timestamp`, `level`, and `message`; operational events may also include fields such as `component`, `operation`, `label`, `error_type`, `retry_in_seconds`, and `retry_window_remaining_seconds`.

Pass `--debug` to include debug-level events. When running Docker, prefer the container log stream rather than relying on the in-container file:

```bash
docker logs -f autodoist
```

Use `--status_url` with services such as Healthchecks.io or Uptime Kuma. Autodoist sends a GET request during sync-loop processing and logs failures without stopping the service:

```bash
uv run --frozen python autodoist.py \
  --label next_action \
  --status_url https://example.com/healthcheck
```

Temporary Todoist failures during startup verification are retried for a bounded window. Persistent startup failures exit the process so Docker or another service manager can restart it.

## Disabled recurring-subtask regeneration

Autodoist historically regenerated subtasks beneath completed recurring parent tasks. The `--regeneration` and `--dateformat` arguments remain visible for compatibility, but regeneration is forcibly disabled because the Todoist REST API does not provide the completed-task data needed by this implementation.

Todoist now provides its own [reset subtasks](https://todoist.com/help/articles/can-i-reset-sub-tasks) behavior. Autodoist's former implementation supported additional ordering and nesting behavior, so the feature may return if the API can support it safely.

## Project history

Autodoist is the latest chapter in a community-maintained line of Todoist automation projects:

```text
akramer/NextAction (2014)
└── BenjaminVanRyseghem/NextAction
    └── nikdoof/NextAction
        └── shadowgate15/automation-todoist-old
            └── Hoffelhas/autodoist (2020)
                └── rodrimaia/autodoist (2025)
```

- **2014 — NextAction:** [Adam Kramer](https://github.com/akramer) created [NextAction](https://github.com/akramer/NextAction), using Todoist's API to maintain an automatic `next_action` label for GTD workflows.
- **Community continuation:** [Benjamin Van Ryseghem](https://github.com/BenjaminVanRyseghem), [Andrew Williams](https://github.com/nikdoof), and [shadowgate15](https://github.com/shadowgate15) carried the code through successive forks as Todoist and its APIs evolved.
- **2020–2023 — Autodoist:** [Alexander Haselhoff (Hoffelhas)](https://github.com/Hoffelhas) expanded the idea into Autodoist, adding hierarchical sequential/parallel strategies, actionable dates, recurring-task tools, end-of-day handling, and releases through v2.0.
- **2025–present — This fork:** [Rodrigo Maia](https://github.com/rodrimaia) forked Autodoist and resumed active development. The fork moved the integration to the official Todoist REST SDK, migrated packaging to uv, added CI and GHCR publishing, introduced structured operational logs and a tested next-action planner, fixed date and strategy behavior, and added all-project and project-cleanup modes.

The Git history retains work from all of these eras. See the [contributors graph](https://github.com/rodrimaia/autodoist/graphs/contributors) for the people whose code and documentation made the project possible.

> Autodoist is genuinely useful to me, so I keep it maintained. It's lovely to know that other people find it useful too—if it could help you more, please let me know. — Rodrigo Maia

## Contributing

Feature requests are especially welcome. If an automation or improvement would make Autodoist more useful in your workflow, please [open an issue](https://github.com/rodrimaia/autodoist/issues) and tell us about it—even if you are not sure how it should be implemented. Bug reports, focused fixes, tests, and documentation improvements are welcome too.

For large behavior changes, open an issue first so the intended compatibility impact is clear.

Set up the development environment and run the tests with:

```bash
uv sync --frozen
uv run --frozen pytest
```

Autodoist intentionally preserves legacy user-visible behavior while its internals are modernized. Changes to label selection, suffix cascading, actionable-date boundaries, or cleanup precedence should include regression tests.

## Support ongoing maintenance

If Autodoist saves you time, you can support continued maintenance through [GitHub Sponsors](https://github.com/sponsors/rodrimaia) or leave a one-time tip on [Ko-fi](https://ko-fi.com/rodrimaia).

[![ko-fi](https://ko-fi.com/img/githubbutton_sm.svg)](https://ko-fi.com/C3Y026MKBX)

## License

Autodoist is available under the [MIT License](LICENSE). Copyright remains with the contributors recorded in the repository history.
