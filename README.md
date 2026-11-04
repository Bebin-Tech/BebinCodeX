# BebincodeX

An executable Next.js + FastAPI foundation for a tenant-scoped AI coding workspace. See [DEVELOPMENT_STATUS.md](DEVELOPMENT_STATUS.md) for verified scope; this repository is not yet an enterprise production release.

## Windows development

Requires Python 3.12+, Node 22+, and optionally Docker Desktop with Linux containers.

```powershell
git clone https://github.com/Bebin-Tech/BebinCodeX.git
cd BebinCodeX
Copy-Item .env.example .env
python -m venv .venv
.\.venv\Scripts\python -m pip install -r backend/requirements.txt
.\.venv\Scripts\python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
# Set ENCRYPTION_KEY in .env to the generated value. Never commit .env.
cd backend
..\.venv\Scripts\python -m alembic upgrade head
..\.venv\Scripts\python -m uvicorn app.main:app --reload --port 8000
# In a second terminal:
cd BebinCodeX/frontend
npm install
npm run dev
```

Open http://localhost:3000. Register, create an organization and a project, add a provider in Connections, discover models, and start an agent request. Review its proposed file diff before applying. No sample accounts or simulated AI responses are supplied. The API is documented at http://localhost:8000/docs.

SQLite is the local default. Set DATABASE_URL to a PostgreSQL psycopg URL for deployment. `docker compose up --build` starts PostgreSQL, Redis, API and frontend. Set ENCRYPTION_KEY first. Run database migrations before starting multiple API instances. The Next.js server proxies `/api/v1` to the API so browser sessions stay on one origin.

```powershell
cd backend
..\.venv\Scripts\python -m pytest -q
cd ../frontend
npm run typecheck
npm run build
```

Provider credentials are encrypted at rest. Remote requests target administrator-configured endpoint roots only. Configure Ollama through OLLAMA_URL; it is never selected from a browser-provided URL. Use **Run file** for saved Python, JavaScript and native TypeScript files, or **Live preview** for static HTML/CSS/JavaScript projects. Execution uses Vercel Sandbox microVMs with blocked egress; no code runs on the API host. See [execution documentation](docs/EXECUTION.md) for limits, supported runtimes and setup. Interactive terminals and framework/package builds are not supported.
