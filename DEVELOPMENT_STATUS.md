# Development status — 3 November 2026

## Release assessment

Functional initial implementation; **not production ready** and **not the complete advanced-edition specification**. No hosted deployment, subscriptions, sandbox or enterprise compliance claims are made. The application uses real database-backed behavior and real provider HTTP adapters; provider fixtures exist only in tests.

## Implemented

- Next.js 16.4.4 App Router / React / TypeScript application, responsive dark/light interface, public introduction and documentation, registration/login and authenticated workspace.
- FastAPI `/api/v1` REST endpoints with Pydantic validation, generated OpenAPI, structured authorization failures, correlation IDs, liveness/readiness.
- SQLAlchemy 2 schema and Alembic initial frozen migration: users, sessions, organizations, memberships, invitations, projects, files/versions, provider connections, agent runs/traces, usage and audit logs. UUID keys, foreign keys, indexes, uniqueness and transactions.
- Argon2 password hashes, hashed opaque session cookies, expiry, logout, Origin checking, per-process request limiting.
- Tenant membership authorization, owner/admin/member/viewer permissions, personally owned provider connections, token-based team invitations/acceptance. Email dispatch is explicitly absent.
- Persistent project creation from empty/Python/HTML templates; project list and reopen; normalized source paths; ZIP import/export with entry/expanded-size/encoding/path/symlink checks.
- Local-bundled Monaco editor, language highlighting, multiple tabs, find-file filter, editor search commands, Ctrl+S, Ctrl+K focus to agent, explicit save, previous versions, deletion, optimistic concurrency, read-only viewer editing.
- Provider configuration for OpenAI, Anthropic, Gemini, Groq, DeepSeek, Ollama and administrator-configured compatible endpoints. Model discovery, encrypted keys, bounded retries/timeouts and process-local circuit breaker. Capability failures are explicit; no unsupported capability is advertised as known.
- Agent with list_files/read_file/search_code tools, project-rules context, redaction, bounded request/context/step/token/time limits, persistent traces, validated proposals and self-review instruction. No arbitrary model-authorized server tools.
- Monaco diff review, selected-file approval/rejection, atomic change application, conflict detection and guarded snapshot rollback. Approval is per file, not per hunk. Self-review is requested in the final model response, not an independent reviewer pass.
- Monthly organization token usage and reservation limits, local-only provider organization policy, real usage aggregation and organization audit viewer. Monetary usage deliberately remains unavailable.
- Dockerfiles/Compose development topology with PostgreSQL/pgvector and Redis, non-root API/frontend, API without Docker socket. GitHub Actions build/typecheck/tests/migration/audit workflow and PowerShell setup documentation.
- Threat model, operations/backup/recovery guidance, architecture decisions and phased implementation plan.

## Executed verification

| Check | Observed result |
| --- | --- |
| Backend Pytest | 22 passed; 1 Starlette test-client deprecation warning |
| TypeScript | Passed through standalone tsc and production build |
| Next.js production build | Passed; `/`, `/app`, `/docs` generated |
| Alembic upgrade → downgrade → upgrade | Passed against a dedicated disposable SQLite database |
| npm production dependency audit | Zero known vulnerabilities after Monaco/DOMPurify updates |
| Backend pinned dependency audit | No known vulnerabilities after cryptography 50.0.2 update |
| Python dependency consistency | `pip check`: no broken requirements before security update; final test suite passed after update |
| Browser/API/database flow | Local QA registration/login, organizations, Python project creation, Monaco load/edit/save, project reopen; saved browser text verified in SQLite at revision 2 |
| Browser console during editor check | No captured error/warning entries |
| Responsive UI | Narrow 320px account/dashboard and desktop 1440px IDE inspected; no accessibility certification |

Monaco includes a vendored sanitizer. The postinstall script rebuilds the editor from ESM with DOMPurify 3.4.17 and local worker bundles; an npm override alone is insufficient. Its version assertion intentionally requires review on sanitizer changes.

