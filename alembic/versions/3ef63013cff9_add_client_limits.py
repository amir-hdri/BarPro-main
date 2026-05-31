"""add client limits

Revision ID: 3ef63013cff9
Revises: 011_add_driver_plates
Create Date: 2026-05-31 18:03:54.770605

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = '3ef63013cff9'
down_revision: Union[str, None] = '011_add_driver_plates'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('clients', sa.Column('max_plates', sa.Integer(), nullable=False, server_default='20'))


def downgrade() -> None:
    op.drop_column('clients', 'max_plates')
