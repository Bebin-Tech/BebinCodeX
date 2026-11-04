# Security model and release gates

## Trust boundaries

Browser → same-origin Next.js proxy → authenticated FastAPI → relational storage. API → explicitly configured provider endpoints. Untrusted source code never crosses into a host command runner. Provider responses can only propose relative source changes; validated server routes authorize application.

Assets: provider keys, code, account credentials, session cookies, organization records, agent snapshots, token quotas. Attackers include unrelated tenants, malicious members, injected source text, compromised providers, and imported archives.

## Controls implemented

- Argon2 password hashing, expiring opaque sessions, hashed session tokens, HttpOnly cookies, logout revocation, Origin validation for mutations.
- Membership checks at every tenant resource route, viewer write denial, personal connection ownership, separate admin role checks for audit/policies/invites.
- Authenticated credential encryption with mandatory environment key, server-configured provider roots, redirects disabled and HTTP proxy environment ignored.
- Relative normalized text paths; no filesystem extraction on import; dotfile/symlink/zip-slip/duplicate rejection, file and expansion limits, secret detection.
- Optimistic project revision locks, atomic proposal application, snapshots, bounded provider agent context/tool/step limits, token reservation.
- No user-code execution on the application server, and no privileged sockets mounted into containers.

## Known limitations / required before production

- Regex redaction cannot guarantee detection of every secret, PII type, or prompt injection. Providers are external data processors. Human review remains required.
- Implement MFA, verified-email/password-reset flows, session/device management, SSO/SCIM, Redis-backed rate limits and distributed quota/cancellation semantics.
- Add PostgreSQL RLS with a separate non-owner application role. Current isolation is application-enforced and covered by SQLite tests, not a database policy guarantee.
- Replace single-key encryption with KMS envelope encryption, dual-read rotation, encrypted backups and key recovery drills.
- Introduce global storage quotas, archive streaming limits at ingress, project size quotas, durable Celery workers and interrupted-run reconciliation. In-process agent execution is not a resilient queue.
- Pin container base image digests after verifying the target registry; scan OS packages and dependencies. No claim that mutable tags are production-pinned.
- Configure HTTPS and COOKIE_SECURE=true. Deploy behind a trusted ingress with request size/rate limits. IP limits behind the Next proxy currently group requests by proxy address.
- Harden Monaco CSP with a verified production nonce/worker strategy; current editor needs eval and inline styles. WCAG conformance and full accessibility audit are not yet established.
- Billing, webhooks, external MCP, arbitrary URL fetches, Git OAuth and deployment actions are absent, so no placeholder credentials activate them.

## Vulnerability disclosure

Do not publish code or keys in an issue. Operators must configure a private security contact before external launch. Preserve correlation IDs and a minimal reproduction; rotate exposed keys immediately.

## Isolated execution addition

Python/JavaScript/native TypeScript execution and static web previews use Vercel Sandbox microVMs. Read EXECUTION.md for tenant checks, time/output/session quotas, blocked VM egress, expiring preview links and iframe restrictions. These controls do not constitute a general sandbox-escape certification, package-scanning service or safe arbitrary deployment pipeline.
