# F2 — Core Queue & Job Model — Implementation Plan

**Spec:** [RELAY-SPEC.md § F2](../../RELAY-SPEC.md) (lines 88–110) · **Structure:** [folder structure](../../RELAY-production-folder-structure.md) · **Architecture:** [write path + key layout](../../ARCHITECTURE.md)
**Goal:** One ordered write path — claim, offload, insert, commit, index — turns an HTTP request into a durable job in under 25 ms, and every column F3 through F10 will write to exists the day F2 merges.

## Scope boundary — build the engine, seam the rest

F1 ended with a typed `ProjectContext` on every request and no queue logic behind it. F2 fills that in and stops at the edge of execution.

**F2 builds:** the `queues`, `jobs`, `job_attempts`, `idempotency_keys` and `handler_schemas` tables with their RLS and partitioning; the job state machine; the enqueue transaction; the Redis stream producer; cursor-paginated reads; queue defaults, pause/resume and purge; payload offload; and `packages/storage`.

**F2 does not build:** anything that *reads* work off a stream. No claim, no lease renewal, no heartbeat, no reaper, no promoter, no cron, no reconciler, no retention loop, no token bucket, no aging, no dependency graph. F2 is the producer half of a producer/consumer pair, and every consumer-side column it lands is written by nobody until F3 arrives.

**The rule that keeps the seam honest:** F2 may create a column, a state, or a Redis key shape that nothing writes yet, but it may not create a Redis key that nothing writes *and* nothing documents an owner for. A key with no writer is a key someone will assume is maintained. Every deferred key is named in the table below with the feature that will add it, and is deliberately absent from `keys.py` until then.

**F2 adds zero new `Permission` members.** `apps/api/src/relay_api/auth/permissions.py` already defines `JOB_ENQUEUE`, `JOB_CANCEL`, `JOB_REPLAY`, `QUEUE_PAUSE`, `QUEUE_PURGE`, `QUEUE_EDIT_DEFAULTS` and `PROJECT_READ`, with both role matrices. Every F2 route maps onto one of them. This is a design confirmation rather than an oversight — F1's vocabulary was written from the spec's own capability list, and F2 *is* that list. The one judgement call is handler-schema registration, which F2 gates on `QUEUE_EDIT_DEFAULTS`: registering a schema changes how future submissions are validated, which is the same class of act as changing `max_attempts`, and inventing `SCHEMA_REGISTER` would have added a permission with an identical role matrix to one that already exists.

**The consequence of api_keys having no `role` column.** F1 fixed API keys at `Role.MEMBER` and argued for it: the credential most likely to leak carries the least power. Member is exactly `JOB_ENQUEUE | JOB_CANCEL | JOB_REPLAY | PROJECT_READ`. So **pause, resume, purge, queue defaults and schema registration are dashboard-JWT-only operations** — there is no API-key path to any of them, and F2 must not add one. A leaked SDK key can flood a queue; it can never take one offline, destroy a backlog, or disable validation for a handler. Proved in `apps/api/tests/integration/test_queue_admin_http.py`: the same request that succeeds with an Admin JWT returns 403 with a valid API key.

## Data model

### Migration numbering — and where it diverges from the structure doc

The structure doc plans `0003_jobs`, `0004_attempts`, `0005_dependencies`, `0006_schedules`, `0007_idempotency`, `0008_audit`, `0009_partitions`, `0010_indexes`. That numbering is already dead, and F2 states its own plainly, exactly as the F1 plan did for `audit_log`:

| Migration | Contents |
|---|---|
| `0003_queues.py` | `queues` + unique `(project_id, name)` + every bound check constraint + RLS |
| `0004_jobs.py` | `job_state` enum type, `jobs` partitioned parent, three monthly partitions, a DEFAULT partition, RLS on parent **and every partition** |
| `0005_job_attempts.py` | `attempt_outcome` enum type, `job_attempts` partitioned parent, its partitions, RLS on each |
| `0006_idempotency.py` | `idempotency_keys` — unpartitioned, with `expires_at` |
| `0007_handler_schemas.py` | `handler_schemas` + unique `(project_id, handler)` + RLS |
| `0008_job_indexes.py` | the cursor index, the dispatch partial index, the filter partial indexes |

Four divergences, each for a reason:

1. **The doc's `0002_projects_tenancy` never existed.** F1 folded tenancy into `0001_initial_schema` and spent `0002` on `audit_log` append-only — the doc's `0008` slot. Every F2 number is therefore shifted down by one relative to the doc, and the doc's `0005_dependencies` / `0006_schedules` slots belong to F6 and F7, which land *after* F2's migrations, not before them.
2. **`queues` has no slot in the doc at all,** and it takes `0003` because every other F2 table references it.
3. **`0009_partitions` is merged into `0004_jobs`.** Partitioning is a property of `CREATE TABLE`, not something `ALTER TABLE` can add. A separate partitions migration means creating `jobs` unpartitioned and then rewriting the entire table to convert it — free on an empty schema, an outage on a live one, and a habit that will eventually be exercised on a live one. Partition at birth.
4. **`0010_indexes` becomes `0008_job_indexes` and keeps its position last, deliberately.** Indexes are the cheapest thing to get wrong and the easiest to change; keeping them in their own trailing migration means a later `CREATE INDEX CONCURRENTLY` fix never has to touch a table definition.

### RLS — the same shape F1 proved, applied to five more tables

Every F2 table is project-scoped and carries `project_id` and **no `org_id`**. That is F1's rule (spec F1 step 5: *job tables never carry an `org_id`*) and F2 does not bend it — one place tenancy resolution can go wrong, not two. Each table gets the identical three statements `0001_initial_schema.py` uses for `memberships` and `api_keys`:

```
ALTER TABLE <t> ENABLE ROW LEVEL SECURITY;
ALTER TABLE <t> FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON <t>
  USING (project_id = NULLIF(current_setting('app.project_id', true), '')::uuid);
```

`FORCE` matters for the same reason it did in F1 — the table owner bypasses a merely-enabled policy, and migrations run as the owner. The `NULLIF` matters for the same reason — a pooled connection whose `app.project_id` was set by an earlier transaction reverts to `''`, not `NULL`, and a bare cast on `''` raises instead of failing closed.

**`WITH CHECK` is deliberately omitted, and that is not a gap.** When a policy has a `USING` expression and no `WITH CHECK`, Postgres applies the `USING` expression as the `WITH CHECK` for INSERT and UPDATE. So an INSERT carrying another project's `project_id` is rejected by the same clause that hides another project's rows. F1 relies on this already; F2 relies on it on the write-heaviest table in the system.

### The partition problem, and how F2 answers it

Two hazards, both real, both called out because getting either wrong is silent:

**Hazard 1 — default privileges only follow tables created by role `relay`.** `infra/postgres/init/01-app-role.sql` grants `relay_app` DML through `ALTER DEFAULT PRIVILEGES FOR ROLE relay IN SCHEMA public`. A partition created at runtime by a control loop connecting as any other role would not inherit that grant, and the first insert into the new month would fail with `permission denied` at midnight on the first of the month. **F2's rule: partition DDL runs only in migrations, as role `relay`, never from application or loop code.** F10's retention loop will shell out to the same path (`scripts/db/partition.sh` in the structure doc) rather than issuing DDL over its own pooled connection. Proved in `tests/integration/postgres/test_job_partitions.py`: connect as `relay_app`, insert through the parent into a migration-created partition, succeed.

**Hazard 2 — RLS on a partitioned parent does not cover a partition addressed directly.** Querying through the parent applies the *parent's* policies and skips the children's; querying a partition by name applies only that partition's own. F2 therefore enables, forces and policies **every partition as well as the parent**, in the same statement block that creates it. The application layer never names a partition — all access goes through the parent — so this layer only ever fires for a psql session or a repair script, which is exactly the situation F1's "enforced by the database itself" argument was written for. Proved in the same test file: `SELECT * FROM jobs_2026_09` as `relay_app` with a foreign `app.project_id` returns zero rows.

**A DEFAULT partition ships with `0004`.** `0004` pre-creates the current month plus two ahead (`jobs_partition_months_ahead`, default 3), and a `jobs_default` catch-all. Without the default, an insert past the last declared range fails outright — the whole system stops accepting work because a daily loop that does not exist yet (F10) did not run. With it, a missed roll degrades to "rows land in the default partition and a metric goes red." The cost is bounded and known: attaching a new range partition that overlaps the default forces Postgres to scan the default to prove no rows belong in the new range. On an empty default that is instant, which it is whenever F10 rolls on time — so the cost is paid only in the case where the alternative was an outage.

### `jobs` — partitioned by RANGE on `created_at`, monthly

Primary key `(id, created_at)`. A partitioned table's primary key must include the partition key, which has a real consequence stated here rather than discovered later: **`id` alone is not enforced unique across partitions.** It is unique in practice — `uuid4` from the application — but the database does not guarantee it. The mitigation is to not need it: `GET /jobs/{id}` goes through the parent and becomes one index probe per live partition. With 30-day hot retention that is two or three partitions plus the default, so four index probes, sub-millisecond. The alternative — a composite external job id exposed to clients so the partition can be pruned — makes every SDK, every log line and every dashboard URL carry a timestamp to save three index probes. Not worth it.

