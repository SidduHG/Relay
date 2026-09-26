# Relay: current implementation handbook

This guide describes the code **as it exists now**, for someone joining the project. The intended finished system is in [RELAY-SPEC.md](../RELAY-SPEC.md), its boundaries are in [ARCHITECTURE.md](../ARCHITECTURE.md), and the proposed long-term layout is in [RELAY-production-folder-structure.md](../RELAY-production-folder-structure.md). Those documents include components that have not been built. This handbook uses the running code as its source of truth for current behavior.

## 1. The project in one minute

Relay is being built as a self-hosted background job system. A client names a **handler** (the function that will eventually perform work), supplies a JSON **payload**, and submits a **job** to a named **queue** inside a **project**. PostgreSQL owns durable job and tenant records. Redis holds short-lived lookup and dispatch data. An API accepts and reads jobs. A worker is intended to take jobs from Redis and execute handlers.

**Current boundary:** the API can authenticate callers, manage projects and queues, durably enqueue jobs, index immediate jobs into Redis, read jobs, and cancel waiting jobs. The worker process is a startup/shutdown shell: it does not read Redis, claim jobs, execute handlers, or write outcomes. A successful enqueue therefore means **accepted and stored**, not **executed**.

```text
Currently implemented
Client -> FastAPI -> tenant/permission checks -> PostgreSQL job row
                                        -> Redis stream pointer (immediate jobs)
Client <- job response                 <- PostgreSQL reads

Planned, not running
Redis stream -> worker -> handler -> result/attempt in PostgreSQL -> acknowledge
```

The core rule is **commit to PostgreSQL before indexing in Redis**. Redis stream entries contain pointers to jobs, not the authoritative job data. See [enqueue_service.py](../apps/api/src/relay_api/services/enqueue_service.py), [enqueue.py](../packages/db/src/relay_db/transactions/enqueue.py), and [producer.py](../packages/redis/src/relay_redis/streams/producer.py).

## 2. What is implemented

| Area | Available now | Boundary to remember |
| --- | --- | --- |
| Foundations | Docker Compose, Python workspace, typed API settings, Alembic migrations, JSON logging, CI checks, tests | `make load` and `make chaos` print placeholders; there is no coverage gate |
| Identity and tenancy | Signup/login, JWT access and refresh tokens, project API keys, organization and project memberships, role checks, invitations, PostgreSQL row-level security | Signup does not give a user an organization membership; first owner provisioning is not an HTTP flow |
| Queues | Implicit creation on first enqueue, queue defaults, reads, edits, pause/resume, purge confirmation, optional handler JSON Schemas | Stored rate and depth settings are not enforced by a dispatcher or enqueue backpressure yet |
| Jobs | Durable enqueue, idempotency claim, inline or offloaded payload, four priority values, reads with filters/cursors, cancel | No execution, attempts, retries, scheduled promotion, or recovery loop yet |
| Redis | Stream producer, queue configuration cache, pause flag, purge token, auth abuse rate counters | No stream consumer, delayed set, worker registry, or Redis rebuild process |
| Frontend and worker | A React home page and a worker process entry point | Home page uses illustrative data; worker has no fetch/execution loop |

The [README](../README.md) summarizes F0–F2. This table is more precise about what those phases can do end to end. In particular, F3's enqueue-to-execution milestone in the spec has not been reached.

## 3. Vocabulary and ownership

| Term | Meaning in this code |
| --- | --- |
| Organization | Top-level tenant. API startup creates one default organization if none exists. The schema can represent more than one. |
| User | A global account with an email and password hash. A user has no resource access merely by existing. |
| Organization membership | Connects a user to an organization with `org_owner`, `org_admin`, or `org_member` role. Governs organization actions, not access to project jobs. |
| Project | The data access boundary under an organization. Queue, job, and API key records carry `project_id`. |
| Project membership | Connects a user to a project with `owner`, `admin`, `member`, or `viewer` role. This is what grants access to project data. |
| API key | A project-bound secret for client requests. It is treated as a project `member`, so it can enqueue/read/cancel but cannot administer queues or keys. |
| Queue | A named project-owned row holding defaults and pause state. A name such as `emails` identifies the queue within its project. |
| Job | One submission to a queue: handler name, payload or payload reference, state, priority, timing and policy fields. |
| Handler | A name such as `email.send` stored on a job. No current worker resolves that name to executable code. |
| Attempt | A schema/table for one execution attempt, including outcome and errors. Current API-created jobs have no worker-written attempts. |
| Unit of work | A database transaction with organization/project context. It commits on success and rolls back on error. |

