# Autodoist

Autodoist is a long-running Todoist automation process that labels actionable tasks and applies related task maintenance rules.

## Language

**Startup verification**:
The checks Autodoist performs once before entering the sync loop, such as validating the Todoist API key, connecting to Todoist, and confirming required labels exist.
_Avoid_: startup sync, boot logic

**Required label**:
A Todoist label that Autodoist needs to exist before a configured feature can run correctly, such as the next-action label used by automatic task labelling.
_Avoid_: startup label, checked label

**Sync loop**:
The repeated work cycle that reads Todoist state, computes task changes, writes updates, reports status, and sleeps before the next cycle.
_Avoid_: polling loop, main loop
