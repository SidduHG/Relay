---
name: relay-engineering
description: Relay's production engineering standard. Use when implementing or reviewing Relay code, picking up a Relay GitHub issue, or changing its schema, Redis keys, worker, control loops, API, or logging.
---

# Relay engineering

Build Relay as a system that stays correct through `kill -9`. Two truths decide most choices: Postgres owns state, and a Redis entry is a hint.

## Working an issue

1. **Scope it.** Read the issue, its dependencies, and the matching section of `RELAY-SPEC.md` and `ARCHITECTURE.md`. For worker work, also read `docs/workerPool/plan.md`. If the issue conflicts with them, stop and explain the conflict. Done when you can state the behavior change in two sentences.
2. **Find the failure windows.** For each write, ask what survives a crash on the line before and the line after it. Done when every window has a named outcome: safe, repaired by a named loop, or an explicit decision.
3. **Design the seam.** Place code using the layer map below, and reuse existing helpers first. Done when each new unit has one job and a test that can reach it without the network.
4. **Write the test first** for domain rules and transactions, and watch it go red. Failure paths come before the happy path.
5. **Implement** the smallest change that passes. Read [references/standards.md](references/standards.md) when the change touches logging, metrics, schema, Redis, concurrency, or patterns.
6. **Verify.** Run `uv run ruff check .`, `uv run mypy .`, and the focused tests. Run the live stack for anything crossing a process boundary. Report skipped tests as not verified.
7. **Close out.** Update `docs/current-implementation-handbook.md` if behavior changed, make one coherent commit, tick the issue checklist, and use the CLAUDE.md end-of-task report.

For a review issue, skip steps 3 to 5: check the code against the spec and the rules below, then record every finding. Fix each confirmed defect with a test, or split it into a new issue. A clean review states what was checked.

## The invariants

Each of these is a stop-the-line rule. A change that weakens one needs a recorded decision first.

- **Commit first.** Postgres commits before any Redis write, and `XACK` follows the outcome commit.
- **The row decides.** Every state change is a conditional update through `JobRepo.transition` and `LEGAL_TRANSITIONS`, and it handles the lost-race result.
- **Fence ownership.** Worker writes compare state, owner, and `attempt`.
- **Server time.** Deadlines come from Postgres `now()` or Redis `TIME`.
- **Park, then show a human.** Every unprocessable job ends in `parked` with a reason.
- **At-least-once.** Handlers are idempotent, and docs say so plainly.
- **Rebuildable Redis.** Everything in Redis can be derived from Postgres or is short-lived.
- **Tenant scope.** Tenant data is reached through `TenantUnitOfWork`. Other tenants' resources return 404.
- **Row and metric.** Every state change writes a row and increments a metric.

## Layer map

| Layer | Location | Owns |
|---|---|---|
| Route | `apps/api/.../api/v1/` | HTTP shape, `Depends`, response |
| Dependencies | `api/deps.py`, `auth/` | Identity, tenant, permission |
| Service | `apps/api/.../services/` | One use case; raises plain exceptions |
| Error map | `middleware/error_handler.py` | Exception to status code |
| Transaction | `packages/db/.../transactions/` | Multi-row atomic changes, explicit result types |
| Repository | `packages/db/.../repositories/` | Scoped SQL |
| Domain | `packages/domain/` | Pure rules, enums, policies, with no I/O |
| Redis | `packages/redis/` | Commands and scripts; key names only in `keys.py` |
| Worker | `apps/worker/` | Orchestrates consumption and execution |
| Control loops | `apps/control-loops/` | Leader-only repair and timing |

Dependencies point downward. Workers import packages, never API services.
