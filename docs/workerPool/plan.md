# Worker Pool — Implementation Plan

**Feature:** [feature.md](./feature.md) · **Spec:** [RELAY-SPEC.md, F3](../../RELAY-SPEC.md) · **Architecture:** [ARCHITECTURE.md](../../ARCHITECTURE.md) · **Placement:** [production folder structure](../../RELAY-production-folder-structure.md)

## Goal and current boundary

Turn an immediate `queued` job into an executed, durably recorded outcome. Keep Postgres authoritative, Redis rebuildable, and delivery at least once. A worker crash, Redis wipe, stale worker, queue pause, and stream trim must not silently lose or permanently strand eligible work. This is a feature plan, not authorization to implement all tasks at once; complete and review one task before starting the next, as `AGENTS.md` requires.

Context inspected: `RELAY-SPEC.md` F2/F3 and ground rules, `ARCHITECTURE.md`, `RELAY-production-folder-structure.md`, `docs/CoreQueueAndJobModel/{feature,plan}.md`, `docs/current-implementation-handbook.md`, the current worker shell and Dockerfile, F2 enqueue/stream producer, job/attempt/queue models and repositories, tenant unit of work, payload storage, Compose, and the Redis/Postgres integration tests. The repository calls the spec `RELAY-SPEC.md` (with a hyphen).

Today the API commits a `queued` job, then `XADD`s a pointer to `q:{project_id}:{queue}:p{priority}`. `apps/worker` has only config, logging, signal handling, and an idle loop. Consumer groups, handler loading, claim/complete transactions, lease renewal, reaper, and reconciler do not exist. The worker Dockerfile currently copies only `packages/observability`, so it cannot yet import the DB, Redis, domain, or storage packages needed for execution.

## Scope and boundaries

**In scope:** immediate jobs, four existing priority streams, worker registration and handler manifest, bounded local concurrency, claim/lease/heartbeat, payload rehydration, handler execution, timeout/cancellation, durable outcomes and attempts, acknowledgement, graceful drain, expired-lease recovery, Redis reconstruction, safe stream retention, worker metrics, and the F3 crash proof.

**Out of scope:** scheduled-job promotion, retry backoff/replay, priority aging, cron, DAGs, downstream rate limiting, dashboard pages, and cross-region operation. Ordinary handler errors record a failed outcome now; F5 later decides whether and when to retry. The existing `run_at`/`scheduled` rows remain ineligible until the promoter exists. No public enqueue contract needs to change except the explicitly planned backlog safeguard.

Module ownership stays as designed: `apps/worker` orchestrates consumption and execution; `packages/db` owns transactional state changes; `packages/redis` owns stream and registry commands; `packages/domain` owns transition rules; `apps/control-loops` owns single-leader reclaim/reconciliation; `apps/api` owns operator commands. The worker must not import API services or use an RLS-bypassing database role.

## Decisions that keep the workflow safe

1. **Two claims, one truth.** `XREADGROUP` assigns a Redis stream entry to a consumer and leaves it pending. That is a transport claim only. A conditional Postgres update from `queued` to `running` is the execution claim. If it loses, the worker must not invoke the handler. An old queued/cancelled/terminal pointer can be acknowledged after verifying Postgres state; a pointer for another live owner cannot.
2. **Fence every attempt.** Use a unique worker instance ID and the job's incremented `attempt` as the ownership token. Claim, renewal, completion, cancellation, and reclaim compare `state`, `lease_owner`, and `attempt`. Completion also requires a still-valid lease, using database time. A worker that wakes after its lease was reassigned cannot overwrite the new attempt or acknowledge its stream entry.
3. **Use server time.** The claim and renewal transactions derive `lease_expires_at` from Postgres `now()` plus the job's snapshotted `lease_seconds`. Worker wall clocks only drive local sleep/timeout scheduling. The snapshotted `timeout_seconds` is a separate maximum runtime; heartbeats never extend it.
4. **Commit before acknowledging.** On success, failure, timeout, or cancellation, one Postgres transaction conditionally changes the job and inserts the completed `job_attempts` row. `XACK` follows the commit. If `XACK` fails, redelivery checks the durable state and acknowledges the stale pointer without rerunning the handler. Attempt rows are written at outcome/reclaim time because the current `outcome` column is non-null; no schema change is needed just to represent an in-flight attempt.
5. **Treat Redis as a pointer, not evidence of a job's state.** The worker always reads Postgres before execution. Redis pending ownership is not a lease, and `redis_indexed_at` proves only that an `XADD` once succeeded. It does not prove that the entry still exists after trimming or a wipe.
6. **Handler compatibility is explicit.** A trusted, configured Python module registers `(name, version, execution kind, callable)` entries. For the first pool, workers consuming a queue use a compatible manifest; heterogeneous fleets need a deliberate routing design before deployment. A missing handler/version is never called as a fallback. After a configurable grace window, a job with no compatible registered worker is parked with a reason; a rolling deployment may supply the handler before that window ends.
7. **No distributed transaction is invented.** F3 says one heartbeat round trip refreshes Redis liveness and extends Postgres leases. These are different stores and cannot be one atomic round trip. Batch the conditional lease renewals in one Postgres transaction and refresh Redis registry/liveness in one pipeline. Postgres lease state decides reclaim; Redis liveness is diagnostic. Record this clarification in `RELAY-SPEC.md` before implementing heartbeat behavior if the spec is edited in a later task.

