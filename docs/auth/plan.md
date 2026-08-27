# F1 — Auth, Tenancy & RBAC — Implementation Plan

**Spec:** [RELAY-SPEC.md § F1](../../RELAY-SPEC.md) (lines 59–81) · **Structure:** [folder structure](../../RELAY-production-folder-structure.md)
**Goal:** Every request resolves to a typed context — `OrgContext` or `ProjectContext` — before any queue logic runs. Two entry paths (JWT for the dashboard, API key for the SDK) collapse into that one shape.

## The three tiers — and the one we are *not* building

```
Platform (RELAY staff)          ← NOT BUILT. separate auth system entirely. see below.
└── Organization                ← the customer company. billing + project ownership.
    └── Project                 ← THE DATA BOUNDARY. every job/queue row carries project_id
        └── Membership          ← user + role in that project
```

**Users are global, not org-scoped.** One account, one password, many orgs — the GitHub model, not the Slack model. A contractor working for two customers has one login. `users.email` is globally unique; org belonging lives in `org_memberships`.

**The org tier is built now even though the spec defers hosted multi-org** (line 348: *self-hosted, one org per deployment*). A single-org deployment simply has exactly one `organizations` row, auto-created at bootstrap. This costs ~5% extra work today and removes the one migration you cannot do cheaply later: adding a tier *above* the permission checks means rewriting every one of them.

**Platform/staff admin is deliberately excluded**, and must never be a boolean on `users`. When it lands in v2 it gets: its own `staff_users` table and login route, mandatory MFA, **no implicit customer data read**, and impersonation that is time-boxed, reason-required, and written to an audit the *customer* can see. A `is_superuser` flag is how one leaked password becomes every customer's breach. The seam that keeps this cheap: `audit_log.actor_type` already accepts `'staff'`.

## Two role scopes — org governs the org, project governs the data

**The rule that makes this safe: an org role grants zero data access.** An OrgAdmin can create a project and can add themselves to it, but that self-grant is an audited event. There is no path to reading a job payload that doesn't go through a project membership row.

| Org-level action | OrgOwner | OrgAdmin | OrgMember |
|---|:--:|:--:|:--:|
| Billing, delete org, transfer org ownership | ✓ | — | — |
| Create / delete projects | ✓ | ✓ | — |
| Invite / remove org members | ✓ | ✓ | — |
| Self-grant project membership (audited) | ✓ | ✓ | — |

| Project-level action | Owner | Admin | Member | Viewer |
|---|:--:|:--:|:--:|:--:|
| Read jobs, queues, workers, DLQ | ✓ | ✓ | ✓ | ✓ |
| Enqueue, cancel, replay a job | ✓ | ✓ | ✓ | — |
| Pause/purge queue, edit queue defaults | ✓ | ✓ | — | — |
| Create / revoke API keys | ✓ | ✓ | — | — |
| Invite members, change project roles | ✓ | ✓ | — | — |
| Delete project, transfer project ownership | ✓ | — | — | — |

**Escalation guards** (both scopes): cannot grant a role above your own; cannot change your own role; the last OrgOwner and the last project Owner cannot be demoted or removed; project invitees must already be org members.

## Data model — migrations `0001_initial_schema`, `0002_projects_tenancy`

| Table | Key columns |
|---|---|
| `organizations` | id, name, slug (unique), created_at |
| `users` | id, email (unique, citext), password_hash — **global, no org_id** |
| `org_memberships` | user_id, org_id, org_role — unique on (user_id, org_id) |
| `projects` | id, **org_id**, name, slug — unique on (org_id, slug) |
| `memberships` | user_id, project_id, role — unique on (user_id, project_id) |
| `api_keys` | id, project_id, prefix (clear), key_hash, name, last_used_at, revoked_at |
| `refresh_tokens` | id, user_id, family_id, token_hash, used_at, expires_at, revoked_at |
| `invitations` | id, org_id, **project_id (nullable)**, email, role, token_hash, expires_at, accepted_at |
| `audit_log` | id, org_id, project_id (nullable), actor_type, actor_id, action, target, metadata, ip, created_at |

`invitations.project_id IS NULL` means an org invite; set means a project invite. `audit_log` lands here rather than the structure's `0008` slot — F1 needs it immediately (P5: no state change without a row write).

## Files by layer

