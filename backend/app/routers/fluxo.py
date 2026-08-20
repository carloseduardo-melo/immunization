from datetime import date
from math import ceil
from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.schemas import (
    FluxoIntermunicipalItem,
    FluxoIntermunicipalResponse,
    FluxoRankingResponse,
    RankingMunicipioItem,
)
from app.sql_views import VIEW_NAME, garantir_fluxo_atualizado

router = APIRouter(prefix="/fluxo", tags=["Fluxo Intermunicipal"])

# A view tem ~486 mil linhas e ~39 mil pares origem/destino distintos. Nenhum
# endpoint daqui devolve o conjunto completo: a agregação e o corte acontecem
# no banco, para que o payload enviado à tela seja sempre pequeno.
PAGE_SIZE_MAXIMO = 200
PAGE_SIZE_PADRAO = 25
RANKING_LIMITE_MAXIMO = 50


def _filtros_sql(
    vacina_id: Optional[int],
    data_inicio: Optional[date],
    data_fim: Optional[date],
    municipio_id: Optional[str] = None,
):
    """Monta o WHERE aplicado à view. Filtrar aqui (e não em pandas) é o que
    mantém o volume trafegado proporcional ao que a tela realmente mostra."""
    condicoes = []
    params: dict = {}
    if vacina_id is not None:
        condicoes.append("vacina_id = :vacina_id")
        params["vacina_id"] = vacina_id
    if data_inicio is not None:
        condicoes.append("data_vacinacao >= :data_inicio")
        params["data_inicio"] = data_inicio
    if data_fim is not None:
        condicoes.append("data_vacinacao <= :data_fim")
        params["data_fim"] = data_fim
    if municipio_id:
        condicoes.append(
            "(municipio_origem_id = :municipio_id OR municipio_destino_id = :municipio_id)"
        )
        params["municipio_id"] = municipio_id
    where_sql = f"WHERE {' AND '.join(condicoes)}" if condicoes else ""
    return where_sql, params


@router.get(
    "/intermunicipal",
    response_model=FluxoIntermunicipalResponse,
    summary="Fluxo de mobilidade vacinal entre municípios (origem x destino)",
    responses={401: {"description": "Token ausente ou inválido."}},
)
def obter_fluxo_intermunicipal(
    vacina_id: Optional[int] = None,
    data_inicio: Optional[date] = None,
    data_fim: Optional[date] = None,
    municipio_id: Optional[str] = None,
    page: int = 1,
    page_size: int = PAGE_SIZE_PADRAO,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """RF13 - Retorna os pares (município de residência, município de aplicação)
    com o total de doses, ordenados do maior fluxo para o menor, para montar a
    tabela/mapa de calor origem x destino.

    Lê exclusivamente da view `mv_fluxo_intermunicipal`, sem agregar em tempo
    real sobre `registros_vacinacao`. A resposta é sempre paginada: existem
    dezenas de milhares de pares, e devolver todos inviabilizaria a tela.
    Aceita filtros opcionais por vacina, período e município."""
    if page < 1:
        page = 1
    if page_size < 1:
        page_size = PAGE_SIZE_PADRAO
    if page_size > PAGE_SIZE_MAXIMO:
        page_size = PAGE_SIZE_MAXIMO

    garantir_fluxo_atualizado(db)
    where_sql, params = _filtros_sql(vacina_id, data_inicio, data_fim, municipio_id)

    # Totais do recorte (quantos pares existem e quantas doses no total),
    # para a tela informar "top N de X" sem precisar baixar os X.
    resumo = db.execute(
        text(f"""
            SELECT count(*) AS total_pares, COALESCE(SUM(total_doses), 0) AS total_doses
            FROM (
                SELECT SUM(total_doses) AS total_doses
                FROM {VIEW_NAME}
                {where_sql}
                GROUP BY municipio_origem_id, municipio_destino_id
            ) pares
        """),
        params,
    ).mappings().one()

    total = int(resumo["total_pares"])
    total_pages = ceil(total / page_size) if total else 0

    rows = db.execute(
        text(f"""
            SELECT
                municipio_origem_id,
                MIN(municipio_origem_nome) AS municipio_origem_nome,
                municipio_destino_id,
                MIN(municipio_destino_nome) AS municipio_destino_nome,
                SUM(total_doses) AS total_doses
            FROM {VIEW_NAME}
            {where_sql}
            GROUP BY municipio_origem_id, municipio_destino_id
            ORDER BY total_doses DESC, municipio_origem_id, municipio_destino_id
            LIMIT :limit OFFSET :offset
        """),
        {**params, "limit": page_size, "offset": (page - 1) * page_size},
    ).mappings().all()

    return FluxoIntermunicipalResponse(
        items=[FluxoIntermunicipalItem(**row) for row in rows],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
        total_doses=int(resumo["total_doses"]),
    )


@router.get(
    "/ranking",
    response_model=FluxoRankingResponse,
    summary="Ranking de municípios-polo e municípios de evasão",
    responses={401: {"description": "Token ausente ou inválido."}},
)
def obter_ranking_fluxo(
    vacina_id: Optional[int] = None,
    data_inicio: Optional[date] = None,
    data_fim: Optional[date] = None,
    limit: int = 10,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """RF14 - Calcula, a partir da view `mv_fluxo_intermunicipal`, o total
    recebido (como destino), o total perdido (como origem) e o saldo líquido de
    cada município, retornando o top N municípios-polo (maior saldo) e o top N
    municípios de evasão (menor saldo).

    A agregação por município é feita no banco: as ~486 mil linhas da view são
    reduzidas a uma linha por município antes de chegar ao Python."""
    if limit < 1:
        limit = 10
    if limit > RANKING_LIMITE_MAXIMO:
        limit = RANKING_LIMITE_MAXIMO

    garantir_fluxo_atualizado(db)
    where_sql, params = _filtros_sql(vacina_id, data_inicio, data_fim)

    rows = db.execute(
        text(f"""
            SELECT
                municipio_id,
                MIN(municipio_nome) AS municipio_nome,
                SUM(recebido) AS total_recebido,
                SUM(perdido) AS total_perdido,
                SUM(recebido) - SUM(perdido) AS saldo_liquido
            FROM (
                SELECT
                    municipio_destino_id AS municipio_id,
                    municipio_destino_nome AS municipio_nome,
                    total_doses AS recebido,
                    0 AS perdido
                FROM {VIEW_NAME}
                {where_sql}
                UNION ALL
                SELECT
                    municipio_origem_id,
                    municipio_origem_nome,
                    0 AS recebido,
                    total_doses AS perdido
                FROM {VIEW_NAME}
                {where_sql}
            ) movimentos
            GROUP BY municipio_id
            ORDER BY saldo_liquido DESC
        """),
        params,
    ).mappings().all()

    ranking = [RankingMunicipioItem(**row) for row in rows]

    # Já vem ordenado por saldo decrescente: o topo são os polos e a cauda,
    # invertida, são os municípios de maior evasão.
    top_polo = ranking[:limit]
    top_evasao = list(reversed(ranking[-limit:]))

    return FluxoRankingResponse(top_polo=top_polo, top_evasao=top_evasao)
