# RELAY — Distributed Job Queue Engine

**Build spec v2.** Self-hosted background job platform.
This spec describes the finished system. For what runs today, see [the implementation handbook](docs/current-implementation-handbook.md).
Postgres is the source of truth. Redis is the hot transport. Python worker pool. FastAPI control plane. React observability dashboard.

**Stack:** FastAPI · Redis 7 Streams · PostgreSQL 15+ · React + TypeScript · WebSocket · OpenTelemetry

---

## Ground rules — these apply to every feature

**P1 — Postgres owns truth, Redis owns speed.**
Every state change commits to Postgres first. Redis holds only what makes dispatch fast: stream entries, delay sets, rate buckets, worker registry. Wiping Redis must be fully recoverable.

**P2 — At-least-once delivery. Never claim exactly-once.**
A job runs at least once. Under crashes it may run twice. Handlers must be idempotent, and the docs must say this in plain words.

**P3 — Park, never drop.**
Unknown handler, oversized payload, bad schema, repeated worker crashes — the job goes to a `parked` state a human can inspect. Nothing is ever silently discarded.

**P4 — Everything must survive `kill -9` at any instant.**
Any component, any moment. A crash cannot be recognized until its lease expires, so the system must return to a consistent state within one lease period plus one reaper cycle.

**P5 — No state change without a row write and a metric.**
If it happened, it's in Postgres and it's on a graph.

---

## Targets to design against

| Dimension | Target |
|---|---|
| Enqueue latency | p99 under 25 ms |
| Dispatch latency, queued to running | p95 under 100 ms at idle |
| Throughput | 5,000 jobs/sec sustained |
| Durability | Zero loss on worker `kill -9`, proven by chaos test |
| Max payload | 256 KB inline, 10 MB via blob offload |
| Retention | 30 days hot, then archived |

---

# F0 — Foundations `build first`

Scaffolding that makes everything after it reproducible. Skipping this costs you a week later.

**Steps**

1. **One-command local stack.** Docker Compose with Postgres, Redis, API, worker, dashboard. A fresh clone reaches a working enqueue in under five minutes.
2. **Migrations from commit one.** Alembic. No hand-run DDL, ever, not even in dev.
3. **Typed config.** Pydantic settings loaded from env, validated at startup. Missing variable equals a loud crash on boot, not a mystery at 3am.
4. **Structured logging.** JSON lines with `request_id`, `job_id`, `project_id`, `worker_id` bound on every log inside a job.
5. **CI pipeline.** Lint, strict type-check, tests, coverage gate. Red build blocks merge.
6. **Makefile.** `make up`, `make test`, `make load`, `make chaos`.

**Done when:** a teammate clones the repo and enqueues their first job in two commands with no README archaeology.

---

# F1 — Auth, Tenancy & RBAC `build first`

Everything hangs off tenant scoping, so this lands before any queue logic.

**Steps**

1. **Organizations, users and projects.** Email plus password, bcrypt hashed. Users are global — one account, many orgs — so a contractor working for two customers has one login. A user joins an organization through an `org_membership` row and a project through a `membership` row; each carries its own role.
2. **Two role scopes.** Org roles govern the organization: OrgOwner handles billing and deletion, OrgAdmin creates projects and invites people, OrgMember simply belongs. Project roles govern the data: Owner deletes the project, Admin manages keys and queues, Member enqueues and replays, Viewer reads only.
3. **JWT path for the dashboard.** 15-minute access token, rotating refresh token.
4. **API key path for the SDK.** Format `rly_live_` plus 24 random characters. Stored as a hash. The visible prefix is kept in clear so the UI can show which key is which.
5. **Project scoping in the data layer.** Every queue and job table carries `project_id`, and middleware injects it into every query. `projects.org_id` is the only place the org tier touches the hot path — job tables never carry an `org_id`.
6. **Invitations.** Single-use tokens, hashed at rest, seven-day expiry, bound to the invited email. An org invite creates the account; a project invite requires the invitee to already be an org member.

**Must handle**

