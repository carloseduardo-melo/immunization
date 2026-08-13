"""add regiao_saude, polo, timestamps to municipios

Revision ID: f3a9c1d2b7e4
Revises: c5c1364dfc81
Create Date: 2026-08-13 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f3a9c1d2b7e4'
down_revision: Union[str, Sequence[str], None] = 'c5c1364dfc81'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('municipios', sa.Column('regiao_saude', sa.String(length=150), nullable=True))
    op.add_column('municipios', sa.Column('polo', sa.Boolean(), server_default=sa.text('false'), nullable=False))
    op.add_column('municipios', sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False))
    op.add_column('municipios', sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('municipios', 'updated_at')
    op.drop_column('municipios', 'created_at')
    op.drop_column('municipios', 'polo')
    op.drop_column('municipios', 'regiao_saude')
