"""SQL da view mv_fluxo_intermunicipal (RF13/RF14) e seu controle de atualização.

Agrega registros_vacinacao (ativos, VALIDO, com deslocamento real, ou seja
residência != aplicação) por origem, destino, vacina e data. O GET /fluxo/*
lê apenas desta view, nunca agrega em tempo real sobre registros_vacinacao.

Definida como MATERIALIZED VIEW no Postgres (produção/docker) e como VIEW
comum no SQLite (dev.db/test.db locais, que não suportam view materializada) -
por isso é criada e mantida a partir de um único lugar, chamado tanto pela API
(database.py, conftest.py) quanto pelo ETL e pela migração Alembic.

Atualização preguiçosa
----------------------
Com os dados reais a view tem ~486 mil linhas e um REFRESH completo custa
~1,4s. Fazer esse REFRESH a cada escrita em /registros tornava cada cadastro
ou edição ~1,4s mais lento, para recalcular um agregado que ninguém tinha
pedido ainda. Em vez disso, uma escrita apenas marca a view como desatualizada
(um UPDATE de uma linha) e o REFRESH acontece na primeira leitura de /fluxo
que encontrar a marca. O usuário continua vendo os dados atualizados; o custo
sai do caminho de escrita e é pago no máximo uma vez por alteração.
"""

from sqlalchemy import text

VIEW_NAME = "mv_fluxo_intermunicipal"
CONTROLE_TABLE = "fluxo_view_controle"

_SELECT_SQL = """
SELECT
    r.municipio_residencia_id AS municipio_origem_id,
    mo.nome AS municipio_origem_nome,
    r.municipio_vacina_id AS municipio_destino_id,
    md.nome AS municipio_destino_nome,
    r.vacina_id AS vacina_id,
    v.nome AS vacina_nome,
    r.data_vacinacao AS data_vacinacao,
    SUM(r.quantidade) AS total_doses
FROM registros_vacinacao r
JOIN municipios mo ON mo.id_ibge = r.municipio_residencia_id
JOIN municipios md ON md.id_ibge = r.municipio_vacina_id
LEFT JOIN vacinas v ON v.id = r.vacina_id
WHERE r.ativo = true
    AND r.status_dado = 'VALIDO'
    AND r.municipio_residencia_id IS NOT NULL
    AND r.municipio_residencia_id <> r.municipio_vacina_id
GROUP BY
    r.municipio_residencia_id, mo.nome,
    r.municipio_vacina_id, md.nome,
    r.vacina_id, v.nome,
    r.data_vacinacao
"""

# Índices que sustentam os filtros de /fluxo (vacina, período e município).
# Sem eles o Postgres varria as ~486 mil linhas da view a cada consulta.
# Só fazem sentido no Postgres: no SQLite a view não é materializada e não
# aceita índices.
_INDICES = [
    (f"idx_{VIEW_NAME}_vacina", "(vacina_id)"),
    (f"idx_{VIEW_NAME}_data", "(data_vacinacao)"),
    (f"idx_{VIEW_NAME}_origem", "(municipio_origem_id)"),
    (f"idx_{VIEW_NAME}_destino", "(municipio_destino_id)"),
]


def _dialect_name(bind) -> str:
    """Resolve o nome do dialeto tanto para Engine/Connection quanto para Session."""
    if hasattr(bind, "get_bind"):
        return bind.get_bind().dialect.name
    return bind.dialect.name


def create_view_sql(dialect: str) -> str:
    """Retorna o DDL de criação da view, adaptado ao dialeto do banco."""
    if dialect == "postgresql":
        return f"CREATE MATERIALIZED VIEW IF NOT EXISTS {VIEW_NAME} AS {_SELECT_SQL}"
    return f"CREATE VIEW IF NOT EXISTS {VIEW_NAME} AS {_SELECT_SQL}"


def create_indexes_sql(dialect: str) -> list[str]:
    if dialect != "postgresql":
        return []
    return [
        f"CREATE INDEX IF NOT EXISTS {nome} ON {VIEW_NAME} {colunas}"
        for nome, colunas in _INDICES
    ]


def create_controle_sql(dialect: str) -> list[str]:
    """Tabela de uma linha que marca se a view precisa ser reagregada."""
    tipo_bool = "BOOLEAN"
    return [
        f"""CREATE TABLE IF NOT EXISTS {CONTROLE_TABLE} (
                id INTEGER PRIMARY KEY,
                precisa_atualizar {tipo_bool} NOT NULL DEFAULT false
            )""",
        f"INSERT INTO {CONTROLE_TABLE} (id, precisa_atualizar) SELECT 1, false "
        f"WHERE NOT EXISTS (SELECT 1 FROM {CONTROLE_TABLE} WHERE id = 1)",
    ]


def drop_view_sql(dialect: str) -> str:
    if dialect == "postgresql":
        return f"DROP MATERIALIZED VIEW IF EXISTS {VIEW_NAME}"
    return f"DROP VIEW IF EXISTS {VIEW_NAME}"


def ensure_fluxo_view(bind) -> None:
    """Cria a view, seus índices e a tabela de controle, se ainda não existirem.

    `bind` é uma Connection, Engine ou Session.
    """
    dialeto = _dialect_name(bind)
    bind.execute(text(create_view_sql(dialeto)))
    for sql in create_indexes_sql(dialeto):  # pragma: no cover - lista vazia no SQLite
        bind.execute(text(sql))
    for sql in create_controle_sql(dialeto):
        bind.execute(text(sql))


def marcar_fluxo_desatualizado(bind) -> None:
    """Sinaliza que houve escrita em registros_vacinacao.

    Custa um UPDATE de uma linha, e é o que substitui o REFRESH de ~1,4s no
    caminho de escrita de /registros.
    """
    bind.execute(text(f"UPDATE {CONTROLE_TABLE} SET precisa_atualizar = true WHERE id = 1"))


def garantir_fluxo_atualizado(bind) -> bool:
    """Reagrega a view se alguma escrita a marcou como desatualizada.

    Chamado no início das leituras de /fluxo. Retorna True se houve REFRESH.
    No SQLite a view não é materializada (é recalculada a cada consulta), então
    basta limpar a marca.
    """
    marca = bind.execute(
        text(f"SELECT precisa_atualizar FROM {CONTROLE_TABLE} WHERE id = 1")
    ).scalar()
    if not marca:
        return False

    if _dialect_name(bind) == "postgresql":  # pragma: no cover - o banco de teste é SQLite
        bind.execute(text(f"REFRESH MATERIALIZED VIEW {VIEW_NAME}"))
    bind.execute(text(f"UPDATE {CONTROLE_TABLE} SET precisa_atualizar = false WHERE id = 1"))

    # O commit é obrigatório: as leituras usam a sessão de `get_db`, que é
    # fechada sem commit. Sem isto, tanto o REFRESH quanto a baixa da marca
    # seriam desfeitos, e toda leitura de /fluxo reagregaria a view de novo.
    if hasattr(bind, "commit"):
        bind.commit()
    return True
