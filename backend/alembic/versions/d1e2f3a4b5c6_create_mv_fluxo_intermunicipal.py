"""create mv_fluxo_intermunicipal materialized view (RF13/RF14)

Revision ID: d1e2f3a4b5c6
Revises: a9d4e7f2c1b3
Create Date: 2026-08-19 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op

import os
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "backend")))
from app.sql_views import (  # noqa: E402
    CONTROLE_TABLE,
    create_controle_sql,
    create_indexes_sql,
    create_view_sql,
    drop_view_sql,
)


# revision identifiers, used by Alembic.
revision: str = 'd1e2f3a4b5c6'
down_revision: Union[str, Sequence[str], None] = 'a9d4e7f2c1b3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute(create_view_sql("postgresql"))
    for sql in create_indexes_sql("postgresql"):
        op.execute(sql)
    for sql in create_controle_sql("postgresql"):
        op.execute(sql)


def downgrade() -> None:
    """Downgrade schema."""
    # Os índices caem junto com a view materializada.
    op.execute(drop_view_sql("postgresql"))
    op.execute(f"DROP TABLE IF EXISTS {CONTROLE_TABLE}")