| Column | Type | Purpose |
|---|---|---|
| `id` | `uuid` | **Application-generated**, not `gen_random_uuid()` — the idempotency claim needs the id before the job row exists |
| `created_at` | `timestamptz NOT NULL DEFAULT now()` | partition key, part of the PK, and the cursor's high-order component |
| `project_id` | `uuid NOT NULL` | RLS scope. No `org_id`, ever |
| `queue_id` | `uuid NOT NULL` | FK to `queues`, `ON DELETE RESTRICT` |
| `queue_name` | `text NOT NULL` | denormalized: a filter-by-queue list must not join, and the Redis key is built without a lookup |
| `handler` | `text NOT NULL` | a string in F2; F3's manifest gives it meaning |
| `handler_version` | `text NULL` | F10's rolling-upgrade seam |
| `payload` | `jsonb NULL` | inline, ≤ 256 KiB |
| `payload_ref` | `text NULL` | blob URI when offloaded |
| `payload_bytes` | `integer NOT NULL` | the measured canonical size the 256 KiB / 10 MiB decision was made on, recorded so the decision is auditable after the fact |
| `metadata` | `jsonb NOT NULL DEFAULT '{}'` | client-supplied, never interpreted by RELAY |
| `state` | `job_state NOT NULL` | Postgres enum, eight labels |
| `priority` | `smallint NOT NULL` | 0–3, as submitted — never modified |
| `priority_effective` | `smallint NOT NULL` | the lane the job actually sits in. F2 sets it equal to `priority` and never moves it; **F4 ages this column** |
| `attempt` | `smallint NOT NULL DEFAULT 0` | attempts started |
| `max_attempts` | `smallint NOT NULL` | snapshot of the queue default at enqueue |
| `timeout_seconds` | `integer NOT NULL` | snapshot |
| `lease_seconds` | `integer NOT NULL` | snapshot |
| `reclaim_count` | `smallint NOT NULL DEFAULT 0` | F3's poison-pill counter |
| `run_at` | `timestamptz NULL` | NULL means run now; set means `scheduled` and a delay-set score for F5/F7 |
| `lease_expires_at` | `timestamptz NULL` | F3 sets it; the reaper's sole authority |
| `lease_owner` | `text NULL` | worker id currently holding it |
| `started_at` / `finished_at` | `timestamptz NULL` | |
| `result` | `jsonb NULL` | F3 writes; F6 passes to children |
| `result_ref` | `text NULL` | offloaded large result (F6) |
| `dependency_count` | `smallint NOT NULL DEFAULT 0` | F6's readiness counter |
| `replayed_from` | `uuid NULL` | F5 sets |
| `cancel_requested_at` | `timestamptz NULL` | F2 writes on cancelling a `running` job; F3's worker honours it |
| `cancel_reason` | `text NULL` | `'operator'`, `'queue_purged'`, `'parent_failed'` |
| `trace_id` | `char(32) NULL` | W3C `traceparent` trace-id, hex |
| `span_id` | `char(16) NULL` | the enqueueing span, restored as parent in F9 |
| `trace_flags` | `smallint NULL` | sampled bit — dropping it loses the sampling decision across the async boundary |
| `enqueued_by_type` | `text NOT NULL` | `'user' \| 'api_key' \| 'schedule' \| 'replay'` |
| `enqueued_by_id` | `uuid NOT NULL` | polymorphic, **no FK** — same reason `audit_log.actor_id` has none: one column cannot reference two tables |
| `idempotency_key_hash` | `char(64) NULL` | so a job knows its own key without a join |
| `redis_indexed_at` | `timestamptz NULL` | NULL between commit and a successful XADD — **the reconciler's entire input** |
| `updated_at` | `timestamptz NOT NULL DEFAULT now()` | |

**Why `trace_id`/`span_id`/`trace_flags` and not the raw `traceparent` header.** F9's headline query is "show me every job in this trace," which is `WHERE trace_id = ?`. A raw header string is not usefully indexable and would have to be re-parsed on every read. Parsing once at enqueue costs a regex on a 55-character string.

**Why snapshot `max_attempts`, `timeout_seconds` and `lease_seconds` onto the job.** Editing a queue default must not retroactively change a job already queued or running — an operator lowering `max_attempts` during an incident would otherwise instantly dead-letter every in-flight job that had already used more attempts than the new value. Three smallint/int columns is the entire cost of that not happening.

Check constraints: `payload IS NULL <> payload_ref IS NULL` (exactly one), `priority BETWEEN 0 AND 3`, `priority_effective BETWEEN 0 AND 3`, `attempt >= 0`, `payload_bytes >= 0`.

### `job_attempts` — partitioned by RANGE on `created_at`, monthly

| Column | Type |
|---|---|
| `id` | `uuid` |
| `created_at` | `timestamptz NOT NULL DEFAULT now()` — partition key, part of the PK |
| `project_id` | `uuid NOT NULL` — RLS |
| `job_id` | `uuid NOT NULL` — indexed |
| `attempt_number` | `smallint NOT NULL` |
| `worker_id` | `text NULL` |
| `started_at` / `finished_at` | `timestamptz NULL` |
| `duration_ms` | `integer NULL` |
| `outcome` | `attempt_outcome NOT NULL` — `succeeded \| failed \| timed_out \| reclaimed \| cancelled` |
| `error_class` | `text NULL` — F9 groups the DLQ by this |
| `error_message` | `text NULL` |
| `error_stack` | `text NULL` |
| `error_category` | `text NULL` — F5's four buckets: `transient \| rate_limited \| permanent \| unknown` |
| `retry_after_seconds` | `integer NULL` — F5's honoured hint |

**No foreign key to `jobs`.** A foreign key referencing a partitioned table must reference its full primary key, which would force every attempt row to carry `job_created_at` and every join to use a two-column key. Worse, an FK blocks `DETACH PARTITION` on the referenced side, which is precisely how F10 ages data out. Attempt rows are orphan-tolerant by design; both tables are partitioned on the same monthly boundary and are aged out together.

**`(job_id, attempt_number)` is not a unique index either** — it could not be one across partitions without including `created_at`, which would defeat the point. Uniqueness comes from the write path instead: only the transaction that successfully compare-and-swaps `jobs.attempt` from *n* to *n+1* is allowed to write attempt *n+1*. Same pattern as the state CAS below — the guarantee lives in the update that already has to happen, not in a second index.

**F2 writes exactly zero rows to this table.** F3 and F5 do. It ships now because it is partitioned and its partitions must be rolled by the same retention machinery on the same schedule as `jobs` — discovering in F5 that a second partitioned table is needed means a second migration touching partition rolling, done twice, in two places. `GET /jobs/{id}` returns `attempts: []` in F2, and that is the endpoint's finished shape.

### `queues`

| Column | Type | Bounds |
|---|---|---|
| `id` | `uuid` PK | |
| `project_id` | `uuid NOT NULL` FK → `projects` `ON DELETE CASCADE` | RLS scope |
| `name` | `text NOT NULL` | CHECK `name ~ '^[a-z0-9][a-z0-9_-]{0,62}$'` |
| `max_attempts` | `smallint NOT NULL DEFAULT 5` | 1–25 |
| `job_timeout_seconds` | `integer NOT NULL DEFAULT 300` | 1–86400 |
| `lease_duration_seconds` | `integer NOT NULL DEFAULT 60` | 10–3600 |
| `default_priority` | `smallint NOT NULL DEFAULT 2` | 0–3 |
| `rate_limit_per_second` | `integer NULL` | ≥ 1 |
| `max_depth` | `integer NULL` | ≥ 1 |
| `paused_at` | `timestamptz NULL` | |
| `paused_by` | `uuid NULL` | |
| `created_at` / `updated_at` | `timestamptz NOT NULL` | |

Unique on `(project_id, name)`. Every bound above is a `CHECK` constraint *and* a Pydantic validator — the validator gives the caller a readable 400, the constraint means a bad value cannot enter through a repair script or a psql session either.

**The 10-second floor on `lease_duration_seconds` is not arbitrary.** F3's heartbeat fires every 5 seconds and extends every lease the worker holds. A lease shorter than two heartbeat intervals is a guaranteed spurious reclaim under any GC pause or network blip, which means guaranteed double execution of a job that was running fine.

### Per-queue defaults — stored versus enforced

| Default | F2 stores & serves | F2 enforces | Enforced by |
|---|:--:|:--:|---|
| `default_priority` | ✓ | ✓ — applied at enqueue when the caller omits `priority` | F2 |
| `paused_at` | ✓ | ✓ — Postgres truth plus the Redis flag; workers obey it | F2 writes, F3 obeys |
| `max_attempts` | ✓ | — | F5 |
| `job_timeout_seconds` | ✓ | — | F3 (the worker enforces its own timeout) |
| `lease_duration_seconds` | ✓ | — | F3 |
| `rate_limit_per_second` | ✓ | — | F8 |
| `max_depth` | ✓ | — | F8 (429 at enqueue) |

