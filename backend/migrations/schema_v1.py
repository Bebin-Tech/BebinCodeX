import uuid
from datetime import datetime, timezone
from sqlalchemy import String, Text, ForeignKey, UniqueConstraint, Integer, JSON, DateTime, Boolean
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.orm import DeclarativeBase
class Base(DeclarativeBase):
    pass


def uid():
    return str(uuid.uuid4())


def now():
    return datetime.now(timezone.utc)


class Record:
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class User(Record, Base):
    __tablename__ = 'users'
    email: Mapped[str] = mapped_column(String(320), unique=True)
    name: Mapped[str] = mapped_column(String(100))
    password_hash: Mapped[str] = mapped_column(Text)


class Session(Record, Base):
    __tablename__ = 'sessions'
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Organization(Record, Base):
    __tablename__ = 'organizations'
    name: Mapped[str] = mapped_column(String(100))
    local_only: Mapped[bool] = mapped_column(Boolean, default=False)
    monthly_token_limit: Mapped[int] = mapped_column(Integer, default=1000000)
    reserved_tokens: Mapped[int] = mapped_column(Integer, default=0)


class Member(Record, Base):
    __tablename__ = 'organization_members'
    __table_args__ = (UniqueConstraint('org_id', 'user_id'),)
    org_id: Mapped[str] = mapped_column(ForeignKey('organizations.id', ondelete='CASCADE'), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), index=True)
    role: Mapped[str] = mapped_column(String(20), default='member')


class Invitation(Record, Base):
    __tablename__ = 'invitations'
    org_id: Mapped[str] = mapped_column(ForeignKey('organizations.id'), index=True)
    email: Mapped[str] = mapped_column(String(320))
    role: Mapped[str] = mapped_column(String(20))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    accepted: Mapped[bool] = mapped_column(Boolean, default=False)


class Project(Record, Base):
    __tablename__ = 'projects'
    org_id: Mapped[str] = mapped_column(ForeignKey('organizations.id'), index=True)
    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[str] = mapped_column(Text, default='')
    revision: Mapped[int] = mapped_column(Integer, default=0)


class File(Record, Base):
    __tablename__ = 'project_files'
    __table_args__ = (UniqueConstraint('project_id', 'path'),)
    project_id: Mapped[str] = mapped_column(ForeignKey('projects.id', ondelete='CASCADE'), index=True)
    path: Mapped[str] = mapped_column(String(512))
    content: Mapped[str] = mapped_column(Text)
    version: Mapped[int] = mapped_column(Integer, default=1)


class FileVersion(Record, Base):
    __tablename__ = 'file_versions'
    project_id: Mapped[str] = mapped_column(ForeignKey('projects.id'), index=True)
    path: Mapped[str] = mapped_column(String(512))
    content: Mapped[str] = mapped_column(Text)
    version: Mapped[int] = mapped_column(Integer)


class Connection(Record, Base):
    __tablename__ = 'user_ai_connections'
    org_id: Mapped[str] = mapped_column(ForeignKey('organizations.id'), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'), index=True)
    provider: Mapped[str] = mapped_column(String(40))
    label: Mapped[str] = mapped_column(String(100))
    encrypted_key: Mapped[str] = mapped_column(Text)


class AgentRun(Record, Base):
    __tablename__ = 'agent_runs'
    project_id: Mapped[str] = mapped_column(ForeignKey('projects.id'), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'))
    prompt: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(30), default='running')
    model: Mapped[str] = mapped_column(String(200))
    base_revision: Mapped[int] = mapped_column(Integer)
    summary: Mapped[str] = mapped_column(Text, default='')
    proposal: Mapped[list] = mapped_column(JSON, default=list)
    snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    applied_revision: Mapped[int | None] = mapped_column(Integer, nullable=True)


class Trace(Record, Base):
    __tablename__ = 'agent_traces'
    run_id: Mapped[str] = mapped_column(ForeignKey('agent_runs.id'), index=True)
    kind: Mapped[str] = mapped_column(String(40))
    data: Mapped[dict] = mapped_column(JSON)


class Usage(Record, Base):
    __tablename__ = 'usage_records'
    org_id: Mapped[str] = mapped_column(ForeignKey('organizations.id'), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'))
    run_id: Mapped[str] = mapped_column(ForeignKey('agent_runs.id'))
    model: Mapped[str] = mapped_column(String(200))
    input_tokens: Mapped[int] = mapped_column(Integer)
    output_tokens: Mapped[int] = mapped_column(Integer)


class Audit(Record, Base):
    __tablename__ = 'audit_logs'
    org_id: Mapped[str] = mapped_column(ForeignKey('organizations.id'), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'))
    action: Mapped[str] = mapped_column(String(100))
    resource_id: Mapped[str] = mapped_column(String(36))

metadata = Base.metadata