### Normal path

```text
API: Postgres INSERT/commit -> Redis XADD
worker: discover stream -> check queue pause -> XREADGROUP (prefetch 1 per free slot)
worker: project-scoped Postgres CAS queued -> running; attempt + 1; lease deadline
worker: load payload -> invoke compatible handler; renew lease while it runs
worker: fenced Postgres outcome + attempt/commit -> Redis XACK
```

Use the existing stream key to obtain project and queue scope, then verify those values against the job row inside a `TenantUnitOfWork`. Discover active queue streams with bounded Redis `SCAN` and refresh the list periodically so implicitly created queues become consumable. Redis discovery is not an authority for tenancy; every job/queue write is project-scoped under the existing RLS policy. If Postgres is unavailable, stop new claims and finish or safely relinquish current work according to the shutdown policy.

Read lanes `p0`, `p1`, `p2` non-blocking before a short blocking read on `p3`, as F3 specifies. Recheck higher lanes after a block returns. Read no more than free execution slots; default prefetch is one. Check the durable queue pause state again during claim, with the Redis pause key as a fast hint, so a pause racing with `XREADGROUP` or a Redis wipe cannot silently start new work. Jobs already claimed finish. A cancelled/purged pointer is acknowledged without executing. If lease renewal fails, stop or cancel the handler as soon as possible and do not write an outcome or acknowledge without a successful ownership check.

### Failure windows to implement and test

| Failure window | Required behavior |
|---|---|
| Redis delivery, before Postgres claim | Pending pointer is reclaimed or reindexed; job is still `queued` and can be claimed later. |
| Claim committed, before or during handler | Lease eventually expires; leader reaper conditionally records `reclaimed`, increments `reclaim_count`, and queues it again or parks at three reclaims. |
| Handler side effect, before Postgres outcome | Job may run again. Document handler idempotency using the stable job ID; never advertise exactly-once execution. |
| Postgres outcome committed, before `XACK` | Redelivery observes the terminal state, acknowledges, and does not call the handler again. |
| Lease expires while old handler is still active | Reaper may reassign; old worker's renewal/completion fails the owner+attempt fence and it must not acknowledge. |
| Redis entry removed by trim or Redis wipe | Reconciler restores every eligible Postgres job, including rows with non-null `redis_indexed_at`; duplicate pointers are harmless because only one Postgres CAS can win. |
| Timeout or SIGTERM | Stop new claims, request cooperative cancellation, allow the configured grace, then terminate killable child work; record/relinquish jobs safely before exit when possible. A hard-killed process relies on the reaper. |

Recovery bound: a crash cannot be recognized until its lease expires. With a 60-second lease and a 5-second reaper interval, the expected bound is roughly lease expiry plus one reaper cycle, not five seconds after the crash. This clarifies the F3/P4 wording without weakening the no-loss requirement.

### Recovery and stream-retention design

The reaper owns `running` jobs whose Postgres lease expired. It changes the job and writes a reclaimed attempt in one fenced transaction **before** changing Redis. It also examines Redis pending entries that were delivered but never claimed in Postgres. Reclaiming a pending Redis entry alone does not authorize execution; the next worker must still win the Postgres claim. Never reclaim a pending entry from a job whose Postgres lease is still valid.

