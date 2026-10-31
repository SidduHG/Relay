# Worker Pool — Feature

**Source:** [RELAY-SPEC.md, F3](../../RELAY-SPEC.md) · [Architecture](../../ARCHITECTURE.md) · [Implementation plan](./plan.md)

## What this feature does

Relay already accepts and stores jobs. The worker pool makes those jobs run. A worker takes an available job, calls the named handler, records what happened, and then takes another job. Several workers can share the same workload.

## Why it matters

Today a successful enqueue means that Relay stored a job; it does not mean that a worker will execute it. The worker pool closes that gap. It must also handle a worker stopping halfway through a job without silently losing the job or claiming that execution can happen only once.

## Who uses it and what they can do

- **Application teams** deploy handlers and submit jobs to a project queue. They can see whether each job ran, failed, timed out, or was parked for inspection.
- **Operators** can add worker capacity, pause a queue without rejecting new submissions, and drain a worker before shutting it down.
- **Job handlers** receive the submitted payload. They must tolerate being called again after a crash, because Relay provides at-least-once execution.

For example, a team submits `reports.generate` for report `42`. A worker picks it up and creates the report. If the worker dies before Relay records completion, another worker may run the same job. The handler writes to the same report ID so the second run does not create a duplicate report.

## Included

- Workers advertise their identity, capacity, and supported handlers.
- Workers take ready jobs in priority order, respect queue pauses, and never take more work than their configured capacity.
- A claimed job has a renewable lease and a separate maximum runtime. A worker that no longer owns a job cannot record its result.
- Relay records every completed or reclaimed attempt before it considers the Redis delivery finished.
- A crashed worker's job becomes eligible again after its lease expires. Repeated crashes park the job for inspection.
- Missing Redis dispatch entries can be restored from durable Postgres jobs. The pool is tested against worker crashes and Redis loss before it is called production ready.

## Outside this feature

Scheduled-job promotion, retry backoff and replay, priority aging, rate limiting, cron, dependency graphs, and dashboard polish remain separate features. An ordinary handler error is recorded accurately; automatic retry policy belongs to F5. Relay does not promise exactly-once handler execution or undo an external side effect made before a crash.

## How to know it works

A submitted immediate job reaches a recorded outcome and can be inspected with its attempt history. Pausing stops new claims while current jobs finish. Killing a worker or wiping Redis in a test deployment does not leave a durable eligible job permanently stuck or lost. The recovery test reports any duplicate executions instead of hiding them.
