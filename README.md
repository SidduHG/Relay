# RELAY

Self-hosted distributed job queue. Postgres is the source of truth, Redis is the transport.

See [RELAY-SPEC.md](RELAY-SPEC.md) for the full build spec and [ARCHITECTURE.md](ARCHITECTURE.md) for the system design.

## Quickstart

```bash
cp config/.env.example config/.env
make up
```

This brings up Postgres, Redis, the API, a worker, and the dashboard. API health check:

```bash
curl http://localhost:8000/health
```

Dashboard: http://localhost:5173

## Status

**F0 — Foundations**, **F1 — Authentication & Multi-Tenancy**, and **F2 — Core Queue & Job
Model** are implemented. F2 provides durable idempotent enqueue, named queue defaults,
partitioned job history, payload offload, Redis priority-stream indexing, cursor reads,
cancel, pause/resume, purge confirmation, and optional handler JSON Schema validation.
Worker execution, retries, scheduling, and observability views begin with F3 — see
RELAY-SPEC.md's build order.

## Commands

| Command | Does |
|---|---|
| `make up` | Start the full local stack |
| `make down` | Stop and remove containers/volumes |
| `make test` | Run the Python test suite |
| `make lint` | Ruff + mypy |
| `make migrate` | Apply Alembic migrations |
