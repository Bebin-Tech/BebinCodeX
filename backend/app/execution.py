"""Tenant-authorized remote microVM execution. No host subprocess execution."""
import asyncio
import json
import logging
import secrets
from datetime import timedelta, timezone
from pathlib import PurePosixPath
from urllib.parse import quote, urlsplit
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from vercel import sandbox
from vercel.api import session as sandbox_api
from vercel.sandbox import NetworkPolicy, SandboxResources
from .config import settings
from .db import get_db
from .models import Audit, Execution, File, Organization, Project, User, now
from .security import current_user, project_access, safe_path, check_content, redact, cipher
from .sandbox_programs import RUNNER, PREVIEW_SERVER

router = APIRouter(prefix='/api/v1')
ACTIVE = ('starting', 'running')
WORK = '/vercel/sandbox/workspace'
PREVIEWS = '/vercel/sandbox/previews'
logger = logging.getLogger('bebincodex.sandbox')


def log_failure(record, error):
    logger.error('sandbox_operation_failed execution=%s type=%s status=%s', record.id, type(error).__name__, getattr(getattr(error, 'response', None), 'status_code', None))


class ExecuteRequest(BaseModel):
    path: str = Field(min_length=1, max_length=512)


class PreviewRequest(BaseModel):
    path: str = Field(default='index.html', min_length=1, max_length=512)


def require_enabled():
    if not settings.sandbox_enabled:
        raise HTTPException(503, 'Code execution is not enabled. Configure Vercel Sandbox and SANDBOX_ENABLED on the server.')


def source_files(db, project_id):
    rows = db.scalars(select(File).where(File.project_id == project_id).order_by(File.path)).all()
    if len(rows) > 200 or sum(len(f.content.encode()) for f in rows) > 2_000_000:
        raise HTTPException(413, 'Execution supports up to 200 files and 2 MB of source.')
    for f in rows:
        safe_path(f.path)
        check_content(f.content)
    return {f.path: f.content for f in rows}


def command_for(path):
    safe_path(path)
    extension = PurePosixPath(path).suffix.lower()
    if extension == '.py':
        return ['python3', '-u', WORK + '/' + path]
    if extension in ('.js', '.mjs', '.cjs', '.ts', '.mts', '.cts'):
        return ['node', WORK + '/' + path]
    raise HTTPException(422, 'Run supports Python, JavaScript, and native TypeScript. Use Preview for HTML projects.')


def reserve(db, user, project, kind, path):
    # Serialize both user-wide and organization-wide reservations in PostgreSQL.
    db.scalar(select(User).where(User.id == user.id).with_for_update())
    db.scalar(select(Organization).where(Organization.id == project.org_id).with_for_update())
    if kind == 'preview' and db.scalar(select(Execution.id).where(Execution.project_id == project.id, Execution.user_id == user.id, Execution.kind == 'preview', Execution.status.in_(ACTIVE), Execution.expires_at > now())):
        raise HTTPException(409, 'A preview is already active. Refresh or stop it before starting another.')
    org_active = db.scalar(select(func.count()).select_from(Execution).join(Project, Project.id == Execution.project_id).where(Project.org_id == project.org_id, Execution.status.in_(ACTIVE), Execution.expires_at > now()))
    if org_active >= 5:
        raise HTTPException(429, 'Organization limit of five active sandbox sessions reached.')
    active = db.scalar(select(func.count()).select_from(Execution).where(Execution.user_id == user.id, Execution.status.in_(ACTIVE), Execution.expires_at > now()))
    if active >= 2:
        raise HTTPException(429, 'Stop an active preview or wait for your current run to finish.')
    day = now().replace(hour=0, minute=0, second=0, microsecond=0)
    count = db.scalar(select(func.count()).select_from(Execution).where(Execution.user_id == user.id, Execution.created_at >= day))
    if count >= 60:
        raise HTTPException(429, 'Daily limit of 60 execution/preview sessions reached.')
    record = Execution(project_id=project.id, user_id=user.id, kind=kind, path=path, revision=project.revision, expires_at=now() + timedelta(seconds=300 if kind == 'preview' else 90))
    db.add(record)
    db.flush()
    record.sandbox_name = 'bxc-' + record.id
    db.add(Audit(org_id=project.org_id, user_id=user.id, action='sandbox.' + kind, resource_id=record.id))
    db.commit()
    return record


