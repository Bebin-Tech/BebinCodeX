import io
import zipfile
from datetime import timedelta
import pytest
from sqlalchemy import select
from .conftest import register, setup_project
from app.models import AgentRun, File, Member, User, Connection, Organization, Usage, now
from app.gateway import Gateway
from app.security import safe_path, redact, cipher


def test_session_logout_and_csrf(client):
    assert client.get('/api/v1/auth/me').status_code == 401
    user = register(client)
    assert 'password' not in str(user)
    assert client.get('/api/v1/auth/me').json()['id'] == user['id']
    assert client.post('/api/v1/organizations', json={'name': 'evil'}, headers={'Origin': 'https://evil.example'}).status_code == 403
    assert client.post('/api/v1/auth/logout').status_code == 200
    assert client.get('/api/v1/auth/me').status_code == 401


def test_password_validation(client):
    assert client.post('/api/v1/auth/register', json={'email': 'a@example.com', 'password': 'short'}).status_code == 422
    register(client)
    assert client.post('/api/v1/auth/login', json={'email': 'owner@example.com', 'password': 'incorrect-password'}).status_code == 401


def test_tenant_boundary(client):
    _, org, project = setup_project(client)
    client.post('/api/v1/auth/logout')
    register(client, 'other@example.com')
    for path in [f'/organizations/{org["id"]}/projects', f'/organizations/{org["id"]}/members', f'/organizations/{org["id"]}/usage', f'/projects/{project["id"]}', f'/projects/{project["id"]}/files', f'/projects/{project["id"]}/runs', f'/projects/{project["id"]}/export']:
        assert client.get('/api/v1' + path).status_code == 404, path
    assert client.put(f'/api/v1/projects/{project["id"]}/files', json={'path': 'main.py', 'content': 'evil', 'revision': 0}).status_code == 404


def test_file_versions_and_optimistic_concurrency(client):
    _, _, p = setup_project(client)
    endpoint = f'/api/v1/projects/{p["id"]}/files'
    assert client.put(endpoint, json={'path': 'main.py', 'content': 'print(42)', 'revision': 0}).json()['revision'] == 1
    assert client.put(endpoint, json={'path': 'main.py', 'content': 'overwrite', 'revision': 0}).status_code == 409
    history = client.get(f'/api/v1/projects/{p["id"]}/history?path=main.py').json()
    assert len(history) == 1
    assert 'def greet' in history[0]['content']
    assert client.get(endpoint).json()[1]['content'] == 'print(42)'


@pytest.mark.parametrize('path', ['../escape', '/absolute', 'C:/file', 'a\\b', 'a/../b', '.env', 'a//b', './file', 'a/./b', 'a/.git/config'])
def test_path_traversal_denied(client, path):
    _, _, p = setup_project(client)
    assert client.put(f'/api/v1/projects/{p["id"]}/files', json={'path': path, 'content': 'x', 'revision': 0}).status_code == 422


def test_secret_scanning_and_redaction(client):
    _, _, p = setup_project(client)
    secret = 'sk-' + 'a' * 40
    assert client.put(f'/api/v1/projects/{p["id"]}/files', json={'path': 'config.py', 'content': secret, 'revision': 0}).status_code == 422
    assert secret not in redact(secret + ' person@example.com')
    assert 'person@example.com' not in redact('person@example.com')


def test_zip_slip_and_roundtrip(client):
    _, _, p = setup_project(client)
    endpoint = f'/api/v1/projects/{p["id"]}'
    raw = client.get(endpoint + '/export').content
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        assert 'main.py' in archive.namelist()
    assert client.post(endpoint + '/import?revision=0', content=raw, headers={'Content-Type': 'application/zip'}).status_code == 200
    malicious = io.BytesIO()
    with zipfile.ZipFile(malicious, 'w') as archive:
        archive.writestr('../escape.py', 'bad')
    assert client.post(endpoint + '/import?revision=1', content=malicious.getvalue()).status_code == 422


def test_invitations_and_viewer_cannot_edit(client):
    _, org, p = setup_project(client)
    token = client.post(f'/api/v1/organizations/{org["id"]}/invitations', json={'email': 'viewer@example.com', 'role': 'viewer'}).json()['token']
    client.post('/api/v1/auth/logout')
    register(client, 'viewer@example.com')
    assert client.post('/api/v1/invitations/accept', json={'token': token}).status_code == 200
    assert client.post('/api/v1/invitations/accept', json={'token': token}).status_code == 404
    assert client.get(f'/api/v1/projects/{p["id"]}/files').status_code == 200
    assert client.put(f'/api/v1/projects/{p["id"]}/files', json={'path': 'test.py', 'content': 'bad', 'revision': 0}).status_code == 403
    assert client.get(f'/api/v1/organizations/{org["id"]}/audit').status_code == 403