F2 enforces two of seven and that is the point. A defaults editor whose values nothing reads yet is not dead code — it is the one config surface every later loop reads instead of inventing its own. Shipping it now means F5 and F8 land as a loop plus a lookup, not a loop plus a migration plus a schema change plus a dashboard change.

### `idempotency_keys` — unpartitioned, deliberately

| Column | Type |
|---|---|
| `project_id` | `uuid NOT NULL` — RLS |
| `queue_id` | `uuid NOT NULL` |
| `key_hash` | `char(64) NOT NULL` — sha256 of the client's key |
| `job_id` | `uuid NOT NULL` |
| `job_created_at` | `timestamptz NOT NULL` |
| `expires_at` | `timestamptz NOT NULL` — indexed, for F10's sweep |
| `created_at` | `timestamptz NOT NULL DEFAULT now()` |

Primary key `(project_id, queue_id, key_hash)` — the unique index *is* the table's reason for existing, so it is the PK rather than a secondary index on a surrogate id.

**Why its own table rather than a unique index on `jobs`.** `jobs` is partitioned; a unique index on a partitioned table must include the partition key, so `UNIQUE (project_id, queue_id, idempotency_key_hash)` is simply not creatable there. Beyond that, the dedupe set has a 24-hour lifetime while jobs have a 30-day one — putting them in the same table means either sweeping rows out of a partition you are trying to age out whole, or keeping a dedupe index 30× larger than it needs to be.

**Why hash the key rather than store it.** A client-supplied idempotency key is unbounded free text and people put customer emails and order numbers in them. Hashing gives a fixed 64-byte index entry and keeps identifiable strings out of the database. `relay_security.hashing.hash_token` already does exactly this for API keys and invitations — same primitive, no new code.

**`job_created_at` is carried on purpose.** The repeat-submission path is the one that must stay under 25 ms, and it is the one path where the partition is known — one index probe rather than a probe per live partition.

### `handler_schemas`

`id`, `project_id` (RLS), `handler text`, `schema jsonb`, `created_at`, `updated_at`. Unique on `(project_id, handler)`.

Registered by a project Admin or Owner via `PUT /v1/projects/{pid}/handler-schemas/{handler}`, gated on `QUEUE_EDIT_DEFAULTS`. The schema is validated against the JSON Schema 2020-12 metaschema at registration — **a malformed schema fails once, at registration, rather than on every subsequent enqueue.** Compiled validators are cached in-process keyed by `(project_id, handler, updated_at)`; recompiling a schema per enqueue would eat a meaningful slice of the 25 ms budget for a value that changes roughly never.

No schema registered means no validation. Optional means optional — and it means a project can adopt validation one handler at a time without a flag day.

### `0008_job_indexes` — three indexes on the write path, the rest partial

| Index | Shape | Why |
|---|---|---|
| PK | `(id, created_at)` | forced by partitioning |
| cursor | `(project_id, created_at DESC, id DESC)` | the list endpoint's only ordering, satisfied by one index seek |
| dispatch / drift | `(project_id, queue_id, state) WHERE state IN ('queued','scheduled')` | the reconciler's "what is un-dispatched" query, and F8's depth count |
| filter: handler | `(project_id, handler, created_at DESC) WHERE state IN ('queued','scheduled','running')` | dashboard filter, live rows only |
| filter: state | `(project_id, state, created_at DESC) WHERE state IN ('queued','scheduled','running','parked')` | dashboard filter, live rows only |
| drift | `(project_id, created_at) WHERE redis_indexed_at IS NULL AND state = 'queued'` | the Redis-wipe repair query as one index scan, not a scan of fifty million rows |
| idempotency | PK on `idempotency_keys`, plus `(expires_at)` | claim, and F10's sweep |
| attempts | `(job_id, attempt_number)` non-unique | the job-detail read |

**The partial predicates are the whole trick, and they come straight from F10's instruction ("partial indexes on live rows only").** A job is `queued` or `running` for seconds and terminal for thirty days. A full index on `handler` would be 99.9% terminal rows — paying insert cost and cache residency for rows the dashboard's live filters never look at. The partial version shrinks to the working set, and Postgres removes a row from it for free when the state transition already writes the row.

Only three of these are maintained at insert time (PK, cursor, dispatch — a new job is always `queued` or `scheduled`), which is the number the 25 ms budget is built around.

## The job state machine

| State | Meaning | Quiescent? |
|---|---|---|
| `blocked` | waiting on unfinished parents | no — F6's decrement releases it |
| `scheduled` | not yet eligible; has a `run_at`; lives in the delay set | no — the promoter releases it |
| `queued` | indexed into a live stream, awaiting a worker | no |
| `running` | claimed, lease held | no |
| `succeeded` | the handler returned | **terminal** |
| `failed` | attempts exhausted, or a permanent error | **terminal** |
| `cancelled` | operator cancel, purge, or a cascade from a cancelled parent | **terminal** |
| `parked` | P3: unknown handler, poison pill, bad payload found post-submit | quiescent, not terminal |

**`parked` is quiescent, not terminal, and the distinction is load-bearing.** Terminal means the machine has no outgoing edge. `parked` has exactly one — replay — and it requires a human. Collapsing the two would make "park, never drop" indistinguishable from "fail", which is the exact thing P3 exists to prevent.

**There is no `dead_letter` state. The DLQ is a view: `state = 'failed'`.** With two states you have to define what separates them, and every consumer — the dashboard, replay, metrics, the retention sweep — has to check both and eventually one of them forgets. With one, "the DLQ" is a filter, and F5's replay is a single operation valid on any failed job. It also matches F9's dashboard spec, which asks for the DLQ *grouped by error class and handler* — a grouping over rows, not a separate store.

**There is no `retrying` state either.** A job waiting out a backoff and a job waiting for its cron time are in the same situation — not eligible, has a `run_at`, sits in the delay set — so both are `scheduled`. The dashboard tells them apart by `attempt > 0`. Adding `retrying` would force F5's promoter to handle two states with identical behaviour, and any state the promoter can forget about is a state where jobs stall.

### Legal transitions

| From | To | Trigger | Actor | Lands in |
|---|---|---|---|---|
| *(new)* | `queued` | enqueue, no parents, no future `run_at` | API | **F2** |
| *(new)* | `scheduled` | enqueue with a future `run_at` | API | **F2** (state + column) |
| *(new)* | `blocked` | enqueue with parent ids | API | F6 |
| `blocked` | `queued` | last parent succeeded, counter hit 0 | F6 decrement | F6 |
| `blocked` | `cancelled` | parent failed under the cancel policy | F6 | F6 |
| `scheduled` | `queued` | `run_at` reached | promoter | F5 / F7 |
| `scheduled` | `cancelled` | operator cancel or purge | API | **F2** |
| `queued` | `running` | worker claim, lease set | worker | F3 |
| `queued` | `cancelled` | operator cancel or purge | API | **F2** |
| `queued` | `parked` | no worker in the fleet declares the handler, after a grace window | reaper | F3 |
| `running` | `succeeded` | the handler returned | worker | F3 |
| `running` | `failed` | permanent error, or attempts exhausted | worker | F3 / F5 |
| `running` | `scheduled` | retryable error, backoff computed | worker | F5 |
| `running` | `queued` | lease expired, entry reclaimed | reaper | F3 |
| `running` | `parked` | third reclaim (poison pill) | reaper | F3 |
| `running` | `cancelled` | cancel honoured at a lease boundary | worker | **F2** requests, F3 honours |
| `failed` | `queued` | replay | API | F5 |
| `parked` | `queued` | operator replay | API | F5 |
| `cancelled` | `queued` | replay | API | F5 |

Every other ordered pair is illegal. Note there is no `succeeded → anything`: a replay of a succeeded job creates a **new job** with `replayed_from` set, rather than resetting the original — otherwise the attempt history of the original run is destroyed by the act of re-running it, which is the entire debugging value F5 exists to protect.

### Where the machine is enforced — three places, on purpose

**1. The domain, purely.** `packages/domain/src/relay_domain/state_machine/transitions.py` holds the table above as a frozen mapping and exposes `assert_transition(from_state, to_state) -> None`, raising `IllegalTransitionError`. No I/O, no session, unit-tested with zero containers.

**2. The repository, as a compare-and-set.** Every state write goes through `JobRepo.transition(job_id, *, from_state, to_state, **fields)`, which issues `UPDATE jobs SET state = :to, ... WHERE id = :id AND state = :from` and raises `StaleTransitionError` when `rowcount == 0`. The domain check catches an *illegal* edge; the CAS catches a *stale* one — two workers racing to move the same job both issue the UPDATE and exactly one gets a row. Without it, a reaper reclaiming a job at the same instant the worker finishes it silently overwrites `succeeded` with `queued` and the job runs twice for no reason.