The schema relationships are roughly:

```text
user -- org_membership --> organization -- owns --> project
user -- project_membership -------------------------> project
project -- has --> queue -- has --> job -- may have --> attempts
project -- has --> API keys and handler schemas
```

Read [membership.py](../packages/db/src/relay_db/models/membership.py), [project.py](../packages/db/src/relay_db/models/project.py), [queue.py](../packages/db/src/relay_db/models/queue.py), and [job.py](../packages/db/src/relay_db/models/job.py) for the actual columns and constraints.

## 4. Repository map

The root [pyproject.toml](../pyproject.toml) declares a `uv` workspace. `apps/api/pyproject.toml` lists local `relay-*` packages as dependencies, so Python imports link the app to packages directly. These are library calls within the API process, not HTTP calls between folders.

| Path | Responsibility and first file to open |
| --- | --- |
| `apps/api/src/relay_api/` | FastAPI control plane. [main.py](../apps/api/src/relay_api/main.py) builds the app; [lifecycle.py](../apps/api/src/relay_api/lifecycle.py) opens shared connections. |
| `apps/api/src/relay_api/api/v1/` | HTTP routes for auth, projects, queues, jobs. [router.py](../apps/api/src/relay_api/api/router.py) includes them. |
| `apps/api/src/relay_api/api/deps.py` | FastAPI dependencies that supply sessions, identity, tenant context, and permission checks. |
| `apps/api/src/relay_api/schemas/` | Pydantic request and response shapes. |
| `apps/api/src/relay_api/services/` | API application operations: signup/login, membership actions, enqueue, cancel, queue changes. |
| `apps/api/src/relay_api/auth/` | JWT, API key, tenant resolution, and role rules. |
| `packages/domain/` | Shared enums, value objects, and allowed job state transitions. |
| `packages/db/` | SQLAlchemy models and repositories, scoped unit of work, enqueue transaction, job list query. |
| `packages/redis/` | Redis client, stream producer, queue cache, pause flag, and auth rate limiter. |
| `packages/storage/` | Payload size/encoding and a local filesystem blob store. |
| `packages/security/` | Hashing, secret generation, email/password validation. |
| `packages/observability/` | Shared JSON logging formatter and context helpers. |
| `apps/worker/` | Process shell and config; job execution is not present. |
| `apps/frontend/` | Vite/React home page with illustrative activity, not an API-connected dashboard. |
| `migrations/` | Alembic schema history and PostgreSQL row-level security policies. |
| `infra/compose/` | Local PostgreSQL, Redis, API, worker, and frontend services. |

**How to follow a request:** start at a route in `api/v1`, follow its `Depends(...)` chain in `api/deps.py`, then its service call, then its `TenantUnitOfWork` repository or transaction, and finally any Redis or storage call. Errors raised below HTTP are mapped centrally in [error_handler.py](../apps/api/src/relay_api/middleware/error_handler.py).

## 5. Starting the local stack

These are the relevant repository commands, shown in PowerShell because this checkout is on Windows. They are instructions derived from the checked-in configuration; they were not executed while writing this guide. Run them from the repository root with Docker and `uv` available.