def is_expired(record):
    return record.expires_at.replace(tzinfo=timezone.utc) <= now()


def execution_json(record):
    expired = record.status in ACTIVE and is_expired(record)
    return {
        'id': record.id, 'kind': record.kind, 'path': record.path,
        'revision': record.revision, 'status': 'expired' if expired else record.status,
        'output': record.output, 'exit_code': record.exit_code,
        'created_at': record.created_at.replace(tzinfo=timezone.utc),
        'expires_at': record.expires_at.replace(tzinfo=timezone.utc),
        'preview_url': cipher().decrypt(record.encrypted_preview.encode()).decode() if record.encrypted_preview and record.status == 'running' and not expired else None,
    }


def execution_access(db, user, execution_id, write=False):
    record = db.get(Execution, execution_id)
    if not record:
        raise HTTPException(404, 'Execution not found')
    project = project_access(db, user, record.project_id, write=write)
    if record.user_id != user.id:
        raise HTTPException(404, 'Execution not found')
    return record, project


async def upload(box, files, directory):
    # Project paths are validated before any SDK request; source never selects a host path.
    await box.fs.mkdir(directory)
    async with box.fs.batch() as batch:
        for path, content in files.items():
            batch.write_text(directory + '/' + path, content)


async def new_box(record, preview=False):
    return await sandbox.create_sandbox(
        name=record.sandbox_name, persistent=False,
        execution_time_limit=300 if preview else 60,
        resources=SandboxResources(vcpus=1),
        network_policy=NetworkPolicy.deny_all(),
        ports=[3000] if preview else [], env={},
    )


async def cleanup(box):
    if box:
        try:
            await asyncio.wait_for(box.destroy(delete_orphan_snapshots=True), timeout=15)
        except Exception:
            # The platform-enforced session timeout still bounds an unavailable stop API.
            pass