- **An org role grants zero data access.** An OrgAdmin can create a project and add themselves to it, but that self-grant is an audited event. There is no path to a job payload that does not go through a project membership row. Skip this and you cannot answer "who read this?" during an incident.
- **Scoping enforced below the middleware.** Postgres row-level security with a per-request setting *and* a repository base class where a query is impossible to build without a scope. Two independent layers, one of them enforced by the database itself. A single forgotten filter is a cross-tenant leak — do not leave it to discipline.
- **Refresh token reuse detection.** If an already-rotated refresh token is presented, revoke the entire token family and force re-login. That's a stolen-token signal.
- **Key rotation with overlap.** Create the new key, run both, then revoke the old. Every key tracks `last_used_at` so you can prove a key is dead before killing it.
- **Instant revocation.** Auth checks a short-TTL revocation cache, not an hour-long one. A leaked key must die in seconds.
- **Audit log.** Append-only record of every privileged action: key created or revoked, job replayed, queue paused or purged, member role changed.
- **Return 404, not 403,** for another organization's or another project's resources. A 403 confirms the resource exists. Inside a project you do belong to, insufficient role is a 403 — you already know it is there.
- **Escalation guards.** Nobody grants a role above their own or edits their own role. The last OrgOwner and the last project Owner cannot be demoted or removed, or you get an orphaned tenant nobody can administer.
- Login and key-auth endpoints get their own aggressive rate limit.

**Done when:** a test authenticates as project A and gets 404 on every single project-B resource, including nested ones; the same holds across organizations, even for an OrgOwner; and an OrgAdmin with no project membership gets 404 on that project's jobs.

---

# F2 — Core Queue & Job Model

The minimum viable engine. Enqueue in, execute out — but with the write ordering that makes it safe.

**Steps**

1. **Named queues per project.** Created implicitly on first use. Examples: emails, reports, webhooks.
2. **Per-queue defaults.** Max attempts, job timeout, lease duration, default priority, rate limit, max depth.
3. **Job record.** Handler name, JSON payload, metadata, priority, attempt counters, timing fields, trace id, who enqueued it.
4. **Enqueue write order — this order is not negotiable.** Claim the idempotency key, offload the payload if oversized, insert the job row, commit the Postgres transaction, *then* index into Redis. If the Redis step fails the job is already durable and the reconciler will pick it up.
5. **Transport.** Redis Streams with consumer groups, one stream per queue per priority lane. Stream size is bounded by backlog admission, and only entries that are safe to remove are trimmed. Unread or pending work is never trimmed. Postgres holds all history.
6. **Read endpoints.** Fetch a job by id with its full attempt history. List jobs with filters on status, handler, queue and date, using cursor pagination.

**Must handle**

- **Why Streams and not lists.** A list pop removes the job before you can record the claim. If the worker dies in that gap the job is gone with no trace. A stream entry stays in the consumer group's pending list until it is explicitly acknowledged, and stale entries can be auto-claimed. That single property removes the biggest correctness footgun in the project.
- **Idempotency.** Key is scoped to project plus queue, with a default 24-hour window. Repeat submissions return the original job and a 200, not a 201. Because the jobs table is partitioned, the dedupe index lives in its own small table with an expiry column.
- **Payload offload.** Above 256 KB the body goes to blob storage and the job row keeps a reference. Above 10 MB, reject at submit.
- **Payload validation at submit.** Optional JSON Schema per handler. A bad payload should fail with a 400 at enqueue, not blow up in a worker three hours later.
- **Queue pause and resume.** A paused queue still accepts enqueues but workers stop draining it. You will need this escape hatch during an incident.
- **Purge requires a confirmation token.** It should be hard to do by accident.

**Done when:** the same idempotency key submitted 100 times concurrently produces exactly one job row and 99 responses pointing at it.

---

# F3 — Worker Pool

The execution layer. This is where the lease mechanic lives, and the lease is the most important idea in the project.

**Steps**

