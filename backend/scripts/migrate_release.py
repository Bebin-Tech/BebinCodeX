"""Apply additive release migrations, serialized across concurrent Vercel builds."""
from pathlib import Path
import sys
from alembic import command
from alembic.config import Config
from sqlalchemy import text

backend = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(backend))
from app.db import engine

config = Config(str(backend / 'alembic.ini'))
config.set_main_option('script_location', str(backend / 'migrations'))
with engine.connect() as connection:
    postgres = engine.dialect.name == 'postgresql'
    if postgres:
        connection.execute(text('SELECT pg_advisory_lock(642017295)'))
    try:
        command.upgrade(config, 'head')
        print('Database migrations are current.')
    finally:
        if postgres:
            connection.execute(text('SELECT pg_advisory_unlock(642017295)'))