**3. The database enforces the vocabulary and nothing else.** `job_state` is a Postgres enum type, so an unknown label is rejected at the type level. F2 deliberately does **not** add a trigger comparing `OLD.state` to `NEW.state`: it would be a second copy of the transition table, in PL/pgSQL, that drifts from the first and cannot be unit-tested without a container. The CAS in (2) already delivers the database-level property that matters — no lost update — with no duplicated rules. The one thing the DB *is* asked to guarantee is that its enum labels match `JobState`'s members exactly, asserted in `tests/integration/postgres/test_job_state_enum.py`.

## The enqueue write path

`packages/db/src/relay_db/transactions/enqueue.py`. The order is the spec's and is not negotiable.

**Step 0 — before any transaction, before any I/O.** Parse and canonicalize the payload, measure it, reject over 10 MiB, validate against the handler schema if one is registered, resolve the queue (cache hit in the common case), apply defaults, generate the job's `uuid4`. Nothing here touches a durable store, so a rejection here costs no database round trip and leaves nothing behind.

**Step 1 — `BEGIN`, then claim the idempotency key.**

```
INSERT INTO idempotency_keys (project_id, queue_id, key_hash, job_id, job_created_at, expires_at)
VALUES (...) ON CONFLICT (project_id, queue_id, key_hash) DO NOTHING
RETURNING job_id
```

A returned row means we won and continue. No row means someone else holds the key: re-select it, load their job, return **200**. Skipped entirely when the caller supplied no key.

**Step 2 — offload the payload if it is over 256 KiB.** Compress, `put` to the blob store, keep the returned URI. Skipped for the overwhelming majority of enqueues.

**Step 3 — insert the job row** with the id generated in step 0 and the state from step 0's `run_at`.

**Step 4 — `COMMIT`. This is the durability line.**

**Step 5 — index into Redis:** one `XADD` onto `q:{project_id}:{queue}:p{lane}`, then `UPDATE jobs SET redis_indexed_at = now()`.

### Why the claim comes before the upload, and not after

Uploading first and claiming second would let 100 concurrent identical 5 MB submissions each upload their own blob — 500 MB of writes to produce one job and 99 pieces of garbage for the retention sweep. Claiming first means exactly one upload happens: the other 99 block on Postgres' speculative insertion lock, discover the winner, and return 200 having written nothing anywhere. The cost is an open transaction held across a network call, bounded by `blob_upload_timeout_seconds` (10 s) and paid only by payloads over 256 KiB, which are by definition not in the 25 ms fast path.

### Why the claim and the job insert are one transaction

**This is the answer to "what happens when the first claimer crashes before committing the job row."** They are in the same transaction, so a crash rolls back both. The claim disappears with the job that never existed, and the next submission of that key wins cleanly.

The alternative — claim in its own committed transaction, then insert the job — produces a claim row pointing at a `job_id` that will never exist. Every subsequent submission of that key for the next 24 hours returns 200 with a dangling id, the caller's job never runs, and nothing in the system is wrong enough to notice. Recovering from that needs a sweeper that reconciles claims against jobs, which is a whole loop existing to clean up after a decision that did not have to be made. One transaction, or an unrecoverable failure mode.

### The concurrency mechanism, precisely

100 concurrent POSTs with the same key against a fresh key:

1. All 100 execute the `INSERT ... ON CONFLICT DO NOTHING` in their own transactions.
2. One wins the speculative insertion. The other 99 **block** on its uncommitted tuple — this is Postgres' documented behaviour for `ON CONFLICT` against an in-flight duplicate, not a race we are hoping loses.
3. The winner inserts its job row and commits. Its transaction is one insert; the blocking window is sub-millisecond.
4. The 99 unblock. Their `INSERT` does nothing (the conflicting row is now committed and visible) and `RETURNING` yields nothing.
5. Each re-selects the claim under a fresh READ COMMITTED snapshot, gets the winner's `(job_id, job_created_at)`, loads the job with an exact partition hit, and returns 200.

If the winner had instead *aborted*, the 99 unblock into a world where the conflicting tuple is dead, and one of them takes the insertion. Both branches converge on exactly one row.

**Why not an advisory lock.** `pg_advisory_xact_lock(hashtext(key))` would serialize on a 64-bit hash of a client-controlled string — a collision silently serializes two unrelated keys — and it holds for the remainder of the transaction, which includes the blob upload. The unique index gives a stronger guarantee (no collisions, it is the actual key) using an index Postgres already has to maintain, and holds nothing past the statement.

**Why not `ON CONFLICT DO UPDATE ... RETURNING`.** It would collapse the winner and loser paths into one round trip, but it writes a dead tuple on *every* repeat submission — turning an idempotent no-op into table bloat and vacuum pressure on the one table whose whole job is to stay small.

### Every failure window, and what the client sees

| Window | Failure | Durable? | Client sees | Repair |
|---|---|:--:|---|---|
| Step 0 | payload > 10 MiB | nothing | **413**, no row, no blob, no claim | none needed |
| Step 0 | schema violation | nothing | **400** naming the offending field | none needed |
| Step 0 | bad queue name, bad priority, unknown field | nothing | **400** | none needed |
| Step 1 | key held, winner committed | winner's job | **200** + the original job | none needed |
| Step 1 | key held, winner in flight | pending | blocks, then 200 (or wins if the winner aborted) | Postgres' insertion lock |
| Step 2 | blob store unreachable | nothing — the txn rolls back and releases the claim | **503** | client retries; the key is free again |
| Step 3–4 | Postgres unreachable or the txn aborts | nothing | **503** | client retries |
| **After step 4, before step 5** | **the API process is killed** | **the job** | connection reset — the client does not know | the reconciler XADDs it within 60 s; a retry with the same key returns 200 and the same job |
| Step 5 | Redis down or XADD fails | **the job** | **201**, `indexed: false` | 3 in-request retries (50/100/200 ms), then the reconciler |

**The eighth row is the argument for idempotency keys**, and it is why RELAY's SDK sets one by default. It is also the only window in the entire path where the client cannot distinguish "nothing happened" from "everything happened."

**Redis being down does not produce a 503 at enqueue.** Once step 4 commits, the job is durable and will run; telling the caller 503 would be a lie that provokes a retry, and a retry without an idempotency key manufactures exactly the duplicate execution that at-least-once asks handlers to tolerate. RELAY would be creating the duplicate itself, for nothing. The spec's degradation matrix line ("Redis: enqueue fails fast with 503") describes the pre-reconciler world; F2's contribution to the better answer is `redis_indexed_at` and the partial index that makes the drift query a single index scan.

The honest 503s are the ones where **the effect the caller asked for did not happen**: Postgres unreachable, or the blob store unreachable. That is the rule the new 503 group encodes, and it is also why `pause` returns 503 on a Redis failure (below) while `enqueue` returns 201 — for pause, the effect *is* the Redis write.

**On P3 and the 413.** Rejecting an oversized payload at submit looks like a violation of "park, never drop," and is not. P3 governs work already inside the system, where no caller is listening. At submit the caller is on the other end of an open socket and can be told exactly what is wrong. Parking a job the caller believes succeeded is strictly worse than a synchronous 413.

## Redis key layout for F2

Keys F2 adds to `packages/redis/src/relay_redis/keys.py`:

| Key | Type | Purpose |
|---|---|---|
| `q:{project_id}:{queue}:p{0..3}` | Stream | live work, one per priority lane |
| `q:{project_id}:{queue}:paused` | String | fast pause read for the worker fetch loop; no TTL |
| `queue:cfg:{project_id}:{queue}` | Hash | cached queue defaults, keeping the enqueue path off Postgres |
| `purge:token:{project_id}:{queue}` | String | sha256 of the outstanding confirmation token, `EX 300` |

**The key shape diverges from ARCHITECTURE.md, which writes `q:{queue}:p0..p3`, and it must.** Queue names are per-project, so two projects both using `emails` would share one stream and one consumer group — project A's workers draining project B's jobs. That is a cross-tenant leak in the transport layer, the exact leak F1's RLS exists to prevent, reintroduced one storage engine down. The project **UUID** is used rather than the slug because slugs are mutable and a key that renames itself orphans every entry already in it.

Keys F2 deliberately does not add, with their owners:

| Key | Type | Purpose | Added by |
|---|---|---|---|
| `q:{project_id}:{queue}:delayed` | Sorted set | retries, throttled and scheduled jobs | F5 / F7 |
| `q:{project_id}:{queue}:rl` | Hash | token bucket state | F8 |
| `q:{project_id}:{queue}:inflight` | Sorted set | concurrency cap, crash-safe in-flight count | F8 |
| `workers` | Sorted set | heartbeat times; stale detection as one range query | F3 |
| `events:{project_id}` | Pub/Sub | dashboard WebSocket fan-out | F9 |