1. **Registration on boot.** Worker id, host, PID, version, concurrency, and a manifest of which handlers it can run.
2. **Fetch loop.** Drain priority lanes in strict order. Non-blocking reads on the top three lanes, then a short blocking read on the lowest lane so an idle worker parks instead of spinning.
3. **Claim sets a lease.** On claim the job gets a lease deadline, default 60 seconds, configurable per queue.
4. **Heartbeat every 5 seconds.** The heartbeat does two things: refreshes the worker's liveness entry in Redis, and **extends the lease on every job that worker currently holds** in one batched Postgres transaction. These are two stores, so this is not one atomic step. The Postgres lease decides reclaim; Redis liveness is diagnostic.
5. **Concurrency slots.** Configurable per worker. Async slots for I/O-bound handlers, a process pool for CPU-bound ones.
6. **Per-job timeout enforced by the worker itself.** Soft cancel first, ten-second grace, then hard kill. The worker records the timeout outcome — the reaper should not be the one discovering it.
7. **Graceful shutdown on SIGTERM.** Stop fetching, let in-flight jobs finish up to a grace period, return the remainder to the queue, deregister, exit clean.

**Must handle**

- **Lease renewal is what prevents double execution.** Without it, a ten-minute job under a sixty-second visibility timeout gets requeued while it is still running, and now two copies are doing the same work. This is the single most common bug in homemade queues.
- **Poison-pill guard.** Every time a job's lease expires and it gets reclaimed, increment a reclaim counter. After three reclaims, park it. A job that reliably crashes its worker will otherwise walk through your entire fleet killing each machine in turn.
- **Unknown handler means park, not fail.** If no worker in the fleet declares a handler, park the job after a grace window so it can be replayed once the right worker deploys.
- **Prefetch of one by default.** Prefetching a batch into worker memory is how you lose a batch when the process dies. Make it configurable, keep the default honest.
- **Never trust the worker's clock** for deadlines. Compute every deadline from the database or Redis server time.
- **Drain command.** An operator can tell a worker to stop fetching and finish what it holds, without killing it.

**Done when:** the chaos test passes — enqueue 10,000 jobs, kill a random worker every two seconds for a minute, and every job reaches a terminal state with zero losses. The count of jobs that ran more than once is reported rather than hidden; a small non-zero number is at-least-once being honest.

---

# F4 — Priority Lanes with Aging

Not all jobs are equal, and urgent work jumps the line without starving the rest.

**Steps**

1. **Four levels.** Critical, high, normal, low. One stream per level per queue.
2. **Strict drain order.** Workers empty higher lanes fully before touching lower ones.
3. **Priority set at enqueue,** overridable, with a per-queue default.
4. **Anti-starvation by aging.** Long-waiting jobs get promoted a lane at a time based on how long they've waited.

**Must handle**

- **Aging beats a skip counter.** A global "force-drain one low job after N skips" counter is not fair per-job and is a nightmare to tune. Aging is per-job, bounded, and you can explain it on a whiteboard in one sentence — which matters when someone asks about it in an interview.
- The aging interval is configurable per queue. Document the worst-case wait it guarantees.

**Done when:** the queue is saturated with critical work for thirty minutes and no low-priority job waits longer than three aging intervals.

---

# F5 — Retries & Dead Letter Queue

Failure handling is the entire reason this system exists.

**Steps**

1. **Exponential backoff with full jitter.** Randomise across the whole backoff window, not a small wobble around it.
2. **Attempt limits.** Per job, with a per-queue default and a hard per-project ceiling.
3. **Delayed retries via a sorted set** scored by the timestamp the job becomes due.
4. **A promoter loop** moves due entries from the delay set into the live stream, atomically.
5. **Exhausted jobs land in the DLQ** with the full error and stack trace from every attempt.
6. **Replay from DLQ,** single job or bulk.

**Must handle**

- **Classify errors, don't blindly retry.** Four buckets: retryable transient failures back off and retry; rate-limited responses honour the retry-after hint and do not burn an attempt; permanent failures like validation errors go straight to the DLQ instead of wasting five attempts; anything unrecognised is treated as retryable and logged loudly.
- **Full jitter is not optional.** When five thousand jobs fail at the same instant against a downstream that just went down, equal-spaced backoff sends all five thousand back at the same moment. Repeatedly.
- **Attempt history is its own table.** Never overwrite attempt one's stack trace with attempt two's. The trail is the whole debugging value.
- **Bulk replay is itself a job.** Re-enqueueing fifty thousand dead rows inside a request handler will time out half-finished. Replay must be throttled, resumable and cancellable, and the UI polls its progress.
- Replay resets the attempt counter but preserves the original attempt history and records what it was replayed from.