```powershell
Copy-Item config/.env.example config/.env
uv sync --all-packages
docker compose -f infra/compose/docker-compose.yml up -d postgres redis

# Alembic runs on the host here; PostgreSQL is published on host port 5433.
$env:DATABASE_ADMIN_URL = 'postgresql+asyncpg://relay:relay@localhost:5433/relay'
uv run --project apps/api alembic -c migrations/alembic.ini upgrade head

docker compose -f infra/compose/docker-compose.yml up --build -d api worker frontend
Invoke-RestMethod http://localhost:8000/health
```

Compose reads `config/.env` into the API and worker containers, but it has **no migration service or migration command**. Run Alembic before starting the API against a fresh database. The database container publishes port `5433` to the host and uses `5432` on the Compose network. The API listens on `8000`; the frontend on `5173`. `/health` returns `{"status":"ok"}` and is only a liveness response, not a full dependency/readiness check. See [docker-compose.yml](../infra/compose/docker-compose.yml), [Makefile](../Makefile), and [config/.env.example](../config/.env.example).

API startup creates the default organization and opens two PostgreSQL session factories: an admin connection for bootstrap and pre-tenant lookups, and a restricted app connection for tenant-scoped work. It also creates a Redis client, queue configuration cache, and local blob store. See [lifecycle.py](../apps/api/src/relay_api/lifecycle.py) and [bootstrap.py](../packages/db/src/relay_db/bootstrap.py).

**First-user caveat:** `POST /v1/auth/signup` creates only a global user. No public endpoint grants that first user the default organization's owner role, and project creation does not automatically grant project membership. The integration tests seed an organization owner through the restricted database unit of work, create a project through HTTP, then call the audited self-grant route for project access. A fresh deployment needs an operator provisioning step before the normal project and enqueue flow is usable. See [test_http_e2e.py](../apps/api/tests/integration/test_http_e2e.py) and [projects.py](../apps/api/src/relay_api/api/v1/projects.py).

## 6. Authentication and tenant flow

### User login

`POST /v1/auth/signup` validates and normalizes email, hashes the password with bcrypt, and inserts a global user. `POST /v1/auth/login` checks the password and returns a 15-minute signed access JWT plus an opaque refresh token. The refresh token is stored only as a hash. `POST /v1/auth/refresh` rotates it; reuse of a previously rotated token revokes its whole token family. `POST /v1/auth/logout` revokes that family. See [auth.py](../apps/api/src/relay_api/api/v1/auth.py), [auth_service.py](../apps/api/src/relay_api/services/auth_service.py), and [jwt.py](../apps/api/src/relay_api/auth/jwt.py).

### API key requests

A project admin/owner can create a key at `POST /v1/projects/{project_id}/api-keys`. The full `rly_live_...` secret is returned once; PostgreSQL stores its hash and a display prefix. For every request, verification uses the admin connection to find the key before its project is known, checks revocation, and updates `last_used_at`. The key only resolves for its own project path. Revocation writes `revoked_at`, which the next verification checks. See [api_keys.py](../apps/api/src/relay_api/auth/api_keys.py) and [tenancy.py](../apps/api/src/relay_api/auth/tenancy.py).

### Authorization after identity

For protected routes, [deps.py](../apps/api/src/relay_api/api/deps.py) reads `Authorization: Bearer <token>`, creates an `Identity`, resolves an organization or project context, and checks the route's permission. A user needs the relevant membership. An API key is fixed to one project and has `member` permissions. An unknown or inaccessible tenant resource returns `404`; a known project action outside the caller's role returns `403`.

The [TenantUnitOfWork](../packages/db/src/relay_db/unit_of_work.py) sets `app.org_id` and, when needed, `app.project_id` for the transaction. PostgreSQL row-level security policies use those settings to filter rows independently of route checks. Global `users` and `refresh_tokens` are intentionally outside tenant RLS. Admin sessions are used for the few lookups that must happen before a tenant can be identified; normal tenant reads and writes use the restricted app session.

Login attempts are limited by IP and email. Invalid API key attempts are limited by IP; valid API key traffic is not put through that abuse limit. This is authentication protection, not the planned per-queue job dispatch rate limit. See [rate_limit.py](../apps/api/src/relay_api/middleware/rate_limit.py).