There is deliberately no `lease:{job_id}` key at any point. The lease deadline lives in `jobs.lease_expires_at`, because the spec's own rule is never to trust a worker's clock and to compute deadlines from the database — and because a lease in Redis is a lease that a Redis wipe silently releases, converting a wipe drill into mass double execution.

**F2's producer does not create consumer groups.** `XADD` auto-creates the stream; the group belongs to the consumer, and F3 creates it at id `0` on worker boot. If the producer created it, it would have to pick a start id, and `$` — the natural choice for a producer — means every entry added before the first worker ever booted is invisible to that group forever. A group with no consumer is also a pending list nobody drains.

### Bounded trimming, concretely

Every `XADD` carries `MAXLEN ~ {queue_stream_maxlen}` (default 100,000, per lane).

**The `~` is not decoration.** Exact `MAXLEN` makes Redis delete entry by entry until the count is met, so a stream that has drifted far over the cap pays a latency spike proportional to the overshoot — on the enqueue hot path, which has a 25 ms p99 budget. Approximate trimming removes whole macro-nodes only when it can do so without splitting one, which is O(1) amortized and never spikes.

**Trimming is safe because the stream entry is a pointer, not data.** The entry fields are `job_id`, `priority`, `enqueued_at` — roughly 120 bytes. Everything a worker needs beyond the id comes from Postgres. Losing a trimmed entry costs a dispatch pointer that the reconciler regenerates from `jobs WHERE state = 'queued'`. Sizing follows from that: 100,000 entries × ~120 B ≈ 12 MB per lane, ~48 MB for a fully saturated four-lane queue, and at the spec's 5,000 jobs/sec that is about 20 seconds of buffer on a single saturated lane. Those are numbers an operator can hold against Redis `maxmemory`.

**What breaks if trimming evicts an unacknowledged entry.** `MAXLEN` deletes entries regardless of pending-list membership, so the entry vanishes from the stream while its PEL record survives. The worker currently holding it is unaffected — it already has the job id and reads state from Postgres. What is lost is the *reclaim* path: `XAUTOCLAIM` on that id returns it in the deleted-ids list rather than as a redeliverable entry, so the stream can no longer hand the job to a replacement worker. That job then sits in `running` past its lease deadline until the reaper finds it by `lease_expires_at < now()` in Postgres and re-indexes it. **This is the concrete reason the reaper's authority is the Postgres lease column and never the Redis PEL** — and it is why `queue_stream_maxlen` is sized so this is a pathological case, not a routine one.

## Cursor pagination

`GET /v1/projects/{pid}/jobs?state=&handler=&queue=&from=&to=&limit=&cursor=`

Ordering is always `(created_at DESC, id DESC)`. The page predicate is a **row-value comparison**:

```
WHERE project_id = :pid AND (created_at, id) < (:cur_created_at, :cur_id)
```

**Row-value comparison rather than the hand-expanded `created_at < X OR (created_at = X AND id < Y)`.** The expanded form is logically identical and the planner will not turn it into a single index range scan — it becomes a bitmap OR over two scans, or a filter. The row-value form maps directly onto the `(project_id, created_at DESC, id DESC)` index as one seek plus a forward walk of `limit` rows.

**Cursor composition:** `base64url("v1:{created_at_micros}:{job_id}:{filter_fingerprint}")`, where the fingerprint is the first 8 hex characters of a sha256 over the canonicalized filter tuple.

- **`v1:`** — the shape can change without breaking a client holding an old cursor; an unrecognized version is a clean 400.
- **`created_at` in integer microseconds** — the exact stored resolution, so the round trip through the cursor is lossless. Formatting it as ISO-8601 loses sub-millisecond precision in some serializers and silently skips or repeats rows at a page boundary where several jobs share a timestamp.
- **`job_id`** — the tiebreaker that makes the order total.
- **`filter_fingerprint`** — a cursor is only meaningful against the filter set it was issued for. Reusing a cursor from a `state=failed` listing on a `state=queued` listing produces a page that is not wrong-looking, merely wrong. F2 rejects a mismatched fingerprint with 400 rather than serving it.

**Why the pair is stable.** `created_at` is never updated after insert and `id` is unique, so `(created_at, id)` is an immutable total order per row. A concurrent insert gets a *larger* `created_at` and therefore lands on a page already passed — never inside the window about to be read. Offset pagination fails on both counts: it skips `offset` tuples on every page, so page 50,000 reads and discards half a million rows before returning ten, and any insert during a scroll shifts every later row by one, so the reader silently skips a job it never saw.

**The honest caveat, stated rather than papered over.** With a `state` filter, rows change state underneath the reader. Cursor pagination guarantees no row is skipped or duplicated *by position*; it does not guarantee that a job which was `queued` on page 1 still matches `state=queued` when the reader reaches page 9. That is a property of filtering on mutable data, not of the cursor, and no pagination scheme fixes it.

`limit` defaults to 50 and is capped at 200. `GET /jobs/{id}` returns the job with `attempts: []` in F2, and never rehydrates an offloaded payload unless `?include=payload` is passed — a list endpoint that rehydrated payloads would fan one request into 50 blob reads.

## Payload offload

**How size is measured:** `len(json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8"))` — the UTF-8 byte length of **RELAY's own canonical serialization of the parsed payload**, not the request's `Content-Length`.

The client's whitespace, key ordering and `\uXXXX` escaping are theirs, not ours. Measuring the raw body would make the 256 KiB threshold a property of whichever SDK formatted the JSON — the same logical payload crossing the line from one language's client and not another's. Measuring our own serialization also makes `payload_bytes` describe the bytes actually stored, so the recorded number and the stored object are the same object.

Thresholds are binary and explicit: `payload_inline_max_bytes = 262144`, `payload_max_bytes = 10485760`. "256KB" is ambiguous by 2.4% and that ambiguity would live in a check constraint.

| Measured size | Stored as | Client sees |
|---|---|---|
| ≤ 256 KiB | `jobs.payload` (JSONB), `payload_ref` NULL | **201**, payload echoed |
| 256 KiB – 10 MiB | blob, `payload_ref` set, `jobs.payload` NULL | **201**, `payload_ref` present, payload omitted unless requested |
| > 10 MiB | nothing | **413** `{"detail": "payload is 12582912 bytes; the limit is 10485760"}` — no row, no blob, no claim, no transaction opened |

Blob keys are deterministic: `{project_id}/{yyyy-mm}/{job_id}.json.gz`. **Deterministic, not random, because orphan detection depends on it** — a transaction that uploads and then rolls back leaves a file with no row, and F10's sweep finds those by listing a month prefix and anti-joining `jobs.payload_ref`. Random keys would make that a full-bucket listing against a full-table scan. gzip because a 5 MB JSON payload typically compresses 5–10×; the 10 MiB cap is measured *before* compression so the limit stays something a client can predict without knowing its own entropy.

## Files by layer