**Done when:** a handler raising a validation error reaches the DLQ after exactly one attempt, and a handler raising a connection error reaches it after the full attempt count with verifiably increasing gaps.

---

# F6 — Job Dependency Chaining `the differentiator`

Turns a queue into a workflow engine. This is what makes RELAY more than a Celery clone.

**Steps**

1. **Declare dependencies at enqueue.** A job can list parent job ids.
2. **Child starts blocked** with a counter set to its number of parents.
3. **On parent success, decrement the counter** on every child in one atomic statement. Children whose counter hits zero become queued immediately.
4. **Cycle detection at submit time.** Reject with a conflict response and name the offending path.
5. **Fan-out and fan-in both supported.** One parent to many children, and many parents to one child.
6. **Parent failure policy.** Default cancels the child and cascades transitively. The alternative releases the child anyway and hands it the parent outcomes.

**Must handle**

- **Counter-based readiness, never polling.** Do not scan for "are my parents done yet." Decrement on completion, and the work is proportional to the number of children, not the number of jobs in the system.
- **Depth and width caps.** Something like depth 32 and fan-out 1000. An unbounded DAG is a denial of service you run against yourself.
- **Result passing.** Small parent results travel inline to the child; large ones go to blob storage with a reference.
- **Orphan sweep.** If the process dies between decrementing the counter and flipping the status, a blocked job with all-terminal parents is stranded. The reconciler must find and release these.
- Cancellation of a parent cascades to the whole downstream subtree, once, without cycles.

**Done when:** a 200-node diamond DAG completes in valid topological order, exactly once per node, even when the leader process is killed mid-execution.

---

# F7 — Scheduled & Recurring Jobs

Cron, but with the same retry and observability guarantees as everything else.

**Steps**

1. **One-off delayed jobs** with a run-at timestamp, held in the delay set.
2. **Cron expressions** for recurring schedules, plus a simple interval shorthand.
3. **Timezone stored per schedule,** and next-run computed in that timezone.
4. **A cron loop** fires due schedules and computes the next occurrence.
5. **Manual trigger** — fire a schedule now, without waiting.

**Must handle**

- **Leader election, or every cron fires twice.** The cron loop, the promoter, the reaper, the reconciler and the retention job all run on exactly one process, elected by a Postgres advisory lock. If that process dies its connection drops and the lock releases automatically — no stale-lock cleanup needed.
- **Idempotent firing.** The job generated for a schedule carries an idempotency key derived from the schedule id plus the exact fire time. A leader failover in the middle of a fire cannot produce two jobs.
- **DST is a real decision.** A 2am daily job on a spring-forward day either skips or shifts. Pick one, write it in the docs, test it.
- **Misfire policy** for when RELAY was down across a scheduled time: skip to the next occurrence by default; optionally run one catch-up; optionally run all missed occurrences, which needs an explicit opt-in and a cap because it can produce thousands of jobs at once.
- **Overlap policy** for when the previous run is still going: skip, queue behind it, or allow concurrent.

**Done when:** killing the leader at the exact moment a cron fires produces exactly one job for that fire time.

---

# F8 — Rate Limiting, Throttling & Backpressure

Protects downstream services from your own workers, and protects RELAY from its users.

**Steps**

1. **Token bucket per queue** — a ceiling on how many jobs may *start* per second, refilled lazily and updated atomically.
2. **Optional per-project ceiling** across all its queues.
3. **Concurrency cap** — a limit on how many jobs of one type may be *running* at once.
4. **Throttled jobs go back to the delay set** with jitter, and do not consume an attempt.

**Must handle**

- **Rate limit and concurrency cap are different controls.** One answers "how many can start per second," the other answers "how many can be in flight." People conflate them and then wonder why a slow downstream still gets buried.
- **The concurrency counter must be crash-safe.** If you only decrement on completion, a hard-killed worker leaks a slot permanently and the cap silently ratchets down to zero. Derive the true in-flight count from the pending entries and have the reaper reconcile the counter every cycle.
- **Backpressure at enqueue.** Each queue has a maximum depth; over it, reject with a 429 and a retry-after hint. A queue that accepts infinite work is a queue that eventually exhausts Redis memory.
- **Circuit breaker per handler.** If a handler's failure rate crosses a threshold over a rolling window, open the breaker and pause dispatch of that handler for a cooldown. Grinding fifty thousand doomed jobs through a downstream that is already on fire helps nobody.

