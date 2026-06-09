"""ensure max_plates column exists in clients table

Revision ID: 4a5b6c7d8e9f
Revises: 3ef63013cff9
Create Date: 2026-06-09 23:30:00.000000

This migration ensures the max_plates column exists in the clients table.
The column was added in migration 3ef63013cff9 but this is a defensive migration
to ensure it exists in all environments, especially production.

The missing max_plates column causes sqlalchemy.exc.ProgrammingError:
column clients.max_plates does not exist
which prevents any Client-related operations (including authentication).

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '4a5b6c7d8e9f'
down_revision: Union[str, None] = '3ef63013cff9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add max_plates column to clients table if it doesn't exist."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = inspector.get_table_names()
    
    if 'clients' in tables:
        columns = {col['name'] for col in inspector.get_columns('clients')}
        if 'max_plates' not in columns:
            # Add the column with a default value
            op.add_column('clients', sa.Column('max_plates', sa.Integer(), nullable=False, server_default='20'))
            # After adding, remove the server_default so it behaves like a normal column
            op.alter_column('clients', 'max_plates', server_default=None)


def downgrade() -> None:
    """Remove max_plates column from clients table if it exists."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = inspector.get_table_names()
    
    if 'clients' in tables:
        columns = {col['name'] for col in inspector.get_columns('clients')}
        if 'max_plates' in columns:
            op.drop_column('clients', 'max_plates')
