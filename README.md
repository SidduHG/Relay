# RELAY

Self-hosted distributed job queue. Postgres is the source of truth, Redis is the transport.

See [RELAY-SPEC.md](RELAY-SPEC.md) for the full build spec and [ARCHITECTURE.md](ARCHITECTURE.md) for the system design.
For the behavior implemented today, start with the [current implementation handbook](docs/current-implementation-handbook.md).

## Quickstart

Compose has no migration step, so a fresh database must be migrated before the API starts.
PostgreSQL is published on host port 5433.

```bash
cp config/.env.example config/.env
uv sync --all-packages
docker compose -f infra/compose/docker-compose.yml up -d postgres redis
DATABASE_ADMIN_URL=postgresql+asyncpg://relay:relay@localhost:5433/relay make migrate
make up
```

This brings up Postgres, Redis, the API, an idle worker process, and the frontend home page.
API health check (liveness only):

```bash
curl http://localhost:8000/health
```

Frontend: http://localhost:5173

A new deployment also needs a first organization owner, which has no HTTP flow yet. See
[Starting the local stack](docs/current-implementation-handbook.md#5-starting-the-local-stack).

## Status

**F0 — Foundations**, **F1 — Authentication & Multi-Tenancy**, and **F2 — Core Queue & Job
Model** are implemented. F2 provides durable idempotent enqueue, named queue defaults,
partitioned job history, payload offload, Redis priority-stream indexing, cursor reads,
cancel, pause/resume, purge confirmation, and optional handler JSON Schema validation.

**Jobs are accepted and stored, but not executed yet.** The worker is a process shell, and
the control loops, retries, schedules, metrics, and dashboard views do not exist. Execution
begins with F3; see the [worker pool plan](docs/workerPool/plan.md) and RELAY-SPEC.md's
build order.

## Commands

| Command | Does |
|---|---|
| `make up` | Start the full local stack |
| `make down` | Stop and remove containers/volumes |
| `make test` | Run the Python test suite |
| `make lint` | Ruff + mypy |
| `make migrate` | Apply Alembic migrations (set `DATABASE_ADMIN_URL` when running from the host) |
| `make load`, `make chaos` | Placeholders until the load harness and chaos suite exist |