@router.get('/projects/{project_id}/executions')
def history(project_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    project_access(db, user, project_id)
    rows = db.scalars(select(Execution).where(Execution.project_id == project_id, Execution.user_id == user.id).order_by(Execution.created_at.desc()).limit(20)).all()
    return [execution_json(r) for r in rows]


@router.post('/projects/{project_id}/sandbox')
async def run_file(project_id: str, data: ExecuteRequest | None = None, user: User = Depends(current_user), db: Session = Depends(get_db)):
    project = project_access(db, user, project_id, write=True)
    require_enabled()
    files = source_files(db, project_id)
    path = data.path if data else next((p for p in ('main.py', 'index.js', 'main.js', 'main.ts') if p in files), '')
    command = command_for(path)
    if path not in files:
        raise HTTPException(404, 'Source file not found')
    record = reserve(db, user, project, 'run', path)
    box = None
    async with sandbox_api():
        try:
            async with asyncio.timeout(100):
                box = await new_box(record)
                await upload(box, files, WORK)
                await box.fs.write_text('/vercel/sandbox/bxc-runner.py', RUNNER)
                record.status = 'running'
                db.commit()
                result = await box.run_process('python3', ['/vercel/sandbox/bxc-runner.py', *command], capture_output=True, kill_after=35)
                if result.returncode != 0:
                    raise RuntimeError('Execution supervisor stopped')
                output = json.loads(result.stdout or '{}')
                record.exit_code = int(output['exit_code'])
                record.output = redact('\n'.join(str(output.get(k, '')) for k in ('stdout', 'stderr', 'reason')).strip())[:70000]
                record.status = 'completed' if record.exit_code == 0 else 'failed'
        except Exception as error:
            log_failure(record, error)
            record.status = 'failed'
            record.output = 'Sandbox could not complete this run. Check Vercel Sandbox access/quota or try again.'
        finally:
            await cleanup(box)
            db.commit()
    return execution_json(record)


@router.post('/projects/{project_id}/preview')
async def start_preview(project_id: str, data: PreviewRequest, user: User = Depends(current_user), db: Session = Depends(get_db)):
    project = project_access(db, user, project_id, write=True)
    require_enabled()
    files = source_files(db, project_id)
    path = safe_path(data.path)
    if not path.lower().endswith(('.html', '.htm')) or path not in files:
        raise HTTPException(422, 'Choose an HTML file to preview. Framework builds and package installation are not supported yet.')
    # Require explicit stop rather than accidentally allocating a fresh VM per click/save.
    previous = db.scalar(select(Execution).where(Execution.project_id == project_id, Execution.user_id == user.id, Execution.kind == 'preview', Execution.status.in_(ACTIVE), Execution.expires_at > now()))
    if previous:
        raise HTTPException(409, 'A preview is already active. Refresh or stop it before starting another.')
    record = reserve(db, user, project, 'preview', path)
    token, version = secrets.token_urlsafe(32), secrets.token_hex(8)
    box = None
    async with sandbox_api():
        try:
            async with asyncio.timeout(100):
                box = await new_box(record, preview=True)
                await upload(box, files, PREVIEWS + '/' + version)
                await box.fs.write_text('/vercel/sandbox/bxc-preview.py', PREVIEW_SERVER)
                await box.create_process('python3', ['/vercel/sandbox/bxc-preview.py', token], stdout=-3, stderr=-3)
                ready = await box.run_process('python3', ['-c', "import time,urllib.request\nfor i in range(30):\n try:\n  urllib.request.urlopen('http://127.0.0.1:3000/" + token + '/' + version + '/' + quote(path) + "',timeout=1);break\n except Exception:\n  time.sleep(.2)\nelse: raise SystemExit(1)"], capture_output=True, kill_after=15)
                if ready.returncode != 0:
                    raise RuntimeError('Preview server did not become ready')
                origin = next(route.url.rstrip('/') for route in box.routes if route.port == 3000)
                parsed = urlsplit(origin)
                if parsed.scheme != 'https' or not parsed.hostname or not parsed.hostname.endswith('.vercel.run'):
                    raise RuntimeError('Unexpected sandbox preview origin')
                record.encrypted_preview = cipher().encrypt((origin + '/' + token + '/' + version + '/' + quote(path)).encode()).decode()
                record.status = 'running'
                record.output = 'Preview ready. Saved edits refresh automatically. Expires after five minutes.'
        except Exception as error:
            log_failure(record, error)
            record.status = 'failed'
            record.output = 'Preview could not start. Check Vercel Sandbox access/quota or try again.'
            await cleanup(box)
        db.commit()
    return execution_json(record)


@router.put('/executions/{execution_id}/preview')
async def refresh_preview(execution_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    record, project = execution_access(db, user, execution_id, write=True)
    require_enabled()
    if record.kind != 'preview' or record.status != 'running' or is_expired(record):
        raise HTTPException(410, 'Preview has stopped or expired. Start a new preview.')
    if record.revision == project.revision:
        return execution_json(record)
    files = source_files(db, project.id)
    if record.path not in files:
        raise HTTPException(422, 'The preview entry file was deleted. Stop this preview and select another HTML file.')
    previous = urlsplit(cipher().decrypt(record.encrypted_preview.encode()).decode())
    token = previous.path.split('/')[1]
    version = secrets.token_hex(8)
    async with sandbox_api():
        try:
            async with asyncio.timeout(45):
                box = await sandbox.get_sandbox(name=record.sandbox_name)
                # Never auto-resume an expired/stopped ephemeral session.
                if str(box.status).lower() not in ('running', 'sandboxstatus.running'):
                    raise HTTPException(410, 'Preview expired. Start a new preview.')
                await upload(box, files, PREVIEWS + '/' + version)
                url = previous.scheme + '://' + previous.netloc + '/' + token + '/' + version + '/' + quote(record.path)
                record.encrypted_preview = cipher().encrypt(url.encode()).decode()
                record.revision = project.revision
                db.commit()
        except HTTPException:
            raise
        except Exception:
            raise HTTPException(503, 'Preview refresh failed. Stop it and start a new preview.')
    return execution_json(record)


@router.delete('/executions/{execution_id}')
async def stop_execution(execution_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    record, project = execution_access(db, user, execution_id, write=True)
    if record.status in ACTIVE and not is_expired(record):
        async with sandbox_api():
            try:
                box = await sandbox.get_sandbox(name=record.sandbox_name)
                await asyncio.wait_for(box.destroy(delete_orphan_snapshots=True), timeout=20)
            except Exception:
                raise HTTPException(503, 'Sandbox stop failed. Try again; its automatic timeout remains active.')
    record.status = 'stopped'
    record.encrypted_preview = ''
    db.add(Audit(org_id=project.org_id, user_id=user.id, action='sandbox.stop', resource_id=record.id))
    db.commit()
    return execution_json(record)
