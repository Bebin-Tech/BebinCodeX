import io
import json
import secrets
import time
import uuid
import zipfile
from collections import defaultdict, deque
from datetime import timedelta, timezone
from fastapi import FastAPI, Depends, HTTPException, Request, Response, UploadFile
from fastapi.responses import StreamingResponse, JSONResponse
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select, delete, update, func
from sqlalchemy.orm import Session as DB
from sqlalchemy.exc import IntegrityError
from .config import settings
from .db import get_db
from .models import User, Session, Organization, Member, Invitation, Project, File, FileVersion, Connection, AgentRun, Trace, Usage, Audit, now
from .security import current_user, new_session, passwords, digest, membership, project_access, cipher, safe_path, check_content, normalize_api_key
from .gateway import Gateway, PROVIDERS
from .agent import execute

app = FastAPI(title='BebincodeX API', version='0.1.0')
API = '/api/v1'
rate_windows = defaultdict(deque)


@app.exception_handler(RequestValidationError)
async def validation_error(request, error):
    # Pydantic's default input field can contain raw keys/passwords. Omit it.
    return JSONResponse(status_code=422, content={'detail': [{'loc': e['loc'], 'msg': e['msg'], 'type': e['type']} for e in error.errors()]})


@app.middleware('http')
async def boundary(request: Request, call_next):
    correlation = str(uuid.uuid4())
    if request.method not in ('GET', 'HEAD', 'OPTIONS'):
        if request.headers.get('origin') not in settings.allowed_origins:
            return JSONResponse({'detail': 'Origin rejected'}, status_code=403)
        length = request.headers.get('content-length')
        if length and (not length.isdigit() or int(length) > 6_000_000):
            return JSONResponse({'detail': 'Request too large'}, status_code=413)
    # Single-process development limiter. Use Redis-backed edge limits in production.
    key = (request.client.host if request.client else 'unknown', 'auth' if '/auth/' in request.url.path else 'api')
    window = rate_windows[key]
    stamp = time.monotonic()
    while window and stamp - window[0] > 60:
        window.popleft()
    limit = 20 if key[1] == 'auth' else 180
    if len(window) >= limit:
        return JSONResponse({'detail': 'Rate limit exceeded'}, status_code=429, headers={'Retry-After': '60'})
    window.append(stamp)
    response = await call_next(request)
    response.headers.update({'X-Request-ID': correlation, 'X-Content-Type-Options': 'nosniff', 'Referrer-Policy': 'same-origin', 'Cache-Control': 'no-store', 'X-RateLimit-Limit': str(limit), 'X-RateLimit-Remaining': str(max(0, limit - len(window)))})
    return response


def audit(db, user, org_id, action, resource):
    db.add(Audit(org_id=org_id, user_id=user.id, action=action, resource_id=resource))


def user_json(user):
    return {'id': user.id, 'name': user.name, 'email': user.email}


class Credentials(BaseModel):
    email: EmailStr
    password: str = Field(min_length=12, max_length=128)
    name: str = Field(default='', max_length=100)


@app.post(API + '/auth/register')
def register(data: Credentials, response: Response, db: DB = Depends(get_db)):
    user = User(email=str(data.email).lower(), name=data.name.strip() or str(data.email).split('@')[0], password_hash=passwords.hash(data.password))
    db.add(user)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, 'Unable to register with this email')
    new_session(db, user, response)
    db.commit()
    return user_json(user)


@app.post(API + '/auth/login')
def login(data: Credentials, response: Response, db: DB = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == str(data.email).lower()))
    # Always perform a password hash verification to reduce account enumeration timing.
    hashed = user.password_hash if user else passwords.hash('unavailable-account-password')
    if not passwords.verify(data.password, hashed) or not user:
        raise HTTPException(401, 'Invalid email or password')
    new_session(db, user, response)
    db.commit()
    return user_json(user)


@app.post(API + '/auth/logout')
def logout(request: Request, response: Response, db: DB = Depends(get_db)):
    db.execute(delete(Session).where(Session.token_hash == digest(request.cookies.get('devpilot_session', ''))))
    db.commit()
    response.delete_cookie('devpilot_session', path='/')
    return {'ok': True}


@app.get(API + '/auth/me')
def me(user: User = Depends(current_user)):
    return user_json(user)


class Name(BaseModel):
    name: str = Field(min_length=1, max_length=100)


