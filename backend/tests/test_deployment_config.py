import pytest
from pydantic import ValidationError
from app.config import Settings


def test_neon_postgres_url_uses_psycopg():
    config = Settings(_env_file=None, database_url='postgresql://user:password@db.example/db')
    assert config.database_url.startswith('postgresql+psycopg://')


def test_cloud_refuses_ephemeral_sqlite():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, vercel=True, database_url='sqlite:///local.db')


def test_cloud_requires_encryption_key():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, vercel=True, database_url='postgresql://db.example/app', encryption_key='')


def test_deployment_origins_are_exact_and_not_wildcard():
    config = Settings(_env_file=None, vercel=True, database_url='postgresql://db.example/app', encryption_key='test-config-only', app_origin='https://app.example', vercel_url='app-unique.vercel.app', vercel_project_production_url='app.vercel.app')
    assert 'https://app-unique.vercel.app' in config.allowed_origins
    assert 'https://app.vercel.app' in config.allowed_origins
    assert 'https://evil.vercel.app' not in config.allowed_origins
