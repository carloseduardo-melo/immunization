"""add ativo to registros_vacinacao

Revision ID: a9d4e7f2c1b3
Revises: f3a9c1d2b7e4
Create Date: 2026-08-14 14:30:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "a9d4e7f2c1b3"
down_revision: Union[str, Sequence[str], None] = "f3a9c1d2b7e4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Adiciona o marcador usado pela exclusão lógica dos registros."""
    op.add_column(
        "registros_vacinacao",
        sa.Column(
            "ativo",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    """Remove o marcador de exclusão lógica."""
    op.drop_column("registros_vacinacao", "ativo")