### Organization and project operations

The API can create/list projects, invite people to an organization or project, accept a single-use email-bound invitation, self-grant project membership when an organization role allows it, and change/remove memberships with escalation and last-owner guards. The self-grant is audited. Project invites require the invitee to belong to the organization already. See [projects.py](../apps/api/src/relay_api/api/v1/projects.py) and [project_service.py](../apps/api/src/relay_api/services/project_service.py).

### Route map

This is a map of implemented route groups, not a replacement for FastAPI's generated `/docs` schema. `{project_id}` and `{org_id}` are UUIDs.

| Route group | Implemented operations |
| --- | --- |
| `/v1/auth` | Signup, login, refresh, logout, current user |
| `/v1/orgs/{org_id}` | Create/list projects, invite organization members, audited project self-grant, change/remove organization members |
| `/v1/invitations/accept` | Accept an invitation as a logged-in user |
| `/v1/projects/{project_id}` | Invite project members, change/remove project members, create/revoke project API keys |
| `/v1/projects/{project_id}/queues` | List/read queues; edit defaults; pause/resume; request purge token and purge backlog |
| `/v1/projects/{project_id}/handler-schemas` | List, set, and delete handler JSON Schemas |
| `/v1/projects/{project_id}/jobs` | List/read jobs and cancel one job |
| `/v1/projects/{project_id}/queues/{queue_name}/jobs` | Enqueue a job, implicitly creating the queue |

The route definitions are in [auth.py](../apps/api/src/relay_api/api/v1/auth.py), [projects.py](../apps/api/src/relay_api/api/v1/projects.py), [queues.py](../apps/api/src/relay_api/api/v1/queues.py), and [jobs.py](../apps/api/src/relay_api/api/v1/jobs.py). No worker, replay, or schedule route is registered in [router.py](../apps/api/src/relay_api/api/router.py).

## 7. Queue and job data flow

### A concrete request

Once a caller has project access, this request submits one job. The handler name is data at this stage; no currently running worker has an `email.send` implementation.

```http
POST /v1/projects/{project_id}/queues/emails/jobs
Authorization: Bearer <project API key or user access JWT>
Idempotency-Key: welcome-123
Content-Type: application/json

{"handler":"email.send","payload":{"to":"new.user@example.com"},"priority":2}
```

The path names the queue. There is no separate queue creation call: the first submission creates the queue row if it is absent. Queue names are validated, and the database makes `(project_id, name)` unique so two concurrent first submissions converge on one queue. The queue defaults are currently `max_attempts=5`, timeout `300` seconds, lease `60` seconds, and priority `2` (`normal`). These defaults are copied onto each new job. Priority `0` is critical, `1` high, `2` normal, and `3` low. They are recorded and used to choose a Redis stream, but nothing drains the streams yet. See [queues.py](../packages/db/src/relay_db/repositories/queues.py), [queue.py](../packages/db/src/relay_db/models/queue.py), and [priority.py](../packages/domain/src/relay_domain/enums/priority.py).

### Enqueue, in exact order

1. The job route validates the Pydantic request and requires `JOB_ENQUEUE` for the resolved project.
2. The enqueue service validates the queue name, measures canonical JSON payload size, checks priority, and reads a short-lived queue defaults cache if available. It loads/creates the queue and validates the payload against an optional per-handler JSON Schema.
3. Inside a project-scoped PostgreSQL transaction, the enqueue transaction hashes and claims the optional `Idempotency-Key` in a separate table. If already claimed, it returns the original job instead of inserting another.
4. Payloads up to `262,144` bytes stay inline in the job's JSONB column. Larger payloads up to `10,485,760` bytes are gzip-compressed into the configured local blob store; the job holds a reference. Larger payloads are rejected with `413`.
5. A job row is inserted with handler, payload/reference, queue defaults, priority, metadata, actor, trace fields, and state. A future `run_at` makes it `scheduled`; otherwise it is `queued`. Exiting the unit of work commits the row and idempotency claim.
6. Only a newly created `queued` job is added to a Redis priority stream. The stream entry contains its job ID, priority, and enqueue time. On success, a second database transaction stamps `redis_indexed_at`.
7. The API returns `201` for a new job and `200` for an idempotent repeat. The response includes `created` and `indexed`; a successful database insert can have `indexed=false` when Redis indexing fails.