**Done when:** a queue limited to 10 jobs/sec, fed 10,000 jobs at once, starts them at 10/sec with no failures, no attempt consumption, and no thundering herd on recovery.

---

# F9 — Observability `backend first, then frontend`

The part that makes it demo-able. Build the telemetry before the UI, because the UI is just a view over it.

**Steps**

1. **Prometheus metrics endpoint.** Enqueued and completed counters by queue, priority and outcome. Job duration histogram. Queue depth gauge. Dispatch latency. Workers online. Lease reclaims. DLQ size.
2. **Distributed tracing across the queue boundary.** The trace context from the enqueueing HTTP request is stored on the job and restored as the parent span when the worker executes it — one continuous trace from API request through queue wait to handler execution.
3. **Event stream.** Every state transition publishes an event; the API fans it out to dashboard clients over WebSocket.
4. **Then build the views.**

**Dashboard views**

| View | Contents |
|---|---|
| **Overview** | Throughput sparkline, failure rate, DLQ size, workers online, age of oldest queued job |
| **Queues** | Depth per lane, throughput per minute, p50/p95/p99 latency, pause and resume, rate-limit editor |
| **Jobs** | Live virtualized feed, filters on status, handler, queue and date, cursor pagination |
| **Job detail** | Full timeline, per-attempt stack traces, payload, dependency graph, cancel and replay |
| **Workers** | Online list, heartbeat age, current jobs, version, handler manifest, drain button |
| **DLQ** | Grouped by error class and handler, with bulk replay and a progress bar |
| **Settings** | API keys, members and roles, queue defaults, audit log |

**Must handle**

- **Trace propagation is the headline.** Almost no portfolio job queue carries a trace across the async boundary. This is the detail that gets remembered.
- **Throttle rendering to about ten frames per second.** At five thousand jobs per second a naive live feed locks the browser tab. Buffer events and flush on an interval.
- **Reconnect properly.** Exponential backoff, then refetch state on reconnect rather than assuming the delta stream had no gaps. Redis Pub/Sub keeps no history, so events missed during a disconnect cannot be resumed.
- **Group the DLQ.** Fifty thousand dead jobs from one bug is one problem, not fifty thousand rows.
- **Cursor pagination everywhere,** never offset — offset pagination on a large jobs table gets slower the further you scroll.
- Empty, loading and error states on every view. It's the thing everyone skips and every reviewer notices.

**Done when:** a single trace view shows the full path of one job from HTTP request to handler completion, including its queue wait time.

---

# F10 — Hardening & Operations `this is the hireable part`

**Steps**

1. **Build the five control loops** and confirm each has an owner, an interval and a metric:

| Loop | Interval | Job |
|---|---|---|
| Promoter | 250 ms | Move due delayed entries into live streams |
| Reaper | 5 s | Reclaim expired leases, park repeat offenders, fix counters |
| Cron | 1 s | Fire due schedules |
| Reconciler | 60 s | Repair Postgres-to-Redis drift in both directions |
| Retention | daily | Roll partitions, archive, sweep expired dedupe keys |

2. **Partition the jobs table by month.** Partial indexes on live rows only. Age data out by detaching partitions, never by deleting rows — an unpartitioned jobs table dies around fifty million rows and takes the dashboard with it.
3. **Prove the Redis wipe drill.** Flush Redis in a test environment and confirm the reconciler rebuilds every queue with zero job loss. Record it.
4. **Document the degradation matrix.**

| Component down | Behaviour |
|---|---|
| Redis | Enqueue commits to Postgres and returns 201 with `indexed: false` after short retries; committed jobs safe; recovery via reconciler |
| Postgres | Enqueue 503; workers finish in-flight then idle; nothing lost |
| Leader | Loops pause briefly; a replica takes the lock and resumes; no double-fire |
| One worker | Its leases expire, reaper requeues, throughput dips |

