import hashlib
import re
import secrets
from datetime import timedelta, timezone
from pathlib import PurePosixPath
from cryptography.fernet import Fernet
from fastapi import Depends, HTTPException, Request
from pwdlib import PasswordHash
from sqlalchemy import select
from sqlalchemy.orm import Session as DB
from .config import settings
from .db import get_db
from .models import Session, User, Member, Project, now

passwords = PasswordHash.recommended()


def normalize_api_key(value: str, required=True):
    """Accept common clipboard wrappers; never include credentials in errors."""
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
        value = value[1:-1].strip()
    if value.lower().startswith('bearer '):
        value = value[7:].strip()
    if not value and required:
        raise HTTPException(422, 'Enter an API key from the selected provider.')
    if any(c.isspace() or ord(c) < 32 or ord(c) == 127 for c in value):
        raise HTTPException(422, 'Paste only the API key, without spaces or line breaks.')
    return value


def digest(value: str):
    return hashlib.sha256(value.encode()).hexdigest()


def cipher():
    if not settings.encryption_key:
        raise HTTPException(503, 'Configure ENCRYPTION_KEY before storing AI credentials')
    return Fernet(settings.encryption_key.encode())


def current_user(request: Request, db: DB = Depends(get_db)):
    token = request.cookies.get('devpilot_session', '')
    session = db.scalar(select(Session).where(Session.token_hash == digest(token))) if token else None
    if not session or session.expires_at.replace(tzinfo=timezone.utc) <= now():
        raise HTTPException(401, 'Sign in to continue')
    user = db.get(User, session.user_id)
    if not user:
        raise HTTPException(401, 'Session invalid')
    return user


def new_session(db, user, response):
    token = secrets.token_urlsafe(48)
    db.add(Session(user_id=user.id, token_hash=digest(token), expires_at=now() + timedelta(days=7)))
    response.set_cookie('devpilot_session', token, httponly=True, secure=settings.cookie_secure, samesite='lax', max_age=604800, path='/')


def membership(db, user, org_id, write=False, admin=False):
    member = db.scalar(select(Member).where(Member.org_id == org_id, Member.user_id == user.id))
    if not member:
        raise HTTPException(404, 'Organization not found')
    if (write and member.role == 'viewer') or (admin and member.role not in ('owner', 'admin')):
        raise HTTPException(403, 'Insufficient role')
    return member


def project_access(db, user, project_id, write=False):
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(404, 'Project not found')
    membership(db, user, project.org_id, write=write)
    return project


def safe_path(path: str):
    parts = PurePosixPath(path).parts
    if not path or len(path) > 512 or '\\' in path or ':' in path or path.startswith('/') or any(p in ('.', '..') or p.startswith('.') for p in parts) or any(ord(c) < 32 for c in path):
        raise HTTPException(422, 'Unsafe path; use a relative path without dot segments or hidden files')
    if str(PurePosixPath(path)) != path:
        raise HTTPException(422, 'Path must be normalized')
    return path


SECRET = re.compile(r'(?:sk-[A-Za-z0-9_-]{20,}|AKIA[A-Z0-9]{16}|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|(?:api[_-]?key|password|secret|token)\s*[:=]\s*[\"\x27][A-Za-z0-9_+/=-]{16,}[\"\x27])', re.I)


def redact(text):
    text = SECRET.sub('[REDACTED_SECRET]', text)
    return re.sub(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b', '[REDACTED_EMAIL]', text)


def check_content(content):
    if len(content.encode()) > 500_000:
        raise HTTPException(413, 'File exceeds 500 KB')
    if SECRET.search(content):
        raise HTTPException(422, 'Potential credential detected. Use an environment variable instead.')