### Development incident

A migration downgrade was mistakenly run against the local development database while verifying reversibility, clearing its local records. The known disposable QA account, `bebin` and `Local QA workspace` organizations, QA Python project and saved source/history were reconstructed from this session. Original sessions/timestamps/audit history could not be recovered. No source/configuration was deleted. A dedicated temporary-database migration verification script now prevents the check from touching the application database. The local QA account was signed in again and a subsequent browser save was verified in storage.

## Not implemented / pending by specification area

| Area | Remaining work |
| --- | --- |
| AI gateway | Streaming, vision, full capability/pricing catalog, smart routing/fallback, caching, KMS envelope encryption/rotation, monetary budgets, residency, MCP, evals |
| Code intelligence | tree-sitter, pgvector embeddings/hybrid retrieval, reranking, knowledge graph, architecture maps, editable long-term memory, incremental index workers |
| Agent runtime | Celery durable jobs/leases/recovery, cancellation/pause/resume, multi-agent/worktree orchestration, independent self-review, per-hunk review, configurable autonomy, checkpoint per step, issue-to-PR, CI reproduction, schedules |
| IDE | Shadcn/Tailwind design-system adoption, xterm terminal, LSP IntelliSense beyond Monaco defaults, autosave/offline recovery, Yjs collaboration/presence/comments, inline completions/edits, structured slash commands/mentions, screenshot input, database explorer, migrations/docs generators, i18n |
| Sandbox | Firecracker/gVisor control plane, resource/egress enforcement, runtime images, warm pools, snapshots, signed isolated preview URLs, package proxy and abuse monitoring. Endpoint currently returns 503; there is no unsafe execution fallback. |
| Git/deployment | GitHub/GitLab OAuth/App and webhooks, repository imports, branch/stage/commit/PR/CI tools, deployment targets/rollback, public API tokens and CLI |
| Enterprise | MFA, password reset/email verification, SAML/OIDC/SCIM, custom roles, session/devices/IP restrictions, PostgreSQL RLS, governance/export/deletion/retention/legal hold/SIEM |
| Billing | Stripe/Razorpay, plan/subscription lifecycle, signatures/idempotent webhooks, immutable credit ledger, seats/credits/tax/GST/invoices/proration/dunning/refunds/coupons |
| Admin | Separate platform-admin authorization, management interfaces and real platform metrics; no ordinary org admin can access nonexistent platform routes |
| Observability | OpenTelemetry exporters, metrics, centralized structured logging, Sentry, public status data, operational alerts |
| Infrastructure | AWS IaC, S3 artifacts, Nginx/TLS production ingress, secrets manager, immutable scanned image digests, distributed limits/quotas, HA and exercised DR |
| Verification | Live providers without credentials, PostgreSQL/Redis/Compose (Docker engine unavailable), payment/sandbox/SSO tests, provider-contract fixtures for every adapter, automated browser regression suite, component/a11y/load/security-escape testing, image deployment |

## Important limitations

Agent work currently runs in the API request. Runs can be interrupted by server failure; operators must reconcile stale reservations before unattended use. Token quotas are conservative request limits, not guaranteed monetary spending limits. Regex secret/PII redaction is incomplete by nature. UI list results use bounded limits; cursor pagination is not implemented. Project storage quotas, distributed rate limits and PostgreSQL RLS are required before external launch. Full WCAG 2.2 AA compliance has not been verified.

## Next delivery priorities

1. Durable agent queue with leases, cancellation and live traces; PostgreSQL integration/tenant tests and RLS.
2. Separate sandbox control plane and isolated preview with security testing; never activate host subprocess execution.
3. Repository intelligence, real-time collaboration and Git issue-to-PR workflow.
4. Identity/governance, metered billing, platform administration and production infrastructure.
5. Full browser/accessibility/load/eval suite and independent security review before commercial release.
