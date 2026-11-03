# Implementation plan and decisions

## Delivery sequence

1. Relational schema, migrations, opaque sessions, organization authorization, audit events.
2. Persistent projects and versioned files with optimistic concurrency, imports/exports and rollback.
3. Provider adapters, encrypted connections, model discovery, bounded agent proposals and review.
4. Next.js IDE, Monaco editing/diffs, settings, usage and team membership.
5. Separately isolated execution and preview, followed by durable agent workers and collaboration.
6. Repository intelligence, Git hosting, billing, enterprise identity and administration.
7. Production observability, infrastructure, security audit and full acceptance testing.

## ADR 001: explicit requested stack

Use Next.js App Router, TypeScript, FastAPI and SQLAlchemy 2 rather than a Worker-only hosted Site or a JavaScript agent framework. The requested Python backend and PostgreSQL need a conventional deployment. No hosted UI is published against an absent backend.

## ADR 002: server authorization

Random opaque session credentials are stored only as SHA-256 hashes in the database and sent in HttpOnly SameSite=Lax cookies. Unsafe requests require an exact allowed Origin. Sessions expire and logout revokes them. Organization membership is checked on every tenant resource access; viewers cannot mutate. Browser organization IDs are resource selectors, never proof of authorization. PostgreSQL RLS remains an additional production hardening requirement.

## ADR 003: changes before execution

The initial agent has read-only repository tools and proposes a validated change set. Application is an atomic, explicit human action against a captured base revision. File versions and snapshots permit rollback. Provider output has no authority to execute commands or bypass authorization. Checkpoint conflicts return 409 rather than overwriting concurrent edits.

## ADR 004: sandbox boundary

Application servers never execute user code. Production execution must use a separate control plane managing Firecracker microVMs (preferred) or gVisor runsc workloads. There is no unsafe local subprocess/Docker fallback. Current API returns an explicit unavailable response. No host Docker socket is mounted into API/worker containers. Warm pools, network proxy, signed preview origin and abuse monitoring are future work, not claims of current isolation.

## ADR 005: provider secrets and limits

Fernet authenticated encryption protects credentials with an environment-provided key. This is single-key encryption, not envelope encryption; KMS envelope keys and rotation are pending. Provider endpoint roots come from deployment configuration to prevent user-driven SSRF. Model choice is discovered from the actual provider. No inferred pricing or cost analytics. Request/token quotas are enforced; monetary budgets need a verified pricing catalog before implementation.

## ADR 006: durable state

SQLAlchemy models support SQLite locally and PostgreSQL in Compose. Alembic owns schema creation. Agent runs, traces, proposals, snapshots, file histories and usage persist. A process crash can leave an interrupted synchronous run; reconciliation and Celery recovery are not yet implemented. This must be solved before offering unattended agents.
