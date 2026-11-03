import os
import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

os.environ['ENCRYPTION_KEY'] = Fernet.generate_key().decode()

from app.db import Base, get_db
from app.main import app, rate_windows


@pytest.fixture()
def database():
    engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    def override():
        with factory() as db:
            yield db
    app.dependency_overrides[get_db] = override
    rate_windows.clear()
    yield factory
    app.dependency_overrides.clear()
    engine.dispose()


@pytest.fixture()
def client(database):
    with TestClient(app, headers={'Origin': 'http://localhost:3000'}) as c:
        yield c


def register(client, email='owner@example.com'):
    result = client.post('/api/v1/auth/register', json={'name': 'Test Developer', 'email': email, 'password': 'a-strong-test-password'})
    assert result.status_code == 200, result.text
    return result.json()


def setup_project(client):
    user = register(client)
    org = client.post('/api/v1/organizations', json={'name': 'Test organization'}).json()
    project = client.post(f'/api/v1/organizations/{org["id"]}/projects', json={'name': 'Test project', 'template': 'python'}).json()
    return user, org, project
