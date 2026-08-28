"""usuarios_admin: coluna municipio_alocado_id

Revision ID: f7c2a4d9e1b3
Revises: e7f1a2b9c3d5
Create Date: 2026-08-28 09:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "f7c2a4d9e1b3"
down_revision: Union[str, Sequence[str], None] = "e7f1a2b9c3d5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _tem_coluna(nome: str) -> bool:
    return nome in {
        coluna["name"] for coluna in sa.inspect(op.get_bind()).get_columns("usuarios_admin")
    }


def upgrade() -> None:
    """Alinha as migrations ao model, que ja declarava a coluna.

    `municipio_alocado_id` entrou em `UsuarioAdmin` sem migration correspondente:
    os bancos existentes ganharam a coluna pelo `create_all()` do `init_db()`, e o
    desvio so aparece quando alguem cria um banco a partir das migrations.

    A guarda de existencia e o que permite rodar isto sobre um banco que ja foi
    criado pelo `create_all()` - o caso de producao - sem colidir.
    """
    if not _tem_coluna("municipio_alocado_id"):
        op.add_column(
            "usuarios_admin",
            sa.Column("municipio_alocado_id", sa.String(length=7), nullable=True),
        )


def downgrade() -> None:
    if _tem_coluna("municipio_alocado_id"):
        op.drop_column("usuarios_admin", "municipio_alocado_id")
