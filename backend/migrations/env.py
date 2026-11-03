from alembic import context
from app.config import settings
from app.db import Base, engine
from app import models

if context.is_offline_mode():
    context.configure(url=settings.database_url, target_metadata=Base.metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()
else:
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=Base.metadata, render_as_batch=settings.database_url.startswith('sqlite'))
        with context.begin_transaction():
            context.run_migrations()