| Layer | File | Responsibility |
|---|---|---|
| domain | `enums/job_state.py` | `JobState` — eight members, the single source the DB enum is asserted against |
| domain | `enums/priority.py` | `Priority` as an **`IntEnum`**, deliberately unlike `enums/role.py`'s `StrEnum`. `role.py` warns explicitly that `Role.ADMIN < Role.MEMBER` silently compares alphabetically and mandates ranking through a dict; priority is the opposite case — it has a genuine numeric total order where `CRITICAL < HIGH` is both true and meaningful, so the ordering belongs on the type instead of in a parallel map that can drift |
| domain | `enums/attempt_outcome.py` | the structure doc calls this `attempt_state.py`; **renamed**, because an attempt has no states — by the time a row exists it is a completed fact with one outcome |
| domain | `value_objects/queue_name.py` | `QueueName.parse()`, the charset/length rule, `InvalidQueueNameError` |
| domain | `value_objects/job_id.py` | `JobId` newtype over UUID |
| domain | `value_objects/priority.py` | **not created.** `enums/priority.py` is the whole thing; a value object wrapping an `IntEnum` adds a constructor and no invariant |
| domain | `value_objects/lease.py` | **not created.** F3's. An empty file that F3 has to rewrite is worse than a missing one |
| domain | `state_machine/transitions.py` | the transition table + `assert_transition` |
| domain | `state_machine/errors.py` | `IllegalTransitionError`, `StaleTransitionError` |
| domain | `state_machine/guards.py` | **not created.** F2's only guard *is* the transition table. The guards that justify a separate module — F6's cycle detection, F5's attempt ceiling — land with those features |
| domain | `entities/{job,attempt,queue}.py` | pure frozen dataclasses, no I/O, matching `entities/project.py`'s shape |
| storage | `packages/storage/.../interface.py` | `BlobStore` as a **`Protocol`**, not an ABC: a test can pass a dict-backed fake without importing `relay_storage` at all. Three methods — `put`, `get`, `delete` |
| storage | `packages/storage/.../local.py` | filesystem backend, the default and the only one F2 ships |
| storage | `packages/storage/.../payloads.py` | canonical serialization, size measurement, the two thresholds, store/rehydrate. The only module `enqueue_service.py` imports |
| storage | `packages/storage/.../{s3,gcs}.py` | **not created.** v1 is one box with one disk. The seam is a URL scheme in `blob_store_url` plus one branch in a factory; adding S3 is one file and touches nothing above it. Requiring an object-store account to enqueue a 300 KB payload on a self-hosted install is a worse product, not a more serious one |
| db | `models/{queue,job,attempt,idempotency,handler_schema}.py` | the five tables |
| db | `repositories/{queues,jobs,attempts,idempotency,handler_schemas}.py` | one per table, each taking the UoW, matching `repositories/projects.py` exactly |
| db | `unit_of_work.py` | **extended, not subclassed** — five new repos hang off `TenantUnitOfWork`. No new UoW class: its docstring already argues one class covers both scopes, and every F2 table is project-scoped, so there is nothing new to scope by. There remains no unscoped path to a repository |
| db | `queries/job_queries.py` | the cursor-paginated filtered list. Kept out of `repositories/jobs.py` because it is a read model with its own filter and cursor vocabulary rather than a row mapper — the split the structure doc already anticipated |
| db | `transactions/enqueue.py` | the five ordered steps as one function. This file earns its slot: the ordering *is* the feature, and putting it in a service would make it testable only through HTTP |
| db | `transactions/{claim,complete,reclaim}.py` | **not created.** F3's, and each needs a lease to exist first |
| db | `migrations/versions/0003…0008` | as tabulated above |
| redis | `keys.py` | extended with the four F2 key shapes. Its docstring already predicted this ("those land with F2/F3/F5/F7") |
| redis | `streams/producer.py` | `index_job(...)` — the single `XADD` with `MAXLEN ~`. Plain `client.xadd`, **not** a Lua script: unlike `rate_limit/limiter.py`, there is nothing here to make atomic. One command is already atomic, and the durability guarantee lives in a Postgres commit that has already happened |
| redis | `streams/{consumer,acknowledge,reclaim}.py` | **not created.** F3's. F2 produces; F3 consumes |
| redis | `queues/config_cache.py` | **new, not in the structure doc.** The cached queue-defaults hash plus the pause flag. It is not a stream, not a rate limiter, and not key naming, so it fits none of the doc's existing `relay_redis` subpackages and gets its own |
| redis | `health.py` | **not created.** F10's readiness endpoint |
| api | `schemas/job.py` | enqueue request, job response, attempt response |
| api | `schemas/queue.py` | queue response, defaults patch, pause/purge responses |
| api | `schemas/common.py` | the `CursorPage[T]` envelope — `items`, `next_cursor`, `has_more`. Deliberately no `total`: a count over a partitioned fifty-million-row table is the exact query cursor pagination exists to avoid, and a UI that shows a total will ask for it on every page |
| api | `services/enqueue_service.py` | validate → size-gate → schema-check → resolve queue → `transactions/enqueue.py` → `streams/producer.py`. Raises plain exceptions, never `HTTPException` |
| api | `services/cancel_service.py` | single-job cancel; the `queued`/`scheduled` CAS and the `running` request-flag path |
| api | `services/queue_service.py` | **new, not in the structure doc's list.** Defaults, pause, resume, purge-token mint, purge. These are not project CRUD and do not belong in `project_service.py`, which is F1's org/membership file |
| api | `api/v1/jobs.py` | enqueue, list, get, cancel |
| api | `api/v1/queues.py` | list, get, patch defaults, pause, resume, purge-token, purge, plus the handler-schema routes |
| api | `api/v1/attempts.py` | **not created.** Attempts come back embedded in `GET /jobs/{id}`. A top-level attempts route is a second way to reach the same rows behind a second RBAC check to get wrong, for a resource nobody navigates to independently |
| api | `api/v1/cancel.py` | **not created.** Cancel is `POST /jobs/{id}/cancel`, one route in `jobs.py`. A file per verb is not a layer |
| api | `api/deps.py` | **unchanged.** `get_project_context` and `require_project_permission` already do everything F2 needs — the clearest evidence F1's seam was cut in the right place |
| api | `middleware/error_handler.py` | extended: a new **413** group and a new **503** group, plus new members in 400/404/409/429. Services raise plain exceptions and the one registration loop maps them — no route in F2 imports `HTTPException` |
| api | `api/router.py` | include `jobs.router` and `queues.router` |
| api | `config.py` | the new `Settings` fields below |
| api | `lifecycle.py` | construct the blob store once at startup onto `app.state.blob_store`, the same shape `app.state.redis` already uses |
| root | `pyproject.toml` | add `packages/storage` to `[tool.uv.workspace] members` and `packages/storage/src` to `[tool.mypy] mypy_path` |

### Routes and their permissions — zero new members

| Method | Path | Permission | Reachable by an API key? |
|---|---|---|:--:|
| POST | `/v1/projects/{pid}/queues/{name}/jobs` | `JOB_ENQUEUE` | ✓ |
| GET | `/v1/projects/{pid}/jobs` | `PROJECT_READ` | ✓ |
| GET | `/v1/projects/{pid}/jobs/{jid}` | `PROJECT_READ` | ✓ |
| POST | `/v1/projects/{pid}/jobs/{jid}/cancel` | `JOB_CANCEL` | ✓ |
| GET | `/v1/projects/{pid}/queues` | `PROJECT_READ` | ✓ |
| GET | `/v1/projects/{pid}/queues/{name}` | `PROJECT_READ` | ✓ |
| PATCH | `/v1/projects/{pid}/queues/{name}` | `QUEUE_EDIT_DEFAULTS` | — |
| POST | `/v1/projects/{pid}/queues/{name}/pause` | `QUEUE_PAUSE` | — |
| POST | `/v1/projects/{pid}/queues/{name}/resume` | `QUEUE_PAUSE` | — |
| POST | `/v1/projects/{pid}/queues/{name}/purge-token` | `QUEUE_PURGE` | — |
| DELETE | `/v1/projects/{pid}/queues/{name}/jobs` | `QUEUE_PURGE` | — |
| PUT / DELETE | `/v1/projects/{pid}/handler-schemas/{handler}` | `QUEUE_EDIT_DEFAULTS` | — |
| GET | `/v1/projects/{pid}/handler-schemas` | `PROJECT_READ` | ✓ |

The path keeps `{project_id}` even for API-key callers, matching the shape F1 already established for the API-key routes — `deps.get_project_context` reads it from the path and `resolve_project_context` verifies the key's own project matches. Cross-project access is a 404, not a 403, exactly as F1 proved.

### New exception groups in `error_handler.py`

| Status | New exceptions | Meaning |
|---|---|---|
| 400 | `InvalidQueueNameError`, `SchemaValidationError`, `InvalidCursorError`, `InvalidQueueDefaultsError`, `PurgeTokenInvalidError` | well-formed request, rule violated |
| 404 | `JobNotFoundError`, `QueueNotFoundError` | includes another project's job — F1's 404-not-403 rule |
| 409 | `IllegalTransitionError`, `StaleTransitionError` | valid request, conflicts with the row's current state |
| **413** | `PayloadTooLargeError` | **new group** |
| **503** | `StorageUnavailableError`, `DatabaseUnavailableError`, `QueueIndexUnavailableError` | **new group** — "the effect you asked for did not happen" |

`QueueIndexUnavailableError` is raised by pause/resume only, never by enqueue. That asymmetry is the 503 rule doing its job: for pause, the Redis write *is* the effect; for enqueue, the Postgres commit is.

## Key mechanisms

**Queue autocreation without a race.** On a config-cache miss: `SELECT` first, and only on a miss `INSERT ... ON CONFLICT (project_id, name) DO NOTHING`, then `SELECT` again. The common case — the queue exists — is one index hit and zero writes, which is what the latency budget requires. Under a concurrent first-enqueue the loser's `DO NOTHING` blocks on the winner's speculative insertion and its follow-up `SELECT` takes a fresh READ COMMITTED snapshot, so it sees the committed row; if the winner aborted, the loser's insert succeeds instead. Exactly one row either way. **Why not `DO UPDATE ... RETURNING`:** it saves a round trip and writes a dead tuple on every single enqueue to an existing queue, which is bloat and vacuum pressure on the hot path in exchange for a saving that only matters on first use. **Why not an advisory lock:** it serializes every first-enqueue cluster-wide on a hash that can collide, and holds for the rest of the transaction. Proved by `tests/integration/postgres/test_queue_autocreate.py`: 50 concurrent first-enqueues to a fresh name produce one `queues` row.

**Queue config cache.** `queue:cfg:{project_id}:{queue}` is a Redis hash, mirrored in-process for `queue_config_cache_seconds` (5). The enqueue path therefore reads the queue's defaults with zero Postgres round trips in the steady state. A defaults `PATCH` writes Postgres, then deletes the Redis hash. Five seconds of staleness on a lease duration is harmless — the value is snapshotted onto the job at enqueue anyway, so the worst case is that a handful of jobs carry the previous lease length. The alternative, a `SELECT` per enqueue, doubles the query count on the most-called endpoint in the system to keep a value fresh that nothing needs fresh.

