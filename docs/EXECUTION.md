# Code execution and live preview

## Use the workspace

Save an open `.py`, `.js`, `.mjs`, `.cjs`, `.ts`, `.mts` or `.cts` file and click **Run file**. The Output panel shows stdout, stderr and the process exit code. TypeScript runs with Node's native type stripping; compilation-only features, JSX/TSX and package installation are not supported.

For a static website, create `index.html` with relative CSS/JavaScript asset references and click **Live preview**. The Preview panel embeds the served page. Every successful saved project revision uploads a new source version to the same sandbox and refreshes the iframe automatically. Stop closes the microVM; an idle preview expires after five minutes. Reopen a project to find its still-active preview through personal execution history.

Supported previews are static HTML/CSS/JavaScript. Vite, Next.js, React bundling, arbitrary dev servers, package installation, external CDNs and interactive stdin terminals are not included. They require a separately controlled dependency/build workflow.

## Isolation and limits

- Official Vercel Python Sandbox SDK and Firecracker microVMs. Source is never executed in FastAPI, Next.js, or a host subprocess.
- One vCPU per VM, ephemeral filesystem and default-deny egress. Source snapshots are limited to 200 files / 2 MB. No application credentials, database URL or provider keys are injected into the VM.
- Script supervisor limits a run to 25 seconds and 64 KB combined output; Unix resource limits constrain child process CPU, file size, open files and process count. The supervisor and generated code share the VM user, so these limits are not an additional security boundary; platform VM isolation and the 60-second runtime timeout bound escape from a child limit.
- Script VMs are destroyed in a finally block. Failed stop calls retain the platform timeout as a fallback. Preview VMs expire in five minutes and are not auto-resumed after expiry.
- Two active sessions per user, five per organization, and 60 new sessions per user per UTC day. Reservations are serialized using database row locks on PostgreSQL; SQLite is for local development.
- Tenant membership and write role checks precede provisioning. Only the session's creator can inspect/control their execution. Activity is audited.

## Preview boundary

Previews run on the separate `*.vercel.run` origin and require an unpredictable access token in the URL path. URLs are encrypted at rest, returned only after authorization, and expire with the sandbox. Anyone receiving a live preview URL can open it until expiry; treat it as a temporary bearer link.

The iframe permits scripts but does not grant same-origin access, forms, popups or top-level navigation. Preview responses set a restrictive CSP, deny directory listings, prevent traversal outside the source root, and omit referrers and caching. Preview browser code can request same-origin static resources; external requests are blocked by CSP. This is static serving, not an authenticated public app deployment.

## Configuration and release

Enable `SANDBOX_ENABLED=true` on a Vercel project with Sandbox access/quota. SDK authentication uses the runtime OIDC identity. Local development requires a separately authorized Vercel development identity; do not copy production keys into source. No unsafe local execution fallback exists when the SDK is unavailable.

Migration `0002` adds `execution_sessions`. Vercel's backend build runs `scripts/migrate_release.py`, which applies forward migrations under a PostgreSQL advisory lock. It never downgrades or resets a live database. Review future migrations for backwards compatibility before pushing, because the Git integration automatically builds and migrates releases.

Sandbox usage can consume the owning Vercel plan's included allowance and metered resources. The app does not upgrade plans or purchase extra capacity. Quota failures return a failed execution with no simulated output. Monitor provider usage before making execution generally available to untrusted external customers.
