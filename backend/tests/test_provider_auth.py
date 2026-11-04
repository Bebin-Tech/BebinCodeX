import asyncio
from types import SimpleNamespace
import httpx
import pytest
from fastapi import HTTPException
from sqlalchemy import select
from .conftest import setup_project, register
from app import gateway
from app.models import Connection, Member
from app.security import cipher, normalize_api_key


@pytest.mark.parametrize('value', ['  fixture-key  ', 'Bearer fixture-key', '"fixture-key"', "'fixture-key'", '"Bearer fixture-key"'])
def test_pasted_credential_wrappers_are_normalized(value):
    assert normalize_api_key(value) == 'fixture-key'


def test_openai_401_has_safe_auth_guidance_and_is_not_retried(monkeypatch):
    key = 'fake-openai-credential-for-test'
    connection = SimpleNamespace(provider='openai', encrypted_key=cipher().encrypt(('  Bearer ' + key + '  ').encode()).decode())
    seen = []
    def transport(request):
        seen.append(request)
        return httpx.Response(401, json={'error': {'message': 'Incorrect API key provided: ' + key}})
    original = httpx.AsyncClient
    monkeypatch.setattr(gateway.httpx, 'AsyncClient', lambda **kwargs: original(transport=httpx.MockTransport(transport), **kwargs))
    gateway.failures.clear()
    with pytest.raises(HTTPException) as error:
        asyncio.run(gateway.Gateway(connection).models())
    assert error.value.status_code == 422
    assert 'OpenAI rejected the API key (401)' in error.value.detail
    assert 'Update key' in error.value.detail
    assert key not in error.value.detail
    assert len(seen) == 1
    assert seen[0].headers['Authorization'] == 'Bearer ' + key
    assert seen[0].url.path == '/v1/models'


def test_openai_model_discovery_uses_normalized_bearer_header(monkeypatch):
    connection = SimpleNamespace(provider='openai', encrypted_key=cipher().encrypt(b' Bearer fixture-key ').decode())
    def transport(request):
        assert request.headers['Authorization'] == 'Bearer fixture-key'
        return httpx.Response(200, json={'data':[{'id':'model-b'},{'id':'model-a'}]})
    original = httpx.AsyncClient
    monkeypatch.setattr(gateway.httpx, 'AsyncClient', lambda **kwargs: original(transport=httpx.MockTransport(transport), **kwargs))
    gateway.failures.clear()
    assert asyncio.run(gateway.Gateway(connection).models()) == ['model-a','model-b']


def test_replace_key_keeps_connection_and_never_returns_secret(client, database):
    _, org, _ = setup_project(client)
    connection = client.post(f'/api/v1/organizations/{org["id"]}/connections',json={'provider':'openai','label':'My provider','api_key':'  Bearer original-fixture-key  '}).json()
    with database() as db:
        assert cipher().decrypt(db.get(Connection,connection['id']).encrypted_key.encode()).decode() == 'original-fixture-key'
    replacement = 'replacement-fixture-key'
    response = client.put(f'/api/v1/connections/{connection["id"]}',json={'api_key':' "'+replacement+'" '})
    assert response.status_code == 200
    assert response.json() == connection
    assert replacement not in response.text
    with database() as db:
        assert cipher().decrypt(db.get(Connection,connection['id']).encrypted_key.encode()).decode() == replacement


def test_key_update_requires_connection_owner_and_write_role(client, database):
    user, org, _ = setup_project(client)
    connection = client.post(f'/api/v1/organizations/{org["id"]}/connections',json={'provider':'openai','label':'My provider','api_key':'fixture-key'}).json()
    with database() as db:
        db.scalar(select(Member).where(Member.user_id == user['id'])).role = 'viewer'
        db.commit()
    assert client.put(f'/api/v1/connections/{connection["id"]}',json={'api_key':'replacement'}).status_code == 403
    client.post('/api/v1/auth/logout')
    register(client,'other-owner@example.com')
    assert client.put(f'/api/v1/connections/{connection["id"]}',json={'api_key':'replacement'}).status_code == 404


def test_invalid_keys_and_validation_errors_do_not_echo_keys(client):
    _, org, _ = setup_project(client)
    for key in ['private key\nwith spaces', 'private-test-value-'*200]:
        response = client.post(f'/api/v1/organizations/{org["id"]}/connections',json={'provider':'openai','label':'Bad','api_key':key})
        assert response.status_code == 422
        assert key not in response.text
        assert 'private-test-value-' not in response.text
