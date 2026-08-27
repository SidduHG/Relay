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

**F0 — Foundations** is scaffolded: one-command stack, typed config, structured JSON logging,
Alembic wired (no models yet), CI. Everything else (auth, the queue engine, workers, retries,
scheduling, observability views) is unbuilt — see RELAY-SPEC.md's build order.

## Commands

| Command | Does |
|---|---|
| `make up` | Start the full local stack |
| `make down` | Stop and remove containers/volumes |
| `make test` | Run the Python test suite |
| `make lint` | Ruff + mypy |
| `make migrate` | Apply Alembic migrations |