The reconciler owns `queued` jobs with no usable Redis pointer. It repairs failed post-commit indexing (`redis_indexed_at IS NULL`), performs a full queued-job rebuild when the Redis generation marker is lost (for example after `FLUSHDB`), and audits queued jobs in bounded batches for an individually deleted or trimmed pointer. The Redis dispatch-membership check must be rebuildable and verified against the actual stream entry; a historical `redis_indexed_at` timestamp or a Redis membership flag by itself is insufficient. Reindexing may produce a duplicate pointer, but the Postgres claim prevents a duplicate live owner. Limit repair batch size and measure how long a full rebuild takes; the 60-second interval is a scan cadence, not a promise that an arbitrarily large backlog rebuilds in 60 seconds.

The current producer's blind `XADD MAXLEN ~` must be removed before enabling a live consumer. For bounded memory, task 6 adds a backlog admission cap and trims only history older than the oldest pending or unread consumer-group entry. An entry still queued or pending must remain in the stream; an operator purge is a separate deliberate cancellation. The backlog cap must be atomic under concurrent enqueues and reconciled after crashes, rather than relying on a counter that can leak permanently. This is the narrow part of F8 needed to make F3's bounded-stream guarantee true; downstream token buckets and rate limits remain outside this feature.

## Reviewable implementation tasks

Complete each row as one coherent change and commit. Run its focused checks, report results, and stop for review before continuing.

| Task | Change | Focused validation |
|---|---|---|
| **1. Runtime contract and packaging** | Add typed worker config, unique instance identity, trusted handler registry/loader and manifest, stream discovery/queue scope, Redis worker registry, and correct `apps/worker` package/Docker/Compose wiring. Keep production dispatch disabled until recovery and safe retention are integrated in task 6; earlier tasks exercise dispatch in tests. | Unit tests for config/registry/handler resolution and a worker image boot smoke test. |
| **2. Atomic claim and transport** | Add Redis consumer group create/read/ack primitives and the project-scoped Postgres claim transaction. Enforce pause, priority, free slots, and state checks; increment the attempt and set an owner/lease with database time. | Two workers racing for one job produce one winning execution claim; cancelled and stale pointers do not execute; project isolation holds. |
| **3. Execute, outcome, acknowledgement** | Rehydrate offloaded payloads, call the registered handler, store fenced success/failure plus attempt in one transaction, then `XACK`. Add a simple test handler and end-to-end immediate-job proof. | Success/failure, missing blob, unknown handler/version, and crash between commit and ack; attempt history is exact. |
| **4. Lease, timeout, and drain** | Add 5-second batched heartbeat, owner/attempt fencing, timeout/cancellation, capacity control, SIGTERM drain, operator drain command, and killable execution for CPU/blocking handlers. | Long job outlives one lease without reclaim; stale worker cannot commit; timeout and shutdown release work; slots never exceed configured capacity. |
| **5. Reaper** | Introduce the control-loop app with Postgres advisory-lock leadership and a 5-second expired-lease loop. Record reclaimed attempts, increment counter, requeue or park after three, and handle orphan Redis pending entries. | Two leaders do not reclaim twice; worker `kill -9` is recovered; a poison job parks after three reclaims. |
| **6. Redis reconstruction and retention** | Add the 60-second reconciler for missing/stale pointers and Redis wipe, remove unsafe blind `MAXLEN ~` behavior, add atomic bounded backlog admission and trim only entries safe to remove. | Redis wipe, individual pointer deletion, trim pressure, and API commit/Redis failure recover without permanent stuck jobs or unbounded stream growth. |
| **7. Operations and proof** | Add worker/reaper/reconciler metrics, structured job context, runbook, deployment example, and the F3 chaos/load proof. | Enqueue 10,000, kill random workers every two seconds for one minute, reach a recorded terminal outcome for every job, report duplicate executions, and show zero missing jobs. |

Task 1 is the **next implementation task**. It creates the runtime contract and packaging only; it does not start consuming production work. A later task can split further if its focused review becomes too large, but it must not pull in unrelated F4/F5/F8 features.

## Likely files and interfaces