| Layer | File | Responsibility |
|---|---|---|
| domain | `packages/domain/.../entities/{user,organization,project,membership}.py` | pure dataclasses, no I/O |
| domain | `packages/domain/.../enums/role.py` | `OrgRole`, `Role`, and their `RANK` orderings |
| security | `packages/security/.../hashing.py` | bcrypt passwords; sha256 for keys and tokens |
| security | `packages/security/.../secrets.py` | `rly_live_` + 24 chars; urlsafe invite/refresh tokens |
| security | `packages/security/.../validation.py` | email normalization, password strength floor |
| db | `packages/db/.../models/*.py` | the nine tables above |
| db | `packages/db/.../repositories/*.py` | one per table; **all take a scoped UoW** |
| db | `packages/db/.../unit_of_work.py` | `OrgUnitOfWork` / `TenantUnitOfWork` — the scoping chokepoints |
| api | `apps/api/.../auth/password.py` | hash + verify, constant-time |
| api | `apps/api/.../auth/jwt.py` | 15-min access token, rotating refresh with reuse detection |
| api | `apps/api/.../auth/api_keys.py` | issue, verify, rotate-with-overlap, `last_used_at` |
| api | `apps/api/.../auth/permissions.py` | `Permission` enum + both role→permission matrices |
| api | `apps/api/.../auth/rbac.py` | `require_org(*perms)` / `require_project(*perms)` |
| api | `apps/api/.../auth/tenancy.py` | resolves org + project, builds the contexts |
| api | `apps/api/.../middleware/auth.py` | reads `Authorization`, routes to JWT or API-key path |
| api | `apps/api/.../middleware/rate_limit.py` | aggressive limits on login + key auth |
| api | `apps/api/.../schemas/{auth,project}.py` | request/response models |
| api | `apps/api/.../services/project_service.py` | project CRUD, invites, accept, role change, remove |
| api | `apps/api/.../api/v1/auth.py` | signup, login, refresh, logout, API keys |
| api | `apps/api/.../api/v1/projects.py` | orgs, projects, members, invitations |
| api | `apps/api/.../api/deps.py` | `get_identity()`, `get_org_ctx()`, `get_project_ctx()` |

## Key mechanisms

**Three types, resolved in order.** Identity says *who*; the contexts say *where*:

```python
@dataclass(frozen=True)
class Identity:                      # middleware/auth.py produces this
    kind: Literal["user", "api_key"]
    user_id: UUID | None
    api_key_id: UUID | None

@dataclass(frozen=True)
class OrgContext:                    # org routes: /v1/orgs/{org_id}/...
    identity: Identity
    org_id: UUID
    org_role: OrgRole

@dataclass(frozen=True)
class ProjectContext:                # project routes: /v1/projects/{project_id}/...
    identity: Identity
    org_id: UUID                     # from project.org_id — never from the client
    project_id: UUID
    role: Role
```

An **API key belongs to exactly one project**, so it carries its own tenant and yields a `ProjectContext` in one lookup — no org or project id in the URL. A **JWT** identifies a global user, so the project comes from the path, and resolution verifies membership *and* that `project.org_id` matches. Both doors, one shape downstream.

**Scoping enforced below the middleware.** The spec forbids leaving this to discipline, so tenancy is structural twice over — a repository cannot be constructed without a scope, and Postgres RLS double-checks:

```python
class TenantUnitOfWork:
    def __init__(self, session: AsyncSession, ctx: ProjectContext):
        self.session, self.ctx = session, ctx
        self.jobs = JobRepo(self)         # repos read scope off the UoW —
        self.api_keys = ApiKeyRepo(self)  # there is no unscoped constructor

    async def __aenter__(self) -> "TenantUnitOfWork":
        await self.session.execute(
            text("SET LOCAL app.org_id = :o, app.project_id = :p"),
            {"o": str(self.ctx.org_id), "p": str(self.ctx.project_id)})
        return self
```

RLS applies at whichever tier owns the row — `projects`, `org_memberships`, `invitations` use `USING (org_id = current_setting('app.org_id')::uuid)`; `jobs`, `attempts`, `api_keys` and every queue table use `project_id`. Control loops connect as a bypass role.

**Refresh rotation with reuse detection:**