def test_credentials_encrypted_and_local_policy(client, database):
    user, org, _ = setup_project(client)
    endpoint = f'/api/v1/organizations/{org["id"]}'
    result = client.post(endpoint + '/connections', json={'provider': 'openai', 'label': 'Primary', 'api_key': 'test-provider-credential'})
    assert result.status_code == 200
    assert 'credential' not in result.text
    with database() as db:
        stored = db.get(Connection, result.json()['id'])
        assert stored.encrypted_key != 'test-provider-credential'
        assert cipher().decrypt(stored.encrypted_key.encode()).decode() == 'test-provider-credential'
    assert client.put(endpoint + '/policy', json={'local_only': True, 'monthly_token_limit': 1000000}).status_code == 200
    assert client.get(f'/api/v1/connections/{result.json()["id"]}/models').status_code == 403
    assert client.post(endpoint + '/connections', json={'provider': 'openai', 'label': 'No', 'api_key': 'x'}).status_code == 403


def proposal(database, user, p):
    with database() as db:
        snapshot = {f.path: f.content for f in db.scalars(select(File).where(File.project_id == p['id']))}
        run = AgentRun(project_id=p['id'], user_id=user['id'], prompt='test proposal', status='awaiting_approval', model='test-only', base_revision=0, snapshot=snapshot, proposal=[{'path': 'main.py', 'content': 'print(123)'}, {'path': 'new.py', 'content': 'print(456)'}])
        db.add(run)
        db.commit()
        return run.id


def test_agent_approval_rollback_and_conflicts(client, database):
    user, org, p = setup_project(client)
    run_id = proposal(database, user, p)
    assert client.post(f'/api/v1/runs/{run_id}/apply', json={'paths': ['not-proposed.py']}).status_code == 422
    assert client.post(f'/api/v1/runs/{run_id}/apply', json={'paths': ['main.py']}).status_code == 200
    paths = {f['path']: f['content'] for f in client.get(f'/api/v1/projects/{p["id"]}/files').json()}
    assert paths['main.py'] == 'print(123)'
    assert 'new.py' not in paths
    assert client.post(f'/api/v1/runs/{run_id}/apply', json={'paths': ['main.py']}).status_code == 409
    assert client.post(f'/api/v1/runs/{run_id}/rollback').status_code == 200
    paths = {f['path']: f['content'] for f in client.get(f'/api/v1/projects/{p["id"]}/files').json()}
    assert 'def greet' in paths['main.py']


def test_stale_agent_proposal_cannot_apply(client, database):
    user, org, p = setup_project(client)
    run_id = proposal(database, user, p)
    client.put(f'/api/v1/projects/{p["id"]}/files', json={'path': 'main.py', 'content': 'newer work', 'revision': 0})
    assert client.post(f'/api/v1/runs/{run_id}/apply', json={'paths': ['main.py']}).status_code == 409


def test_agent_read_tool_workflow_fixture(client, database, monkeypatch):
    # Test-only provider fixture. Product execution always uses a real provider.
    _, org, p = setup_project(client)
    connection = client.post(f'/api/v1/organizations/{org["id"]}/connections', json={'provider': 'ollama', 'label': 'Local'}).json()
    calls = []
    async def complete(self, model, messages, tools):
        calls.append(messages[-1])
        if len(calls) == 1:
            return {'role': 'assistant', 'content': '', 'tool_calls': [{'id': 'c1', 'type': 'function', 'function': {'name': 'read_file', 'arguments': '{"path":"main.py"}'}}]}, {'input_tokens': 10, 'output_tokens': 5}
        assert messages[-1]['role'] == 'tool'
        assert 'def greet' in messages[-1]['content']
        return {'role': 'assistant', 'content': '{"summary":"Reviewed change. Tests not run.","changes":[{"path":"main.py","content":"print(42)"}]}'}, {'input_tokens': 20, 'output_tokens': 15}
    monkeypatch.setattr(Gateway, 'complete', complete)
    response = client.post(f'/api/v1/projects/{p["id"]}/runs', json={'prompt': 'Improve code', 'connection_id': connection['id'], 'model': 'fixture-model'})
    assert response.status_code == 200, response.text
    assert response.json()['status'] == 'awaiting_approval'
    assert len(calls) == 2
    with database() as db:
        assert db.get(Organization, org['id']).reserved_tokens == 0
        usage = db.scalar(select(Usage))
        assert usage.input_tokens == 30 and usage.output_tokens == 20
        assert 'def greet' in db.scalar(select(File).where(File.path == 'main.py')).content


def test_unavailable_sandbox_is_explicit(client):
    _, _, p = setup_project(client)
    assert client.post(f'/api/v1/projects/{p["id"]}/sandbox').status_code == 503
