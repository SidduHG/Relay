# Relay coding standards

Apply the sections your change touches.

## Design patterns

Use a pattern when it removes a real branch or dependency. Relay's established ones:

| Pattern | Where | Purpose |
|---|---|---|
| Unit of Work | `TenantUnitOfWork` | One scoped transaction, the only route to a repository |
| Repository | `relay_db/repositories/` | SQL behind intent-named methods |
| Strategy | `BlobStore`, `RetryPolicy`, execution backends | Swap behavior behind a Protocol |
| Registry | Handler registry | Resolve a job's handler by name and version |
| Template Method | `ControlLoop` | Base owns timing and errors; each loop implements `tick()` |
| State | Job state machine, circuit breaker | One explicit transition table |
| Cache-Aside | `QueueConfigCache` | Read through a short TTL; Postgres stays the truth |

Prefer a function until state or a second implementation justifies a class. Pass collaborators through constructors, so tests can use fakes. Add an abstraction when the second real caller exists.

## Python

- Full type hints, passing `mypy` strict. Use `Protocol` for seams and frozen, slotted dataclasses for values.
- Return explicit result types for races, such as won, lost, or stale.
- Keep functions focused, and name them after the outcome they produce.
- Raise specific plain exceptions below the route layer.
- Write comments for the reason behind a choice, in one or two lines.

## Async and concurrency

- Keep the event loop free. Run blocking or CPU work in a thread or process, including gzip of large payloads and sync handlers.
- Bound everything: queues, batches, caches, retries, and timeouts on every network call.
- Give each background task an owner and a clean shutdown.
- Start batching with natural batches: flush when the previous flush ends.

## Postgres

- Every schema change is an Alembic migration with a tested downgrade.
- New tenant tables get FORCE RLS, including each partition. Include `project_id` on job-related tables, never `org_id`.
- Pass `created_at` with job lookups, so one partition is touched.
- Index live rows with partial indexes. Build indexes on large tables concurrently, per partition.
- Keep transactions short, with no network calls inside except a bounded blob upload.
- Use `FOR UPDATE SKIP LOCKED` for loop batches, and always `LIMIT`.
- Check `EXPLAIN` for any query on the hot path.
- Treat old and new code as running together during rollouts: expand, migrate, contract.

## Redis

- Add key names only in `keys.py`, keeping a queue's keys in one hash slot.
- Use Lua for read-modify-write. Pass every key in `KEYS`.
- Pipeline related commands. Run with `noeviction`.
- Removing an entry that nobody has read is an operator purge, and nothing else.
- For each new key, write down how it is rebuilt after a wipe.

## Logging

- Use structured JSON through `relay_observability`, with stable event names such as `job.claimed`.
- Bind `request_id`, `project_id`, `job_id`, and `worker_id` at the boundary with `contextvars`.
- Levels: `ERROR` needs a human, `WARNING` is an unexpected but handled state, `INFO` is a lifecycle event, `DEBUG` is diagnostic.
- Log each failure once, at the layer that handles it, with the exception attached.
- Payloads, tokens, and passwords stay out of logs. Apply redaction paths for sensitive fields.

## Metrics and tracing

- Label with queue, handler, priority, and outcome. Identifiers such as `job_id` belong in logs and traces.
- Keep trace context across the queue boundary using the fields stored on the job.
- Each control loop reports a tick duration and a lag.
- A new failure mode gets a metric and an alert that point to a runbook.

## API

- Map errors in `error_handler.py`. A 503 means the requested effect did not happen.
- Return 404 for other tenants' resources, and 403 for a low role inside your own project.
- Use cursor pagination. Audit every privileged action in the same transaction.

## Testing

- Unit-test domain rules with no I/O, and test transactions against real Postgres.
- Cover races with real concurrency, and crash windows by killing the process at that step.
- Test through public interfaces, and assert on durable state.
- Each `Must handle` item in the spec maps to a named test.
- Tests may skip when a service is missing, so treat a skip as not verified.

## Production checklist

Before calling a feature done, confirm:

- [ ] Every crash window has an owner
- [ ] Retries are idempotent and bounded
- [ ] Timeouts exist on all external calls
- [ ] Inputs are validated and limits enforced
- [ ] Tenant isolation is tested
- [ ] Logs, metrics, and traces cover the new path
- [ ] A failure can be diagnosed from telemetry alone
- [ ] Migrations are safe during a rolling deploy
- [ ] Docs match the behavior
