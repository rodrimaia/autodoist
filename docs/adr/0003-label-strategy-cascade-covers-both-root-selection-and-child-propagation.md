# Label strategy cascade covers both root selection and child propagation

The label strategy parsed from project and section name suffixes (`-`, `=`) serves two purposes: (1) selecting which parentless tasks receive the next-action label, and (2) providing a fallback child-propagation strategy when a parent task has no explicit suffix of its own.

We considered decoupling these -- making child propagation exclusively task-level opt-in, never inherited from project or section suffixes. This would let an unsuffixed parent task live under a suffixed project without its subtasks being affected by the project strategy. However, decoupling breaks a valid workflow where project-level suffixes intentionally control child propagation depth without requiring every parent task to carry its own suffix.

We keep the cascade intact. If a future need arises for explicit separation, the escape hatch should preserve the current behavior by default and require explicit opt-in (a task-level suffix or config flag) to opt out of inherited child propagation.
