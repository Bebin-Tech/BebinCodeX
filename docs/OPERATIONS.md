# Operations

Local PowerShell commands are in README.md. Database migrations run with `python -m alembic upgrade head` from backend. Check `/health` for process liveness and `/ready` for schema access and encryption configuration. OpenAPI is at `/docs` on the API origin.

## Deployment topology

Deploy Next.js and FastAPI separately behind one HTTPS ingress. Rewrite `/api/v1` to FastAPI and all other paths to Next.js. API_INTERNAL_URL is evaluated by the Next rewrite during build; set it before building a standalone image. The supplied Compose image uses a stable `http://api:8000` destination through its build argument. Never expose PostgreSQL or Redis publicly. Redis is provisioned for the planned worker architecture; no current code depends on it.

Keep ENCRYPTION_KEY and DATABASE_URL in your secret manager. Set APP_ORIGIN to the exact public origin and COOKIE_SECURE=true. Separate migration-owner and runtime database accounts before production. Use a validated PostgreSQL password without URL-reserved characters, or supply a correctly encoded DATABASE_URL through deployment-specific secrets.

## Backup and restore

Take daily encrypted PostgreSQL custom-format dumps and continuous WAL archives in private S3 with versioning. Retain encryption keys separately under access control; a database backup without its key cannot recover provider connections. Define RPO/RTO with the customer, test restores into an isolated database, run readiness and tenant-isolation tests, and verify snapshot restoration before promoting. SQLite local development can be backed up with sqlite backup APIs while writes are paused.

## Rollout and recovery

Build/test/scan immutable images in CI. Apply backward-compatible migrations once, deploy an API canary, verify health and authenticated project read/write, then roll the frontend. Roll back images if errors rise. Never automatically downgrade a data migration in production; restore a tested backup or apply a forward fix. The current initial migration is reversible for local testing only.

## Agent recovery

Runs currently execute within the API request. A process crash may leave a running record and a token reservation. Disable unattended use. An operator should inspect traces, confirm no request is still active, mark interrupted runs failed, and reconcile reserved_tokens under an exclusive maintenance window. A durable worker lease and automatic reconciliation are required before production use.

## Not provisioned

AWS Terraform, TLS ingress, S3 storage, log aggregation, Prometheus/Grafana, Sentry, OpenTelemetry exporters, Firecracker workers, signed preview domain, package proxy and automatic deployment are not implemented. Compose is a development topology, not a claim of a hardened AWS environment.