**Pause and resume.** Truth is `queues.paused_at`; the fast read is `q:{project_id}:{queue}:paused`. Postgres commits first, per P1, then Redis. **If the Redis write fails, the route returns 503 with the queue already paused in truth**, and says so — workers are still draining. That is the honest answer because the caller's actual intent (stop the workers) did not happen, and it is exactly the case the new 503 group exists for. The window closes on its own at the next worker restart, since a worker reads pause truth from Postgres on boot. Nothing in the enqueue path reads the flag — that is the requirement, not an omission: pausing during an incident must not start rejecting customer submissions.

**A worker mid-fetch is not interrupted.** Pause stops fetching, not executing. A worker that has already claimed an entry finishes it. Cancelling in-flight work on pause would turn every pause into a burst of lease expirations and reclaimed duplicate executions — the precise failure leases exist to prevent. F3's fetch loop checks the flag once per iteration, before the `XREADGROUP`; F2 lands the flag and this semantics.

**Purge, and why it is two requests.** `POST .../purge-token` returns `{"token", "expires_at", "queue", "job_count"}`. The token is `secrets.token_urlsafe(32)` — `relay_security.secrets.generate_url_token`, the same primitive F1 ships for invitations — stored as its sha256 in Redis under `purge:token:{project_id}:{queue}` with `EX 300`. `DELETE .../jobs?confirm=<token>` consumes it with `GETDEL`, so a replayed request cannot purge twice.

- **Redis, not a Postgres table:** the token is a five-minute anti-fat-finger interlock, not an audited artifact. A table means a migration, a sweeper, and rows that outlive their meaning. The purge *itself* is audited, in Postgres, forever, via F1's existing `AuditRepo` — F2 adds a call, not machinery. Losing tokens to a Redis restart is the right failure mode: you re-confirm.
- **Keyed by queue, not just random:** a token minted for `emails` cannot purge `payments` even if the caller pastes the wrong path. That is the specific accident a bare random token would not stop.
- **`job_count` at mint time** is there so the human sees the blast radius before confirming. The purge does not re-check it — a purge that fails because three more jobs arrived would be a worse tool.

**What purge actually does.**

- *Postgres:* it **deletes nothing.** One `UPDATE jobs SET state='cancelled', cancel_reason='queue_purged' WHERE project_id=? AND queue_id=? AND state IN ('queued','scheduled')`. P5 — if it happened, there is a row. Deleting would erase the evidence of the operation most likely to have been a mistake.
- *Redis:* `XTRIM {lane} MAXLEN 0` on each of the four lanes. **Not `DEL`:** `DEL` destroys the consumer group and its pending list along with the stream, which would orphan the in-flight entries currently held by workers. `XTRIM` empties the backlog and leaves the group and PEL intact.
- *In-flight (`running`) jobs are untouched.* They keep their lease, finish, and write their outcome. Purge means "stop the backlog," not "kill running work" — a job that is mid-way through talking to a downstream would otherwise be abandoned half-sent. The response reports `{"cancelled": N, "still_running": M}` so the operator knows exactly what survived and can wait out the leases or cancel individually.

**Cancel returns two different status codes, both honest.** Cancelling a `queued`, `scheduled` or `blocked` job is a CAS straight to `cancelled` and returns **200** — it is done. Cancelling a `running` job sets `cancel_requested_at` and returns **202** — the worker honours it at its next lease boundary (F3). Returning 200 for the second case would claim an effect that has not happened yet; returning 409 would be wrong because the request was accepted.

## Config surface

New fields on `apps/api/src/relay_api/config.py`'s `Settings`, all validated at boot per F0's rule that a bad value is a loud crash:

| Field | Default | Why this value |
|---|---|---|
| `blob_store_url` | `file:///var/lib/relay/payloads` | the scheme selects the backend; local is the only one F2 ships |
| `payload_inline_max_bytes` | `262144` | 256 KiB, spec F2 |
| `payload_max_bytes` | `10485760` | 10 MiB, spec F2 |
| `blob_upload_timeout_seconds` | `10` | bounds the open transaction held across the upload |
| `idempotency_window_hours` | `24` | spec default; a per-request override is clamped to this |
| `queue_stream_maxlen` | `100000` | ≈12 MB and ≈20 s of buffer per saturated lane |
| `queue_config_cache_seconds` | `5` | keeps the enqueue path off Postgres; staleness is harmless because defaults are snapshotted onto the job |
| `enqueue_redis_retry_attempts` | `3` | 50/100/200 ms after commit, then hand off to the reconciler |
| `job_list_page_size_default` | `50` | |
| `job_list_page_size_max` | `200` | |
| `purge_token_ttl_seconds` | `300` | long enough to read the count and confirm, short enough that a token left in a terminal is dead |
| `jobs_partition_months_ahead` | `3` | how many months `0004`/`0005` pre-create before F10's roller exists |

A model validator asserts `payload_inline_max_bytes < payload_max_bytes` — inverting them would silently offload nothing and reject everything over the inline cap.

## Operational behaviour

**Day one.** `make up`, `make migrate`, sign up, self-grant the project membership (audited, per F1), create an API key, `POST /v1/projects/{pid}/queues/emails/jobs`. **No queue provisioning step exists**, and no operator configuration is required to enqueue. The blob directory is created on first offload, not at startup, so a deployment that never sends a large payload never touches the disk.

**API restart.** Nothing to rebuild. The in-process queue-config cache is cold and refills lazily from Redis, then Postgres. Committed jobs are unaffected; the only loss is any un-indexed job whose retry loop was in flight, which is a job already recorded with `redis_indexed_at IS NULL`.

**Redis wiped.** Streams, pause flags, config caches and outstanding purge tokens are all gone. Everything is derivable, which is the point of P1 — but two things deserve naming:

1. Every `queued` job still says `state = 'queued'` with `redis_indexed_at` set, which is now a lie. F2's contribution to the rebuild is the drift index (`WHERE redis_indexed_at IS NULL AND state='queued'`) plus `JobRepo.list_queued_for_reindex(...)`, so the reconciler's input is one index scan rather than a sequential scan of fifty million rows. The reconciler loop itself is F10's.
2. **The pause flags come back too, or a wipe silently un-pauses every paused queue** — during an incident, which is the only time queues are paused. `QueueRepo.list_paused()` exists in F2 for exactly this, and restoring pause flags is listed as a required step of the wipe drill rather than left to be discovered when a drained-on-purpose queue starts draining again.

**Redis down at enqueue.** Three retries at 50/100/200 ms after the commit, then **201** with `indexed: false` and a counter incremented. The job is durable; only its dispatch is delayed. Reasoned through above.

**Postgres down at enqueue.** 503, nothing durable, the client retries. With an idempotency key that retry is safe; without one it may duplicate, which is the documented at-least-once contract said out loud rather than hidden.

**The Redis persistence gap, and F2's deliberate decision not to close it.** `infra/compose/docker-compose.yml` runs `redis:7-alpine` with no `appendonly yes` and no mounted `redis.conf`, while the spec's out-of-scope section assumes "one Redis with append-only persistence and a replica." **F2 does not add AOF, on purpose.** Persisting stream entries across a Redis restart is a *convenience*, not a correctness property — the reconciler has to rebuild from Postgres regardless, and a half-working AOF is worse than none because it makes the wipe drill pass for the wrong reason: the streams survive, so the rebuild path is never actually exercised, and the first genuine wipe happens in production with untested code. F2's position is that the drill must pass with Redis configured exactly as it is today, losing everything on restart. `infra/redis/redis.conf` with `appendonly yes` is F10's to add, *after* the reconciler has proved it is not needed.

## Deferred, and the seam that makes it cheap

| Deferred | Why it is safe to wait | The seam that is already here |
|---|---|---|
| S3 / GCS blob backends | v1 is one box with one disk | `BlobStore` Protocol + a URL-scheme factory; one file, nothing above it changes |
| Redis AOF and a replica | the reconciler must work without it; enabling it early makes the wipe drill pass for the wrong reason | the drill itself, plus `redis_indexed_at` |
| Bulk cancel and bulk replay | F5 already rules that bulk replay is *a job*, not a request handler | `enqueued_by_type='replay'`, `replayed_from`, and the `failed → queued` edge |
| Queue deletion | nobody has asked, and deleting a queue with history means deciding what happens to its jobs | pause is the reversible version of the same intent |
| Per-project attempt ceiling | F5's | `queues.max_attempts` exists; a project-level column above it is additive |
| Payload encryption for sensitive queues | F10's security pass | `queues` is the anchor flag; `payload_ref` already indirects the body |
| Handler registry and manifest | F3's — a handler is a string until a worker declares it | `jobs.handler`, `jobs.handler_version` |
| Job-level `total` counts in list responses | a count over a partitioned table is the query cursor pagination exists to avoid | `has_more` answers the only question a UI actually needs |
| A `conftest.py` | F1 deliberately has none; each test file declares its own fixtures and skips on missing env | F2 follows the same idiom rather than introducing a shared fixture layer mid-project |

