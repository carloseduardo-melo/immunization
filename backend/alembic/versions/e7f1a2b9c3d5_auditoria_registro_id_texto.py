"""log_auditoria: registro_id como texto e indices dos filtros do RF22

Revision ID: e7f1a2b9c3d5
Revises: d1e2f3a4b5c6
Create Date: 2026-08-27 10:30:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "e7f1a2b9c3d5"
down_revision: Union[str, Sequence[str], None] = "d1e2f3a4b5c6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """RF21 - o log passa a cobrir municipios e vacinas, cujas chaves não são UUID.

    `registro_id` vira texto para acomodar o id_ibge (string de 7 dígitos) e o
    id inteiro de vacinas, além do UUID de registros_vacinacao que já gravava.
    Os dois índices novos servem aos filtros de período e de usuário do RF22.
    """
    with op.batch_alter_table("log_auditoria") as batch:
        batch.alter_column(
            "registro_id",
            existing_type=sa.UUID(),
            type_=sa.String(length=50),
            existing_nullable=False,
            postgresql_using="registro_id::text",
        )

    op.create_index("idx_auditoria_criado_em", "log_auditoria", ["criado_em"])
    op.create_index("idx_auditoria_usuario", "log_auditoria", ["usuario_id"])


def downgrade() -> None:
    """Volta registro_id a UUID. Só é reversível se o log tiver apenas UUIDs."""
    op.drop_index("idx_auditoria_usuario", table_name="log_auditoria")
    op.drop_index("idx_auditoria_criado_em", table_name="log_auditoria")

    with op.batch_alter_table("log_auditoria") as batch:
        batch.alter_column(
            "registro_id",
            existing_type=sa.String(length=50),
            type_=sa.UUID(),
            existing_nullable=False,
            postgresql_using="registro_id::uuid",
        )
