"""Verify schema reversibility in an exclusively owned temporary database."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile

backend = Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory(prefix='devpilot-migrations-') as temporary:
    database = (Path(temporary) / 'verification.db').as_posix()
    environment = {**os.environ, 'DATABASE_URL': 'sqlite:///' + database}
    for operation, target in [('upgrade', 'head'), ('downgrade', 'base'), ('upgrade', 'head')]:
        subprocess.run([sys.executable, '-m', 'alembic', operation, target], cwd=backend, env=environment, check=True)
print('Migration upgrade, downgrade and re-upgrade passed in a temporary database.')