### What F2 lands for each later feature, and what it refuses to build

| Feature | F2 lands | F2 deliberately does not build |
|---|---|---|
| **F3 — worker pool** | `lease_expires_at`, `lease_owner`, `reclaim_count`, snapshotted `timeout_seconds`/`lease_seconds`, the `job_attempts` table, the pause flag's semantics | the claim, `XREADGROUP`, consumer-group creation, the heartbeat, the reaper, `streams/consumer.py` |
| **F4 — priority aging** | four lanes per queue already addressed; `priority` (as submitted, immutable) and `priority_effective` (the lane) as separate columns | the aging loop; `priority_effective` is written once at enqueue and never moved |
| **F5 — retries & DLQ** | `attempt`, `max_attempts`, `run_at`, `replayed_from`, the `scheduled` state, `job_attempts.error_category` and `retry_after_seconds`, the `failed → queued` edge | backoff math, the `:delayed` zset, the promoter, replay, error classification |
| **F6 — dependencies** | `dependency_count` (0), the `blocked` state and its two edges, `result` / `result_ref` | the `job_dependencies` table, the atomic decrement, cycle detection, the cancel cascade |
| **F7 — schedules** | `run_at`, the `scheduled` state, `enqueued_by_type='schedule'` | the `schedules` table, cron parsing, timezones, leader election |
| **F8 — limits** | `queues.rate_limit_per_second` and `queues.max_depth` stored, bounded, validated and served; the dispatch partial index that makes a depth count one index scan | the token bucket, the depth check, 429 at enqueue, the concurrency cap, the circuit breaker |
| **F9 — observability** | `trace_id`, `span_id`, `trace_flags` parsed from the enqueueing request's `traceparent` and stored on the job | span creation, the OTel exporter, `events:{project}`, the WebSocket fan-out, metrics |
| **F10 — partitions & retention** | both big tables partitioned from birth, three months pre-created, a DEFAULT partition, RLS on every partition, DDL confined to migrations running as `relay`, `idempotency_keys.expires_at` | the retention loop, partition detach/archive, `scripts/db/partition.sh`, `redis.conf` |
| **F10 — reconciler** | `redis_indexed_at`, the drift partial index, `QueueRepo.list_paused()` | the reconciler loop |

## Task order

1. **Domain: enums, value objects, the transition table.** Pure Python, no containers, no database. Lands first because migration `0004`'s `job_state` enum and every service below quote from it — writing the DDL first means transcribing the state list twice, in two languages, with no test that they agree.
2. **`packages/storage`.** The `BlobStore` Protocol, the local backend, and `payloads.py`'s measure/store/rehydrate. Lands before the models because `payload_bytes` and `payload_ref` are columns whose *meaning* is defined here — the 256 KiB decision has to be a tested pure function before it becomes a check constraint. Also the point at which the workspace and mypy path are extended, so everything after it type-checks.
3. **Models and migrations `0003`–`0008`.** Including RLS on every table *and every partition*, the DEFAULT partition, and every bound check constraint. Write `tests/integration/postgres/test_job_partitions.py` here: a row inserted through the parent lands in the right partition; `relay_app` can DML a partition created by a migration; a partition addressed directly still fails closed under RLS. These are the two hazards named above, proved before any code depends on them being handled.
4. **Repositories, the `unit_of_work.py` extension, and `queries/job_queries.py`.** **Write the isolation and cursor tests here, before any route** — the same sequencing F1 used, for the same reason: an isolation bug found through an HTTP route has been found one layer too late to know where it lives.
5. **`transactions/enqueue.py`.** The ordered write path including the idempotency claim. Lands before the service so the ordering can be tested against real Postgres with no HTTP in the way — including the 100-concurrent claim test and the "kill the winner mid-transaction" test, both of which are far harder to drive through a TestClient.
6. **`relay_redis`: the `keys.py` extension, `streams/producer.py`, `queues/config_cache.py`.** After step 5, deliberately: the XADD is bolted onto a write path already proven durable *without* it, which makes "Redis failed, the job is still there" testable by simply not running this step.
7. **`services/{enqueue,queue,cancel}_service.py`.** Composition only — validation, size gate, schema check, queue resolution, step 5's transaction, step 6's index. Plain exceptions, no `HTTPException`, matching every F1 service.
8. **Schemas, routes, `error_handler.py`'s new 413/503 groups, `router.py` wiring, `lifecycle.py`'s blob store, `config.py`'s new fields.** First end-to-end HTTP proof: enqueue → list → get → cancel → pause → enqueue-while-paused → purge-token → purge, over real HTTP against real Postgres and real Redis. `deps.py` is untouched, which is the check that F1's seam was cut correctly.
9. **The proof tests that are the feature's reason for existing:** 100 concurrent identical submissions over real HTTP; the 413/offload boundary; the Admin-JWT-versus-API-key matrix on every queue-admin route; a forced Redis failure at step 5 returning 201 with an un-indexed row. Last, because each of them needs the whole stack standing to mean anything.
10. **Latency measurement.** `tests/load/enqueue_load.py` against the 25 ms p99 target, recorded as a number rather than asserted as a gate — a latency assertion in CI on shared hardware is a flaky test that gets deleted, and the number is what the README pitch has to be able to quote.

## Done when

The spec's own bar, plus the guarantees F2 claims above, each proved where it actually lives:

- **`apps/api/tests/integration/test_idempotency_concurrency.py::test_100_concurrent_identical_submissions_produce_one_job`** — the spec's stated bar. 100 concurrent POSTs sharing one idempotency key: exactly one row in `jobs`, exactly one **201**, exactly ninety-nine **200**s, and all 100 responses carrying the same `job_id`.
- `tests/integration/postgres/test_enqueue_write_order.py` — the claim and the insert are one transaction: a forced failure after the claim leaves zero `idempotency_keys` rows and zero `jobs` rows, and the next submission of the same key wins cleanly rather than 200-ing at a job that never existed.
- `tests/integration/postgres/test_job_partitions.py` — routing through the parent; `relay_app` DML on a migration-created partition; a directly-addressed partition still failing closed under RLS; and an insert past the last declared range landing in `jobs_default` instead of erroring.
- `tests/integration/postgres/test_tenant_isolation_jobs.py` — a project-scoped connection sees only its own jobs, queues, attempts and idempotency rows, and an INSERT carrying a foreign `project_id` is rejected by the policy's implied `WITH CHECK`. Below the app layer entirely, as raw `asyncpg` connected as `relay_app`, matching F1's `test_tenant_isolation.py`.
- `tests/integration/postgres/test_job_cursor_pagination.py` — a full walk with concurrent inserts running throughout: no row seen twice, no row skipped; and a cursor issued under one filter set rejected with 400 under another.
- `tests/integration/postgres/test_queue_autocreate.py` — 50 concurrent first-enqueues to a brand-new queue name produce exactly one `queues` row.
- `tests/integration/postgres/test_job_state_enum.py` — the Postgres `job_state` type's labels equal `JobState`'s members exactly. The drift a second copy of a vocabulary always invites.
- `tests/unit/state_machine/test_transitions.py` — every legal edge accepted, every one of the remaining ordered pairs rejected, and `succeeded` proven to have no outgoing edge at all.
- `tests/unit/domain/test_queue_name.py` — charset, length bounds, leading character, and case rejection rather than silent normalization.
- `tests/unit/domain/test_payload_limits.py` — canonical measurement is stable across key ordering and whitespace; the inline boundary is exact at 262144; the reject boundary is exact at 10485760.
- `tests/integration/redis/test_stream_producer.py` — the XADD lands in the lane matching `priority_effective`; `MAXLEN ~` bounds the stream; and a trimmed unacknowledged entry is reported by `XAUTOCLAIM` as deleted rather than silently vanishing, which is the property the reaper's Postgres-first design depends on.
- `apps/api/tests/integration/test_enqueue_http.py` — **413** above 10 MiB with no job row, no blob and no claim written; **201** with `payload_ref` between 256 KiB and 10 MiB; **400** on a schema violation naming the field; **404** on another project's job id; **201** with `indexed: false` when the Redis step is forced to fail after commit.
- `apps/api/tests/integration/test_queue_admin_http.py` — a paused queue still accepts enqueues; an API key (fixed Member) gets **403** on pause, resume, purge and defaults while an Admin JWT succeeds; purge with no token, a stale token, or a token minted for a different queue is **400**; a valid purge cancels the `queued` backlog, leaves `running` jobs alone, writes an `audit_log` row, and reports both counts.
- `tests/load/enqueue_load.py` — p99 enqueue latency measured and recorded against the 25 ms target.

Once these pass, F2 is done. The next thing to build is F3, not another queue-management endpoint — per the spec's own ordering note, an engine that provably does not lose jobs is the deliverable, and nothing above dispatches a single job yet.
