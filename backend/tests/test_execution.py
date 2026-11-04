"""Security/lifecycle tests use explicit SDK fixtures; production never simulates execution."""
from contextlib import asynccontextmanager
from datetime import timedelta
from types import SimpleNamespace
import json
import pytest
from sqlalchemy import select
from .conftest import setup_project, register
from app import execution as service
from app.models import Execution, File, Member, now


class Files:
    def __init__(self):
        self.writes = {}

    async def mkdir(self, path):
        pass

    async def write_text(self, path, content):
        self.writes[path] = content

    def batch(self):
        owner = self
        class Batch:
            async def __aenter__(self): return self
            async def __aexit__(self, *args): pass
            def write_text(self, path, content): owner.writes[path] = content
        return Batch()


@pytest.fixture
def sdk(monkeypatch):
    box = SimpleNamespace(fs=Files(), status='running', routes=[SimpleNamespace(port=3000, url='https://fixture-3000.vercel.run')], destroyed=False, options=[], commands=[])
    async def create(**options):
        box.options.append(options)
        return box
    async def get(**kwargs): return box
    async def destroy(**kwargs): box.destroyed = True
    async def run(command, args, **kwargs):
        box.commands.append((command, args))
        if args[0] == '/vercel/sandbox/bxc-runner.py':
            return SimpleNamespace(returncode=0, stdout=json.dumps({'stdout':'fixture output\n', 'stderr':'', 'exit_code':0, 'reason':''}))
        return SimpleNamespace(returncode=0, stdout='')
    async def process(*args, **kwargs): return SimpleNamespace()
    @asynccontextmanager
    async def api_session(): yield
    box.run_process, box.create_process, box.destroy = run, process, destroy
    monkeypatch.setattr(service.settings, 'sandbox_enabled', True)
    monkeypatch.setattr(service, 'sandbox_api', api_session)
    monkeypatch.setattr(service.sandbox, 'create_sandbox', create)
    monkeypatch.setattr(service.sandbox, 'get_sandbox', get)
    return box


def test_run_uses_remote_box_and_cleans_up(client, database, sdk):
    _, _, p = setup_project(client)
    result = client.post(f'/api/v1/projects/{p["id"]}/sandbox', json={'path':'main.py'})
    assert result.status_code == 200, result.text
    assert result.json()['status'] == 'completed'
    assert result.json()['exit_code'] == 0
    assert 'fixture output' in result.json()['output']
    assert sdk.destroyed
    assert sdk.options[0]['persistent'] is False
    assert sdk.options[0]['resources'].vcpus == 1
    assert sdk.options[0]['network_policy'] == service.NetworkPolicy.deny_all()
    assert sdk.options[0]['env'] == {}
    assert any('/workspace/main.py' in value for _, args in sdk.commands for value in args)
    with database() as db:
        assert db.scalar(select(Execution)).status == 'completed'


def test_failed_supervisor_still_destroys_sandbox(client, sdk):
    _, _, p = setup_project(client)
    async def fail(*args, **kwargs): raise RuntimeError('provider failure with private detail')
    sdk.run_process = fail
    result = client.post(f'/api/v1/projects/{p["id"]}/sandbox', json={'path':'main.py'}).json()
    assert result['status'] == 'failed'
    assert 'private detail' not in result['output']
    assert sdk.destroyed


@pytest.mark.parametrize('path', ['../escape.py','/absolute.py','main.py;echo hi','DEVPILOT.md'])
def test_invalid_run_paths_never_start_sandbox(client, sdk, path):
    _, _, p = setup_project(client)
    result = client.post(f'/api/v1/projects/{p["id"]}/sandbox', json={'path':path})
    assert result.status_code == 422
    assert not sdk.options


def test_other_tenant_and_viewer_cannot_execute(client, database, sdk):
    user, org, p = setup_project(client)
    with database() as db:
        db.scalar(select(Member).where(Member.user_id == user['id'])).role = 'viewer'
        db.commit()
    assert client.post(f'/api/v1/projects/{p["id"]}/sandbox', json={'path':'main.py'}).status_code == 403
    assert not sdk.options
    client.post('/api/v1/auth/logout')
    register(client,'another@example.com')
    assert client.post(f'/api/v1/projects/{p["id"]}/sandbox', json={'path':'main.py'}).status_code == 404
    assert not sdk.options


def web_file(client, p):
    assert client.put(f'/api/v1/projects/{p["id"]}/files',json={'path':'index.html','content':'<h1>First version</h1>','revision':0}).status_code == 200


def test_preview_refresh_stop_and_url_encryption(client, database, sdk):
    _, _, p = setup_project(client)
    web_file(client,p)
    result = client.post(f'/api/v1/projects/{p["id"]}/preview',json={'path':'index.html'})
    assert result.status_code == 200, result.text
    preview = result.json()
    assert preview['status'] == 'running'
    assert preview['preview_url'].startswith('https://fixture-3000.vercel.run/')
    assert not sdk.destroyed
    assert sdk.options[0]['ports'] == [3000]
    with database() as db:
        row = db.get(Execution,preview['id'])
        assert row.encrypted_preview != preview['preview_url']
        assert 'vercel.run' not in row.encrypted_preview
    assert client.post(f'/api/v1/projects/{p["id"]}/preview',json={'path':'index.html'}).status_code == 409
    client.put(f'/api/v1/projects/{p["id"]}/files',json={'path':'index.html','content':'<h1>Updated version</h1>','revision':1})
    refreshed = client.put(f'/api/v1/executions/{preview["id"]}/preview').json()
    assert refreshed['revision'] == 2
    assert refreshed['preview_url'] != preview['preview_url']
    assert '<h1>Updated version</h1>' in sdk.fs.writes.values()
    assert len(sdk.options) == 1  # saved edits reuse the VM
    stopped = client.delete(f'/api/v1/executions/{preview["id"]}').json()
    assert stopped['status'] == 'stopped'
    assert stopped['preview_url'] is None
    assert sdk.destroyed


def test_expired_preview_never_resumes(client, database, sdk):
    _, _, p = setup_project(client)
    web_file(client,p)
    preview = client.post(f'/api/v1/projects/{p["id"]}/preview',json={'path':'index.html'}).json()
    with database() as db:
        db.get(Execution,preview['id']).expires_at = now() - timedelta(seconds=1)
        db.commit()
    assert client.put(f'/api/v1/executions/{preview["id"]}/preview').status_code == 410
    result = client.get(f'/api/v1/projects/{p["id"]}/executions').json()[0]
    assert result['status'] == 'expired' and result['preview_url'] is None


def test_daily_session_quota(client, database, sdk):
    user, _, p = setup_project(client)
    with database() as db:
        for _ in range(60):
            db.add(Execution(project_id=p['id'],user_id=user['id'],kind='run',path='main.py',revision=0,status='completed',expires_at=now()))
        db.commit()
    assert client.post(f'/api/v1/projects/{p["id"]}/sandbox',json={'path':'main.py'}).status_code == 429
    assert not sdk.options