```python
async def rotate(uow, presented: str) -> TokenPair:
    row = await uow.refresh_tokens.get_by_hash(sha256(presented))
    if row is None or row.expires_at < now():
        raise HTTPException(401)
    if row.used_at is not None:                      # a spent token replayed
        await uow.refresh_tokens.revoke_family(row.family_id)   # stolen-token signal
        raise HTTPException(401, "token reuse detected")
    await uow.refresh_tokens.mark_used(row.id)
    return await issue_pair(row.user_id, family_id=row.family_id)
```

**Two-level invitations** — single-use, hashed at rest, 7-day expiry, bound to the invited email. An org invite creates the user + `org_membership`; a project invite requires the invitee to already be an org member:

```python
async def invite(uow, actor, email: str, role, project_id: UUID | None) -> str:
    if RANK[role] > RANK[actor.role]:
        raise HTTPException(403, "cannot grant a role above your own")
    if project_id and not await uow.org_memberships.exists(email):
        raise HTTPException(409, "invite to the organization first")
    token = secrets.token_urlsafe(32)
    await uow.invitations.upsert_pending(       # re-inviting replaces, never duplicates
        email=email, role=role, project_id=project_id,
        token_hash=sha256(token), expires_at=now() + timedelta(days=7))
    await uow.audit.write(actor, "member.invited", target=email, meta={"role": role})
    return token              # goes out in the email link; never stored in clear
```

**404 vs 403 — the distinction matters.** Another org's or another project's resource is **404** (a 403 confirms it exists). Inside a project you belong to, insufficient role is **403** (you already know it exists).

**Instant revocation.** A Redis denylist keyed by `api_key_id` / refresh `family_id`, written on revoke and checked on every auth. Positive auth lookups cache ~10s — short enough that a leaked key dies in seconds.

**API key rotation with overlap.** Create new → both valid → revoke old. `last_used_at` proves the old key is dead before you kill it.

## Scope boundary — build the seam, then stop

F1 builds the org *tier*, not the SaaS *product*. Everything below is deliberately deferred, and each is cheap to add later precisely because the tier exists:

| Deferred | Why it's safe to wait | The seam that's already here |
|---|---|---|
| Platform / staff admin | separate auth system; zero customers today | `audit_log.actor_type` accepts `'staff'` |
| Billing, quotas, metering | spec line 348 defers it | `organizations` is the natural anchor |
| SSO / SAML / social login | one enterprise deal away, not now | `users` has no password-only assumption |
| Transactional email for invites | F1 returns the invite token; delivery is a separate concern | `invitations.token_hash` |
| Password reset | same token machinery as invitations | reuse `upsert_pending` + expiry |

**Then go build F2 and F3.** Per the spec's own ordering note: *"A dashboard over an engine that loses jobs under `kill -9` is a frontend project."* Auth is the gate everything hangs off, not the thing worth polishing. Once the three isolation tests below pass, F1 is done — resist adding role #5.

## Task order

1. `OrgRole` + `Role` enums and domain entities — pure, unit-testable with zero containers
2. `packages/security`: password hashing, key/token generation, validation
3. Models + migrations `0001`, `0002`, including both tiers of RLS policy
4. Bootstrap: a fresh deployment auto-creates one `organizations` row (single-org mode)
5. `OrgUnitOfWork` / `TenantUnitOfWork` + repositories — **write the isolation tests here, before any routes**
6. `auth/password.py`, `auth/jwt.py` (unit-test rotation and reuse with a fake clock)
7. `auth/api_keys.py` — issue, verify, overlap rotation
8. `auth/permissions.py` + `auth/rbac.py` — both matrices, both dependencies
9. `auth/tenancy.py` + `middleware/auth.py` — both paths → `Identity` → contexts
10. `services/project_service.py` — org + project invites, accept, role change, escalation guards
11. Routes `api/v1/auth.py` + `api/v1/projects.py`, wired into `api/router.py`
12. `middleware/rate_limit.py` — per-IP *and* per-email on login (stops spray and targeted brute force)
13. Audit writes on every privileged action, including OrgAdmin self-grants; verify append-only

## Done when

`apps/api/tests/integration/auth/test_tenant_isolation.py` proves all three:
- Authenticated as project A → **404 on every project-B resource**, including nested ones (spec's bar)
- Authenticated in org X → **404 on every org-Y project**, even as OrgOwner
- An **OrgAdmin with no project membership gets 404 on that project's jobs** — the org role grants no data access

Plus: a replayed refresh token revokes its whole family, and a revoked API key stops working within seconds.
