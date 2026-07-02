# Autodoist

Autodoist is a long-running Todoist automation process that labels actionable tasks and applies related task maintenance rules.

## Language

**Startup verification**:
The checks Autodoist performs once before entering the sync loop, such as validating the Todoist API key, connecting to Todoist, and confirming required labels exist.
_Avoid_: startup sync, boot logic

**Startup retry window**:
The bounded period during startup verification where Autodoist retries temporary Todoist API failures before exiting and letting the runtime decide what happens next.
_Avoid_: infinite startup retry, retry loop

**Temporary Todoist failure**:
A Todoist API failure that may resolve without a configuration change, such as rate limiting, server errors, connection errors, or timeouts.
_Avoid_: configuration error, invalid token

**Required label**:
A Todoist label that Autodoist needs to exist before a configured feature can run correctly, such as the next-action label used by automatic task labelling.
_Avoid_: startup label, checked label

**Sync loop**:
The repeated work cycle that reads Todoist state, computes task changes, writes updates, reports status, and sleeps before the next cycle.
_Avoid_: polling loop, main loop

**Next-action label planner**:
The part of Autodoist that decides which tasks should gain or lose the next-action label during a sync loop.
_Avoid_: labeling service, label engine, sync logic

**Transparent planner migration**:
The requirement that next-action label planner refactors preserve existing user-visible behavior for legacy Autodoist configurations.
_Avoid_: breaking cleanup, behavioral rewrite, v3 behavior

**Label strategy**:
The sequential or parallel rule that tells Autodoist how to choose actionable tasks at a project, section, task, or child-task level.
_Avoid_: suffix code, mode string, type code

**Actionable date marker**:
A phrase on a Todoist task that delays when the task may receive the next-action label, either until an absolute date or until a date relative to the task's due date.
_Avoid_: start-date hack, date suffix

**Autodoist metadata**:
Persisted facts from previous sync loops that Autodoist uses to detect label strategy changes and continue next-action label propagation correctly.
_Avoid_: SQLite data, task_type columns, internal cache
