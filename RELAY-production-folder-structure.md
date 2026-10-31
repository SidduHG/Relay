# RELAY — Production-Grade Folder Structure

This is the target layout. Create a file only when a task needs it. Files marked `(built)` already exist, and an unmarked file in a built area may simply not be needed yet.

```text
relay/
│
├── .github/
│   ├── workflows/
│   │   ├── ci.yml
│   │   ├── test.yml
│   │   ├── security.yml
│   │   ├── docker.yml
│   │   └── release.yml
│   ├── CODEOWNERS
│   ├── dependabot.yml
│   └── pull_request_template.md
│
├── apps/
│   │
│   ├── api/                              # FastAPI Control Plane
│   │   ├── src/
│   │   │   └── relay_api/
│   │   │       ├── __init__.py
│   │   │       ├── main.py
│   │   │       ├── api/
│   │   │       │   ├── __init__.py
│   │   │       │   ├── deps.py
│   │   │       │   ├── router.py
│   │   │       │   └── v1/
│   │   │       │       ├── __init__.py
│   │   │       │       ├── auth.py
│   │   │       │       ├── projects.py
│   │   │       │       ├── jobs.py
│   │   │       │       ├── queues.py
│   │   │       │       ├── attempts.py
│   │   │       │       ├── schedules.py
│   │   │       │       ├── dependencies.py
│   │   │       │       ├── workers.py
│   │   │       │       ├── events.py
│   │   │       │       ├── replay.py
│   │   │       │       ├── cancel.py
│   │   │       │       └── health.py
│   │   │       ├── auth/
│   │   │       │   ├── jwt.py
│   │   │       │   ├── api_keys.py
│   │   │       │   ├── rbac.py
│   │   │       │   ├── permissions.py
│   │   │       │   └── tenancy.py
│   │   │       ├── middleware/
│   │   │       │   ├── request_id.py
│   │   │       │   ├── rate_limit.py
│   │   │       │   ├── logging.py
│   │   │       │   ├── tracing.py
│   │   │       │   └── error_handler.py
│   │   │       ├── schemas/
│   │   │       │   ├── auth.py
│   │   │       │   ├── project.py
│   │   │       │   ├── queue.py
│   │   │       │   ├── job.py
│   │   │       │   ├── attempt.py
│   │   │       │   ├── schedule.py
│   │   │       │   ├── dependency.py
│   │   │       │   ├── worker.py
│   │   │       │   └── common.py
│   │   │       ├── services/
│   │   │       │   ├── auth_service.py
│   │   │       │   ├── queue_service.py
│   │   │       │   ├── job_errors.py
│   │   │       │   ├── enqueue_service.py
│   │   │       │   ├── cancel_service.py
│   │   │       │   ├── replay_service.py
│   │   │       │   ├── schedule_service.py
│   │   │       │   ├── dependency_service.py
│   │   │       │   └── project_service.py
│   │   │       ├── websocket/
│   │   │       │   ├── manager.py
│   │   │       │   ├── connections.py
│   │   │       │   └── event_consumer.py
│   │   │       ├── config.py
│   │   │       ├── logging.py
│   │   │       └── lifecycle.py
│   │   ├── tests/
│   │   │   ├── unit/
│   │   │   ├── integration/
│   │   │   └── contract/
│   │   ├── Dockerfile
│   │   └── pyproject.toml
│   │
│   ├── worker/                           # Worker runtime
│   │   ├── src/
│   │   │   └── relay_worker/
│   │   │       ├── __init__.py
│   │   │       ├── main.py
│   │   │       ├── runtime/
│   │   │       │   ├── worker.py
│   │   │       │   ├── pool.py
│   │   │       │   ├── lifecycle.py
│   │   │       │   ├── shutdown.py
│   │   │       │   └── registration.py
│   │   │       ├── consumer/
│   │   │       │   ├── stream_consumer.py
│   │   │       │   ├── consumer_group.py
│   │   │       │   ├── claim.py
│   │   │       │   ├── acknowledge.py
│   │   │       │   └── backpressure.py
│   │   │       ├── execution/
│   │   │       │   ├── executor.py
│   │   │       │   ├── handler_registry.py
│   │   │       │   ├── handler_loader.py
│   │   │       │   ├── timeout.py
│   │   │       │   ├── cancellation.py
│   │   │       │   └── result.py
│   │   │       ├── lease/
│   │   │       │   ├── lease_manager.py
│   │   │       │   ├── heartbeat.py
│   │   │       │   └── expiration.py
│   │   │       ├── outcome/
│   │   │       │   ├── success.py
│   │   │       │   ├── failure.py
│   │   │       │   ├── retry.py
│   │   │       │   └── permanent_failure.py
│   │   │       ├── rate_limit/
│   │   │       │   ├── limiter.py
│   │   │       │   └── token_bucket.py
│   │   │       ├── config.py
│   │   │       └── logging.py
│   │   ├── tests/
│   │   │   ├── unit/
│   │   │   ├── integration/
│   │   │   └── crash/
│   │   ├── Dockerfile
│   │   └── pyproject.toml
│   │
│   ├── control-loops/                    # Single leader
│   │   ├── src/
│   │   │   └── relay_control/
│   │   │       ├── __init__.py
│   │   │       ├── main.py
│   │   │       ├── leader/
│   │   │       │   ├── election.py
│   │   │       │   ├── advisory_lock.py
│   │   │       │   └── leadership.py
│   │   │       ├── loops/
│   │   │       │   ├── base.py
│   │   │       │   ├── promoter.py
│   │   │       │   ├── reaper.py
│   │   │       │   ├── cron.py
│   │   │       │   ├── reconciler.py
│   │   │       │   └── retention.py
│   │   │       ├── promotion/
│   │   │       │   ├── due_jobs.py
│   │   │       │   └── priority.py
│   │   │       ├── reclaim/
│   │   │       │   ├── expired_leases.py
│   │   │       │   ├── reclaim_counter.py
│   │   │       │   └── poison_pill.py
│   │   │       ├── scheduling/
│   │   │       │   ├── scheduler.py
│   │   │       │   ├── cron_parser.py
│   │   │       │   ├── fire_idempotency.py
│   │   │       │   └── next_run.py
│   │   │       ├── reconciliation/
│   │   │       │   ├── postgres_to_redis.py
│   │   │       │   ├── redis_to_postgres.py
│   │   │       │   ├── drift.py
│   │   │       │   └── repair.py
│   │   │       ├── retention/
│   │   │       │   ├── partitions.py
│   │   │       │   ├── archive.py
│   │   │       │   └── dedupe_cleanup.py
│   │   │       ├── config.py
│   │   │       └── logging.py
│   │   ├── tests/
│   │   │   ├── unit/
│   │   │   ├── integration/
│   │   │   └── failover/
│   │   ├── Dockerfile
│   │   └── pyproject.toml
│   │
│   └── frontend/                        # React operator dashboard
│       ├── src/
│       │   ├── app/
│       │   │   ├── App.tsx
│       │   │   ├── router.tsx
│       │   │   └── providers.tsx
│       │   ├── pages/
│       │   │   ├── Login/
│       │   │   ├── Overview/
│       │   │   ├── Jobs/
│       │   │   ├── JobDetails/
│       │   │   ├── Queues/
│       │   │   ├── Workers/
│       │   │   ├── Schedules/
│       │   │   ├── Attempts/
│       │   │   ├── DeadLetter/
│       │   │   ├── Projects/
│       │   │   └── Audit/
│       │   ├── components/
│       │   │   ├── jobs/
│       │   │   ├── queues/
│       │   │   ├── workers/
│       │   │   ├── schedules/
│       │   │   ├── attempts/
│       │   │   ├── charts/
│       │   │   ├── tables/
│       │   │   └── common/
│       │   ├── features/
│       │   │   ├── auth/
│       │   │   ├── jobs/
│       │   │   ├── queues/
│       │   │   ├── workers/
│       │   │   ├── schedules/
│       │   │   └── projects/
│       │   ├── api/
│       │   │   ├── client.ts
│       │   │   ├── jobs.ts
│       │   │   ├── queues.ts
│       │   │   ├── workers.ts
│       │   │   └── schedules.ts
│       │   ├── hooks/
│       │   ├── stores/
│       │   ├── websocket/
│       │   ├── types/
│       │   ├── lib/
│       │   └── styles/
│       ├── public/
│       ├── tests/
│       │   ├── unit/
│       │   └── e2e/
│       ├── Dockerfile
│       ├── package.json
│       └── vite.config.ts
│
├── packages/                            # Shared libraries
│   ├── domain/
│   │   ├── src/relay_domain/
│   │   │   ├── entities/
│   │   │   │   ├── job.py
│   │   │   │   ├── attempt.py
│   │   │   │   ├── project.py
│   │   │   │   ├── queue.py
│   │   │   │   ├── worker.py
│   │   │   │   └── schedule.py
│   │   │   ├── value_objects/
│   │   │   │   ├── job_id.py
│   │   │   │   ├── project_id.py
│   │   │   │   ├── queue_name.py
│   │   │   │   ├── lease.py
│   │   │   │   └── priority.py
│   │   │   ├── enums/
│   │   │   │   ├── job_state.py
│   │   │   │   ├── attempt_state.py
│   │   │   │   └── priority.py
│   │   │   ├── state_machine/
│   │   │   │   ├── transitions.py
│   │   │   │   ├── guards.py
│   │   │   │   └── errors.py
│   │   │   └── policies/
│   │   │       ├── retry.py
│   │   │       ├── aging.py
│   │   │       ├── retention.py
│   │   │       └── dependency.py
│   │   └── pyproject.toml
│   │
│   ├── db/
│   │   ├── src/relay_db/
│   │   │   ├── models/
│   │   │   │   ├── organization.py
│   │   │   │   ├── user.py
│   │   │   │   ├── membership.py
│   │   │   │   ├── project.py
│   │   │   │   ├── invitation.py
│   │   │   │   ├── refresh_token.py
│   │   │   │   ├── api_key.py
│   │   │   │   ├── audit.py
│   │   │   │   ├── queue.py
│   │   │   │   ├── handler_schema.py
│   │   │   │   ├── job.py
│   │   │   │   ├── attempt.py
│   │   │   │   ├── idempotency.py
│   │   │   │   ├── dependency.py
│   │   │   │   └── schedule.py
│   │   │   ├── repositories/
│   │   │   │   ├── jobs.py
│   │   │   │   ├── attempts.py
│   │   │   │   ├── dependencies.py
│   │   │   │   ├── schedules.py
│   │   │   │   ├── projects.py
│   │   │   │   └── idempotency.py
│   │   │   ├── queries/
│   │   │   │   ├── job_queries.py
│   │   │   │   ├── worker_queries.py
│   │   │   │   └── analytics_queries.py
│   │   │   ├── transactions/
│   │   │   │   ├── enqueue.py
│   │   │   │   ├── claim.py
│   │   │   │   ├── complete.py
│   │   │   │   └── reclaim.py
│   │   │   ├── bootstrap.py
│   │   │   ├── connection.py
│   │   │   └── unit_of_work.py
│   │   └── pyproject.toml
│   │
│   ├── redis/
│   │   ├── src/relay_redis/
│   │   │   ├── streams/
│   │   │   │   ├── producer.py
│   │   │   │   ├── consumer.py
│   │   │   │   ├── acknowledge.py
│   │   │   │   └── reclaim.py
│   │   │   ├── delay/
│   │   │   │   ├── delayed.py
│   │   │   │   └── promoter.py
│   │   │   ├── queues/
│   │   │   │   └── config_cache.py
│   │   │   ├── rate_limit/
│   │   │   │   ├── bucket.py
│   │   │   │   └── limiter.py
│   │   │   ├── workers/
│   │   │   │   └── registry.py
│   │   │   ├── events/
│   │   │   │   └── publisher.py
│   │   │   ├── keys.py
│   │   │   ├── connection.py
│   │   │   └── health.py
│   │   └── pyproject.toml
│   │
│   ├── storage/
│   │   ├── src/relay_storage/
│   │   │   ├── interface.py
│   │   │   ├── local.py
│   │   │   ├── s3.py
│   │   │   ├── gcs.py
│   │   │   └── payloads.py
│   │   └── pyproject.toml
│   │
│   ├── contracts/
│   │   ├── openapi/
│   │   │   └── relay.yaml
│   │   ├── events/
│   │   │   ├── job_events.py
│   │   │   └── worker_events.py
│   │   └── pyproject.toml
│   │
│   ├── observability/
│   │   ├── src/relay_observability/
│   │   │   ├── logging.py
│   │   │   ├── tracing.py
│   │   │   ├── metrics.py
│   │   │   ├── context.py
│   │   │   └── propagation.py
│   │   └── pyproject.toml
│   │
│   ├── security/
│   │   ├── src/relay_security/
│   │   │   ├── hashing.py
│   │   │   ├── encryption.py
│   │   │   ├── secrets.py
│   │   │   └── validation.py
│   │   └── pyproject.toml
│   │
│   └── sdk-python/
│       ├── src/relay_sdk/
│       │   ├── client.py
│       │   ├── jobs.py
│       │   ├── queues.py
│       │   ├── schedules.py
│       │   ├── exceptions.py
│       │   ├── models.py
│       │   └── retry.py
│       ├── tests/
│       └── pyproject.toml
│
├── migrations/
│   ├── alembic.ini
│   ├── env.py
│   ├── script.py.mako
│   └── versions/
│       ├── 0001_initial_schema.py
│       ├── 0002_audit_log_append_only.py
│       ├── 0003_queues.py
│       ├── 0004_jobs.py
│       ├── 0005_job_attempts.py
│       ├── 0006_idempotency.py
│       ├── 0007_handler_schemas.py
│       ├── 0008_job_indexes.py
│       └── later migrations: dependencies, schedules, partitions, lease indexes
│
├── tests/
│   ├── unit/
│   │   ├── domain/
│   │   ├── retry/
│   │   ├── priority/
│   │   └── state_machine/
│   ├── integration/
│   │   ├── postgres/
│   │   ├── redis/
│   │   ├── api/
│   │   ├── worker/
│   │   └── control_loops/
│   ├── contract/
│   │   ├── api/
│   │   └── events/
│   ├── e2e/
│   │   ├── enqueue_to_success/
│   │   ├── retry_flow/
│   │   ├── schedule_flow/
│   │   ├── dependency_flow/
│   │   └── dlq_flow/
│   ├── chaos/
│   │   ├── test_worker_crash.py
│   │   ├── test_redis_wipe.py
│   │   ├── test_leader_crash.py
│   │   ├── test_poison_pill.py
│   │   ├── test_postgres_failure.py
│   │   └── test_network_partition.py
│   ├── load/
│   │   ├── enqueue_load.py
│   │   ├── worker_load.py
│   │   ├── mixed_priority.py
│   │   ├── rate_limit_load.py
│   │   └── scenarios/
│   │       ├── baseline.py
│   │       ├── burst.py
│   │       └── sustained.py
│   └── fixtures/
│       ├── jobs.py
│       ├── projects.py
│       ├── workers.py
│       └── schedules.py
│
├── infra/
│   ├── docker/
│   │   ├── api.Dockerfile
│   │   ├── worker.Dockerfile
│   │   ├── control.Dockerfile
│   │   └── dashboard.Dockerfile
│   ├── compose/
│   │   ├── docker-compose.yml
│   │   ├── docker-compose.dev.yml
│   │   └── docker-compose.test.yml
│   ├── postgres/
│   │   ├── init/
│   │   └── config/
│   ├── redis/
│   │   └── redis.conf
│   ├── prometheus/
│   │   ├── prometheus.yml
│   │   └── alerts.yml
│   ├── grafana/
│   │   ├── dashboards/
│   │   │   ├── relay-overview.json
│   │   │   ├── queues.json
│   │   │   ├── workers.json
│   │   │   └── control-loops.json
│   │   └── provisioning/
│   ├── otel/
│   │   └── collector.yaml
│   └── k8s/
│       ├── namespace.yaml
│       ├── configmap.yaml
│       ├── secrets.yaml
│       ├── postgres/
│       ├── redis/
│       ├── api/
│       ├── worker/
│       ├── control/
│       └── dashboard/
│
├── scripts/
│   ├── dev/
│   │   ├── bootstrap.sh
│   │   ├── reset.sh
│   │   └── seed.sh
│   ├── db/
│   │   ├── migrate.sh
│   │   ├── rollback.sh
│   │   └── partition.sh
│   ├── chaos/
│   │   ├── kill-worker.sh
│   │   ├── flush-redis.sh
│   │   ├── kill-leader.sh
│   │   └── poison-job.sh
│   └── load/
│       ├── run.sh
│       └── report.sh
│
├── docs/
│   ├── architecture/
│   │   ├── architecture.md
│   │   ├── system-design.md
│   │   ├── data-model.md
│   │   ├── state-machine.md
│   │   ├── consistency-model.md
│   │   ├── scaling.md
│   │   └── failure-modes.md
│   ├── auth/
│   ├── CoreQueueAndJobModel/
│   ├── frontend-home-design/
│   ├── workerPool/
│   └── current-implementation-handbook.md
│
├── config/
│   ├── .env.example
│   ├── development.env.example
│   ├── test.env.example
│   └── production.env.example
│
├── .dockerignore
├── .editorconfig
├── .gitignore
├── .pre-commit-config.yaml
├── Makefile
├── README.md
├── LICENSE
├── pyproject.toml
├── uv.lock
└── package.json
```

## Foundation requirements

- Docker Compose provides the local Postgres, Redis, API, worker, and dashboard stack.
- Alembic migrations are used from the first commit; no hand-run DDL.
- Configuration is typed and validated at startup.
- Logs use structured JSON and carry `request_id`, `job_id`, `project_id`, and `worker_id` where applicable.
- CI runs linting, strict type checking, tests, and coverage/security checks.
- The `Makefile` provides reproducible commands such as `make up`, `make test`, `make load`, and `make chaos`.
- PostgreSQL remains the source of truth; Redis remains rebuildable infrastructure.
- Chaos tests explicitly verify worker crash recovery, Redis reconstruction, leader failover, and poison-pill isolation.