@app.get(API + '/organizations')
def organizations(user: User = Depends(current_user), db: DB = Depends(get_db)):
    rows = db.execute(select(Organization, Member.role).join(Member, Member.org_id == Organization.id).where(Member.user_id == user.id).order_by(Organization.created_at)).all()
    return [{'id': o.id, 'name': o.name, 'role': role, 'local_only': o.local_only, 'monthly_token_limit': o.monthly_token_limit} for o, role in rows]


@app.post(API + '/organizations')
def create_org(data: Name, user: User = Depends(current_user), db: DB = Depends(get_db)):
    org = Organization(name=data.name)
    db.add(org)
    db.flush()
    db.add(Member(org_id=org.id, user_id=user.id, role='owner'))
    audit(db, user, org.id, 'organization.create', org.id)
    db.commit()
    return {'id': org.id, 'name': org.name}


class OrgPolicy(BaseModel):
    local_only: bool
    monthly_token_limit: int = Field(ge=0, le=1000000000)


@app.put(API + '/organizations/{org_id}/policy')
def policy(org_id: str, data: OrgPolicy, user: User = Depends(current_user), db: DB = Depends(get_db)):
    membership(db, user, org_id, admin=True)
    org = db.get(Organization, org_id)
    org.local_only = data.local_only
    org.monthly_token_limit = data.monthly_token_limit
    audit(db, user, org_id, 'policy.update', org_id)
    db.commit()
    return {'ok': True}


@app.get(API + '/organizations/{org_id}/members')
def members(org_id: str, user: User = Depends(current_user), db: DB = Depends(get_db)):
    membership(db, user, org_id)
    return [{'id': m.id, 'name': u.name, 'email': u.email, 'role': m.role} for m, u in db.execute(select(Member, User).join(User, User.id == Member.user_id).where(Member.org_id == org_id))]


class Invite(BaseModel):
    email: EmailStr
    role: str = Field(pattern='^(admin|member|viewer)$')


@app.post(API + '/organizations/{org_id}/invitations')
def invite(org_id: str, data: Invite, user: User = Depends(current_user), db: DB = Depends(get_db)):
    membership(db, user, org_id, admin=True)
    token = secrets.token_urlsafe(32)
    invite = Invitation(org_id=org_id, email=str(data.email).lower(), role=data.role, token_hash=digest(token), expires_at=now() + timedelta(days=3))
    db.add(invite)
    audit(db, user, org_id, 'invitation.create', org_id)
    db.commit()
    return {'token': token, 'expires_at': invite.expires_at, 'note': 'Share this one-time token with the intended member. Email delivery is not configured.'}


class Token(BaseModel):
    token: str = Field(min_length=20, max_length=200)


@app.post(API + '/invitations/accept')
def accept_invite(data: Token, user: User = Depends(current_user), db: DB = Depends(get_db)):
    invitation = db.scalar(select(Invitation).where(Invitation.token_hash == digest(data.token)))
    if not invitation or invitation.email != user.email or invitation.accepted or invitation.expires_at.replace(tzinfo=timezone.utc) <= now():
        raise HTTPException(404, 'Invitation unavailable')
    result = db.execute(update(Invitation).where(Invitation.id == invitation.id, Invitation.accepted == False).values(accepted=True))
    if not result.rowcount:
        raise HTTPException(409, 'Invitation already accepted')
    if not db.scalar(select(Member).where(Member.org_id == invitation.org_id, Member.user_id == user.id)):
        db.add(Member(org_id=invitation.org_id, user_id=user.id, role=invitation.role))
    audit(db, user, invitation.org_id, 'invitation.accept', invitation.id)
    db.commit()
    return {'org_id': invitation.org_id}


class NewProject(Name):
    description: str = Field(default='', max_length=2000)
    template: str = Field(default='empty', pattern='^(empty|python|web)$')


@app.get(API + '/organizations/{org_id}/projects')
def projects(org_id: str, user: User = Depends(current_user), db: DB = Depends(get_db)):
    membership(db, user, org_id)
    return db.scalars(select(Project).where(Project.org_id == org_id).order_by(Project.created_at.desc()).limit(100)).all()


@app.post(API + '/organizations/{org_id}/projects')
def create_project(org_id: str, data: NewProject, user: User = Depends(current_user), db: DB = Depends(get_db)):
    membership(db, user, org_id, write=True)
    project = Project(org_id=org_id, name=data.name, description=data.description)
    db.add(project)
    db.flush()
    files = {'DEVPILOT.md': '# Project conventions\n\nKeep changes focused. Add meaningful tests. Never commit credentials.\n'}
    if data.template == 'python':
        files['main.py'] = 'def greet(name: str) -> str:\n    return f"Hello, {name}!"\n\n\nif __name__ == "__main__":\n    print(greet("world"))\n'
    elif data.template == 'web':
        files['index.html'] = '<!doctype html>\n<html lang="en">\n<head><meta charset="UTF-8"><title>My application</title></head>\n<body><h1>Hello, world!</h1></body>\n</html>\n'
    for path, content in files.items():
        db.add(File(project_id=project.id, path=path, content=content))
    audit(db, user, org_id, 'project.create', project.id)
    db.commit()
    return project