The call chain is [jobs.py](../apps/api/src/relay_api/api/v1/jobs.py) → [enqueue_service.py](../apps/api/src/relay_api/services/enqueue_service.py) → [enqueue.py](../packages/db/src/relay_db/transactions/enqueue.py) → [producer.py](../packages/redis/src/relay_redis/streams/producer.py). The size/offload behavior is in [payloads.py](../packages/storage/src/relay_storage/payloads.py).

**Important current limits:** an idempotency claim has an expiry timestamp, but no cleanup loop currently expires old claims, so the configured 24-hour window is not yet enforced over time. A future `run_at` creates a `scheduled` database row without a Redis entry; no promoter moves it later. If Redis indexing fails after the PostgreSQL commit, the job remains durable but no reconciler currently repairs that missing entry. These gaps are part of the remaining spec work.

### Job states today

The [JobState enum](../packages/domain/src/relay_domain/enums/job_state.py) defines `blocked`, `scheduled`, `queued`, `running`, `succeeded`, `failed`, `cancelled`, and `parked`. The API currently creates `queued` or `scheduled` jobs and can move waiting jobs to `cancelled`. The other states are modeled for future worker, dependency, retry, and recovery flows; seeing them in a model does not mean those flows run today. The [transition table](../packages/domain/src/relay_domain/state_machine/transitions.py) records which changes are legally allowed when those components are implemented.

### Where the data lives

| Data | Current owner |
| --- | --- |
| Organization, membership, project, queue, job, idempotency, API key, audit, schema, and attempt rows | PostgreSQL |
| Inline job payload (up to 256 KiB) | PostgreSQL `jobs.payload` |
| Larger accepted payload | gzip file in the configured local blob store, referenced by `jobs.payload_ref` |
| Immediate job dispatch pointer | Redis stream `q:{project_id}:{queue_name}:p{0..3}` |
| Queue defaults cache and pause flag | Redis keys derived in [keys.py](../packages/redis/src/relay_redis/keys.py); durable queue defaults/pause timestamp are in PostgreSQL |
| Purge confirmation and auth abuse counters | Short-lived Redis keys |

The Compose API service does not mount `/var/lib/relay/payloads` as a persistent volume. Large payload files in that container can be lost when it is recreated even though their PostgreSQL references remain. Treat local blob storage as the present development implementation, not a proven durable production store.

## 8. Reading and changing jobs and queues

`GET /v1/projects/{project_id}/jobs` queries PostgreSQL with optional state, handler, queue, and date filters. It orders by `(created_at, id)` and returns a cursor for the next page. `GET /v1/projects/{project_id}/jobs/{job_id}` reads one job and its attempt rows. For an offloaded payload, `?include=payload` loads and decompresses the blob; without it, the response carries its reference. See [job_queries.py](../packages/db/src/relay_db/queries/job_queries.py) and [jobs.py](../apps/api/src/relay_api/api/v1/jobs.py).

`POST /v1/projects/{project_id}/jobs/{job_id}/cancel` immediately marks a `queued`, `scheduled`, or `blocked` job cancelled in PostgreSQL. For a `running` job it only sets a cancellation request and returns `202`; no current worker acts on that request. The shared [state machine](../packages/domain/src/relay_domain/state_machine/transitions.py) guards transitions. Cancelling one queued job does not remove its individual Redis stream entry; future consumers must check PostgreSQL state before acting. See [cancel_service.py](../apps/api/src/relay_api/services/cancel_service.py).

