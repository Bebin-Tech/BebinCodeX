# Vercel deployment

Project: `bebin-dotms-projects/bebincodex`.

Root `vercel.json` uses Vercel Services (beta) to deploy Next.js from `frontend/` and FastAPI from `backend/`. Ingress routes `/api/v1/*`, `/health` and `/ready` to FastAPI; other paths go to Next.js. Local development retains the existing Next.js API proxy. Node 24 is selected in the Vercel project settings; the hosted Python builder currently selects Python 3.12.

## Storage and secrets

The Neon Marketplace integration provisions `bebincodex-db` on its Free plan in Singapore. Production PostgreSQL was initialized with Alembic `upgrade head`. Existing local accounts, provider credentials and projects are not uploaded; register a new hosted account and reconnect providers.

`DATABASE_URL` comes from the integration. SQLAlchemy normalizes standard PostgreSQL URLs to the psycopg driver. Cloud startup refuses SQLite and missing encryption configuration. Vercel stores separate production and preview `ENCRYPTION_KEY` secrets, `COOKIE_SECURE=true` and the exact production `APP_ORIGIN`. Deployment-specific origins are accepted only from Vercel-provided server environment values. Secrets remain outside Git.

Back up the encryption key under your own access controls before storing important provider connections. Replacing that key prevents decryption of existing connections. Never put it in a public environment variable or commit it.

## Release process

1. Run backend tests and the frontend production build.
2. Apply new migrations explicitly to the intended database, using the unpooled connection for administrative migrations. Do not downgrade a live database.
3. Stage with `vercel deploy --prod --skip-domain` from the linked repository root.
4. Use `vercel curl` to check the staged deployment while preserving Deployment Protection.
5. Promote the tested deployment with `vercel promote <deployment-url>`.

The backend build now runs scripts/migrate_release.py to apply forward migrations under a PostgreSQL advisory lock. Review future migrations for backwards compatibility before pushing; no migration runs on normal API requests. Verify preview branch database isolation through the Neon integration before testing data mutations in preview environments.

## Current boundaries

The release is still the initial functional implementation described in DEVELOPMENT_STATUS.md. SANDBOX_ENABLED enables isolated scripts and static live previews using the deployed project identity. Hosting does not activate collaboration, billing, enterprise SSO, framework dev servers, or Git tools inside the product. Local Ollama cannot be reached from Vercel; a secure reachable endpoint would need separate administrator configuration. Live AI responses require customers' provider keys and remain unverified without them.

Vercel Authentication protects deployment URLs according to the team's project defaults. Sign into the owning Vercel account if prompted. Centralized error monitoring, an external log drain, distributed rate limiting and full production security certification are not configured.
