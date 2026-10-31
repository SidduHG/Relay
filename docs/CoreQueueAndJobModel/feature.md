# F2 — Core Queue & Job Model — Feature

**Spec:** [RELAY-SPEC.md § F2](../../RELAY-SPEC.md) (lines 88–110) · **Structure:** [folder structure](../../RELAY-production-folder-structure.md) · **Plan:** [plan.md](./plan.md)
**Goal:** A caller with an API key puts work in and gets a durable job id back in under 25 ms, and every later feature — leases, retries, priority, DAGs, cron, throttling, tracing — finds the column it needs already there.

## What F2 delivers

**Named queues, created on first use.** A project never provisions a queue. The first enqueue to `emails` creates it carrying the project's defaults; the thousandth costs nothing extra. Names are lowercase `a–z`, `0–9`, `-` and `_`, 1–63 characters, starting alphanumeric — one spelling per queue, so `Emails` and `emails` can never become two queues that look like one in a dashboard. Concurrent first-enqueues to the same new name produce exactly one queue.

**Per-queue defaults as a config surface.** Max attempts, job timeout, lease duration, default priority, rate limit and max depth are stored, bounded, validated and served by F2. F2 *enforces* two of them — default priority, applied at enqueue, and pause. The rest are read by F3, F5 and F8 when those ship. That is deliberate: a defaults editor whose values nothing reads yet is not dead code, it is the single config surface every later control loop reads instead of inventing its own.

**A job record later features do not have to migrate.** Handler, JSON payload, metadata, priority (as submitted and as effective), attempt counters, lease fields, timing fields, W3C trace id, and who enqueued it. Values that policy depends on — max attempts, timeout, lease duration — are snapshotted onto the job at enqueue, so lowering a queue default during an incident cannot retroactively dead-letter work already in flight.

**An enqueue write order that is the feature.** Claim the idempotency key, offload an oversized payload, insert the job row, commit Postgres, *then* index into Redis. The commit is the durability line: everything before it fails clean and leaves nothing behind, everything after it is a lagging index the reconciler repairs.

**Redis Streams as transport, one stream per queue per priority lane.** Streams, not lists, because a list pop removes the job before the claim can be recorded — a worker dying in that gap loses the job with no trace anywhere. A stream entry stays in the consumer group's pending list until it is acknowledged, and a stale one can be auto-claimed. The entry carries only a job id, so losing one costs a dispatch pointer, never data. F2's producer still trims with `MAXLEN ~`, which can remove undelivered entries, so the [worker pool plan](../workerPool/plan.md) replaces it before a consumer is enabled.

**Read endpoints built for a table that will hold fifty million rows.** A job by id with its full attempt history, and a job list filtered by status, handler, queue and date with cursor pagination — never offset. The cursor is an immutable `(created_at, id)` pair, so a page boundary cannot shift under a concurrent insert and page 10,000 costs what page 1 costs.

**Idempotency scoped to project plus queue,** 24-hour default window. A repeat submission returns the original job with a **200, not a 201**. The dedupe index lives in its own small unpartitioned table with an expiry column, because the jobs table is partitioned and a unique index there cannot span partitions.

**Payload offload above 256 KiB, rejection above 10 MiB.** Size is RELAY's own canonical UTF-8 serialization of the parsed payload, never the request's Content-Length — so the threshold is a property of the payload, not of whichever SDK formatted the JSON. Over the cap the caller gets a 413 before any row, blob or claim exists.

**Optional per-handler JSON Schema validation at submit.** A registered schema turns a bad payload into a 400 at enqueue instead of an explosion in a worker three hours later. The schema itself is validated once at registration, so a malformed schema fails there rather than on every subsequent enqueue. No schema means no validation — a project adopts it one handler at a time, with no flag day.

**Queue pause and resume.** A paused queue keeps accepting enqueues; workers stop draining it. Nothing in the write path consults the pause flag, which is the requirement rather than an omission — pausing during an incident must not also start rejecting your customers' submissions. A worker that has already claimed a job finishes it; pause stops fetching, not executing.

**Purge behind a confirmation token.** Minting the token tells the operator how many jobs are about to die and binds the token to that one queue. It is single-use and five-minute. Purge cancels the queued backlog and empties the streams; it never deletes a row, and it never touches a job that is already running.

## The job lifecycle