Queue routes list/read queues, patch defaults, pause/resume, and purge the waiting backlog. Pause/resume writes PostgreSQL and a Redis pause flag; enqueues still enter a paused queue. With no stream consumer, pause currently has no dispatch effect to observe. Purge is two-step: mint a short-lived confirmation token, then submit it to `DELETE /v1/projects/{project_id}/queues/{queue_name}/jobs?confirm=...`. It marks queued/scheduled jobs cancelled and trims the queue's four Redis streams; it reports how many jobs were running. Handler schema routes register, list, or delete per-project JSON Schemas used at enqueue. See [queues.py](../apps/api/src/relay_api/api/v1/queues.py) and [queue_service.py](../apps/api/src/relay_api/services/queue_service.py).

Errors from service/domain/storage code become HTTP responses in [error_handler.py](../apps/api/src/relay_api/middleware/error_handler.py): `400` for invalid business input, `401` for bad credentials, `403` for denied actions, `404` for inaccessible or absent tenant resources, `409` for conflicts, `413` for oversized payloads, `429` for auth abuse limits, and `503` for mapped storage/database/queue index failures. Normal FastAPI/Pydantic request-shape validation remains its own response path.

## 9. Integrations and current gaps

| Integration | What is connected | What is still missing |
| --- | --- | --- |
| PostgreSQL | Async SQLAlchemy through `relay_db`; Alembic schema; RLS; admin and restricted app sessions | Automatic partition maintenance and retention loop |
| Redis | Auth abuse counters, queue config cache, pause/purge keys, priority stream producer | Consumer groups, worker fetch, scheduled/delayed sets, reclaim, reconciliation |
| Blob store | Local filesystem implementation for large payloads and readback | Persistent Compose volume and cloud store implementations |
| API | Auth, tenancy, project/member, queue, schema, job read/enqueue/cancel routes | Worker control, replay, schedules, live events, readiness check |
| Worker | Config, logging, signal handling, idle loop | Handler registration, claim, lease, heartbeat, execution, timeout, retry, acknowledgement |
| Frontend | React/Vite home page | Authenticated dashboard, real job/queue API calls, WebSocket live updates |
| Observability | JSON logging and trace IDs stored from a valid `traceparent` header | Metrics endpoint, distributed spans, trace restoration in a worker |

The design documents describe a future at-least-once engine with promoter, reaper, cron, reconciler, and retention loops. None of those loops exists in the current application. The [worker main](../apps/worker/src/relay_worker/main.py) explicitly leaves fetch, claim/lease, and execution for F3. The frontend [App.tsx](../apps/frontend/src/app/App.tsx) renders only the home page; its activity examples in [HomePage.tsx](../apps/frontend/src/pages/Home/HomePage.tsx) are hard-coded.

## 10. Where to make a change

| If the change concerns... | Start here, then follow... |
| --- | --- |
| HTTP endpoint or response | `apps/api/src/relay_api/api/v1/` → `schemas/` → relevant service |
| Permission or project isolation | `api/deps.py` → `auth/tenancy.py` / `auth/permissions.py` → `packages/db/unit_of_work.py` → migration RLS policies |
| Queue or job persistence | Relevant service → `packages/db/repositories/` or `transactions/` → `models/` and Alembic migration |
| Redis key or stream behavior | `packages/redis/keys.py` → producer/cache/limiter → API service call site |
| Payload size or blob storage | `packages/storage/payloads.py` → `local.py` → API lifecycle configuration |
| A new worker behavior | Start with F3 in `RELAY-SPEC.md`; the current worker is a shell, so do not infer an existing claim protocol from its folder |

For orientation, read the focused tests under [apps/api/tests/integration](../apps/api/tests/integration), [tests/integration/postgres](../tests/integration/postgres), and [tests/integration/redis](../tests/integration/redis). The F2 HTTP suite includes a 100-concurrent-submission idempotency case. Integration tests may skip when their database/Redis environment is unavailable; a collected test is not proof that the live stack passed it. CI's declared lint, type, test, and frontend build steps are in [ci.yml](../.github/workflows/ci.yml). No tests were run to produce this handbook.