5. **Security pass.** Payload encryption at rest for queues flagged sensitive. Per-handler redaction paths so secrets never reach logs or the dashboard. Signed webhook callbacks with a replay window. Dependency scanning in CI.
6. **Rolling upgrades.** Jobs record the handler version they were enqueued against; a worker refuses versions it doesn't implement rather than running the wrong code against an old payload shape.
7. **Health endpoints.** Liveness, and a readiness check that confirms dependencies are reachable and migrations are current.
8. **Runbooks.** One page each for: queue backed up, DLQ spike, worker fleet down, Redis memory pressure. Each with the exact command to run.
9. **Published load numbers** from a real load test, and the chaos suite wired into CI.

**Done when:** all four proof tests pass in CI — worker killed mid-job completes anyway; Redis flushed and fully rebuilt; leader killed mid-cron produces exactly one job; a handler that crashes its worker gets parked after three reclaims while the fleet stays healthy.

---

# Build order and milestones

| Phase | Features | Milestone | Effort |
|---|---|---|---|
| **1 — Skeleton** | F0, F1, F2, F3 | End-to-end enqueue and execute on one worker | ~2 weeks |
| **2 — Correct** | F5 plus lease, reaper, reconciler | **Chaos test passes. This is the real milestone.** | ~1.5 weeks |
| **3 — Production** | F4, F7, F8 | Priority, cron, throttling, backpressure | ~2 weeks |
| **4 — Differentiator** | F6 | DAG chaining with cancellation cascade | ~1.5 weeks |
| **5 — Visible** | F9 | Metrics and traces first, then the UI | ~2 weeks |
| **6 — Hireable** | F10 | Runbooks, load numbers, chaos in CI | ~1 week |

**The ordering correction that matters.** The obvious instinct is to finish the dashboard because it's the visible part. It isn't the valuable part. A dashboard over an engine that loses jobs under `kill -9` is a frontend project. An engine that provably doesn't lose jobs, with a short README section explaining the lease and the reaper, is a distributed systems project. Phase 2 before any more dashboard polish.

---

# Explicitly out of scope for v1.0

State this in the README. Knowing what you left out reads as judgement, not as gaps.

**Deferred by design**
- Multi-region and cross-datacenter replication — single region only
- Redis Cluster sharding — one Redis with a replica, with append-only persistence enabled only after the wipe drill passes without it; sharding is a v2 problem with a documented plan
- Non-Python workers — the wire protocol is documented so a Go or Node worker is possible, but not shipping one
- Billing, quotas and usage metering — the `organizations` tier they anchor to ships in F1, but nothing meters or charges in v1
- Platform staff administration — no cross-org operator role. When it lands it gets its own credentials, mandatory MFA, and time-boxed impersonation logged to an audit the customer can read. Never an `is_superuser` flag on `users`
- SSO, SAML and social login — email plus password only

**Impossible, and said so**
- Exactly-once delivery. At-least-once with idempotent handlers, by design.

**Deferred but seamed for**
- AI and agentic job types. The seams that keep this cheap to add later already exist in this spec: the handler abstraction, per-job timeouts with lease renewal for long-running work, result passing between DAG nodes, and streaming output over the existing WebSocket. Nothing here needs rewriting to support it.
- Hosted multi-org operation. The `organizations` tier ships in F1 even though v1 deploys self-hosted with a single org created at bootstrap. Billing, quotas, SSO and staff administration all anchor to it. Adding a tier *above* the permission checks later would mean rewriting every one of them; adding features beneath a tier that already exists is additive.

---

# The README pitch

Write this last, but write it. It is the interview.

> RELAY is a self-hosted distributed job queue. Postgres is the source of truth, Redis is the transport. It survives worker crashes through leases and a reaper, survives a total Redis wipe through a reconciler, and survives leader failover without double-firing crons. Every job carries a distributed trace from the HTTP request that enqueued it through to the handler that ran it. Five thousand jobs per second, p99 enqueue under 25 milliseconds, zero jobs lost across a sixty-second chaos run — all reproducible with one make command.

Everything above is how you earn the right to say that truthfully.