- `apps/worker/src/relay_worker/config.py`, `main.py`, and focused modules under `runtime/`, `consumer/`, `execution/`, `lease/`, and `outcome/` as named in the folder structure. Do not create every listed module preemptively; add one when its task needs it.
- `apps/worker/pyproject.toml`, `Dockerfile`, `infra/compose/docker-compose.yml`, and worker environment examples for shared package installation, handler module configuration, unique IDs, capacity, and graceful stop.
- `packages/db/src/relay_db/transactions/{claim,complete,reclaim}.py` and the existing job/attempt repositories. Their public operations take a project-scoped unit of work and return an explicit won/lost/stale result; callers never write job state directly.
- `packages/redis/src/relay_redis/streams/{consumer,acknowledge,reclaim}.py`, `packages/redis/src/relay_redis/workers/registry.py`, and `keys.py`. The stream wire payload remains a job pointer; no payload or authoritative outcome goes into Redis.
- `apps/control-loops/src/relay_control/` and its package/Compose files when task 5 begins. Only its elected leader runs reclaim and reconciliation; do not place those loops in every worker.
- `apps/api/src/relay_api/api/v1/workers.py` and a matching service/schema only for the operator drain command. Add a narrowly scoped permission and authorization test rather than exposing a raw Redis command.
- Tests in `apps/worker/tests/`, `tests/integration/{postgres,redis,worker,control_loops}/`, and `tests/chaos/` as each task lands. Update `docs/current-implementation-handbook.md` and a handler idempotency example after behavior exists.

No database migration is planned initially: the F2 job row already has `attempt`, `lease_owner`, `lease_expires_at`, `reclaim_count`, `timeout_seconds`, and `lease_seconds`; `job_attempts` already stores completed/reclaimed outcomes. If a task proves a schema gap, add a dedicated migration in that task and preserve existing partition/RLS conventions.

## Open technical checks before task 1 closes

- **Handler deployment:** confirm the supported callable signatures and whether synchronous CPU handlers require a per-job child process to meet the ten-second hard-kill rule. `asyncio` cancellation alone cannot forcibly stop arbitrary blocking Python code. Do not claim hard-kill support from a plain `ProcessPoolExecutor` without a test that kills one task without corrupting the pool.
- **Backlog safety:** the producer currently uses `XADD MAXLEN ~ 100000`; Redis may trim an unprocessed or pending pointer. Remove that option before enabling consumption, then task 6 must add the admission/cleanup policy whose concurrent enqueue behavior and memory bound are measured. Until then, do not label the system production safe.
- **Consumer compatibility:** all consumers draining a queue must be able to run the queue's deployed handler versions, or the pool needs explicit routing. The first version documents and validates a homogeneous manifest per queue; rolling upgrades with incompatible manifests are a separate design task.
- **Unknown handler grace:** choose and document one configurable duration during task 1, then prove a handler deployed inside the grace window runs and a genuinely unknown handler parks afterward. Do not park merely because the Redis worker registry was wiped or is temporarily unavailable. No worker should repeatedly execute or burn attempts on an unknown handler.
- **Metrics ownership:** use existing `packages/observability` patterns. At minimum expose claimed, completed, failed, timed out, reclaimed, parked, lease-renewal failure, Redis pending depth, oldest queued age, worker liveness, and duplicate execution count without high-cardinality `job_id` labels.

## Definition of done

1. The worker image starts with the real DB/Redis/domain/storage dependencies, registers a unique identity and handler manifest, and consumes newly created project queues without unscoped Postgres reads.
2. Immediate jobs move through `queued → running → succeeded/failed/parked` with one durable attempt record per execution or reclaim. Acknowledgement never precedes the Postgres commit.
3. Heartbeats extend only currently owned leases; timeouts remain independent; old owners cannot renew, finish, or acknowledge a reassigned attempt.
4. Queue pause, cancellation, priority order, worker drain, prefetch one, and concurrency limit have focused tests.
5. A single elected reaper recovers expired leases and parks jobs after three reclaims. Reconciliation restores dispatch after failed indexing, trimming, or a Redis wipe.
6. Backlog growth is bounded without deleting unread/pending work, and the crash/Redis-loss proof reports zero missing jobs plus the real duplicate count.
7. Each task passes its relevant unit/integration tests and applicable `ruff`/`mypy` checks. The final feature runs the F3 chaos test against a live Postgres/Redis stack; skipped tests are reported as unverified, never as passed.