| State | Meaning | Exits via |
|---|---|---|
| `blocked` | waiting on unfinished parents | a parent completing, or a cascade |
| `scheduled` | not yet eligible; has a run-at time | the promoter, or cancellation |
| `queued` | indexed into a live stream, awaiting a worker | a worker claim, or cancellation |
| `running` | claimed, lease held | success, failure, retry, reclaim, or cancel |
| `succeeded` | the handler returned | **terminal** — a replay creates a new job, never resets this one |
| `failed` | attempts exhausted, or a permanent error. **The DLQ is this state, not a separate queue** | **terminal** — replay makes a new job |
| `cancelled` | operator cancel, purge, or a cascade | **terminal** |
| `parked` | P3: unknown handler, poison pill, bad payload found after submit | a human, and only a human |

`parked` is quiescent, not terminal — it has exactly one exit and no automated process will take it. Collapsing it into `failed` would make "park, never drop" indistinguishable from "give up", which is the thing P3 exists to prevent.

## Who can do what

F2 introduces **zero new permissions**. Every route maps onto a permission F1 already defined with its role matrix.

| Capability | Owner | Admin | Member | Viewer | API key |
|---|:--:|:--:|:--:|:--:|:--:|
| Enqueue, cancel a job | ✓ | ✓ | ✓ | — | ✓ |
| Read jobs, attempts, queues | ✓ | ✓ | ✓ | ✓ | ✓ |
| Edit queue defaults, register a handler schema | ✓ | ✓ | — | — | — |
| Pause / resume a queue | ✓ | ✓ | — | — | — |
| Purge a queue | ✓ | ✓ | — | — | — |

An API key is fixed at project Member, so **pause, resume, purge, queue defaults and schema registration are dashboard-JWT-only.** A leaked SDK key can flood a queue with jobs; it can never take one offline, destroy a backlog, or turn off validation for a handler. That is the F1 decision holding, not a gap.

## Guarantees

| Guarantee | How it holds |
|---|---|
| A 201 means the job will run | The response is written only after the Postgres commit. A Redis failure past that point delays dispatch; it cannot lose the job. |
| The same idempotency key produces one job | The claim and the job insert are one transaction, serialized by a unique index. 100 concurrent submissions yield one row and 99 pointers to it. |
| A crashed claimer leaves no debris | The claim rolls back with the job insert. The next submission of that key wins cleanly — no dangling pointer, no sweeper needed. |
| No cross-tenant read, ever | Every F2 table carries `project_id` and no `org_id`, sits under FORCEd row-level security including on each partition, and is reachable only through a scoped unit of work. The same two independent layers F1 proved. |
| An illegal state change cannot be written | The domain rejects illegal edges; every write is a compare-and-set on the current state, so a stale transition fails even when it is legal in the abstract. |
| Nothing is dropped | Oversized-at-submit is rejected synchronously to a caller who can react. Anything discovered oversized, unhandled or poisonous later parks. |
| A wipe of Redis loses nothing | Streams, pause flags and caches are all derived. The row's `redis_indexed_at` finds jobs that were never indexed, but it stays set after a wipe, so a wipe needs a full rebuild of queued jobs, detected by a Redis generation marker. |

## Targets

| Target | What serves it |
|---|---|
| p99 enqueue under 25 ms | One Postgres round trip, three indexes maintained at insert time, queue defaults read from cache rather than Postgres, and a single pipelined Redis command. |
| 256 KiB inline / 10 MiB cap | Measured on RELAY's own serialization, checked before any transaction opens, so a rejection costs no database work. |
| A list endpoint that stays fast at fifty million rows | Cursor pagination on an immutable key, and partial indexes covering live rows only. |
| Thirty days hot, then archived | Both large tables are partitioned by month from birth, with three months pre-created and a catch-all so a missed roll degrades instead of failing. |

## Boundaries — what F2 does not build

F2 is the producer half of a producer/consumer pair. It lands the columns, states and key shapes later features write to, and stops.

It does **not** build: the claim, lease renewal, the heartbeat or the reaper (F3); priority aging (F4); backoff, the delay set, the promoter or replay (F5); the dependency table, the decrement or the cascade (F6); schedules, cron or leader election (F7); token buckets, depth checks or circuit breakers (F8); spans, metrics or the WebSocket fan-out (F9); the reconciler, the retention loop or partition rolling (F10).

Blob storage ships with a local filesystem backend only. S3 and GCS sit behind an interface that already exists, one file and one URL scheme away — v1 is one box with one disk, and requiring an object-store account to enqueue a 300 KB payload would be a worse product, not a more serious one.

Redis append-only persistence is deliberately still off. Persisting stream entries across a restart is a convenience, not a correctness property, and switching it on before the reconciler exists would make the wipe drill pass for the wrong reason — the streams survive, the rebuild path never runs, and the first real wipe happens in production against untested code.

**Done when** the same idempotency key submitted 100 times concurrently produces exactly one job row and 99 responses pointing at it.