@app.get(API + '/projects/{project_id}')
def get_project(project_id: str, user: User = Depends(current_user), db: DB = Depends(get_db)):
    return project_access(db, user, project_id)


@app.get(API + '/projects/{project_id}/files')
def files(project_id: str, user: User = Depends(current_user), db: DB = Depends(get_db)):
    project_access(db, user, project_id)
    return db.scalars(select(File).where(File.project_id == project_id).order_by(File.path)).all()


def lock_revision(db, project, expected):
    result = db.execute(update(Project).where(Project.id == project.id, Project.revision == expected).values(revision=Project.revision + 1))
    if not result.rowcount:
        db.rollback()
        raise HTTPException(409, 'Project changed. Reload before applying changes.')


def set_file(db, project_id, path, content):
    file = db.scalar(select(File).where(File.project_id == project_id, File.path == path))
    if file:
        db.add(FileVersion(project_id=project_id, path=path, content=file.content, version=file.version))
        if content is None:
            db.delete(file)
        else:
            file.content = content
            file.version += 1
    elif content is not None:
        db.add(File(project_id=project_id, path=path, content=content))


class SaveFile(BaseModel):
    path: str
    content: str | None
    revision: int = Field(ge=0)


@app.put(API + '/projects/{project_id}/files')
def save_file(project_id: str, data: SaveFile, user: User = Depends(current_user), db: DB = Depends(get_db)):
    project = project_access(db, user, project_id, write=True)
    safe_path(data.path)
    if data.content is not None:
        check_content(data.content)
    lock_revision(db, project, data.revision)
    set_file(db, project_id, data.path, data.content)
    audit(db, user, project.org_id, 'file.delete' if data.content is None else 'file.save', project_id)
    db.commit()
    return {'revision': data.revision + 1}


@app.get(API + '/projects/{project_id}/history')
def history(project_id: str, path: str, user: User = Depends(current_user), db: DB = Depends(get_db)):
    project_access(db, user, project_id)
    return db.scalars(select(FileVersion).where(FileVersion.project_id == project_id, FileVersion.path == path).order_by(FileVersion.created_at.desc()).limit(50)).all()


@app.get(API + '/projects/{project_id}/search')
def search(project_id: str, q: str, user: User = Depends(current_user), db: DB = Depends(get_db)):
    project_access(db, user, project_id)
    if not q or len(q) > 200:
        raise HTTPException(422, 'Query must contain 1–200 characters')
    return [{'path': f.path, 'line': n + 1, 'text': line[:300]} for f in db.scalars(select(File).where(File.project_id == project_id)) for n, line in enumerate(f.content.splitlines()) if q.lower() in line.lower()][:100]


@app.get(API + '/projects/{project_id}/export')
def export(project_id: str, user: User = Depends(current_user), db: DB = Depends(get_db)):
    project_access(db, user, project_id)
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as archive:
        for file in db.scalars(select(File).where(File.project_id == project_id)):
            archive.writestr(file.path, file.content)
    return Response(output.getvalue(), media_type='application/zip', headers={'Content-Disposition': 'attachment; filename="project.zip"'})


@app.post(API + '/projects/{project_id}/import')
async def import_zip(project_id: str, request: Request, revision: int, user: User = Depends(current_user), db: DB = Depends(get_db)):
    project = project_access(db, user, project_id, write=True)
    raw = await request.body()
    if len(raw) > 5_000_000:
        raise HTTPException(413, 'Archive exceeds 5 MB')
    changes = []
    paths = set()
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            if len(archive.infolist()) > 500 or sum(f.file_size for f in archive.infolist()) > 5_000_000:
                raise HTTPException(413, 'Archive expands beyond file or size limit')
            for entry in archive.infolist():
                if entry.is_dir():
                    continue
                path = safe_path(entry.filename)
                if path in paths or (entry.external_attr >> 16) & 0o170000 == 0o120000:
                    raise HTTPException(422, 'Duplicate path or symlink in ZIP')
                paths.add(path)
                content = archive.read(entry).decode('utf-8')
                check_content(content)
                changes.append((path, content))
    except (zipfile.BadZipFile, UnicodeDecodeError, RuntimeError):
        raise HTTPException(422, 'Import requires an unencrypted ZIP of UTF-8 source files')
    lock_revision(db, project, revision)
    for path, content in changes:
        set_file(db, project_id, path, content)
    audit(db, user, project.org_id, 'project.import', project_id)
    db.commit()
    return {'files': len(changes), 'revision': revision + 1}


