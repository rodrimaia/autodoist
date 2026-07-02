# JSON operational logs

Autodoist is commonly run as a long-running Docker process, where logs are consumed by container tooling and monitoring systems. We will emit operational logs as JSON rather than free-form text so retry, rate-limit, and sync-loop events can be parsed reliably.

Use `python-json-logger` with the standard library `logging` module. This keeps the existing logging calls mostly intact while avoiding a custom JSON formatter.
