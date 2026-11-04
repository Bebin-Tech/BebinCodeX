"""Tenant-scoped sandbox execution and preview records."""
import sqlalchemy as sa
from alembic import op

revision = '0002'
down_revision = '0001'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('execution_sessions',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('project_id', sa.String(36), sa.ForeignKey('projects.id'), nullable=False),
        sa.Column('user_id', sa.String(36), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('kind', sa.String(16), nullable=False),
        sa.Column('path', sa.String(512), nullable=False),
        sa.Column('revision', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(24), nullable=False),
        sa.Column('sandbox_name', sa.String(120), nullable=False),
        sa.Column('output', sa.Text(), nullable=False),
        sa.Column('exit_code', sa.Integer(), nullable=True),
        sa.Column('encrypted_preview', sa.Text(), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    )
    for column in ('project_id', 'user_id', 'expires_at'):
        op.create_index(f'ix_execution_sessions_{column}', 'execution_sessions', [column])


def downgrade():
    op.drop_table('execution_sessions')