class NewConnection(BaseModel):
    provider: str
    label: str = Field(min_length=1, max_length=100)
    api_key: str = Field(default='', max_length=2000)


@app.get(API + '/organizations/{org_id}/connections')
def connections(org_id: str, user: User = Depends(current_user), db: DB = Depends(get_db)):
    membership(db, user, org_id)
    return [{'id': c.id, 'provider': c.provider, 'label': c.label} for c in db.scalars(select(Connection).where(Connection.org_id == org_id, Connection.user_id == user.id))]


@app.post(API + '/organizations/{org_id}/connections')
def connect(org_id: str, data: NewConnection, user: User = Depends(current_user), db: DB = Depends(get_db)):
    membership(db, user, org_id, write=True)
    if data.provider not in PROVIDERS:
        raise HTTPException(422, 'Select a provider and supply its API key')
    key = normalize_api_key(data.api_key, required=data.provider != 'ollama')
    if db.get(Organization, org_id).local_only and data.provider != 'ollama':
        raise HTTPException(403, 'Organization permits local providers only')
    connection = Connection(org_id=org_id, user_id=user.id, provider=data.provider, label=data.label, encrypted_key=cipher().encrypt(key.encode()).decode())
    db.add(connection)
    audit(db, user, org_id, 'connection.create', org_id)
    db.commit()
    return {'id': connection.id, 'provider': connection.provider, 'label': connection.label}


def owned_connection(db, user, connection_id):
    connection = db.get(Connection, connection_id)
    if not connection or connection.user_id != user.id:
        raise HTTPException(404, 'Connection not found')
    membership(db, user, connection.org_id)
    if db.get(Organization, connection.org_id).local_only and connection.provider != 'ollama':
        raise HTTPException(403, 'Organization permits local providers only')
    return connection


class UpdateConnectionKey(BaseModel):
    api_key: str = Field(min_length=1, max_length=2000)


@app.put(API + '/connections/{connection_id}')
def update_connection_key(connection_id: str, data: UpdateConnectionKey, user: User = Depends(current_user), db: DB = Depends(get_db)):
    connection = owned_connection(db, user, connection_id)
    membership(db, user, connection.org_id, write=True)
    key = normalize_api_key(data.api_key)
    connection.encrypted_key = cipher().encrypt(key.encode()).decode()
    audit(db, user, connection.org_id, 'connection.key_update', connection.id)
    db.commit()
    return {'id': connection.id, 'provider': connection.provider, 'label': connection.label}


@app.delete(API + '/connections/{connection_id}')
def disconnect(connection_id: str, user: User = Depends(current_user), db: DB = Depends(get_db)):
    connection = owned_connection(db, user, connection_id)
    audit(db, user, connection.org_id, 'connection.delete', connection_id)
    db.delete(connection)
    db.commit()
    return {'ok': True}


@app.get(API + '/connections/{connection_id}/models')
async def models(connection_id: str, user: User = Depends(current_user), db: DB = Depends(get_db)):
    connection = owned_connection(db, user, connection_id)
    return {'models': await Gateway(connection).models(), 'capabilities': 'Provider-reported model IDs. Tool support is validated by the provider at request time; unsupported requests fail explicitly.'}


class RunRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=12000)
    connection_id: str
    model: str = Field(min_length=1, max_length=200)


def run_json(run):
    return {'id': run.id, 'project_id': run.project_id, 'prompt': run.prompt, 'status': run.status, 'model': run.model, 'summary': run.summary, 'proposal': run.proposal, 'base_revision': run.base_revision, 'created_at': run.created_at, 'snapshot': run.snapshot, 'applied_revision': run.applied_revision}


@app.post(API + '/projects/{project_id}/runs')
async def start_run(project_id: str, data: RunRequest, user: User = Depends(current_user), db: DB = Depends(get_db)):
    project = project_access(db, user, project_id, write=True)
    connection = owned_connection(db, user, data.connection_id)
    if connection.org_id != project.org_id:
        raise HTTPException(404, 'Connection not found')
    return run_json(await execute(db, user, project, connection, data.model, data.prompt))


@app.get(API + '/projects/{project_id}/runs')
def runs(project_id: str, user: User = Depends(current_user), db: DB = Depends(get_db)):
    project_access(db, user, project_id)
    return [run_json(r) for r in db.scalars(select(AgentRun).where(AgentRun.project_id == project_id).order_by(AgentRun.created_at.desc()).limit(50))]


def authorized_run(db, user, run_id, write=False):
    run = db.get(AgentRun, run_id)
    if not run:
        raise HTTPException(404, 'Run not found')
    project = project_access(db, user, run.project_id, write=write)
    return run, project


@app.get(API + '/runs/{run_id}/traces')
def traces(run_id: str, user: User = Depends(current_user), db: DB = Depends(get_db)):
    authorized_run(db, user, run_id)
    return db.scalars(select(Trace).where(Trace.run_id == run_id).order_by(Trace.created_at)).all()


class ApplyRequest(BaseModel):
    paths: list[str] = Field(max_length=20)


@app.post(API + '/runs/{run_id}/apply')
def apply_run(run_id: str, data: ApplyRequest, user: User = Depends(current_user), db: DB = Depends(get_db)):
    run, project = authorized_run(db, user, run_id, write=True)
    if run.status != 'awaiting_approval':
        raise HTTPException(409, 'Run is not awaiting approval')
    available = {c['path'] for c in run.proposal}
    if not data.paths or not set(data.paths).issubset(available):
        raise HTTPException(422, 'Select valid proposed files')
    lock_revision(db, project, run.base_revision)
    for change in run.proposal:
        if change['path'] in data.paths:
            safe_path(change['path'])
            if change['content'] is not None:
                check_content(change['content'])
            set_file(db, project.id, change['path'], change['content'])
    run.status = 'applied'
    run.applied_revision = run.base_revision + 1
    audit(db, user, project.org_id, 'agent.apply', run.id)
    db.commit()
    return {'revision': run.applied_revision}


@app.post(API + '/runs/{run_id}/reject')
def reject_run(run_id: str, user: User = Depends(current_user), db: DB = Depends(get_db)):
    run, project = authorized_run(db, user, run_id, write=True)
    if run.status != 'awaiting_approval':
        raise HTTPException(409, 'Run is not awaiting approval')
    run.status = 'rejected'
    audit(db, user, project.org_id, 'agent.reject', run.id)
    db.commit()
    return {'ok': True}


@app.post(API + '/runs/{run_id}/rollback')
def rollback(run_id: str, user: User = Depends(current_user), db: DB = Depends(get_db)):
    run, project = authorized_run(db, user, run_id, write=True)
    if run.status != 'applied' or run.applied_revision is None:
        raise HTTPException(409, 'Only an applied run can be restored')
    lock_revision(db, project, run.applied_revision)
    existing = {f.path for f in db.scalars(select(File).where(File.project_id == project.id))}
    for path in existing | set(run.snapshot):
        set_file(db, project.id, path, run.snapshot.get(path))
    run.status = 'rolled_back'
    audit(db, user, project.org_id, 'agent.rollback', run.id)
    db.commit()
    return {'revision': run.applied_revision + 1}


@app.get(API + '/organizations/{org_id}/usage')
def usage(org_id: str, user: User = Depends(current_user), db: DB = Depends(get_db)):
    membership(db, user, org_id)
    month = now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    rows = db.execute(select(Usage.model, func.sum(Usage.input_tokens), func.sum(Usage.output_tokens), func.count()).where(Usage.org_id == org_id, Usage.created_at >= month).group_by(Usage.model)).all()
    return {'models': [{'model': m, 'input_tokens': i, 'output_tokens': o, 'runs': c} for m, i, o, c in rows], 'token_limit': db.get(Organization, org_id).monthly_token_limit, 'cost': None, 'note': 'Tokens reported by providers. Monetary pricing and subscription billing are not enabled.'}


@app.get(API + '/organizations/{org_id}/audit')
def audits(org_id: str, user: User = Depends(current_user), db: DB = Depends(get_db)):
    membership(db, user, org_id, admin=True)
    return db.scalars(select(Audit).where(Audit.org_id == org_id).order_by(Audit.created_at.desc()).limit(100)).all()


from .execution import router as execution_router
app.include_router(execution_router)


@app.get('/health')
def health():
    return {'status': 'ok', 'version': '0.1.0'}


@app.get('/ready')
def ready(db: DB = Depends(get_db)):
    db.execute(select(User.id).limit(1))
    return {'database': 'ready', 'credential_encryption': bool(settings.encryption_key)}
